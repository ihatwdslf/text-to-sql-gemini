"""
Перевірка, що ключ Gemini API працює.

Запуск з кореня проєкту:
    python scripts/check_gemini.py
"""
import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise SystemExit("Не знайдено GEMINI_API_KEY. Перевір файл .env у корені проєкту.")

client = genai.Client(
    api_key=api_key,
    http_options=types.HttpOptions(
        timeout=30_000,                                   # 30 с на запит
        retry_options=types.HttpRetryOptions(attempts=1),  # без прихованих повторів
    ),
)

# Спершу моделі з .env, потім запасні
candidates = [os.getenv("GEMINI_MODEL"), os.getenv("GEMINI_FALLBACK_MODEL"),
              "gemini-2.5-flash", "gemini-2.5-flash-lite"]
candidates = list(dict.fromkeys(m for m in candidates if m))  # без дублікатів

for model in candidates:
    print(f"Тестовий запит до {model}...", end=" ", flush=True)
    start = time.perf_counter()
    try:
        response = client.models.generate_content(
            model=model,
            contents="Напиши SQL-запит, що рахує кількість рядків у таблиці orders. Лише SQL.",
        )
    except Exception as e:
        print(f"❌ {type(e).__name__}: {str(e)[:120]}")
        continue
    print(f"✅ за {time.perf_counter() - start:.1f} с\n")
    print(response.text)
    print(f"\nКлюч працює. Робоча модель: {model}")
    break
else:
    print("\nЖодна модель зараз не відповіла – спробуй ще раз через кілька хвилин.")