"""
Інтеграція з Google Gemini API.

Модель отримує схему бази й запитання та повертає структуровану
відповідь у форматі JSON (SQL + пояснення + порада щодо графіка).
Формат задається Pydantic-моделлю, тому відповідь завжди однакової форми.
"""
import time
from typing import Literal

from google import genai
from google.genai import errors, types
from pydantic import BaseModel, Field

from app import config


class SQLAnswer(BaseModel):
    """Структура відповіді, яку ми вимагаємо від Gemini."""
    sql: str = Field(description="Один SQL-запит SELECT для SQLite, без крапки з комою")
    explanation: str = Field(description="Коротке пояснення українською: що і як рахує запит")
    chart: Literal["none", "bar", "line", "pie"] = Field(
        description="Тип графіка для результату: line – динаміка в часі, "
                    "bar – порівняння категорій, pie – частки цілого (до 8 частин), "
                    "none – якщо графік не потрібен (одне число, список без чисел)")
    x_column: str | None = Field(default=None, description="Колонка результату для осі X / підписів")
    y_column: str | None = Field(default=None, description="Числова колонка результату для осі Y")


SYSTEM_PROMPT = """Ти – експерт з SQL і аналітик даних. Твоє завдання – перетворити запитання
користувача природною мовою на ОДИН коректний SQL-запит для SQLite.

Правила:
1. Сервіс працює ЛИШЕ в режимі читання. Якщо користувач просить видалити, змінити,
   додати чи очистити дані (видали, зміни, додай, онови, очисти тощо), НЕ пиши такий
   запит, а поверни рівно:
   SELECT 'Сервіс працює лише в режимі читання: змінювати дані не можна' AS "Повідомлення"
   і chart = none.
2. Пиши лише запити на читання: SELECT або WITH ... SELECT.
3. Використовуй ТІЛЬКИ таблиці й колонки зі схеми нижче.
4. Дати зберігаються як текст 'YYYY-MM-DD'; для року/місяця використовуй strftime.
5. Давай колонкам результату зрозумілі назви українською через AS
   (наприклад, AS "Виручка, грн"), обгортай їх у подвійні лапки.
6. Округлюй грошові суми та середні значення до 2 знаків (ROUND).
7. Якщо користувач не вказав кількість – обмеж результат розумним LIMIT (до 100 рядків).
8. Виручку (суми грошей) рахуй лише за замовленнями, які не скасовані
   (status <> 'cancelled'), якщо користувач не просить інакше.
   Кількість замовлень рахуй за всіма статусами, якщо не сказано інакше.
   «Середній чек» – це середня сума ОДНОГО ЗАМОВЛЕННЯ: спершу порахуй суму кожного
   замовлення (SUM по order_items), потім візьми AVG від цих сум. Не плутай із середньою
   вартістю рядка order_items.
9. Якщо запитання взагалі не стосується даних у базі (погода, рецепти тощо), поверни
   SELECT 'Запитання не стосується цієї бази даних' AS "Повідомлення" і chart = none.
10. Пояснення пиши українською, 1–3 речення, без SQL-коду (SQL повертається окремим полем).

Схема бази даних:
{schema}"""


class GeminiUnavailableError(Exception):
    """Жодна з моделей не відповіла (перевантаження, ліміти, мережа)."""


_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        if not config.GEMINI_API_KEY:
            raise GeminiUnavailableError("Не задано GEMINI_API_KEY (файл .env).")
        _client = genai.Client(
            api_key=config.GEMINI_API_KEY,
            http_options=types.HttpOptions(
                timeout=config.GEMINI_TIMEOUT_MS,
                retry_options=types.HttpRetryOptions(attempts=1),  # повтори робимо самі
            ),
        )
    return _client


# Помилки, після яких є сенс повторити запит або перейти на запасну модель
RETRYABLE_CODES = {429, 500, 503, 504}


def generate_sql(schema: str, question: str,
                 previous_sql: str | None = None,
                 error: str | None = None) -> tuple[SQLAnswer, str]:
    """
    Просить Gemini написати SQL. Якщо передано previous_sql і error –
    просить виправити свій попередній запит, що завершився помилкою.

    Повертає (відповідь, назва моделі, яка відповіла).
    Порядок: основна модель -> повтор через 2 с -> запасна модель.
    """
    contents = f"Запитання користувача: {question}"
    if previous_sql and error:
        contents += (f"\n\nТвій попередній запит:\n{previous_sql}\n"
                     f"завершився помилкою SQLite:\n{error}\n"
                     f"Виправ запит з урахуванням схеми.")

    gen_config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT.format(schema=schema),
        response_mime_type="application/json",
        response_schema=SQLAnswer,
        temperature=0,  # максимально передбачувані відповіді
    )

    attempts = [(config.GEMINI_MODEL, 0), (config.GEMINI_MODEL, 2),
                (config.GEMINI_FALLBACK_MODEL, 0)]
    last_error = None
    for model, delay in attempts:
        time.sleep(delay)
        try:
            response = get_client().models.generate_content(
                model=model, contents=contents, config=gen_config)
            answer = response.parsed
            if answer is None:  # модель повернула некоректний JSON
                answer = SQLAnswer.model_validate_json(response.text)
            return answer, model
        except errors.APIError as e:
            if e.code not in RETRYABLE_CODES:
                raise
            last_error = e
        except Exception as e:  # таймаут мережі тощо
            last_error = e

    raise GeminiUnavailableError(
        f"Gemini зараз недоступний, спробуйте пізніше. ({last_error})")
