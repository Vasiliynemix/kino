import os
import socket
from pathlib import Path

import requests
from dotenv import load_dotenv
from loguru import logger
from telebot import TeleBot, apihelper, StateMemoryStorage, custom_filters
from telebot.states.sync import StateMiddleware
from telebot.util import update_types
from yookassa import Configuration

load_dotenv()

# Форсируем IPv4 глобально
orig_getaddrinfo = socket.getaddrinfo
socket.getaddrinfo = lambda host, *args, **kwargs: [
    r for r in orig_getaddrinfo(host, *args, **kwargs) if r[0] == socket.AF_INET
]

# Проверяем, что DNS теперь резолвится только в IPv4
print(socket.getaddrinfo("api.telegram.org", 443))

IS_PROD = os.getenv('IS_PROD')

# доки сбера https://securepayments.sberbank.ru/wiki/doku.php/integration:api:rest:requests:getorderstatusextended

# Конфиг для юкассы
youkassa_shop_id = os.getenv('YOUKASSA_SHOP_ID')
youkassa_secret_key = os.getenv('YOUKASSA_SECRET_KEY')
# Конфиг для юкассы

# конфиг для валидации
validation_url = os.getenv('VALIDATION_URL')
pochta_bank_token = os.getenv('POCHTA_BANK_TOKEN')
# конфиг для валидации

pro_kino_api_key = os.getenv('PRO_KINO_API_KEY')
pro_kino_url = os.getenv('PRO_KINO_URL')
kinopoisk_token = os.getenv('KINOPOISK_TOKEN')
url_kino_baza = os.getenv('URL_KINO_BAZA')
url_prokultura = os.getenv('URL_PROKULTURA')
sber_login = os.getenv('SBER_LOGIN')
sber_password = os.getenv('SBER_PASSWORD')
logger.info("Попали сюда")
if IS_PROD == "True":
    BOT_TOKEN = os.getenv('BOT_TOKEN')  # http://t.me/Mirkinopro_Bot
    url = os.getenv('URL')
    url_server = os.getenv('URL')
else:
    url = "https://super-powerful-bee.ngrok-free.app"
    url_server = "https://epic-man-obviously.ngrok-free.app"
    BOT_TOKEN = os.getenv('BOT_TOKEN_TEST')  # https://t.me/test_2_func_bot

state_storage = StateMemoryStorage()
bot = TeleBot(BOT_TOKEN, state_storage=state_storage, use_class_middlewares=True)
try:
    bot.delete_webhook()
except Exception as e:
    logger.exception(f"{e}")
logger.info(f"webhook_url: {url}/webhook")
bot.set_webhook(
    url=f"{url}/webhook",
    allowed_updates=update_types,
    drop_pending_updates=True,
)

# Add custom filters
bot.add_custom_filter(custom_filters.StateFilter(bot))

bot.setup_middleware(StateMiddleware(bot))

root_path = Path(__file__).parent
old_sqlite_path = os.path.join(root_path, "kino.db")
db_path = os.getenv('POSTGRES_DB_URL')
log_dir = os.path.join(root_path, "logs")
error_log_file = os.path.join(log_dir, "error.log")
info_log_file = os.path.join(log_dir, "info.log")

# Словарь с русскими названиями месяцев для send_messages.send_dates()
months_ru = {
    1: 'января',
    2: 'февраля',
    3: 'марта',
    4: 'апреля',
    5: 'мая',
    6: 'июня',
    7: 'июля',
    8: 'августа',
    9: 'сентября',
    10: 'октября',
    11: 'ноября',
    12: 'декабря'
}
