"""Спільні налаштування тестів: перед запуском створюємо демо-базу, якщо її немає."""
import pytest

from app.config import DEMO_DB_PATH


@pytest.fixture(scope="session", autouse=True)
def demo_db():
    if not DEMO_DB_PATH.exists():
        from scripts.create_demo_db import main
        main()
