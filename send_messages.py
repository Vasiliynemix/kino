"""
Функции отправки сообщений пользователям через MAX Bot API.
WebApp Telegram удалён — вместо него отправляется прямая ссылка на сайт.
"""
import datetime

import psycopg2
from loguru import logger
from maxapi.enums.attachment import AttachmentType
from maxapi.types import ButtonsPayload, CallbackButton, MessageCallback, LinkButton, Attachment, OtherAttachmentPayload

from config import bot, db_path, months_ru, url_server, info_log_file
from pkg.log import CustomLogger

CustomLogger().add_logger(info_log_file, __name__)


def _inline(rows: list[list[tuple[str, str]]]):
    return ButtonsPayload(
        buttons=[
            [
                CallbackButton(
                    text=text,
                    payload=payload,
                )
                for text, payload in row
            ]
            for row in rows
        ]
    ).pack()


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


async def send_cinemas(chat_id: int, user_id: int) -> None:
    """Шаг 1: показать ФИО + кнопки выбора города."""
    with psycopg2.connect(db_path) as conn:
        with conn.cursor() as curs:
            curs.execute("SELECT DISTINCT city FROM cinemas;")
            cinemas = curs.fetchall()
            curs.execute(
                "SELECT name, surname, patronymic FROM users WHERE user_id = %s;",
                (user_id,),
            )
            user = curs.fetchone()

    fio_text = f"{user[1]} {user[0]} {user[2]}".strip() if user else "—"

    try:
        await bot.send_message(chat_id, user_id, fio_text, attachments=[
            ButtonsPayload(
                buttons=[[
                    CallbackButton(
                        text="Изменить ФИО",
                        payload="update_fio"
                    )
                ]]
            ).pack()
        ])
    except Exception as e:
        logger.error(f"send_cinemas fio: {e}")

    city_buttons = [[(c[0], f"choose_cinema {c[0]}")] for c in cinemas]
    try:
        await bot.send_message(chat_id, user_id, "Выберите город", attachments=[_inline(city_buttons)])
    except Exception as e:
        logger.error(f"send_cinemas cities: {e}")


async def send_dates(callback: MessageCallback) -> None:
    """Шаг 2: показать доступные даты сеансов."""

    delta = datetime.timedelta(hours=7, minutes=14)
    today_dt = datetime.datetime.now(datetime.timezone.utc) + delta
    today_time = today_dt.time().strftime('%H:%M')
    today_date = today_dt.date().strftime('%Y-%m-%d')

    chat_id, user_id = callback.get_ids()

    with psycopg2.connect(db_path) as conn:
        with conn.cursor() as curs:

            # --- ОРИГИНАЛЬНАЯ ЛОГИКА БЕЗ ГОРОДОВ ---
            curs.execute(
                """SELECT DISTINCT DATE(date)
                   FROM performance
                   WHERE date > %s OR (%s = date AND %s <= time)
                   ORDER BY date ASC;""",
                (today_date, today_date, today_time),
            )
            dates = curs.fetchall()

    # --- форматирование как в оригинале ---
    delta = datetime.timedelta(hours=7)
    today = (datetime.datetime.now(datetime.timezone.utc) + delta).date()
    tomorrow = today + datetime.timedelta(days=1)

    date_list = [
        d[0].strftime('%Y-%m-%d') if isinstance(d[0], datetime.date) else d[0]
        for d in dates
    ]

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

    # --- кнопки 1 в ряд, максимум 7 (как в оригинале) ---
    buttons = []
    i = 0
    while i < len(formatted_dates):
        buttons.append([
            (formatted_dates[i], f"choose_date {date_list[i]}")
        ])
        i += 1
        if i % 7 == 0:
            break

    try:
        if len(buttons) == 0:
            await bot.send_message(
                chat_id,
                user_id,
                f"Сеансов на ближайшее время нет"
            )
        else:
            await bot.send_message(
                chat_id,
                user_id,
                "Выберите день:",
                attachments=[_inline(buttons)]
            )
    except Exception as e:
        logger.error(f"send_dates: {e}")


async def send_movies(callback: MessageCallback, date: str) -> None:
    """Шаг 3: показать фильмы с сеансами. Каждый сеанс — ссылка на сайт выбора мест."""
    chat_id, user_id = callback.get_ids()

    try:
        with psycopg2.connect(db_path) as conn:
            with conn.cursor() as curs:
                curs.execute("SELECT city FROM users WHERE user_id = %s;", (user_id,))
                city_row = curs.fetchone()
                city = city_row[0] if city_row else "Новосибирск"

                curs.execute("SELECT building_id FROM cinemas WHERE city = %s;", (city,))
                cinemas_list = [r[0] for r in curs.fetchall()]

                curs.execute("SELECT * FROM show WHERE pushkin_card = 1;")
                accepted_shows = curs.fetchall()

                delta = datetime.timedelta(hours=7, minutes=14)
                now = datetime.datetime.now(datetime.timezone.utc) + delta
                today_time = now.time().strftime("%H:%M")
                today_date = now.date().strftime("%Y-%m-%d")

                something_sent = False

                for show in accepted_shows:
                    params: list = [cinemas_list, show[0], date]
                    time_filter = "AND time >= %s" if today_date == date else ""
                    if today_date == date:
                        params.append(today_time)

                    query = f"""
                        SELECT * FROM performance
                        WHERE building_id = ANY(%s)
                          AND show_id = %s
                          AND date = %s
                          AND freeplaces != 0
                          AND hall_id != 15
                          {time_filter}
                        ORDER BY hallname, time ASC
                    """
                    curs.execute(query, params)
                    performances = curs.fetchall()
                    if not performances:
                        continue

                    # Каждый сеанс → кнопка с прямой ссылкой на сайт (вместо WebApp)
                    rows = [
                        [
                            (
                                f"{perf[3]} {perf[9]}",
                                f"{url_server}/kino/{perf[0]}/{user_id}",
                            )
                        ]
                        for perf in performances
                    ]

                    # 👉 если есть фото — добавляем кнопку
                    # if show[4]:
                    #     rows.append([
                    #         ("📷 Открыть постер", show[4])
                    #     ])

                    perf_markup = _inline_url(rows)

                    rating = show[5]
                    desc = show[3] or ""
                    caption = (f"{show[1]}\nКинопоиск {round(rating, 1)}\n\n{desc}"
                               if rating else f"{show[1]}\n\n{desc}")
                    caption = caption[:1024]
                    something_sent = True

                    try:
                        if show[4]:
                            photo_attachment = Attachment(
                                type=AttachmentType.IMAGE,  # или PHOTO если есть
                                payload=OtherAttachmentPayload(url=show[4]),
                                bot=bot,
                            )
                            await bot.send_message(chat_id, user_id, caption,
                                                   attachments=[photo_attachment, perf_markup])
                        else:
                            await bot.send_message(chat_id, user_id, caption, attachments=[perf_markup])
                    except Exception as e:
                        logger.error(f"send_movies отправка: {e}")
                        try:
                            await bot.send_message(chat_id, user_id, show[1], attachments=[perf_markup])
                        except Exception as e2:
                            logger.error(f"send_movies fallback: {e2}")

                if not something_sent:
                    await bot.send_message(
                        chat_id,
                        user_id,
                        "Кажется, сеансов по заданным критериям для Пушкинской карты нет, простите😔",
                    )
    except Exception:
        logger.exception("Ошибка в send_movies")
