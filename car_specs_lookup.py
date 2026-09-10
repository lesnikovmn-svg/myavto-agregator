"""T-161 (10.09.2026, запрошено пользователем): поиск базовых ТТХ (двигатель,
мощность, привод, разгон, тип топлива) по бренду+модели+году на внешнем
источнике — для постов, где сам источник (продавец) не написал вообще
никаких характеристик (реальный пример — пост artalexgroup "BMW X7
xDrive40d 2026": только модель/год/цена, ни двигателя, ни привода, ни
комплектации). Пользователь подтвердил именно этот подход — "искать на
внешних источниках по модели/году", а не ограничиваться тем, что и так
есть в тексте (это уже покрыто status_card_parser.py — другая задача).

ИСТОЧНИК: ultimatespecs.com. Выбран после ручной проверки (WebSearch/
WebFetch, эта же сессия) среди нескольких кандидатов:
  - auto-data.net — вернул 402 (paywall/блокировка) при прямом обращении.
  - ultimatespecs.com — отдаёт серверный HTML (не JS-каркас), значения
    подписаны понятными английскими метками ("Horsepower", "Drive wheels",
    "Torque" и т.п.), структура страниц предсказуема.
  - Wikipedia — рассматривался как fallback/сверка, НЕ реализован в этой
    версии (инфобокс не всегда содержит мощность/разгон по конкретному
    трим-варианту, только общие данные модели) — если потребуется
    "хоть что-то, лучше чем ничего", можно добавить отдельным уровнем.

URL-структура (проверено вручную, WebFetch, только на одном реальном
примере — BMW X7):
  1) https://www.ultimatespecs.com/car-specs/BMW-models/BMW-<Model>
     — конструируется НАПРЯМУЮ из бренда+модели (без запроса/поиска).
     Список поколений модели с годами выпуска и ссылками на каждое.
  2) https://www.ultimatespecs.com/car-specs/<Brand>/M<id>/<Model>-<Gen>
     — страница поколения (ссылка с шага 1) — список версий (двигатель/
     привод в названии, например "xDrive40d") со ссылками на ТТХ.
  3) https://www.ultimatespecs.com/car-specs/<Brand>/<id>/...html
     — сама страница ТТХ (ссылка с шага 2).
Ни <id> поколения (M-префикс), ни <id> версии НЕ вычисляются напрямую из
бренда/модели/года — нужна цепочка из 2-3 запросов, результат кэшируется
(см. _CACHE), чтобы не повторять её для каждого поста с одной и той же
моделью/поколением.

ПАРСИНГ — БЕЗ BeautifulSoup/lxml (лишняя зависимость, в проекте и так
достаточно тяжёлых bin-зависимостей — tesseract/ffmpeg/opencv, см.
requirements.txt): просто вырезаем теги регуляркой в plain-text построчно
(_to_lines) и ищем строку с нужной англоязычной подписью ("Horsepower" и
т.п.), значение — в ближайших нескольких строках после неё (_value_near).
Терпимо к точной HTML-разметке (table/dl/div — неважно, что использует
сайт), но чувствительно к смене ФОРМУЛИРОВОК подписей — при полном
редизайне сайта потребуется актуализация меток в _FIELD_LABELS.

ВАЖНАЯ ОГОВОРКА: точная HTML-разметка страниц НЕ проверялась байт-в-байт
из песочницы этой сессии — исходящий доступ к ultimatespecs.com оттуда
заблокирован политикой организации (то же самое, что мешало прямому
curl/device_bash весь этот проект), рабочей была ТОЛЬКО такая же
заблокированная проверка через сам агент, но WebFetch-инструмент
(маршрутизируется иначе) дал текстовое описание структуры страницы, не
байтовую копию. Первый реальный прогон — только на VPS (см.
test_specs_lookup_once.py, TASKS.md T-161) — если что-то не распознается,
скорее всего дело в неточном описании меток здесь, актуализировать
_FIELD_LABELS/_GENERATION_ROW_RE/_VERSION_ROW_RE по реальному выводу.

Философия проекта (см. status_card_parser.py, badge-детектор): НИКОГДА не
гадать — при любой неуверенности (сайт недоступен, поколение по году не
нашлось, версия по трим-подсказке не нашлась однозначно) lookup_specs()
возвращает None, вызывающий код просто не добавляет секцию ТТХ, как было
раньше. Лучше пропустить обогащение, чем показать характеристики другой
комплектации как есть."""
import html
import json
import logging
import os
import re
import time

