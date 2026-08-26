"""
T-77: живой парсинг ТГ-каналов-источников -> рерайт под наш формат ->
постинг в @MY_Avto5 / @My_Avto_Optimal по цене.

Работает постоянно (event-driven через Telethon), использует уже
залогиненную сессию myavto_userbot.session (см. userbot_login.py).
Источники и цели читаются из userbot_config.env.

DRY_RUN=true (по умолчанию) — постит не в боевые каналы, а в тестовую
группу (TEST_GROUP_INVITE), чтобы можно было живьём посмотреть текст,
фото и видео перед включением на реальные MY_Avto5/My_Avto_Optimal.
При старте в DRY_RUN дополнительно разбирает последние
TEST_BACKFILL_LIMIT постов каждого источника — не нужно ждать новых
постов, чтобы проверить парсинг.
Переключить на боевой режим: DRY_RUN=false в userbot_config.env.

VIDEO_DRY_RUN=true (по умолчанию, T-79, 25.08.2026) — НЕЗАВИСИМЫЙ от
DRY_RUN переключатель именно для постов, где есть видео: пока он true,
такие посты уходят в тестовую группу, даже если общий DRY_RUN уже false
(боевой режим для фото/текста). Альбом публикуется ЦЕЛИКОМ в одно место —
фото и видео одного поста никогда не разбиваются по разным каналам.
Причина: снятие водяного знака с видео (winner_auto_club) ещё не
встроено в этот файл — есть рабочий прототип, `watermark_video.py`
(переделан 26.08.2026, T-85, на OCR-детект + локальный трекинг, см. его
докстринг; проверен на реальном тестовом видео), но он НЕ вызывается ни
из handle_group(), ни из _prepare_media_list() — публиковать видео с
чужим логотипом в боевые нельзя. Когда его подключат и подтвердят на
реальных постах — выключить VIDEO_DRY_RUN=false в userbot_config.env.
T-83 (25.08.2026, обнаружено пользователем — "почему в тест групу пришли
посты из безпокраса?"): это правило применяется НЕ ко всем источникам
подряд, а только к тем, что перечислены в VIDEO_DRY_RUN_SOURCES (по
умолчанию только winner_auto_club) — у остальных источников (например,
bezpokrasa) видео не содержит чужого водяного знака, причины прятать его
в тест нет, идёт по обычному DRY_RUN как фото/текст.

T-84 (26.08.2026, запрошено пользователем — "постим с 8 до 21:30 по мск в
май авто и май авто оптимал?"): посты в БОЕВЫЕ каналы (@My_Avto5 /
@My_Avto_Optimal) отправляются только в окне 08:00–21:30 по Москве
(POSTING_WINDOW_START/END). Вне окна пост НЕ отбрасывается — сохраняется в
userbot_pending_queue.json и уходит, как только окно снова откроется (см.
_pending_queue_flusher(), опрашивает раз в ~120с). Ограничение касается
ТОЛЬКО боевых целей — тестовая группа (DRY_RUN/VIDEO_DRY_RUN/
TEST_ONLY_SOURCES) публикуется в любое время суток, как и раньше. Москва —
без перехода на летнее/зимнее время, поэтому время считается фиксированным
смещением UTC+3 (см. _now_msk()) без зависимости от zoneinfo/pytz.

T-85 (26.08.2026, пользователь прислал реальные фото из тестового прогона —
"фиаско полное, посмотри какие огромные закраски бейджа"): template-matching
детект бейджа winner_auto_club (v1) ни разу не нашёл настоящий бейдж на
реальных фото, вместо этого закрашивал случайные места. В тот же день
переделан на OCR-детект текста бейджа (v2, Tesseract) — см. подробный
комментарий над remove_watermark() ниже. Проверено на всех 5 реальных фото
из жалобы: бейдж найден и закрашен на 2 из 3 фото с настоящим бейджем
(третье — OCR не распознал уверенно, фото ушло как есть, это ожидаемо), ни
одного ложного срабатывания на 2 фото без бейджа (раньше ложно срабатывало
на обоих). PHOTO_PROCESSORS восстановлен. winner_auto_club всё ещё в
TEST_ONLY_SOURCES — обработка идёт только в тестовую группу, пока
пользователь не проверит результат на живом трафике.

Известные упрощения v1 (см. T-77 в TASKS.md):
- Альбомы (несколько фото в одном посте) обрабатываются по первому
  найденному медиа-файлу поста, не всей группой.
- Курс EUR/RUB и USD/RUB — константы в конфиге, обновлять вручную.
- Наценка на итоговую цену — грубая оценка (сумма уже данных в посте
  составляющих), не точный калькулятор растаможки.
- winner_auto_club (добавлен 25.08.2026): автоматическое удаление водяного
  знака канала с фото (согласовано с собственником) — детект переделан на
  OCR текста бейджа (T-85, 26.08.2026, см. remove_watermark ниже), пока в
  TEST_ONLY_SOURCES. Видео с тем же знаком всё ещё не обрабатывается —
  публикуется как есть, такие посты принудительно идут в тестовую группу
  через VIDEO_DRY_RUN (см. выше) — сейчас, впрочем, это неактуально, весь
  источник и так в тесте через TEST_ONLY_SOURCES. Есть рабочий прототип
  обработки видео — `watermark_video.py` (переделан 26.08.2026, T-85, на
  тот же OCR-детект, что и для фото, + локальный трекинг между кадрами),
  проверен на реальном тестовом видео, но НЕ подключён к этому файлу
  (handle_group()/_prepare_media_list() его не вызывают).
"""
import asyncio
import io
import json
import logging
import re
from datetime import datetime, timedelta, time as dtime
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import cv2
try:
    import pytesseract  # T-85 (26.08.2026): OCR-детект бейджа winner_auto_club вместо template matching
except ImportError:  # pragma: no cover — на случай, если пакет/бинарь tesseract ещё не поставлены
    pytesseract = None
from telethon import TelegramClient, events
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.errors import UserAlreadyParticipantError, MediaCaptionTooLongError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("userbot_parser")

STATE_PATH = Path("userbot_parser_state.json")

# Фирменный футер — тот же на каждом посте, задан пользователем 24.08.2026
# по образцу реального поста на канале. Плейсхолдеры без ссылок (MAX,
# Яндекс) — заполнить точными URL, когда пользователь их даст, пока просто
# текст, как в оригинале.
# Разбит на intro/contacts (25.08.2026, T-78), чтобы вставить строку с
# ботом обратной связи МЕЖДУ ними — см. build_footer() ниже.
_OUR_FOOTER_INTRO = """Почему именно MY_Avto?
Мы не просто продаём автомобили. Мы тщательно подбираем машину, которая на 100% соответствует вашим задачам, бюджету, стилю вождения и ожиданиям. Каждый экземпляр проходит полную проверку по всем параметрам.

Фото/видео, осмотр после доставки, полный расчёт под ключ — пишите прямо сейчас!"""

_OUR_FOOTER_CONTACTS = """✈️ Telegram: [My_Avto_Optimal](https://t.me/My_Avto_Optimal)
✈️ Telegram: [MY_Avto5](https://t.me/MY_Avto5)
✈️ Telegram: [my_avto_opyt](https://t.me/my_avto_opyt)
✈️ Максим: [LesnikovM](https://t.me/LesnikovM) | [+7 938 409-67-08](tel:+79384096708)
✈️ Антон: [Tohakmv](https://t.me/Tohakmv) | [+7 963 383-79-28](tel:+79633837928)
🌐 Сайт: [my-avto.online](https://www.my-avto.online)
🌐 Сайт: [myavto-agregator.ru](https://myavto-agregator.ru)
📸 Instagram: [my_avto5](https://www.instagram.com/my_avto5)
💙 VK: [my_avto5](https://vk.com/my_avto5)
💬 MAX: [Присоединиться](https://max.ru/join/DXEGJWNaZPpj8WYi3eIMqJLriw-T0hF5ddCfUN2tk7I)
📍 Яндекс: [Профиль](https://yandex.ru/profile/-/CTvFvXPa)
MY_Avto — ваш надёжный партнёр в выборе авто! 🚗"""

