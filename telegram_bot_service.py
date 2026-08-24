"""
Бэкенд для варианта 1 (личка бота, без общих групп) — задачи #49/#50/#51,
решение от 10.08.2026: "клиент добавленный в группу заявки видел только
информацию касаемую только его" -> вывод: общей группы не будет вообще,
каждый (и клиент, и компания) общается с ботом лично.

Что делает:
1. HTTP-эндпоинт POST /api/mass-request — сайт (index.html, кнопка
   "Оплатить и отправить запрос") шлёт сюда данные заявки ПОСЛЕ успешной
   оплаты. Сохраняет заявку локально (bot_state.json) и отдаёт request_id.
   Дальше сайт открывает `t.me/<бот>?start=req_<request_id>` — у клиента
   в Telegram появляется кнопка "Старт".
2. Поллинг Telegram (getUpdates) в фоне:
   - /start req_<id> — клиент нажал кнопку из п.1. Бот запоминает его
     chat_id за этой заявкой, подтверждает клиенту, и рассылает заявку
     ЛИЧНЫМИ сообщениями всем компаниям подходящего направления, у
     которых уже есть зарегistрированный chat_id (см. онбординг ниже).
   - /start без параметра (или с чем угодно ещё) — если username
     отправителя совпадает с полем telegram у какой-то компании в
     Google-таблице (регистр не важен) — считаем это ОНБОРДИНГОМ
     компании: запоминаем её chat_id, подтверждаем. Иначе — обычное
     приветствие.
   - Любое другое сообщение от уже онбордившейся компании — пересылаем
     клиенту той заявки, на которую компанию последней уведомляли
     (упрощение для MVP: если компания параллельно ведёт несколько
     заявок, точного роутинга ответа нет — см. "Известные ограничения"
     ниже).

Хранилище — bot_state.json (локальный файл на VPS, НЕ в Google Sheets —
это оперативные данные бота: chat_id клиентов/компаний, статусы заявок,
не нужны в основной базе компаний). В git не попадает (.gitignore).

Настройка (bot_config.env, тоже НЕ в git, создать вручную рядом):
    BOT_TOKEN=<токен от @BotFather>
    BOT_USERNAME=<username бота без @>
    PROXY_URL=<опционально, см. ниже>
    ADMIN_CHAT_ID=<опционально, см. ниже>
    ADMIN_GROUP_CHAT_ID=<опционально, см. ниже>

PROXY_URL — обход блокировки api.telegram.org с российских VPS (см.
PROJECT_STATE.md, раздел "Telegram-бот не достучаться до api.telegram.org
с VPS", 12.08.2026: curl -4 и -6 до api.telegram.org с VPS оба висли до
таймаута). Если задан — все запросы к Telegram Bot API (sendMessage,
getUpdates) идут через этот прокси вместо прямого соединения. Формат —
полный URL с логином/паролем, если есть:
    http://user:pass@host:port
    socks5://user:pass@host:port
Для socks5:// на сервере дополнительно нужен пакет PySocks:
    pip3 install --break-system-packages "requests[socks]"
Если PROXY_URL не задан — поведение как раньше (прямое соединение).

ADMIN_CHAT_ID — личный chat_id владельца в Telegram (12.08.2026: без
этого владелец вообще не видел, что происходит в боте — ни новых заявок,
ни ответов компаний, только вручную через bot_state.json по SSH). Если
задан — копия каждого ключевого события (новая заявка, подтверждение
клиентом, онбординг компании, ответ компании клиенту) дублируется в
личку владельцу через notify_admin(). Если не задан — уведомления просто
не отправляются, остальной функционал не страдает.

ADMIN_GROUP_CHAT_ID — то же самое, но в рабочую группу владельца вместо
(или вместе с) личного чата — можно задать оба сразу, уйдёт в оба места.
chat_id группы узнать через сам бот: написать любое сообщение (лучше
команду вроде /start) в группу, где бот уже состоит участником, и
посмотреть в `journalctl -u telegram-bot -f` строку "[bot] сообщение из
chat_id=...", там же будет type=group/supergroup и title группы.

Запуск (для разработки):
    python3 telegram_bot_service.py
В проде — через systemd, см. инструкцию, которую Claude даёт в чате
(деплой на VPS 89.108.70.185, где уже стоит nginx для сайта).

Известные ограничения (Phase 1, осознанно упрощено):
- Бот не может писать ПЕРВЫМ ни клиенту, ни компании, пока они сами не
  нажали /start у бота — это ограничение самого Telegram, не наше.
  Значит компании нужно один раз онбордить (прислать им ссылку на бота
  и попросить нажать Старт) ДО того как первая заявка на их направление
  придёт — иначе они её не получат, просто выпадут из рассылки молча.
- Rate limits Telegram Bot API не обрабатываются (send с retry) — на
  небольшом объёме заявок не критично, добавить позже при росте.

Точная маршрутизация ответов компаний -> клиентам (14.08.2026, было
исправлено — раньше роутилось только по "последняя заявка для этого
chat_id", что путалось при 2+ параллельных заявках у одной компании).
Теперь: при рассылке заявки компании в тексте сообщения прямо просим её
отвечать РЕПЛАЕМ на это сообщение; message_id сохраняется в
state["message_routes"][f"{chat_id}:{message_id}"] -> {request_id,
company_name}; если компания действительно ответила реплаем — маршрут
однозначный. Если ответила обычным сообщением (без реплая) — используется
запасной вариант "последняя известная заявка" (как раньше), а самой
компании отдельно уходит предупреждение, что в следующий раз лучше
отвечать реплаем. Клиенту в любом случае видно ИМЯ компании в тексте
пересланного ответа (раньше было безлико "Ответ от компании").
"""
import collections
import functools
import json
import logging
import os
import re
import smtplib
import sys
import threading
import time
from email.mime.text import MIMEText

