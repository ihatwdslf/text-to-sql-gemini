"""
Робота з базою даних SQLite:
  * опис схеми для Gemini;
  * перевірка безпеки SQL;
  * виконання запиту в режимі «лише читання».
"""
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from app.config import MAX_ROWS, SQL_TIMEOUT_SEC


class UnsafeSQLError(Exception):
    """Запит намагається змінити базу або містить кілька команд."""


# ---------------------------------------------------------------- схема бази

def get_schema(db_path: Path, sample_rows: int = 3) -> str:
    """
    Текстовий опис бази для промпту: CREATE TABLE кожної таблиці
    (разом з коментарями до колонок) + кілька прикладів рядків.
    Приклади допомагають моделі зрозуміти формат даних
    (наприклад, що дати мають вигляд '2025-03-14', а статуси – англійською).
    """
    con = _connect_readonly(db_path)
    try:
        parts = []
        tables = con.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        for name, create_sql in tables:
            parts.append(create_sql.strip() + ";")
            cur = con.execute(f'SELECT * FROM "{name}" LIMIT {sample_rows}')
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            if rows:
                parts.append(f"-- Приклади рядків з {name}: " + " | ".join(cols))
                parts.extend("--   " + " | ".join(map(str, r)) for r in rows)
            parts.append("")
        return "\n".join(parts)
    finally:
        con.close()


def get_tables(db_path: Path) -> list[dict]:
    """Структура бази для показу в інтерфейсі: таблиці, колонки, кількість рядків."""
    con = _connect_readonly(db_path)
    try:
        result = []
        names = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        for name in names:
            columns = [{"name": c[1], "type": c[2], "pk": bool(c[5])}
                       for c in con.execute(f'PRAGMA table_info("{name}")')]
            count = con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            result.append({"name": name, "columns": columns, "rows": count})
        return result
    finally:
        con.close()


# ---------------------------------------------------------- безпека запиту

FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|TRUNCATE|ATTACH|DETACH|"
    r"PRAGMA|VACUUM|REINDEX|GRANT|REVOKE)\b",
    re.IGNORECASE,
)


def clean_sql(sql: str) -> str:
    """Прибирає ```sql ... ``` обгортку і крапку з комою в кінці."""
    sql = sql.strip()
    sql = re.sub(r"^```(?:sql)?\s*|\s*```$", "", sql, flags=re.IGNORECASE).strip()
    return sql.rstrip(";").strip()


def validate_sql(sql: str) -> str:
    """
    Перший рівень захисту – перевірка тексту запиту.
    Повертає очищений SQL або кидає UnsafeSQLError.
    """
    sql = clean_sql(sql)
    if not sql:
        raise UnsafeSQLError("Порожній запит.")
    # Прибираємо рядкові літерали, щоб слово 'delete' всередині тексту не заважало
    without_strings = re.sub(r"'(?:[^']|'')*'", "''", sql)
    if ";" in without_strings:
        raise UnsafeSQLError("Дозволено лише один SQL-запит.")
    if not re.match(r"^\s*(SELECT|WITH)\b", without_strings, re.IGNORECASE):
        raise UnsafeSQLError("Дозволено лише запити на читання (SELECT).")
    match = FORBIDDEN.search(without_strings)
    if match:
        raise UnsafeSQLError(f"Заборонена команда: {match.group(1).upper()}.")
    return sql


# ------------------------------------------------------- виконання запиту

@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list]
    truncated: bool       # чи обрізано результат до MAX_ROWS
    elapsed_ms: float


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    """
    Другий рівень захисту – база відкривається в режимі read-only.
    Навіть якщо небезпечний запит обійде перевірку тексту, SQLite його не виконає.
    """
    if not Path(db_path).exists():
        raise FileNotFoundError(
            f"База {db_path} не знайдена. Запусти: python scripts/create_demo_db.py")
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, check_same_thread=False)
    con.execute("PRAGMA query_only = ON")
    return con


def _authorizer(action, arg1, arg2, db_name, trigger):
    """Третій рівень захисту – SQLite сам відхиляє будь-яку дію, крім читання."""
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
    # SQLITE_RECURSIVE потрібен для WITH RECURSIVE (є не в усіх версіях Python)
    allowed.add(getattr(sqlite3, "SQLITE_RECURSIVE", 33))
    return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY


def run_query(db_path: Path, sql: str) -> QueryResult:
    """Перевіряє і виконує SQL. Помилки SQLite (sqlite3.Error) передаються далі."""
    sql = validate_sql(sql)
    con = _connect_readonly(db_path)
    con.set_authorizer(_authorizer)

    # Обмеження часу: довгий запит переривається
    deadline = time.monotonic() + SQL_TIMEOUT_SEC
    con.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)

    start = time.perf_counter()
    try:
        cur = con.execute(sql)
        columns = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchmany(MAX_ROWS + 1)
    except sqlite3.OperationalError as e:
        if "interrupted" in str(e):
            raise sqlite3.OperationalError(
                f"Запит виконувався довше {SQL_TIMEOUT_SEC} с і був зупинений.") from e
        raise
    finally:
        con.close()

    truncated = len(rows) > MAX_ROWS
    return QueryResult(
        columns=columns,
        rows=[list(r) for r in rows[:MAX_ROWS]],
        truncated=truncated,
        elapsed_ms=(time.perf_counter() - start) * 1000,
    )