OUR_FOOTER = f"{_OUR_FOOTER_INTRO}\n\n{_OUR_FOOTER_CONTACTS}"


def build_footer(feedback_bot_username=None):
    """Как OUR_FOOTER, но если задан FEEDBACK_BOT_USERNAME (T-78, бот
    обратной связи) — вставляет ссылку на бота отдельной строкой перед
    остальными контактами."""
    if not feedback_bot_username:
        return OUR_FOOTER
    bot_line = f"📮 Оставить заявку боту: [Написать](https://t.me/{feedback_bot_username})"
    return f"{_OUR_FOOTER_INTRO}\n\n{bot_line}\n{_OUR_FOOTER_CONTACTS}"

# Строки источника, которые вычищаем перед репостом — их собственные сайт/
# контакты/CTA, чтобы покупатель писал нам, а не в источник.
_DROP_PATTERNS = [
    re.compile(r"www\.", re.I),
    re.compile(r"https?://", re.I),
    re.compile(r"не нашли", re.I),
    re.compile(r"заполните форму", re.I),
    re.compile(r"primoryechinaexport", re.I),
    re.compile(r"\+7\s*\(?995\)?\s*866[-\s]?40[-\s]?82"),
    re.compile(r"проверить\s+в\s+боте", re.I),  # чужая VIN-проверка источника — не наша фича
]

_NO_LETTERS_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ]")


def _is_decoration_only(line):
    """Строка-разделитель без единой буквы (только эмодзи/символы) — чистая
    визуальная линия у источника, у нас только раздувает подпись."""
    stripped = line.strip()
    return bool(stripped) and not _NO_LETTERS_RE.search(stripped)

# Только для bezpokrasa: убираем построчную раскладку цены источника (инвойс/
# таможня/готовая цена в Москве) — вместо неё вставляем одну итоговую строку
# с нашей наценкой (см. CHINA_MARKUP_RUB), пользователь просил "показывать
# только итоговую сумму".
_CHINA_PRICE_LINE_PATTERNS = [
    re.compile(r"инвойс", re.I),
    re.compile(r"^\s*таможн[а-я]*:", re.I),
    re.compile(r"цена\s*(под\s*ключ\s*)?в\s*москве", re.I),
    re.compile(r"конфигурация.*сток", re.I),  # мёртвая ссылка на источник, нам не нужна
]

# Раздел про состояние/повреждения — важная для покупателя информация,
# сокращение опций его никогда не должно затрагивать.
_CONDITION_SECTION_RE = re.compile(r"состояни|оригинальн[а-я]*\s*лкп|без\s*повреждени|ремонт", re.I)

# Базовые ТТХ, которые у bezpokrasa всегда идут в начале и всегда нужны —
# их не считаем "лишними опциями", даже если оформлены как "Label: value"
# точно так же, как строки комфорта/опций.
_CHINA_SPEC_LABEL_RE = re.compile(
    r"^(дата\s*производства|пробег|комплектаци|тип\s*кузова|двигатель|коробка|привод|город\s*нахождени)",
    re.I,
)

# Только для winner_auto_club: собственные контакты/соцсети источника и
# его строка цены (вставляем свою итоговую строку в рублях, см. ниже) —
# те же общие _DROP_PATTERNS не ловят их (в тексте это голые домены/
# юзернеймы без "http(s)://" и "www.").
_WAC_DROP_PATTERNS = [
    re.compile(r"@Art_WAC", re.I),
    re.compile(r"instagram\.com", re.I),
    re.compile(r"wa\.me", re.I),
    re.compile(r"whats\s*app", re.I),
    re.compile(r"tik\s*tok", re.I),
    re.compile(r"winner[_.\s]*auto[_.\s]*club", re.I),
    re.compile(r"^\s*[💸]?\s*\**\s*[Цц]ена", re.I),
    re.compile(r"официальн[а-я]*\s*(дилер|партнёр)", re.I),
    re.compile(r"репутаци", re.I),
    re.compile(r"гарант[а-я]*\s*сделк", re.I),
]

# T-82 (25.08.2026, добавлен источник @TamSyam26, "с этой группы тоже
# парсим объявления"). Строки с ценой источника вычищаем целиком (обе —
# "под ключ до РФ" и "с доставкой в <город продавца>") и вставляем свою
# одну строку под ключ с доставкой в Краснодар (решение пользователя:
# "меняем на с доставкой на краснодар" / "локацию меняем на краснодар
# (под ключ)"). Адрес офиса продавца и промо-блоки (кредит, свой канал в
# MAX, CTA "купить консультацию") вычищаем как чужие контакты у других
# источников (решение пользователя — "Вычищать"). "Доставка в Москву
# +30000 т₽" пользователь попросил ОСТАВИТЬ как есть.
_TAM_DROP_PATTERNS = [
    re.compile(r"офис\s+находит", re.I),
    re.compile(r"^\s*[✅]?\s*[Цц]ена", re.I),
    re.compile(r"в\s+кредит", re.I),
    re.compile(r"MAX\s*канал", re.I),
    re.compile(r"[Кк]упить.*консультац", re.I),
]

MAX_CHINA_FEATURE_LINES = 6


def _condense_china_features(lines, max_lines=MAX_CHINA_FEATURE_LINES):
    """У bezpokrasa список опций/комфорта — 15-20 строк (часто тоже в
    формате "Label: value"), сильно раздувает подпись и часто выбивает её
    за лимит Telegram. Оставляем заголовок, базовые ТТХ (VIN/дата/пробег/
    комплектация/кузов/двигатель/коробка/привод/город) и первые max_lines
    "лишних" строк опций — остальное заменяем одной пометкой. Раздел
    "Честно о состоянии" (ремонт/повреждения) не трогаем — как только
    встречаем его, дальше строки не считаем и не режем."""
    result = []
    feature_count = 0
    truncated = False
    in_features_zone = True
    for line in lines:
        stripped = line.strip()
        if in_features_zone and _CONDITION_SECTION_RE.search(stripped):
            in_features_zone = False
        is_title_or_spec = bool(_CHINA_SPEC_LABEL_RE.match(stripped)) or "vin" in stripped.lower()
        is_extra_feature_line = (
            in_features_zone
            and stripped
            and not is_title_or_spec
        )
        if is_extra_feature_line:
            feature_count += 1
            if feature_count > max_lines:
                truncated = True
                continue
        result.append(line)
    if truncated:
        result.append("…и другие опции")
    return result


def _collapse_blank_lines(lines):
    """Не более одной пустой строки подряд — после вычистки декоративных
    разделителей и опций в тексте могли остаться "дыры" в 2-3 строки."""
    result = []
    for line in lines:
        if line.strip() == "" and result and result[-1].strip() == "":
            continue
        result.append(line)
    return result


# VIN — стандартно 17 символов, буквы+цифры без I/O/Q (чтобы не путать с
# 1/0). T-81 (25.08.2026, запрошено пользователем — "смотри какая задача
# из канала арталекс винкод если есть в тексте и на картинке, фото убираем
# последние 5 цифр, закрываем звездочкой"): пока сделана только текстовая
# часть для artalexgroup — маскировка VIN на ФОТО (табличка/шильд) отложена,
# нужен OCR и реальные примеры фото для прототипа (см. TASKS.md).
_VIN_RE = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b", re.IGNORECASE)


def mask_vin(text):
    """Заменяет последние 5 символов найденного VIN на звёздочки (не только
    цифры — пользователь сказал "последние 5 цифр", но VIN на этой позиции
    может содержать и буквы; маскируем последние 5 символов целиком, чтобы
    не оставлять частичный VIN читаемым из-за буквы на пятой позиции)."""
    return _VIN_RE.sub(lambda m: m.group(0)[:-5] + "*****", text)