import requests

logger = logging.getLogger("car_specs_lookup")

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
_HEADERS = {"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"}
_TIMEOUT = 12
_BASE = "https://www.ultimatespecs.com"

# T-161: не бить по сайту на каждый пост — кэш на диске (не в git, тот же
# принцип, что и у остальных *_ARCHIVE_DIR/*_STATE — см. userbot_config.env.example).
# Кэшируем даже "ничего не нашлось" (None), чтобы не пытаться заново на
# каждом посте с той же непонятной моделью — TTL см. _CACHE_TTL_SECONDS.
_CACHE_FILE = os.environ.get("CAR_SPECS_CACHE_FILE", "car_specs_cache.json")
_CACHE_TTL_SECONDS = 30 * 24 * 3600  # 30 дней — модельный ряд/ТТХ меняются редко
_cache = None  # ленивая загрузка, см. _load_cache


def _load_cache():
    global _cache
    if _cache is not None:
        return _cache
    try:
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            _cache = json.load(f)
    except Exception:
        _cache = {}
    return _cache


def _save_cache():
    try:
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_cache, f, ensure_ascii=False, indent=1)
    except Exception:
        logger.exception("[car_specs_lookup] не удалось сохранить кэш %s", _CACHE_FILE)


def _cache_key(brand, model, year, trim_hint):
    return f"{brand}|{model}|{year or ''}|{(trim_hint or '').lower()}"


