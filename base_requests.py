import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor

import psycopg2
import requests
import time
import datetime

from loguru import logger
from telebot import types
import telebot
import re

from yookassa import Payment, Configuration

from config import bot, url_kino_baza, url_prokultura, kinopoisk_token, info_log_file, \
    db_path, root_path, url, youkassa_shop_id, youkassa_secret_key, validation_url, pochta_bank_token
from pkg.log import CustomLogger
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

CustomLogger().add_logger(info_log_file, __name__)


def film_update_main():
    i = 1

    kinopoisk_enabled = True  # фла
    last_check_date = datetime.date.today()  # сегодня

    while True:
        try:
            # Сброс флага в новый день
            if datetime.date.today() != last_check_date:
                kinopoisk_enabled = True
                last_check_date = datetime.date.today()
                logger.info("Новый день — флаг kinopoisk_enabled сброшен на True")

            if i % 2 == 0 or i == 1:
                safe_execute(all_show_request, "all_show_request")

            safe_execute(get_show_info, "get_show_info")

            if i % 10 == 0 or i == 1:
                safe_execute(what_show_can_be_sell_pushkin_card, "what_show_can_be_sell_pushkin_card")

            if kinopoisk_enabled:
                res = safe_execute(get_kinopoisk_info, "get_kinopoisk_info")
                if res is False:  # именно False, а не None
                    kinopoisk_enabled = False

            if i % 4 == 0 or i == 1:
                safe_execute(all_performances_request, "all_performances_request")

            safe_execute(unblock_5_min, "unblock_5_min")

            # Проверяем статусы платежей
            process_orders()

        except Exception as e:
            logger.exception("Произошла ошибка в film_update_main")
            bot.send_message(5254091301, f'Ошибка в film_update_main\n{e}')

        finally:
            i = 1 if i > 10000 else i + 1  # Сброс счётчика
            time.sleep(5)


def safe_execute(func, func_name, timeout=120):
    """Выполняет функцию с таймаутом и логированием ошибок."""
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func)
        try:
            result = future.result(timeout=timeout)  # получаем результат
            logger.info(f"Функция {func_name} выполнена успешно")
            return result
        except FuturesTimeout:
            logger.error(f"Таймаут при выполнении {func_name}")
            bot.send_message(5254091301, f'Таймаут в {func_name}')
        except Exception as e:
            logger.exception(f"Ошибка в {func_name}")
            bot.send_message(5254091301, f'Ошибка в {func_name}\n{e}')
        return None  # если ошибка — возвращаем None


def process_orders():
    """Обрабатывает заказы с оплатой."""
    try:
        with psycopg2.connect(db_path) as conn:
            with conn.cursor() as curs:
                curs.execute("""SELECT payment_id FROM orders WHERE status = 3;""")
                orders = curs.fetchall()

        for order in orders:
            safe_execute(lambda: check_payment_status(order[0]), "check_payment_status")
    except Exception as e:
        logger.exception("Ошибка при получении заказов")
        bot.send_message(5254091301, f'Ошибка при получении заказов\n{e}')


def all_show_request():
    # запрашиваем список всех show
    params = {
        "sp": "Wga_GetShow",
        "df": "J"
    }
    response = requests.request("GET", url_kino_baza, params=params)
    # print(response.url)

    if response.status_code == 200:
        try:
            with psycopg2.connect(db_path) as conn:
                with conn.cursor() as curs:
                    data_show = response.json()
                    for show in data_show:
                        try:
                            show['ShowName'] = show['ShowName'].replace('&quot;', '').replace('«', '').replace('»', '')

                            # logger.info(f"Вставляем show_id: {show['IdShow']}, name: {show['ShowName']}, duration: {show['Duration']}")
                            curs.execute(
                                """INSERT INTO show (show_id, name, duration)
                                   VALUES (%s, %s, %s)
                                   ON CONFLICT (show_id) DO NOTHING;""",
                                (show['IdShow'], show['ShowName'], show['Duration'])
                            )
                            curs.execute("""UPDATE show SET name = %s, duration = %s WHERE show_id = %s""",
                                         (show['ShowName'], show['Duration'], show['IdShow']))
                        except Exception as e:
                            logger.exception(f"Ошибка при вставке шоу {show.get('IdShow')}: {e}")
        except json.JSONDecodeError as json_err:
            logger.exception("Ошибка декодирования JSON")
            bot.send_message(5254091301, f'Ошибка при декодировании JSON-ответа от сервера: {json_err}')
        except Exception as e:
            logger.exception("Произошла ошибка")
            bot.send_message(5254091301, f'Ошибка базы по запросу всех show \n{e}')
    else:
        pass
        bot.send_message(5254091301,
                         f'Ошибка по запросу всех show \nВ ответ на запрос возвращается код {response.status_code}')


