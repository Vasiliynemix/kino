from telebot import apihelper
from config import proxy_url

apihelper.proxy = {"https": proxy_url}

import datetime
import os
import re
import sys
import time

import requests
from dotenv import load_dotenv
from telebot import types
from telebot.states import State, StatesGroup
from telebot.states.sync import StateContext
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
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


# @bot.message_handler(content_types=['text', 'comands'], chat_types=['private'], commands=['start'])
# def start_text(message):
#     return
#     args = message.text.split(" ")
#     if len(args) <= 1:
#         return
#
#     if not args[1].startswith("finishpayment"):
#         return
#
#     finishpayment_data = args[1].split(",")
#     if len(finishpayment_data) <= 1:
#         return
#
#     order_id = finishpayment_data[1]
#     try:
#         order_id = int(order_id)
#     except Exception:
#         return
#
#     with psycopg2.connect(db_path) as conn:  # использование psycopg2 для PostgreSQL
#         with conn.cursor() as curs:
#             curs.execute("""SELECT payment_id FROM orders WHERE order_id = %s;""", (order_id,))
#             performance = curs.fetchone()
# # is_succeeded = base_requests.check_payment_status(performance[0])


class UserState(StatesGroup):
    waiting_for_first_name = State()
    waiting_for_last_name = State()
    waiting_for_middle_name = State()
    waiting_for_pd_agreement = State()


def normalize_name(name: str) -> str:
    name = name.strip().lower()
    parts = name.split('-')
    parts = [p.capitalize() for p in parts]
    return "-".join(parts)


def validate_name(name: str) -> bool:
    pattern = r"^[А-ЯЁ][а-яё]+(-[А-ЯЁ][а-яё]+)?$"
    return bool(re.match(pattern, name))


# First name
@bot.message_handler(state=UserState.waiting_for_first_name)
def get_first_name(message: types.Message, state: StateContext):
    name = normalize_name(message.text)
    if not validate_name(name):
        bot.send_message(message.chat.id,
                         "❌ Имя введено некорректно.\nИспользуйте только кириллицу.\nПример: Иван или Анна-Мария")
        return

    state.add_data(first_name=name)
    state.set(UserState.waiting_for_last_name)
    bot.send_message(message.chat.id, "Введите вашу Фамилию:")


# Last name
@bot.message_handler(state=UserState.waiting_for_last_name)
def get_last_name(message: types.Message, state: StateContext):
    last_name = normalize_name(message.text)
    if not validate_name(last_name):
        bot.send_message(message.chat.id,
                         "❌ Фамилия введена некорректно.\nПример: Петров или Сидоров-Иванов")
        return

    state.add_data(last_name=last_name)
    state.set(UserState.waiting_for_middle_name)
    bot.send_message(message.chat.id, "Введите Отчество (или напишите «Нет»):")


# Middle name
@bot.message_handler(state=UserState.waiting_for_middle_name)
def get_middle_name(message: types.Message, state: StateContext):
    text = message.text.strip()
    if text.lower() == "нет":
        middle_name = ""
    else:
        middle_name = normalize_name(text)
        if not validate_name(middle_name):
            bot.send_message(message.chat.id,
                             "❌ Отчество введено некорректно.\nПример: Иванович\nИли напишите «Нет»")
            return

    state.add_data(middle_name=middle_name)

    # Сбор всех данных
    with state.data() as data:
        full_name = f"{data.get('last_name')} {data.get('first_name')} {data.get('middle_name')}".strip()

    agreement_text = (
        f"Ваши данные:\n{full_name}\n\n"
        "Нажимая кнопку ниже, вы подтверждаете согласие на обработку "
        "персональных данных в целях оформления билетов."
    )

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✅ Согласен на обработку ПД", callback_data="pd_agree"))

    state.set(UserState.waiting_for_pd_agreement)
    bot.send_message(message.chat.id, agreement_text, reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data == "update_fio")
def pd_agreement_handler(call: types.CallbackQuery, state: StateContext):
    bot.send_message(
        call.from_user.id,
        "🎟 Для дальнейшего оформления билетов через этого бота необходимо указать ваши данные.\n\n"
        "Пожалуйста, вводите ФИО строго так, как указано в паспорте.\n\n"
        "Эти данные будут использоваться для формирования билетов на фильмы. "
        "Ответственность за корректность введённых данных лежит на вас."
    )
    state.delete()
    state.set(UserState.waiting_for_first_name)

    bot.send_message(call.from_user.id, "Введите ваше Имя:")
    bot.edit_message_reply_markup(
        chat_id=call.from_user.id, message_id=call.message.message_id
    )


# PD agreement callback
@bot.callback_query_handler(func=lambda call: call.data == "pd_agree", state=UserState.waiting_for_pd_agreement)
def pd_agreement_handler(call, state: StateContext):
    chat_id = call.message.chat.id
    user_id = call.from_user.id

    with state.data() as data:
        base_requests.user_fio_save(
            user_id,
            data.get('first_name', None),
            data.get('last_name', None),
            data.get('middle_name', None),
            True,
        )

    state.delete()

    bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)
    bot.send_message(chat_id, "✅ Согласие принято. Регистрация завершена.")
    send_messages.send_cinemas(call.from_user.id)


# Cancel command
@bot.message_handler(commands=["cancel"], state="*")
def cancel(message: types.Message, state: StateContext):
    state.delete()
    bot.send_message(message.chat.id, "Регистрация отменена. Введите /start чтобы начать снова.")


@bot.message_handler(content_types=['text'], chat_types=['private'])
def state_machine_text(message, state: StateContext):
    try:
        state.delete()
        user = base_requests.user_reg(message.from_user.id)

        if user.get("name") is None:
            bot.send_message(
                message.from_user.id,
                "🎟 Для дальнейшего оформления билетов через этого бота необходимо указать ваши данные.\n\n"
                "Пожалуйста, вводите ФИО строго так, как указано в паспорте.\n\n"
                "Эти данные будут использоваться для формирования билетов на фильмы. "
                "Ответственность за корректность введённых данных лежит на вас."
            )

            state.set(UserState.waiting_for_first_name)

            bot.send_message(message.chat.id, "Введите ваше Имя:")
            return

        send_messages.send_cinemas(message.from_user.id)

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
