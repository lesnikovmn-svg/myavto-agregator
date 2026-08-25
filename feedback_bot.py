"""
Бот обратной связи для покупателей из @MY_Avto5 / @My_Avto_Optimal
(запрошено пользователем 25.08.2026: "нужно сделать бота для обратной
связи"). Решение пользователя по устройству бота (уточнено через
AskUserQuestion в этом же диалоге):
  - Функция: короткая анкета (какая машина интересует / бюджет / контакт),
    затем пересылка готовой заявки менеджерам (Максим/Антон).
  - Отдельный новый бот, НЕ переиспользует telegram_bot_service.py —
    та логика (заявки с сайта, онбординг компаний-подрядчиков, роутинг
    ответов по grouped_id) концептуально не связана с этим ботом,
    смешивать не стали.

Что делает:
1. Поллинг Telegram Bot API (getUpdates), тот же паттерн, что уже
   используется в telegram_bot_service.py (requests + optional PROXY_URL,
   без сторонних библиотек вроде python-telegram-bot — их в проекте нет,
   не стали добавлять ради одного файла).
2. /start (в т.ч. по диплинку из ссылки в футере постов) — начинает
   анкету заново, три вопроса подряд (машина -> бюджет -> контакт),
   после последнего ответа подтверждает клиенту и пересылает заявку всем
   chat_id из MANAGER_CHAT_IDS.
3. Если пользователь пишет что-то без активной сессии (не через /start) —
   всё равно начинаем анкету с первого вопроса, не заставляем разбираться
   с командами.

Хранилище — feedback_bot_state.json (сессии по chat_id + offset
getUpdates), НЕ в git (.gitignore), тот же принцип атомарной записи
(tmp + os.replace), что и в userbot_parser.py/telegram_bot_service.py.

Настройка (feedback_bot_config.env, тоже НЕ в git, создать вручную рядом,
см. feedback_bot_config.env.example):
    BOT_TOKEN=<токен от @BotFather>
    MANAGER_CHAT_IDS=<chat_id Максима>,<chat_id Антона>
    PROXY_URL=<опционально, тот же формат, что в bot_config.env>

MANAGER_CHAT_IDS — узнать свой chat_id: написать что угодно уже
запущенному боту, посмотреть в journalctl -u myavto-feedback-bot строку
"[feedback_bot] сообщение из chat_id=...".

Известные упрощения v1:
- Анкета линейная, без кнопок/inline-клавиатуры — три текстовых вопроса
  подряд, отменить/вернуться назад нельзя, только начать заново через
  /start.
- Нет валидации ответов (бюджет/контакт принимаются как есть, любой
  текст) — сознательно просто, чтобы не отсеивать реальные заявки
  неудачным парсингом свободного текста.
- Rate limiting не реализован — тот же трейд-офф, что в
  telegram_bot_service.py (небольшой объём заявок, не критично).
"""
import json
import logging
import os
import sys
import time

import requests

sys.stdout.reconfigure(line_buffering=True)

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("feedback_bot")

CONFIG = {}
with open("feedback_bot_config.env", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            CONFIG[k.strip()] = v.strip()

BOT_TOKEN = CONFIG["BOT_TOKEN"]
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

PROXY_URL = CONFIG.get("PROXY_URL", "").strip()
PROXIES = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None

MANAGER_CHAT_IDS = [c.strip() for c in CONFIG.get("MANAGER_CHAT_IDS", "").split(",") if c.strip()]
if not MANAGER_CHAT_IDS:
    logger.warning(
        "MANAGER_CHAT_IDS пуст в feedback_bot_config.env — заявки будут собираться, "
        "но пересылать их будет НЕКУДА. Узнать chat_id: написать боту что угодно, "
        "посмотреть в этом же логе."
    )

STATE_FILE = "feedback_bot_state.json"

# Порядок анкеты: (ключ_в_answers, текст_вопроса).
QUESTIONS = [
    ("car", "Какая машина вас интересует? (модель, ссылка на объявление или просто опишите словами)"),
    ("budget", "Какой у вас бюджет?"),
    ("contact", "Как с вами удобнее связаться? Укажите телефон или @username в Telegram."),
]

WELCOME_TEXT = (
    "Здравствуйте! Это бот обратной связи MY_Avto — соберём короткую заявку "
    "и менеджер свяжется с вами в ближайшее время.\n\n" + QUESTIONS[0][1]
)

DONE_TEXT = (
    "Спасибо! Заявка передана менеджеру, с вами свяжутся в ближайшее время.\n"
    "Если нужно оставить ещё одну заявку — просто отправьте /start."
)


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"sessions": {}, "last_update_id": 0}


