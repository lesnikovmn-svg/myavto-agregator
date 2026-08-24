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
- Курс EUR/RUB — константа в конфиге, обновлять вручную.
- Наценка на итоговую цену — грубая оценка (сумма уже данных в посте
  составляющих), не точный калькулятор растаможки.
"""
import asyncio
import json
import logging
import re
from pathlib import Path
from urllib.parse import urlparse

from telethon import TelegramClient, events
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.errors import UserAlreadyParticipantError

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
OUR_FOOTER = """Почему именно MY_Avto?
Мы не просто продаём автомобили. Мы тщательно подбираем машину, которая на 100% соответствует вашим задачам, бюджету, стилю вождения и ожиданиям. Каждый экземпляр проходит полную проверку по всем параметрам.

Фото/видео, осмотр после доставки, полный расчёт под ключ — пишите прямо сейчас!

✈️ Telegram: [My_Avto_Optimal](https://t.me/My_Avto_Optimal) ✈️ Telegram: [MY_Avto5](https://t.me/MY_Avto5) ✈️ Telegram: [my_avto_opyt](https://t.me/my_avto_opyt)
✈️ Максим: [LesnikovM](https://t.me/LesnikovM) | +7 938 409-67-08 ✈️ Антон: [Tohakmv](https://t.me/Tohakmv) | +7 963 383-79-28
🌐 Сайт: [my-avto.online](https://www.my-avto.online) 🌐 Сайт: [myavto-agregator.ru](https://myavto-agregator.ru)
📸 Instagram: [my_avto5](https://www.instagram.com/my_avto5) 💙 VK: [my_avto5](https://vk.com/my_avto5) 💬 MAX: [Присоединиться](https://max.ru/join/DXEGJWNaZPpj8WYi3eIMqJLriw-T0hF5ddCfUN2tk7I) 📍 Яндекс: [Профиль](https://yandex.ru/profile/-/CTvFvXPa)
MY_Avto — ваш надёжный партнёр в выборе авто! 🚗"""

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


def build_repost_text(raw_text):
    """Исходный текст объявления как есть (без чужих контактов/сайта) + наш футер."""
    kept = []
    for line in raw_text.splitlines():
        if any(p.search(line) for p in _DROP_PATTERNS):
            continue
        kept.append(line)
    while kept and not kept[-1].strip():
        kept.pop()
    body = "\n".join(kept).strip()
    return f"{body}\n\n{OUR_FOOTER}" if body else OUR_FOOTER

PRICE_LOW = 4_500_000
PRICE_HIGH = 6_000_000


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
        price_rub = clean_amount(invoice_rub.group(1)) + clean_amount(customs_rub.group(1))

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
        "price_rub": price_rub,
    }


SOURCE_PARSERS = {
    "artalexgroup": parse_eu_wholesale,
    "bezpokrasa": parse_china_invoice,
}


def compute_price_rub(parsed, eur_rub_rate):
    if parsed["price_rub"] is not None:
        return parsed["price_rub"]
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


# --- Обработка одного сообщения -----------------------------------------

async def handle_message(client, source_username, message, targets_cfg, eur_rub_rate, dry_run, test_group, state):
    text = message.raw_text or ""
    if not text.strip():
        return

    parser = SOURCE_PARSERS.get(source_username)
    if parser is None:
        logger.warning("Нет парсера для источника %s, пропускаю", source_username)
        return

    parsed = parser(text)
    if parsed is None:
        logger.info("[%s#%s] не распознан как объявление об авто — пропускаю", source_username, message.id)
        return

    price_rub = compute_price_rub(parsed, eur_rub_rate)
    if price_rub is None:
        logger.info("[%s#%s] не удалось посчитать цену в рублях — пропускаю, не рискую с каналом", source_username, message.id)
        return

    real_targets = route_targets(price_rub, targets_cfg["optimal"], targets_cfg["my_avto5"])
    post_text = build_repost_text(text)

    if dry_run:
        send_targets = [test_group] if test_group else []
        note = f" (боевые цели были бы: {real_targets})"
    else:
        send_targets = real_targets
        note = ""

    price_str = f"{price_rub:,}".replace(",", " ")
    logger.info(
        "[%s#%s] цена=%s ₽%s\n%s",
        source_username, message.id, price_str, note, post_text,
    )

    for target in send_targets:
        try:
            if message.media:
                await client.send_message(target, post_text, file=message.media, parse_mode="md")
            else:
                await client.send_message(target, post_text, parse_mode="md")
            logger.info("[%s#%s] запощено в %s", source_username, message.id, target)
        except Exception:
            logger.exception("[%s#%s] ошибка при постинге в %s", source_username, message.id, target)

    key = f"last_id:{source_username}"
    state[key] = max(state.get(key, 0), message.id)
    save_state(state)


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
        # уже участник — получаем сущность через диалоги
        async for dialog in client.iter_dialogs():
            if getattr(dialog.entity, "id", None) and invite_hash:
                pass
        # проще: Telethon сам разрулит по инвайт-ссылке даже если уже внутри
        entity = await client.get_entity(invite_url)
        return entity


async def main():
    env = load_env()
    api_id = env.get("API_ID")
    api_hash = env.get("API_HASH")
    proxy = build_proxy(env.get("PROXY_URL"))
    sources = [s.strip().lstrip("@") for s in env.get("SOURCES", "artalexgroup,bezpokrasa").split(",") if s.strip()]
    target_optimal = env.get("TARGET_OPTIMAL", "@My_Avto_Optimal")
    target_my_avto5 = env.get("TARGET_MY_AVTO5", "@MY_Avto5")
    eur_rub_rate = float(env.get("EUR_RUB_RATE", "100"))
    dry_run = env.get("DRY_RUN", "true").strip().lower() != "false"
    backfill_limit = int(env.get("TEST_BACKFILL_LIMIT", "5"))
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

    if dry_run and backfill_limit > 0:
        logger.info("--- Тестовый прогон по последним %s постам каждого источника ---", backfill_limit)
        for source in sources:
            async for message in client.iter_messages(source, limit=backfill_limit):
                await handle_message(client, source, message, targets_cfg, eur_rub_rate, dry_run, test_group, state)
        logger.info("--- Конец тестового прогона, жду новые посты в реальном времени ---")

    @client.on(events.NewMessage(chats=sources))
    async def on_new_message(event):
        source_username = (event.chat.username or "").lower()
        await handle_message(client, source_username, event.message, targets_cfg, eur_rub_rate, dry_run, test_group, state)

    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