def get_show_info():
    try:
        with psycopg2.connect(db_path) as conn:
            with conn.cursor() as curs:
                curs.execute("""SELECT show_id, name FROM show WHERE kinopoisk_id IS NULL;""")
                shows = curs.fetchall()
                # print(shows)
                for show in shows:
                    show_id = show[0]
                    name = show[1]
                    # запрашиваем список всех show
                    params = {
                        "sp": "Wga_GetShowInfo",
                        # 'IdBuilding': '3522',
                        'idShow': show_id,
                        # 'IdPerformance': '9371432',
                        "df": "J"
                    }

                    response = requests.request("GET", url_kino_baza, params=params)
                    # print(response.url)
                    # logger.info(f"show_id: {show_id}, name: {name}, response.status_code: {response.status_code}")

                    if response.status_code == 200:
                        data_show = response.json()
                        # print(data_show, '\n')
                        kinopoisk_id = data_show['Remark']
                        if kinopoisk_id == " ":
                            kinopoisk_id = None
                        curs.execute("""UPDATE show SET kinopoisk_id = %s WHERE show_id = %s""",
                                     (kinopoisk_id, show_id))
                        conn.commit()
                    else:
                        pass
                        # bot.send_message(5254091301, f'Ошибка по запросу Wga_GetShowInfo\nВ ответ на запрос возвращается код {response.status_code}')

    except Exception as e:
        logger.exception("Произошла ошибка")
        bot.send_message(5254091301, f'Ошибка базы по запросу всех Wga_GetShowInfo \n{e}')


def normalize_name(name: str) -> str:
    # В нижний регистр
    name = name.lower()
    # Убираем все символы кроме букв и цифр
    name = re.sub(r'[^\w\dа-яё]', '', name, flags=re.UNICODE)
    # Убираем повторяющиеся пробелы (если бы оставляли пробелы)
    # name = re.sub(r'\s+', ' ', name).strip()
    return name


def what_show_can_be_sell_pushkin_card():
    try:
        # берем с прокультуры все фильмы, которые можно показывать по пушкинской карте
        params_prokultura = {
            "organizations": "31698",
            'limit': '100',
            'categories': 'kino',
            "isPushkinsCard": "true",
            "apiKey": "txjo5hdvmmgqs7frjb64",
            'status': 'accepted'
        }

        response = requests.request("GET", url_prokultura, params=params_prokultura)
        # print(response.url)

        if response.status_code == 200:
            data = response.json()
            with open('data_prokult.json', 'w', encoding='utf-8') as file:
                json.dump(data, file, indent=4, ensure_ascii=False)
            # print(len(data['events']))
            accepted_films_list = []
            pu_number_list = {}
            id_procult_list = {}
            # добавляем их в списокфильмов которые можно
            for event in data['events']:
                match = re.search(r'«(.+)', event['name'])
                try:
                    film_name = match.group(1) if match else event['name']
                    film_name = normalize_name(film_name)
                except Exception as e:
                    logger.exception(f"Произошла ошибка {e}")
                    continue

                pu_number_list[film_name] = event['rentalCertificate'][0]
                id_procult_list[film_name] = event['_id']
                accepted_films_list.append(film_name)

            with psycopg2.connect(db_path) as conn:
                with conn.cursor() as curs:
                    # берем все фильмы что у нас есть, и сверяем названия со списком разрешенных.
                    # ghb этом названия могут быть одинаковые у нескольких шоу, меняем у всех
                    curs.execute("""SELECT DISTINCT name FROM show;""")
                    shows = curs.fetchall()
                    # print(accepted_films_list)
                    # print(id_procult_list)
                    for show in shows:
                        film_name = normalize_name(show[0])
                        if film_name in accepted_films_list:
                            curs.execute(
                                """UPDATE show SET pushkin_card = 1, pu_number = %s, id_procult = %s WHERE name = %s""",
                                (pu_number_list[film_name], id_procult_list[film_name], show[0])
                            )
                        else:
                            curs.execute("""UPDATE show SET pushkin_card = 0 WHERE name = %s""", (show[0],))

        # if response.status_code == 200:
        #     data_show = response.json()
        #     print(data_show['Remark'], '\n')
        #     curs.execute("""UPDATE show SET kinopoisk_id = %s WHERE show_id = %s""", (data_show['Remark'], show_id))
        else:
            # print(response.text)
            bot.send_message(5254091301,
                             f'Ошибка по запросу what_show_can_be_sell_pushkin_card \nВ ответ на запрос возвращается код {response.status_code} текст {response.text}')

    except Exception as e:
        logger.exception("Произошла ошибка")
        bot.send_message(5254091301, f'Ошибка базы по запросу всех what_show_can_be_sell_pushkin_card \n{e}')
        # if int(data_zu[0]['IdBuilding']):
        #     curs.execute("""DELETE FROM cinemas""")


