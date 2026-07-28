"""
Локальное формирование XML-отчётов eKinobilet из готового orders_merged.json.

По тому же принципу, что и send_xml_to_ekinobilet() в base_requests.py,
НО без отправки: только собирает и сохраняет XML-файлы на диск.
XML создаётся для ВСЕХ заказов (статус не учитывается).

Источник данных — УЖЕ сгенерированный orders_merged.json (повторно не пересобираем).

Поля XML и откуда берутся:
  showroom / section  <- rec["showroom"]        (есть)
  seans_date          <- rec["seans date"]      (есть)
  place_x / place_y   <- rec["place"] / ["row"] (есть)
  price               <- rec["price"]           (есть)
  form.payment_id     <- rec["rrn"]             (есть)
  org_id              <- rec["org_id"]          (дописать из БД: cinemas.fond_kino_id)
  pu_number           <- rec["pu_number"]       (дописать из БД: show.pu_number)
  seans_title         <- rec["seans_title"]     (дописать из БД: show.name)
  event_id            <- rec["event_id"]        (дописать из БД: show.id_procult)
Если поля ещё нет в записи — подставляется PLACEHOLDER.

Запуск:
    python orders_report.py

Зависимостей нет — только стандартная библиотека.
"""

import datetime
import json
import os
import xml.etree.ElementTree as ET

# --------------------------------------------------------------------------- #
BASE = os.path.dirname(os.path.abspath(__file__))
MERGED_JSON = os.path.join(BASE, "orders_merged.json")
XML_DIR = os.path.join(BASE, "xml_files")

# Значение для ещё не заполненных полей.
PLACEHOLDER = ""  # TODO: заполнить из БД (org_id, pu_number, seans_title, event_id)

# Константы формы (из оригинального send_xml_to_ekinobilet)
XML_VER = "3.2.0"
XML_FORMAT = "2D"
TICKET_TYPE = "Основной"
TERMINAL_ID = "26485891"
TERMINAL_OWNER = "5402052576"


# --------------------------------------------------------------------------- #
def attr(value):
    """None -> '' , иначе строка (для атрибутов XML)."""
    return "" if value is None else str(value)


def seans_date_xml(value):
    """'2026-01-07 11:10:00' -> '20260107 11:10' (дата без '-', время HH:MM)."""
    if not value:
        return ""
    parts = str(value).split(" ")
    day = parts[0].replace("-", "")
    tm = parts[1][:5] if len(parts) > 1 else ""
    return f"{day} {tm}".strip()


def build_seans_xml(rec, sale_date):
    """Собрать <seans>/<form> для одного заказа. Возвращает bytes."""
    hall_name = rec.get("showroom") or ""

    root_el = ET.Element("seans")
    root_el.set("ver", XML_VER)
    root_el.set("org_id", attr(rec.get("org_id", PLACEHOLDER)))
    root_el.set("showroom", attr(hall_name))
    root_el.set("seans_date", seans_date_xml(rec.get("seans date")))
    root_el.set("pu_number", attr(rec.get("pu_number", PLACEHOLDER)))
    root_el.set("format", XML_FORMAT)
    root_el.set("seans_title", attr(rec.get("seans_title", PLACEHOLDER)))
    root_el.set("event_id", attr(rec.get("event_id", PLACEHOLDER)))

    form = ET.SubElement(root_el, "form")
    form.set("place_x", attr(rec.get("place")))
    form.set("place_y", attr(rec.get("row")))
    form.set("section", attr(hall_name))
    form.set("price", attr(rec.get("price")))
    form.set("discount", "0")
    form.set("ticket_type", TICKET_TYPE)
    form.set("sale_date", sale_date)
    form.set("subscription", "false")
    form.set("online", "true")
    form.set("webtax_included", "false")
    form.set("payment_type", "1")
    form.set("payment_id", attr(rec.get("rrn")))
    form.set("terminal_id", TERMINAL_ID)
    form.set("terminal_owner", TERMINAL_OWNER)

    return ET.tostring(root_el, encoding="utf-8")


def write_xml_files(data):
    """По одному XML-файлу на заказ в XML_DIR. Возвращает количество."""
    os.makedirs(XML_DIR, exist_ok=True)

    now_plus7 = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=7)
    sale_date = now_plus7.strftime("%Y%m%d %H:%M:%S")
    doc_date = now_plus7.strftime("%Y%m%d_%H%M%S")

    count = 0
    for rec in data:
        order_id = rec.get("order_id")
        fond_kino_id = rec.get("org_id") or "NA"
        xml_data = build_seans_xml(rec, sale_date)
        # order_id в имени, чтобы файлы в пакете не перезаписывали друг друга
        fname = f"ekb_{fond_kino_id}_{order_id}_{doc_date}145.xml"
        with open(os.path.join(XML_DIR, fname), "wb") as f:
            f.write(xml_data)
        count += 1
    return count


# --------------------------------------------------------------------------- #
def main():
    with open(MERGED_JSON, encoding="utf-8") as f:
        data = json.load(f)

    count = write_xml_files(data)

    print(f"Заказов в JSON: {len(data)}")
    print(f"Создано XML-файлов: {count}")
    print(f"Папка XML: {XML_DIR}")

    missing = [
        k for k in ("org_id", "pu_number", "seans_title", "event_id")
        if any(not r.get(k) for r in data)
    ]
    if missing:
        print("ВНИМАНИЕ: не у всех заказов заполнены поля из БД:", ", ".join(missing))


if __name__ == "__main__":
    main()
