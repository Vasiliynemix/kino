from config import *
import telebot
import psycopg2
from telebot import types, util
import datetime
import time
import sys
from loguru import logger

from pkg.log import CustomLogger

CustomLogger().add_logger(info_log_file, __name__)


def send_cinemas(message):
    # 1 шаг, спрашиваем город
    # берем все города, приобразовываем в кнопки и посылаем в сообщении

    t1 = time.time()
    with psycopg2.connect(db_path) as conn:
        with conn.cursor() as curs:
            curs.execute("""SELECT DISTINCT city FROM cinemas;""")
            cinemas = curs.fetchall()

    city_markup = types.InlineKeyboardMarkup(row_width=1)
    for cinema in cinemas:
        city_but = types.InlineKeyboardButton(text=cinema[0], callback_data=f'choose_cinema {cinema[0]}')
        city_markup.add(city_but)
    t2 = time.time()
    try:
        bot.send_message(message.from_user.id, 'Выберите город', reply_markup=city_markup)
    except telebot.apihelper.ApiTelegramException:
        pass
    t3 = time.time()
    logger.info(f"Total time: {t3 - t1}, Execution time: {t2 - t1}, Sending time: {t3 - t2}")


def send_dates(callback):
    # 1 шаг, спрашиваем город
    # берем все города, приобразовываем в кнопки и посывлаем в сообщении
    # 7 часов чтобы соблюсти часовой пояс, 14 минут чтобы соблюсти возможность продажи билетов через 15 минут после начала
    delta = datetime.timedelta(hours=7, minutes=14)
    today = datetime.datetime.now(datetime.timezone.utc) + delta
    today_time = today.time().strftime('%H:%M')
    today_date = today.date().strftime('%Y-%m-%d')
    with psycopg2.connect(db_path) as conn:
        with conn.cursor() as curs:
            curs.execute(
                "SELECT DISTINCT DATE(date) FROM performance WHERE date > %s  OR (%s = date AND %s <= time) ORDER BY date ASC;",
                (today_date, today_date, today_time))
            dates = curs.fetchall()

    # получив даты по порядку мы преобразовываем их в нужный для кнопок формат
    date_list = [date[0] for date in dates]

    # если это сегодняшняя дата, она изменилась на "Сегодня" если завтрашняя, то на "Завтра", а если ни то и ни другое, то дата 2023-05-09 преобразовалась в 9 мая
    delta = datetime.timedelta(hours=7)
    today = datetime.datetime.now(datetime.timezone.utc) + delta
    today = today.date()
    tomorrow = today + datetime.timedelta(days=1)

    formatted_dates = []
    for date_str in date_list:
        date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
        if date == today:
            formatted_dates.append('Сегодня')
        elif date == tomorrow:
            formatted_dates.append('Завтра')
        else:
            day = date.strftime('%e')
            month = months_ru[date.month]
            formatted_dates.append(f"{day} {month}")

    # создаем кнопки и отсылаем
    date_markup = types.InlineKeyboardMarkup(row_width=1)
    i = 0
    while i < len(formatted_dates):
        date_but = types.InlineKeyboardButton(text=formatted_dates[i], callback_data=f'choose_date {date_list[i]}')
        date_markup.add(date_but)
        i += 1
        if i % 7 == 0:
            break
    try:
        bot.send_message(callback.from_user.id, '*Выберите день:*', reply_markup=date_markup, parse_mode='MARKDOWN')
    except telebot.apihelper.ApiTelegramException:
        pass