def get_kinopoisk_info():
    try:
        with psycopg2.connect(db_path) as conn:
            with conn.cursor() as curs:
                curs.execute(
                    """SELECT kinopoisk_id 
                       FROM show 
                       WHERE kinopoisk_id IS NOT NULL 
                         AND (poster IS NULL OR poster = '');"""
                )
                shows = curs.fetchall()

                for show in shows:
                    kinopoisk_id = show[0]

                    params = {"token": kinopoisk_token}
                    response = requests.get(
                        f'https://api.kinopoisk.dev/v1/movie/{kinopoisk_id}',
                        params=params
                    )

                    # Если лимит исчерпан — прекращаем выполнение
                    if response.status_code == 403:
                        try:
                            err_data = response.json()
                        except Exception:
                            err_data = {}

                        message = err_data.get("message", "")
                        if "суточный лимит" in message:
                            logger.error(f"Суточный лимит по API Кинопоиск исчерпан. Остановка обновления.")
                            bot.send_message(
                                5254091301,
                                "Суточный лимит по API Кинопоиск исчерпан. Обновление остановлено."
                            )
                            return False  # флаг "больше не звать сегодня"
                        else:
                            logger.error(f"403 ошибка: {err_data}")
                            continue

                    if response.status_code == 200:
                        data_kinopoisk = response.json()
                        poster = (data_kinopoisk.get("poster") or {}).get("url", "")
                        curs.execute(
                            """UPDATE show 
                               SET description = %s, poster = %s, kp_rating = %s 
                               WHERE kinopoisk_id = %s""",
                            (
                                data_kinopoisk.get('description'),
                                poster,
                                (data_kinopoisk.get('rating') or {}).get('kp'),
                                kinopoisk_id
                            )
                        )
                        conn.commit()
                    else:
                        logger.error(
                            f"kinopoisk_id: {kinopoisk_id}, "
                            f"status_code: {response.status_code}, "
                            f"response: {response.text}"
                        )
                        bot.send_message(
                            5254091301,
                            f'Ошибка по запросу get_kinopoisk_info\nКод {response.status_code}'
                        )

        return True  # всё нормально, можно продолжать
    except Exception as e:
        logger.exception("Произошла ошибка")
        bot.send_message(5254091301, f'Ошибка базы по запросу get_kinopoisk_info\n{e}')
        return True  # тут можно вернуть True, чтобы не останавливать цикл полностью