def build_repost_text(raw_text, source_username=None, price_rub=None, price_usd=None, feedback_bot_username=None):
    """Исходный текст объявления как есть (без чужих контактов/сайта) + наш футер.
    bezpokrasa — вычищает построчную раскладку цены источника, вставляет
    готовую строку в рублях (с наценкой за доставку под ключ). winner_auto_club
    (решение пользователя 25.08.2026) — цену оставляем в $, без конвертации в
    рубли: это цена в Грузии, за точной ценой к моменту сделки просят писать
    в личку менеджерам (курс/доставка/растаможка не фиксированы заранее)."""
    drop_patterns = list(_DROP_PATTERNS)
    if source_username == "bezpokrasa":
        drop_patterns += _CHINA_PRICE_LINE_PATTERNS
    elif source_username == "winner_auto_club":
        drop_patterns += _WAC_DROP_PATTERNS
    elif source_username == "tamsyam26":
        drop_patterns += _TAM_DROP_PATTERNS

    kept = []
    for line in raw_text.splitlines():
        if _is_decoration_only(line):
            continue
        if any(p.search(line) for p in drop_patterns):
            continue
        kept.append(line)

    if source_username == "bezpokrasa":
        kept = _condense_china_features(kept)
    kept = _collapse_blank_lines(kept)

    while kept and not kept[-1].strip():
        kept.pop()
    body = "\n".join(kept).strip()

    if source_username == "artalexgroup":
        body = mask_vin(body)
    elif source_username == "tamsyam26":
        # Продавец в Ставрополе, мы работаем из Краснодара — город продавца
        # в оставшемся тексте (например, в строке про сроки доставки) не
        # должен противоречить нашей же строке с ценой ниже.
        body = re.sub(r"ставрополь", "Краснодар", body, flags=re.I)
        # 26.08.2026 (пользователь увидел реальные посты в тесте — "буквы т
        # зачем? убрать"): в исходнике источника лишняя "т" приклеена прямо
        # к числу перед единицей — "32300т км" (пробег) и "+30000 т₽"
        # (доставка в Москву). Убираем именно эту "т", саму цифру и текст
        # вокруг не трогаем.
        body = re.sub(r"(?<=\d)т(?=\s*км)", "", body)
        body = re.sub(r"(?<=\s)т₽", "₽", body)

    if source_username == "bezpokrasa" and price_rub is not None:
        price_str = f"{price_rub:,}".replace(",", " ")
        price_line = f"Цена под ключ в Москве: {price_str} \u20bd"
        body = f"{body}\n\n{price_line}" if body else price_line
    elif source_username == "tamsyam26" and price_rub is not None:
        price_str = f"{price_rub:,}".replace(",", " ")
        price_line = f"Цена под ключ в Краснодаре: {price_str} " + "₽"
        body = f"{body}\n\n{price_line}" if body else price_line
    elif source_username == "winner_auto_club" and price_usd is not None:
        price_str = f"{price_usd:,}"
        price_line = f"Цена: ${price_str} (цена в Грузии). За точной ценой на момент сделки — пишите в личку."
        body = f"{body}\n\n{price_line}" if body else price_line

    footer = build_footer(feedback_bot_username)
    return f"{body}\n\n{footer}" if body else footer

PRICE_LOW = 4_500_000
PRICE_HIGH = 6_000_000

# Фикс. наценка на автомобили из bezpokrasa (Суйфэньхэ): итоговая цена =
# инвойс (стоимость авто) + таможня (пошлина) + эта наценка. Задано
# пользователем 24.08.2026.
CHINA_MARKUP_RUB = 470_000

# Telegram: подпись (caption) к фото/видео/альбому не может быть длиннее
# ~1024 символов (считает по отрендеренному тексту, не по сырой markdown-
# разметке с [текст](ссылка) — поэтому точную длину заранее не посчитать).
# Логика ниже сперва пробует отправить одним сообщением с подписью и
# переключается на разбивку только если Telegram сам вернёт
# MediaCaptionTooLongError — это надёжнее прикидки по сырой длине текста.


def load_env(path="userbot_config.env"):
    env = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def build_proxy(proxy_url):
    if not proxy_url:
        return None
    import python_socks

    parsed = urlparse(proxy_url)
    return (
        python_socks.ProxyType.HTTP,
        parsed.hostname,
        parsed.port,
        True,
        parsed.username,
        parsed.password,
    )


def clean_amount(raw):
    """'220.000' / '1 740 200' / '154 000' -> int, или None."""
    if not raw:
        return None
    digits = re.sub(r"[^\d]", "", raw)
    if not digits:
        return None
    return int(digits)


def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {}


def save_state(state):
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)


# --- T-84: окно постинга в боевые каналы + очередь отложенных постов ---
#
# Россия не переходит на летнее/зимнее время — фиксированное смещение
# UTC+3 достаточно точно и не требует зависимости от zoneinfo/pytz.
POSTING_WINDOW_START = dtime(8, 0)
POSTING_WINDOW_END = dtime(21, 30)

PENDING_QUEUE_PATH = Path("userbot_pending_queue.json")


def _now_msk():
    return datetime.utcnow() + timedelta(hours=3)


def _in_posting_window(now_msk=None):
    now_msk = now_msk or _now_msk()
    return POSTING_WINDOW_START <= now_msk.time() <= POSTING_WINDOW_END


def load_pending_queue():
    if PENDING_QUEUE_PATH.exists():
        return json.loads(PENDING_QUEUE_PATH.read_text(encoding="utf-8"))
    return {"items": []}


def save_pending_queue(queue):
    tmp = PENDING_QUEUE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(PENDING_QUEUE_PATH)


def _queue_pending(source_username, ids):
    """Кладёт пост (вне окна постинга, см. handle_group) в очередь
    отложенных — без дублей, если он там уже лежит (например, событие
    доставилось Telethon повторно)."""
    queue = load_pending_queue()
    ids_set = set(ids)
    for item in queue["items"]:
        if item["source_username"] == source_username and set(item["ids"]) == ids_set:
            return
    queue["items"].append({"source_username": source_username, "ids": sorted(ids_set)})
    save_pending_queue(queue)


# Дедуп по точному набору уже отправленных id сообщений, а не по "максимальному
# id" (watermark). Watermark ошибочен для ретроспективного бэкфилла: старый
# пост, пропущенный раньше (например, альбом без подписи в узком окне выборки),
# имеет id МЕНЬШЕ уже отправленного нового — watermark считает его "уже
# сделанным", хотя реально он не отправлялся, и не даёт его переотправить,
# даже если окно выборки потом расширили и подпись в него попала.

def _sent_ids_key(source_username):
    return f"sent_ids:{source_username}"


def _get_sent_ids(state, source_username):
    return set(state.get(_sent_ids_key(source_username), []))


def _mark_sent(state, source_username, ids):
    key = _sent_ids_key(source_username)
    state[key] = sorted(set(state.get(key, [])) | set(ids))


def _already_sent(state, source_username, ids):
    return bool(set(ids) & _get_sent_ids(state, source_username))


# --- Парсинг источников -----------------------------------------------

def parse_eu_wholesale(text):
    """Формат artalexgroup: Netto € + услуги экспорта/логистики + таможня РБ/РФ."""
    title = None
    for line in text.splitlines():
        line = line.strip(" ❗️🚘🚨")
        if re.search(r"20\d{2}", line) and len(line) > 3:
            title = line
            break

    vin = re.search(r"vin[-\s]?code:?\s*([A-Z0-9]{5,20})", text, re.I)
    netto = re.search(r"(?:netto|НЕТТО)[^\d]{0,15}([\d.,\s]+)\s*€", text, re.I)
    export = re.search(
        r"(?:экспорт[а-я]*(?:\s*\+?\s*логистик[а-я]*)?)[^\d€]{0,15}([\d.,\s]+)\s*€",
        text, re.I,
    )
    customs = re.search(
        r"таможн[а-я]*\s*(?:РБ|РФ)?[^\d€]{0,15}([\d.,\s]+)\s*€",
        text, re.I,
    )

    netto_v = clean_amount(netto.group(1)) if netto else None
    export_v = clean_amount(export.group(1)) if export else 0
    customs_v = clean_amount(customs.group(1)) if customs else 0

    if netto_v is None:
        return None

    return {
        "title": title or "Автомобиль",
        "vin": vin.group(1) if vin else None,
        "mileage": None,
        "price_eur_total": netto_v + export_v + customs_v,
        "price_usd_total": None,
        "price_rub": None,  # считается отдельно, нужен курс
    }


