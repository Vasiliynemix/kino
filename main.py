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
import psycopg2  # заменено sqlite3 на psycopg2
from loguru import logger
import base_requests
import threading
import telebot
import send_messages

CustomLogger().add_logger(info_log_file, __name__)

threading.Thread(target=base_requests.film_update_main).start()


def send_xml_to_me(
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
    except Exception as e:
        logger.exception(f"Произошла ошибка {e}")
        bot.send_message(5254091301, f"Произошла ошибка {e}")


def set_data(order_id, kino_add_payment_id):
    with psycopg2.connect(db_path) as data:
        with data.cursor() as curs:
            curs.execute("""SELECT * FROM orders WHERE order_id = %s""", (order_id,))
            order_data = curs.fetchone()

    order_id = order_data[0]
    place_id = order_data[4]
    price = order_data[5]
    user_id = order_data[1]
    row = order_data[11]
    place = order_data[12]
    performance_id = order_data[3]

    is_succeeded = True
    is_fk_report_send = True
    try:
        kino_add_payment_id = kino_add_payment_id
        with psycopg2.connect(db_path) as data:
            with data.cursor() as curs:
                curs.execute("""SELECT * FROM performance WHERE performance_id = %s""",
                                                (performance_id,))
                performance_data = curs.fetchone()

                curs.execute("""SELECT fond_kino_id FROM cinemas WHERE building_id = %s""",
                                            (performance_data[2],))
                fond_kino_id = curs.fetchone()[0]

                curs.execute("""SELECT pu_number, name, id_procult FROM show WHERE show_id = %s""",
                                         (performance_data[1],))
                show_data = curs.fetchone()
    except TypeError:
        bot.send_message(5254091301,
                         f'!!!!Ошибка. Заказ оплачен, но оформить его правильно не вышло\n Я его пропускаю, вот данные клиента и заказа, свяжитесь с ним:order_id {order_data[0]}\nuser_id_tg {order_data[1]}\nperformance {order_data[3]}\nplace_id {order_data[4]}\nряд {order_data[11]}\nместо {order_data[12]}\npayment_id {order_data[6]}')
    except Exception as e:
        logger.exception("Произошла ошибка")
        bot.send_message(5254091301, text=f"Произошла ошибка {e}")

    Configuration.account_id = int(youkassa_shop_id)
    Configuration.secret_key = youkassa_secret_key

    with psycopg2.connect(db_path) as data:
        with data.cursor() as curs:
            curs.execute("""SELECT payment_id FROM orders WHERE order_id = %s""", (order_id,))
            payment_id = curs.fetchone()[0]

    payment = Payment.find_one(payment_id)

    send_xml_to_me(
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


@bot.message_handler(content_types=['text', 'comands'], chat_types=['private'], commands=['db'])
def logs_text(message):
    if message.from_user.id != 5254091301:
        return

    try:
        bot.send_document(message.from_user.id, open(db_path, 'rb'))
    except Exception as e:
        logger.exception(f"Произошла ошибка {e}")


@bot.message_handler(content_types=['text', 'comands'], chat_types=['private'], commands=['xml'])
def xml_text(message):
    print("xml_text клик")
    if message.from_user.id != 5254091301:
        return

    try:
        order_id = int(message.text.split(" ")[1])
        kino_add_payment_id = int(message.text.split(" ")[2])
        set_data(order_id, kino_add_payment_id)
    except Exception as e:
        logger.exception(f"Произошла ошибка {e}")



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

    with psycopg2.connect(db_path) as conn:  # использование psycopg2 для PostgreSQL
        with conn.cursor() as curs:
            curs.execute("""SELECT payment_id FROM orders WHERE order_id = %s;""", (order_id,))
            performance = curs.fetchone()
    # is_succeeded = base_requests.check_payment_status(performance[0])


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
            with psycopg2.connect(db_path) as conn:  # использование psycopg2 для PostgreSQL
                with conn.cursor() as curs:
                    curs.execute("""UPDATE users SET city = %s WHERE user_id = %s""",
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
