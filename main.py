"""
Точка входа: MAX-бот + aiohttp webhook сервер.
Запуск: python main.py
"""
import asyncio
import os
import re
import threading

import psycopg2
from aiohttp import web
from loguru import logger
from maxapi.context import State, StatesGroup, BaseContext
from maxapi.context import MemoryContext
from maxapi.methods.types.getted_updates import process_update_request, process_update_webhook
from maxapi.types import Message, CallbackButton, MessageCallback, MessageCreated, ButtonsPayload
from maxapi.types.attachments.buttons import InlineButtonUnion
from maxapi.types import UpdateUnion

import base_requests
import send_messages

from config import (
    bot, dp,
    db_path,
    info_log_file, error_log_file, log_dir,
    WEBHOOK_HOST, WEBHOOK_PORT, WEBHOOK_URL, WEBHOOK_SECRET,
    set_loop,
)
from pkg.log import CustomLogger

os.makedirs(log_dir, exist_ok=True)
CustomLogger().init_logging()
CustomLogger().add_logger(info_log_file, __name__)


# ─── FSM States ───────────────────────────────────────────────────────────────

class UserState(StatesGroup):
    waiting_for_first_name = State()
    waiting_for_last_name = State()
    waiting_for_middle_name = State()
    waiting_for_pd_agreement = State()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def normalize_name(name: str) -> str:
    parts = name.strip().lower().split('-')
    return '-'.join(p.capitalize() for p in parts)


def validate_name(name: str) -> bool:
    return bool(re.match(r'^[А-ЯЁ][а-яё]+(-[А-ЯЁ][а-яё]+)?$', name))


# ─── Любое сообщение без активного состояния — стартовая точка ───────────────

@dp.bot_started()
@dp.message_created()
async def any_message_handler(message: MessageCreated, context: BaseContext):
    """
    Обрабатываем все входящие сообщения.
    Если пользователь в FSM-состоянии — маршрутизируем по нему.
    Иначе — это «старт» диалога.
    """
    chat_id, user_id = message.get_ids()
    state: MemoryContext = context
    text = (message.message.body.text or '').strip()

    # ── /cancel в любом состоянии ────────────────────────────────────────────
    if text.lower() in ('/cancel', 'отмена'):
        await state.clear()
        await bot.send_message(chat_id,
                               user_id,
                               'Регистрация отменена. Напишите что-нибудь, чтобы начать снова.')
        return

    current_state = await state.get_state()
    logger.info(f"{current_state=}")

    # ── FSM: сбор имени ──────────────────────────────────────────────────────
    if current_state == UserState.waiting_for_first_name.name:
        name = normalize_name(text)
        if not validate_name(name):
            await bot.send_message(chat_id,
                                   user_id,
                                   '❌ Имя введено некорректно.\n'
                                   'Используйте только кириллицу.\n'
                                   'Пример: Иван или Анна-Мария')
            return
        await state.update_data(first_name=name)
        await state.set_state(UserState.waiting_for_last_name)
        await bot.send_message(chat_id, user_id, 'Введите вашу Фамилию:')
        return

    if current_state == UserState.waiting_for_last_name:
        last_name = normalize_name(text)
        if not validate_name(last_name):
            await bot.send_message(chat_id,
                                   user_id,
                                   '❌ Фамилия введена некорректно.\n'
                                   'Пример: Петров или Сидоров-Иванов')
            return
        await state.update_data(last_name=last_name)
        await state.set_state(UserState.waiting_for_middle_name)
        await bot.send_message(chat_id, user_id, 'Введите Отчество (или напишите «Нет»):')
        return

    if current_state == UserState.waiting_for_middle_name:
        if text.lower() == 'нет':
            middle_name = ''
        else:
            middle_name = normalize_name(text)
            if not validate_name(middle_name):
                await bot.send_message(chat_id,
                                       user_id,
                                       '❌ Отчество введено некорректно.\n'
                                       'Пример: Иванович\nИли напишите «Нет»')
                return
        await state.update_data(middle_name=middle_name)
        data = await state.get_data()
        full_name = ' '.join(filter(None, [
            data.get('last_name'),
            data.get('first_name'),
            middle_name,
        ]))
        agreement_text = (
            f'Ваши данные:\n{full_name}\n\n'
            'Нажимая кнопку ниже, вы подтверждаете согласие на обработку '
            'персональных данных в целях оформления билетов.'
        )
        await state.set_state(UserState.waiting_for_pd_agreement)
        await bot.send_message(chat_id, user_id, agreement_text, attachments=[
            ButtonsPayload(
                buttons=[[
                    CallbackButton(
                        text="✅ Согласен на обработку ПД",
                        payload="pd_agree"
                    )
                ]]
            ).pack()
        ])
        return

    # ── Нет активного состояния — стартовый поток ────────────────────────────
    try:
        await state.clear()
        user = base_requests.user_reg(user_id, chat_id)
        print(user)

        if user.get('name') is None:
            await bot.send_message(
                chat_id,
                user_id,
                '🎟 Для дальнейшего оформления билетов через этого бота необходимо указать ваши данные.\n\n'
                'Пожалуйста, вводите ФИО строго так, как указано в паспорте.\n\n'
                'Эти данные будут использоваться для формирования билетов на фильмы. '
                'Ответственность за корректность введённых данных лежит на вас.'
            )
            await state.set_state(UserState.waiting_for_first_name)
            await bot.send_message(chat_id, user_id, 'Введите ваше Имя:')
            return

        await send_messages.send_cinemas(chat_id, user_id)
    except Exception:
        logger.exception('Ошибка в any_message_handler')