def _get(url):
    """GET с таймаутом, никогда не бросает исключение наружу — любая
    сетевая проблема (таймаут, DNS, 4xx/5xx) — просто None, вызывающий
    код это трактует как "не удалось, пропускаем"."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        if resp.status_code != 200:
            logger.info("[car_specs_lookup] %s -> HTTP %s", url, resp.status_code)
            return None
        return resp.text
    except Exception as e:
        logger.info("[car_specs_lookup] %s -> ошибка запроса: %r", url, e)
        return None


def _to_lines(raw_html):
    """Убирает теги/скрипты/стили, разворачивает HTML-сущности, возвращает
    непустые строки текста по порядку появления — используется и для
    поиска подписей ТТХ (_value_near), и как общий fallback-парсинг."""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw_html, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = html.unescape(text)
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


_LINK_RE = re.compile(r'<a\b[^>]*?href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def _extract_links(raw_html):
    """Список (href, plain_text) для всех <a> в порядке появления —
    используется для навигации по хабу поколений и по списку версий."""
    out = []
    for href, inner in _LINK_RE.findall(raw_html):
        text = html.unescape(_TAG_RE.sub(" ", inner))
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            out.append((href, text))
    return out


def _abs_url(href):
    if href.startswith("http"):
        return href
    return _BASE + ("" if href.startswith("/") else "/") + href


_MODEL_SLUG_RE = re.compile(r"[^A-Za-z0-9]+")


def _model_slug(model):
    """'X7' -> 'X7', 'C-Class' -> 'C-Class' (дефис сохраняем — реальные
    URL модели используют его, например BMW-X5, Mercedes-Benz-C-Class);
    остальное — не-буквенно-цифровое схлопываем в дефис."""
    return _MODEL_SLUG_RE.sub("-", model.strip()).strip("-")


def hub_url(brand, model):
    brand_slug = _model_slug(brand)
    model_slug = _model_slug(model)
    return f"{_BASE}/car-specs/{brand_slug}-models/{brand_slug}-{model_slug}"


_YEAR_RANGE_RE = re.compile(r"(19|20)\d{2}\s*[-–]\s*(Present|(19|20)\d{2})", re.I)


def _find_generations(hub_html):
    """Разбирает хаб-страницу поколений модели — возвращает список
    {"href", "text", "year_from", "year_to"} (year_to=None для "Present",
    т.е. ещё выпускается). Ссылка на поколение — обычно та, что находится
    РЯДОМ (в той же строке plain-текста, после HTML->текст) с диапазоном
    годов вида "2022 - Present"; чтобы не зависеть от точной вложенности
    тегов, сопоставляем по близости в списке (href,text) — если текст
    ссылки САМ содержит диапазон годов (частый вариант) либо идёт сразу
    следом за отдельной строкой с диапазоном."""
    generations = []
    links = _extract_links(hub_html)
    for href, text in links:
        m = _YEAR_RANGE_RE.search(text)
        if not m:
            continue
        if "/car-specs/" not in href:
            continue
        years_in_match = re.findall(r"(?:19|20)\d{2}", m.group(0))
        y_from = int(years_in_match[0])
        y_to = None if "present" in m.group(0).lower() else int(years_in_match[-1])
        generations.append({"href": _abs_url(href), "text": text, "year_from": y_from, "year_to": y_to})
    return generations


def _pick_generation(generations, year):
    if not generations:
        return None
    if year is None:
        # без года — берём самое новое поколение (обычно первое в списке
        # на сайте, но на всякий случай сортируем сами)
        return sorted(generations, key=lambda g: g["year_from"], reverse=True)[0]
    for g in generations:
        upper = g["year_to"] if g["year_to"] is not None else 9999
        if g["year_from"] <= year <= upper:
            return g
    return None


_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _norm_trim(s):
    """Схлопывает пробелы/дефисы и приводит к нижнему регистру — источники
    поста и сайт пишут одну и ту же комплектацию по-разному ("xDrive40d" в
    посте vs "xDrive 40d" на сайте): без нормализации прямое вхождение
    подстроки почти никогда не совпадает. Проверено юнит-тестом
    (test_specs_lookup_once.py) — с этой нормализацией "xDrive40d" находит
    "BMW X7 G07 LCI xDrive 40d", без неё — нет."""
    return _NON_ALNUM_RE.sub("", s.lower())


def _find_versions(gen_html):
    """Список (href, text) версий/комплектаций на странице поколения —
    ссылки, ведущие на страницу конкретной ТТХ (URL содержит .html и
    /car-specs/<Brand>/<id>/)."""
    out = []
    for href, text in _extract_links(gen_html):
        if re.search(r"/car-specs/[^/]+/\d+/[^/]+\.html", href, re.I):
            out.append((_abs_url(href), text))
    return out


def _pick_version(versions, trim_hint):
    if not versions or not trim_hint:
        # без подсказки не гадаем наугад между разными двигателями/приводами
        # одного поколения — честно возвращаем None (см. докстринг модуля)
        return None
    hint_norm = _norm_trim(trim_hint)
    if not hint_norm:
        return None
    candidates = [(href, text) for href, text in versions if hint_norm in _norm_trim(text)]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        # неоднозначно (подсказка слишком короткая/общая, совпала с
        # несколькими версиями) — лучше пропустить обогащение, чем
        # показать характеристики не той комплектации
        logger.info("[car_specs_lookup] подсказка %r неоднозначна среди версий: %s", trim_hint, [t for _, t in candidates])
        return None
    return None


_FIELD_LABELS = {
    "engine": [r"engine\s*type", r"number\s*of\s*cylinders"],
    "displacement": [r"engine\s*displacement", r"displacement\b"],
    "power_hp": [r"horsepower", r"\bpower\b"],
    "torque": [r"maximum\s*torque", r"\btorque\b"],
    "transmission": [r"gearbox", r"transmission"],
    "drivetrain": [r"drive\s*wheels", r"drivetrain", r"traction"],
    "accel_0_100": [r"0\s*to\s*100\s*km/h", r"0-100\s*km/h"],
    "fuel_type": [r"fuel\s*type"],
    "top_speed": [r"top\s*speed"],
}

_VALUE_PATTERNS = {
    "engine": r"(?:inline|straight|v)[\s-]?\d{1,2}|boxer|electric\s*motor",
    "displacement": r"[\d][\d.,]*\s*cm3|[\d][\d.,]*\s*cc\b",
    "power_hp": r"\d{2,4}\s*HP",
    "torque": r"\d{2,4}\s*Nm",
    "transmission": r"\d\s*speed\s*[A-Za-z]+|manual|automatic|cvt|dct",
    "drivetrain": r"\bAWD\b|\b4WD\b|\bFWD\b|\bRWD\b|\b4x4\b",
    "accel_0_100": r"[\d]+\.?[\d]*\s*s\b",
    "fuel_type": r"diesel|petrol|gasoline|electric|hybrid|hydrogen",
    "top_speed": r"\d{2,4}\s*km/h",
}


def _value_near(lines, label_patterns, value_pattern, window=6):
    """Ищет строку, содержащую одну из label_patterns (regex, без учёта
    регистра), и возвращает первое совпадение value_pattern в этой же
    строке или в нескольких следующих (на случай разметки "подпись" и
    "значение" в разных ячейках/строках)."""
    for i, line in enumerate(lines):
        if any(re.search(lp, line, re.I) for lp in label_patterns):
            for j in range(i, min(i + window, len(lines))):
                m = re.search(value_pattern, lines[j], re.I)
                if m:
                    return re.sub(r"\s+", " ", m.group(0)).strip()
    return None


def _extract_specs_from_page(spec_html):
    lines = _to_lines(spec_html)
    result = {}
    for field, label_patterns in _FIELD_LABELS.items():
        val = _value_near(lines, label_patterns, _VALUE_PATTERNS[field])
        if val:
            result[field] = val
    return result if result else None


def lookup_specs(brand, model, year=None, trim_hint=None):
    """Главная точка входа. brand/model — как уже извлечены парсером поста
    (см. status_card_parser._split_brand_model — брать оттуда же, не
    дублировать). year — int или None. trim_hint — свободная строка,
    например "xDrive40d" (то, что шло после модели в заголовке поста) —
    без неё, если у модели несколько версий/двигателей, вернём None (не
    гадаем, см. докстринг модуля).

    Возвращает dict с ключами из _FIELD_LABELS (только те, что реально
    нашлись — не все ключи гарантированы) либо None, если что-то на любом
    из шагов пошло не так (сайт недоступен, поколение/версия не нашлись).
    Кэшируется на диске (_CACHE_FILE, _CACHE_TTL_SECONDS) — в т.ч. и
    отрицательный результат, чтобы не долбить сайт повторно по одной и
    той же непонятной модели."""
    cache = _load_cache()
    key = _cache_key(brand, model, year, trim_hint)
    cached = cache.get(key)
    if cached and time.time() - cached.get("ts", 0) < _CACHE_TTL_SECONDS:
        return cached.get("specs")

    specs = None
    try:
        hub_html = _get(hub_url(brand, model))
        if hub_html:
            generations = _find_generations(hub_html)
            gen = _pick_generation(generations, year)
            if gen:
                gen_html = _get(gen["href"])
                if gen_html:
                    versions = _find_versions(gen_html)
                    picked = _pick_version(versions, trim_hint)
                    if picked:
                        version_href, version_text = picked
                        spec_html = _get(version_href)
                        if spec_html:
                            specs = _extract_specs_from_page(spec_html)
    except Exception:
        logger.exception("[car_specs_lookup] неожиданная ошибка при поиске ТТХ %s %s %s", brand, model, year)
        specs = None

    cache[key] = {"specs": specs, "ts": time.time()}
    _save_cache()
    return specs
