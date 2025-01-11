from datetime import datetime
import sqlite3
import psycopg2
from config import db_path, old_sqlite_path

# Подключение к SQLite
sqlite_conn = sqlite3.connect(old_sqlite_path)
sqlite_cursor = sqlite_conn.cursor()

# Подключение к PostgreSQL
with psycopg2.connect(db_path) as pg_conn:
    with pg_conn.cursor() as pg_cursor:
        # Создание таблиц в PostgreSQL
        pg_cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            city TEXT,
            buyer_id BIGINT
        );
        """)

        pg_cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id BIGINT PRIMARY KEY,
            user_id BIGINT REFERENCES users(user_id),
            buyer_id BIGINT,
            performance_id BIGINT,
            place_id BIGINT,
            price INTEGER,
            payment_id TEXT,
            payment_link TEXT,
            place_locked_time BIGINT,
            status INTEGER,
            kino_add_payment_id BIGINT,
            row INTEGER,
            place INTEGER,
            report_sented INTEGER DEFAULT 0
        );
        """)

        pg_cursor.execute("""
        CREATE TABLE IF NOT EXISTS show (
            show_id BIGINT PRIMARY KEY,
            name TEXT,
            kinopoisk_id BIGINT,
            duration INTEGER,
            description TEXT,
            poster TEXT,
            kp_rating INTEGER,
            pushkin_card INTEGER DEFAULT 0,
            pu_number BIGINT,
            id_procult BIGINT
        );
        """)

        # pg_cursor.execute("""
        #     -- 1. Добавляем новую колонку с типом TEXT
        #     ALTER TABLE show ADD COLUMN duration_text TEXT;
        #
        #     -- 2. Копируем данные из старой колонки в новую (если данные можно безопасно преобразовать)
        #     UPDATE show SET duration_text = CAST(duration AS TEXT);
        #
        #     -- 3. Удаляем старую колонку
        #     ALTER TABLE show DROP COLUMN duration;
        #
        #     -- 4. Переименовываем новую колонку в имя старой
        #     ALTER TABLE show RENAME COLUMN duration_text TO duration;
        # """)

        pg_cursor.execute("""
        CREATE TABLE IF NOT EXISTS performance (
            performance_id BIGINT PRIMARY KEY,
            show_id BIGINT REFERENCES show(show_id),
            building_id BIGINT,
            hallname TEXT,
            date TIME,
            time TIME,
            minprice INTEGER,
            maxprice INTEGER,
            freeplaces TEXT,
            building_name TEXT,
            hall_id BIGINT
        );
        """)

        pg_cursor.execute("""
            -- 1. Добавляем новую колонку с типом TEXT
            ALTER TABLE performance ADD COLUMN date_date TIMESTAMP;
            ALTER TABLE performance ADD COLUMN time_date TIMESTAMP;

            -- 3. Удаляем старую колонку
            ALTER TABLE performance DROP COLUMN date;
            ALTER TABLE performance DROP COLUMN time;

            -- 4. Переименовываем новую колонку в имя старой
            ALTER TABLE performance RENAME COLUMN date_date TO date;
            ALTER TABLE performance RENAME COLUMN time_date TO time;
        """)

        pg_cursor.execute("""
        CREATE TABLE IF NOT EXISTS cinemas (
            building_id BIGINT PRIMARY KEY,
            name TEXT,
            city TEXT,
            address TEXT,
            fond_kino_id BIGINT
        );
        """)

        # # Перенос данных из SQLite в PostgreSQL
        # def transfer_table(sqlite_query, pg_insert_query, params=None):
        #     sqlite_cursor.execute(sqlite_query, params or ())
        #     rows = sqlite_cursor.fetchall()
        #     for row in rows:
        #         # Преобразование данных перед вставкой
        #         transformed_row = []
        #         for value in row:
        #             # Преобразование пустых строк или NULL значений
        #             if value == "":  # пустая строка
        #                 transformed_row.append(None)
        #             elif value == " ":
        #                 transformed_row.append(None)
        #             elif isinstance(value, str) and len(value) == 10 and value.count('-') == 2:
        #                 # Преобразование даты в формат TIMESTAMP
        #                 transformed_row.append(f"{value} 00:00:00")  # Добавляем время, если только дата
        #             elif isinstance(value, str) and ":" in value and len(value) == 5:
        #                 # Преобразование времени в формат TIMESTAMP
        #                 transformed_row.append(f"{datetime.now().date()} {value}:00")
        #             else:
        #                 transformed_row.append(value)
        #         pg_cursor.execute(pg_insert_query, tuple(transformed_row))
        #
        # # Перенос данных из таблицы users
        # transfer_table(
        #     "SELECT user_id, city, buyer_id FROM users",
        #     """
        #     INSERT INTO users (user_id, city, buyer_id)
        #     VALUES (%s, %s, %s)
        #     ON CONFLICT (user_id) DO NOTHING;
        #     """
        # )
        #
        # # Перенос данных из таблицы orders
        # transfer_table(
        #     """
        #     SELECT order_id, user_id, buyer_id, performance_id, place_id, price,
        #            payment_id, payment_link, place_locked_time, status,
        #            kino_add_payment_id, row, place, report_sented
        #     FROM orders
        #     """,
        #     """
        #     INSERT INTO orders (order_id, user_id, buyer_id, performance_id, place_id, price,
        #                         payment_id, payment_link, place_locked_time, status,
        #                         kino_add_payment_id, row, place, report_sented)
        #     VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        #     ON CONFLICT (order_id) DO NOTHING;
        #     """
        # )
        #
        # # Перенос данных из таблицы show
        # transfer_table(
        #     """
        #     SELECT show_id, name, kinopoisk_id, duration, description, poster,
        #            kp_rating, pushkin_card, pu_number, id_procult
        #     FROM show
        #     """,
        #     """
        #     INSERT INTO show (show_id, name, kinopoisk_id, duration, description, poster,
        #                       kp_rating, pushkin_card, pu_number, id_procult)
        #     VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        #     ON CONFLICT (show_id) DO NOTHING;
        #     """
        # )
        #
        # # Перенос данных из таблицы performance
        # transfer_table(
        #     """
        #     SELECT performance_id, show_id, building_id, hallname, date, time,
        #            minprice, maxprice, freeplaces, building_name, hall_id
        #     FROM performance
        #     """,
        #     """
        #     INSERT INTO performance (performance_id, show_id, building_id, hallname, date, time,
        #                              minprice, maxprice, freeplaces, building_name, hall_id)
        #     VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        #     ON CONFLICT (performance_id) DO NOTHING;
        #     """
        # )
        #
        # # Перенос данных из таблицы cinemas
        # transfer_table(
        #     "SELECT building_id, name, city, address, fond_kino_id FROM cinemas",
        #     """
        #     INSERT INTO cinemas (building_id, name, city, address, fond_kino_id)
        #     VALUES (%s, %s, %s, %s, %s)
        #     ON CONFLICT (building_id) DO NOTHING;
        #     """
        # )

# Закрытие соединений
sqlite_conn.close()
print("SQLite соединение закрыто")
