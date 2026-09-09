"""
T-158: разбор итогового текста поста (уже опубликованного в MY_Avto5 /
My_Avto_Optimal — не важно, ботом или вручную, см. TASKS.md T-158
"почему не хук на handle_group") на поля для карточки-статуса
(status_card.CarCard).

Ключевой факт, из-за которого этот парсер вообще так устроен (см.
TASKS.md T-158): реальные посты в целевых каналах СИЛЬНО отличаются по
формату — от чистых эмодзи-полей ("⚙️ Мощность: 197 л.с.") до почти
свободного текста абзацем без единой эмодзи-метки. Единого формата нет,
потому что часть постов — это репост бота (build_repost_text, формат
зависит от источника), а часть — ручные посты админов канала напрямую в
Telegram (не через бота вообще).

Решение пользователя (AskUserQuestion этой сессии): если уверенно не
удалось вытащить бренд+модель+цену — пропускать пост целиком, не
публиковать кривую карточку. Для 5 полей спек-панели — то же самое "бери
что нашёл": приоритет год/регистрация -> пробег -> мощность/объём ->
тип/привод -> локация/условия, слот просто не показывается, если
конкретное поле не найдено (согласовано с пользователем: этот приоритет
подтверждён как есть, без правок порядка/состава).

Не импортирует telethon, чистые функции — тестируется отдельно от бота.
"""
from __future__ import annotations

import re
from typing import Optional

from status_card import CarCard, Spec

# Известные бренды/алиасы — первое слово(а) заголовочной строки сверяется с
# этим списком (без учёта регистра), чтобы отделить бренд от модели.
# Список расширять по мере появления новых реальных постов (см. T-158).
_BRAND_ALIASES = {
    "mercedes-benz": "Mercedes-Benz",
    "mercedes benz": "Mercedes-Benz",
    "mercedes": "Mercedes-Benz",
    "mb": "Mercedes-Benz",
    "bmw": "BMW",
    "audi": "Audi",
    "porsche": "Porsche",
    "volkswagen": "Volkswagen",
    "vw": "Volkswagen",
    "volvo": "Volvo",
    "land rover": "Land Rover",
    "range rover": "Range Rover",
    "bentley": "Bentley",
    "rolls-royce": "Rolls-Royce",
    "rolls royce": "Rolls-Royce",
    "maserati": "Maserati",
    "ferrari": "Ferrari",
    "lamborghini": "Lamborghini",
    "jaguar": "Jaguar",
    "mini": "MINI",
    "lexus": "Lexus",
    "toyota": "Toyota",
    "nissan": "Nissan",
    "infiniti": "Infiniti",
    "honda": "Honda",
    "mazda": "Mazda",
    "subaru": "Subaru",
    "mitsubishi": "Mitsubishi",
    "suzuki": "Suzuki",
    "genesis": "Genesis",
    "hyundai": "Hyundai",
    "kia": "Kia",
    "geely": "Geely",
    "chery": "Chery",
    "exeed": "Exeed",
    "omoda": "Omoda",
    "haval": "Haval",
    "tank": "Tank",
    "changan": "Changan",
    "gac": "GAC",
    "byd": "BYD",
    "zeekr": "Zeekr",
    "li auto": "Li Auto",
    "nio": "NIO",
    "cadillac": "Cadillac",
    "chevrolet": "Chevrolet",
    "gmc": "GMC",
    "ford": "Ford",
    "jeep": "Jeep",
    "chrysler": "Chrysler",
    "dodge": "Dodge",
    "ram": "Ram",
    "tesla": "Tesla",
    "maybach": "Mercedes-Maybach",
}
# длинные алиасы (с пробелом) должны проверяться раньше коротких — иначе
# "range rover" разберётся как ["range", "rover..."] по первому слову
_BRAND_ALIASES_SORTED = sorted(_BRAND_ALIASES.items(), key=lambda kv: -len(kv[0]))

_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF⁉‼️]+"
)
_YEAR_RE = re.compile(r"\b(19[89]\d|20[0-4]\d)\b")


def _strip_decor(line: str) -> str:
    line = _EMOJI_RE.sub(" ", line)
    line = re.sub(r"[!‼️❗️]+", " ", line)
    return re.sub(r"\s+", " ", line).strip(" -–—|:")


