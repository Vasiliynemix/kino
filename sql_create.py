import sqlite3

from config import db_path

with sqlite3.connect(db_path, timeout=15000) as data:
    curs = data.cursor()
    curs.execute("""PRAGMA journal_mode=WAL""")

    curs.execute("""CREATE TABLE IF NOT EXISTS users(
    		user_id INTEGER NOT NULL PRIMARY KEY,
			city TEXT,
			buyer_id INTEGER 
            )""")
   
   
    #status
    #0 - заказ не состоялся
    #1 - заказ оплачен
    #2 - забронировано место          = через 5 минут после создания сбрасываем если не продвинулось дальше
    #3 - создан заказ и пользователь переправлен на форму оплаты
    #4 - не смог обработать вероятно оплаченный заказ и написал об этом 
    curs.execute("""CREATE TABLE IF NOT EXISTS orders(
    		order_id INTEGER,
    		user_id INTEGER,
			buyer_id INTEGER,
			performance_id INTEGER,
			place_id INTEGER,
			price INTEGER,
			payment_id INTEGER,
			payment_link TEXT,
			place_locked_time INTEGER,
			status INTEGER,
			kino_add_payment_id INTEGER,
			row INTEGER,
			place INTEGER,
			report_sented BULL DEFAULT False
            )""")
    curs.execute("""CREATE TABLE IF NOT EXISTS show(
			show_id INTEGER NOT NULL PRIMARY KEY,
			name TEXT,
			kinopoisk_id INTEGER,
			duration INTEGER,
			description TEXT,
			poster TEXT,
			kp_rating INTEGER,
			pushkin_card BOOL DEFAULT False,
			pu_number INTEGER,
			id_procult INTEGER
            )""")
    curs.execute("""CREATE TABLE IF NOT EXISTS performance(
    		performance_id INTEGER NOT NULL PRIMARY KEY,
			show_id INTEGER,
			building_id INTEGER,
			hallname TEXT,
			date DATATIME,
			time DATATIME,
			minprice INTEGER,
			maxprice INTEGER,
			freeplaces TEXT,
			building_name TEXT,
			hall_id INTEGER
            )""")
    
    curs.execute("""CREATE TABLE IF NOT EXISTS cinemas(
			building_id INTEGER NOT NULL PRIMARY KEY,
			name TEXT,
			city TEXT,
			address TEXT,
			fond_kino_id INTEGER
            )""")

    curs.execute("""INSERT OR IGNORE INTO cinemas (building_id, name, city, address, fond_kino_id) VALUES (2515, 'Орион', 'Бердск', 'г. Бердск, ул. Островского, 69', 1629);""")
    curs.execute("""INSERT OR IGNORE INTO cinemas (building_id, name, city, address, fond_kino_id) VALUES (3522, 'Планета кино', 'Бийск', 'г. Бийск, ул. Советская, 205/2', 1626);""")
    # curs.execute("""INSERT OR IGNORE INTO cinemas (building_id, name, city, address, fond_kino_id) VALUES (9054, 'Голден синема', 'Новосибирск', 'г. Новосибирск ул.Курчатова 1');""")
    curs.execute("""INSERT OR IGNORE INTO cinemas (building_id, name, city, address, fond_kino_id) VALUES (5041, 'Планета кино', 'Горно-Алтайск', 'г. Горно-Алтайск, пр. Коммунистический, 11', 1627);""")
    curs.execute("""INSERT OR IGNORE INTO cinemas (building_id, name, city, address, fond_kino_id) VALUES (1009, 'Россия', 'Искитим', 'г. Искитим, пр. Юбилейный, 15', 1628);""")
    curs.execute("""DELETE FROM cinemas WHERE city = 'Кемерово';""")
    # curs.execute("""INSERT OR IGNORE INTO cinemas (building_id, name, city, address, fond_kino_id) VALUES (508, 'Променад 2', 'Кемерово', 'г. Кемерово, пр. Химиков, 39', 1625);""")
    # curs.execute("""INSERT OR IGNORE INTO cinemas (building_id, name, city, address, fond_kino_id) VALUES (6544, 'Променад 3', 'Кемерово', 'г. Кемерово, пр. Ленина, 59а', 1529);""")
    # curs.execute("""INSERT OR IGNORE INTO cinemas (building_id, name, city, address, fond_kino_id) VALUES (9053, 'МКП ККК им. В.В. Маяковского', 'Новосибирск', 'г. Новосибирск, красный проспект 17');""")
    curs.execute("""INSERT OR IGNORE INTO cinemas (building_id, name, city, address, fond_kino_id) VALUES (1511, 'Аврора', 'Новосибирск', 'г. Новосибирск, пр. Карла Маркса, 49', 1632);""")
    curs.execute("""INSERT OR IGNORE INTO cinemas (building_id, name, city, address, fond_kino_id) VALUES (3516, 'Горизонт', 'Новосибирск', 'г. Новосибирск, ул. Бориса Богаткова, 266', 1633);""")
    # curs.execute("""INSERT OR IGNORE INTO cinemas (building_id, name, city, address, fond_kino_id) VALUES (4540, 'Седьмое Небо', 'Новосибирск', 'г. Новосибирск, ул. Дуси Ковальчук, 179/4');""")