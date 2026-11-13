"""
Тести ядра. Gemini підмінюється «фейковою» функцією, тому тести
працюють без інтернету і не витрачають ліміти API.

Запуск: python -m pytest -v
"""
import sqlite3

import pytest

from app.config import DEMO_DB_PATH
from app.db import UnsafeSQLError, get_schema, run_query, validate_sql
from app.llm import SQLAnswer
from app.nl2sql import ask


# ------------------------------------------------------------ безпека SQL

@pytest.mark.parametrize("sql", [
    "DELETE FROM orders",
    "DROP TABLE customers",
    "UPDATE products SET price = 0",
    "SELECT 1; DROP TABLE orders",
    "INSERT INTO categories VALUES (99, 'x')",
    "PRAGMA table_info(orders)",
    "",
])
def test_dangerous_sql_is_rejected(sql):
    with pytest.raises(UnsafeSQLError):
        validate_sql(sql)


def test_word_delete_inside_string_is_allowed():
    assert validate_sql("SELECT * FROM products WHERE name LIKE '%delete%'")


def test_markdown_wrapper_is_removed():
    assert validate_sql("```sql\nSELECT 1;\n```") == "SELECT 1"


def test_database_is_read_only_even_if_validation_bypassed():
    # Навіть якщо обійти перевірку тексту, read-only з'єднання не дасть змінити базу
    from app.db import _authorizer, _connect_readonly
    con = _connect_readonly(DEMO_DB_PATH)
    con.set_authorizer(_authorizer)
    with pytest.raises(sqlite3.DatabaseError):
        con.execute("DELETE FROM orders")
    con.close()


# ------------------------------------------------------- схема і виконання

def test_schema_contains_all_tables():
    schema = get_schema(DEMO_DB_PATH)
    for table in ["customers", "categories", "products", "orders", "order_items"]:
        assert f"CREATE TABLE {table}" in schema


def test_run_query_returns_columns_and_rows():
    r = run_query(DEMO_DB_PATH, 'SELECT name AS "Категорія" FROM categories ORDER BY 1')
    assert r.columns == ["Категорія"]
    assert len(r.rows) == 7


def test_long_query_is_interrupted():
    with pytest.raises(sqlite3.OperationalError, match="зупинений"):
        run_query(DEMO_DB_PATH, "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL "
                                "SELECT x + 1 FROM c) SELECT COUNT(*) FROM c")


# --------------------------------------------- конвеєр з підставним Gemini

def fake_gemini(*answers):
    """Повертає функцію, яка по черзі видає задані SQL – замість справжнього Gemini."""
    calls = []

    def generate(schema, question, previous_sql=None, error=None):
        calls.append({"previous_sql": previous_sql, "error": error})
        return SQLAnswer(sql=answers[len(calls) - 1], explanation="тест",
                         chart="bar", x_column="a", y_column="b"), "fake-model"

    generate.calls = calls
    return generate


def test_ask_success():
    gen = fake_gemini("SELECT COUNT(*) AS n FROM orders")
    r = ask("Скільки замовлень?", generate=gen)
    assert r.error is None
    assert r.result.rows[0][0] > 0
    assert r.attempts == 1


def test_ask_fixes_broken_sql():
    # Перший SQL з помилкою в назві колонки, другий – виправлений
    gen = fake_gemini("SELECT cost FROM products", "SELECT price FROM products")
    r = ask("Ціни товарів", generate=gen)
    assert r.error is None
    assert r.attempts == 2
    assert "no such column" in gen.calls[1]["error"]   # помилку передали в Gemini
    assert gen.calls[1]["previous_sql"] == "SELECT cost FROM products"


def test_ask_gives_up_after_max_attempts():
    gen = fake_gemini("SELECT x FROM nope", "SELECT y FROM nope", "SELECT z FROM nope")
    r = ask("щось", generate=gen)
    assert r.result is None
    assert "Не вдалося" in r.error


def test_ask_blocks_dangerous_sql():
    gen = fake_gemini("DROP TABLE orders")
    r = ask("Видали всі замовлення", generate=gen)
    assert r.result is None
    assert "відхилено" in r.error
