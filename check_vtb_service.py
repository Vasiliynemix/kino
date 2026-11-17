"""
Проверка связи с сервисом оператора «Пушкинской карты» (ВТБ, метод tickets/check).

Запускать на сервере бота (нужен российский IP):  python check_vtb_service.py

Отправляет запрос с токеном, но БЕЗ данных покупки — это не проверка билета,
банк просто отвечает ошибкой валидации. Ожидаемые ответы:
  HTTP 400        — адрес и токен рабочие, всё в порядке;
  HTTP 401        — токен не принят (просрочен или не тот);
  таймаут/ошибка  — банк недоступен с этого IP (зарубежный сервер, VPN) или сеть.
"""
import requests

import pushkin
from config import pochta_bank_token, validation_url

if not (validation_url and pochta_bank_token):
    raise SystemExit("В .env не заданы VALIDATION_URL или POCHTA_BANK_TOKEN")

try:
    country = requests.get("https://ipinfo.io/country", timeout=10).text.strip()
except Exception:
    country = "?"
print(f"Внешний IP сервера: страна {country}")

auth = pochta_bank_token if pochta_bank_token.startswith("Bearer ") else f"Bearer {pochta_bank_token}"
try:
    r = requests.post(validation_url, params={"online": "false"}, json={},
                      headers={"Authorization": auth, "User-Agent": pushkin.USER_AGENT}, timeout=30,
                      verify=pushkin.VTB_CA_FILE)
except Exception as e:
    raise SystemExit(f"❌ Банк не ответил: {e}\n"
                     f"   Если страна не RU — сервер или VPN за границей, банк таких не обслуживает.")

print(f"HTTP {r.status_code}: {r.text[:300]}")
if r.status_code == 400:
    print("✅ Адрес и токен рабочие")
elif r.status_code == 401:
    print("❌ Токен не принят: проверьте POCHTA_BANK_TOKEN (получить новый — PRO.Культура.РФ, «Учреждение»)")
else:
    print("⚠️ Неожиданный ответ — пришлите его разработчику")
