import os
from pathlib import Path

import urllib3
from django.http import HttpResponse
from django.shortcuts import render, redirect
import sqlite3

from dotenv import load_dotenv
from loguru import logger
from urllib3.exceptions import InsecureRequestWarning

from pkg.log import CustomLogger
from .forms import MyForm
import time, requests, sys
import json
load_dotenv()

IS_PROD = os.getenv("IS_PROD")

root_path = str(Path(__file__).parent.parent.parent)
path_to_log = os.path.join(Path(__file__).parent.parent, "logs", "info.log")
db_path = os.path.join(Path(__file__).parent.parent.parent, "kino.db")
sber_login = os.getenv("SBER_LOGIN")
sber_password = os.getenv("SBER_PASSWORD")
if IS_PROD == "True":
    url = os.getenv("URL")
else:
    url = "https://verified-greatly-bonefish.ngrok-free.app"

CustomLogger().add_logger(os.path.join(Path(__file__).parent.parent.parent, "logs", "info_server.log"), __name__)


# обработать все потенциальные ошибки

# обратить внимание при норм тестах
# формат цены, чтоб не вышло что мне прислали с копейками и из-за этого я плохую сумму пользователю послал, я же в копейках шлю
def finishpayment(request, order_id):
    try:
        with sqlite3.connect(db_path, timeout=15000) as data:
            curs = data.cursor()
            payment_id = curs.execute("""SELECT payment_id FROM orders WHERE order_id == ?;""", (order_id,)).fetchone()[0]
        sys.path.append(root_path)
        from base_requests import check_payment_status
        check_payment_status(payment_id)
        return render(request, 'finish.html')
    except Exception:
        logger.exception("-")


def kino(request, performance_id):
    try:
        # print(request)
        if request.method == 'POST':  # при нажатии на кнопку
            form = MyForm(request.POST)
            if form.is_valid():
                logger.info(request.POST)
                user_id = request.POST['user_id']
                state, price, place_place, place_row, place_id = request.POST['chair_but'].split(',')
                if state == 'back':  # если нажал назад, разблокируем все его места
                    unblock_all(user_id, performance_id, 'all')
                    seatMap = create_list_of_buttons(performance_id)
                    form = MyForm()
                    return render(request, 'index.html',
                                  {'form': form, 'seatMap': seatMap, 'down_text': 'Веберите 1 место', 'is_new_data': True})
                elif state == 'pay':  # если нажал оплатить
                    ret = payment_button_pressed(request, user_id, performance_id, place_id, price)
                    return ret
                elif state == 'choose_place':  # если выбрал место
                    ret = cheir_choosed(request, performance_id, form)
                    return ret
        else:  # при первом обращении
            seatMap = create_list_of_buttons(performance_id)
            form = MyForm()
            return render(request, 'index.html',
                          {'form': form, 'seatMap': seatMap, 'down_text': 'Веберите 1 место', 'is_new_data': True})
    except Exception:
        logger.exception("-")


def unblock_all(user_id, performance_id, place_id):
    with sqlite3.connect(db_path, timeout=15000) as data:
        curs = data.cursor()
        if place_id == 'all':
            # берем все брони у пользователя на этот сеанс
            orders_to_close = curs.execute(
                """SELECT performance_id, place_id, buyer_id FROM orders WHERE user_id == ? AND performance_id == ? AND status == 2;""",
                (user_id, performance_id)).fetchall()
        else:
            # берем все брони кроме place_id который нам передали
            orders_to_close = curs.execute(
                """SELECT performance_id, place_id, buyer_id FROM orders WHERE user_id == ? AND performance_id == ? AND status == 2 AND place_id IS NOT ?;""",
                (user_id, performance_id, place_id)).fetchall()

        # print('11111111', orders_to_close)
        # проходимся по всем таким броням
        for order in orders_to_close:
            # print(order)
            params = {
                "sp": "WgA_UnlockPlace",
                "IdPerformance": order[0],
                "IdPlace": order[1],
                "IdClient": order[2],
                "df": "J"}
            response = requests.request("GET", 'http://195.208.148.248:18088/TicketAutomat/get.php', params=params)

            curs.execute(
                """UPDATE orders SET status == 0 WHERE performance_id == ? AND place_id == ? AND buyer_id == ? AND user_id == ?""",
                (order[0], order[1], order[2], user_id))