def all_performances_request():
    # запрашиваем список всех сеансов
    params = {
        "sp": "Wga_GetPerformance",
        "df": "J"
    }
    response = requests.request("GET", url_kino_baza, params=params)
    # print(response.url)

    if response.status_code == 200:
        try:
            data_performances = response.json()
            with psycopg2.connect(db_path) as data:
                with data.cursor() as curs:
                    # Удаляем старые данные
                    curs.execute("""DELETE FROM performance""")

                    # Вставляем новые данные в performance
                    for data_performance in data_performances:
                        try:
                            try:
                                dt = datetime.datetime.strptime(data_performance['DateTime'], "%B %d %Y %I:%M:%S:%f%p")
                            except ValueError:
                                dt = datetime.datetime.strptime(data_performance['DateTime'], "%b %d %Y %I:%M:%S:%f%p")
                            date = dt.date()
                            date_str = datetime.datetime.strftime(date, '%Y-%m-%d')
                            time = dt.time()
                            time_str = time.strftime('%H:%M')

                            # Вставляем данные в таблицу performance, игнорируя дубликаты по performance_id
                            curs.execute("""
                                            INSERT INTO performance (performance_id, show_id, building_id, hallname, date, time, 
                                                minprice, maxprice, freeplaces, building_name, hall_id) 
                                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) 
                                            ON CONFLICT (performance_id) DO NOTHING;
                                        """, (data_performance['IdPerformance'], data_performance['IdShow'],
                                              data_performance['IdBuilding'], data_performance['HallName'], date_str,
                                              time_str,
                                              data_performance['MinPrice'], data_performance['MaxPrice'],
                                              data_performance['FreePlace'],
                                              data_performance['BuildingName'], data_performance['IdHall']))
                        except Exception as e:
                            logger.exception(f"Произошла ошибка при вставке performance: {e}")
                            continue
        except Exception as e:
            logger.exception("Произошла ошибка")
            bot.send_message(5254091301, f'Ошибка базы по запросу all_performances_request \n{e}')
    else:
        bot.send_message(5254091301,
                         f'Ошибка по запросу all_performances_request \nВ ответ на запрос возвращается код {response.status_code}')


def user_reg(user_id):  # проверяем зареган ли пользователь, если нет то регаем
    with psycopg2.connect(db_path) as data:
        with data.cursor() as curs:
            # если пользователя еще нет
            curs.execute("""SELECT user_id FROM users WHERE user_id = %s;""", (user_id,))
            user = curs.fetchone()
            if user == None:
                # получаем  идентификатор клиента и регистрируем пользователя
                params = {
                    "sp": "Wga_Autorize",
                    "Login": f'a{user_id}с',
                    "Name": f"tg_id{user_id}",
                    "IdDocument": "3165",
                    "df": "J"}
                response = requests.request("GET", url_kino_baza, params=params)
                try:
                    buyer = response.json()
                    curs.execute(
                        """INSERT INTO users (user_id, buyer_id) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING;""",
                        (user_id, buyer['IdClient']))
                except Exception:
                    curs.execute(
                        """INSERT INTO users (user_id, buyer_id) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING;""",
                        (user_id, 998277))

    return


def validate_pochta_bank(
        buyer_info,
        rrn,
        event_id,
        place_id,
        event_session_timestamp,
        term_inst_id="11132",
        organization_id="31698",
        client_buy_ip_address="0.0.0.0",
):
    query_params = {
        "online": "false"  # "true" если тест, иначе "false"
    }
    buyer_hash = hashlib.sha512(buyer_info.encode('utf-8')).hexdigest()
    json_data = {
        "buyer": buyer_hash,
        "termInstId": term_inst_id,
        "rrn": rrn,  # замените на реальный RRN транзакции
        "eventId": event_id,  # идентификатор мероприятия
        "placeId": place_id,  # идентификатор места проведения
        "organizationId": organization_id,  # идентификатор организатора мероприятия
        "eventSessionTimestamp": event_session_timestamp,  # UNIX-время начала сеанса (замените на нужное значение)
        "clientBuyIpAddress": client_buy_ip_address,  # IP-адрес покупателя, либо 0.0.0., если онлайн продажа
    }
    headers = {
        "Authorization": pochta_bank_token,
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
    }
    response = requests.post(validation_url, headers=headers, params=query_params, json=json_data)

    # Проверка ответа
    if response.status_code == 200:
        response = response.json()
        result = response.get("result")
        if result == "ACCEPTED":
            return True, ""

        if result == "DECLINED":
            print("Транзакция отклонена")
            reason = response.get("reason")
            reason_text = ""
            if reason == "PERSONAL_DATA":
                reason_text = "Несоответствие ФИО покупателя билета ФИО держателя карты"
            elif reason == "EVENT":
                reason_text = "Какая-то проблема с параметрами мероприятия"
            elif reason == "MULTISESSION":
                reason_text = "Попытка купить более одного билета на один сеанс мероприятия"
            elif reason == "PRICE":
                reason_text = "Некорректная стоимость билета "
            elif reason == "OTHER":
                reason_text = ""

            return False, reason_text
    else:
        logger.info(f"validate_pochta_bank {response.status_code=}, {response.json()=}")
        return False, "400"


