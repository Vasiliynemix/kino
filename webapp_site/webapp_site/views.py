import asyncio
import os
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import psycopg2
import urllib3
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect

from dotenv import load_dotenv
from loguru import logger
from maxapi import Bot
from maxapi.enums import ParseMode
from maxapi.types import ButtonsPayload, LinkButton
from urllib3.exceptions import InsecureRequestWarning
from yookassa import Payment, Configuration

from pkg.log import CustomLogger
from .forms import MyForm
import time, requests, sys
import json

load_dotenv()

IS_PROD = os.getenv("IS_PROD")

if IS_PROD == "True":
    MAX_BOT_TOKEN = os.getenv('MAX_BOT_TOKEN')  # http://t.me/Mirkinopro_Bot
    url = os.getenv('URL')
    bot_url = "https://max.ru/id5402026216_bot"
    url_server = os.getenv('URL')
else:
    url = "https://l8lxne-37-78-194-77.ru.tuna.am"
    url_server = "https://verified-greatly-bonefish.ngrok-free.app"
    MAX_BOT_TOKEN = os.getenv('MAX_BOT_TOKEN_TEST')  # https://t.me/test_2_func_bot
    bot_url = "https://max.ru/id5402026216_bot"

bot = Bot(token=MAX_BOT_TOKEN)

url_kino_baza = os.getenv("URL_KINO_BAZA")
youkassa_shop_id = os.getenv("YOUKASSA_SHOP_ID")
youkassa_secret_key = os.getenv("YOUKASSA_SECRET_KEY")

validation_url = os.getenv('VALIDATION_URL')
pochta_bank_token = os.getenv('POCHTA_BANK_TOKEN')

root_path = str(Path(__file__).parent.parent.parent)
path_to_log = os.path.join(Path(__file__).parent.parent, "logs", "info.log")
db_path = os.getenv("POSTGRES_DB_URL")
sber_login = os.getenv("SBER_LOGIN")
sber_password = os.getenv("SBER_PASSWORD")

if IS_PROD == "True":
    url = os.getenv("URL")
else:
    url = "https://verified-greatly-bonefish.ngrok-free.app"

CustomLogger().add_logger(os.path.join(Path(__file__).parent.parent.parent, "logs", "info_server.log"), __name__)


def send_message_sync(chat_id: int, user_id: int, text: str, attachments=None):
    requests.post(
        "http://localhost:8080/send_message",
        json={
            "chat_id": chat_id,
            "user_id": user_id,
            "text": text,
            "attachments": attachments,
        },
        timeout=5
    )
    # threading.Thread(
    #     target=_run_async_send,
    #     args=(chat_id, user_id, text, attachments),
    #     daemon=True
    # ).start()


def _run_async_send(chat_id, user_id, text, attachments):
    asyncio.run(
        send_message_async(chat_id, user_id, text, attachments)
    )


async def send_message_async(chat_id: int, user_id: int, text: str, attachments=None):
    await bot.send_message(
        chat_id=chat_id,
        user_id=user_id,
        text=text,
        parse_mode=ParseMode.HTML,
        attachments=attachments,
    )


def _inline_url(rows: list[list[tuple[str, str]]]):
    return ButtonsPayload(
        buttons=[
            [
                LinkButton(
                    text=text,
                    url=url,
                )
                for text, url in row
            ]
            for row in rows
        ]
    ).pack()