def _split_brand_model(title: str) -> Optional[tuple]:
    low = title.lower()
    for alias, canon in _BRAND_ALIASES_SORTED:
        if low.startswith(alias):
            rest = title[len(alias):].strip(" -–—:")
            if canon == "Mercedes-Maybach" and rest.lower().startswith("gls"):
                pass  # модель остаётся как есть ("GLS 600")
            if not rest:
                return None
            return canon, rest
    return None


_LABEL_LINE_RE = re.compile(r"^[a-zа-яё][\w -]{1,20}:\s*\S", re.IGNORECASE)


def _find_title_line(text: str) -> Optional[str]:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    first_lines = lines[:6]

    # 1) самый надёжный сигнал — строка, которая (после чистки) начинается
    # с известного бренда (см. _BRAND_ALIASES) — не зависит от того, есть
    # ли в строке эмодзи-машинка (в реальных постах она бывает и на
    # служебной строке типа "🚘Автомобиль: Официальный", см. T-158
    # maybach-пример — там это дало бы неверный заголовок).
    for l in first_lines:
        cleaned = _strip_decor(l)
        if cleaned and _split_brand_model(cleaned) is not None:
            return cleaned

    # 2) строка с "машинным" эмодзи, которая не похожа на служебное поле
    # вида "Метка: значение"
    for l in first_lines:
        if re.search(r"[\U0001F697\U0001F698\U0001F699\U0001F69A\U0001F6FB\U0001F3CE]", l):
            cleaned = _strip_decor(l)
            if cleaned and not _LABEL_LINE_RE.match(cleaned):
                return cleaned

    # 3) иначе первая содержательная строка, не состоящая только из
    # декоративных emoji-выкриков ("❗️СВЕЖЕЕ ПРЕДЛОЖЕНИЕ❗️") и не похожая
    # на служебное поле
    skip_words = {"свежее", "предложение", "новинка", "хит"}
    for l in first_lines:
        cleaned = _strip_decor(l)
        if (cleaned and cleaned.lower() not in skip_words and len(cleaned) > 2
                and not _LABEL_LINE_RE.match(cleaned)):
            return cleaned
    return None


# Цена в тексте встречается в двух порядках — "12 500 000 ₽" (символ
# после числа, обычно для ₽) и "€169,000" (символ перед числом, обычно для
# €/$ в постах на европейский манер) — оба варианта реальные (T-158).
_PRICE_CORE = r"(?:[€$]\s?[\d][\d\s.,]{2,}|[\d][\d\s.,]{2,}\s?(?:₽|руб\.?|€|eur|\$|usd))"
_PRICE_LABELED_RE = re.compile(
    r"(?:цена|netto|нетто)[^\n]{0,20}?(" + _PRICE_CORE + r")",
    re.IGNORECASE,
)
_PRICE_ANY_RE = re.compile(r"(" + _PRICE_CORE + r")", re.IGNORECASE)


def _find_price(text: str) -> Optional[str]:
    m = _PRICE_LABELED_RE.search(text)
    if not m:
        m = _PRICE_ANY_RE.search(text)
    if not m:
        return None
    return re.sub(r"\s+", " ", m.group(1)).strip()


def _has(pattern: str, text: str) -> bool:
    return re.search(pattern, text, re.IGNORECASE) is not None


def _clean_value(val: str, max_len: int = 22) -> str:
    val = _EMOJI_RE.sub("", val).strip(" .,:;")
    # уточнения в скобках ("197 л.с. (145 кВт)") — декоративны для карточки,
    # в узкий слот спек-панели не влезут, обрезаем по первой открывающей
    val = re.split(r"\s*[({]", val, maxsplit=1)[0].strip(" .,:;")
    if len(val) <= max_len:
        return val
    cut = val[:max_len]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" .,:;") + "…"


def _search(patterns, text: str) -> Optional[str]:
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = _clean_value(m.group(1))
            if val:
                return val
    return None


