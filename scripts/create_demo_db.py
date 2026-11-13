"""
Створює демо-базу даних інтернет-магазину (SQLite) у файлі data/shop.db.

Запуск з кореня проєкту:
    python scripts/create_demo_db.py

Дані генеруються випадково, але з фіксованим seed – тому щоразу
виходить однакова база (зручно для тестів і демонстрації).
"""
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

random.seed(42)

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "shop.db"

SCHEMA = """
CREATE TABLE customers (
    customer_id   INTEGER PRIMARY KEY,
    first_name    TEXT NOT NULL,
    last_name     TEXT NOT NULL,
    city          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    registered_at DATE NOT NULL
);

CREATE TABLE categories (
    category_id INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE
);

CREATE TABLE products (
    product_id  INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    category_id INTEGER NOT NULL REFERENCES categories(category_id),
    price       REAL NOT NULL,          -- ціна в гривнях
    stock       INTEGER NOT NULL        -- залишок на складі, шт.
);

CREATE TABLE orders (
    order_id    INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    order_date  DATE NOT NULL,
    status      TEXT NOT NULL           -- 'delivered', 'shipped', 'cancelled'
);

CREATE TABLE order_items (
    order_id   INTEGER NOT NULL REFERENCES orders(order_id),
    product_id INTEGER NOT NULL REFERENCES products(product_id),
    quantity   INTEGER NOT NULL,
    unit_price REAL NOT NULL,           -- ціна на момент покупки
    PRIMARY KEY (order_id, product_id)
);
"""

FIRST_NAMES = ["Олена", "Андрій", "Марія", "Дмитро", "Ірина", "Олександр", "Наталія",
               "Сергій", "Юлія", "Віталій", "Катерина", "Максим", "Анна", "Богдан",
               "Софія", "Тарас", "Дарина", "Ігор", "Вікторія", "Назар"]
LAST_NAMES = ["Шевченко", "Коваленко", "Бондаренко", "Ткаченко", "Кравченко", "Олійник",
              "Мельник", "Поліщук", "Савченко", "Руденко", "Лисенко", "Марченко",
              "Гончаренко", "Кузьменко", "Павленко", "Литвиненко"]
CITIES = ["Київ"] * 5 + ["Львів"] * 3 + ["Харків"] * 2 + ["Одеса"] * 2 + \
         ["Дніпро", "Вінниця", "Полтава", "Черкаси", "Житомир", "Ужгород"]

CATALOG = {
    "Ноутбуки": [("Ноутбук Lenovo IdeaPad 5", 28999), ("Ноутбук ASUS VivoBook 15", 22499),
                 ("Ноутбук HP Pavilion 14", 31999), ("Ноутбук Acer Aspire 7", 34999),
                 ("Ноутбук Apple MacBook Air M3", 52999)],
    "Смартфони": [("Смартфон Samsung Galaxy A55", 15999), ("Смартфон Xiaomi Redmi Note 13", 9499),
                  ("Смартфон Apple iPhone 15", 37999), ("Смартфон Google Pixel 8a", 19999),
                  ("Смартфон Motorola G84", 8499)],
    "Навушники": [("Навушники Sony WH-1000XM5", 13999), ("Навушники JBL Tune 520BT", 1999),
                  ("Навушники Apple AirPods Pro 2", 10999), ("Навушники Xiaomi Buds 5", 2799)],
    "Аксесуари": [("Миша Logitech MX Master 3S", 4299), ("Клавіатура Logitech K380", 1599),
                  ("Павербанк Baseus 20000 мА·год", 1299), ("Чохол для смартфона", 399),
                  ("Зарядний пристрій 65 Вт", 999), ("USB-C кабель 2 м", 299)],
    "Монітори": [("Монітор Dell 27\" S2721DS", 10999), ("Монітор LG 24\" 24MP60G", 5499),
                 ("Монітор Samsung 32\" Odyssey G5", 13499)],
    "Планшети": [("Планшет Apple iPad 10.9", 18999), ("Планшет Samsung Galaxy Tab S9 FE", 16499),
                 ("Планшет Lenovo Tab M10", 6999)],
    "Розумний дім": [("Розумна лампа Xiaomi", 699), ("Розумна розетка TP-Link", 549),
                     ("Робот-пилосос Roborock Q7", 14999), ("Камера Xiaomi C300", 1599)],
}

START = date(2024, 1, 1)
END = date(2025, 12, 31)


def random_date(start: date, end: date) -> date:
    return start + timedelta(days=random.randint(0, (end - start).days))


def main() -> None:
    DB_PATH.parent.mkdir(exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)

    # Категорії і товари
    product_rows = []
    for cat_id, (cat_name, items) in enumerate(CATALOG.items(), start=1):
        con.execute("INSERT INTO categories VALUES (?, ?)", (cat_id, cat_name))
        for name, price in items:
            product_rows.append((name, cat_id, price, random.randint(0, 120)))
    con.executemany(
        "INSERT INTO products (name, category_id, price, stock) VALUES (?, ?, ?, ?)",
        product_rows,
    )
    products = con.execute("SELECT product_id, price FROM products").fetchall()
    # Дешеві товари купують частіше
    weights = [1 / (price ** 0.5) for _, price in products]

    # Клієнти
    customers = []
    for cid in range(1, 301):
        fn, ln = random.choice(FIRST_NAMES), random.choice(LAST_NAMES)
        customers.append((cid, fn, ln, random.choice(CITIES),
                          f"user{cid}@example.com",
                          random_date(date(2023, 1, 1), date(2025, 6, 30)).isoformat()))
    con.executemany("INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?)", customers)

    # Замовлення: деякі клієнти купують значно частіше за інших
    activity = {c[0]: random.choice([1, 1, 1, 2, 3, 6]) for c in customers}
    order_id = 0
    for cid, fn, ln, city, email, reg in customers:
        reg_date = date.fromisoformat(reg)
        for _ in range(random.randint(0, 4) * activity[cid]):
            d = random_date(max(reg_date, START), END)
            # Сезонність: у листопаді-грудні замовлень більше
            if d.month not in (11, 12) and random.random() < 0.25:
                continue
            order_id += 1
            status = random.choices(["delivered", "shipped", "cancelled"], [85, 7, 8])[0]
            con.execute("INSERT INTO orders VALUES (?, ?, ?, ?)",
                        (order_id, cid, d.isoformat(), status))
            chosen = random.choices(products, weights=weights, k=random.randint(1, 4))
            for pid, price in {p[0]: p[1] for p in chosen}.items():
                # невеликі коливання ціни (знижки)
                unit_price = round(price * random.choice([1, 1, 1, 0.95, 0.9]), 2)
                con.execute("INSERT INTO order_items VALUES (?, ?, ?, ?)",
                            (order_id, pid, random.choices([1, 2, 3], [80, 15, 5])[0], unit_price))

    con.commit()
    for table in ["customers", "categories", "products", "orders", "order_items"]:
        n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"{table:12} {n:6} рядків")
    con.close()
    print(f"\nБазу створено: {DB_PATH}")


if __name__ == "__main__":
    main()