def process_payment(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        order_id = data['order_id']
        iframe_url = data['iframe_url']
        query_id = data['query_id']  # Получаем query_id

        try:
            # Выполняем логику платежа и заказа
            with psycopg2.connect(db_path) as data:
                with data.cursor() as curs:
                    curs.execute(
                        """SELECT payment_id, payment_link, user_id, price, row, place, performance_id FROM orders WHERE order_id = %s""",
                        (order_id,))
                    order = curs.fetchone()
                    if order is None:
                        return JsonResponse({"status": "error", "message": "Order not found"}, status=404)

                    curs.execute(
                        """SELECT name, surname, patronymic, agreement, max_chat_id FROM users WHERE user_id = %s;""",
                        (order[2],))
                    user = curs.fetchone()
                    if user is None:
                        return JsonResponse({"status": "error", "message": "User not found"}, status=404)

                    chat_id = user[4]

                    if user[0] is None or user[1] is None:
                        send_message_sync(
                            chat_id,
                            order[2],
                            "Извините, для начала Вам нужно заполнить ФИО, для этого введите /start",
                        )
                        return JsonResponse({"status": "success"})

                    fio = f"{user[1]} {user[0]} {user[2]}"
                    fio = fio.strip()

                    curs.execute(
                        """SELECT hallname, date, time, show_id, building_id FROM performance WHERE performance_id = %s""",
                        (order[6],))
                    performance = curs.fetchone()
                    if performance is None:
                        return JsonResponse({"status": "error", "message": "Performance not found"}, status=404)

                    curs.execute(
                        """SELECT name FROM show WHERE show_id = %s""",
                        (performance[3],))
                    show = curs.fetchone()
                    if show is None:
                        return JsonResponse({"status": "error", "message": "Show not found"}, status=404)

                    curs.execute(
                        """SELECT city FROM cinemas WHERE building_id = %s""",
                        (performance[4],))
                    cinema = curs.fetchone()
                    if cinema is None:
                        return JsonResponse({"status": "error", "message": "Cinema not found"}, status=404)

                    payment_link = order[1]
                    user_id = order[2]
                    price = order[3]
                    row = order[4]
                    place = order[5]

                    hallname = performance[0]
                    date = performance[1]
                    time = performance[2]
                    name = show[0]
                    city = cinema[0]

                    # Преобразуем дату из строки в объект datetime
                    date_obj = datetime.strptime(date, "%Y-%m-%d")

                    # Словарь с русскими названиями месяцев
                    months = {
                        1: "января", 2: "февраля", 3: "марта", 4: "апреля",
                        5: "мая", 6: "июня", 7: "июля", 8: "августа",
                        9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
                    }

                    # Формируем красивую дату
                    date_ru = f"{date_obj.day} {months[date_obj.month]} {date_obj.year}"

                    # Пример: объединяем с временем
                    date_time_ru = f"{date_ru} {time}"

                    msg_text = (
                        f"<b>Заказ №:</b> {order_id}\n\n"
                        f"<b>Сеанс:</b> {name}\n"
                        f"<b>Кинотеатр:</b> {hallname} ({city})\n"
                        f"<b>Дата и время сеанса:</b> {date_time_ru}\n"
                        f"<b>Ряд / Место:</b> {row} / {place}\n"
                        f"<b>Цена:</b> {price} р.\n\n"
                        f"Для оплаты нажмите кнопку ниже ⬇️"
                    )

                    attachments = [_inline_url([[("Оплатить по пушкинской карте", payment_link)]])]

                    send_message_sync(
                        chat_id,
                        user_id,
                        msg_text,
                        attachments=attachments,
                    )
                    # msg = bot.send_message(
                    #     user_id,
                    #     f"<b>Заказ №{order_id}.\nЦена: {price} р.\nРяд: {row}\nМесто: {place}</b>",
                    #     reply_markup=telebot.types.InlineKeyboardMarkup(
                    #         [[telebot.types.InlineKeyboardButton("Оплатить по Пушкинской карте", url=payment_link)]]),
                    #     parse_mode='HTML',
                    # )
                    # curs.execute(
                    #     """UPDATE orders SET payment_msg_id = %s WHERE order_id = %s""",
                    #     (msg., order_id,))

            return JsonResponse({"status": "success"})

        except Exception as e:
            logger.exception("process_payment")
            return JsonResponse({"status": "error", "message": str(e)}, status=500)


def finishpayment(request, order_id):
    try:
        with psycopg2.connect(db_path) as data:
            with data.cursor() as curs:
                curs.execute("""SELECT payment_id FROM orders WHERE order_id = %s;""", (order_id,))
                payment_id = curs.fetchone()[0]

        # Здесь идет проверка статуса платежа
        sys.path.append(root_path)
        from base_requests import check_payment_status
        # check_payment_status(payment_id)

        # Вместо рендеринга HTML, возвращаем JavaScript, который взаимодействует с Telegram WebApp
        return HttpResponse("""
            <script type="text/javascript">
                let tg = window.Telegram.WebApp;
                tg.MainButton.setParams({
                    text: "Оплата завершена",
                    color: "#4CAF50",
                    is_active: true
                });
                tg.MainButton.show();
                tg.MainButton.onClick(function(){
                    tg.close();
                });
            </script>
            """, content_type="text/html")

    except Exception:
        logger.exception("-")
        return HttpResponse("""
            <script type="text/javascript">
                let tg = window.Telegram.WebApp;
                alert("Произошла ошибка при проверке платежа. Попробуйте позже.");
                tg.close();
            </script>
            """, content_type="text/html")


def kino(request, performance_id, user_id):
    try:
        with psycopg2.connect(db_path) as data:
            with data.cursor() as curs:
                curs.execute("""SELECT name, surname, patronymic FROM users WHERE user_id = %s;""", (user_id,))
                user = curs.fetchone()
                fio = f"{user[1]} {user[0]} {user[2]}"
                fio = fio.strip()

        if request.method == 'POST':  # при нажатии на кнопку
            form = MyForm(request.POST)
            if form.is_valid():
                # logger.info(request.POST)

                state, price, place_place, place_row, place_id, order_id = request.POST['chair_but'].split(',')

                if state == 'back':  # если нажал назад, разблокируем все его места
                    unblock_performance(user_id, performance_id)
                    seatMap = create_list_of_buttons(performance_id)
                    form = MyForm()
                    return render(request, 'index.html',
                                  {'form': form, 'seatMap': seatMap, 'fio': fio, 'down_text': 'Выберите 1 место',
                                   'is_new_data': True})
                elif state == 'pay':  # если нажал оплатить
                    ret = payment_button_pressed(request, user_id, performance_id, place_id, price, order_id)
                    return ret
                elif state == 'choose_place':  # если выбрал место
                    ret = cheir_choosed(request, user_id, performance_id, place_id, price, order_id, form)
                    return ret
        else:  # при первом обращении
            # Если уже куплен есть бронь на сеанс, то сразу кнопка оплатить
            if check_user_performance(user_id, performance_id):
                ret = cheir_choosed_from_main(request, user_id, performance_id)
                return ret

            # ret = payment_button_pressed(request, user_id, performance_id, place_id, price, order_id)
            seatMap = create_list_of_buttons(performance_id)
            form = MyForm()
            return render(request, 'index.html',
                          {'form': form, 'seatMap': seatMap, 'fio': fio, 'down_text': 'Выберите 1 место',
                           'is_new_data': True})
    except Exception:
        logger.exception("-")


def payment_button_pressed(request, user_id, performance_id, place_id, price, order_id):
    with psycopg2.connect(db_path) as data:
        with data.cursor() as curs:
            try:
                curs.execute("""SELECT buyer_id FROM users WHERE user_id = %s;""", (user_id,))
                buyer_id = curs.fetchone()[0]
            except TypeError:
                buyer_id = 998277

            try:
                curs.execute(
                    """SELECT status, payment_link, payment_msg_id FROM orders WHERE user_id = %s AND performance_id = %s""",
                    (user_id, performance_id))
                check_status = curs.fetchone()
                if check_status[0] == 3:
                    # try:
                    #     bot.delete_message(
                    #         chat_id=user_id,
                    #         message_id=check_status[2]
                    #     )
                    # except Exception:
                    #     pass
                    return render(request, 'payment.html',
                                  {'iframe_url': check_status[1], 'close_webapp': True, 'order_id': order_id})
                if check_status[0] == 0:
                    # try:
                    #     bot.delete_message(
                    #         chat_id=user_id,
                    #         message_id=check_status[2]
                    #     )
                    # except Exception:
                    #     pass
                    unblock_performance(user_id, performance_id)
                    return render(request, 'finish.html')
            except Exception as e:
                unblock_performance(user_id, performance_id)
                return render(request, 'finish.html')

            curs.execute(
                """SELECT row, place, price, order_id FROM orders WHERE order_id = %s AND  user_id = %s AND status = 1;""",
                (order_id, user_id))
            did_he_almoust_bye = curs.fetchone()

    if did_he_almoust_bye != None:  # если уже успешно купил билет на сеанс
        with psycopg2.connect(db_path) as conn:
            with conn.cursor() as curs:
                curs.execute(
                    "SELECT name, surname, patronymic, max_chat_id FROM users WHERE user_id = %s;",
                    (user_id,)
                )
                user = curs.fetchone()

        chat_id = user[3]
        send_message_sync(chat_id, user_id,
                                f'На сеанс можно купить только 1 билет по Пушкинской карте\n'
                                f'Ваш билет\nРяд {did_he_almoust_bye[0]} Место {did_he_almoust_bye[1]} Цена {did_he_almoust_bye[2]}\nНомер заказа {did_he_almoust_bye[3]}')
        return render(request, 'finish.html')

    Configuration.account_id = int(youkassa_shop_id)
    Configuration.secret_key = youkassa_secret_key

    # делаем оплату юкасса
    payment = Payment.create({
        "amount": {
            "value": str(float(price)),
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect",
            "return_url": f"{bot_url}?start=finishpayment,{order_id}"
        },
        "capture": True,
        "description": f"Заказ №{order_id}",
    }, uuid.uuid4())

    payment_link = payment.confirmation.confirmation_url
    payment_id = payment.id

    # пишем в заявку все данные
    with psycopg2.connect(db_path) as dataf:
        with dataf.cursor() as curs:
            curs.execute(
                """UPDATE orders SET status = 3, payment_id = %s, payment_link = %s WHERE order_id = %s AND user_id = %s AND performance_id = %s""",
                (payment_id, payment_link, order_id, user_id, performance_id))

    return render(request, 'payment.html',
                  {'iframe_url': payment_link, 'close_webapp': True, 'order_id': order_id, 'user_id': user_id})


def cheir_choosed(request, user_id, performance_id, place_id, price, place_locked_time, form):
    state, price, place_place, place_row, place_id, place_locked_time = request.POST['chair_but'].split(',')
    with psycopg2.connect(db_path) as data:
        with data.cursor() as curs:
            # вытаскиваем id зала, потому что у некоторых залов специфические настройки
            try:
                curs.execute("""SELECT buyer_id, name, surname, patronymic FROM users WHERE user_id = %s;""",
                             (user_id,))
                user = curs.fetchone()
                buyer_id = user[0]
            except TypeError:
                buyer_id = 2024

            fio = f"{user[2]} {user[1]} {user[3]}"
            fio = fio.strip()

            curs.execute("""SELECT * FROM orders WHERE user_id = %s AND performance_id = %s AND status != 0""",
                         (user_id, performance_id))
            check_order = curs.fetchone()

    if check_order is not None:
        return render(request, 'finish.html')

    # print(price, place_place, place_row, place_id, buyer_id)
    params = {
        "sp": "WgA_LockPlace",
        "IdPerformance": performance_id,
        "IdPlace": int(place_id),
        "IdClient": int(buyer_id),
        "IdPriceCategory": 17198,
        "df": "J"
    }
    logger.info(f"{params=}")

    try:
        response = requests.request("GET", 'http://195.208.148.248:18088/TicketAutomat/get.php', params=params,
                                    timeout=5)
    except Exception as e:
        logger.exception("WgA_LockPlace")
        unblock_performance(user_id, performance_id)
        return render(request, 'finish.html')

    locked_place = response.json()
    logger.info(f"{locked_place=}")
    # записываем в базу как заказ со статусом 1
    try:
        if locked_place['Price']:  # если место свободно
            place_locked_time = int(time.time())
            uuid_order = str(uuid.uuid4())
            price = locked_place['Price']

            # регистрируем заказ
            params = {
                "sp": "WgA_CreateMultyOrder",
                "IdClient": int(buyer_id),
                "df": "J"}

            try:
                response = requests.request("GET", 'http://195.208.148.248:18088/TicketAutomat/get.php', params=params,
                                            timeout=5)
            except Exception as e:
                logger.exception("WgA_CreateMultyOrder")
                unblock_performance(user_id, performance_id)
                return render(request, 'finish.html')

            order_data = response.json()

            if isinstance(order_data, dict):
                if order_data.get('Error') is not None:
                    with psycopg2.connect(db_path) as conn:
                        with conn.cursor() as curs:
                            curs.execute(
                                "SELECT name, surname, patronymic, max_chat_id FROM users WHERE user_id = %s;",
                                (user_id,)
                            )
                            user = curs.fetchone()

                    chat_id = user[3]
                    send_message_sync(chat_id, user_id,
                                            f'''Какая-то ошибка, попробуйте позже.\n{order_data.get('Error')}''')
                    unblock_performance(user_id, performance_id)
                    return render(request, 'finish.html')

            try:
                order_id = order_data['IdOrder']
            except TypeError:
                unblock_performance(user_id, performance_id)
                return render(request, 'finish.html')

            total_tickets = 1
            try:
                total_tickets = order_data['TotalTickets']
                total_tickets = int(total_tickets)
            except (TypeError, ValueError):
                pass

            if total_tickets != 1:
                unblock_performance(user_id, performance_id)
                seatMap = create_list_of_buttons(performance_id)
                return render(request, 'index.html',
                              {'form': form, 'seatMap': seatMap, 'fio': fio, 'down_text': 'Простите, '})

            try:
                with psycopg2.connect(db_path) as data:
                    with data.cursor() as curs:
                        curs.execute(
                            """INSERT INTO orders 
                            (user_id, buyer_id, performance_id, place_id,
                             place_locked_time, status, place, row, uuid_order, price, order_id)
                             VALUES (%s, %s, %s, %s, %s, 2, %s, %s, %s, %s, %s);""",
                            (user_id, buyer_id, performance_id, place_id,
                             place_locked_time, place_place, place_row, uuid_order, price, order_id)
                        )
            except psycopg2.IntegrityError as e:
                if e.pgcode == '23505':  # Код ошибки UNIQUE VIOLATION
                    unblock_performance(user_id, performance_id)
                    with psycopg2.connect(db_path) as data:
                        with data.cursor() as curs:
                            curs.execute("""DELETE FROM orders WHERE user_id = %s AND performance_id = %s""",
                                         (user_id, performance_id))
                            curs.execute(
                                """INSERT INTO orders 
                                (user_id, buyer_id, performance_id, place_id,
                                 place_locked_time, status, place, row, uuid_order, price, order_id)
                                 VALUES (%s, %s, %s, %s, %s, 2, %s, %s, %s, %s, %s);""",
                                (user_id, buyer_id, performance_id, place_id,
                                 place_locked_time, place_place, place_row, uuid_order, price, order_id)
                            )
                else:
                    logger.exception(f"psycopg2.IntegrityError INSERT INTO orders: {e}")
                    unblock_performance(user_id, performance_id)
                    return render(request, 'finish.html')
            except Exception as e:
                logger.exception("INSERT INTO orders")
                unblock_performance(user_id, performance_id)
                return render(request, 'finish.html')

            seatMap = create_list_of_buttons(performance_id)
            return render(request, 'when_place_choosed.html',
                          {'form': form, 'fio': fio,
                           'back_value': f'back,{price},{place_place},{place_row},{place_id},{order_id}',
                           'button_value': f'pay,{price},{place_place},{place_row},{place_id},{order_id}',
                           'text': f'Ряд {place_row}\nМесто {place_place}\n\nЦена {price}'})
    except KeyError as ex:  # если место заблокировано уже
        logger.info(f"KeyError: lock {ex}")
        unblock_performance(user_id, performance_id)
        seatMap = create_list_of_buttons(performance_id)
        return render(request, 'index.html',
                      {'form': form, 'seatMap': seatMap, 'fio': fio, 'down_text': 'Простите, это место уже занято'})
    except Exception as e:
        logger.exception("cheir_choosed")
        unblock_performance(user_id, performance_id)
        return render(request, 'finish.html')


def decode_unicode(data):
    if isinstance(data, str):
        return data.encode('utf-8').decode('unicode_escape')
    elif isinstance(data, dict):
        return {k: decode_unicode(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [decode_unicode(v) for v in data]
    return data


def create_list_of_buttons(performance_id):
    # общий принцип работы: берем из базы кинотеатра по сеансу который запрошен в ссылке по которой перешли все места. Нам нужно расставить их так как они находятся в зале.
    # для этого есть пустые кнопки которые обозначаются как empt и есть занятые места occ. При этом мы формируем список из списков, каждый список это ряд, эллементы в нем это места.
    t1 = time.time()
    # запрашиваем список всех мест на сеансе
    params = {
        "sp": "Wga_GetPlacesNC",
        'IdPerformance': performance_id,
        "df": "J"
    }
    response = requests.request("GET", 'http://195.208.148.248:18088/TicketAutomat/get.php', params=params)
    # logger.info(decode_unicode(response.text))
    # logger.info(response.url)

    if response.status_code == 200:
        # print(response.text)
        data_show = response.json()
        # print(data_show, '\n\n')
        with psycopg2.connect(db_path) as data:
            with data.cursor() as curs:
                # вытаскиваем id зала, потому что у некоторых залов специфические настройки
                curs.execute("""SELECT hall_id FROM performance WHERE performance_id = %s;""",
                             (performance_id,))
                hall_id = curs.fetchone()[0]
        # в цикле мы разбиваем данные так что отдельные ряды это отдельные списки, внутри них есть занятые места и свободные.
        seatMap = []
        row = []
        i = data_show[0]['PlaceRow']
        t2 = time.time()
        pos_x = 0
        place_last = data_show[0]
        try:
            # привожу в правильный порядок, потому что база выдает когда правильно когда как попало
            data_show = sorted(data_show, key=lambda x: (int(x['PlaceRow']), int(x['PlacePlace'])))
        except ValueError:
            pass
        # если определенныйе залы, то из-за малого размера нужно чтобы все было в центре и нужны соответствующие отступы по краям
        if int(hall_id) == 17:  # зал Орион малый
            pos_x_max = 800
            pos_x_min = -200
        elif int(hall_id) == 17:  # зал Орион 3
            pos_x_max = 600
            pos_x_min = 0
        else:  # все остальные
            pos_x_max = 0
            pos_x_min = 1500
            for place in data_show:  # определяем pos_x_max и pos_x_min
                pos_x = int(place['PosX'])
                if pos_x > pos_x_max:
                    pos_x_max = pos_x
                if pos_x < pos_x_min:
                    pos_x_min = pos_x
        # если они дают зал справа налево, то сценарий 1, если слева направо, то сценарий 2
        if int(data_show[0]['PosX']) > int(data_show[2]['PosX']):
            right_to_left = True
        else:
            right_to_left = False
        # print(right_to_left)

        if right_to_left == True:
            for place in data_show:
                # Если новое место дальше старого больше чем на 50 единиц, то вставляем 1 пустое место за каждые 50 единиц
                # промежуток между местами
                difx = pos_x - int(place['PosX'])
                while difx > 50:
                    difx -= 50
                    row.append('empt')
                    # print('betw', difx)

                # print(place)
                if place['PlaceRow'] != i:  # если новый ряд, то добавляем к основному списку и обнуляем список
                    difxmin = int(place_last['PosX']) - pos_x_min
                    while difxmin >= 50:
                        difxmin -= 50
                        row.append('empt')
                        # print('min')
                    seatMap.append(reversed(row))
                    row = []

                # то же самое про 50 единиц и плюс в самом начале
                if place['PlaceRow'] != i or (int(place['PlaceRow']) == 1 and int(place['PlacePlace']) == 1):
                    # print(place_last['PosX'], place['PosX'], pos_x_max, pos_x_min)
                    difxmax = pos_x_max - int(place['PosX'])
                    while difxmax >= 50:
                        difxmax -= 50
                        row.append('empt')
                        # print('max')
                    i = place['PlaceRow']

                if place['State'] == '0':
                    row.append(
                        f'choose_place,{place["Price"]},{place["PlacePlace"]},{place["PlaceRow"]},{place["IdPlace"]},null')
                else:
                    row.append(f'occ')

                # print(place['PosX'], place['PosY'], place["PlaceRow"], place["PlacePlace"])
                place_last = place
                pos_x = int(place['PosX'])
            # проверяем последние отступы
            difxmin = int(place_last['PosX']) - pos_x_min
            while difxmin >= 50:
                difxmin -= 50
                row.append('empt')
                # print('min')
            seatMap.append(reversed(row))  # добавляем последний ряд

        elif right_to_left == False:
            for place in data_show:
                # Если новое место дальше старого больше чем на 50 единиц, то вставляем 1 пустое место за каждые 50 единиц
                # промежуток между местами

                difx = int(place['PosX']) - pos_x
                try:  # lkz зала где нет нафиг вообще мест
                    if int(place['PlaceRow']) == 1 and int(place['PlacePlace']) == 1:
                        pass
                    else:
                        while difx > 53:  # сделал 53 потому что так работает зал  Звёздный, нахрен блин
                            difx -= 50
                            row.append('empt')
                            # print('betw', difx)
                except ValueError:
                    pass

                # print(place['PosX'])
                if place['PlaceRow'] != i:  # если новый ряд, то добавляем к основному списку и обнуляем список
                    difxmax = pos_x_max - int(place_last['PosX'])
                    while difxmax >= 50:
                        difxmax -= 50
                        row.append('empt')
                        # print('max', difxmax)
                    seatMap.append(row)
                    row = []

                # то же самое про 50 единиц и плюс в самом начале
                if place['PlaceRow'] != i or (place['PlaceRow'] in ('1', '01') and place['PlacePlace'] in ('1', '01')):
                    # print(place_last['PosX'], place['PosX'], pos_x_max, pos_x_min)
                    difxmin = int(place['PosX']) - pos_x_min
                    while difxmin >= 50:
                        difxmin -= 50
                        row.append('empt')
                    # print('min')
                    i = place['PlaceRow']

                if place['State'] == '0':
                    row.append(
                        f'choose_place,{place["Price"]},{place["PlacePlace"]},{place["PlaceRow"]},{place["IdPlace"]},null')
                else:
                    row.append(f'occ')
                pos_x = int(place['PosX'])

                # print(place['PosX'], place['PosY'], place["PlaceRow"], place["PlacePlace"])
                place_last = place
            difxmax = pos_x_max - int(place_last['PosX'])
            while difxmax >= 50:
                difxmax -= 50
                row.append('empt')
                # print('max', difxmax)
            seatMap.append(row)  # добавляем последний ряд

        t3 = time.time()
        return seatMap
        # print(t3-t2, t2-t1, seatMap)
        # for a in seatMap:
        #     for b in a:
        #         print(b)


def unblock_all(user_id, performance_id, place_id, delete_connection=True):
    with psycopg2.connect(db_path) as data:
        with data.cursor() as curs:
            if place_id == 'all':
                # берем все брони у пользователя на этот сеанс
                curs.execute(
                    """SELECT performance_id, place_id, buyer_id, order_id FROM orders WHERE user_id = %s AND performance_id = %s AND status != 0;""",
                    (user_id, performance_id))
                orders_to_close = curs.fetchall()
            else:
                # берем все брони кроме place_id который нам передали
                curs.execute(
                    """SELECT performance_id, place_id, buyer_id, order_id FROM orders WHERE user_id = %s AND performance_id = %s AND place_id != %s AND status != 0;""",
                    (user_id, performance_id, place_id))
                orders_to_close = curs.fetchall()

    # print('11111111', orders_to_close)
    # проходимся по всем таким броням
    logger.info(orders_to_close)
    for order in orders_to_close:
        logger.info(order)
        params = {
            "sp": "WgA_SetOrderToNull",
            "idOrder": order[3],
            "df": "J",
        }
        for i in range(5):
            try:
                response = requests.request("GET", url_kino_baza, params=params)
                logger.info(decode_unicode(response.text))
                break
            except Exception as e:
                # bot.send_message(5254091301,
                #                  f'!!!!Ошибка. Заказ unblock_all, но отменить не вышло {e}')
                logger.exception("Произошла ошибка RRWgA_SetOrderToNull")
                time.sleep(7)

        with psycopg2.connect(db_path) as data:
            with data.cursor() as curs:
                try:
                    curs.execute(
                        """UPDATE orders SET status = 0 WHERE performance_id = %s AND place_id = %s AND buyer_id = %s AND user_id = %s""",
                        (order[0], order[1], order[2], user_id))
                except Exception as e:
                    # bot.send_message(5254091301,
                    #                  f'!!!!Ошибка UPDATE orders SET status. Заказ unblock_all, но отменить не вышло {e}: {order=}')
                    logger.exception("unblock_all")


def unblock_performance(user_id, performance_id):
    with psycopg2.connect(db_path) as data:
        with data.cursor() as curs:
            curs.execute(
                """SELECT performance_id, place_id, buyer_id, order_id, payment_msg_id, user_id FROM orders WHERE user_id = %s AND performance_id = %s AND status != 3 AND status != 1;""",
                (user_id, performance_id))
            order = curs.fetchone()

    logger.info(order)
    if order is not None:
        params = {
            "sp": "WgA_SetOrderToNull",
            "idOrder": order[3],
            "df": "J",
        }
        for i in range(5):
            try:
                response = requests.request("GET", url_kino_baza, params=params, timeout=5)
                logger.info(decode_unicode(response.text))
                break
            except Exception as e:
                # bot.send_message(5254091301,
                #                  f'!!!!Ошибка. Заказ unblock_performance, но отменить не вышло {e}')
                logger.exception("Произошла ошибка RRWgA_SetOrderToNull")
                time.sleep(7)

    try:
        bot.delete_message(
            chat_id=order[5],
            message_id=order[4],
        )
    except Exception:
        pass

    with psycopg2.connect(db_path) as data:
        with data.cursor() as curs:
            try:
                curs.execute(
                    """UPDATE orders SET status = 0, payment_link = NULL, payment_id = NULL, payment_msg_id = NULL WHERE performance_id = %s AND user_id = %s""",
                    (performance_id, user_id))
            except Exception as e:
                # bot.send_message(5254091301,
                #                  f'!!!!Ошибка UPDATE orders SET status. Заказ unblock_performance, но отменить не вышло {e}: {order=}')
                logger.exception("unblock_performance")


def check_user_performance(tg_id, performance_id):
    with psycopg2.connect(db_path) as conn:
        with conn.cursor() as curs:
            curs.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM orders 
                        WHERE user_id = %s AND performance_id = %s AND status != 0
                    );
                """, (tg_id, performance_id))
            return curs.fetchone()[0]  # Получаем булево значение


def cheir_choosed_from_main(request, user_id, performance_id):
    with psycopg2.connect(db_path) as data:
        with data.cursor() as curs:
            curs.execute(
                """SELECT place_id, place, row, order_id, price, status, payment_msg_id, payment_link FROM orders where user_id = %s AND performance_id = %s;""",
                (user_id, performance_id))
            order = curs.fetchone()
            curs.execute("""SELECT name, surname, patronymic, max_chat_id FROM users WHERE user_id = %s;""", (user_id,))
            user = curs.fetchone()
            fio = f"{user[1]} {user[0]} {user[2]}"
            fio = fio.strip()

    place_id = order[0]
    price = order[4]
    place_place = order[1]
    place_row = order[2]
    order_id = order[3]
    status = order[5]
    chat_id = user[3]
    payment_link = order[7]

    form = MyForm()

    if status == 2:
        comment = "\nВы уже выбрали место на этот сеанс, оплатите его\nлибо нажмите назад, чтобы выбрать другое место"
        return render(request, 'when_place_choosed.html',
                      {'form': form, 'fio': fio,
                       'back_value': f'back,{price},{place_place},{place_row},{place_id},{order_id}',
                       'button_value': f'pay,{price},{place_place},{place_row},{place_id},{order_id}',
                       'text': f'Ряд {place_row}\nМесто {place_place}\n\nЦена {price}',
                       'comment': comment})

    elif status == 3:
        comment = "\nВы уже выбрали место на этот сеанс, оплатите его\nлибо нажмите назад, чтобы выбрать другое место"
        if payment_link is not None:
            return render(request, 'when_place_choosed_with_url.html',
                          {'form': form, 'fio': fio, 'payment_link': payment_link,
                           'text': f'Ряд {place_row}\nМесто {place_place}\n\nЦена {price}',
                           'comment': comment})
        else:
            return render(request, 'finish.html')
    elif status == 4:
        return render(request, 'finish.html')

    elif status == 1:
        send_message_sync(chat_id, user_id,
                                f'На сеанс можно купить только 1 билет по Пушкинской карте\n'
                                f'Ваш билет\nРяд {place_row} Место {place_place} Цена {price}\nНомер заказа {order_id}')
        return render(request, 'finish.html')

    elif status == 0:
        unblock_performance(user_id, performance_id)
        return render(request, 'finish.html')

    else:
        return render(request, 'finish.html')
