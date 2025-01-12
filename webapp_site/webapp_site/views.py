import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import psycopg2
import urllib3
import telebot
from telebot import TeleBot
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect

from dotenv import load_dotenv
from loguru import logger
from urllib3.exceptions import InsecureRequestWarning
from yookassa import Payment, Configuration

from pkg.log import CustomLogger
from .forms import MyForm
import time, requests, sys
import json
load_dotenv()

IS_PROD = os.getenv("IS_PROD")

if IS_PROD == "True":
    BOT_TOKEN = os.getenv('BOT_TOKEN')  # http://t.me/Mirkinopro_Bot
    url = os.getenv('URL')
    bot_url = "https://t.me/Mirkinopro_Bot"
    url_server = os.getenv('URL')
else:
    url = "https://l8lxne-37-78-194-77.ru.tuna.am"
    url_server = "https://verified-greatly-bonefish.ngrok-free.app"
    BOT_TOKEN = os.getenv('BOT_TOKEN_TEST')  # https://t.me/test_2_func_bot
    bot_url = "https://t.me/test_2_func_bot"

bot = TeleBot(BOT_TOKEN)

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
                    curs.execute("""SELECT payment_id, payment_link, user_id, price, row, place FROM orders WHERE order_id = %s""", (order_id,))
                    order = curs.fetchone()
                    if order is None:
                        return JsonResponse({"status": "error", "message": "Order not found"}, status=404)
                    payment_link = order[1]
                    user_id = order[2]
                    price = order[3]
                    row = order[4]
                    place = order[5]

                    bot.send_message(
                        user_id,
                        f"<b>Заказ №{order_id}.\nЦена: {price} р.\nРяд: {row}\nМесто: {place}</b>",
                        reply_markup=telebot.types.InlineKeyboardMarkup([[telebot.types.InlineKeyboardButton("Оплатить по Пушкинской карте", url=payment_link)]]),
                        parse_mode='HTML',
                    )

            return JsonResponse({"status": "success"})

        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=500)


# обработать все потенциальные ошибки

# обратить внимание при норм тестах
# формат цены, чтоб не вышло что мне прислали с копейками и из-за этого я плохую сумму пользователю послал, я же в копейках шлю
def finishpayment(request, order_id):
    try:
        with psycopg2.connect(db_path) as data:
            with data.cursor() as curs:
                curs.execute("""SELECT payment_id FROM orders WHERE order_id = %s;""", (order_id,))
                payment_id = curs.fetchone()[0]

        # Здесь идет проверка статуса платежа
        sys.path.append(root_path)
        from base_requests import check_payment_status
        check_payment_status(payment_id)

        # Вместо рендеринга HTML, возвращаем JavaScript, который взаимодействует с Telegram WebApp
        return HttpResponse("""
            <script src="https://telegram.org/js/telegram-web-app.js"></script>
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
            <script src="https://telegram.org/js/telegram-web-app.js"></script>
            <script type="text/javascript">
                let tg = window.Telegram.WebApp;
                alert("Произошла ошибка при проверке платежа. Попробуйте позже.");
                tg.close();
            </script>
            """, content_type="text/html")


def kino(request, performance_id):
    try:
        # print(request)
        if request.method == 'POST':  # при нажатии на кнопку
            form = MyForm(request.POST)
            if form.is_valid():
                # logger.info(request.POST)
                user_id = request.POST['user_id']

                state, price, place_place, place_row, place_id, order_id = request.POST['chair_but'].split(',')

                if state == 'back':  # если нажал назад, разблокируем все его места
                    unblock_all(user_id, performance_id, 'all')
                    seatMap = create_list_of_buttons(performance_id)
                    form = MyForm()
                    return render(request, 'index.html',
                                  {'form': form, 'seatMap': seatMap, 'down_text': 'Веберите 1 место', 'is_new_data': True})
                elif state == 'pay':  # если нажал оплатить
                    ret = payment_button_pressed(request, user_id, performance_id, place_id, price, order_id)
                    unblock_all(user_id, performance_id, 'all')
                    return ret
                elif state == 'choose_place':  # если выбрал место
                    ret = cheir_choosed(request, user_id, performance_id, place_id, price, order_id, form)
                    return ret
        else:  # при первом обращении
            seatMap = create_list_of_buttons(performance_id)
            form = MyForm()
            return render(request, 'index.html',
                          {'form': form, 'seatMap': seatMap, 'down_text': 'Веберите 1 место', 'is_new_data': True})
    except Exception:
        logger.exception("-")