def parse_china_invoice(text):
    """Формат bezpokrasa: VIN, дата производства, пробег, инвойс+таможня в рублях."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    title = lines[0].split("(VIN")[0].strip(" ❗️") if lines else "Автомобиль"

    vin = re.search(r"vin:?\s*([A-Za-z0-9]{4,20})", text, re.I)
    mileage = re.search(r"Пробег:?\s*([\d\s]+)\s*км", text, re.I)

    ready_price = re.search(
        r"[Цц]ена\s*в\s*Москве[^\d]{0,10}([\d.,\s]+)",
        text, re.I,
    )
    invoice_rub = re.search(r"[Ии]нвойс[^~]*~\s*([\d\s]+)\s*руб", text, re.I)
    customs_rub = re.search(r"[Тт]аможн[а-я]*:?\s*~?\s*([\d\s]+)\s*руб", text, re.I)

    price_rub = None
    if ready_price:
        raw = ready_price.group(1)
        val = clean_amount(raw)
        # "2,390 млн" — при запятой как разделителе это тысячи, а не рубли напрямую
        if "млн" in ready_price.group(0).lower() and val and val < 1000:
            val = val * 1000
        price_rub = val
    elif invoice_rub and customs_rub:
        price_rub = clean_amount(invoice_rub.group(1)) + clean_amount(customs_rub.group(1)) + CHINA_MARKUP_RUB

    if price_rub is None:
        return None

    mileage_str = None
    if mileage:
        mileage_str = f"{clean_amount(mileage.group(1))} км"

    return {
        "title": title,
        "vin": vin.group(1) if vin else None,
        "mileage": mileage_str,
        "price_eur_total": None,
        "price_usd_total": None,
        "price_rub": price_rub,
    }


def parse_winner_auto_club(text):
    """Формат winner_auto_club: метки по-русски (Год выпуска/Пробег/Цена),
    цена в $ (формат "54.500$" — точка как разделитель тысяч, знак после
    числа). VIN в этом источнике обычно не публикуется — просто None,
    ничего не выдумываем."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    title = None
    for line in lines:
        stripped = line.strip(" ❗️🚨🚘🔥‼️➡️➖—-*")
        if stripped:
            title = stripped
            break

    vin = re.search(r"vin[:\s]*([A-Za-z0-9]{5,20})", text, re.I)
    mileage = re.search(r"[Пп]робег:?\s*\**\s*([\d.,\s]+)\s*км", text, re.I)
    price = re.search(r"[Цц]ена:?\s*\**\s*([\d.,\s]+)\s*\$", text)

    price_usd = clean_amount(price.group(1)) if price else None
    if price_usd is None:
        return None

    mileage_str = None
    if mileage:
        mileage_str = f"{clean_amount(mileage.group(1))} км"

    return {
        "title": title or "Автомобиль",
        "vin": vin.group(1) if vin else None,
        "mileage": mileage_str,
        "price_eur_total": None,
        "price_usd_total": price_usd,
        "price_rub": None,
    }


_TAM_TITLE_RE = re.compile(r"^[A-ZА-ЯЁ0-9][A-ZА-ЯЁ0-9\s\-]{1,30}$")