def send_xml_to_ekinobilet(
        performance_data,
        show_data,
        payment,
        fond_kino_id,
        place,
        row,
        price,
        payment_id,
        order_id,
):
    try:
        ##отправка в министерство отчета о продаже
        import xml.etree.ElementTree as ET
        # print(performance_data)
        building_name = performance_data[6]
        id_procult = show_data[2]
        seans_date = f'''{performance_data[8].replace('-', '')} {performance_data[9]}'''
        pu_number = show_data[0]
        film_name = show_data[1]
        hall_name = performance_data[3]
        # выясняем время продажи
        delta = datetime.timedelta(hours=7)
        today = datetime.datetime.now(datetime.timezone.utc) + delta
        sale_date = today.strftime('%Y%m%d %H:%M:%S')
        doc_date = today.strftime('%Y%m%d_%H%M%S')
        # rrn = sber['authRefNum']
        rrn = payment.authorization_details.rrn
        # # Создаем структуру XML
        root = ET.Element('seans')
        root.set('ver', '3.2.0')
        root.set('org_id', str(fond_kino_id))
        root.set('showroom', str(hall_name))
        root.set('seans_date', str(seans_date))
        root.set('pu_number', str(pu_number))
        root.set('format', '2D')
        root.set('seans_title', str(film_name))
        root.set('event_id', str(id_procult))

        form = ET.SubElement(root, 'form')
        form.set('place_x', str(place))
        form.set('place_y', str(row))
        form.set('section', str(hall_name))
        form.set('price', str(price))
        form.set('discount', '0')
        form.set('ticket_type', 'Основной')
        form.set('sale_date', str(sale_date))
        form.set('subscription', 'false')
        form.set('online', 'true')
        form.set('webtax_included', 'false')
        form.set('payment_type', '1')
        form.set('payment_id', str(rrn))
        form.set('terminal_id', '26485891')
        form.set('terminal_owner', '5402052576')

        xml_data = ET.tostring(root, encoding='utf-8')
        xml_file_name = os.path.join(root_path, "xml_files", f'ekb_{fond_kino_id}_{doc_date}145.xml')
        # logger.info(xml_file_name)
        with open(xml_file_name, 'wb') as file:
            # Записываем XML-данные в файл
            file.write(xml_data)

        try:
            bot.send_message(5254091301, f'xml_file_name {order_id}\n{xml_file_name}')
            bot.send_document(5254091301, open(xml_file_name, 'rb'))
        except Exception:
            pass

        # print('xml_}', xml_data)
        # Создаем словарь с логином и паролем
        auth = {
            'login': '505@mirkino.pro',
            'password': 'pukugk',
        }
        # Загружаем XML-файл
        with open(xml_file_name, 'rb') as file:
            files = {
                'XMLfile': file
            }
            for i in range(5):
                try:
                    response = requests.post('https://ekinobilet.ru/ekbs/upload.aspx', data=auth, files=files)
                    break
                except Exception as e:
                    time.sleep(7)
        # response = requests.post('https://ekinobilet.ru/ekbs/upload.aspx', data=xml_data, auth=HTTPBasicAuth('505@mirkino.pro', 'pukugk'), headers={'Content-Type': 'application/xml; charset=utf-8'})
        # print(response.url)
        # print(response.content.decode('utf-8'))
        text_resp = str(response.content.decode('utf-8'))
        # print(text_resp)
        if 'error' not in text_resp:
            # print(200)
            with psycopg2.connect(db_path) as data:
                with data.cursor() as curs:
                    curs.execute("""UPDATE orders SET report_sented = 1 WHERE payment_id = %s""", (payment_id,))

        else:
            bot.send_message(5254091301,
                             f'!!!!Ошибка. Заказ оплачен, но в министерство правильно не отправлен\norder_id {order_id} ошибка {text_resp} файл {xml_file_name}')
    except Exception as e:
        logger.exception("Произошла ошибка")
        bot.send_message(5254091301,
                         f'!!!!Ошибка. Заказ оплачен, но в министерство правильно не отправлен\n{e} order_id {order_id} файл')


