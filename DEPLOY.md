# Деплой бота «Пушкинская карта»

Сервер: VDSina `132.243.190.168` (Москва, Ubuntu 24.04), рядом с другими проектами.
Домен бота: **kino.finance-tracker-api.ru** (DNS — у AdminVPS, регистратор REG.RU).

Сервер **обязательно с российским IP**: ВТБ, PRO.Культура и билетная система кинотеатров
не отвечают на зарубежные адреса.

## Как устроено

Всё в Docker, проект `kino` (`docker-compose.yaml`):

| Контейнер | Что делает |
|---|---|
| `db` | PostgreSQL 17, наружу не открыт; схема из `deploy/schema.sql` применяется сама при первом запуске |
| `db-backup` | ежедневный дамп базы (хранит 7 дней / 4 недели / 6 месяцев) |
| `bot` | бот MAX: вебхук + синхронизация расписания и реестра + обработка платежей |
| `send` | отправка сообщений в MAX по запросу сайта (только внутри проекта) |
| `web` | сайт выбора мест (Django) |

HTTPS и маршрутизацию делает общий `edge-nginx` (nginx-proxy + acme-companion) сервера:
`https://kino.finance-tracker-api.ru/webhook` → `bot`, остальное → `web`. Сертификат выпускается сам.

Память: весь проект ~300 МБ.

## 1. Подготовка сервера (один раз)

**Подкачка 2 ГБ** — страховка по памяти для всех проектов:

```bash
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

**Закрыть открытую базу maxfrilance** — сейчас она доступна из интернета (`0.0.0.0:55432`).
В compose-файле MaxFrilance заменить `"55432:5432"` на `"127.0.0.1:55432:5432"`
(или убрать `ports`, если снаружи к ней не ходят) и сделать `docker compose up -d`.

**SSH только по ключу** (ключ уже должен быть в `~/.ssh/authorized_keys`):

```bash
sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl reload ssh
```

## 2. Код и настройки

```bash
git clone <адрес репозитория> /root/kino
cd /root/kino
```

Положить боевой `.env` (готовый лежит у разработчика в `_local/env.prod`):

```bash
# с компьютера разработчика:
scp _local/env.prod root@132.243.190.168:/root/kino/.env
# на сервере:
chmod 600 /root/kino/.env
```

В `.env` вписать `PROXY_NETWORK` — сеть, в которой работает `edge-nginx`:

```bash
docker inspect edge-nginx --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}'
```

Проверить, что все ключи **новые** (старые утекли вместе с прошлым хостингом):
ЮKassa, токен бота MAX, ekinobilet, Сбер.

⚠️ Docker берёт переменные из окружения shell раньше, чем из `.env`.
Если в shell задан `POSTGRES_PASSWORD` от другого проекта — база получит чужой пароль.
Перед запуском: `unset POSTGRES_PASSWORD`.

## 3. Запуск

```bash
cd /root/kino
docker compose up -d --build
docker compose ps
docker compose logs -f bot
```

## 4. Домен

У AdminVPS (там DNS-зона `finance-tracker-api.ru`) поменять A-запись:

```
kino.finance-tracker-api.ru  A  132.243.190.168
```

Сейчас она указывает на старый сервер `46.173.28.3`. После обновления DNS (от минут до пары часов)
acme-companion сам выпустит сертификат, бот при старте сам перерегистрирует вебхук MAX.
Если бот стартовал раньше, чем обновился DNS: `docker compose restart bot`.

## 5. Проверка

```bash
docker compose exec bot python check_vtb_service.py   # ВТБ: ждём «✅ Адрес и токен рабочие»
```

- В боте `/start` → город → дата → фильмы с кнопками сеансов.
- Кнопка сеанса открывает схему зала.
- Админу в MAX не приходят сообщения об ошибках.

## Обновление кода

```bash
cd /root/kino && git pull && docker compose up -d --build
```

## Бэкапы

```bash
docker compose exec db-backup ls -lh /backups/daily      # список
docker compose cp db-backup:/backups/daily/. ./backups/   # забрать на сервер
```

Лучше периодически забирать копии и за пределы сервера.

## Перед запуском продаж (ЮKassa)

- двухстадийная оплата (холдирование) включена;
- терминал ограничен BIN Пушкинских карт 22002482, 22002483, 22002484.

Без этого банк не сможет одобрять покупки — они будут отменяться через 5 минут.

## Пушкинская карта: как устроена продажа

1. Сайт создаёт платёж ЮKassa с холдированием (деньги замораживаются).
2. Бот (`base_requests.check_payment_status`) запрашивает одобрение ВТБ
   (`pushkin.validate`, спецификация — `docs/vtb_spec_tickets_check_v3.pdf`).
3. `ACCEPTED` → списание, PDF-билет, отчёт в ЕАИС. `DECLINED` → отмена платежа.
4. Токен ВТБ действует год; бот напоминает админу за 30/14/7/3/1 дней
   (`POCHTA_BANK_TOKEN_EXPIRES`). Новый токен: PRO.Культура.РФ → «Учреждение» → «Пушкинская карта».
