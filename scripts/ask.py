"""
Консольна версія – щоб перевірити ядро ще до вебінтерфейсу.

Запуск з кореня проєкту:
    python scripts/ask.py "Топ-5 товарів за виручкою у 2025 році"
    python scripts/ask.py          # інтерактивний режим
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.nl2sql import ask  # noqa: E402


def show(question: str) -> None:
    r = ask(question)
    print(f"\nSQL ({r.model}, спроба {r.attempts}):\n{r.sql}\n")
    print(f"Пояснення: {r.explanation}")
    if r.error:
        print(f"\n❌ {r.error}")
        return
    res = r.result
    widths = [max(len(str(c)), *(len(str(row[i])) for row in res.rows[:20]))
              for i, c in enumerate(res.columns)] if res.rows else [len(c) for c in res.columns]
    print()
    print(" | ".join(str(c).ljust(w) for c, w in zip(res.columns, widths)))
    print("-+-".join("-" * w for w in widths))
    for row in res.rows[:20]:
        print(" | ".join(str(v).ljust(w) for v, w in zip(row, widths)))
    if len(res.rows) > 20:
        print(f"... ще {len(res.rows) - 20} рядків")
    print(f"\nГрафік: {r.chart} (x={r.x_column}, y={r.y_column})")
    print(f"Час: Gemini {r.timings['gemini']} мс, SQL {r.timings['sql']} мс")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        show(" ".join(sys.argv[1:]))
    else:
        print("Введи запитання до бази (порожній рядок – вихід).")
        while q := input("\n> ").strip():
            show(q)