def unblock_all(user_id, performance_id, place_id):
    with psycopg2.connect(db_path) as data:
        with data.cursor() as curs:
            if place_id == 'all':
                # берем все брони у пользователя на этот сеанс
                curs.execute(
                    """SELECT performance_id, place_id, buyer_id, order_id FROM orders WHERE user_id = %s AND performance_id = %s AND status = 2;""",
                    (user_id, performance_id))
                orders_to_close = curs.fetchall()
            else:
                # берем все брони кроме place_id который нам передали
                curs.execute(
                    """SELECT performance_id, place_id, buyer_id, order_id FROM orders WHERE user_id = %s AND performance_id = %s AND status = 2 AND place_id != %s;""",
                    (user_id, performance_id, place_id))
                orders_to_close = curs.fetchall()

    # print('11111111', orders_to_close)
    # проходимся по всем таким броням
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
                bot.send_message(5254091301,
                                 f'!!!!Ошибка. Заказ unblock_all, но отменить не вышло {e}')
                logger.exception("Произошла ошибка RRWgA_SetOrderToNull")
                time.sleep(7)

    with psycopg2.connect(db_path) as data:
        with data.cursor() as curs:
            try:
                curs.execute(
                    """UPDATE orders SET status = 2 WHERE performance_id = %s AND place_id = %s AND buyer_id = %s AND user_id = %s""",
                    (order[0], order[1], order[2], user_id))
            except Exception as e:
                bot.send_message(5254091301,
                                 f'!!!!Ошибка UPDATE orders SET status. Заказ unblock_all, но отменить не вышло {e}: {order=}')


def payment_button_pressed(request, user_id, performance_id, place_id, price, order_id):
    with psycopg2.connect(db_path) as data:
        with data.cursor() as curs:
            try:
                curs.execute("""SELECT buyer_id FROM users WHERE user_id = %s;""", (user_id,))
                buyer_id = curs.fetchone()[0]
            except TypeError:
                buyer_id = 998277

            curs.execute(
                """SELECT row, place, price, order_id FROM orders WHERE order_id = %s AND  user_id = %s AND status = 1;""",
                (order_id, user_id))
            did_he_almoust_bye = curs.fetchone()

    # unblock_all(user_id, performance_id, "all")  # если у пользователя были другие брони, снимаем их, чтобы не дать ему купить 2 билета

    # params = {
    #     "sp": "WgA_LockPlace",
    #     "IdPerformance": performance_id,
    #     "IdPlace": int(place_id),
    #     "IdClient": 2024,
    #     "IdPriceCategory": 17198,
    #     "df": "J"
    # }
    #
    # response = requests.request("GET", 'http://195.208.148.248:18088/TicketAutomat/get.php', params=params)

    if did_he_almoust_bye != None:  # если уже успешно купил билет на сеанс
        import telebot
        bot.send_message(user_id,
                         f'''На сеанс можно купить только 1 билет по Пушкинской карте\nВаш билет\nРяд {did_he_almoust_bye[0]} Место {did_he_almoust_bye[1]} Цена {did_he_almoust_bye[2]}\nНомер заказа {did_he_almoust_bye[3]}''')
        return render(request, 'finish.html')

    # регистрируем заказ
    # params = {
    #     "sp": "WgA_CreateMultyOrder",
    #     "IdClient": 2024,
    #     "df": "J"}
    #
    # response = requests.request("GET", 'http://195.208.148.248:18088/TicketAutomat/get.php', params=params)
    # order_data = response.json()

    # if isinstance(order_data, dict):
    #     if order_data.get('Error') is not None:
    #         bot.send_message(user_id,
    #                          f'''Какая-то ошибка, попробуйте позже.\n{order_data.get('Error')}''')
    #         unblock_all(user_id, performance_id, "all")
    #         return render(request, 'finish.html')

    # try:
    #     order_id = order_data['IdOrder']
    # except TypeError:
    #     unblock_all(user_id, performance_id, "all")
    #     return render(request, 'finish.html')

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
        "description": f"Заказ №{order_id}",
    }, uuid.uuid4())

    payment_link = payment.confirmation.confirmation_url
    payment_id = payment.id

    # пишем в заявку все данные
    with psycopg2.connect(db_path) as dataf:
        with dataf.cursor() as curs:
            curs.execute(
                """UPDATE orders SET status = 3, order_id = %s, payment_id = %s, payment_link = %s WHERE order_id = %s AND  user_id = %s""",
                (order_id, payment_id, payment_link, order_id, user_id))

    return render(request, 'payment.html', {'iframe_url': payment_link, 'close_webapp': True, 'order_id': order_id})