import requests
from flask import Flask, jsonify, request

# T-72 (21.08.2026): раньше здесь были прямые import gspread + Credentials
# для собственного подключения к таблице (см. get_companies() ниже) —
# теперь через общий sheets_client.py (connect_sheets/SHEET_ID), тот же
# модуль уже используют company_agent.py и update_site.py.
from sheets_client import SHEET_ID, connect_sheets

# 12.08.2026: под systemd stdout не подключён к терминалу, поэтому Python
# по умолчанию блочно буферизует вывод — сообщения могут подолгу не
# доходить до journalctl, из-за чего живая диагностика вводила в
# заблуждение (казалось, что поток вообще ничего не делает). Включаем
# построчную буферизацию, чтобы лог был виден сразу же.
sys.stdout.reconfigure(line_buffering=True)

# T-73 (21.08.2026): раньше все сообщения шли через голый print() —
# в systemd journal всё летело одним потоком без уровней, нельзя было
# штатно отфильтровать шум от реальных ошибок (poll_loop логировал КАЖДЫЙ
# цикл опроса Telegram — "запрашиваю getUpdates"/"getUpdates ответил" —
# это заливало журнал десятками строк в минуту, за которыми терялись
# редкие настоящие ошибки). Теперь: INFO — по умолчанию видно (старт,
# входящие сообщения, ошибки отправки), DEBUG — только если явно включить
# (подробности каждого цикла поллинга), поднять уровень можно без правки
# кода через переменную окружения LOG_LEVEL (например, `LOG_LEVEL=DEBUG
# systemctl edit telegram-bot` для временной диагностики).
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("bot")

BOT_CONFIG = {}
with open("bot_config.env") as f:
    for line in f:
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.strip().split("=", 1)
            BOT_CONFIG[k] = v
