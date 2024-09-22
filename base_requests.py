import json
import os

import requests
import sqlite3
import time
import datetime

import urllib3
from loguru import logger
from telebot import types
import telebot
import re

from urllib3.exceptions import InsecureRequestWarning
from yookassa import Payment, Configuration

from config import bot, url_kino_baza, url_prokultura, kinopoisk_token, sber_login, sber_password, info_log_file, \
    db_path, root_path, url, youkassa_shop_id, youkassa_secret_key
from pkg.log import CustomLogger

CustomLogger().add_logger(info_log_file, __name__)


def film_update_main():
    i = 1
    while True:
        try:
            t1 = time.time()
            if i % 2 == 0 or i == 1:
                all_show_request()
            t2 = time.time()
            get_show_info()
            t3 = time.time()
            if i % 10 == 0 or i == 1:
                what_show_can_be_sell_pushkin_card()
            t4 = time.time()
            get_kinopoisk_info()
            t5 = time.time()
            if i % 4 == 0 or i == 1:
                all_performances_request()
            t6 = time.time()
            unblock_5_min()  # разблокируем все где 5 мин заблочено и не куплено
            t7 = time.time()
            # проверяем всех кто должен оплатить
            with sqlite3.connect(db_path, timeout=15000) as data:
                curs = data.cursor()
                orders = curs.execute("""SELECT payment_id FROM orders WHERE status == 3;""").fetchall()
            for order in orders:
                check_payment_status(order[0])
            t8 = time.time()
            # with open('enviroments/kino/film_update.txt', 'a') as file:
            #               file.write(f"")
            # print(f'i = {i}\nall_show_request {round(t2-t1, 3)}\nget_show_info {round(t3-t2, 3)}\nwhat_show_can_be_sell_pushkin_card {round(t4-t3, 3)}\nget_kinopoisk_info {round(t5-t4, 3)}\nall_performances_request {round(t6-t5, 3)}\nunblock_5_min {round(t7-t6, 3)}\ncheck_payment_status {round(t8-t7, 3)}\nвсе {round(t8-t1, 3)}')
            # with sqlite3.connect(db_path, timeout=15000) as data:
            #     curs = data.cursor()
            #     curs.execute("""UPDATE show SET pushkin_card = 1""")

        except Exception as e:
            logger.exception("Произошла ошибка")
            bot.send_message(5254091301, f'Ошибка в вызове функций по обновлению всей базы film_update_main\n{e}')
        finally:
            i += 1
            time.sleep(30)


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
            with sqlite3.connect(db_path, timeout=15000) as data:
                curs = data.cursor()
                data_show = response.json()
                for show in data_show:
                    # print(show, '\n')
                    show['ShowName'] = show['ShowName'].replace('&quot;', '').replace('«', '').replace('»', '')
                    curs.execute("""INSERT OR IGNORE INTO show (show_id, name, duration) VALUES (?, ?, ?);""",
                                 (show['IdShow'], show['ShowName'], show['Duration']))
                    # если обновили название, то оно обновится в базе
                    curs.execute("""UPDATE show SET name = ?, duration = ? WHERE show_id = ?""",
                                 (show['ShowName'], show['Duration'], show['IdShow']))
                    shows = curs.execute("""SELECT name FROM show WHERE show_id == ?;""", (43537885,)).fetchall()
                    # print(shows)
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
        with sqlite3.connect(db_path, timeout=15000) as data:
            curs = data.cursor()
            shows = curs.execute("""SELECT show_id FROM show WHERE kinopoisk_id IS NULL;""").fetchall()
            # print(shows)
            for show in shows:
                show_id = show[0]
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

                if response.status_code == 200:
                    data_show = response.json()
                    # print(data_show, '\n')
                    curs.execute("""UPDATE show SET kinopoisk_id = ? WHERE show_id == ?""",
                                 (data_show['Remark'], show_id))
                else:
                    pass
                    # bot.send_message(5254091301, f'Ошибка по запросу Wga_GetShowInfo\nВ ответ на запрос возвращается код {response.status_code}')

    except Exception as e:
        logger.exception("Произошла ошибка")
        bot.send_message(5254091301, f'Ошибка базы по запросу всех Wga_GetShowInfo \n{e}')


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
            # print(len(data['events']))
            accepted_films_list = []
            pu_number_list = {}
            id_procult_list = {}
            # добавляем их в списокфильмов которые можно
            for event in data['events']:
                # print(event['name'])
                match = re.search(r'«(.+)', event['name'])
                # film_name = event['name'].split('«')[1].split('»')[0].lower() #старый способ, не работает когда внутри другие кавычки
                try:
                    film_name = match.group(1).lower()
                    film_name = film_name.replace('«', '').replace('»', '')
                except Exception as e:
                    logger.exception(f"Произошла ошибка {e}")
                    continue

                if 'Позывной' in event['name']:
                    logger.info(film_name)
                pu_number_list[film_name] = event['rentalCertificate'][0]
                id_procult_list[film_name] = event[r'_id']
                # print(event, '\n\n\n')
                accepted_films_list.append(film_name)

            with sqlite3.connect(db_path, timeout=15000) as data:
                curs = data.cursor()
                # берем все фильмы что у нас есть, и сверяем названия со списком разрешенных.
                # ghb этом названия могут быть одинаковые у нескольких шоу, меняем у всех
                shows = curs.execute("""SELECT DISTINCT name FROM show;""").fetchall()
                # print(accepted_films_list)
                # print(id_procult_list)
                for show in shows:
                    film_name = show[0].lower()
                    if film_name in accepted_films_list:
                        curs.execute(
                            """UPDATE show SET pushkin_card = True, pu_number = ?, id_procult = ? WHERE name == ?""",
                            (pu_number_list[film_name], id_procult_list[film_name], show[0]))
                        # print('True', show[0].lower())
                    elif film_name not in accepted_films_list:
                        curs.execute("""UPDATE show SET pushkin_card = False WHERE name == ?""", (show[0],))
                        # print('False', show[0].lower())

        # if response.status_code == 200:
        #     data_show = response.json()
        #     print(data_show['Remark'], '\n')
        #     curs.execute("""UPDATE show SET kinopoisk_id = ? WHERE show_id == ?""", (data_show['Remark'], show_id))
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
        with sqlite3.connect(db_path, timeout=15000) as data:
            curs = data.cursor()
            shows = curs.execute(
                """SELECT kinopoisk_id FROM show WHERE kinopoisk_id IS NOT NULL AND kinopoisk_id != ' ' AND (poster IS NULL OR poster == '');""").fetchall()
            # print(shows)
            for show in shows:
                kinopoisk_id = show[0]
                # запрашиваем список всех show
                # 'https://api.kinopoisk.dev/v1/movie/4907586'
                params = {
                    "token": f"{kinopoisk_token}"
                }

                response = requests.request("GET", f'https://api.kinopoisk.dev/v1/movie/{kinopoisk_id}', params=params)
                # print(response.url)

                if response.status_code == 200:
                    data_kinopoisk = response.json()
                    # print(data_kinopoisk['description'], '\n')
                    # print(data_kinopoisk['poster']['url'], '\n')
                    # print(data_kinopoisk['rating']['kp'], '\n')
                    curs.execute(
                        """UPDATE show SET description = ?, poster = ?, kp_rating = ? WHERE kinopoisk_id == ?""", (
                            data_kinopoisk['description'], data_kinopoisk['poster']['url'],
                            data_kinopoisk['rating']['kp'],
                            kinopoisk_id))
                else:
                    bot.send_message(5254091301,
                                     f'Ошибка по запросу get_kinopoisk_info \nВ ответ на запрос возвращается код {response.status_code}')

    except Exception as e:
        logger.exception("Произошла ошибка")
        bot.send_message(5254091301, f'Ошибка базы по запросу всех get_kinopoisk_info \n{e}')


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
            with sqlite3.connect(db_path, timeout=15000) as data:
                curs = data.cursor()
                # если получен верный запрос в верной форме, стираем старые сеансы и заполняем заново
                curs.execute("""DELETE FROM performance""")
                for data_performance in data_performances:
                    try:
                        # print(data_performance)
                        # Получение отдельной даты и времени
                        try:
                            dt = datetime.datetime.strptime(data_performance['DateTime'], "%B %d %Y %I:%M:%S:%f%p")
                        except ValueError:
                            dt = datetime.datetime.strptime(data_performance['DateTime'], "%b %d %Y %I:%M:%S:%f%p")
                        date = dt.date()
                        date_str = datetime.datetime.strftime(date, '%Y-%m-%d')
                        time = dt.time()
                        time_str = time.strftime('%H:%M')

                        # print(date_str, time)
                        # print(today_date, date_str, today_time, time_str)
                        # отсеиваем все, что прошло более 14 минут назад
                        # print(data_performance)
                        curs.execute(
                            """INSERT OR IGNORE INTO performance (performance_id, show_id, building_id, hallname, date, time, minprice, maxprice, freeplaces, building_name, hall_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);""",
                            (data_performance['IdPerformance'], data_performance['IdShow'],
                             data_performance['IdBuilding'], data_performance['HallName'], date_str, time_str,
                             data_performance['MinPrice'], data_performance['MaxPrice'], data_performance['FreePlace'],
                             data_performance['BuildingName'], data_performance['IdHall']))
                    except Exception as e:
                        logger.exception(f"Произошла ошибка {e}")

        except Exception as e:
            logger.exception("Произошла ошибка")
            bot.send_message(5254091301, f'Ошибка базы по запросу all_performances_request \n{e}')
    else:
        bot.send_message(5254091301,
                         f'Ошибка по запросу all_performances_request \nВ ответ на запрос возвращается код {response.status_code}')


