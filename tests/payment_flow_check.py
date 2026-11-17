"""
Сценарии оплаты по Пушкинской карте на ЛОКАЛЬНОЙ тестовой БД (POSTGRES_DB_URL из .env).
ЮKassa, ВТБ, MAX и билетная система подменены заглушками — внешних запросов нет.

Запуск из корня проекта:  PYTHONPATH=. .venv/bin/python tests/payment_flow_check.py
Нужны: таблицы из deploy/schema.sql и заполненный pushkin_periods (хотя бы один период для Бердска).
Создаёт записи с отрицательными id и удаляет их в конце.
"""
import asyncio
import datetime
import types

import psycopg2
from zoneinfo import ZoneInfo

import base_requests as br
import pushkin
from config import db_path

assert "test" in db_path, "запускать только на тестовой базе"

log = []


async def fake_admin(text, **kw):
    log.append(("admin", text[:60]))


async def fake_user(chat, uid, text, *a, **kw):
    log.append(("user", text[:90]))


br.notify_admin = fake_admin
br.send_message_sync = fake_user
br.Payment.capture = lambda pid: log.append(("CAPTURE", pid))
br.Payment.cancel = lambda pid: log.append(("CANCEL", pid))
br.Refund.create = lambda body, key: log.append(("REFUND", body["payment_id"]))
br.requests.get = lambda *a, **k: types.SimpleNamespace(text="{}", status_code=200)
br.pushkin_term_inst_id = "70372200101"
br.validation_url = "https://example.invalid/tickets/check"
br.pochta_bank_token = "eyJTEST"

calls = []


class Resp:
    def __init__(self, code, js):
        self.status_code, self._js, self.text = code, js, str(js)

    def json(self):
        return self._js


vtb = {"resp": None}


def fake_post(url, headers, params, json, timeout):
    calls.append((json, headers, params))
    return vtb["resp"]


pushkin.requests.post = fake_post

db = psycopg2.connect(db_path)
db.autocommit = True
cur = db.cursor()
cur.execute("SELECT show_id, start_ms, end_ms FROM pushkin_periods WHERE city = 'Бердск' LIMIT 1")
show_id, start_ms, end_ms = cur.fetchone()
mid = datetime.datetime.fromtimestamp((start_ms + end_ms) / 2000, ZoneInfo("Asia/Novosibirsk"))
cur.execute(
    "INSERT INTO performance (performance_id, show_id, building_id, date, time, hallname) VALUES "
    "(-10, %s, 2515, %s, %s, 'Зал'), (-11, %s, 2515, '2020-01-01', '10:00', 'Зал')",
    (show_id, mid.strftime('%Y-%m-%d'), mid.strftime('%H:%M'), show_id),
)


def make_order(oid, perf):
    uid = oid * 100
    cur.execute("INSERT INTO users (user_id, max_chat_id, buyer_id, name, surname, patronymic) "
                "VALUES (%s, %s, 1, 'Иван', 'Иванов', 'Иванович') ON CONFLICT DO NOTHING", (uid, uid))
    cur.execute("INSERT INTO orders (order_id, user_id, buyer_id, performance_id, place_id, price, payment_id, "
                "status, row, place, uuid_order, client_ip) "
                "VALUES (%s, %s, 1, %s, 5, 300, %s, 3, 1, 1, %s, '1.2.3.4')",
                (oid, uid, perf, f"pay{oid}", f"u{oid}"))


def payment(oid, status, rrn="123456789012", first6="220024"):
    return types.SimpleNamespace(
        id=f"pay{oid}", status=status,
        created_at=datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z'),
        authorization_details=types.SimpleNamespace(rrn=rrn),
        amount=types.SimpleNamespace(value="300.00", currency="RUB"),
        payment_method=types.SimpleNamespace(card=types.SimpleNamespace(first6=first6)),
    )


