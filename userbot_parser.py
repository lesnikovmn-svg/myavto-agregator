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

Известные упрощения v1 (см. T-77 в TASKS.md):
- Альбомы (несколько фото в одном посте) обрабатываются по первому
  найденному медиа-файлу поста, не всей группой.
- Курс EUR/RUB и USD/RUB — константы в конфиге, обновлять вручную.
- Наценка на итоговую цену — грубая оценка (сумма уже данных в посте
  составляющих), не точный калькулятор растаможки.
- winner_auto_club (добавлен 25.08.2026): с фото автоматически убирается
  водяной знак канала (согласовано с собственником, template matching +
  inpaint, см. remove_watermark ниже); видео с тем же знаком НЕ
  обрабатывается — публикуется как есть.
"""
import asyncio
import io
import json
import logging
import re
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import cv2
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

    if source_username == "bezpokrasa" and price_rub is not None:
        price_str = f"{price_rub:,}".replace(",", " ")
        price_line = f"Цена под ключ в Москве: {price_str} \u20bd"
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


SOURCE_PARSERS = {
    "artalexgroup": parse_eu_wholesale,
    "bezpokrasa": parse_china_invoice,
    "winner_auto_club": parse_winner_auto_club,
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
# Подход: multi-scale template matching (cv2.matchTemplate,
# TM_CCOEFF_NORMED) находит бейдж "WINNER AUTO CLUB" на фото в неизвестном
# заранее масштабе/позиции, затем область сильно размывается (Gaussian blur).
#
# Раньше вместо блюра использовался cv2.inpaint (INPAINT_TELEA) — он неплохо
# работал там, где вокруг бейджа была текстура для "дорисовки" (решётка
# радиатора), но бейдж почти всегда висит именно на месте номера — там
# заведомо нет настоящей текстуры для реконструкции, и inpaint давал плоское
# мутное пятно ("замылил", жалоба пользователя 25.08.2026). Обычный сильный
# блюр в этом месте выглядит естественно — ровно так уже выглядит блюр
# настоящего номера на части фото источника, так что дополнительный блюр
# бейджа не выделяется на общем фоне.
#
# Если знак не найден с уверенным совпадением — фото не трогаем и шлём как
# есть, чтобы не портить кадр ложным срабатыванием.
#
# v1 сознательно ограничен фото — видео с этим бейджем не обрабатываются
# (см. TASKS.md), нужен отдельный подход (кадр за кадром/трекинг).

# Канал использует несколько разных дизайнов бейджа (минимум два подтверждено
# на практике: светлый шаблон с горой и тёмный/текстурный шаблон — см.
# TASKS.md T-77) — перебираем все известные шаблоны из watermark_templates/
# и берём лучшее совпадение по всем сразу.
WATERMARK_TEMPLATES_DIR = Path(__file__).parent / "watermark_templates"
WATERMARK_TEMPLATE_GLOB = "winner_auto_club*.png"
_WATERMARK_MATCH_THRESHOLD = 0.6
_WATERMARK_SCALES = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5]
_WATERMARK_PAD = 8  # px, отступ вокруг найденного бокса перед inpaint

_watermark_templates_gray = None


def _load_watermark_templates():
    global _watermark_templates_gray
    if _watermark_templates_gray is None:
        paths = sorted(WATERMARK_TEMPLATES_DIR.glob(WATERMARK_TEMPLATE_GLOB))
        templates = []
        for p in paths:
            tmpl = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
            if tmpl is None:
                logger.warning("Не удалось загрузить шаблон водяного знака: %s — пропускаю", p)
                continue
            templates.append(tmpl)
        if not templates:
            raise RuntimeError(f"Не найдено ни одного шаблона водяного знака в {WATERMARK_TEMPLATES_DIR}")
        _watermark_templates_gray = templates
    return _watermark_templates_gray


def _find_watermark_box(image_gray, template_gray):
    """Перебирает несколько масштабов шаблона — бейдж на разных фото может
    быть разного размера в зависимости от разрешения кадра у источника.
    Возвращает (x, y, w, h, score) лучшего совпадения для ОДНОГО шаблона."""
    best = None
    th, tw = template_gray.shape[:2]
    for scale in _WATERMARK_SCALES:
        w, h = int(tw * scale), int(th * scale)
        if w < 8 or h < 8 or w > image_gray.shape[1] or h > image_gray.shape[0]:
            continue
        resized = cv2.resize(template_gray, (w, h))
        result = cv2.matchTemplate(image_gray, resized, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if best is None or max_val > best[4]:
            best = (max_loc[0], max_loc[1], w, h, max_val)
    return best


def _find_best_watermark_box(image_gray, templates_gray):
    """Прогоняет image_gray через все известные шаблоны и возвращает лучший
    результат (по score) среди них — так один вызов ловит любой из
    известных дизайнов бейджа."""
    best = None
    for template_gray in templates_gray:
        box = _find_watermark_box(image_gray, template_gray)
        if box is not None and (best is None or box[4] > best[4]):
            best = box
    return best


def remove_watermark(image_bytes):
    """Убирает бейдж WINNER AUTO CLUB с фото (JPEG/PNG-байты на входе и
    выходе) сильным блюром найденной области. Если знак не найден уверенно
    ни одним из известных шаблонов — возвращает исходные байты без
    изменений."""
    templates_gray = _load_watermark_templates()
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return image_bytes

    img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    box = _find_best_watermark_box(img_gray, templates_gray)
    if box is None or box[4] < _WATERMARK_MATCH_THRESHOLD:
        logger.info("Водяной знак не найден уверенно (score=%s) — фото без изменений", box[4] if box else None)
        return image_bytes

    x, y, w, h, score = box
    pad = _WATERMARK_PAD
    x0, y0 = max(0, x - pad), max(0, y - pad)
    x1, y1 = min(img.shape[1], x + w + pad), min(img.shape[0], y + h + pad)

    roi = img[y0:y1, x0:x1]
    roi_h, roi_w = roi.shape[:2]
    # Ядро блюра — половина меньшей стороны области (обязательно нечётное),
    # но не меньше 21px — иначе на крупных фото текст бейджа может остаться
    # частично читаемым.
    k = max(21, (min(roi_h, roi_w) // 2) | 1)
    blurred_roi = cv2.GaussianBlur(roi, (k, k), 0)
    result = img.copy()
    result[y0:y1, x0:x1] = blurred_roi

    ok, encoded = cv2.imencode(".jpg", result, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    if not ok:
        return image_bytes
    return encoded.tobytes()


# Источники, чьи фото нужно скачать/обработать перед отправкой (а не просто
# переслать оригинальный Telegram-media-хэндл, как для остальных).
PHOTO_PROCESSORS = {
    "winner_auto_club": remove_watermark,
}


async def _prepare_media_list(client, source_username, messages):
    """Для большинства источников просто передаём Telegram media как есть —
    без перекачки. Для источников из PHOTO_PROCESSORS фото скачиваем,
    прогоняем через процессор (сейчас — удаление водяного знака) и шлём уже
    новыми байтами; видео не трогаем (см. комментарий выше)."""
    processor = PHOTO_PROCESSORS.get(source_username)
    media_list = []
    for m in messages:
        if not m.media:
            continue
        if processor and m.photo:
            try:
                raw = await client.download_media(m, file=bytes)
                processed = processor(raw)
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


async def handle_group(client, source_username, messages, targets_cfg, eur_rub_rate, usd_rub_rate, dry_run, test_group, state, feedback_bot_username=None):
    ids = [m.id for m in messages]
    text = next((m.raw_text for m in messages if m.raw_text and m.raw_text.strip()), "")
    if not text.strip():
        logger.info("[%s#%s] группа без текста (альбом без подписи в выборке?) — пропускаю", source_username, ids)
        return

    parser = SOURCE_PARSERS.get(source_username)
    if parser is None:
        logger.warning("Нет парсера для источника %s, пропускаю", source_username)
        return

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
    media_list = await _prepare_media_list(client, source_username, messages)

    if dry_run:
        send_targets = [test_group] if test_group else []
        note = f" (боевые цели были бы: {real_targets})"
    else:
        send_targets = real_targets
        note = ""

    price_str = f"{price_rub:,}".replace(",", " ")
    logger.info(
        "[%s#%s] цена=%s ₽%s, медиа=%s\n%s",
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
    if dry_run and test_group_invite:
        test_group = await ensure_test_group(client, test_group_invite)

    logger.info(
        "Режим: %s | источники: %s | цели: %s / %s",
        "DRY_RUN -> тестовая группа" if dry_run else "БОЕВОЙ",
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
                await handle_group(client, source, group, targets_cfg, eur_rub_rate, usd_rub_rate, dry_run, test_group, state, feedback_bot_username)
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
        await handle_group(client, source_username, group, targets_cfg, eur_rub_rate, usd_rub_rate, dry_run, test_group, state, feedback_bot_username)

    @client.on(events.NewMessage(chats=sources))
    async def on_new_message(event):
        source_username = (event.chat.username or "").lower()
        msg = event.message
        if msg.grouped_id is None:
            if _already_sent(state, source_username, [msg.id]):
                logger.info("[%s#%s] уже обработано ранее (повтор доставки?) — пропускаю", source_username, [msg.id])
                return
            await handle_group(client, source_username, [msg], targets_cfg, eur_rub_rate, usd_rub_rate, dry_run, test_group, state, feedback_bot_username)
            return
        gid = msg.grouped_id
        pending_albums.setdefault(gid, []).append(msg)
        if gid not in pending_tasks:
            pending_tasks[gid] = asyncio.create_task(flush_album(gid, source_username))

    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