BOT_TOKEN = BOT_CONFIG["BOT_TOKEN"]
BOT_USERNAME = BOT_CONFIG["BOT_USERNAME"]
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Обход блокировки api.telegram.org с VPS (см. docstring выше и
# PROJECT_STATE.md) — если PROXY_URL задан в bot_config.env, все запросы
# к Telegram API идут через него.
PROXY_URL = BOT_CONFIG.get("PROXY_URL", "").strip()
PROXIES = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None

# 12.08.2026: у владельца не было НИКАКОЙ видимости происходящего в боте
# — ни новых заявок, ни того, кто с кем связался, ни ответов компаний,
# только ручной просмотр bot_state.json по SSH. ADMIN_CHAT_ID (опционально,
# в bot_config.env) — личный chat_id владельца в Telegram, куда дублируются
# копии ключевых событий. Получить свой chat_id просто: написать боту
# что угодно, потом посмотреть в getUpdates поле message.from.id (или
# @userinfobot). Если не задан — уведомления просто не отправляются,
# остальной функционал не страдает.
ADMIN_CHAT_ID = BOT_CONFIG.get("ADMIN_CHAT_ID", "").strip()
# 12.08.2026: владелец попросил дублировать переписку клиент<->компания
# в свою рабочую группу (не общую с клиентами/компаниями — это отдельная
# закрытая группа только для владельца, ссылка t.me/+QSlupk86OJBmYTky).
# chat_id группы отрицательный (или -100... для супергрупп) — узнаётся
# через диагностический print выше (написать что-нибудь в группу, глянуть
# journalctl). Можно задать одновременно с ADMIN_CHAT_ID — уйдёт в оба.
ADMIN_GROUP_CHAT_ID = BOT_CONFIG.get("ADMIN_GROUP_CHAT_ID", "").strip()

# 14.08.2026: помимо Telegram-уведомлений (ADMIN_CHAT_ID/ADMIN_GROUP_CHAT_ID
# выше), владелец попросил дублировать те же события на почту — на случай,
# если не смотрит в телефон, а почта проверяется чаще/есть уведомления на
# рабочем месте. Переиспользуем тот же mail_config.env, что уже настроен
# для send_onboarding_emails.py (тот же SMTP-аккаунт, дополнительно не
# нужно ничего заводить) — просто нужно скопировать этот файл на VPS
# рядом с bot_config.env (он в .gitignore, через git не попадёт). Если
# mail_config.env на VPS нет — email-уведомления просто не отправляются,
# Telegram-уведомления и весь остальной функционал бота не страдают
# (тот же принцип отказоустойчивости, что и у ADMIN_CHAT_ID).
MAIL_CONFIG = {}
if os.path.exists("mail_config.env"):
    with open("mail_config.env") as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                MAIL_CONFIG[k.strip()] = v.strip()


def send_admin_email(subject, body):
    if not MAIL_CONFIG:
        return
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        from_addr = MAIL_CONFIG["SMTP_USER"]
        to_addr = MAIL_CONFIG.get("ADMIN_EMAIL", "").strip() or from_addr
        msg["From"] = f"{MAIL_CONFIG.get('FROM_NAME', from_addr)} <{from_addr}>"
        msg["To"] = to_addr
        with smtplib.SMTP(MAIL_CONFIG["SMTP_HOST"], int(MAIL_CONFIG["SMTP_PORT"]), timeout=10) as server:
            server.starttls()
            server.login(from_addr, MAIL_CONFIG["SMTP_PASSWORD"])
            server.sendmail(from_addr, [to_addr], msg.as_string())
    except Exception as e:
        # Сбой почты никогда не должен ронять сам бот — та же осторожность,
        # что и у tg_send() (try/except вокруг сетевого похода).
        logger.warning(f"не удалось отправить email-уведомление: {e}")


def notify_admin(text):
    for dest in (ADMIN_CHAT_ID, ADMIN_GROUP_CHAT_ID):
        if dest:
            tg_send(dest, f"🔔 {text}")
    send_admin_email("MyAvtoAgregator — уведомление", text)

# SHEET_ID импортирован из sheets_client (T-72) — см. импорты вверху файла.

STATE_FILE = "bot_state.json"
_state_lock = threading.Lock()

app = Flask(__name__)


# T-21 (21.08.2026): у /api/mass-request и /api/review не было вообще
# никакой защиты от спама/накрутки — форма шлёт JSON без токена, скрипт
# может дёргать её сколько угодно раз в секунду, заваливая admin-уведомления
# и (для mass-request) реальные компании. По решению пользователя — без
# внешних сервисов (reCAPTCHA и т.п., это отдельная настройка с ключами),
# два простых и бесплатных барьера:
#   1) rate-limit по IP — не больше N запросов на эндпоинт за окно времени;
#   2) honeypot — скрытое от людей поле в форме (см. index.html, класс
#      .hp-field), которое видят только боты, читающие HTML целиком.
#      Если оно заполнено — заявка тихо отбрасывается, но клиенту всё равно
#      отвечаем "ok" (чтобы не подсказывать боту, что его вычислили).
def get_client_ip():
    # Flask за nginx видит remote_addr = 127.0.0.1 для всех запросов, если
    # nginx не прокидывает реальный IP явно. Смотрим X-Forwarded-For первым
    # (стандартный заголовок реверс-прокси), remote_addr — запасной вариант.
    # Проверить на VPS: `grep X-Forwarded-For /etc/nginx/sites-enabled/*`.
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or "unknown"


_rate_lock = threading.Lock()
_rate_buckets = collections.defaultdict(list)  # (endpoint, ip) -> [timestamps]


def rate_limit(max_calls, window_seconds):
    """Не больше max_calls запросов с одного IP на этот эндпоинт за window_seconds."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            ip = get_client_ip()
            key = (fn.__name__, ip)
            now = time.time()
            with _rate_lock:
                bucket = _rate_buckets[key]
                cutoff = now - window_seconds
                while bucket and bucket[0] < cutoff:
                    bucket.pop(0)
                if len(bucket) >= max_calls:
                    return jsonify({"error": "too many requests, попробуйте позже"}), 429
                bucket.append(now)
            return fn(*args, **kwargs)
        return wrapped
    return decorator


def is_honeypot_filled(data):
    return bool((data.get("website") or "").strip())


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"requests": {}, "companies": {}, "last_update_id": 0}


def save_state(state):
    # T-22 (21.08.2026): раньше писали прямо в STATE_FILE — падение процесса
    # (OOM, kill -9, рестарт деплоем) ровно в момент записи оставляло файл
    # обрезанным наполовину, следующий load_state() падал на json.load() и
    # терял весь накопленный онбординг компаний и заявок. Тот же паттерн,
    # что уже применён для visits.json: пишем во временный файл рядом и
    # атомарно подменяем — os.replace() на одной файловой системе никогда
    # не оставляет STATE_FILE в промежуточном состоянии.
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)


def tg_send(chat_id, text):
    # 14.08.2026: раньше результат send всегда отбрасывался. Теперь
    # возвращаем распарсенный ответ Telegram API (или None при ошибке) —
    # нужен message_id отправленного сообщения, чтобы потом уметь понять,
    # на какое именно сообщение компания ответила реплаем (см. handle_reply
    # и раздел "Точная маршрутизация ответов компаний" в PROJECT_STATE.md).
    try:
        r = requests.post(f"{API}/sendMessage", json={"chat_id": chat_id, "text": text}, timeout=10, proxies=PROXIES)
        return r.json()
    except Exception as e:
        logger.warning(f"не удалось отправить сообщение {chat_id}: {e}")
        return None


# 14.08.2026: без кэша каждый /start клиента заново ходил в Google Sheets
# (см. PROJECT_STATE.md, раздел про нагрузку при всплеске заявок) — при
# нескольких одновременных клиентах это сериализовало обработку в
# poll_loop() (все под одним _state_lock) и копило задержку. Кэш на 90
# секунд — компании обновляются в таблице не поминутно, свежесть не
# критична, а нагрузка на Sheets API и время ответа сильно падают.
_companies_cache = {"data": None, "ts": 0}
_companies_cache_lock = threading.Lock()
COMPANIES_CACHE_TTL = 90


def get_companies():
    """Читаем telegram/directions компаний прямо из Google Sheets —
    та же таблица, что использует company_agent.py/update_site.py, тут
    отдельной копии данных не держим. Результат кэшируется на
    COMPANIES_CACHE_TTL секунд (см. комментарий выше)."""
    with _companies_cache_lock:
        if _companies_cache["data"] is not None and time.time() - _companies_cache["ts"] < COMPANIES_CACHE_TTL:
            return _companies_cache["data"]

    # T-72 (21.08.2026): connect_sheets() из sheets_client.py делает то же
    # самое (Credentials + gspread.authorize + open_by_key(...).sheet1),
    # что раньше было продублировано прямо тут.
    ws = connect_sheets()
    rows = ws.get_all_values()[1:]
    companies = []
    for row in rows:
        name = row[1].strip() if len(row) > 1 else ""
        telegram = row[9].strip() if len(row) > 9 else ""
        directions = row[7].strip() if len(row) > 7 else ""
        if name and telegram:
            companies.append({
                "name": name,
                "telegram": telegram.lstrip("@").lower(),
                "directions": [d.strip() for d in directions.split(",") if d.strip()],
            })

    with _companies_cache_lock:
        _companies_cache["data"] = companies
        _companies_cache["ts"] = time.time()
    return companies


@app.route("/api/mass-request", methods=["POST"])
@rate_limit(max_calls=5, window_seconds=300)
def mass_request():
    data = request.get_json(force=True) or {}
    if is_honeypot_filled(data):
        # Бот заполнил скрытое поле — тихо делаем вид, что всё ок, реальную
        # заявку не сохраняем и никого не уведомляем.
        return jsonify({"request_id": "0", "bot_username": BOT_USERNAME})
    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip()
    email = (data.get("email") or "").strip()
    direction = (data.get("direction") or "").strip()
    budget = (data.get("budget") or "").strip()
    model = (data.get("model") or "").strip()
    if not name or not phone or not direction or not email or "@" not in email:
        return jsonify({"error": "missing required fields"}), 400

    # email нужен, чтобы онлайн-касса (после подключения, см. PROJECT_STATE.md)
    # могла отправить электронный чек по 54-ФЗ. Сам вызов кассы/эквайринга
    # сюда пока не добавлен — фискализация делается на стороне платёжного
    # провайдера (CloudPayments + касса), когда реквизиты будут готовы;
    # здесь email просто сохраняется вместе с заявкой на всякий случай.
    request_id = str(int(time.time() * 1000))
    with _state_lock:
        state = load_state()
        state["requests"][request_id] = {
            "name": name, "phone": phone, "email": email, "direction": direction,
            "budget": budget, "model": model,
            "client_chat_id": None, "companies_notified": [],
            "created_at": time.time(),
        }
        save_state(state)
    notify_admin(
        f"Новая заявка #{request_id}\nИмя: {name}\nКонтакт: {phone}\nEmail: {email}\n"
        f"Направление: {direction}\n" +
        (f"Бюджет: {budget}\n" if budget else "") +
        (f"Что ищет: {model}\n" if model else "") +
        "(ещё не подтверждена — клиент должен открыть бота и нажать Старт)"
    )
    return jsonify({"request_id": request_id, "bot_username": BOT_USERNAME})


# 17.08.2026: нативные отзывы на сайте — задача пользователя: кнопка
# "Оставить отзыв" раньше вела на сторонние площадки (Яндекс.Карты, 2ГИС,
# Google), теперь отзыв создаётся прямо у нас. Хранение — отдельная вкладка
# "Отзывы" той же Google Таблицы (connect_reviews_sheet() в company_agent.py,
# та же таблица/креды, что уже использует get_companies() выше — новых
# credentials заводить не нужно). Модерация обязательна (решение
# пользователя: "с модерацией, рекомендую") — сюда пишем только статус
# "pending", публикуются на сайте только "approved"-строки, которые
# update_site.py подтягивает в карточки при следующей синхронизации.
from company_agent import connect_reviews_sheet

_reviews_lock = threading.Lock()


@app.route("/api/review", methods=["POST"])
@rate_limit(max_calls=5, window_seconds=300)
def submit_review():
    data = request.get_json(force=True) or {}
    if is_honeypot_filled(data):
        return jsonify({"status": "ok", "id": "0"})
    company_id = str(data.get("company_id") or "").strip()
    company_name = (data.get("company_name") or "").strip()
    author_name = (data.get("author_name") or "").strip()
    text = (data.get("text") or "").strip()
    contact = (data.get("contact") or "").strip()
    try:
        rating = int(data.get("rating"))
    except (TypeError, ValueError):
        rating = 0

    if not company_name or not author_name or not text or rating < 1 or rating > 5:
        return jsonify({"error": "missing or invalid fields"}), 400
    # Минимальная защита от пустого/спам-текста — тот же принцип, что и в
    # mass_request() (простая валидация полей, без внешних антиспам-сервисов).
    if len(text) < 10:
        return jsonify({"error": "text too short"}), 400
    if len(text) > 2000:
        text = text[:2000]

    review_id = str(int(time.time() * 1000))
    created_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    with _reviews_lock:
        ws = connect_reviews_sheet()
        ws.append_row([review_id, company_id, company_name, author_name, str(rating), text, "pending", created_at, contact])

    notify_admin(
        f"Новый отзыв #{review_id} на модерацию\nКомпания: {company_name}\n"
        f"Автор: {author_name}\nОценка: {rating}/5\nТекст: {text}\n"
        "Модерация: python3 moderate_reviews.py на сервере."
    )
    return jsonify({"status": "ok", "id": review_id})


# Счётчик посетителей — 18.08.2026, по запросу пользователя (T-60 в
# TASKS.md). Простой хит-каунтер: каждый POST /api/visit увеличивает число
# на 1 и возвращает текущее значение, index.html дёргает его раз при
# каждой загрузке страницы (см. DOMContentLoaded) и подставляет в
# .stats-bar. Не дедуплицирует уникальных посетителей (это не Метрика, а
# честный простой счётчик хитов — ровно то, что просили). Хранится в
# отдельном JSON-файле, не в bot_state.json — логически другая сущность
# (не оперативное состояние бота), проще откатить/обнулить отдельно.
VISITS_FILE = "visits.json"
_visits_lock = threading.Lock()


def _load_visits():
    if os.path.exists(VISITS_FILE):
        try:
            with open(VISITS_FILE, encoding="utf-8") as f:
                return int(json.load(f).get("count", 0))
        except Exception:
            return 0
    return 0


def _save_visits(count):
    tmp = VISITS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"count": count}, f)
    os.replace(tmp, VISITS_FILE)


@app.route("/api/visit", methods=["POST"])
def register_visit():
    with _visits_lock:
        count = _load_visits() + 1
        _save_visits(count)
    return jsonify({"count": count})


@app.route("/api/visit", methods=["GET"])
def get_visits():
    return jsonify({"count": _load_visits()})


def handle_start(chat_id, username, payload, state):
    if payload.startswith("req_"):
        req_id = payload[len("req_"):]
        req = state["requests"].get(req_id)
        if not req:
            tg_send(chat_id, "Не нашёл эту заявку — возможно, ссылка устарела. Заполни форму на сайте ещё раз.")
            return
        req["client_chat_id"] = chat_id
        tg_send(chat_id, "Заявка принята! Ищу подходящие компании по направлению \"" + req["direction"] +
                "\" и рассылаю им запрос — ответы придут сюда же, каждый раз с указанием, какая именно "
                "компания ответила (если откликнется несколько — увидишь их по отдельности).")

        matched = [c for c in get_companies()
                   if req["direction"] in c["directions"] and c["telegram"] in state["companies"]]
        for c in matched:
            company_chat_id = state["companies"][c["telegram"]]
            text = (f"Новая заявка через MyAvtoAgregator.ru\n\n"
                    f"Клиент: {req['name']}\nКонтакт: {req['phone']}\n"
                    f"Направление: {req['direction']}\n" +
                    (f"Бюджет: {req['budget']}\n" if req["budget"] else "") +
                    (f"Что ищет: {req['model']}\n" if req["model"] else "") +
                    "\n❗️Отвечай РЕПЛАЕМ (в Telegram: зажать это сообщение и "
                    "выбрать \"Ответить\") именно на ЭТО сообщение — так бот "
                    "точно поймёт, к какой заявке относится твой ответ, даже "
                    "если у тебя параллельно несколько заявок.")
            resp = tg_send(company_chat_id, text)

            req["companies_notified"].append(c["telegram"])

            # 14.08.2026: точная маршрутизация ответа компании -> клиента.
            # Раньше был только "запомнить последнюю заявку для этого
            # chat_id" — если компании прилетало 2+ заявки подряд до того,
            # как она ответила на первую, вторая перезаписывала первую и
            # ответ компании мог уйти не тому клиенту. Теперь для каждого
            # отправленного сообщения запоминаем его message_id -> заявка,
            # и если компания отвечает РЕПЛАЕМ именно на него — маршрут
            # однозначный, независимо от того, сколько у неё заявок сразу.
            sent_msg_id = None
            if resp and resp.get("ok"):
                sent_msg_id = resp.get("result", {}).get("message_id")
            if sent_msg_id:
                state["message_routes"] = state.get("message_routes", {})
                state["message_routes"][f"{company_chat_id}:{sent_msg_id}"] = {
                    "request_id": req_id, "company_name": c["name"],
                }

            # Запасной вариант (если компания всё же ответит НЕ реплаем,
            # а обычным сообщением) — та же логика "последняя заявка", что
            # и раньше, но теперь с именем компании, чтобы клиент видел,
            # кто именно ответил, а не безликое "Ответ от компании".
            state["companies_last_request"] = state.get("companies_last_request", {})
            state["companies_last_request"][str(company_chat_id)] = {
                "request_id": req_id, "company_name": c["name"],
            }

        if matched:
            tg_send(chat_id, f"Заявка отправлена {len(matched)} компаниям.")
        else:
            tg_send(chat_id, "Пока не нашлось онбордившихся компаний по этому направлению — свяжемся с тобой вручную.")
        notify_admin(
            f"Заявка #{req_id} подтверждена клиентом (chat_id={chat_id}), "
            f"направление \"{req['direction']}\" — разослана {len(matched)} компаниям"
            + (f": {', '.join(c['telegram'] for c in matched)}" if matched else " (никому, нет онбордившихся)")
        )
        return

    # Не заявка клиента — пробуем онбординг компании по совпадению username
    if username:
        companies = get_companies()
        match = next((c for c in companies if c["telegram"] == username.lower()), None)
        if match:
            state["companies"][match["telegram"]] = chat_id
            tg_send(chat_id, f"Готово, {match['name']}! Теперь новые заявки по вашим направлениям будут приходить сюда.")
            notify_admin(f"Компания онбордилась: {match['name']} (@{match['telegram']}, chat_id={chat_id})")
            return

    tg_send(chat_id, "Привет! Это бот MyAvtoAgregator.ru. Если ты клиент — оформи заявку на сайте, ссылка придёт сюда автоматически.")


def handle_reply(chat_id, text, state, reply_to_message_id=None):
    """
    Пересылает сообщение компании клиенту. Два способа понять, к какой
    заявке относится ответ (14.08.2026, см. "Точная маршрутизация ответов
    компаний" в PROJECT_STATE.md):
    1. ТОЧНЫЙ: компания ответила РЕПЛАЕМ на сообщение с конкретной заявкой
       — по message_routes однозначно находим нужную заявку, даже если у
       компании сейчас несколько параллельных заявок.
    2. ЗАПАСНОЙ: компания ответила обычным сообщением (без реплая) —
       берём "последнюю заявку, о которой ей сообщали", как раньше. Может
       ошибиться, если заявок несколько подряд — в этом случае дополнительно
       предупреждаем САМУ КОМПАНИЮ, чтобы в следующий раз использовала реплай.
    """
    request_id, company_name, matched_by_reply = None, "", False

    if reply_to_message_id:
        route = state.get("message_routes", {}).get(f"{chat_id}:{reply_to_message_id}")
        if route:
            request_id = route.get("request_id")
            company_name = route.get("company_name", "")
            matched_by_reply = True

    if not request_id:
        last = state.get("companies_last_request", {}).get(str(chat_id))
        if isinstance(last, dict):
            request_id = last.get("request_id")
            company_name = last.get("company_name", "")
        elif isinstance(last, str):
            # Старый формат записи (до 14.08.2026, без имени компании) —
            # поддержан для совместимости с уже накопленным bot_state.json.
            request_id = last

    if not request_id:
        return
    req = state["requests"].get(request_id)
    if not req or not req.get("client_chat_id"):
        return

    label = f"«{company_name}»" if company_name else "компании"
    tg_send(req["client_chat_id"], f"Ответ от {label}:\n\n{text}")

    if not matched_by_reply:
        tg_send(chat_id, "⚠️ Не понял точно, к какой заявке относится это сообщение (это не был "
                          "реплай на заявку) — переслал клиенту как ответ на последнюю известную "
                          "заявку. Если ведёшь несколько заявок одновременно, в следующий раз "
                          "отвечай РЕПЛАЕМ прямо на сообщение с нужной заявкой, чтобы не перепутать.")

    notify_admin(f"Компания {label} (chat_id={chat_id}) ответила по заявке #{request_id} "
                 f"клиенту {req['name']}:\n\n{text}")


def poll_loop():
    logger.info("поллинг запущен")
    while True:
        # 12.08.2026: раньше исключение из handle_start()/handle_reply()
        # (например, сбой похода в Google Sheets внутри handle_start —
        # это ОТДЕЛЬНЫЙ от Telegram-прокси сетевой вызов) не ловилось
        # нигде и тихо убивало весь фоновый поток навсегда — снаружи это
        # выглядело как "бот не отвечает", БЕЗ единой строки в логе,
        # потому что except был только вокруг самого запроса getUpdates.
        # Живой кейс: 7 подряд /start от пользователей за несколько
        # часов провисели неподтверждёнными в очереди Telegram, поток
        # не забирал вообще ничего — поймано через ручной curl
        # getUpdates мимо сервиса, в самом логе не было ни строки.
        # Теперь: try/except вокруг ВСЕГО тела цикла (а не только
        # getUpdates) + отдельно вокруг обработки каждого сообщения —
        # одно упавшее сообщение больше не должно уносить с собой весь
        # поллинг, и любая ошибка теперь печатается в лог.
        try:
            with _state_lock:
                state = load_state()
                offset = state.get("last_update_id", 0) + 1
            logger.debug(f"запрашиваю getUpdates, offset={offset}, proxies={PROXIES}")
            try:
                r = requests.get(f"{API}/getUpdates", params={"offset": offset, "timeout": 20}, timeout=25, proxies=PROXIES)
                updates = r.json().get("result", [])
                logger.debug(f"getUpdates ответил: status={r.status_code}, апдейтов={len(updates)}")
                for u in updates:
                    # 12.08.2026: печатаем СЫРОЙ апдейт целиком, даже если
                    # это не обычное "message" (например, my_chat_member —
                    # событие о том, что бота добавили/повысили в группе).
                    # Раньше такие апдейты молча пропускались (if not msg:
                    # continue) без единой строки в логе — не давало понять,
                    # что вообще происходит в группе.
                    logger.debug(f"сырой апдейт: {json.dumps(u, ensure_ascii=False)}")
            except Exception as e:
                logger.warning(f"getUpdates ошибка: {e}")
                time.sleep(5)
                continue

            if not updates:
                continue

            logger.info(f"получено апдейтов: {len(updates)}")

            with _state_lock:
                state = load_state()
                for u in updates:
                    state["last_update_id"] = u["update_id"]
                    msg = u.get("message")
                    if not msg:
                        continue
                    chat_id = msg["chat"]["id"]
                    username = msg["from"].get("username", "")
                    text = msg.get("text", "")
                    # 12.08.2026: диагностика для поиска chat_id рабочей
                    # группы (владелец хочет получать туда переписку
                    # клиент<->компания) — печатаем тип/название чата для
                    # КАЖДОГО входящего сообщения, не только обработанных.
                    logger.info(f"сообщение из chat_id={chat_id}, type={msg['chat'].get('type')}, "
                                f"title={msg['chat'].get('title', '')}, from=@{username}, text={text!r}")
                    try:
                        if text.startswith("/start"):
                            parts = text.split(maxsplit=1)
                            payload = parts[1] if len(parts) > 1 else ""
                            handle_start(chat_id, username, payload, state)
                        else:
                            # reply_to_message есть только если пользователь
                            # реально ответил реплаем на конкретное сообщение
                            # — это и нужно для точной маршрутизации (см.
                            # handle_reply). Если реплая нет, будет None и
                            # сработает запасной вариант внутри handle_reply.
                            reply_to = msg.get("reply_to_message") or {}
                            handle_reply(chat_id, text, state, reply_to.get("message_id"))
                    except Exception as e:
                        # Не даём одному сбойному сообщению убить весь
                        # поллинг — двигаем offset дальше (уже сделано
                        # выше, state["last_update_id"] обновлён) и просто
                        # логируем, чтобы было видно в journalctl.
                        logger.error(f"ошибка обработки апдейта {u.get('update_id')} от chat_id={chat_id}: {e}")
                save_state(state)
        except Exception as e:
            # Последний рубеж — если упало что-то совсем неожиданное
            # (например, сама блокировка/файл состояния), цикл всё равно
            # не должен умирать молча.
            logger.error(f"неожиданная ошибка в poll_loop: {e}")
            time.sleep(5)


# T-71 (21.08.2026): тред поллинга запускается на уровне МОДУЛЯ, а не
# внутри `if __name__ == "__main__":`. Раньше он стартовал только там —
# это работало под Flask dev-сервером (`python telegram_bot_service.py`
# исполняет файл как __main__), но НЕ сработало бы под gunicorn: gunicorn
# импортирует модуль и сам обращается к объекту `app` как WSGI-приложению,
# `__main__` при этом не выполняется — бот бы поднялся, отвечал на HTTP,
# но молчал бы в Telegram, потому что getUpdates никто не вызывает.
# Код верхнего уровня модуля выполняется ровно один раз при первом импорте
# (что бы его ни импортировало — gunicorn или прямой запуск), поэтому
# здесь треду безопасно стартовать один раз.
#
# ВАЖНО при деплое: должен существовать РОВНО один процесс с этим тредом.
# offset в getUpdates — состояние в памяти одного процесса; если поднять
# больше одного gunicorn worker'а, каждый начнёт свой параллельный
# getUpdates с одним и тем же offset — сообщения будут дублироваться и
# теряться непредсказуемо. В бою — строго `--workers 1`
# (см. deploy/telegram-bot.service), многопоточность внутри процесса даёт
# `--threads` у gunicorn (аналог прежнего Flask `threaded=True`, но с
# нормальным production-сервером вместо dev-сервера, который сам Flask не
# рекомендует использовать в проде).
threading.Thread(target=poll_loop, daemon=True).start()

if __name__ == "__main__":
    # Прямой запуск без gunicorn — только для локальной проверки/дебага
    # (например, на Маке без nginx перед сервисом). На VPS в проде
    # запускается через gunicorn (см. deploy/telegram-bot.service), этот
    # блок там не исполняется.
    app.run(host="0.0.0.0", port=5055, threaded=True)