def save_state(state):
    # Та же защита от обрезанного файла при падении процесса ровно во
    # время записи, что и в userbot_parser_state.json/bot_state.json —
    # atomic write через tmp + os.replace.
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)


def tg_send(chat_id, text):
    try:
        r = requests.post(
            f"{API}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
            proxies=PROXIES,
        )
        return r.json()
    except Exception as e:
        logger.warning("не удалось отправить сообщение %s: %s", chat_id, e)
        return None


def notify_managers(text):
    for chat_id in MANAGER_CHAT_IDS:
        tg_send(chat_id, text)


def format_lead(username, chat_id, answers):
    who = f"@{username}" if username else f"id {chat_id}"
    lines = [f"🚗 Новая заявка через бота обратной связи (от {who})"]
    for key, question in QUESTIONS:
        label = question.split("?")[0].split("(")[0].strip().rstrip(":")
        lines.append(f"{label}: {answers.get(key, '—')}")
    return "\n".join(lines)


def handle_message(chat_id, username, text, state):
    sessions = state.setdefault("sessions", {})
    key = str(chat_id)
    session = sessions.get(key)

    if text.strip().startswith("/start"):
        sessions[key] = {"step": 0, "answers": {}, "username": username}
        tg_send(chat_id, WELCOME_TEXT)
        return

    if session is None:
        # Написали без /start (например, сразу текстом) — не заставляем
        # разбираться с командами, просто начинаем анкету с первого вопроса
        # и засчитываем это сообщение как приветствие, а не как ответ —
        # человек ещё не видел вопрос, отвечать ему рано.
        sessions[key] = {"step": 0, "answers": {}, "username": username}
        tg_send(chat_id, WELCOME_TEXT)
        return

    step = session["step"]
    if step >= len(QUESTIONS):
        # Анкета уже завершена в этой сессии, а пользователь написал ещё
        # что-то — не переспрашиваем заново молча, направляем к /start.
        tg_send(chat_id, "Заявка уже отправлена менеджеру. Чтобы оставить новую — отправьте /start.")
        return

    field_key, _ = QUESTIONS[step]
    session["answers"][field_key] = text.strip()
    session["step"] = step + 1

    if session["step"] < len(QUESTIONS):
        tg_send(chat_id, QUESTIONS[session["step"]][1])
    else:
        tg_send(chat_id, DONE_TEXT)
        lead_text = format_lead(username, chat_id, session["answers"])
        logger.info("[lead] %s", lead_text.replace("\n", " | "))
        notify_managers(lead_text)


def poll_loop():
    logger.info("поллинг бота обратной связи запущен")
    while True:
        try:
            state = load_state()
            offset = state.get("last_update_id", 0) + 1
            try:
                r = requests.get(
                    f"{API}/getUpdates",
                    params={"offset": offset, "timeout": 20},
                    timeout=25,
                    proxies=PROXIES,
                )
                updates = r.json().get("result", [])
            except Exception as e:
                logger.warning("getUpdates ошибка: %s", e)
                time.sleep(5)
                continue

            if not updates:
                continue

            logger.info("получено апдейтов: %s", len(updates))
            state = load_state()
            for u in updates:
                state["last_update_id"] = u["update_id"]
                msg = u.get("message")
                if not msg or "text" not in msg:
                    continue
                chat_id = msg["chat"]["id"]
                username = msg["from"].get("username", "")
                text = msg["text"]
                logger.info("сообщение из chat_id=%s, from=@%s, text=%r", chat_id, username, text)
                try:
                    handle_message(chat_id, username, text, state)
                except Exception as e:
                    # Одно сбойное сообщение не должно ронять весь поллинг —
                    # тот же принцип, что в telegram_bot_service.py.
                    logger.error("ошибка обработки сообщения от chat_id=%s: %s", chat_id, e)
            save_state(state)
        except Exception as e:
            logger.error("неожиданная ошибка в poll_loop: %s", e)
            time.sleep(5)


if __name__ == "__main__":
    poll_loop()
