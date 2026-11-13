# Querio

Вебсервіс, що перетворює запитання природною мовою на SQL-запити за допомогою
**Google Gemini API**, виконує їх на базі даних і показує результат у вигляді таблиці та графіка.

> Лабораторна робота з дисципліни «Хмарні обчислення».

## Можливості
- запитання українською → SQL-запит + пояснення (Gemini, структурована JSON-відповідь);
- автоматичне виправлення SQL з помилкою (помилка SQLite повертається в Gemini);
- автоматичний перехід на запасну модель, якщо основна перевантажена;
- захист: лише читання (перевірка тексту, read-only з'єднання, SQLite-авторизатор), ліміт часу і рядків;
- таблиця, графік (стовпчиковий / лінійний / круговий), експорт у CSV;
- редагування й повторне виконання SQL без Gemini;
- REST API з документацією Swagger (`/docs`).

## Архітектура
```
Браузер ──► FastAPI (Cloud Run) ──► Gemini API (Google Cloud)
                 │
                 └──► SQLite (демо-база інтернет-магазину)
```

## Локальний запуск
```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements-dev.txt
copy .env.example .env          # і вставити свій GEMINI_API_KEY
python scripts/create_demo_db.py
uvicorn app.main:app --reload   # http://127.0.0.1:8000
python -m pytest -v             # тести
```

## Розгортання в Google Cloud Run
```bash
gcloud run deploy querio --source . --region europe-west1 --allow-unauthenticated \
  --set-secrets GEMINI_API_KEY=gemini-api-key:latest \
  --set-env-vars GEMINI_MODEL=gemini-3.5-flash-lite,GEMINI_FALLBACK_MODEL=gemini-2.5-flash
```
Ключ Gemini зберігається в **Secret Manager** і не потрапляє ні в код, ні в образ.

## Стек
Python 3.13 · FastAPI · Google Gen AI SDK · Pydantic · SQLite · Chart.js · pytest · Docker · Cloud Run · Secret Manager
