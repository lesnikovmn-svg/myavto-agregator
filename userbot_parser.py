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

T-99 (30.08.2026, запрошено пользователем — "давай проверим почему не
автопостит?"): отдельная очередь userbot_manual_queue.json для постов БЕЗ
исходного сообщения в отслеживаемом канале (например, ролик, собранный
вручную из чужого скринкаста, с текстом, написанным руками) —
_pending_queue_flusher() выше для такого не подходит, он умеет только
заново СКАЧАТЬ уже существующее сообщение источника по id, а тут скачивать
неоткуда. queue_manual_post(text, media_paths, targets) кладёт готовый
пост в очередь, _manual_queue_flusher() разбирает её раз в ~60с и шлёт
через ТОТ ЖЕ живой client, что и остальной пайплайн — второй
Telethon-сессии не открывается, конфликтов с боевым сервисом нет. Файлы
из media_paths должны заранее лежать на этом же сервере (флашер их
никуда не скачивает). См. queue_manual_post.py — CLI-обёртка для запуска
прямо на сервере юзербота.

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
import uuid
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
    # T-97 (28.08.2026): реальный пост (GMC Sierra, tamsyam26) содержал живой
    # номер продавца прямо в тексте ("📞для участи 89288198007") — раньше
    # ловился только один захардкоженный номер (см. паттерн выше), любой
    # другой уходил в репост как есть. Пользователь: "в тексте номер
    # телефона не вычищен". Общий паттерн — российский номер в любом
    # написании (+7/8, с скобками/дефисами/пробелами или слитно) — вырезаем
    # строку целиком, как и остальные чужие контакты выше; наш собственный
    # футер с нашими номерами сюда не попадает (эти паттерны применяются
    # только к исходному тексту источника, до добавления футера).
    re.compile(r"(?:\+?7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}\b"),
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
    # T-96 (28.08.2026, честный fallback для постов без "под ключ" —
    # см. parse_tamsyam26): строка-цена без метки "Цена" (просто число+₽,
    # как в примере GMC Sierra: "5.900.000₽.") и отдельная строка про
    # город доставки ("с Доставкой до Ставрополя") — обе заменяются нашей
    # собранной строкой ниже, оставлять исходные не нужно (дублирование).
    re.compile(r"^\s*[\d][\d.,\s]*\s*₽\.?\s*$"),
    re.compile(r"^\s*с\s+[Дд]оставкой\s+до\s+\S+"),
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


def build_repost_text(raw_text, source_username=None, price_rub=None, price_usd=None, feedback_bot_username=None, price_eur=None, price_approximate=False, delivery_city=None):
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
        # должен противоречить нашей же строке с ценой ниже. T-96
        # (28.08.2026): но это верно только для "под ключ"-цены (наша
        # строка "под ключ в Краснодаре" ниже) — для честного fallback-
        # варианта (price_approximate=True) город продавца оставляем как
        # есть, подменять его на Краснодар как раз и было бы нечестно.
        if not price_approximate:
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
        if price_approximate:
            # T-96 (28.08.2026, решение пользователя — "показывать честно"):
            # нет "под ключ"-цены в посте, только ориентировочная с
            # доставкой в город продавца — не подписываем как "под ключ в
            # Краснодаре" (было бы неверно), показываем как есть.
            city_part = f", доставка до {delivery_city}" if delivery_city else ""
            price_line = f"Цена ориентировочная{city_part}: {price_str} ₽"
        else:
            price_line = f"Цена под ключ в Краснодаре: {price_str} " + "₽"
        body = f"{body}\n\n{price_line}" if body else price_line
    elif source_username == "winner_auto_club" and (price_usd is not None or price_eur is not None):
        # T-96 (28.08.2026): цена может быть и в $, и в € — раньше символ
        # был захардкожен как "$", из-за чего евровая цена показалась бы
        # пользователю как долларовая (в 1.1+ раза дешевле реальной).
        if price_usd is not None:
            price_str, symbol = f"{price_usd:,}", "$"
        else:
            price_str, symbol = f"{price_eur:,}", "€"
        price_line = f"Цена: {symbol}{price_str} (цена в Грузии). За точной ценой на момент сделки — пишите в личку."
        body = f"{body}\n\n{price_line}" if body else price_line

    footer = build_footer(feedback_bot_username)
    return f"{body}\n\n{footer}" if body else footer


# T-107 (01.09.2026, инстаграм-формат): подпись для видео, собранного
# auto_montage.build_short() (короткий вертикальный ролик с текстом НА
# видео) — пока уходит в ту же тестовую группу winner_auto_club, что и
# T-104 (см. TASKS.md), как черновик для проверки перед реальной
# публикацией в Instagram. НЕ переиспользует build_repost_text():
# - там в футере markdown-ссылка на бота ([Написать](https://t.me/...)) —
#   Instagram такую разметку не рендерит, ссылка ушла бы в подписи как
#   голый текст, это не то, что реально увидит подписчик в IG;
# - здесь вместо неё призыв к комментарию (см. auto_montage.CTA_TEXT —
#   тот же призыв дублируется и на самом видео, и в подписи, по данным
#   instagram-content-agent/content/2026-08-31_strategy_notes.md: у
#   my_avto5 сейчас 0 комментариев на reels, у единственного конкурента с
#   заметными комментариями в подписи прямой повторяющийся призыв написать
#   слово в комментариях — это самый чёткий паттерн вовлечённости во всей
#   выборке конкурентов).
# T-107, уточнение того же дня (пользователь — "цена для тебя в твоем
# городе"): показанная в цене строке ниже сумма — цена в Грузии, БЕЗ
# доставки (для winner_auto_club мы не считаем "под ключ" сами, курс/
# доставка/растаможка не фиксированы заранее — см. build_repost_text
# выше). Значит призыв должен просить не абстрактное "ЦЕНА", а ГОРОД —
# именно города не хватает, чтобы посчитать и прислать точную цену под
# ключ конкретно этому покупателю (та же идея, что для bezpokrasa/
# tamsyam26, там город уже часть цены).
IG_CAPTION_CTA = "Напишите город в комментариях — пришлём точную цену под ключ в Директ."


def build_instagram_caption(parsed, price_usd=None, price_eur=None):
    """Подпись для инстаграм-формата (см. докстринг выше). НЕ выдумывает
    цифры — только то, что реально распознал parser (title/mileage) и уже
    посчитанная цена (price_usd/price_eur, те же поля, что использует
    build_repost_text() для winner_auto_club)."""
    parsed = parsed or {}
    title = (parsed.get("title") or "").strip()
    mileage = (parsed.get("mileage") or "").strip()

    lines = []
    if title:
        lines.append(title)
    if mileage:
        lines.append(f"Пробег: {mileage}")

    if price_usd is not None:
        price_str = f"{price_usd:,}".replace(",", " ")
        lines.append(f"Цена: ${price_str} (цена в Грузии, без доставки)")
    elif price_eur is not None:
        price_str = f"{price_eur:,}".replace(",", " ")
        lines.append(f"Цена: €{price_str} (цена в Грузии, без доставки)")

    lines.append("")
    lines.append(IG_CAPTION_CTA)
    return "\n".join(lines).strip()


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


# --- T-99 (30.08.2026): очередь ручных постов (без исходного сообщения источника) ---

MANUAL_QUEUE_PATH = Path("userbot_manual_queue.json")


def load_manual_queue():
    if MANUAL_QUEUE_PATH.exists():
        return json.loads(MANUAL_QUEUE_PATH.read_text(encoding="utf-8"))
    return {"items": []}


def save_manual_queue(queue):
    tmp = MANUAL_QUEUE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(MANUAL_QUEUE_PATH)


def queue_manual_post(text, media_paths, targets):
    """Кладёт вручную собранный пост (готовый текст + пути к файлам,
    уже лежащим на этом сервере) в очередь на отправку через уже живую
    сессию юзербота. targets — список юзернеймов каналов, например
    ["@My_Avto_Optimal", "@MY_Avto5"]. Разбирает _manual_queue_flusher()."""
    queue = load_manual_queue()
    item = {
        "id": str(uuid.uuid4()),
        "text": text,
        "media": list(media_paths),
        "targets": list(targets),
        "queued_at": datetime.utcnow().isoformat(),
    }
    queue["items"].append(item)
    save_manual_queue(queue)
    return item["id"]


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
    цена в формате "54.500$"/"73.500€" (точка как разделитель тысяч, знак
    валюты после числа). VIN в этом источнике обычно не публикуется —
    просто None, ничего не выдумываем.

    T-96 (28.08.2026, реальный пропущенный пост "Mercedes-Benz V 300" —
    цена была в €, старый регэксп ловил только "$", пост тихо считался
    "не распознан как объявление об авто"): канал публикует цены и в $, и
    в € — ловим оба, кладём в соответствующее поле (price_usd_total ИЛИ
    price_eur_total), compute_price_rub() уже умеет считать рубли из
    любого из них."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    title = None
    for line in lines:
        stripped = line.strip(" ❗️🚨🚘🔥‼️➡️➖—-*")
        if stripped:
            title = stripped
            break

    vin = re.search(r"vin[:\s]*([A-Za-z0-9]{5,20})", text, re.I)
    mileage = re.search(r"[Пп]робег:?\s*\**\s*([\d.,\s]+)\s*км", text, re.I)
    price = re.search(r"[Цц]ена:?\s*\**\s*([\d.,\s]+)\s*([$€])", text)

    if price is None:
        return None
    amount = clean_amount(price.group(1))
    if amount is None:
        return None
    currency = price.group(2)

    mileage_str = None
    if mileage:
        mileage_str = f"{clean_amount(mileage.group(1))} км"

    return {
        "title": title or "Автомобиль",
        "vin": vin.group(1) if vin else None,
        "mileage": mileage_str,
        "price_eur_total": amount if currency == "€" else None,
        "price_usd_total": amount if currency == "$" else None,
        "price_rub": None,
    }


_TAM_TITLE_RE = re.compile(r"^[A-ZА-ЯЁ0-9][A-ZА-ЯЁ0-9\s\-]{1,30}$")


def parse_tamsyam26(text):
    """Формат TamSyam26 (T-82, добавлен 25.08.2026): свободный текст с
    эмодзи-баннерами, модель/ТТХ отдельными строками, ДВЕ цены в рублях —
    "под ключ до РФ (Владивосток-Уссурийск)" (не привязана к городу
    продавца) и "с доставкой в <город продавца>" (не наша, это его город).
    Решение пользователя: берём цену "под ключ", в репосте показываем как
    доставку в Краснодар (см. build_repost_text()).

    T-96 (28.08.2026, реальный пост GMC Sierra без фразы "под ключ" вообще
    — только "ЦЕНА ориентировочная ... с Доставкой до Ставрополя ...
    5.900.000₽." — раньше такие посты тихо считались "не распознан").
    Fallback: если "под ключ" не нашли, берём цену рядом со словом "цена"
    и, если есть, город доставки — помечаем price_approximate=True и
    показываем честно (решение пользователя — "показывать честно", не
    выдавать чужой город продавца за наш "под ключ в Краснодаре")."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    # Модель у этого источника — отдельная строка КАПСОМ (например "TIGUAN"),
    # а не первая строка с буквами вообще (первые строки обычно — эмодзи-
    # баннер и рекламные фразы вроде "сделки проходят только по договору").
    title = next((l for l in lines if _TAM_TITLE_RE.match(l)), "Автомобиль")

    mileage = re.search(r"[Пп]робег\s*([\d\s]+)\s*км", text)
    mileage_str = f"{clean_amount(mileage.group(1))} км" if mileage else None

    # DOTALL: цена в реальных постах бывает на другой строке, чем "под
    # ключ"/"цена" (см. пример GMC Sierra ниже в docstring) — без DOTALL
    # "." не пересекает перенос строки, и regex тихо не находит цену.
    price_match = re.search(r"под\s+ключ.{0,150}?([\d][\d.,\s]{3,})\s*₽", text, re.I | re.DOTALL)
    if price_match is not None:
        price_rub = clean_amount(price_match.group(1))
        if price_rub is None:
            return None
        return {
            "title": title,
            "mileage": mileage_str,
            "price_eur_total": None,
            "price_usd_total": None,
            "price_rub": price_rub,
            "price_approximate": False,
            "delivery_city": None,
        }

    approx_match = re.search(r"[Цц][Ее][Нн][Аа].{0,150}?([\d][\d.,\s]{3,})\s*₽", text, re.DOTALL)
    if approx_match is None:
        return None
    price_rub = clean_amount(approx_match.group(1))
    if price_rub is None:
        return None

    city_match = re.search(r"[Дд]оставк\w*\s+до\s+([A-ZА-ЯЁ][a-zа-яё]+)", text)
    delivery_city = city_match.group(1) if city_match else None

    return {
        "title": title,
        "mileage": mileage_str,
        "price_eur_total": None,
        "price_usd_total": None,
        "price_rub": price_rub,
        "price_approximate": True,
        "delivery_city": delivery_city,
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
    реально встречается на присланных пользователем фото (T-85).

    26.08.2026: полоса 0.62-0.88 была подобрана только по 5 исходным
    Jeep-фото и оказалась слишком узкой — реальное фото Nissan Altima
    (задний ракурс) показало бейдж на 0.597-0.636h, то есть ВЫШЕ нижней
    границы старой полосы (0.62h). Расширяем до 0.55-0.92 — то же самое
    значение, что уже проверено на видео (_badge_video_regions в
    watermark_video.py) и покрывает оба случая с запасом."""
    h, w = img.shape[:2]
    band_y0, band_y1 = int(h * 0.55), int(h * 0.92)
    return (
        (0, band_y0, int(w * 0.30), band_y1),
        (int(w * 0.70), band_y0, w, band_y1),
    )


_BADGE_OCR_SCALES = (3, 2)  # 26.08.2026: одного scale=3 не хватило — на фото
                             # Nissan Altima (передний ракурс, бейдж крупнее
                             # в кадре, крупная область поиска) апскейл x3
                             # давал слишком большое изображение и Tesseract
                             # разваливался в шум, а x2 уверенно читал
                             # "WINNER"/"CLUB". Пробуем оба, а не только x3,
                             # чтобы не терять либо мелкий, либо крупный бейдж.

# 31.08.2026 (T-104): фото-путь гонял OCR ТОЛЬКО с psm=11 (россыпь текста),
# хотя ещё в T-98 (28.08.2026, watermark_video.py) выяснилось, что psm=6
# (один блок текста) надёжнее ловит "WINNER"/"CLUB" на реальном кадре — и
# просто никогда не переносилось обратно на фото. Проверено на 7 реальных
# фото из тестовой группы (жалоба "бейджи не везде полностью забрюлили"):
# на прямых/почти прямых ракурсах (не 3/4) psm=11 не находил НИ ОДНОГО
# слова бейджа там, где psm=6 уверенно ловил "WINNER" (dist=0). Пробуем
# оба psm, как и оба scale — дороже по времени, но не меняет логику
# принятия решения "это бейдж", только добавляет ещё один шанс найти текст.
_BADGE_OCR_PSMS = (11, 6)

# 31.08.2026 (T-104): OCR почти никогда не ловит все 3 слова бейджа сразу
# (обычно только "WINNER" ИЛИ только "CLUB") — а старый паддинг
# (_BADGE_PAD_FRAC_X от ширины НАЙДЕННОГО текста) считался симметрично от
# этого одного короткого слова и физически не дотягивался до остальных
# двух: на реальных фото из теста нашли "WINNER" (ширина ~70px), а вся
# табличка "WINNER AUTO CLUB" шире ещё примерно на 220px правее — паддинг
# в 0.55*70+10≈49px до туда не доставал, "AUTO CLUB" оставались на фото.
# Порядок слов на бейдже фиксирован (всегда "WINNER AUTO CLUB" слева
# направо) — используем это: если поймали "WINNER", но не "CLUB", запас
# добавляем в основном ВПРАВО (там непойманные "AUTO CLUB"), и наоборот.
# 5x высоты найденного слова — измерено на реальном фото (61b4d088,
# T-104): ~220px запаса при высоте буквы ~45px.
_BADGE_EXTRA_MULT = 5.0


def _find_badge_box(img, regions=None, scales=None, psm=None, return_words=False):
    """Ищет бейдж WINNER AUTO CLUB по тексту в заданных областях кадра
    (по умолчанию — нижние углы, см. _badge_corner_regions; видео-пайплайн
    передаёт другой набор регионов — там бейдж встречается и по центру
    низа кадра, не только по углам). Возвращает плотный (x, y, w, h) вокруг
    распознанных слов, либо None, если уверенного совпадения нет — тогда
    кадр/фото не трогаем.

    28.08.2026 (T-98): scales/psm теперь параметризуемы — не трогает
    поведение для фото (default None/11 = как раньше, _BADGE_OCR_SCALES и
    psm=11), но видео-пайплайн передаёт свои значения. Причина: у видео
    регион поиска — вся ширина кадра (см. _badge_video_regions в
    watermark_video.py), а не узкие угловые кропы, как у фото. На реальном
    тесте (IMG_0901) штатные scale=(3,2)+psm=11 при апскейле такой широкой
    области (2560-3840px) разваливались в шум и НЕ находили даже крупный
    чёткий анфас-бейдж (кадр 0 того видео) — тот же класс проблемы, что уже
    описан в комментарии у _BADGE_OCR_SCALES про фото, только острее из-за
    большей ширины региона.

    31.08.2026 (T-104): psm теперь по умолчанию None — фото-путь пробует
    ОБА _BADGE_OCR_PSMS (11 и 6, см. комментарий там), а не только 11.
    Видео как передавало один конкретный psm (сейчас 6, T-98), так и
    передаёт — его поведение не меняется. return_words=True дополнительно
    возвращает set() найденных слов ("WINNER"/"AUTO"/"CLUB") — remove_watermark
    использует его, чтобы направленно расширить паддинг в сторону
    непойманных слов (см. _BADGE_EXTRA_MULT); видео этот флаг не использует
    и получает как раньше только box."""
    if regions is None:
        regions = _badge_corner_regions(img)
    if scales is None:
        scales = _BADGE_OCR_SCALES
    psms = _BADGE_OCR_PSMS if psm is None else (psm,)
    all_hits = []
    for sx0, sy0, sx1, sy1 in regions:
        crop = img[sy0:sy1, sx0:sx1]
        if crop.size == 0:
            continue
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        for variant in (gray, 255 - gray):
            for scale in scales:
                for p in psms:
                    for target, dist, x, y, ww, hh in _ocr_badge_hits(variant, scale=scale, psm=p):
                        all_hits.append((target, dist, sx0 + x, sy0 + y, ww, hh))

    if not all_hits:
        return (None, set()) if return_words else None

    # На каждое целевое слово оставляем только лучшее (наименьшее расстояние) совпадение
    best_per_word = {}
    for target, dist, x, y, ww, hh in all_hits:
        if target not in best_per_word or dist < best_per_word[target][0]:
            best_per_word[target] = (dist, x, y, ww, hh)

    strong = any(dist <= _BADGE_STRONG_MAX_DIST for dist, *_ in best_per_word.values())
    if not strong and len(best_per_word) < _BADGE_MIN_DISTINCT_WORDS:
        return (None, set()) if return_words else None

    xs0 = min(x for _, x, y, ww, hh in best_per_word.values())
    ys0 = min(y for _, x, y, ww, hh in best_per_word.values())
    xs1 = max(x + ww for _, x, y, ww, hh in best_per_word.values())
    ys1 = max(y + hh for _, x, y, ww, hh in best_per_word.values())
    box = (int(xs0), int(ys0), int(xs1 - xs0), int(ys1 - ys0))
    return (box, set(best_per_word.keys())) if return_words else box


# 31.08.2026 (T-104): на ракурсе 3/4 (не анфас/корма строго в лоб) текст
# бейджа в кадре заметно скошен перспективой — обычный _find_badge_box (без
# поворота) не находит НИ ОДНОГО слова ни при каком psm/scale, проверено
# вручную на реальном фото (белый TX, корма, F8C40AEF из жалобы 31.08.2026).
# Перебор поворота кропа на несколько углов перед OCR подтверждённо чинит
# именно этот случай (при +20° находились И "WINNER", И "CLUB" с точным
# совпадением) — но НЕ чинит другой, внешне похожий случай (текст на фото
# уже почти горизонтален, но OCR всё равно не находит ничего ни при каком
# угле — там причина не в скосе, а в том, что весь угловой регион поиска
# (768x710) слишком захламлён соседними деталями решётки/шторы для
# psm=6 "единый блок текста"; для этого нужен отдельный фикс — сужение
# региона или локализация в 2 прохода, здесь НЕ реализовано).
#
# Пробуем только КАК ФОЛБЭК — когда обычный _find_badge_box() вернул None,
# то есть ничего не нашли и так, терять нечего. Сознательно ограничен набор
# углов/scale/psm (4 угла × 2 варианта × 1 scale × 1 psm = 8 OCR-вызовов на
# регион — тот же порядок, что и у обычного прохода), чтобы в худшем случае
# (когда фолбэк тоже сработал впустую) обработка одного фото не утраивалась,
# а примерно удваивалась — пользователь одобрил именно "удвоить время"
# 31.08.2026, не больше.
_BADGE_ROTATION_ANGLES = (-20, -15, 15, 20)
_BADGE_ROTATION_SCALE = 2
_BADGE_ROTATION_PSM = 11


def _find_badge_box_rotated(img, regions=None, angles=None, scale=None, psm=None, return_words=False):
    """Фолбэк-версия _find_badge_box() с перебором поворота кропа — см.
    комментарий у _BADGE_ROTATION_ANGLES. Возвращает то же самое, что и
    _find_badge_box (box или (box, words) при return_words=True), координаты
    уже пересчитаны обратно в систему координат НЕповёрнутого кадра."""
    if regions is None:
        regions = _badge_corner_regions(img)
    if angles is None:
        angles = _BADGE_ROTATION_ANGLES
    if scale is None:
        scale = _BADGE_ROTATION_SCALE
    if psm is None:
        psm = _BADGE_ROTATION_PSM

    all_hits = []
    for sx0, sy0, sx1, sy1 in regions:
        crop = img[sy0:sy1, sx0:sx1]
        if crop.size == 0:
            continue
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape[:2]
        for angle in angles:
            center = (w / 2, h / 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            rotated = cv2.warpAffine(gray, M, (w, h), borderValue=128)
            # Обратное вращение (тот же центр, противоположный угол) — чтобы
            # пересчитать найденный в ПОВЁРНУТОМ кропе бокс обратно в
            # координаты исходного (неповёрнутого) кропа.
            m_inv = cv2.getRotationMatrix2D(center, -angle, 1.0)
            for variant in (rotated, 255 - rotated):
                for target, dist, x, y, ww, hh in _ocr_badge_hits(variant, scale=scale, psm=psm):
                    pts = np.array([[[x, y]], [[x + ww, y]], [[x, y + hh]], [[x + ww, y + hh]]], dtype=np.float32)
                    mapped = cv2.transform(pts, m_inv)
                    xs, ys = mapped[:, 0, 0], mapped[:, 0, 1]
                    ox, oy = float(xs.min()), float(ys.min())
                    ow, oh = float(xs.max() - xs.min()), float(ys.max() - ys.min())
                    all_hits.append((target, dist, sx0 + ox, sy0 + oy, ow, oh))

    if not all_hits:
        return (None, set()) if return_words else None

    best_per_word = {}
    for target, dist, x, y, ww, hh in all_hits:
        if target not in best_per_word or dist < best_per_word[target][0]:
            best_per_word[target] = (dist, x, y, ww, hh)

    strong = any(dist <= _BADGE_STRONG_MAX_DIST for dist, *_ in best_per_word.values())
    if not strong and len(best_per_word) < _BADGE_MIN_DISTINCT_WORDS:
        return (None, set()) if return_words else None

    xs0 = min(x for _, x, y, ww, hh in best_per_word.values())
    ys0 = min(y for _, x, y, ww, hh in best_per_word.values())
    xs1 = max(x + ww for _, x, y, ww, hh in best_per_word.values())
    ys1 = max(y + hh for _, x, y, ww, hh in best_per_word.values())
    box = (int(xs0), int(ys0), int(xs1 - xs0), int(ys1 - ys0))
    return (box, set(best_per_word.keys())) if return_words else box


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
        box, words = _find_badge_box(img, return_words=True)
        if box is None:
            # 31.08.2026 (T-104): фолбэк на ракурс 3/4 — только когда обычный
            # проход ничего не нашёл (см. комментарий у _BADGE_ROTATION_ANGLES
            # про то, почему это не всегда помогает, но раз обычный проход и
            # так вернул None, терять уже нечего).
            box, words = _find_badge_box_rotated(img, return_words=True)
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
    # 31.08.2026 (T-104): симметричный pad_x от найденного текста не
    # дотягивался до остальных слов, если OCR поймала только одно короткое
    # (обычно "WINNER" слева или "CLUB" справа) — см. комментарий у
    # _BADGE_EXTRA_MULT. Порядок слов фиксирован, поэтому запас смещаем
    # направленно в сторону непойманных слов, а не растягиваем поровну.
    extra = int(h * _BADGE_EXTRA_MULT)
    pad_left, pad_right = pad_x, pad_x
    if "WINNER" in words and "CLUB" not in words:
        pad_right += extra
    elif "CLUB" in words and "WINNER" not in words:
        pad_left += extra
    elif words == {"AUTO"}:
        pad_left += extra // 2
        pad_right += extra // 2
    x0, y0 = max(0, x - pad_left), max(0, y - pad_y)
    x1, y1 = min(img.shape[1], x + w + pad_right), min(img.shape[0], y + h + pad_y)

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
# T-94 (27.08.2026): ретрай для бэкфилла истории — диагностика показала
# плавающий сетевой сбой (см. комментарий у места использования ниже).
_BACKFILL_TIMEOUT = 25
_BACKFILL_RETRIES = 3
_BACKFILL_RETRY_DELAY = 5

# T-108 (01.09.2026, обнаружено пользователем — "на безпокрасе были посты,
# почему не было постинга к нам?"): в логе стабильно повторялась
# telethon.errors.rpcerrorlist.UsernameNotOccupiedError на "bezpokrasa" —
# не таймаут/сеть (T-94, та проблема была самоустраняющейся и ретраилась),
# а Telegram прямо говорит "такого username сейчас ни у кого нет". Канал
# сменил публичный @-хендл на @AutoLibraryChina (подтверждено
# пользователем) — старый освободился, поэтому юзербот не мог найти канал
# НИ в бэкфилле (ValueError сразу, без ретрая — see except Exception ниже
# по файлу), НИ в живом потоке (chats=sources в events.NewMessage не мог
# резолвнуть несуществующий username, значит live-события тоже не
# долетали). Внутренний идентификатор "bezpokrasa" ОСТАЁТСЯ прежним везде
# в остальном коде (SOURCE_PARSERS, наценка/цена, TEST_ONLY_SOURCES,
# состояние отправленных постов и т.д. — это тот же бизнес/формат
# объявлений, просто новая публичная ссылка в Telegram) — меняется только
# то, по какому хендлу юзербот реально ищет канал в самом Telegram. Если
# канал сменит хендл ещё раз — достаточно поправить только эту строку.
SOURCE_TG_HANDLE = {"bezpokrasa": "autolibrarychina"}
_TG_HANDLE_TO_SOURCE = {v: k for k, v in SOURCE_TG_HANDLE.items()}

PHOTO_PROCESSORS = {"winner_auto_club": remove_watermark}

# T-86 (27.08.2026, запрошено пользователем — "давай в автомат ставь видео
# монтаж не в ручной режим"): источники, для которых видео автоматически
# перемонтируется в короткий вертикальный ролик (auto_montage.build_short) —
# см. докстринг auto_montage.py про сам алгоритм и договорённость с
# пользователем "сначала в тестовую" (winner_auto_club и так уже целиком в
# TEST_ONLY_SOURCES — до отдельного решения пользователя в боевые не уйдёт).
# Прототип, проверен ПОЛНОСТЬЮ автоматически (без ручного отсмотра кадров)
# только на одном реальном видео — см. TASKS.md T-86.
# T-95 (27.08.2026, ЭКСТРЕННО ОТКЛЮЧЕНО): авто-монтаж стабильно роняет
# сервис по OOM-killer на этапе обработки видео winner_auto_club — не
# исключение (try/except его не ловит, ОС убивает процесс целиком), а
# самовоспроизводящийся краш-луп каждые ~5 минут (см. TASKS.md T-95,
# лог с 07:10 по 07:38 27.08.2026 — 4+ OOM-kill подряд, tamsyam26 из-за
# этого ни разу не добрался до бэкфилла).
# T-95bis (01.09.2026, инстаграм-формат, включено обратно ОСТОРОЖНО):
# сборка теперь изолирована в подпроцесс (см. _prepare_media_list) — OOM
# убьёт максимум этот подпроцесс, не Telethon-сессию целиком, и корректно
# попадёт в fallback (оригинал видео) вместо краш-лупа сервиса. Плюс
# кандидатов уменьшено 8 -> 6 (см. PEAK_MAX_CANDIDATES в auto_montage.py).
# winner_auto_club и так целиком в TEST_ONLY_SOURCES — результат уйдёт
# только в тестовую группу, боевые каналы не затронуты, что бы ни
# случилось. НЕ проверено на реальном VPS-трафике после этого фикса —
# после деплоя посмотреть `free -h`/journalctl на VPS (T-95, пункт 1).
#
# T-109 (01.09.2026, запрошено пользователем — целевая схема: "для инсты
# берем из боевых каналов, а в боевой канал пусть заходит уже после
# автомонтажа" + "все источники"): расширили монтаж на все источники с
# парсером (artalexgroup, bezpokrasa), не только winner_auto_club. НО тем
# же сообщением пользователь уточнил: "пока авто монтаж в процессе
# доработки кидаем все видео в тестовую группу" — то есть целевая схема
# (боевой канал получает УЖЕ обработанное монтажом видео) сознательно
# отложена, пока качество не подтверждено на реальном трафике для всех
# источников. Поэтому в handle_group() ниже source_username из
# AUTO_MONTAGE_SOURCES теперь безусловно форсирует видео в тестовую
# группу (новая ветка, независимая от video_dry_run/video_dry_run_sources
# и от TEST_ONLY_SOURCES) — artalexgroup и bezpokrasa раньше слали видео
# сразу в боевые (не были в video_dry_run_sources), теперь их видео тоже
# уходит в тест, пока они в AUTO_MONTAGE_SOURCES. Текст/фото-посты этих
# источников не затронуты — идут в боевые как раньше.
# НЕ проверено на реальном трафике artalexgroup/bezpokrasa через монтаж —
# посмотреть тестовую группу и `journalctl ... | grep -i montage` после
# деплоя.
AUTO_MONTAGE_SOURCES = {"artalexgroup", "bezpokrasa", "winner_auto_club"}  # было {"winner_auto_club"} (T-109)


async def _prepare_media_list(client, source_username, messages, parsed=None):
    """Для большинства источников просто передаём Telegram media как есть —
    без перекачки. Для источников из PHOTO_PROCESSORS фото скачиваем,
    прогоняем через процессор (сейчас — удаление водяного знака) и шлём уже
    новыми байтами. Для источников из AUTO_MONTAGE_SOURCES видео скачиваем и
    перемонтируем в короткий вертикальный ролик (T-86, auto_montage.py) —
    остальные источники видео не трогают (пересылают как есть, см. докстринг
    модуля наверху про VIDEO_DRY_RUN).

    T-85 (26.08.2026): processor теперь делает OCR (Tesseract) вместо
    простого template matching — заметно медленнее (секунды, не доли
    секунды, на фото). Раньше `processor(raw)` вызывался прямо в event
    loop'е — с OCR это надолго блокировало бы ВЕСЬ asyncio event loop
    (другие каналы/очередь отложенных постов ждали бы), особенно на
    альбомах из нескольких фото. Поэтому вызов вынесен в отдельный поток
    через `asyncio.to_thread`. T-86: то же самое для видео-монтажа — это
    минуты CPU (см. auto_montage.build_short), сборка вынесена в отдельный
    подпроцесс (T-95bis, см. комментарий ниже).

    Возвращает (media_list, montage_used) — T-107: montage_used=True только
    если auto_montage реально собрал короткий ролик хотя бы для одного видео
    (а не упал и не откатился на оригинал) — handle_group() по этому флагу
    решает, какую подпись слать (build_instagram_caption вместо
    build_repost_text)."""
    processor = PHOTO_PROCESSORS.get(source_username)
    auto_montage_on = source_username in AUTO_MONTAGE_SOURCES
    montage_used = False
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
        elif auto_montage_on and m.video:
            try:
                import tempfile
                import os
                import sys
                with tempfile.TemporaryDirectory() as tmpdir:
                    in_path = os.path.join(tmpdir, f"{m.id}_in.mp4")
                    out_path = os.path.join(tmpdir, f"{m.id}_short.mp4")
                    await client.download_media(m, file=in_path)
                    title = (parsed or {}).get("title") or ""
                    mileage = (parsed or {}).get("mileage") or ""
                    # T-95bis (01.09.2026): build_short() раньше вызывался
                    # in-process через asyncio.to_thread — на реальном трафике
                    # это стабильно роняло ВЕСЬ юзербот-сервис OOM-killer'ом
                    # (TASKS.md T-95): OOM убивает процесс на уровне ядра ОС,
                    # try/except ниже физически не мог это поймать — он течёт
                    # в ТОМ ЖЕ процессе, который убивают. Вынесли сборку в
                    # отдельный python3-подпроцесс (тот же auto_montage.py,
                    # что раньше импортировался — теперь запускается его CLI):
                    # если памяти не хватит, убьют только его, а не
                    # Telethon-сессию с живым слушателем каналов — сервис
                    # продолжит работать и корректно попадёт в except ниже
                    # (ненулевой returncode), ровно как и задумывался fallback.
                    # T-110 (01.09.2026): source_username передаём отдельным
                    # аргументом — auto_montage.build_short() запускает
                    # OCR-детект бейджа (detect_boxes()) только когда
                    # source == "winner_auto_club" (единственный источник, под
                    # который этот OCR подбирался); для остальных источников
                    # из AUTO_MONTAGE_SOURCES (T-109) детект пропускается
                    # целиком — экономит время/CPU и не рискует ложным
                    # срабатыванием на видео, под которое OCR не проверялся.
                    proc = await asyncio.create_subprocess_exec(
                        sys.executable, "auto_montage.py", in_path, out_path, title, mileage, source_username,
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                    )
                    out, _ = await proc.communicate()
                    log_tail = out.decode("utf-8", "replace")[-2000:] if out else ""
                    if proc.returncode != 0 or not os.path.exists(out_path):
                        logger.warning(
                            "[%s#%s] auto_montage подпроцесс завершился с кодом %s — шлю оригинал видео\n%s",
                            source_username, m.id, proc.returncode, log_tail,
                        )
                        media_list.append(m.media)
                        continue
                    logger.info("[%s#%s] auto_montage подпроцесс:\n%s", source_username, m.id, log_tail)
                    with open(out_path, "rb") as f:
                        processed = f.read()
                bio = io.BytesIO(processed)
                bio.name = f"{m.id}_short.mp4"
                media_list.append(bio)
                montage_used = True
            except Exception:
                logger.exception(
                    "[%s#%s] ошибка при авто-монтаже видео — шлю оригинал",
                    source_username, m.id,
                )
                media_list.append(m.media)
        else:
            media_list.append(m.media)
    return media_list, montage_used


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
        post_text = build_repost_text(text, source_username, price_rub, parsed.get("price_usd_total"), feedback_bot_username, price_eur=parsed.get("price_eur_total"), price_approximate=parsed.get("price_approximate", False), delivery_city=parsed.get("delivery_city"))

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
    # T-115 (01.09.2026, запрошено пользователем — "запускай в боевые
    # группы кроме видео винера", после успешного ручного теста T-111/
    # T-112/T-113/T-114 на artalexgroup): временная ветка T-109 ("любое
    # видео источника из AUTO_MONTAGE_SOURCES -> только тест") УБРАНА —
    # artalexgroup/bezpokrasa теперь идут по обычной логике ниже (как и их
    # текст/фото), то есть в боевые, если не DRY_RUN и в окне постинга.
    # winner_auto_club по-прежнему ЗАЩИЩЁН — он целиком в TEST_ONLY_SOURCES
    # (ветка выше, T-82/T-85), это НЕ зависело от убранной ветки и
    # продолжает работать без изменений — "кроме видео винера" выполняется
    # автоматически, отдельно ничего не потребовалось.
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

    media_list, montage_used = await _prepare_media_list(client, source_username, messages, parsed)

    if montage_used:
        # T-107 (01.09.2026): видео реально прошло через auto_montage
        # (короткий вертикальный ролик с текстом на видео) — это черновик
        # инстаграм-формата, а не обычный TG-репост, поэтому и подпись
        # нужна инстаграмная (build_instagram_caption), не build_repost_text
        # (там markdown-ссылка на бота, которую Instagram не отрендерит —
        # см. докстрин build_instagram_caption). parsed гарантированно не
        # None здесь: auto_montage_on проверяется только для источников из
        # AUTO_MONTAGE_SOURCES, а это подмножество источников с парсером.
        post_text = build_instagram_caption(
            parsed,
            price_usd=parsed.get("price_usd_total") if parsed else None,
            price_eur=parsed.get("price_eur_total") if parsed else None,
        )

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
                    # T-108: тот же alias, что в бэкфилле/живом потоке — если
                    # source_username переименован в Telegram (SOURCE_TG_HANDLE),
                    # искать нужно по реальному текущему хендлу.
                    fetched = await client.get_messages(SOURCE_TG_HANDLE.get(source_username, source_username), ids=ids)
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


async def _manual_queue_flusher(client, poll_seconds=60):
    """T-99 (30.08.2026, запрошено пользователем — "давай проверим почему
    не автопостит?"): аналог _pending_queue_flusher(), но для постов без
    исходного сообщения в отслеживаемом канале-источнике (например,
    видео, собранное вручную из чужого скринкаста, с текстом, написанным
    руками) — там нечего заново скачивать по id, текст и пути к файлам
    уже готовы и лежат прямо в очереди (userbot_manual_queue.json,
    queue_manual_post()). Файлы должны физически лежать на этом же
    сервере ДО постановки в очередь — сам флашер их никуда не скачивает.
    Отправка — тем же живым client, что и у остального пайплайна: никакой
    второй Telethon-сессии не открывается, поэтому безопасно работает
    параллельно с боевым сервисом."""
    while True:
        await asyncio.sleep(poll_seconds)
        try:
            queue = load_manual_queue()
            items = queue.get("items", [])
            if not items:
                continue
            save_manual_queue({"items": []})
            logger.info("--- Разбираю очередь ручных постов: %s шт. ---", len(items))
            for item in items:
                item_id = item.get("id", "?")
                text = item.get("text", "")
                media_paths = item.get("media", [])
                targets = item.get("targets", [])
                missing = [mp for mp in media_paths if not Path(mp).exists()]
                if missing:
                    logger.error(
                        "[manual#%s] файлы не найдены на диске этого сервера: %s — пост НЕ отправлен, убираю из очереди (скопируй файлы на сервер и поставь в очередь заново)",
                        item_id, missing,
                    )
                    continue
                for target in targets:
                    try:
                        if media_paths:
                            try:
                                await client.send_message(target, text, file=media_paths, parse_mode="md", link_preview=False)
                            except MediaCaptionTooLongError:
                                logger.info("[manual#%s] подпись слишком длинная для медиа, шлю текст отдельным сообщением", item_id)
                                await client.send_message(target, "", file=media_paths)
                                await client.send_message(target, text, parse_mode="md", link_preview=False)
                        else:
                            await client.send_message(target, text, parse_mode="md", link_preview=False)
                        logger.info("[manual#%s] запощено в %s", item_id, target)
                    except Exception:
                        logger.exception("[manual#%s] ошибка при постинге в %s", item_id, target)
        except Exception:
            logger.exception("Ошибка в фоновой задаче отправки ручных постов — продолжаю, попробую на следующем цикле")


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
    # T-99 (30.08.2026): очередь ручных постов (userbot_manual_queue.json) —
    # опрашивается раз в ~60с, отправляет через этот же живой client.
    asyncio.create_task(_manual_queue_flusher(client))

    logger.info(
        "Режим: %s | видео: %s | источники: %s | цели: %s / %s",
        "DRY_RUN -> тестовая группа" if dry_run else "БОЕВОЙ",
        "DRY_RUN -> тестовая группа" if video_dry_run else "БОЕВОЙ",
        sources, target_optimal, target_my_avto5,
    )

    if backfill_limit > 0:
        logger.info("--- Стартовый бэкфилл: последние %s сообщений каждого источника (с учётом альбомов и уже отправленного ранее) ---", backfill_limit)
        for source in sources:
            # T-94 (27.08.2026): диагностика на VPS (см. TASKS.md T-94 —
            # debug-лог telethon) показала, что таймаут get_entity/
            # iter_messages — плавающий, самоустраняющийся сбой (один и тот
            # же канал то виснет на все 25-60с, то через минуту отвечает за
            # 0.1с), не постоянная проблема с конкретным каналом и не
            # нехватка таймаута. Поэтому лечим ретраем с паузой, а не
            # увеличением таймаута.
            raw_messages = None
            for attempt in range(1, _BACKFILL_RETRIES + 1):
                logger.info("[%s] запрашиваю историю (попытка %s/%s, таймаут %sс)...", source, attempt, _BACKFILL_RETRIES, _BACKFILL_TIMEOUT)
                try:
                    # T-108: ищем канал в Telegram по его РЕАЛЬНОМУ текущему
                    # хендлу (SOURCE_TG_HANDLE), а не по внутреннему source —
                    # для источников без переименования это одно и то же.
                    raw_messages = await asyncio.wait_for(_collect_messages(client, SOURCE_TG_HANDLE.get(source, source), backfill_limit), timeout=_BACKFILL_TIMEOUT)
                    break
                except asyncio.TimeoutError:
                    if attempt < _BACKFILL_RETRIES:
                        logger.warning("[%s] таймаут при получении истории (попытка %s/%s) — жду %sс и пробую снова", source, attempt, _BACKFILL_RETRIES, _BACKFILL_RETRY_DELAY)
                        await asyncio.sleep(_BACKFILL_RETRY_DELAY)
                    else:
                        logger.error("[%s] таймаут при получении истории — все %s попытки исчерпаны, пропускаю источник, проверь сеть/прокси/доступ юзербота к каналу", source, _BACKFILL_RETRIES)
                except Exception:
                    logger.exception("[%s] ошибка при получении истории (попытка %s/%s) — пропускаю источник", source, attempt, _BACKFILL_RETRIES)
                    break
            if raw_messages is None:
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

    # T-108: подписываемся по РЕАЛЬНЫМ текущим хендлам (SOURCE_TG_HANDLE),
    # иначе переименованный канал (например bezpokrasa -> AutoLibraryChina)
    # вообще не резолвится Telethon'ом и живые события с него не приходят.
    tg_chat_filters = [SOURCE_TG_HANDLE.get(s, s) for s in sources]

    @client.on(events.NewMessage(chats=tg_chat_filters))
    async def on_new_message(event):
        # T-108: event.chat.username — это ТЕКУЩИЙ хендл канала в Telegram
        # (после переименования — новый), а не то, что настроено в SOURCES.
        # Переводим обратно во внутренний идентификатор (_TG_HANDLE_TO_SOURCE),
        # чтобы парсер/цена/state продолжили работать так же, как раньше —
        # вся остальная логика по-прежнему знает источник как "bezpokrasa".
        raw_username = (event.chat.username or "").lower()
        source_username = _TG_HANDLE_TO_SOURCE.get(raw_username, raw_username)
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