def parse_tamsyam26(text):
    """Формат TamSyam26 (T-82, добавлен 25.08.2026): свободный текст с
    эмодзи-баннерами, модель/ТТХ отдельными строками, ДВЕ цены в рублях —
    "под ключ до РФ (Владивосток-Уссурийск)" (не привязана к городу
    продавца) и "с доставкой в <город продавца>" (не наша, это его город).
    Решение пользователя: берём цену "под ключ", в репосте показываем как
    доставку в Краснодар (см. build_repost_text()). Сэмпл — 1 реальный
    пост, регэксп может потребовать правки на других форматах этого же
    источника."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    # Модель у этого источника — отдельная строка КАПСОМ (например "TIGUAN"),
    # а не первая строка с буквами вообще (первые строки обычно — эмодзи-
    # баннер и рекламные фразы вроде "сделки проходят только по договору").
    title = next((l for l in lines if _TAM_TITLE_RE.match(l)), "Автомобиль")

    price_match = re.search(r"под\s+ключ.{0,150}?([\d][\d.,\s]{3,})\s*₽", text, re.I)
    if price_match is None:
        return None
    price_rub = clean_amount(price_match.group(1))
    if price_rub is None:
        return None

    mileage = re.search(r"[Пп]робег\s*([\d\s]+)\s*км", text)
    mileage_str = f"{clean_amount(mileage.group(1))} км" if mileage else None

    return {
        "title": title,
        "mileage": mileage_str,
        "price_eur_total": None,
        "price_usd_total": None,
        "price_rub": price_rub,
    }


SOURCE_PARSERS = {
    "artalexgroup": parse_eu_wholesale,
    "bezpokrasa": parse_china_invoice,
    "winner_auto_club": parse_winner_auto_club,
    "tamsyam26": parse_tamsyam26,
}


def compute_price_rub(parsed, eur_rub_rate, usd_rub_rate=None):
    if parsed["price_rub"] is not None:
        return parsed["price_rub"]
    if parsed.get("price_usd_total") is not None and usd_rub_rate:
        return round(parsed["price_usd_total"] * usd_rub_rate)
    if parsed["price_eur_total"] is not None and eur_rub_rate:
        return round(parsed["price_eur_total"] * eur_rub_rate)
    return None


def route_targets(price_rub, target_optimal, target_my_avto5):
    if price_rub is None:
        return []
    if price_rub < PRICE_LOW:
        return [target_optimal]
    if price_rub <= PRICE_HIGH:
        return [target_optimal, target_my_avto5]
    return [target_my_avto5]


# --- Группировка альбомов (несколько фото/видео в одном посте) ---------
#
# В альбоме Telegram подпись (текст) есть только у ОДНОГО сообщения из
# группы (общий grouped_id), у остальных text пустой. Раньше это тихо
# пропускалось (пустой text -> return без лога) — из-за этого backfill по
# N последних СООБЩЕНИЙ мог не дать ни одного реального ПОСТА, если все N
# оказались частью одного альбома без текстового элемента в выборке.

def group_backfill_messages(messages):
    """messages — список Message из iter_messages (любой порядок).
    Возвращает список групп (списков Message), сохраняя порядок первого
    появления группы; одиночные посты — группы из одного элемента."""
    order = []
    groups = {}
    for m in messages:
        key = m.grouped_id if m.grouped_id is not None else f"single-{m.id}"
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(m)
    return [groups[k] for k in order]


# --- Удаление водяного знака (только winner_auto_club) ------------------
#
# Согласовано с собственником канала лично пользователем (24.08.2026,
# "с собственником переговорили он не против") — без этого согласия
# правку чужих фото делать было бы нельзя, даже технически возможную.
#
# v1 (24-25.08.2026) — multi-scale template matching (cv2.matchTemplate).
# ОТКАЗАЛИСЬ от подхода (T-85, 26.08.2026, реальные фото боевого прогона —
# "фиаско полное, посмотри какие огромные закраски бейджа"): лучшее
# совпадение (score 0.55-0.62) ни разу не попало на настоящий бейдж —
# стабильно ложилось на однотонный фон-штору, а на фото салона (где
# бейджа нет вообще) тоже уверенно "находило" случайное место и портило
# его. Причина — сырое попиксельное сравнение с 5 вырезанными шаблонами
# слишком чувствительно к освещению/ракурсу/JPEG-сжатию конкретного кадра,
# а канал явно накладывает бейдж минимум в двух цветовых вариантах (светлая
# табличка и тёмная табличка — оба видны на реальных фото, шаблоны в
# watermark_templates/ покрывали не все случаи), из-за чего единый порог
# совпадения не отличал "нашёл бейдж" от "нашёл случайный однотонный фон".
#
# v2 (26.08.2026) — распознавание текста (Tesseract OCR) вместо пиксельного
# сравнения с шаблоном. Бейдж на этом канале — ВСЕГДА один и тот же
# читаемый текст ("WINNER AUTO CLUB"), а не абстрактный узор, поэтому
# вместо "похоже по пикселям на вырезанный образец" ищем буквально "есть ли
# эти слова на фото" — устойчиво к смене цветовой схемы таблички, ракурсу и
# сжатию конкретного кадра, поскольку не завязано на конкретные пиксели
# шаблона. Область поиска сужена до нижних углов кадра (бейдж на всех
# присланных пользователем реальных фото висел на бампере слева или справа
# снизу — никогда не в центре и не в верхней половине) — это и ускоряет
# OCR (не гоняем его по всему кадру), и снижает риск случайного совпадения
# где-то ещё в кадре. Проверяем обе полярности (светлый текст на тёмном
# фоне / тёмный на светлом), т.к. на реальных фото подтверждены оба
# варианта таблички. Сравнение нечёткое (расстояние Левенштейна) — Tesseract
# на мелком/сжатом тексте иногда путает буквы (WINNER -> WINNEA и т.п.),
# точное совпадение было бы слишком хрупким. Решение "это бейдж": хотя бы
# одно почти точное совпадение слова (расстояние <=1) ЛИБО совпали 2+
# разных слова из "WINNER"/"AUTO"/"CLUB" сразу — единичное слабое
# fuzzy-совпадение само по себе не считается (риск случайного совпадения
# короткого слова вроде "AUTO" на постороннем тексте в кадре).
# Как и раньше: если бейдж не найден уверенно — фото не трогаем и шлём как
# есть. Лучше пропустить реальный бейдж, чем испортить случайное место на
# фото — тот же принцип, что и в v1, порог теперь просто основан на
# содержимом (реальных словах), а не на пиксельном сходстве с образцом.
# Проверено на 5 реальных фото из жалобы пользователя (T-85): 3 фото с
# настоящим бейджем (перед/зад Jeep) — найден и закрашен на 2 из 3 (третье,
# с более сжатым/нечётким ракурсом, OCR не распознал уверенно — фото ушло
# как есть, это ожидаемое поведение "лучше пропустить", не регресс);
# 2 фото салона без бейджа вообще — ни одного ложного срабатывания (в v1
# ложно закрашивались оба).
#
# Ограничение осталось прежним — только фото. Для видео с тем же бейджем
# есть рабочий прототип, watermark_video.py (переделан 26.08.2026, T-85, на
# ту же OCR-логику, что и здесь, + быстрый локальный трекинг кадр-к-кадру
# между OCR-якорями; проверен на реальном тестовом видео) — но он НЕ
# подключён к этому файлу, ни handle_group(), ни _prepare_media_list() его
# не вызывают (см. TASKS.md T-85 — там же про то, что осталось для
# интеграции: скачивание видео, вызов process_video() через
# asyncio.to_thread, повторная загрузка результата в Telegram).

_BADGE_TARGET_WORDS = ("WINNER", "AUTO", "CLUB")
_BADGE_STRONG_MAX_DIST = 1  # "почти точное" совпадение слова (расстояние Левенштейна)
_BADGE_MIN_DISTINCT_WORDS = 2  # либо совпали хотя бы 2 разных слова (слабее, но вместе — тоже принимаем)
_BADGE_PAD_FRAC_X = 0.55  # запас вокруг найденного текста по ширине — OCR обычно ловит не все 3 слова таблички
_BADGE_PAD_FRAC_Y = 0.5


def _levenshtein(a, b):
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _fuzzy_badge_word(word):
    """Сопоставляет распознанное OCR-слово с одним из целевых слов бейджа
    с допуском на ошибки распознавания. Возвращает (слово, расстояние)
    лучшего совпадения или None, если ни одно не подошло достаточно близко."""
    if len(word) < 3:
        return None
    best = None
    for target in _BADGE_TARGET_WORDS:
        d = _levenshtein(word, target)
        if d <= max(1, len(target) // 3) and (best is None or d < best[1]):
            best = (target, d)
    return best


def _ocr_badge_hits(gray, scale=3, psm=11):
    """Прогоняет Tesseract по одному варианту (светлый или инвертированный)
    фрагмента и возвращает найденные слова бейджа — координаты уже в
    масштабе ИСХОДНОГО (не увеличенного для OCR) фрагмента."""
    upscaled = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    data = pytesseract.image_to_data(upscaled, config=f"--psm {psm}", output_type=pytesseract.Output.DICT)
    hits = []
    for i in range(len(data["text"])):
        txt = re.sub(r"[^A-Za-z]", "", data["text"][i]).upper()
        conf = float(data["conf"][i]) if data["conf"][i] not in ("-1", "") else -1
        if not txt or conf < 20:
            continue
        match = _fuzzy_badge_word(txt)
        if match is None:
            continue
        target, dist = match
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        hits.append((target, dist, x / scale, y / scale, w / scale, h / scale))
    return hits


def _badge_corner_regions(img):
    """Нижние левый/правый углы кадра — единственное место, где бейдж
    реально встречается на присланных пользователем фото (T-85)."""
    h, w = img.shape[:2]
    band_y0, band_y1 = int(h * 0.62), int(h * 0.88)
    return (
        (0, band_y0, int(w * 0.30), band_y1),
        (int(w * 0.70), band_y0, w, band_y1),
    )


def _find_badge_box(img, regions=None):
    """Ищет бейдж WINNER AUTO CLUB по тексту в заданных областях кадра
    (по умолчанию — нижние углы, см. _badge_corner_regions; видео-пайплайн
    передаёт другой набор регионов — там бейдж встречается и по центру
    низа кадра, не только по углам). Возвращает плотный (x, y, w, h) вокруг
    распознанных слов, либо None, если уверенного совпадения нет — тогда
    кадр/фото не трогаем."""
    if regions is None:
        regions = _badge_corner_regions(img)
    all_hits = []
    for sx0, sy0, sx1, sy1 in regions:
        crop = img[sy0:sy1, sx0:sx1]
        if crop.size == 0:
            continue
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        for variant in (gray, 255 - gray):
            for target, dist, x, y, ww, hh in _ocr_badge_hits(variant):
                all_hits.append((target, dist, sx0 + x, sy0 + y, ww, hh))

    if not all_hits:
        return None

    # На каждое целевое слово оставляем только лучшее (наименьшее расстояние) совпадение
    best_per_word = {}
    for target, dist, x, y, ww, hh in all_hits:
        if target not in best_per_word or dist < best_per_word[target][0]:
            best_per_word[target] = (dist, x, y, ww, hh)

    strong = any(dist <= _BADGE_STRONG_MAX_DIST for dist, *_ in best_per_word.values())
    if not strong and len(best_per_word) < _BADGE_MIN_DISTINCT_WORDS:
        return None

    xs0 = min(x for _, x, y, ww, hh in best_per_word.values())
    ys0 = min(y for _, x, y, ww, hh in best_per_word.values())
    xs1 = max(x + ww for _, x, y, ww, hh in best_per_word.values())
    ys1 = max(y + hh for _, x, y, ww, hh in best_per_word.values())
    return int(xs0), int(ys0), int(xs1 - xs0), int(ys1 - ys0)


def remove_watermark(image_bytes):
    """Убирает бейдж WINNER AUTO CLUB с фото (JPEG/PNG-байты на входе и
    выходе) сплошной заливкой найденной области. Если знак не найден
    уверенно — возвращает исходные байты без изменений."""
    if pytesseract is None:
        logger.warning("pytesseract не установлен (см. requirements.txt) — remove_watermark пропущена, фото без изменений")
        return image_bytes

    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return image_bytes

    try:
        box = _find_badge_box(img)
    except pytesseract.TesseractNotFoundError:
        # pytesseract (Python-пакет) стоит, а сам бинарь tesseract-ocr на
        # машине — нет (apt install tesseract-ocr, отдельно от pip install
        # pytesseract из requirements.txt). Не роняем обработку поста из-за
        # этого — просто не трогаем фото, как и при любом другом "не нашли".
        logger.warning("tesseract-ocr не установлен в системе (нужен `apt install tesseract-ocr` на VPS) — remove_watermark пропущена, фото без изменений")
        return image_bytes
    if box is None:
        logger.info("Водяной знак не найден уверенно — фото без изменений")
        return image_bytes

    x, y, w, h = box
    # OCR обычно распознаёт не все 3 слова таблички (и никогда — саму
    # табличку/рамку целиком, только буквы) — расширяем найденный бокс с
    # заметным запасом, чтобы накрыть табличку полностью, включая
    # нераспознанное слово и фон вокруг текста.
    pad_x = int(w * _BADGE_PAD_FRAC_X) + 10
    pad_y = int(h * _BADGE_PAD_FRAC_Y) + 8
    x0, y0 = max(0, x - pad_x), max(0, y - pad_y)
    x1, y1 = min(img.shape[1], x + w + pad_x), min(img.shape[0], y + h + pad_y)

    roi = img[y0:y1, x0:x1]
    # Сплошная заливка средним цветом области — блюр не убирает бейдж
    # полностью (жалоба пользователя 25.08.2026: "за блюром проглядывается
    # логотип винера"), заливке нечем "просвечивать".
    fill_color = cv2.mean(roi)[:3]
    result = img.copy()
    result[y0:y1, x0:x1] = fill_color

    ok, encoded = cv2.imencode(".jpg", result, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    if not ok:
        return image_bytes
    return encoded.tobytes()


# Источники, чьи фото нужно скачать/обработать перед отправкой (а не просто
# переслать оригинальный Telegram-media-хэндл, как для остальных).
#
# T-85 (26.08.2026): remove_watermark() для winner_auto_club была временно
# отключена (PHOTO_PROCESSORS пуст) после жалобы на v1 (template matching,
# см. комментарий над remove_watermark). Восстановлена здесь после перехода
# на OCR-детект (v2) — тот же день, проверено на всех 5 реальных фото из
# жалобы (см. комментарий выше). winner_auto_club всё ещё в TEST_ONLY_SOURCES
# (см. main()) — то есть новая обработка сейчас идёт ТОЛЬКО в тестовую
# группу, в боевые каналы не публикуется, пока пользователь не проверит
# результат на живом трафике и не подтвердит перевод источника в боевые
# (как это уже было для tamsyam26, см. TASKS.md T-82/T-85).
PHOTO_PROCESSORS = {"winner_auto_club": remove_watermark}


async def _prepare_media_list(client, source_username, messages):
    """Для большинства источников просто передаём Telegram media как есть —
    без перекачки. Для источников из PHOTO_PROCESSORS фото скачиваем,
    прогоняем через процессор (сейчас — удаление водяного знака) и шлём уже
    новыми байтами; видео не трогаем (см. комментарий выше).

    T-85 (26.08.2026): processor теперь делает OCR (Tesseract) вместо
    простого template matching — заметно медленнее (секунды, не доли
    секунды, на фото). Раньше `processor(raw)` вызывался прямо в event
    loop'е — с OCR это надолго блокировало бы ВЕСЬ asyncio event loop
    (другие каналы/очередь отложенных постов ждали бы), особенно на
    альбомах из нескольких фото. Поэтому вызов вынесен в отдельный поток
    через `asyncio.to_thread`."""
    processor = PHOTO_PROCESSORS.get(source_username)
    media_list = []
    for m in messages:
        if not m.media:
            continue
        if processor and m.photo:
            try:
                raw = await client.download_media(m, file=bytes)
                processed = await asyncio.to_thread(processor, raw)
                bio = io.BytesIO(processed)
                bio.name = f"{m.id}.jpg"
                media_list.append(bio)
            except Exception:
                logger.exception(
                    "[%s#%s] ошибка при обработке фото (водяной знак) — шлю оригинал",
                    source_username, m.id,
                )
                media_list.append(m.media)
        else:
            media_list.append(m.media)
    return media_list


async def handle_group(client, source_username, messages, targets_cfg, eur_rub_rate, usd_rub_rate, dry_run, video_dry_run, test_group, state, feedback_bot_username=None, test_only_sources=frozenset(), video_dry_run_sources=frozenset({"winner_auto_club"})):
    ids = [m.id for m in messages]
    text = next((m.raw_text for m in messages if m.raw_text and m.raw_text.strip()), "")
    if not text.strip():
        logger.info("[%s#%s] группа без текста (альбом без подписи в выборке?) — пропускаю", source_username, ids)
        return

    parser = SOURCE_PARSERS.get(source_username)
    if parser is None:
        # T-82 (25.08.2026, запрошено пользователем — добавили @TamSyam26
        # как источник: "с этой группы тоже парсим объявления", формат цены
        # под парсер ещё не разбирали, пользователь сказал "пока в тест
        # группу"). Раньше источник без парсера в SOURCE_PARSERS молча
        # пропускался целиком — теперь вместо этого шлём пост как есть
        # (общая чистка текста + футер, БЕЗ расчёта цены и строки с ценой)
        # только в тестовую группу, никогда в боевые — пока не появится
        # парсер под конкретный формат этого источника, роутинг по цене для
        # него в принципе невозможен.
        if not test_group:
            logger.warning(
                "Нет парсера для источника %s и не задана тестовая группа — пропускаю (нужен либо парсер, либо TEST_GROUP_INVITE)",
                source_username,
            )
            return
        parsed = None
        price_rub = None
        real_targets = []
        post_text = build_repost_text(text, source_username, None, None, feedback_bot_username)
    else:
        parsed = parser(text)
        if parsed is None:
            logger.info("[%s#%s] не распознан как объявление об авто — пропускаю", source_username, ids)
            return

        price_rub = compute_price_rub(parsed, eur_rub_rate, usd_rub_rate)
        if price_rub is None:
            logger.info("[%s#%s] не удалось посчитать цену в рублях — пропускаю, не рискую с каналом", source_username, ids)
            return

        real_targets = route_targets(price_rub, targets_cfg["optimal"], targets_cfg["my_avto5"])
        post_text = build_repost_text(text, source_username, price_rub, parsed.get("price_usd_total"), feedback_bot_username)

    # 25.08.2026 (решение пользователя): фото/текст уже можно в боевые группы,
    # а видео — пока нет (для winner_auto_club водяной знак с видео ещё не
    # снимается, публиковать с логотипом источника в боевые нельзя). Поэтому
    # DRY_RUN и video_dry_run — теперь ДВА независимых переключателя:
    # пост с видео всегда идёт в тестовую группу, пока video_dry_run не
    # выключат отдельно (когда обработка видео подтвердится на реальных
    # постах), независимо от общего DRY_RUN. Пост без видео — как обычно,
    # по общему DRY_RUN. Альбом (фото+видео вместе) публикуется ЦЕЛИКОМ в
    # одно место — не разбиваем медиа одного поста на разные группы.
    #
    # Роутинг решается ДО подготовки медиа (скачивание/удаление водяного
    # знака) — если пост в итоге откладывается в очередь (T-84, окно
    # постинга), незачем тратить время на обработку фото сейчас, это же
    # самое handle_group сделает заново, когда очередь разберёт его позже.
    has_video = any(getattr(m, "video", None) for m in messages)
    if parser is None or source_username in test_only_sources:
        # Источник без парсера (роутинг по цене невозможен в принципе) или
        # явно в TEST_ONLY_SOURCES (парсер есть, но ещё не обкатан на
        # реальном трафике, T-82) — всегда только тест, независимо от
        # DRY_RUN/video_dry_run.
        send_targets = [test_group] if test_group else []
        note = " (нет парсера — показ как есть -> тестовая)" if parser is None else f" (источник ещё не проверен на боевом трафике -> тестовая, боевые цели были бы: {real_targets})"
    elif has_video and video_dry_run and source_username in video_dry_run_sources:
        # T-83 (25.08.2026): раньше это правило било по видео ЛЮБОГО
        # источника — теперь только по source_username из
        # video_dry_run_sources (по умолчанию winner_auto_club, у него
        # реальная причина — водяной знак на видео ещё не снимается).
        send_targets = [test_group] if test_group else []
        note = f" (видео -> тестовая, боевые цели были бы: {real_targets})"
    elif dry_run:
        send_targets = [test_group] if test_group else []
        note = f" (боевые цели были бы: {real_targets})"
    elif not _in_posting_window():
        # T-84 (26.08.2026, запрошено пользователем — "постим с 8 до 21:30
        # по мск в май авто и май авто оптимал?"): вне окна пост в БОЕВЫЕ
        # каналы не отправляем — откладываем в userbot_pending_queue.json,
        # _pending_queue_flusher() отправит его, когда окно снова откроется
        # (не отбрасываем). Тестовую группу это ограничение не касается —
        # она уже отфильтрована ветками выше и публикуется в любое время.
        _queue_pending(source_username, ids)
        logger.info(
            "[%s#%s] вне окна постинга (%s–%s МСК, сейчас %s) — отложено в очередь, боевые цели: %s",
            source_username, ids, POSTING_WINDOW_START, POSTING_WINDOW_END,
            _now_msk().time().strftime("%H:%M"), real_targets,
        )
        return
    else:
        send_targets = real_targets
        note = ""

    media_list = await _prepare_media_list(client, source_username, messages)

    price_str = (f"{price_rub:,}".replace(",", " ") + " ₽") if price_rub is not None else "не определена (нет парсера для источника)"
    logger.info(
        "[%s#%s] цена=%s%s, медиа=%s\n%s",
        source_username, ids, price_str, note, len(media_list), post_text,
    )

    for target in send_targets:
        try:
            if media_list:
                # BytesIO (обработанные фото winner_auto_club) — курсор после
                # предыдущей отправки в конце файла, перематываем перед
                # каждой новой целью, иначе Telegram получит пустой файл.
                for item in media_list:
                    if isinstance(item, io.BytesIO):
                        item.seek(0)
                try:
                    await client.send_message(target, post_text, file=media_list, parse_mode="md", link_preview=False)
                except MediaCaptionTooLongError:
                    # Подпись реально не влезла (Telegram сам так решил) — шлём
                    # фото/видео без подписи, текст отдельным сообщением следом.
                    logger.info("[%s#%s] подпись слишком длинная для медиа, шлю текст отдельным сообщением", source_username, ids)
                    for item in media_list:
                        if isinstance(item, io.BytesIO):
                            item.seek(0)
                    await client.send_message(target, "", file=media_list)
                    await client.send_message(target, post_text, parse_mode="md", link_preview=False)
            else:
                await client.send_message(target, post_text, parse_mode="md", link_preview=False)
            logger.info("[%s#%s] запощено в %s", source_username, ids, target)
        except Exception:
            logger.exception("[%s#%s] ошибка при постинге в %s", source_username, ids, target)

    _mark_sent(state, source_username, ids)
    save_state(state)


async def _pending_queue_flusher(client, targets_cfg, eur_rub_rate, usd_rub_rate, dry_run, video_dry_run, test_group, state, feedback_bot_username, test_only_sources, video_dry_run_sources, poll_seconds=120):
    """T-84: фоновая задача, раз в poll_seconds проверяет, открыто ли окно
    постинга (08:00-21:30 МСК) и, если да, разбирает userbot_pending_queue.json
    — посты, которые в своё время попали туда из-за window-ограничения в
    handle_group(). Очередь сразу очищается, а не после отправки: если
    отправка какого-то элемента снова не удастся (не удалось получить
    сообщения, окно закрылось прямо во время разбора и т.п.), он вернётся в
    очередь сам — через _queue_pending() (при ошибке get_messages) или через
    сам handle_group() (если увидит, что окно снова закрыто).
    Критическая защита от дублей: перед повторной обработкой каждый элемент
    проверяется через _already_sent() — на случай, если пост уже ушёл другим
    путём (например, бэкфиллом после рестарта сервиса), пока сидел в очереди."""
    while True:
        await asyncio.sleep(poll_seconds)
        try:
            if not _in_posting_window():
                continue
            queue = load_pending_queue()
            items = queue.get("items", [])
            if not items:
                continue
            save_pending_queue({"items": []})
            logger.info("--- Окно постинга открыто, разбираю очередь отложенных: %s поста(ов) ---", len(items))
            for item in items:
                source_username = item["source_username"]
                ids = item["ids"]
                if _already_sent(state, source_username, ids):
                    logger.info("[%s#%s] уже отправлено другим путём, пока сидел в очереди — пропускаю", source_username, ids)
                    continue
                try:
                    fetched = await client.get_messages(source_username, ids=ids)
                    group = [m for m in fetched if m is not None]
                except Exception:
                    logger.exception("[%s#%s] не удалось получить сообщения из очереди отложенных — верну в очередь, попробую позже", source_username, ids)
                    _queue_pending(source_username, ids)
                    continue
                if not group:
                    logger.warning("[%s#%s] сообщения из очереди отложенных больше недоступны (удалены?) — убираю из очереди", source_username, ids)
                    continue
                await handle_group(client, source_username, group, targets_cfg, eur_rub_rate, usd_rub_rate, dry_run, video_dry_run, test_group, state, feedback_bot_username, test_only_sources, video_dry_run_sources)
        except Exception:
            logger.exception("Ошибка в фоновой задаче отправки отложенных постов — продолжаю, попробую на следующем цикле")


async def _collect_messages(client, source, limit):
    return [m async for m in client.iter_messages(source, limit=limit)]


async def ensure_test_group(client, invite_url):
    """Вступает в тестовую группу по инвайт-ссылке (+hash), если ещё не участник."""
    if not invite_url:
        return None
    invite_hash = invite_url.rstrip("/").split("/")[-1].lstrip("+")
    try:
        result = await client(ImportChatInviteRequest(invite_hash))
        chat = result.chats[0]
        logger.info("Вступил в тестовую группу: %s", chat.title)
        return chat
    except UserAlreadyParticipantError:
        entity = await client.get_entity(invite_url)
        return entity


async def main():
    env = load_env()
    api_id = env.get("API_ID")
    api_hash = env.get("API_HASH")
    proxy = build_proxy(env.get("PROXY_URL"))
    # .lower() — источники и ключи SOURCE_PARSERS/PHOTO_PROCESSORS/state
    # должны совпадать регистронезависимо (winner_auto_club пишется в ТГ с
    # заглавных букв: @Winner_Auto_Club); event.chat.username в живом потоке
    # уже приводится к нижнему регистру ниже, теперь и здесь для бэкфилла.
    sources = [s.strip().lstrip("@").lower() for s in env.get("SOURCES", "artalexgroup,bezpokrasa").split(",") if s.strip()]
    target_optimal = env.get("TARGET_OPTIMAL", "@My_Avto_Optimal")
    target_my_avto5 = env.get("TARGET_MY_AVTO5", "@MY_Avto5")
    eur_rub_rate = float(env.get("EUR_RUB_RATE", "100"))
    usd_rub_rate = float(env.get("USD_RUB_RATE", "80"))
    # T-78 (25.08.2026): бот обратной связи — если задан в конфиге, в футер
    # каждого поста добавляется ссылка на него (см. build_footer()). Не
    # задан — футер как раньше, без строки про бота.
    feedback_bot_username = env.get("FEEDBACK_BOT_USERNAME", "").strip().lstrip("@")
    dry_run = env.get("DRY_RUN", "true").strip().lower() != "false"
    # T-79 (25.08.2026, решение пользователя): фото/текст уже можно в
    # боевые группы, видео — пока нет (снятие вотемарка с видео ещё не
    # подключено в проде). Отдельный переключатель именно для постов с
    # видео — держим true (тестовая группа), пока video-пайплайн не
    # подтвердится на реальных постах, независимо от общего DRY_RUN.
    video_dry_run = env.get("VIDEO_DRY_RUN", "true").strip().lower() != "false"
    # T-83 (25.08.2026, обнаружено пользователем — "почему в тест групу
    # пришли посты из безпокраса?"): раньше video_dry_run применялся ко
    # ВСЕМ источникам без разбора, хотя причина ограничения (водяной знак
    # на видео) актуальна только для winner_auto_club — видео bezpokrasa
    # без причины уводило в тест вместе с ним. Теперь video_dry_run
    # применяется только к источникам из этого списка (решение
    # пользователя — "в боевые сразу" для bezpokrasa).
    video_dry_run_sources = {s.strip().lstrip("@").lower() for s in env.get("VIDEO_DRY_RUN_SOURCES", "winner_auto_club").split(",") if s.strip()}
    # T-82 (25.08.2026, добавлен источник @TamSyam26 — "пока в тест
    # группу"): источники в этом списке ВСЕГДА идут только в тестовую
    # группу, независимо от общего DRY_RUN/video_dry_run — для новых
    # источников, чей парсер/цена ещё не обкатаны на реальном трафике.
    # Убрать источник из списка (или очистить весь список), когда
    # результат в тесте устроит — тогда пойдёт по обычной логике DRY_RUN.
    # tamsyam26 убран отсюда 26.08.2026 — пользователь увидел 2 реальных
    # поста в тесте (GEELY Coolray, KAMIQ), парсинг/цена/доставка выглядят
    # верно, подтвердил "давай в боевую тогда конечно". Теперь идёт по
    # обычной логике DRY_RUN, как остальные проверенные источники.
    # T-85 (26.08.2026): winner_auto_club добавлен сюда же — remove_watermark()
    # отключена (см. PHOTO_PROCESSORS выше, ни разу не нашла настоящий бейдж
    # на реальных фото), пока в проде фото шли бы с чужим бейджем без
    # обработки. Держим в тесте, пока не появится рабочее распознавание.
    test_only_sources = {s.strip().lstrip("@").lower() for s in env.get("TEST_ONLY_SOURCES", "winner_auto_club").split(",") if s.strip()}
    # Бэкфилл при старте работает и в боевом режиме, не только в DRY_RUN —
    # чтобы при первом запуске на реальные каналы сразу подтянуть немного
    # свежего контента, а не просто ждать новых постов с нуля. Благодаря
    # дедупу по state (last_id) это безопасно и при рестартах сервиса —
    # повторно уже отправленные посты не полезут.
    backfill_limit = int(env.get("TEST_BACKFILL_LIMIT", "15"))
    test_group_invite = env.get("TEST_GROUP_INVITE", "").strip()

    if not (api_id and api_hash):
        raise SystemExit("userbot_config.env: нужны API_ID/API_HASH (см. userbot_login.py)")

    targets_cfg = {"optimal": target_optimal, "my_avto5": target_my_avto5}
    state = load_state()

    client = TelegramClient("myavto_userbot", int(api_id), api_hash, proxy=proxy)
    await client.start()

    test_group = None
    # Тестовая группа нужна, если её вообще может использовать хоть один из
    # режимов — общий DRY_RUN, video_dry_run (посты с видео) или
    # test_only_sources (конкретные источники) — любой из них может увести
    # пост в тест, даже когда общий режим уже боевой.
    if (dry_run or video_dry_run or test_only_sources) and test_group_invite:
        test_group = await ensure_test_group(client, test_group_invite)

    # T-84: фоновая задача разбирает очередь постов, отложенных из-за окна
    # постинга (08:00-21:30 МСК) — не блокирует ни бэкфилл, ни живой поток
    # сообщений ниже, просто периодически (раз в ~120с) проверяет очередь.
    # Запускаем ПОСЛЕ того, как test_group определена выше — иначе задача
    # захватила бы в замыкании None и не смогла бы роутить в тест, если
    # отложенный элемент внутри handle_group всё же попадёт в тестовую ветку.
    asyncio.create_task(_pending_queue_flusher(
        client, targets_cfg, eur_rub_rate, usd_rub_rate, dry_run, video_dry_run,
        test_group, state, feedback_bot_username, test_only_sources, video_dry_run_sources,
    ))

    logger.info(
        "Режим: %s | видео: %s | источники: %s | цели: %s / %s",
        "DRY_RUN -> тестовая группа" if dry_run else "БОЕВОЙ",
        "DRY_RUN -> тестовая группа" if video_dry_run else "БОЕВОЙ",
        sources, target_optimal, target_my_avto5,
    )

    if backfill_limit > 0:
        logger.info("--- Стартовый бэкфилл: последние %s сообщений каждого источника (с учётом альбомов и уже отправленного ранее) ---", backfill_limit)
        for source in sources:
            logger.info("[%s] запрашиваю историю (таймаут 25с)...", source)
            try:
                raw_messages = await asyncio.wait_for(_collect_messages(client, source, backfill_limit), timeout=25)
            except asyncio.TimeoutError:
                logger.error("[%s] таймаут при получении истории — пропускаю источник, проверь сеть/прокси/доступ юзербота к каналу", source)
                continue
            except Exception:
                logger.exception("[%s] ошибка при получении истории — пропускаю источник", source)
                continue
            groups = group_backfill_messages(raw_messages)
            logger.info("[%s] %s сообщений -> %s постов после склейки альбомов", source, len(raw_messages), len(groups))
            skipped = 0
            for group in groups:
                if _already_sent(state, source, [m.id for m in group]):
                    # Уже публиковали этот пост в прошлом запуске — не дублируем
                    # (важно при автозапуске сервиса через systemd: без этой
                    # проверки каждый рестарт заново постил бы весь бэкфилл).
                    skipped += 1
                    continue
                await handle_group(client, source, group, targets_cfg, eur_rub_rate, usd_rub_rate, dry_run, video_dry_run, test_group, state, feedback_bot_username, test_only_sources, video_dry_run_sources)
            if skipped:
                logger.info("[%s] %s из %s постов бэкфилла уже были обработаны раньше — пропущены", source, skipped, len(groups))
        logger.info("--- Конец стартового бэкфилла, жду новые посты в реальном времени ---")

    # Живой поток: элементы одного альбома прилетают отдельными событиями
    # почти одновременно — копим по grouped_id и обрабатываем группой через
    # небольшую паузу, а не поштучно.
    pending_albums = {}
    pending_tasks = {}

    async def flush_album(gid, source_username):
        await asyncio.sleep(2.0)
        group = pending_albums.pop(gid, None)
        pending_tasks.pop(gid, None)
        if not group:
            return
        ids = [m.id for m in group]
        if _already_sent(state, source_username, ids):
            # Telegram иногда повторно доставляет событие после
            # переподключения (нестабильная сеть на VPS уже такое
            # устраивала) — этот пост уже был отправлен, не дублируем.
            logger.info("[%s#%s] уже обработано ранее (повтор доставки?) — пропускаю", source_username, ids)
            return
        await handle_group(client, source_username, group, targets_cfg, eur_rub_rate, usd_rub_rate, dry_run, video_dry_run, test_group, state, feedback_bot_username, test_only_sources, video_dry_run_sources)

    @client.on(events.NewMessage(chats=sources))
    async def on_new_message(event):
        source_username = (event.chat.username or "").lower()
        msg = event.message
        if msg.grouped_id is None:
            if _already_sent(state, source_username, [msg.id]):
                logger.info("[%s#%s] уже обработано ранее (повтор доставки?) — пропускаю", source_username, [msg.id])
                return
            await handle_group(client, source_username, [msg], targets_cfg, eur_rub_rate, usd_rub_rate, dry_run, video_dry_run, test_group, state, feedback_bot_username, test_only_sources, video_dry_run_sources)
            return
        gid = msg.grouped_id
        pending_albums.setdefault(gid, []).append(msg)
        if gid not in pending_tasks:
            pending_tasks[gid] = asyncio.create_task(flush_album(gid, source_username))

    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