# проверяем статус переданного платежа, если платеж прошел, то ставим статус ок, если нет, то отменяем, в противном случае ничего не делаем
def check_payment_status(payment_id, report=True):
    is_succeeded = False

    Configuration.account_id = int(youkassa_shop_id)
    Configuration.secret_key = youkassa_secret_key

    payment = Payment.find_one(payment_id)
    payment_status = payment.status

    with psycopg2.connect(db_path) as data:
        with data.cursor() as curs:
            curs.execute("""SELECT * FROM orders WHERE payment_id = %s""", (payment_id,))
            order_data = curs.fetchone()

    order_id = order_data[0]
    place_id = order_data[4]
    price = order_data[5]
    user_id = order_data[1]
    row = order_data[11]
    place = order_data[12]
    performance_id = order_data[3]
    payment_msg_id = order_data[15]

    # Если оплата отменена ЮКАССА
    if payment_status in ["canceled", "succeeded", "pending", "waiting_for_capture"]:
        if payment_status == "waiting_for_capture":
            Payment.capture(payment_id)

        elif payment_status == 'canceled':
            params = {
                "sp": "WgA_SetOrderToNull",
                "idOrder": order_id,
                "df": "J",
            }
            for i in range(5):
                try:
                    response = requests.request("GET", url_kino_baza, params=params)
                    break
                except Exception as e:
                    bot.send_message(5254091301,
                                     f'!!!!Ошибка. Заказ canceled, но отменить не вышло {e}')
                    logger.exception("Произошла ошибка RRWgA_SetOrderToNull")
                    time.sleep(7)

            with psycopg2.connect(db_path) as data:
                with data.cursor() as curs:
                    curs.execute("""UPDATE orders SET status = 0 WHERE payment_id = %s""", (payment_id,))
            perf_markup = types.InlineKeyboardMarkup(row_width=5)
            perf_webapp = types.WebAppInfo(f"{url}/kino/{performance_id}/{user_id}")  # создаем webapp
            perf_but = types.KeyboardButton(text='Тот самый сеанс', web_app=perf_webapp)
            perf_markup.add(perf_but)
            try:
                bot.send_message(user_id,
                                 f'Заказ не был оплачен вовремя.\nЕс️ли еще не передумали, то вот тот самый сеанс, можете попробовать еще раз😄',
                                 reply_markup=perf_markup)
            except telebot.apihelper.ApiTelegramException:
                pass

            return "canceled"

        # Если оплата успешна ЮКАССА
        elif payment_status == 'succeeded':
            is_succeeded = True
            is_fk_report_send = True
            try:
                try:
                    bot.send_message(user_id,
                                     f'Заказ успешно оплачен.\nРяд {row} Место {place} Цена {price}\nНомер заказа {order_id}\nПросто продиктуйте номер заказа на входе чтобы пройти в зал☺️')
                except telebot.apihelper.ApiTelegramException:
                    pass
                params = {  # создаем оплату в базе миркино
                    "sp": "WgA_AddPayment",
                    "IdOrder": order_id,
                    "Amount": price,
                    "IdPaymentMethod": 11,
                    "idUser": 1,
                    "df": "J"}
                for i in range(5):
                    try:
                        response = requests.request("GET", url_kino_baza, params=params)
                        break
                    except Exception as e:
                        time.sleep(7)
                payment_kino = response.json()
                kino_add_payment_id = payment_kino['IdPayment']
                with psycopg2.connect(db_path) as data:
                    with data.cursor() as curs:
                        try:
                            kino_add_payment_id = int(kino_add_payment_id)
                            curs.execute(
                                """UPDATE orders SET status = 1, kino_add_payment_id = %s WHERE payment_id = %s""",
                                (kino_add_payment_id, payment_id))
                        except ValueError:
                            curs.execute("""UPDATE orders SET status = 1 WHERE payment_id = %s""",
                                         (payment_id,))

                        curs.execute("""SELECT * FROM performance WHERE performance_id = %s""",
                                     (performance_id,))
                        performance_data = curs.fetchone()

                        curs.execute("""SELECT fond_kino_id FROM cinemas WHERE building_id = %s""",
                                     (performance_data[2],))
                        fond_kino_id = curs.fetchone()[0]

                        curs.execute("""SELECT pu_number, name, id_procult FROM show WHERE show_id = %s""",
                                     (performance_data[1],))
                        show_data = curs.fetchone()

                        curs.execute("""SELECT report_sented FROM orders WHERE payment_id = %s""",
                                     (payment_id,))
                        is_fk_report_send = curs.fetchone()[0]
            except TypeError:
                bot.send_message(5254091301,
                                 f'!!!!Ошибка. Заказ оплачен, но оформить его правильно не вышло\n Я его пропускаю, вот данные клиента и заказа, свяжитесь с ним:order_id {order_data[0]}\nuser_id_tg {order_data[1]}\nperformance {order_data[3]}\nplace_id {order_data[4]}\nряд {order_data[11]}\nместо {order_data[12]}\npayment_id {order_data[6]}')
                # Антон
                if report:
                    bot.send_message(1013689498,
                                     f'!!!!Ошибка. Заказ оплачен, но оформить его правильно не вышло\n Я его пропускаю, вот данные клиента и заказа, свяжитесь с ним:order_id {order_data[0]}\nuser_id_tg {order_data[1]}\nperformance {order_data[3]}\nplace_id {order_data[4]}\nряд {order_data[11]}\nместо {order_data[12]}\npayment_id {order_data[6]}')
                with psycopg2.connect(db_path) as data:
                    with data.cursor() as curs:
                        curs.execute("""UPDATE orders SET status = 4 WHERE payment_id = %s""", (payment_id,))
            except Exception as e:
                logger.exception("Произошла ошибка")
                bot.send_message(5254091301,
                                 f'!!!!Ошибка. Заказ оплачен, но оформить его правильно не вышло\n{e}\nОтвет на запрос WgA_AddPayment {response.text}, статус {response}')

            if not is_fk_report_send:
                send_xml_to_ekinobilet(
                    performance_data,
                    show_data,
                    payment,
                    fond_kino_id,
                    place,
                    row,
                    price,
                    payment_id,
                    order_id,
                )

            rrn = payment.authorization_details.rrn

            with psycopg2.connect(db_path) as data:
                with data.cursor() as curs:
                    curs.execute("""SELECT date, time, show_id FROM performance where performance_id = %s""",
                                 (performance_id,))
                    performance = curs.fetchone()
                    curs.execute("""SELECT id_procult FROM show where show_id = %s""", (performance[2],))
                    event_id = curs.fetchone()[0]

            date_start = performance[0]
            date_end = performance[1]
            event_id = event_id
            date_time_str = f'{date_start} {date_end}'
            # Преобразование строки в объект datetime
            date_time_obj = datetime.datetime.strptime(date_time_str, '%Y-%m-%d %H:%M')

            # Преобразование datetime в UNIX timestamp
            event_session_timestamp = int(time.mktime(date_time_obj.timetuple()))

            buyer_info = "зуеввасилийсергеевич"

            ok, text = validate_pochta_bank(
                buyer_info=buyer_info,
                rrn=rrn,
                event_id=event_id,
                place_id=place_id,
                event_session_timestamp=event_session_timestamp,
            )
            if not ok:
                if text == "400":
                    return

                send_xml_to_ekinobilet(
                    performance_data,
                    show_data,
                    payment,
                    fond_kino_id,
                    place,
                    row,
                    -price,
                    payment_id,
                    order_id,
                )
                bot.send_message(
                    user_id,
                    f"Извините, возникла ошибка, деньги вернутся на вашу карту.\n{text}",
                )

    else:  # если есть ошибка
        bot.send_message(5254091301,
                         f'''!!!!!Ошибка в запросе юкассу о проверке статуса заказа\n{payment.status} {payment.id} {order_id}''')

    return is_succeeded


