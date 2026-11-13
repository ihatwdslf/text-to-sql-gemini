"""Налаштування застосунку – читаються з файлу .env (локально) або зі змінних середовища (у хмарі)."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DEMO_DB_PATH = DATA_DIR / "shop.db"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash")

GEMINI_TIMEOUT_MS = 30_000   # скільки чекати на відповідь моделі
MAX_FIX_ATTEMPTS = 2         # скільки разів просити Gemini виправити SQL з помилкою
MAX_ROWS = 1000              # максимум рядків у результаті
SQL_TIMEOUT_SEC = 5          # максимальний час виконання SQL-запиту
