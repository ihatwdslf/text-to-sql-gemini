"""
REST API сервісу Querio (FastAPI).

Локальний запуск з кореня проєкту:
    uvicorn app.main:app --reload
Документація API (Swagger):  http://127.0.0.1:8000/docs
"""
import sqlite3

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import config
from app.db import UnsafeSQLError, get_tables, run_query
from app.llm import GeminiUnavailableError
from app.nl2sql import ask

app = FastAPI(
    title="Querio API",
    description="Перетворення запитань природною мовою на SQL за допомогою Google Gemini API.",
    version="1.0.0",
)

STATIC_DIR = config.BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ------------------------------------------------------------ моделі даних

class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500,
                          examples=["Топ-5 товарів за виручкою у 2025 році"])


class RunRequest(BaseModel):
    sql: str = Field(min_length=1, max_length=5000,
                     examples=['SELECT name AS "Категорія" FROM categories'])


class TableData(BaseModel):
    columns: list[str]
    rows: list[list]
    row_count: int
    truncated: bool


class AskResponse(BaseModel):
    question: str
    sql: str
    explanation: str
    chart: str
    x_column: str | None
    y_column: str | None
    model: str
    attempts: int
    timings_ms: dict
    result: TableData | None
    error: str | None


class RunResponse(BaseModel):
    sql: str
    result: TableData
    timings_ms: dict


def _table(res) -> TableData:
    return TableData(columns=res.columns, rows=res.rows,
                     row_count=len(res.rows), truncated=res.truncated)


# ------------------------------------------------------------- ендпоінти

@app.get("/", include_in_schema=False)
def index():
    """Головна сторінка (вебінтерфейс)."""
    page = STATIC_DIR / "index.html"
    if page.exists():
        return FileResponse(page)
    return {"message": "Querio API працює. Документація: /docs"}


@app.get("/api/health", tags=["Службові"])
def health():
    """Перевірка, що сервіс живий (знадобиться для хмари)."""
    return {"status": "ok", "model": config.GEMINI_MODEL,
            "fallback_model": config.GEMINI_FALLBACK_MODEL}


@app.get("/api/schema", tags=["База даних"])
def schema():
    """Таблиці бази, їхні колонки та кількість рядків."""
    return {"database": config.DEMO_DB_PATH.stem, "tables": get_tables(config.DEMO_DB_PATH)}


@app.post("/api/ask", response_model=AskResponse, tags=["Запити"])
def ask_question(req: AskRequest):
    """
    Головний ендпоінт: запитання природною мовою -> SQL (Gemini) -> результат.
    Якщо SQL з помилкою, Gemini автоматично отримує помилку і виправляє запит.
    """
    try:
        r = ask(req.question.strip())
    except GeminiUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return AskResponse(
        question=r.question, sql=r.sql, explanation=r.explanation, chart=r.chart,
        x_column=r.x_column, y_column=r.y_column, model=r.model, attempts=r.attempts,
        timings_ms=r.timings, result=_table(r.result) if r.result else None, error=r.error,
    )


@app.post("/api/run", response_model=RunResponse, tags=["Запити"])
def run_sql(req: RunRequest):
    """
    Виконати SQL, відредагований користувачем, без звернення до Gemini.
    Діють ті самі обмеження безпеки: лише читання.
    """
    try:
        res = run_query(config.DEMO_DB_PATH, req.sql)
    except UnsafeSQLError as e:
        raise HTTPException(status_code=400, detail=f"Запит відхилено: {e}")
    except sqlite3.Error as e:
        raise HTTPException(status_code=400, detail=f"Помилка SQL: {e}")
    return RunResponse(sql=req.sql, result=_table(res),
                       timings_ms={"sql": round(res.elapsed_ms, 1)})
