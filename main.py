import os
import sys

from dotenv import load_dotenv

# sys.path.append('/enviroments/kino')
from config import info_log_file, bot, db_path, error_log_file, root_path, log_dir

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