def send_movies(callback, date):
    # вытаскиваем из базы все фильмы и кинотеатры, потом цикло прогоняем по фильмам и получаем все сеансы на эти фильмы в этих кинотеатрах
    try:
        with psycopg2.connect(db_path) as conn:
            with conn.cursor() as curs:
                # получаем город который пользователь указывал ранее, потом кинотеатры этого города
                curs.execute("""SELECT city FROM users WHERE user_id = %s;""", (callback.from_user.id,))
                city = curs.fetchone()
                try:
                    curs.execute("""SELECT building_id FROM cinemas WHERE city = %s;""", (city[0],))
                    cinemas = curs.fetchall()
                except TypeError:  # если человек почему то не выбрал город или он не записался
                    curs.execute("""SELECT building_id FROM cinemas WHERE city = %s;""",
                                 ('Новосибирск',))
                    cinemas = curs.fetchall()
                cinemas_list = [cinema[0] for cinema in cinemas]
                # dct разрешенные пушкинской карте фильмы
                curs.execute("""SELECT * FROM show WHERE pushkin_card = 1;""")
                accepted_shows = curs.fetchall()
                somthing_sended = False
                # 7 часов чтобы соблюсти часовой пояс, 14 минут чтобы соблюсти возможность продажи билетов через 15 минут после начала
                delta = datetime.timedelta(hours=7, minutes=-14)
                today = datetime.datetime.now(datetime.timezone.utc) + delta
                today_time = today.time().strftime('%H:%M')
                today_date = today.date().strftime('%Y-%m-%d')
                for show in accepted_shows:
                    # мы запрашиваем те сеансы которые проходят в одном из кинотеатров нужного нам города и относятся к нужному нам фильму если есть свободные места и это не зал детская площадка. Выдаем сначала по залу, потом по времени
                    if today_date == date:
                        curs.execute(
                            f"SELECT * FROM performance WHERE building_id IN ({','.join('%s' * len(cinemas_list))}) AND show_id = %s AND date = %s AND freeplaces != 0 AND hall_id != 15 AND %s <= time ORDER BY hallname, time ASC",
                            cinemas_list + [show[0]] + [date] + [today_time])
                        performances = curs.fetchall()
                    else:
                        curs.execute(
                            f"SELECT * FROM performance WHERE building_id IN ({','.join('%s' * len(cinemas_list))}) AND show_id = %s AND date = %s AND freeplaces != 0 AND hall_id != 15 ORDER BY hallname, time ASC",
                            cinemas_list + [show[0]] + [date])
                        performances = curs.fetchall()

                    if performances == []:
                        continue
                    perf_markup = types.InlineKeyboardMarkup(row_width=5)
                    for perf in performances:
                        perf_webapp = types.WebAppInfo(f"{url_server}/kino/{perf[0]}")  # создаем webappinfo - формат хранения url
                        perf_but = types.KeyboardButton(text=f'{perf[9]} {perf[5]}', web_app=perf_webapp)  # создаем кнопку типа webapp
                        perf_markup.add(perf_but)
                    # отсылаем фильм с сеансами на выбранную дату
                    # если есть фото
                    somthing_sended = True
                    if show[5] is not None:
                        if show[6] != 0:
                            text1 = f'{show[1]}\nКинопоиск {round(show[6], 1)}\n\n{show[4]}'
                        else:
                            text1 = f'{show[1]}\n\n{show[4]}'
                        text = util.smart_split(text1, 1024)[0]
                        try:
                            bot.send_photo(callback.from_user.id, photo=show[5], caption=text, reply_markup=perf_markup)
                        except telebot.apihelper.ApiTelegramException as e:
                            try:
                                bot.send_message(callback.from_user.id, {show[1]}, reply_markup=perf_markup)
                            except telebot.apihelper.ApiTelegramException as e:
                                logger.error(e)
                    else:
                        try:
                            bot.send_message(callback.from_user.id, {show[1]}, reply_markup=perf_markup)
                        except telebot.apihelper.ApiTelegramException as e:
                            logger.error(e)
                if somthing_sended is False:
                    try:
                        bot.send_message(callback.from_user.id, 'Кажется сеансов по заданным критериям для пушкинской карты нет, простите😔')
                    except telebot.apihelper.ApiTelegramException:
                        pass

    except Exception as e:
        logger.exception('-')
