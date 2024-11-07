import datetime
import os
import sys
import time

import requests
from dotenv import load_dotenv
from yookassa import Configuration, Payment

# sys.path.append('/enviroments/kino')
from config import info_log_file, bot, db_path, error_log_file, log_dir, youkassa_shop_id, youkassa_secret_key, \
    url_kino_baza, root_path

import cherrypy

from pkg.log import CustomLogger

CustomLogger().init_logging()
import sql_create
import sqlite3
from loguru import logger
import base_requests
import threading
import telebot
import send_messages

CustomLogger().add_logger(info_log_file, __name__)

threading.Thread(target=base_requests.film_update_main).start()


@bot.message_handler(content_types=['text', 'comands'], chat_types=['private'], commands=['logs'])
def logs_text(message):
    if message.from_user.id != 5254091301:
        return

    try:
        bot.send_document(message.from_user.id, open(info_log_file, 'rb'))
        bot.send_document(message.from_user.id, open(error_log_file, 'rb'))

        info_server_log_file = os.path.join(log_dir, "info_server.log")
        bot.send_document(message.from_user.id, open(info_server_log_file, 'rb'))
    except Exception as e:
        logger.exception(f"Произошла ошибка {e}")


@bot.message_handler(content_types=['text', 'comands'], chat_types=['private'], commands=['start'])
def start_text(message):

    args = message.text.split(" ")
    if len(args) <= 1:
        return

    if not args[1].startswith("finishpayment"):
        return

    finishpayment_data = args[1].split(",")
    if len(finishpayment_data) <= 1:
        return

    order_id = finishpayment_data[1]
    try:
        order_id = int(order_id)
    except Exception:
        return

    with sqlite3.connect(db_path, timeout=15000) as data:
        curs = data.cursor()
        performance = curs.execute("""SELECT payment_id FROM orders WHERE order_id == ?;""", (order_id,))
    # is_succeeded = base_requests.check_payment_status(performance.fetchone()[0])


@bot.message_handler(content_types=['text', 'comands'], chat_types=['private'], commands=['order_return'])
def start_text(message):
    bot.send_message(chat_id=message.from_user.id, text="Заказ возвращен")
    with sqlite3.connect(db_path, timeout=15000) as data:
        curs = data.cursor()
        order_data = curs.execute("""SELECT * FROM orders WHERE order_id = ?""", (38891045,)).fetchone()

    order_id = order_data[0]
    price = -order_data[5]
    payment_id = order_data[6]
    user_id = order_data[1]
    row = order_data[11]
    place = order_data[12]
    performance_id = order_data[3]

    Configuration.account_id = int(youkassa_shop_id)
    Configuration.secret_key = youkassa_secret_key

    payment = Payment.find_one(payment_id)
    payment_status = payment.status

    try:
        # try:
        #     bot.send_message(user_id,
        #                      f'Заказ успешно оплачен.\nРяд {row} Место {place} Цена {price}\nНомер заказа {order_id}\nПросто продиктуйте номер заказа на входе чтобы пройти в зал☺️')
        # except telebot.apihelper.ApiTelegramException:
        #     pass
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
                logger.error(f"time sleep get url_kino_baza: {e}")
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
        logger.info(xml_file_name)
        try:
            bot.send_message(5254091301, f'xml_file_name\n{xml_file_name}')
        except Exception:
            pass
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


@bot.message_handler(content_types=['text', 'comands'], chat_types=['private'])
def state_machine_text(message):
    try:
        send_messages.send_cinemas(message)
        base_requests.user_reg(message.from_user.id)
    except Exception as e:
        logger.exception(f"Произошла ошибка {e}")


@bot.callback_query_handler(func=lambda callback: callback.data)
def state_machine_callback(callback):
    try:
        # берем callback.data, разбиваем по пробелу, первая часть указывает на то, именно нам с этим делать, вторая дает конкретику, что выбрал пользователь
        callback_data = callback.data.split(' ')

        # выдаем выбор даты
        if callback_data[0] == 'choose_cinema':
            # регистрируем пользователя
            with sqlite3.connect(db_path, timeout=15000) as data:
                curs = data.cursor()
                curs.execute("""UPDATE users SET city = ? WHERE user_id == ?""",
                             (callback_data[1], callback.from_user.id))
            send_messages.send_dates(callback)

        # выдаем фильмы
        elif callback_data[0] == 'choose_date':
            logger.info(callback.data)
            # пользователь выбрал дату, даем ему список фильмов
            send_messages.send_movies(callback, callback_data[1])
    except Exception as e:
        logger.exception(f"Произошла ошибка {e}")


class WebhookServer(object):
    @cherrypy.expose
    def webhook(self):
        length = int(cherrypy.request.headers['content-length'])
        json_string = cherrypy.request.body.read(length).decode("utf-8")
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''


if __name__ == '__main__':
    cherrypy.config.update({
        'server.socket_host': '127.0.0.1',
        'server.socket_port': 8080,
        'engine.autoreload.on': False,
        'log.screen': False
    })
    cherrypy.quickstart(WebhookServer(), '/', {'/': {}})
