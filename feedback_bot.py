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

v2 (25.08.2026, запрошено пользователем — "заявку нужно подправить:
придумай оптимальный вариант, чтоб клиент сразу сам решил для себя какой
авто ему нужен", уточнено через AskUserQuestion: кнопки + бюджет/тип
кузова/новое-с пробегом):
  - Анкета переделана с одного расплывчатого текстового вопроса "какая
    машина интересует" на три наводящих вопроса КНОПКАМИ (inline
    keyboard): бюджет диапазоном, тип кузова, новое/с пробегом. Кнопки
    заставляют клиента сразу сузить выбор до конкретных параметров вместо
    произвольного текста — и попутно помогают ему самому определиться,
    что именно ему нужно. Последний вопрос (контакт) остался текстовым —
    для телефона/username кнопки не подходят.
  - Технически это первое место в проекте, где боту нужно обрабатывать
    callback_query (нажатия inline-кнопок), не только обычные text-
    сообщения — добавлены tg_send_buttons/tg_answer_callback/
    tg_strip_keyboard и отдельная ветка в poll_loop.

v3 (25.08.2026, после первого живого теста — "в принципе норм бот
работает, можно добавить какая марка модель"):
  - Добавлен первый шаг анкеты "марка/модель" — снова текстом (не
    кнопками: марок и моделей слишком много для инлайн-клавиатуры), с
    подсказкой писать "не важно", если конкретики нет — чтобы вопрос не
    был обязательным барьером для тех, кто ещё не определился.

Что делает:
1. Поллинг Telegram Bot API (getUpdates), тот же паттерн, что уже
   используется в telegram_bot_service.py (requests + optional PROXY_URL,
   без сторонних библиотек вроде python-telegram-bot — их в проекте нет,
   не стали добавлять ради одного файла).
2. /start (в т.ч. по диплинку из ссылки в футере постов) — начинает
   анкету заново: три вопроса кнопками (бюджет -> тип кузова ->
   новое/с пробегом), затем текстовый вопрос про контакт. После
   последнего ответа подтверждает клиенту и пересылает заявку всем
   chat_id из MANAGER_CHAT_IDS.
3. Если пользователь пишет что-то без активной сессии (не через /start) —
   всё равно начинаем анкету с первого вопроса, не заставляем разбираться
   с командами.
4. Если на "кнопочный" вопрос прислали текст вместо нажатия кнопки —
   не пытаемся угадать ответ, просим воспользоваться кнопками ещё раз.
   Если нажали кнопку от уже пройденного/устаревшего вопроса (например,
   после двойного клика) — такое нажатие тихо игнорируется.

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

Известные упрощения v2:
- Rate limiting не реализован — тот же трейд-офф, что в
  telegram_bot_service.py (небольшой объём заявок, не критично).
- Ответ на текстовый вопрос (контакт) без валидации — принимается как
  есть, любой текст, сознательно просто, чтобы не отсеивать реальные
  заявки неудачным парсингом свободного текста.
- Кнопочные вопросы жёстко привязаны к порядку шага (callback_data вида
  "<step_key>:<option_code>" сверяется с текущим шагом сессии) — если
  клиент отвечает не по порядку (например, старой клавиатурой после
  /start заново), нажатие просто игнорируется, а не ломает анкету.
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

# Анкета: наводящие вопросы кнопками (клиент сам сужает выбор до
# конкретного авто), последний шаг — контакт текстом.
# key    — идентификатор шага (используется в callback_data и в answers).
# label  — короткая подпись для заявки менеджеру.
# type   — "buttons" (inline keyboard) или "text" (обычное сообщение).
# options — только для type="buttons": список (текст_кнопки, код_варианта).
STEPS = [
    {
        "key": "brand_model",
        "label": "Марка/модель",
        "type": "text",
        "question": "Какая марка и модель вас интересуют? Если конкретики нет — напишите «не важно», подберём варианты.",
    },
    {
        "key": "budget",
        "label": "Бюджет",
        "type": "buttons",
        "question": "Какой у вас бюджет на автомобиль?",
        "options": [
            ("До 1.5 млн ₽", "lt1.5"),
            ("1.5–2.5 млн ₽", "1.5-2.5"),
            ("2.5–4 млн ₽", "2.5-4"),
            ("От 4 млн ₽", "gt4"),
            ("Пока не определился(-лась)", "unsure"),
        ],
    },
    {
        "key": "body_type",
        "label": "Тип кузова",
        "type": "buttons",
        "question": "Какой тип кузова вам нужен?",
        "options": [
            ("Седан", "sedan"),
            ("Кроссовер/внедорожник", "suv"),
            ("Хэтчбек", "hatchback"),
            ("Минивэн/универсал", "van"),
            ("Не важно", "any"),
        ],
    },
    {
        "key": "condition",
        "label": "Состояние",
        "type": "buttons",
        "question": "Какой автомобиль ищете — новый или с пробегом?",
        "options": [
            ("Новый", "new"),
            ("С пробегом", "used"),
            ("Не принципиально", "any"),
        ],
    },
    {
        "key": "contact",
        "label": "Контакт",
        "type": "text",
        "question": "Как с вами удобнее связаться? Укажите телефон или @username в Telegram.",
    },
]

WELCOME_PREFIX = (
    "Здравствуйте! Это бот обратной связи MY_Avto.\n"
    "Ответьте на пару вопросов кнопками — это поможет вам самим быстрее "
    "определиться с вариантом, а нам подобрать подходящие предложения "
    "и связаться с вами."
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


def build_inline_keyboard(step_key, options, per_row=2):
    rows = []
    row = []
    for label, code in options:
        row.append({"text": label, "callback_data": f"{step_key}:{code}"})
        if len(row) == per_row:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return {"inline_keyboard": rows}


def tg_send_buttons(chat_id, text, step_key, options):
    try:
        r = requests.post(
            f"{API}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "reply_markup": build_inline_keyboard(step_key, options),
            },
            timeout=10,
            proxies=PROXIES,
        )
        return r.json()
    except Exception as e:
        logger.warning("не удалось отправить кнопки %s: %s", chat_id, e)
        return None


def tg_answer_callback(callback_query_id):
    # Обязательно отвечать на callback_query, иначе у клиента кнопка
    # виснет в состоянии "загрузка" в интерфейсе Telegram.
    try:
        requests.post(
            f"{API}/answerCallbackQuery",
            json={"callback_query_id": callback_query_id},
            timeout=10,
            proxies=PROXIES,
        )
    except Exception as e:
        logger.warning("не удалось ответить на callback %s: %s", callback_query_id, e)


def tg_strip_keyboard(chat_id, message_id):
    # Убираем клавиатуру у уже отвеченного вопроса, чтобы повторный клик
    # по старым кнопкам не создавал путаницу (обрабатывается это и так
    # безопасно через сверку step_key в handle_callback, но так чище).
    try:
        requests.post(
            f"{API}/editMessageReplyMarkup",
            json={"chat_id": chat_id, "message_id": message_id, "reply_markup": {"inline_keyboard": []}},
            timeout=10,
            proxies=PROXIES,
        )
    except Exception as e:
        logger.warning("не удалось убрать клавиатуру %s/%s: %s", chat_id, message_id, e)


def notify_managers(text):
    for chat_id in MANAGER_CHAT_IDS:
        tg_send(chat_id, text)


def format_lead(username, chat_id, answers):
    who = f"@{username}" if username else f"id {chat_id}"
    lines = [f"🚗 Новая заявка через бота обратной связи (от {who})"]
    for step in STEPS:
        lines.append(f"{step['label']}: {answers.get(step['key'], '—')}")
    return "\n".join(lines)


def send_step(chat_id, step, prefix=None):
    text = f"{prefix}\n\n{step['question']}" if prefix else step["question"]
    if step["type"] == "buttons":
        tg_send_buttons(chat_id, text, step["key"], step["options"])
    else:
        tg_send(chat_id, text)


def advance_session(chat_id, username, session, state):
    if session["step"] < len(STEPS):
        send_step(chat_id, STEPS[session["step"]])
    else:
        tg_send(chat_id, DONE_TEXT)
        lead_text = format_lead(username, chat_id, session["answers"])
        logger.info("[lead] %s", lead_text.replace("\n", " | "))
        notify_managers(lead_text)


def handle_message(chat_id, username, text, state):
    sessions = state.setdefault("sessions", {})
    key = str(chat_id)
    session = sessions.get(key)

    if text.strip().startswith("/start") or session is None:
        # И явный /start, и первое сообщение без команды — начинаем анкету
        # заново с первого (кнопочного) вопроса, не заставляем разбираться
        # с командами.
        sessions[key] = {"step": 0, "answers": {}, "username": username}
        send_step(chat_id, STEPS[0], prefix=WELCOME_PREFIX)
        return

    step_idx = session["step"]
    if step_idx >= len(STEPS):
        # Анкета уже завершена в этой сессии, а пользователь написал ещё
        # что-то — не переспрашиваем заново молча, направляем к /start.
        tg_send(chat_id, "Заявка уже отправлена менеджеру. Чтобы оставить новую — отправьте /start.")
        return

    step = STEPS[step_idx]
    if step["type"] == "buttons":
        # На кнопочный вопрос прислали текст вместо нажатия — не пытаемся
        # угадать ответ по свободному тексту, просим воспользоваться
        # кнопками (и присылаем их ещё раз на случай, если предыдущее
        # сообщение потерялось из истории чата).
        send_step(chat_id, step, prefix="Пожалуйста, выберите один из вариантов кнопками 👇")
        return

    # Текстовый шаг (контакт).
    session["answers"][step["key"]] = text.strip()
    session["step"] = step_idx + 1
    advance_session(chat_id, username, session, state)


def handle_callback(chat_id, username, data, state):
    sessions = state.setdefault("sessions", {})
    key = str(chat_id)
    session = sessions.get(key)
    if session is None or ":" not in data:
        return

    step_idx = session["step"]
    if step_idx >= len(STEPS):
        return

    step = STEPS[step_idx]
    if step["type"] != "buttons":
        return

    step_key, option_code = data.split(":", 1)
    if step_key != step["key"]:
        # Нажата кнопка от уже пройденного или устаревшего вопроса
        # (например, двойной клик или клавиатура от анкеты до /start) —
        # тихо игнорируем, сессия не портится.
        return

    label = next((opt_label for opt_label, opt_code in step["options"] if opt_code == option_code), None)
    if label is None:
        return

    session["answers"][step["key"]] = label
    session["step"] = step_idx + 1
    advance_session(chat_id, username, session, state)


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
                cb = u.get("callback_query")

                if msg and "text" in msg:
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
                elif cb:
                    chat_id = cb["message"]["chat"]["id"]
                    username = cb.get("from", {}).get("username", "")
                    data = cb.get("data", "")
                    message_id = cb["message"]["message_id"]
                    logger.info("callback от chat_id=%s, from=@%s, data=%r", chat_id, username, data)
                    tg_answer_callback(cb["id"])
                    tg_strip_keyboard(chat_id, message_id)
                    try:
                        handle_callback(chat_id, username, data, state)
                    except Exception as e:
                        logger.error("ошибка обработки callback от chat_id=%s: %s", chat_id, e)
            save_state(state)
        except Exception as e:
            logger.error("неожиданная ошибка в poll_loop: %s", e)
            time.sleep(5)


if __name__ == "__main__":
    poll_loop()
