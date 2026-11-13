"""
Головний конвеєр: запитання -> Gemini -> перевірка -> виконання -> (виправлення).
"""
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

from app import config, llm
from app.db import QueryResult, UnsafeSQLError, clean_sql, get_schema, run_query


@dataclass
class AskResult:
    question: str
    sql: str
    explanation: str
    chart: str
    x_column: str | None
    y_column: str | None
    model: str
    result: QueryResult | None
    error: str | None
    attempts: int                       # скільки разів генерувався SQL
    timings: dict = field(default_factory=dict)  # мс: gemini, sql


def ask(question: str, db_path: Path = config.DEMO_DB_PATH,
        generate=None) -> AskResult:
    """
    Відповідає на запитання до бази.
    `generate` можна підмінити в тестах, щоб не звертатися до справжнього Gemini.
    """
    generate = generate or llm.generate_sql
    schema = get_schema(db_path)
    gemini_ms = sql_ms = 0.0
    sql, error = None, None

    for attempt in range(1, config.MAX_FIX_ATTEMPTS + 2):
        t0 = time.perf_counter()
        answer, model = generate(schema, question, previous_sql=sql, error=error)
        gemini_ms += (time.perf_counter() - t0) * 1000
        sql = answer.sql

        try:
            result = run_query(db_path, sql)
            sql_ms += result.elapsed_ms
            return AskResult(question, clean_sql(sql), answer.explanation, answer.chart,
                             answer.x_column, answer.y_column, model, result, None,
                             attempt, {"gemini": round(gemini_ms), "sql": round(sql_ms, 1)})
        except UnsafeSQLError as e:
            # Небезпечний запит не виправляємо – одразу повідомляємо
            return AskResult(question, sql, answer.explanation, "none", None, None, model,
                             None, f"Запит відхилено: {e}", attempt,
                             {"gemini": round(gemini_ms), "sql": 0})
        except sqlite3.Error as e:
            error = str(e)  # даємо Gemini шанс виправити

    return AskResult(question, sql, answer.explanation, "none", None, None, model, None,
                     f"Не вдалося побудувати коректний запит: {error}", attempt,
                     {"gemini": round(gemini_ms), "sql": round(sql_ms, 1)})