def cheir_choosed(request, user_id, performance_id, place_id, price, place_locked_time, form):
    # print(request.POST['chair_but'], request.POST['user_id'], request.POST)
    state, price, place_place, place_row, place_id, place_locked_time = request.POST['chair_but'].split(',')
    user_id = request.POST['user_id']
    # если место занято то {'Error': '-35005' если свободно, то {'Price': '200'}
    with psycopg2.connect(db_path) as data:
        with data.cursor() as curs:
            # вытаскиваем id зала, потому что у некоторых залов специфические настройки
            try:
                curs.execute("""SELECT buyer_id FROM users WHERE user_id = %s;""", (user_id,))
                buyer_id = curs.fetchone()[0]
            except TypeError:
                buyer_id = 998277

    # print(price, place_place, place_row, place_id, buyer_id)
    params = {
        "sp": "WgA_LockPlace",
        "IdPerformance": performance_id,
        "IdPlace": int(place_id),
        "IdClient": 2024,
        "IdPriceCategory": 17198,
        "df": "J"
    }

    response = requests.request("GET", 'http://195.208.148.248:18088/TicketAutomat/get.php', params=params)
    locked_place = response.json()
    # print(locked_place)
    # записываем в базу как заказ со статусом 1
    place_locked_time = time.time()
    with psycopg2.connect(db_path) as data:
        with data.cursor() as curs:
            curs.execute(
                """INSERT INTO orders (user_id, buyer_id, performance_id, place_id, place_locked_time, status, place, row) VALUES (%s, %s, %s, %s, %s, 2, %s, %s);""",
                (user_id, buyer_id, performance_id, place_id, place_locked_time, place_place, place_row))
    try:
        if locked_place['Price']:  # если место свободно
            # print(locked_place, 'open')
            price = locked_place['Price']

            # регистрируем заказ
            params = {
                "sp": "WgA_CreateMultyOrder",
                "IdClient": 2024,
                "df": "J"}

            response = requests.request("GET", 'http://195.208.148.248:18088/TicketAutomat/get.php', params=params)
            order_data = response.json()

            if isinstance(order_data, dict):
                if order_data.get('Error') is not None:
                    bot.send_message(user_id,
                                     f'''Какая-то ошибка, попробуйте позже.\n{order_data.get('Error')}''')
                    unblock_all(user_id, performance_id, "all")
                    return render(request, 'finish.html')

            try:
                order_id = order_data['IdOrder']
            except TypeError:
                unblock_all(user_id, performance_id, "all")
                return render(request, 'finish.html')

            with psycopg2.connect(db_path) as data:
                with data.cursor() as curs:
                    curs.execute(
                        """UPDATE orders SET price = %s, order_id = %s WHERE performance_id = %s AND place_id = %s AND buyer_id = %s AND user_id = %s AND status = 2;""",
                        (price, order_id, performance_id, place_id, buyer_id, user_id))
            seatMap = create_list_of_buttons(performance_id)
            return render(request, 'when_place_choosed.html',
                          {'form': form, 'back_value': f'back,{price},{place_place},{place_row},{place_id},{order_id}',
                           'button_value': f'pay,{price},{place_place},{place_row},{place_id},{order_id}',
                           'text': f'Ряд {place_row}\nМесто {place_place}\n\nЦена {price}'})
    except KeyError as ex:  # если место заблокировано уже
        logger.info(f"KeyError: lock {ex}")
        seatMap = create_list_of_buttons(performance_id)
        return render(request, 'index.html',
                      {'form': form, 'seatMap': seatMap, 'down_text': 'Простите, это место уже занято'})


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
