"""
Пушкинская карта: реестр /pushkinsCardEvents и сервис оператора (метод validation).

Правила (методичка PRO.Культура.РФ + docs.culture.ru/service):
  * продавать можно только сеанс события, которое СЕЙЧАС есть в /pushkinsCardEvents,
    для своей площадки и в пределах периода показа этой площадки;
  * билет выдаётся и уходит в ЕАИС только после result=ACCEPTED от оператора;
  * при DECLINED покупка отменяется (reversal), возврат вместо отмены не допускается.
"""
import datetime
import hashlib
import re
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

# организация на PRO.Культура.РФ
ORGANIZATION_ID = 31698
# все наши кинотеатры живут в UTC+7
DEFAULT_TZ = "Asia/Novosibirsk"


def ensure_schema(curs) -> None:
    """Идемпотентные миграции: только добавляем, ничего не удаляем."""
    # оба фоновых процесса стартуют одновременно — без лока CREATE TABLE может упасть
    curs.execute("SELECT pg_advisory_xact_lock(31698001);")
    curs.execute("""
        CREATE TABLE IF NOT EXISTS pushkin_periods (
            show_id BIGINT,
            event_id BIGINT,
            organization_id BIGINT,
            place_id BIGINT,
            place_name TEXT,
            city TEXT,
            tz TEXT,
            start_ms BIGINT,
            end_ms BIGINT
        );
    """)
    curs.execute("CREATE INDEX IF NOT EXISTS pushkin_periods_show_idx ON pushkin_periods (show_id);")
    curs.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS validation TEXT;")
    curs.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS validation_reason TEXT;")
    curs.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS client_ip TEXT;")
    # момент первого запроса к оператору и подпись банка из ответа ACCEPTED
    curs.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS validation_started BIGINT;")
    curs.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS validation_signature TEXT;")