def user_reg(user_id):  # проверяем зареган ли пользователь, если нет то регаем
    with sqlite3.connect(db_path, timeout=15000) as data:
        curs = data.cursor()
        # если пользователя еще нет
        user = curs.execute("""SELECT user_id FROM users WHERE user_id == ?;""", (user_id,)).fetchone()
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
                curs.execute("""INSERT OR IGNORE INTO users (user_id, buyer_id) VALUES (?, ?);""",
                             (user_id, buyer['IdClient']))
            except Exception:
                curs.execute("""INSERT OR IGNORE INTO users (user_id, buyer_id) VALUES (?, ?);""", (user_id, 998277))

    return


# проверяем статус переданного платежа, если платеж прошел, то ставим статус ок, если нет, то отменяем, в противном случае ничего не делаем
def check_payment_status(payment_id):
    # params = {
    #     "userName": sber_login,
    #     "password": sber_password,
    #     'orderId': payment_id,
    #     'language': 'ru'
    # }
    #
    # # Отключение предупреждений о небезопасном соединении
    # urllib3.disable_warnings(InsecureRequestWarning)
    #
    # # Создание сессии с отключенной проверкой сертификата
    # session = requests.Session()
    # session.verify = False
    # for i in range(4):
    #     try:
    #         response = session.get(
    #             'https://securepayments.sberbank.ru/payment/rest/getOrderStatusExtended.do',
    #             params=params,
    #         )
    #         break
    #     except Exception as e:
    #         time.sleep(4)
    #
    # # print(response.url)
    # sber = response.json()
    # print(sber)

    Configuration.account_id = int(youkassa_shop_id)
    Configuration.secret_key = youkassa_secret_key

    payment = Payment.find_one(payment_id)
    payment_status = payment.status

    with sqlite3.connect(db_path, timeout=15000) as data:
        curs = data.cursor()
        order_data = curs.execute("""SELECT * FROM orders WHERE payment_id == ?""", (payment_id,)).fetchone()
    order_id = order_data[0]
    price = order_data[5]
    user_id = order_data[1]
    row = order_data[11]
    place = order_data[12]
    performance_id = order_data[3]

    # сбер проверка
    # if sber['errorCode'] == '0':
    #     if sber['orderStatus'] in (3, 4, 6):  # платеж несостоялся
    #         params = {  # отменяем заказ в базе миркино
    #             "sp": "WgA_SetOrderToNull",
    #             "idOrder": order_id,
    #             "df": "J"}
    #         for i in range(5):
    #             try:
    #                 response = requests.request("GET", url_kino_baza, params=params)
    #                 break
    #             except Exception as e:
    #                 time.sleep(7)
    #         with sqlite3.connect(db_path, timeout=15000) as data:
    #             curs = data.cursor()
    #             curs.execute("""UPDATE orders SET status = 0 WHERE payment_id == ?""", (payment_id,))
    #         perf_markup = types.InlineKeyboardMarkup(row_width=5)
    #         perf_webapp = types.WebAppInfo(f"{url}/kino/{performance_id}")  # создаем webapp
    #         perf_but = types.KeyboardButton(text='Тот самый сеанс', web_app=perf_webapp)
    #         perf_markup.add(perf_but)
    #         try:
    #             bot.send_message(user_id,
    #                              f'Заказ не был оплачен вовремя.\nЕс️ли еще не передумали, то вот тот самый сеанс, можете попробовать еще раз😄',
    #                              reply_markup=perf_markup)
    #         except telebot.apihelper.ApiTelegramException:
    #             pass
    #     elif sber['orderStatus'] == 2:  # платеж проведен успешно
    #         try:
    #             try:
    #                 bot.send_message(user_id,
    #                                  f'Заказ успешно оплачен.\nРяд {row} Место {place} Цена {price}\nНомер заказа {order_id}\nПросто продиктуйте номер заказа на входе чтобы пройти в зал☺️')
    #             except telebot.apihelper.ApiTelegramException:
    #                 pass
    #             params = {  # создаем оплату в базе миркино
    #                 "sp": "WgA_AddPayment",
    #                 "IdOrder": order_id,
    #                 "Amount": price,
    #                 "IdPaymentMethod": 11,
    #                 "idUser": 1,
    #                 "df": "J"}
    #             for i in range(5):
    #                 try:
    #                     response = requests.request("GET", url_kino_baza, params=params)
    #                     break
    #                 except Exception as e:
    #                     time.sleep(7)
    #             payment_kino = response.json()
    #             # print(payment_kino)
    #             kino_add_payment_id = payment_kino['IdPayment']
    #             with sqlite3.connect(db_path, timeout=15000) as data:
    #                 curs = data.cursor()
    #                 curs.execute("""UPDATE orders SET status = 1, kino_add_payment_id = ? WHERE payment_id == ?""",
    #                              (kino_add_payment_id, payment_id))
    #                 performance_data = curs.execute("""SELECT * FROM performance WHERE performance_id == ?""",
    #                                                 (performance_id,)).fetchone()
    #                 fond_kino_id = curs.execute("""SELECT fond_kino_id FROM cinemas WHERE building_id == ?""",
    #                                             (performance_data[2],)).fetchone()[0]
    #                 show_data = curs.execute("""SELECT pu_number, name, id_procult FROM show WHERE show_id == ?""",
    #                                          (performance_data[1],)).fetchone()
    #                 is_fk_report_send = curs.execute("""SELECT report_sented FROM orders WHERE payment_id == ?""",
    #                                                  (payment_id,)).fetchone()[0]
    #             if is_fk_report_send == True:  # если уже отправляли отчет, то больше не надо
    #                 return
    #         except TypeError:
    #             bot.send_message(5254091301,
    #                              f'!!!!Ошибка. Заказ оплачен, но оформить его правильно не вышло\n Я его пропускаю, вот данные клиента и заказа, свяжитесь с ним:order_id {order_data[0]}\nuser_id_tg {order_data[1]}\nperformance {order_data[3]}\nplace_id {order_data[4]}\nряд {order_data[11]}\nместо {order_data[12]}\npayment_id {order_data[6]}')
    #             # Антон
    #             bot.send_message(1013689498,
    #                              f'!!!!Ошибка. Заказ оплачен, но оформить его правильно не вышло\n Я его пропускаю, вот данные клиента и заказа, свяжитесь с ним:order_id {order_data[0]}\nuser_id_tg {order_data[1]}\nperformance {order_data[3]}\nplace_id {order_data[4]}\nряд {order_data[11]}\nместо {order_data[12]}\npayment_id {order_data[6]}')
    #             with sqlite3.connect(db_path, timeout=15000) as data:
    #                 curs = data.cursor()
    #                 curs.execute("""UPDATE orders SET status = 4 WHERE payment_id == ?""", (payment_id,))
    #         except Exception as e:
    #             logger.exception("Произошла ошибка")
    #             bot.send_message(5254091301,
    #                              f'!!!!Ошибка. Заказ оплачен, но оформить его правильно не вышло\n{e}\nОтвет на запрос WgA_AddPayment {response.text}, статус {response}')
    #         try:
    #             ##отправка в министерство отчета о продаже
    #             import xml.etree.ElementTree as ET
    #             # print(performance_data)
    #             building_name = performance_data[9]
    #             id_procult = show_data[2]
    #             seans_date = f'''{performance_data[4].replace('-', '')} {performance_data[5]}'''
    #             pu_number = show_data[0]
    #             film_name = show_data[1]
    #             hall_name = performance_data[3]
    #             # выясняем время продажи
    #             delta = datetime.timedelta(hours=7)
    #             today = datetime.datetime.now(datetime.timezone.utc) + delta
    #             sale_date = today.strftime('%Y%m%d %H:%M:%S')
    #             doc_date = today.strftime('%Y%m%d_%H%M%S')
    #             rrn = sber['authRefNum']
    #             # # Создаем структуру XML
    #             root = ET.Element('seans')
    #             root.set('ver', '3.2.0')
    #             root.set('org_id', str(fond_kino_id))
    #             root.set('showroom', str(hall_name))
    #             root.set('seans_date', str(seans_date))
    #             root.set('pu_number', str(pu_number))
    #             root.set('format', '2D')
    #             root.set('seans_title', str(film_name))
    #             root.set('event_id', str(id_procult))
    #
    #             form = ET.SubElement(root, 'form')
    #             form.set('place_x', str(place))
    #             form.set('place_y', str(row))
    #             form.set('section', str(hall_name))
    #             form.set('price', str(price))
    #             form.set('discount', '0')
    #             form.set('ticket_type', 'Основной')
    #             form.set('sale_date', str(sale_date))
    #             form.set('subscription', 'false')
    #             form.set('online', 'true')
    #             form.set('webtax_included', 'false')
    #             form.set('payment_type', '1')
    #             form.set('payment_id', str(rrn))
    #             form.set('terminal_id', '26485891')
    #             form.set('terminal_owner', '5402052576')
    #
    #             xml_data = ET.tostring(root, encoding='utf-8')
    #             xml_file_name = os.path.join(root_path, "xml_files", f'ekb_{fond_kino_id}_{doc_date}145.xml')
    #             with open(xml_file_name, 'wb') as file:
    #                 # Записываем XML-данные в файл
    #                 file.write(xml_data)
    #             # print('xml_}', xml_data)
    #             # Создаем словарь с логином и паролем
    #             auth = {
    #                 'login': '505@mirkino.pro',
    #                 'password': 'pukugk',
    #             }
    #             # Загружаем XML-файл
    #             with open(xml_file_name, 'rb') as file:
    #                 files = {
    #                     'XMLfile': file
    #                 }
    #                 for i in range(5):
    #                     try:
    #                         response = requests.post('https://ekinobilet.ru/ekbs/upload.aspx', data=auth, files=files)
    #                         break
    #                     except Exception as e:
    #                         time.sleep(7)
    #             # response = requests.post('https://ekinobilet.ru/ekbs/upload.aspx', data=xml_data, auth=HTTPBasicAuth('505@mirkino.pro', 'pukugk'), headers={'Content-Type': 'application/xml; charset=utf-8'})
    #             # print(response.url)
    #             # print(response.content.decode('utf-8'))
    #             text_resp = str(response.content.decode('utf-8'))
    #             # print(text_resp)
    #             if 'error' not in text_resp:
    #                 # print(200)
    #                 with sqlite3.connect(db_path, timeout=15000) as data:
    #                     curs = data.cursor()
    #                     curs.execute("""UPDATE orders SET report_sented = True WHERE payment_id == ?""", (payment_id,))
    #
    #             else:
    #                 bot.send_message(5254091301,
    #                                  f'!!!!Ошибка. Заказ оплачен, но в министерство правильно не отправлен\norder_id {order_id} ошибка {text_resp} файл {xml_file_name}')
    #         except Exception as e:
    #             logger.exception("Произошла ошибка")
    #             bot.send_message(5254091301,
    #                              f'!!!!Ошибка. Заказ оплачен, но в министерство правильно не отправлен\n{e} order_id {order_id} файл {xml_file_name}')

    # Если оплата отменена ЮКАССА
    if payment_status == 'canceled':
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
                time.sleep(7)
        with sqlite3.connect(db_path, timeout=15000) as data:
            curs = data.cursor()
            curs.execute("""UPDATE orders SET status = 0 WHERE payment_id == ?""", (payment_id,))
        perf_markup = types.InlineKeyboardMarkup(row_width=5)
        perf_webapp = types.WebAppInfo(f"{url}/kino/{performance_id}")  # создаем webapp
        perf_but = types.KeyboardButton(text='Тот самый сеанс', web_app=perf_webapp)
        perf_markup.add(perf_but)
        try:
            bot.send_message(user_id,
                             f'Заказ не был оплачен вовремя.\nЕс️ли еще не передумали, то вот тот самый сеанс, можете попробовать еще раз😄',
                             reply_markup=perf_markup)
        except telebot.apihelper.ApiTelegramException:
            pass

    # Если оплата успешна ЮКАССА
    elif payment_status == 'success':
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
            # print(payment_kino)
            kino_add_payment_id = payment_kino['IdPayment']
            with sqlite3.connect(db_path, timeout=15000) as data:
                curs = data.cursor()
                curs.execute("""UPDATE orders SET status = 1, kino_add_payment_id = ? WHERE payment_id == ?""",
                             (kino_add_payment_id, payment_id))
                performance_data = curs.execute("""SELECT * FROM performance WHERE performance_id == ?""",
                                                (performance_id,)).fetchone()
                fond_kino_id = curs.execute("""SELECT fond_kino_id FROM cinemas WHERE building_id == ?""",
                                            (performance_data[2],)).fetchone()[0]
                show_data = curs.execute("""SELECT pu_number, name, id_procult FROM show WHERE show_id == ?""",
                                         (performance_data[1],)).fetchone()
                is_fk_report_send = curs.execute("""SELECT report_sented FROM orders WHERE payment_id == ?""",
                                                 (payment_id,)).fetchone()[0]
            if is_fk_report_send == True:  # если уже отправляли отчет, то больше не надо
                return
        except TypeError:
            bot.send_message(5254091301,
                             f'!!!!Ошибка. Заказ оплачен, но оформить его правильно не вышло\n Я его пропускаю, вот данные клиента и заказа, свяжитесь с ним:order_id {order_data[0]}\nuser_id_tg {order_data[1]}\nperformance {order_data[3]}\nplace_id {order_data[4]}\nряд {order_data[11]}\nместо {order_data[12]}\npayment_id {order_data[6]}')
            # Антон
            bot.send_message(1013689498,
                             f'!!!!Ошибка. Заказ оплачен, но оформить его правильно не вышло\n Я его пропускаю, вот данные клиента и заказа, свяжитесь с ним:order_id {order_data[0]}\nuser_id_tg {order_data[1]}\nperformance {order_data[3]}\nplace_id {order_data[4]}\nряд {order_data[11]}\nместо {order_data[12]}\npayment_id {order_data[6]}')
            with sqlite3.connect(db_path, timeout=15000) as data:
                curs = data.cursor()
                curs.execute("""UPDATE orders SET status = 4 WHERE payment_id == ?""", (payment_id,))
        except Exception as e:
            logger.exception("Произошла ошибка")
            bot.send_message(5254091301,
                             f'!!!!Ошибка. Заказ оплачен, но оформить его правильно не вышло\n{e}\nОтвет на запрос WgA_AddPayment {response.text}, статус {response}')
        try:
            ##отправка в министерство отчета о продаже
            import xml.etree.ElementTree as ET
            # print(performance_data)
            building_name = performance_data[9]
            id_procult = show_data[2]
            seans_date = f'''{performance_data[4].replace('-', '')} {performance_data[5]}'''
            pu_number = show_data[0]
            film_name = show_data[1]
            hall_name = performance_data[3]
            # выясняем время продажи
            delta = datetime.timedelta(hours=7)
            today = datetime.datetime.now(datetime.timezone.utc) + delta
            sale_date = today.strftime('%Y%m%d %H:%M:%S')
            doc_date = today.strftime('%Y%m%d_%H%M%S')
            # rrn = sber['authRefNum']
            rrn = payment.id
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
            with open(xml_file_name, 'wb') as file:
                # Записываем XML-данные в файл
                file.write(xml_data)
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
                with sqlite3.connect(db_path, timeout=15000) as data:
                    curs = data.cursor()
                    curs.execute("""UPDATE orders SET report_sented = True WHERE payment_id == ?""", (payment_id,))

            else:
                bot.send_message(5254091301,
                                 f'!!!!Ошибка. Заказ оплачен, но в министерство правильно не отправлен\norder_id {order_id} ошибка {text_resp} файл {xml_file_name}')
        except Exception as e:
            logger.exception("Произошла ошибка")
            bot.send_message(5254091301,
                             f'!!!!Ошибка. Заказ оплачен, но в министерство правильно не отправлен\n{e} order_id {order_id} файл {xml_file_name}')


    else:  # если есть ошибка
        bot.send_message(5254091301,
                         f'''!!!!!Ошибка в запросе юкассу о проверке статуса заказа\n{payment.status} {payment.id} {order_id}''')
        with sqlite3.connect(db_path, timeout=15000) as data:
            curs = data.cursor()
            curs.execute("""DELETE FROM orders WHERE payment_id = ?""", (payment_id,))