def run(oid, pay):
    br.Payment.find_one = lambda pid: pay
    log.clear()
    calls.clear()
    ret = asyncio.run(br.check_payment_status(f"pay{oid}"))
    cur.execute("SELECT status, validation, validation_reason FROM orders WHERE order_id = %s", (oid,))
    print(f"  -> ret={ret} vtb_calls={len(calls)} db={cur.fetchone()}\n     log={log}")


try:
    print("1 холд + ACCEPTED")
    make_order(-1, -10)
    vtb["resp"] = Resp(200, {"result": "ACCEPTED", "createDt": 1, "signatureData": "SIG=="})
    run(-1, payment(-1, "waiting_for_capture"))
    cur.execute("SELECT validation_signature FROM orders WHERE order_id = -1")
    print("  подпись банка сохранена:", cur.fetchone())
    print("  повтор (банк повторно не вызывается)")
    run(-1, payment(-1, "waiting_for_capture"))

    print("2 холд + DECLINED NOT_EQUAL_PRICE")
    make_order(-2, -10)
    vtb["resp"] = Resp(200, {"result": "DECLINED", "reason": "NOT_EQUAL_PRICE"})
    run(-2, payment(-2, "waiting_for_capture"))
    print("  затем canceled")
    run(-2, payment(-2, "canceled"))

    print("3 холд + 425 (админа не тревожим), затем 500 (админ один раз)")
    make_order(-3, -10)
    vtb["resp"] = Resp(425, {"timeout": "PT3S"})
    run(-3, payment(-3, "waiting_for_capture"))
    vtb["resp"] = Resp(500, {"err": 1})
    run(-3, payment(-3, "waiting_for_capture"))
    run(-3, payment(-3, "waiting_for_capture"))

    print("4 нет результата 5 минут от первого запроса")
    cur.execute("UPDATE orders SET validation_started = validation_started - 301 WHERE order_id = -3")
    run(-3, payment(-3, "waiting_for_capture"))
    print("  затем canceled")
    run(-3, payment(-3, "canceled"))

    print("5 старый одностадийный succeeded + DECLINED")
    make_order(-5, -10)
    vtb["resp"] = Resp(200, {"result": "DECLINED", "reason": "MULTISESSION"})
    run(-5, payment(-5, "succeeded"))

    print("6 сеанс не в реестре")
    make_order(-6, -11)
    vtb["resp"] = Resp(200, {"result": "ACCEPTED"})
    run(-6, payment(-6, "waiting_for_capture"))

    print("7 не задан код эквайера")
    br.pushkin_term_inst_id = None
    make_order(-7, -10)
    run(-7, payment(-7, "waiting_for_capture"))
    br.pushkin_term_inst_id = "70372200101"

    print("8 RRN ещё нет")
    make_order(-8, -10)
    run(-8, payment(-8, "waiting_for_capture", rrn=None))

    print("9 чужая карта (first6 220220) — отмена сразу, без запроса в ВТБ")
    make_order(-9, -10)
    run(-9, payment(-9, "waiting_for_capture", first6="220220"))
    print("  затем canceled")
    run(-9, payment(-9, "canceled"))

    print("10 старая карта Почта Банка (220077) — решает ВТБ")
    make_order(-10, -10)
    run(-10, payment(-10, "waiting_for_capture", first6="220077"))

    print("11 нет данных о карте — решает ВТБ")
    make_order(-11, -10)
    run(-11, payment(-11, "waiting_for_capture", first6=None))

    print("12 формат запроса в ВТБ")
    make_order(-12, -10)
    run(-12, payment(-12, "waiting_for_capture"))
    body, headers, params = calls[-1]
    print("  body:", {k: (v[:16] + '…' if k == 'buyer' else v) for k, v in body.items()})
    print("  headers:", {k: (v[:12] + '…' if k == 'Authorization' else v) for k, v in headers.items()},
          "params:", params)
finally:
    cur.execute("DELETE FROM orders WHERE order_id < 0")
    cur.execute("DELETE FROM performance WHERE performance_id < 0")
    cur.execute("DELETE FROM users WHERE user_id < 0")
