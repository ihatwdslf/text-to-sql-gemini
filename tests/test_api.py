"""Тести REST API (Gemini підмінено, інтернет не потрібен)."""
import pytest
from fastapi.testclient import TestClient

from app import llm
from app.main import app

client = TestClient(app)


@pytest.fixture
def fake_gemini(monkeypatch):
    """Підміняє Gemini: повертає заданий SQL."""
    def install(sql, chart="bar"):
        def generate(schema, question, previous_sql=None, error=None):
            return llm.SQLAnswer(sql=sql, explanation="тестове пояснення", chart=chart,
                                 x_column="Категорія", y_column="Товарів"), "fake-model"
        monkeypatch.setattr(llm, "generate_sql", generate)
    return install


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_schema():
    tables = {t["name"] for t in client.get("/api/schema").json()["tables"]}
    assert tables == {"customers", "categories", "products", "orders", "order_items"}


def test_ask(fake_gemini):
    fake_gemini('SELECT c.name AS "Категорія", COUNT(*) AS "Товарів" '
                'FROM products p JOIN categories c USING(category_id) GROUP BY c.name')
    r = client.post("/api/ask", json={"question": "Скільки товарів у кожній категорії?"})
    body = r.json()
    assert r.status_code == 200
    assert body["result"]["columns"] == ["Категорія", "Товарів"]
    assert body["result"]["row_count"] == 7
    assert body["chart"] == "bar" and body["error"] is None


def test_ask_too_short_question():
    assert client.post("/api/ask", json={"question": "a"}).status_code == 422


def test_ask_when_gemini_down(monkeypatch):
    def down(*args, **kwargs):
        raise llm.GeminiUnavailableError("перевантажено")
    monkeypatch.setattr(llm, "generate_sql", down)
    r = client.post("/api/ask", json={"question": "Скільки замовлень?"})
    assert r.status_code == 503


def test_run_edited_sql():
    r = client.post("/api/run", json={"sql": "SELECT COUNT(*) AS n FROM customers"})
    assert r.status_code == 200 and r.json()["result"]["rows"] == [[300]]


def test_run_rejects_delete():
    r = client.post("/api/run", json={"sql": "DELETE FROM orders"})
    assert r.status_code == 400 and "відхилено" in r.json()["detail"]


def test_run_sql_error():
    r = client.post("/api/run", json={"sql": "SELECT nope FROM orders"})
    assert r.status_code == 400 and "Помилка SQL" in r.json()["detail"]