def unblock_5_min():
    with sqlite3.connect(db_path, timeout=15000) as data:
        curs = data.cursor()
        # берем все брони где не создан заказ и прошло 5 мин
        place_to_unblock = curs.execute(
            """SELECT performance_id, place_id, buyer_id FROM orders WHERE status == 2 AND place_locked_time < ?;""",
            (time.time() - 300,)).fetchall()
        # print(time.time()-900)
        # print('11111111', place_to_unblock)
        # проходимся по всем таким броням
        for order in place_to_unblock:
            # print(order)
            params = {
                "sp": "WgA_UnlockPlace",
                "IdPerformance": order[0],
                "IdPlace": order[1],
                "IdClient": order[2],
                "df": "J"}
            for i in range(5):
                try:
                    response = requests.request("GET", 'http://195.208.148.248:18088/TicketAutomat/get.php',
                                                params=params)
                    break
                except Exception as e:
                    time.sleep(7)

            curs.execute(
                """UPDATE orders SET status == 0 WHERE performance_id == ? AND place_id == ? AND buyer_id == ?""",
                (order[0], order[1], order[2]))

# def to_null():

#     params = {
#     "sp": "WgA_SetOrderToNull",
#     "IdOrder": 35738691,
#     "df": "J" }
#     response = requests.request("GET", url_kino_baza, params=params)