def fetch_all_events(url: str, params: dict, timeout) -> list:
    """Все страницы /pushkinsCardEvents. Неполный ответ -> исключение, а не частичные данные."""
    events, offset = [], 0
    while True:
        response = requests.get(url, params={**params, "limit": 100, "offset": offset}, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        page = data["events"]
        events.extend(page)
        offset += len(page)
        if not page or offset >= data["total"]:
            break
    if len(events) < data["total"]:
        raise RuntimeError(f"pushkinsCardEvents: получено {len(events)} из {data['total']}")
    return events


def event_periods(event: dict) -> list[tuple]:
    """(place_id, place_name, city, tz, start_ms, end_ms) по каждому периоду показа площадки."""
    places = event.get("places") or []
    rows = []
    for seance in event.get("seances") or []:
        idx = seance.get("placeIndex", 0)
        if idx >= len(places):
            continue
        p = places[idx]
        locale = p.get("locale") or {}
        rows.append((p["_id"], p.get("name"), locale.get("name"), locale.get("timezone") or DEFAULT_TZ,
                     seance["start"], seance["end"]))
    return rows


def _session_ms(date: str, time_: str, tz: str) -> int:
    dt = datetime.datetime.strptime(f"{date} {time_}", "%Y-%m-%d %H:%M")
    return int(dt.replace(tzinfo=ZoneInfo(tz)).timestamp() * 1000)


def find_event(curs, performance_id: int) -> dict | None:
    """
    Событие PRO.Культура, по которому можно продать этот сеанс, или None.
    Сверяются: фильм, город/площадка кинотеатра, время сеанса в периоде показа.
    """
    curs.execute(
        """SELECT p.date, p.time, c.city, c.name, pp.event_id, pp.organization_id,
                  pp.place_id, pp.place_name, pp.tz, pp.start_ms, pp.end_ms
           FROM performance p
           JOIN cinemas c ON c.building_id = p.building_id
           JOIN pushkin_periods pp ON pp.show_id = p.show_id AND pp.city = c.city
           WHERE p.performance_id = %s""",
        (performance_id,),
    )
    candidates = {}
    for date, time_, _, cinema_name, event_id, org_id, place_id, place_name, tz, start_ms, end_ms in curs.fetchall():
        if start_ms <= _session_ms(date, time_, tz) <= end_ms:
            candidates[(event_id, place_id)] = {
                "event_id": event_id, "organization_id": org_id, "place_id": place_id,
                "place_name": place_name or "", "cinema_name": cinema_name or "",
            }
    found = list(candidates.values())
    if len(found) > 1:
        # в городе несколько наших площадок — берём ту, чьё название совпадает с кинотеатром
        found = [f for f in found if f["cinema_name"].lower() in f["place_name"].lower()]
    return found[0] if len(found) == 1 else None


def buyer_hash(surname: str, name: str, patronymic: str | None) -> str:
    """SHA-512 от ФИО: фамилия+имя+отчество слитно, нижний регистр, только [а-яё]."""
    fio = f"{surname or ''}{name or ''}{patronymic or ''}".lower()
    fio = re.sub(r"[^а-яё]", "", fio)
    return hashlib.sha512(fio.encode("utf-8")).hexdigest()


def session_timestamp(date: str, time_: str, tz: str = DEFAULT_TZ) -> str:
    """Начало сеанса, UNIX timestamp в секундах (10 цифр)."""
    return str(_session_ms(date, time_, tz) // 1000)


DECLINE_REASONS = {
    "PERSONAL_DATA": "ФИО покупателя не совпадает с ФИО держателя карты. "
                     "Укажите ФИО строго как в паспорте, включая букву «Ё»",
    "EVENT": "проблема с параметрами мероприятия",
    "MULTISESSION": "по Пушкинской карте можно купить только один билет на сеанс",
    "PRICE": "некорректная стоимость билета",
    "SESSION_TIME": "сеанс не входит в период участия фильма в программе",
    "MCC": "мероприятие не соответствует терминалу оплаты",
    "NOT_EQUAL_PRICE": "стоимость билета не совпадает с суммой списания",
    "OTHER": "банк-оператор отказал в выдаче билета",
}

# Первые 6 цифр Пушкинских карт (ЮKassa отдаёт только first6, BIN карты — 8 цифр):
# 220024xx — ВТБ (22002482/83/84), 220077xx — Почта Банк (22007708/09/11).
# Отсекает явно чужие карты сразу; окончательно карту проверяет сервис ВТБ.
PUSHKIN_CARD_FIRST6 = ("220024", "220077")


def is_foreign_card(first6: str | None) -> bool:
    """True — карта точно не Пушкинская. Нет данных о карте — решает сервис ВТБ."""
    return bool(first6) and not str(first6).startswith(PUSHKIN_CARD_FIRST6)


# Сертификат pushkin.api.vtb.ru выдан УЦ Минцифры («Russian Trusted Root CA»),
# которого нет в стандартном наборе Python. Используется только для запросов в ВТБ.
# Источник: https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt
# SHA-256: D2:6D:2D:02:31:B7:C3:9F:92:CC:73:85:12:BA:54:10:35:19:E4:40:5D:68:B5:BD:70:3E:97:88:CA:8E:CF:31
VTB_CA_FILE = str(Path(__file__).parent / "deploy" / "certs" / "russian_trusted_root_ca.pem")

# сервис ВТБ требует браузерный User-Agent
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0"


def validate(url: str, token: str, timeout, *, buyer: str, term_inst_id: str, rrn: str, price: str,
             event_id, place_id, organization_id, event_session_timestamp: str,
             client_ip: str | None) -> tuple[str, str, str | None]:
    """
    Метод tickets/check сервиса оператора (спецификация ВТБ v3.0 от 25.04.2026).
    Возвращает (verdict, описание, signatureData):
      ACCEPTED — билет можно выдавать, signatureData — подпись банка;
      DECLINED — выдача запрещена, нужна отмена покупки;
      WAIT     — HTTP 425, транзакция ещё не дошла до банка, повторить позже;
      ERROR    — ответа нет (сеть, 400/401/500): билет не выдаём, повторим позже.
    """
    if not (url and token and term_inst_id):
        return "ERROR", "не настроены VALIDATION_URL / POCHTA_BANK_TOKEN / PUSHKIN_TERM_INST_ID", None
    body = {
        "buyer": buyer,
        "termInstId": str(term_inst_id),
        "rrn": str(rrn),
        "price": price,
        "eventId": str(event_id),
        "placeId": str(place_id),
        "organizationId": str(organization_id),
        "eventSessionTimestamp": event_session_timestamp,
        "clientBuyIpAddress": client_ip or "0.0.0.0",
    }
    auth = token if token.startswith("Bearer ") else f"Bearer {token}"
    try:
        response = requests.post(url, headers={"Authorization": auth, "User-Agent": USER_AGENT},
                                 params={"online": "false"}, json=body, timeout=timeout,
                                 verify=VTB_CA_FILE)
    except Exception as e:
        return "ERROR", f"нет связи с сервисом оператора: {e}", None
    if response.status_code == 425:
        return "WAIT", f"транзакция ещё не поступила к оператору (425): {response.text[:200]}", None
    if response.status_code != 200:
        return "ERROR", f"HTTP {response.status_code}: {response.text[:500]}", None
    try:
        resp = response.json()
    except ValueError:
        return "ERROR", f"не JSON: {response.text[:500]}", None
    result = resp.get("result")
    if result == "ACCEPTED":
        return "ACCEPTED", "", resp.get("signatureData")
    if result == "DECLINED":
        reason = resp.get("reason") or "OTHER"
        return "DECLINED", DECLINE_REASONS.get(reason, f"отказ оператора ({reason})"), None
    return "ERROR", f"неожиданный ответ: {str(resp)[:500]}", None