def _extract_specs(text: str) -> list:
    specs = []

    reg = _search([r"первая регистрация:?\s*([0-9]{1,2}[./][0-9]{2,4})"], text)
    if reg:
        specs.append(Spec("Первая регистрация", reg))
    else:
        yr = _search([r"год выпуска:?\s*(\d{4})"], text)
        if yr:
            specs.append(Spec("Год выпуска", yr))

    mileage = _search([
        r"техническ\w* пробег:?\s*([\d\s]{2,}\s?км)",
        r"пробег:?\s*([\d\s]{1,}\s?км)",
    ], text)
    if mileage:
        specs.append(Spec("Пробег", re.sub(r"\s+", " ", mileage)))

    power = _search([
        r"мощность:?\s*([\d]+\s?л\.?\s?с\.?[^\n,]{0,15})",
        r"объ[её]м:?\s*([\d.,]+\s?л[^\n,]{0,20})",
    ], text)
    if power:
        specs.append(Spec("Мощность" if "л.с" in power.lower() or "л с" in power.lower() else "Объём", power))

    drive = _search([r"тип:?\s*([^\n,;]{2,20})"], text)
    if not drive:
        if re.search(r"4matic|quattro|xdrive|awd\b|4wd\b|полный привод", text, re.IGNORECASE):
            drive = "Полный привод"
    if drive:
        specs.append(Spec("Тип" if _has(r"тип:?\s*", text) else "Привод", drive))

    loc = _search([r"локация:?\s*([^\n,;]{2,24})"], text)
    if not loc:
        if re.search(r"в наличии", text, re.IGNORECASE):
            loc = "В наличии"
        elif re.search(r"услуги экспорта", text, re.IGNORECASE):
            loc = "Экспорт/логистика"
    if loc:
        specs.append(Spec("Локация" if _has(r"локация:?\s*", text) else "Условия", loc))

    return specs[:5]


def parse_post_for_status_card(text: str) -> Optional[CarCard]:
    """Возвращает CarCard или None (пропустить пост — недостаточно данных,
    решение пользователя T-158). Не поднимает исключений на произвольном
    тексте — любая ошибка разбора трактуется как "не смогли", не падение."""
    if not text or not text.strip():
        return None

    try:
        title = _find_title_line(text)
        if not title:
            return None

        year = None
        m = _YEAR_RE.search(title)
        if m:
            year = m.group(1)
            title = (title[:m.start()] + title[m.end():]).strip(" -–—")
        else:
            m2 = _YEAR_RE.search(text)
            if m2:
                year = m2.group(1)

        split = _split_brand_model(title)
        if split is None:
            parts = title.split(None, 1)
            if len(parts) < 2:
                return None
            brand, model = parts[0], parts[1]
        else:
            brand, model = split

        brand = brand.strip(" -–—:")
        model = model.strip(" -–—:")
        if not brand or not model:
            return None

        price = _find_price(text)
        if not price:
            return None

        specs = _extract_specs(text)

        return CarCard(brand=brand, model=model, year=year or "", price=price, specs=specs)
    except Exception:
        return None


if __name__ == "__main__":
    SAMPLES = {
        "gle_coupe": """❗️СВЕЖЕЕ ПРЕДЛОЖЕНИЕ❗️
🚘 Mercedes-Benz GLE Coupe 4MATIC Plug-in Hybrid 2026
AMG Line Advanced Plus | Night Package | AIRMATIC | 360°
✅ Технический пробег: 8 000 км

⚙️ Мощность: 197 л.с. (145 кВт)

🔋 Тип: Гибрид (дизель + электро)

📅 Первая регистрация: 04/2026

⚡ Быстрая зарядка: 29 мин
💰 Цена под ключ в РФ: 12 500 000 ₽
Ключевые особенности:
AMG Line Advanced Plus + Night Package
""",
        "s450d": """❗️СВЕЖЕЕ ПРЕДЛОЖЕНИЕ ❗️

🚘 Mercedes Benz S450d 2026

📑 vin-code:

✅ В наличии/ готов к сделке

💶 Цена Netto 153.000€

🛫 Услуги экспорта и логистики

📈Таможенное оформление на специальных условиях!
""",
        "maybach": """‼️MB Maybach GLS 600 ‼️

🚘Автомобиль: Официальный

Год выпуска: 2026
Объём : 4.0л бензин
Пробег: 22 км
Локация: Georgia 🇬🇪

Комплектация: R-23 диски, обогрев, вентиляция и массаж всех сидений...

Цена: €169,000 (цена в Грузии). За точной ценой на момент сделки — пишите в личку.
""",
    }
    for name, txt in SAMPLES.items():
        card = parse_post_for_status_card(txt)
        print("===", name, "===")
        if card is None:
            print("  SKIP (недостаточно данных)")
        else:
            print(" ", card.brand, "|", card.model, "|", card.year, "|", card.price)
            for s in card.specs:
                print("   -", s.label, ":", s.value)