# to_null()\

# def sber():

#     from requests.packages.urllib3.exceptions import InsecureRequestWarning

#     params = {
#     "userName": sber_login,
#     "password": sber_password,
#     'orderId': 'f3087273-7d62-74f5-8d43-6f9e02850e7b',
#     'language': 'ru'
#     }

#     # Отключение предупреждений о небезопасном соединении
#     requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

#     # Создание сессии с отключенной проверкой сертификата
#     session = requests.Session()
#     session.verify = False
#     response = session.get('https://securepayments.sberbank.ru/payment/rest/getOrderStatusExtended.do', params=params)
#     #print(response.url)
#     sber = response.json()
#     print(sber)
# sber()


# def send_to_min():
#     params = {
#         "userName": sber_login,
#         "password": sber_password,
#         'orderId': '9a0c3fc0-54d2-7fd9-8cbb-e21502850e7b',
#         'language': 'ru'
#     }
#
#     # Отключение предупреждений о небезопасном соединении
#     urllib3.disable_warnings(InsecureRequestWarning)
#
#     # Создание сессии с отключенной проверкой сертификата
#     session = requests.Session()
#     session.verify = False
#     response = session.get('https://securepayments.sberbank.ru/payment/rest/getOrderStatusExtended.do', params=params)
#     # print(response.url)
#     sber = response.json()
#     # print(sber)
#     with sqlite3.connect(db_path, timeout=15000) as data:
#         curs = data.cursor()
#         performance_data = [9377428, 43037535, 1009, 'Россия б/з', '2023-05-21', '17:25', 250, 250, 418, 'Россия', 10]
#         fond_kino_id = \
#             curs.execute("""SELECT fond_kino_id FROM cinemas WHERE building_id == ?""",
#                          (performance_data[2],)).fetchone()[
#                 0]
#         show_data = [111006223, 'Хитровка. Знак четырёх', 3144867]
#
#     ##отправка в министерство отчета о продаже
#     import xml.etree.ElementTree as ET
#     # print(performance_data)
#     building_name = performance_data[9]
#     id_procult = show_data[2]
#     seans_date = f'''{performance_data[4].replace('-', '')} {performance_data[5]}'''
#     pu_number = show_data[0]
#     film_name = show_data[1]
#     hall_name = performance_data[3]
#     # выясняем время продажи
#     delta = datetime.timedelta(hours=7)
#     today = datetime.datetime.now(datetime.timezone.utc) + delta
#     sale_date = today.strftime('%Y%m%d %H:%M:%S')
#     doc_date = today.strftime('%Y%m%d_%H%M%S')
#     rrn = sber['authRefNum']
#     # # Создаем структуру XML
#     root = ET.Element('seans')
#     root.set('ver', '3.2.0')
#     root.set('org_id', str(fond_kino_id))
#     root.set('showroom', str(hall_name))
#     root.set('seans_date', str(seans_date))
#     root.set('pu_number', str(pu_number))
#     root.set('format', '2D')
#     root.set('seans_title', str(film_name))
#     root.set('event_id', str(id_procult))
#
#     form = ET.SubElement(root, 'form')
#     form.set('place_x', str(17))
#     form.set('place_y', str(16))
#     form.set('section', str(hall_name))
#     form.set('price', str(-190))
#     form.set('discount', '0')
#     form.set('ticket_type', 'Основной')
#     form.set('sale_date', str(sale_date))
#     form.set('subscription', 'false')
#     form.set('online', 'true')
#     form.set('webtax_included', 'false')
#     form.set('payment_type', '1')
#     form.set('payment_id', str(rrn))
#     form.set('terminal_id', '26485891')
#     form.set('terminal_owner', '5402052576')
#
#     xml_data = ET.tostring(root, encoding='utf-8')
#     xml_file_name = os.path.join(root_path, "xml_files", f'ekb_{fond_kino_id}_{doc_date}145.xml')
#     with open(xml_file_name, 'wb') as file:
#         # Записываем XML-данные в файл
#         file.write(xml_data)
#     # print('xml_}', xml_data)
#     # Создаем словарь с логином и паролем
#     auth = {
#         'login': '505@mirkino.pro',
#         'password': 'pukugk',
#     }
#     # Загружаем XML-файл
#     with open(xml_file_name, 'rb') as file:
#         files = {
#             'XMLfile': file
#         }
#
#         # response = requests.post('https://ekinobilet.ru/ekbs/upload.aspx', data=auth, files=files)
#
#     # print(response.url)
#     # print(response.content.decode('utf-8'))
#     text_resp = str(response.content.decode('utf-8'))
# send_to_min()
