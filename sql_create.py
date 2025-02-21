import uuid
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

        pg_cursor.execute("""ALTER TABLE orders ADD COLUMN uuid_order TEXT;""")

        pg_cursor.execute("""
                    UPDATE orders
                    SET uuid_order = gen_random_uuid();
                """)

        # Делаем поле обязательным
        pg_cursor.execute("""
                    ALTER TABLE orders
                    ALTER COLUMN uuid_order SET NOT NULL;
                """)
        pg_cursor.execute("ALTER TABLE orders ALTER COLUMN uuid_order SET NOT NULL;")
        pg_cursor.execute("""ALTER TABLE orders ADD CONSTRAINT orders_uuid_order_unique UNIQUE (uuid_order);""")

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

        # pg_cursor.execute("""
        # ALTER TABLE orders DROP CONSTRAINT orders_pkey;
        # CREATE UNIQUE INDEX order_id_unique ON orders(order_id);
        # ALTER TABLE orders ALTER COLUMN order_id DROP NOT NULL;
        # """)

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

        # pg_cursor.execute("""
        #     -- 1. Добавляем новую колонку с типом TEXT
        #     ALTER TABLE performance ADD COLUMN date_date INTEGER;
        #
        #     -- 3. Удаляем старую колонку
        #     ALTER TABLE performance DROP COLUMN freeplaces;
        #
        #     -- 4. Переименовываем новую колонку в имя старой
        #     ALTER TABLE performance RENAME COLUMN date_date TO freeplaces;
        # """)

        pg_cursor.execute("""
        CREATE TABLE IF NOT EXISTS cinemas (
            building_id BIGINT PRIMARY KEY,
            name TEXT,
            city TEXT,
            address TEXT,
            fond_kino_id BIGINT
        );
        """)

        pg_cursor.execute(
            """INSERT INTO cinemas (building_id, name, city, address, fond_kino_id) VALUES (2515, 'Орион', 'Бердск', 'г. Бердск, ул. Островского, 69', 1629) ON CONFLICT (building_id) DO NOTHING;""")
        pg_cursor.execute(
            """INSERT INTO cinemas (building_id, name, city, address, fond_kino_id) VALUES (3522, 'Планета кино', 'Бийск', 'г. Бийск, ул. Советская, 205/2', 1626) ON CONFLICT (building_id) DO NOTHING;""")
        # curs.execute("""INSERT OR IGNORE INTO cinemas (building_id, name, city, address, fond_kino_id) VALUES (9054, 'Голден синема', 'Новосибирск', 'г. Новосибирск ул.Курчатова 1');""")
        pg_cursor.execute(
            """INSERT INTO cinemas (building_id, name, city, address, fond_kino_id) VALUES (5041, 'Планета кино', 'Горно-Алтайск', 'г. Горно-Алтайск, пр. Коммунистический, 11', 1627) ON CONFLICT (building_id) DO NOTHING;""")
        pg_cursor.execute(
            """INSERT INTO cinemas (building_id, name, city, address, fond_kino_id) VALUES (1009, 'Россия', 'Искитим', 'г. Искитим, пр. Юбилейный, 15', 1628) ON CONFLICT (building_id) DO NOTHING;""")
        pg_cursor.execute("""DELETE FROM cinemas WHERE city = 'Кемерово';""")
        # curs.execute("""INSERT OR IGNORE INTO cinemas (building_id, name, city, address, fond_kino_id) VALUES (508, 'Променад 2', 'Кемерово', 'г. Кемерово, пр. Химиков, 39', 1625);""")
        # curs.execute("""INSERT OR IGNORE INTO cinemas (building_id, name, city, address, fond_kino_id) VALUES (6544, 'Променад 3', 'Кемерово', 'г. Кемерово, пр. Ленина, 59а', 1529);""")
        # curs.execute("""INSERT OR IGNORE INTO cinemas (building_id, name, city, address, fond_kino_id) VALUES (9053, 'МКП ККК им. В.В. Маяковского', 'Новосибирск', 'г. Новосибирск, красный проспект 17');""")
        pg_cursor.execute(
            """INSERT INTO cinemas (building_id, name, city, address, fond_kino_id) VALUES (1511, 'Аврора', 'Новосибирск', 'г. Новосибирск, пр. Карла Маркса, 49', 1632) ON CONFLICT (building_id) DO NOTHING;""")
        pg_cursor.execute(
            """INSERT INTO cinemas (building_id, name, city, address, fond_kino_id) VALUES (3516, 'Горизонт', 'Новосибирск', 'г. Новосибирск, ул. Бориса Богаткова, 266', 1633) ON CONFLICT (building_id) DO NOTHING;""")
        # curs.execute("""INSERT OR IGNORE INTO cinemas (building_id, name, city, address, fond_kino_id) VALUES (4540, 'Седьмое Небо', 'Новосибирск', 'г. Новосибирск, ул. Дуси Ковальчук, 179/4');""")

# Закрытие соединений
sqlite_conn.close()
print("SQLite соединение закрыто")
