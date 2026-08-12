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
- Ответ компании клиенту роутится по "последняя заявка, о которой этой
  компании сообщили" — если компания ведёт 2+ параллельные заявки,
  возможна путаница. Для реального объёма это нужно дорабатывать
  (например, просить компанию отвечать реплаем на исходное сообщение
  и парсить message_id).
- Rate limits Telegram Bot API не обрабатываются (send с retry) — на
  небольшом объёме заявок не критично, добавить позже при росте.
"""
import json
import os
import re
import sys
import threading
import time

import gspread
import requests
from flask import Flask, jsonify, request
from google.oauth2.service_account import Credentials

# 12.08.2026: под systemd stdout не подключён к терминалу, поэтому Python
# по умолчанию блочно буферизует print() — сообщения могут подолгу не
# доходить до journalctl, из-за чего живая диагностика вводила в
# заблуждение (казалось, что поток вообще ничего не делает). Включаем
# построчную буферизацию, чтобы print() был виден в логе сразу же.
sys.stdout.reconfigure(line_buffering=True)

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

SHEET_CONFIG = {}
with open("agent_config.env") as f:
    for line in f:
        if "=" in line:
            k, v = line.strip().split("=", 1)
            SHEET_CONFIG[k] = v
SHEET_ID = SHEET_CONFIG["SHEET_ID"]

STATE_FILE = "bot_state.json"
_state_lock = threading.Lock()

app = Flask(__name__)


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"requests": {}, "companies": {}, "last_update_id": 0}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def tg_send(chat_id, text):
    try:
        requests.post(f"{API}/sendMessage", json={"chat_id": chat_id, "text": text}, timeout=10, proxies=PROXIES)
    except Exception as e:
        print(f"[bot] не удалось отправить сообщение {chat_id}: {e}")


def get_companies():
    """Читаем telegram/directions компаний прямо из Google Sheets —
    та же таблица, что использует company_agent.py/update_site.py, тут
    отдельной копии данных не держим."""
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
    client = gspread.authorize(creds)
    ws = client.open_by_key(SHEET_ID).sheet1
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
    return companies


@app.route("/api/mass-request", methods=["POST"])
def mass_request():
    data = request.get_json(force=True) or {}
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
    return jsonify({"request_id": request_id, "bot_username": BOT_USERNAME})


def handle_start(chat_id, username, payload, state):
    if payload.startswith("req_"):
        req_id = payload[len("req_"):]
        req = state["requests"].get(req_id)
        if not req:
            tg_send(chat_id, "Не нашёл эту заявку — возможно, ссылка устарела. Заполни форму на сайте ещё раз.")
            return
        req["client_chat_id"] = chat_id
        tg_send(chat_id, "Заявка принята! Ищу подходящие компании по направлению \"" + req["direction"] + "\" и рассылаю им запрос — ответы придут сюда же.")

        matched = [c for c in get_companies()
                   if req["direction"] in c["directions"] and c["telegram"] in state["companies"]]
        for c in matched:
            company_chat_id = state["companies"][c["telegram"]]
            text = (f"Новая заявка через MyAvtoAgregator.ru\n\n"
                    f"Клиент: {req['name']}\nКонтакт: {req['phone']}\n"
                    f"Направление: {req['direction']}\n" +
                    (f"Бюджет: {req['budget']}\n" if req["budget"] else "") +
                    (f"Что ищет: {req['model']}\n" if req["model"] else "") +
                    "\nОтветь сюда же — сообщение перешлём клиенту.")
            tg_send(company_chat_id, text)
            req["companies_notified"].append(c["telegram"])
            # для MVP-роутинга ответа компании -> клиенту (см. docstring)
            state["companies_last_request"] = state.get("companies_last_request", {})
            state["companies_last_request"][str(company_chat_id)] = req_id

        if matched:
            tg_send(chat_id, f"Заявка отправлена {len(matched)} компаниям.")
        else:
            tg_send(chat_id, "Пока не нашлось онбордившихся компаний по этому направлению — свяжемся с тобой вручную.")
        return

    # Не заявка клиента — пробуем онбординг компании по совпадению username
    if username:
        companies = get_companies()
        match = next((c for c in companies if c["telegram"] == username.lower()), None)
        if match:
            state["companies"][match["telegram"]] = chat_id
            tg_send(chat_id, f"Готово, {match['name']}! Теперь новые заявки по вашим направлениям будут приходить сюда.")
            return

    tg_send(chat_id, "Привет! Это бот MyAvtoAgregator.ru. Если ты клиент — оформи заявку на сайте, ссылка придёт сюда автоматически.")


def handle_reply(chat_id, text, state):
    last_req = state.get("companies_last_request", {}).get(str(chat_id))
    if not last_req:
        return
    req = state["requests"].get(last_req)
    if not req or not req.get("client_chat_id"):
        return
    tg_send(req["client_chat_id"], f"Ответ от компании:\n\n{text}")


def poll_loop():
    print("[bot] поллинг запущен")
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
            print(f"[bot] запрашиваю getUpdates, offset={offset}, proxies={PROXIES}")
            try:
                r = requests.get(f"{API}/getUpdates", params={"offset": offset, "timeout": 20}, timeout=25, proxies=PROXIES)
                updates = r.json().get("result", [])
                print(f"[bot] getUpdates ответил: status={r.status_code}, апдейтов={len(updates)}")
            except Exception as e:
                print(f"[bot] getUpdates ошибка: {e}")
                time.sleep(5)
                continue

            if not updates:
                continue

            print(f"[bot] получено апдейтов: {len(updates)}")

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
                    try:
                        if text.startswith("/start"):
                            parts = text.split(maxsplit=1)
                            payload = parts[1] if len(parts) > 1 else ""
                            handle_start(chat_id, username, payload, state)
                        else:
                            handle_reply(chat_id, text, state)
                    except Exception as e:
                        # Не даём одному сбойному сообщению убить весь
                        # поллинг — двигаем offset дальше (уже сделано
                        # выше, state["last_update_id"] обновлён) и просто
                        # логируем, чтобы было видно в journalctl.
                        print(f"[bot] ошибка обработки апдейта {u.get('update_id')} от chat_id={chat_id}: {e}")
                save_state(state)
        except Exception as e:
            # Последний рубеж — если упало что-то совсем неожиданное
            # (например, сама блокировка/файл состояния), цикл всё равно
            # не должен умирать молча.
            print(f"[bot] неожиданная ошибка в poll_loop: {e}")
            time.sleep(5)


if __name__ == "__main__":
    threading.Thread(target=poll_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5055)
