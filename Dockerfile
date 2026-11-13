# Образ для розгортання Querio в Google Cloud Run
FROM python:3.13-slim

# Не створювати .pyc і одразу виводити логи (щоб їх було видно в Cloud Run)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Спершу залежності – так Docker кешує цей шар між збірками
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Код застосунку
COPY app ./app
COPY scripts ./scripts
COPY static ./static

# Демо-база створюється під час збірки образу
RUN python scripts/create_demo_db.py

# Cloud Run передає порт у змінній PORT (за замовчуванням 8080)
ENV PORT=8080
EXPOSE 8080
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