def unblock_all(user_id, performance_id, place_id):
    with psycopg2.connect(db_path) as data:
        with data.cursor() as curs:
            if place_id == 'all':
                # берем все брони у пользователя на этот сеанс
                curs.execute(
                    """SELECT performance_id, place_id, buyer_id, order_id FROM orders WHERE user_id = %s AND status = 2;""",
                    (user_id,))
                orders_to_close = curs.fetchall()
            else:
                # берем все брони кроме place_id который нам передали
                curs.execute(
                    """SELECT performance_id, place_id, buyer_id, order_id FROM orders WHERE user_id = %s AND status = 2 AND place_id != %s;""",
                    (user_id, place_id))
                orders_to_close = curs.fetchall()

            # print('11111111', orders_to_close)
            # проходимся по всем таким броням
            for order in orders_to_close:
                # print(order)
                params = {
                    "sp": "WgA_SetOrderToNull",
                    "idOrder": order[3],
                    "df": "J",
                }
                for i in range(5):
                    try:
                        response = requests.request("GET", url_kino_baza, params=params)
                        break
                    except Exception as e:
                        bot.send_message(5254091301,
                                         f'!!!!Ошибка. Заказ unblock_all, но отменить не вышло {e}')
                        logger.exception("Произошла ошибка RRWgA_SetOrderToNull")
                        time.sleep(7)

                curs.execute(
                    """UPDATE orders SET status = 0 WHERE performance_id = %s AND place_id = %s AND buyer_id = %s AND user_id = %s""",
                    (order[0], order[1], order[2], user_id))