# ─── Callback handlers ────────────────────────────────────────────────────────

@dp.message_callback()
async def callback_router(callback: MessageCallback, context: BaseContext):
    payload = callback.callback.payload or ''
    chat_id, user_id = callback.get_ids()
    state: MemoryContext = context

    # ── Обновить ФИО ─────────────────────────────────────────────────────────
    if payload == 'update_fio':
        await bot.send_message(
            chat_id,
            user_id,
            '🎟 Для дальнейшего оформления билетов через этого бота необходимо указать ваши данные.\n\n'
            'Пожалуйста, вводите ФИО строго так, как указано в паспорте.\n\n'
            'Эти данные будут использоваться для формирования билетов на фильмы. '
            'Ответственность за корректность введённых данных лежит на вас.'
        )
        await state.clear()
        await state.set_state(UserState.waiting_for_first_name)
        await bot.send_message(chat_id, user_id, 'Введите ваше Имя:')
        return

    # ── Согласие на ПД ───────────────────────────────────────────────────────
    if payload == 'pd_agree':
        current_state = await state.get_state()
        if current_state != UserState.waiting_for_pd_agreement.name:
            return
        data = await state.get_data()
        base_requests.user_fio_save(
            user_id,
            chat_id,
            data.get('first_name'),
            data.get('last_name'),
            data.get('middle_name'),
            True,
        )
        await state.clear()
        await bot.send_message(chat_id, user_id, '✅ Согласие принято. Регистрация завершена.')
        await send_messages.send_cinemas(chat_id, user_id)
        return

    # ── Выбор города ─────────────────────────────────────────────────────────
    if payload.startswith('choose_cinema '):
        city = payload.split(' ', 1)[1]
        with psycopg2.connect(db_path) as conn:
            with conn.cursor() as curs:
                curs.execute(
                    'UPDATE users SET city = %s WHERE user_id = %s',
                    (city, user_id),
                )
        await send_messages.send_dates(callback)
        return

    # ── Выбор даты ───────────────────────────────────────────────────────────
    if payload.startswith('choose_date '):
        logger.info(f'choose_date: {payload}')
        date = payload.split(' ', 1)[1]
        await send_messages.send_movies(callback, date)
        return


# ─── Регистрация webhook в MAX ────────────────────────────────────────────────

async def register_webhook() -> None:
    try:
        await bot.delete_webhook()
    except Exception:
        pass
    webhook_full = f'{WEBHOOK_URL}'
    await bot.subscribe_webhook(url=webhook_full, secret=WEBHOOK_SECRET)
    logger.info(f'Webhook зарегистрирован: {webhook_full}')


async def send_message_handler(request: web.Request) -> web.Response:
    try:
        data = await request.json()

        await bot.send_message(
            chat_id=data["chat_id"],
            user_id=data["user_id"],
            text=data["text"],
            attachments=data.get("attachments"),
        )

        return web.json_response({"status": "ok"})

    except Exception:
        logger.exception("send_message_handler")
        return web.json_response({"status": "error"}, status=500)


async def webhook_handler(request: web.Request) -> web.Response:
    secret = request.headers.get("X-Max-Bot-Api-Secret")

    if secret != WEBHOOK_SECRET:
        return web.Response(status=403)

    try:
        raw = await request.json()

        # 🔥 правильный парсинг через maxapi
        event = await process_update_webhook(raw, bot=bot)

        await dp.handle(event)

        return web.Response(text="ok")

    except Exception:
        logger.exception("Ошибка обработки webhook update")
        return web.Response(text="error", status=500)


# ─── Entrypoint ───────────────────────────────────────────────────────────────

# start_async_loop()
# set_main_loop()

async def main() -> None:
    # loop = asyncio.get_running_loop()
    # set_loop(loop)
    dp.storage = MemoryContext

    # Фоновый поток обновления данных о фильмах
    # asyncio.create_task(film_update_loop())
    # asyncio.create_task(process_orders_loop())
    # threading.Thread(
    #     target=base_requests.film_update_main,
    #     args=(loop,),
    #     daemon=True
    # ).start()
    # threading.Thread(
    #     target=base_requests.process_orders,
    #     args=(loop,),
    #     daemon=True
    # ).start()

    # регаем webhook в MAX
    await register_webhook()

    # 🔥 создаем ОДИН aiohttp app
    app = web.Application()

    # webhook
    app.router.add_post("/webhook", webhook_handler)

    # internal API
    app.router.add_post("/send_message", send_message_handler)

    # запуск
    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, WEBHOOK_HOST, WEBHOOK_PORT)
    await site.start()

    logger.info(f"Server started on {WEBHOOK_HOST}:{WEBHOOK_PORT}")

    # чтобы не завершался
    while True:
        await asyncio.sleep(3600)


if __name__ == '__main__':
    asyncio.run(main())