def payment_button_pressed(request, user_id, performance_id, place_id, price):
    with sqlite3.connect(db_path, timeout=15000) as data:
        curs = data.cursor()
        try:
            buyer_id = curs.execute("""SELECT buyer_id FROM users WHERE user_id == ?;""", (user_id,)).fetchone()[0]
        except TypeError:
            buyer_id = 998277
        did_he_almoust_bye = curs.execute(
            """SELECT row, place, price, order_id FROM orders WHERE user_id == ? AND performance_id == ? AND status == 1;""",
            (user_id, performance_id)).fetchone()

    unblock_all(user_id, performance_id,
                place_id)  # если у пользователя были другие брони, снимаем их, чтобы не дать ему купить 2 билета

    if did_he_almoust_bye != None:  # если уже успешно купил билет на сеанс
        from config import bot
        import telebot
        bot.send_message(user_id,
                         f'''На сеанс можно купить только 1 билет по Пушкинской карте\nВаш билет\nРяд {did_he_almoust_bye[0]} Место {did_he_almoust_bye[1]} Цена {did_he_almoust_bye[2]}\nНомер заказа {did_he_almoust_bye[3]}''')
        return render(request, 'finish.html')

    # регистрируем заказ
    params = {
        "sp": "WgA_CreateMultyOrder",
        "IdClient": buyer_id,
        "df": "J"}
    response = requests.request("GET", 'http://195.208.148.248:18088/TicketAutomat/get.php', params=params)
    order_data = response.json()
    # print(order_data)
    order_id = order_data['IdOrder']

    # делаем оплату
    params = {
        "userName": sber_login,
        "password": sber_password,
        "orderNumber": order_id,
        "amount": int(f'{price}00'),  # отправляем в копейках
        # "amount": int(f'100'),#отправляем в копейках
        'sessionTimeoutSecs': 900,  # 15 min
        "returnUrl": f"{url}/finishpayment/{order_id}",
        'language': 'ru'

    }
    # Отключение предупреждений о небезопасном соединении
    urllib3.disable_warnings(InsecureRequestWarning)
    # Создание сессии с отключенной проверкой сертификата
    session = requests.Session()
    session.verify = False
    # Путь к файлу самоподписанного сертификата
    # cert_path = '/etc/ssl/certs/Cert_CA.pem'
    response = session.get('https://securepayments.sberbank.ru/payment/rest/register.do', params=params)
    # print(response.url)
    sber = response.json()
    payment_link = sber['formUrl']
    payment_id = sber['orderId']
    logger.info(sber)

    # пишем в заявку все данные
    with sqlite3.connect(db_path, timeout=15000) as data:
        curs = data.cursor()
        curs.execute(
            """UPDATE orders SET status = 3, order_id = ?, payment_id = ?, payment_link = ? WHERE performance_id == ? AND place_id == ? AND buyer_id == ? AND user_id == ? AND status == 2""",
            (order_id, payment_id, payment_link, performance_id, place_id, buyer_id, user_id))
    return render(request, 'payment.html', {'iframe_url': payment_link})


def cheir_choosed(request, performance_id, form):
    # print(request.POST['chair_but'], request.POST['user_id'], request.POST)
    state, price, place_place, place_row, place_id = request.POST['chair_but'].split(',')
    user_id = request.POST['user_id']
    # если место занято то {'Error': '-35005' если свободно, то {'Price': '200'}
    with sqlite3.connect(db_path, timeout=15000) as data:
        curs = data.cursor()
        # вытаскиваем id зала, потому что у некоторых залов специфические настройки
        try:
            buyer_id = curs.execute("""SELECT buyer_id FROM users WHERE user_id == ?;""", (user_id,)).fetchone()[0]
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

    logger.info(params)
    response = requests.request("GET", 'http://195.208.148.248:18088/TicketAutomat/get.php', params=params)
    logger.info(decode_unicode(response.text))
    locked_place = response.json()
    # print(locked_place)
    # записываем в базу как заказ со статусом 1
    with sqlite3.connect(db_path, timeout=15000) as data:
        curs = data.cursor()
        curs.execute(
            """INSERT INTO orders (user_id, buyer_id, performance_id, place_id, place_locked_time, status, place, row) VALUES (?, ?, ?, ?, ?, 2, ?, ?);""",
            (user_id, buyer_id, performance_id, place_id, time.time(), place_place, place_row))
    try:
        if locked_place['Price']:  # если место свободно
            # print(locked_place, 'open')
            price = locked_place['Price']
            with sqlite3.connect(db_path, timeout=15000) as data:
                curs = data.cursor()
                curs.execute(
                    """UPDATE orders SET price == ? WHERE performance_id == ? AND place_id == ? AND buyer_id == ? AND user_id == ?""",
                    (price, performance_id, place_id, buyer_id, user_id))
            seatMap = create_list_of_buttons(performance_id)
            return render(request, 'when_place_choosed.html',
                          {'form': form, 'back_value': f'back,{price},{place_place},{place_row},{place_id}',
                           'button_value': f'pay,{price},{place_place},{place_row},{place_id}',
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
    # print(response.url)

    if response.status_code == 200:
        # print(response.text)
        data_show = response.json()
        # print(data_show, '\n\n')
        with sqlite3.connect(db_path, timeout=15000) as data:
            curs = data.cursor()
            # вытаскиваем id зала, потому что у некоторых залов специфические настройки
            hall_id = curs.execute("""SELECT hall_id FROM performance WHERE performance_id == ?;""",
                                   (performance_id,)).fetchone()[0]
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
                        f'choose_place,{place["Price"]},{place["PlacePlace"]},{place["PlaceRow"]},{place["IdPlace"]}')
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
                        f'choose_place,{place["Price"]},{place["PlacePlace"]},{place["PlaceRow"]},{place["IdPlace"]}')
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
