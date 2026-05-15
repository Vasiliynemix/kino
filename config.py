import asyncio
import os
import threading
from pathlib import Path
from typing import Any

import requests as _requests
from dotenv import load_dotenv
from loguru import logger
from maxapi import Bot, Dispatcher
from maxapi.enums import ParseMode
from maxapi.enums.upload_type import UploadType
from maxapi.types import InputMediaBuffer
from maxapi.types.attachments.upload import AttachmentUpload, AttachmentPayload

load_dotenv()

# ─── Режим работы ─────────────────────────────────────────────────────────────
IS_PROD = os.getenv('IS_PROD')

# ─── YooKassa ─────────────────────────────────────────────────────────────────
youkassa_shop_id = os.getenv('YOUKASSA_SHOP_ID')
youkassa_secret_key = os.getenv('YOUKASSA_SECRET_KEY')

# ─── Валидация (Почта Банк) ───────────────────────────────────────────────────
validation_url = os.getenv('VALIDATION_URL')
pochta_bank_token = os.getenv('POCHTA_BANK_TOKEN')

# ─── Внешние API ──────────────────────────────────────────────────────────────
pro_kino_api_key = os.getenv('PRO_KINO_API_KEY')
pro_kino_url = os.getenv('PRO_KINO_URL')
kinopoisk_token = os.getenv('KINOPOISK_TOKEN')
url_kino_baza = os.getenv('URL_KINO_BAZA')
url_prokultura = os.getenv('URL_PROKULTURA')
sber_login = os.getenv('SBER_LOGIN')
sber_password = os.getenv('SBER_PASSWORD')

# ─── URLs и токен бота ────────────────────────────────────────────────────────
if IS_PROD == "True":
    MAX_BOT_TOKEN = os.getenv('MAX_BOT_TOKEN')
    url = os.getenv('URL')
    url_server = os.getenv('URL_SERVER', url)
else:
    url = "https://super-powerful-bee.ngrok-free.app"
    url_server = "https://epic-man-obviously.ngrok-free.app"
    MAX_BOT_TOKEN = os.getenv('MAX_BOT_TOKEN_TEST')

WEBHOOK_URL = f"{url}/webhook"
WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET', 'changeme12345')
WEBHOOK_HOST = os.getenv('WEBHOOK_HOST', '0.0.0.0')
WEBHOOK_PORT = int(os.getenv('WEBHOOK_PORT', '8080'))

# ─── MAX REST base ─────────────────────────────────────────────────────────────
MAX_API_BASE = "https://botapi.max.ru"

# ─── Инициализация бота и диспетчера ──────────────────────────────────────────
bot = Bot(token=MAX_BOT_TOKEN)
dp = Dispatcher()

_loop = None


def set_loop(loop):
    global _loop
    _loop = loop


def get_loop():
    return _loop


# ─── Пути ─────────────────────────────────────────────────────────────────────
root_path = Path(__file__).parent
db_path = os.getenv('POSTGRES_DB_URL')
log_dir = os.path.join(root_path, "logs")
error_log_file = os.path.join(log_dir, "error.log")
info_log_file = os.path.join(log_dir, "info.log")

# ─── Русские названия месяцев ─────────────────────────────────────────────────
months_ru = {
    1: 'января', 2: 'февраля', 3: 'марта', 4: 'апреля',
    5: 'мая', 6: 'июня', 7: 'июля', 8: 'августа',
    9: 'сентября', 10: 'октября', 11: 'ноября', 12: 'декабря',
}


async def send_message_sync(chat_id: int, user_id: int, text: str, attachments=None):
    await bot.send_message(
        chat_id=chat_id,
        user_id=user_id,
        text=text,
        parse_mode=ParseMode.HTML,
        attachments=attachments,
    )


ADMIN_ID = 8099031
ADMIN_ID_CHAT = 284784629
ADMIN_ID_2 = 1013689498  # Антон


async def notify_admin(text: str, admin_2: bool = False) -> None:
    """Уведомить администратора (синхронно из любого потока)."""
    await send_message_sync(chat_id=ADMIN_ID_CHAT, user_id=ADMIN_ID, text=text)
    if admin_2:
        pass


async def send_document_sync(
    chat_id: int,
    user_id: int,
    file_path: str,
    caption: str = "",
    filename: str | None = None,
) -> None:
    if filename is None:
        filename = os.path.basename(file_path)

    try:
        # 1. читаем файл в память
        with open(file_path, "rb") as f:
            buffer = f.read()

        # 2. создаём media объект (без mime — SDK сам определит)
        media = InputMediaBuffer(
            buffer=buffer,
            filename=filename,
        )

        # 3. SDK сам:
        # - определит тип
        # - загрузит файл
        # - получит token
        attachment = await bot.upload_media(media)

        # 4. отправка сообщения
        await bot.send_message(
            chat_id=chat_id,
            user_id=user_id,
            text=caption,
            attachments=[attachment],
        )

    except Exception as e:
        logger.error(f"[send_document] ошибка: {e}")