# check_payment_status("2ebeeb04-000f-5000-a000-109d870811c3")


def unblock_5_min():
    with psycopg2.connect(db_path) as data:
        with data.cursor() as curs:
            # берем все брони где не создан заказ и прошло 5 мин
            curs.execute(
                """SELECT performance_id, place_id, buyer_id, payment_id, order_id, user_id FROM orders WHERE status = 2 AND place_locked_time < %s;""",
                (time.time() - 300,))
            place_to_unblock = curs.fetchall()

    # print(time.time()-900)
    # print('11111111', place_to_unblock)
    # проходимся по всем таким броням
    for order in place_to_unblock:
        if order[4] is None:
            with psycopg2.connect(db_path) as data:
                with data.cursor() as curs:
                    curs.execute("""UPDATE orders SET status = 0 WHERE user_id = %s AND performance_id = %s""",
                                 (order[5], order[0]))
            continue

        logger.info(order)
        params = {
            "sp": "WgA_SetOrderToNull",
            "idOrder": order[4],
            "df": "J",
        }
        for i in range(5):
            try:
                response = requests.request("GET", url_kino_baza, params=params)
                logger.info(decode_unicode(response.text))
                break
            except Exception as e:
                bot.send_message(5254091301,
                                 f'!!!!Ошибка. Заказ unblock_5_min, но отменить не вышло {e}')
                logger.exception("Произошла ошибка RRWgA_SetOrderToNull")
                time.sleep(7)

        with psycopg2.connect(db_path) as data:
            with data.cursor() as curs:
                curs.execute("""UPDATE orders SET status = 0 WHERE order_id = %s""", (order[4],))


def decode_unicode(data):
    if isinstance(data, str):
        return data.encode('utf-8').decode('unicode_escape')
    elif isinstance(data, dict):
        return {k: decode_unicode(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [decode_unicode(v) for v in data]
    return data
