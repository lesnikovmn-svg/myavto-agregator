import requests
import re
import time
import datetime
from ddgs import DDGS

# T-72 (21.08.2026): Credentials/gspread.authorize/парсинг agent_config.env
# и логика подключения к таблице переехали в sheets_client.py — тот же
# блок был скопипащен в 11+ файлах. connect_sheets/connect_reviews_sheet/
# SHEET_ID/REVIEWS_HEADER/REVIEWS_SHEET_TITLE реэкспортируются отсюда без
# изменений, чтобы все `from company_agent import connect_sheets` и
# подобное в остальных скриптах продолжали работать как раньше.
from sheets_client import (  # noqa: F401 — намеренный реэкспорт, см. комментарий выше
    SHEET_ID,
    connect_sheets,
    connect_reviews_sheet,
    REVIEWS_SHEET_TITLE,
    REVIEWS_HEADER,
    load_env,
)

config = load_env("agent_config.env")

# 13.08.2026: перенос агента на VPS показал, что t.me с VPS напрямую не
# открывается (тот же блок, что раньше ловили с api.telegram.org) —
# curl без прокси вернул 000, через прокси — 200. tgstat.ru при этом
# 403-ит и с прокси, и без — это не сетевой блок, а анти-бот фильтр
# самого tgstat (видимо, поэтому и на Маке в логах бывают дни с
# "0 каналов" по всем запросам), прокси тут не поможет, чинить отдельно.
# PROXY_URL опционален — если не задан в agent_config.env, работаем
# как раньше, напрямую. (Это не про Sheets — про фетч сайтов/tgstat —
# поэтому осталось здесь, а не в sheets_client.py.)
PROXY_URL = config.get("PROXY_URL", "").strip()
PROXIES = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None


def check_site(url):
    try:
        r = requests.get(
            url, timeout=5, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}
        )
        return r.status_code == 200
    except Exception:
        # T-73 (21.08.2026): было голое `except:` — ловило вообще всё,
        # включая KeyboardInterrupt/SystemExit, из-за чего Ctrl+C во время
        # прогона агента иногда "проглатывался" вместо остановки. Exception
        # покрывает все реальные сетевые/парсинговые сбои, но не системные.
        return False


def extract_phone(text):
    m = re.search(r"[78][\s\-\(]?\d{3}[\s\-\(]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}", text)
    return m.group(0) if m else "-"


def extract_telegram(text):
    m = re.search(r"@([A-Za-z0-9_]{3,32})", text)
    return m.group(1) if m else ""


# Email — добавлено 14.08.2026 для будущей email-рассылки при онбординге
# компаний (см. onboarding_companies.xlsx). Ищем прямо в HTML/тексте
# сайта/карточки, тем же путём, что телефон/ИНН — не отдельным запросом.
#
# Известные источники ложных совпадений простого email-регэкспа (по
# аналогии с уже пойманными багами в этом файле — antibot-заглушки,
# vk.com/js-виджеты и т.п. — тот же класс проблемы "технический
# артефакт похож по форме на настоящий контакт"):
# - retina-картинки вида "logo@2x.png" — по форме неотличимы от email
#   (локальная часть + @ + "домен" с точкой), фильтруем по расширению.
# - служебные адреса аналитики/конструкторов сайтов (Wix, Sentry и т.п.),
#   плейсхолдеры из шаблонов ("example.com", "yourdomain.ru") — сайт
#   компании их не имеет в виду как реальный контакт.
EMAIL_JUNK_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "gif",
    "svg",
    "webp",
    "ico",
    "bmp",
    "tiff",
    "avif",
    "css",
    "js",
}
EMAIL_JUNK_DOMAINS = [
    "example.com",
    "example.org",
    "example.net",
    "example.ru",
    "test.com",
    "domain.com",
    "domain.ru",
    "yourdomain.com",
    "yourdomain.ru",
    "yoursite.com",
    "sentry.io",
    "sentry-next.io",
    "wixpress.com",
    "wix.com",
    "schema.org",
    "w3.org",
    "w3schools.com",
    "godaddy.com",
    "gstatic.com",
    "cloudflare.com",
    "jquery.com",
    "google.com",
    "googleapis.com",
    "google-analytics.com",
    "recaptcha.net",
    "bem.info",
    "vk.com",
    "yastatic.net",
    # Найдено 14.08.2026 на реальном прогоне fix_backfill_emails.py: когда
    # источником служит карточка компании на 2ГИС/Яндекс.Картах, на самой
    # странице рядом с данными компании часто есть СОБСТВЕННЫЙ служебный
    # email площадки (ссылка "Написать в поддержку" и т.п.) — старый
    # extract_email() брал его как "первый похожий на email в тексте", не
    # различая "это контакт самой компании" от "это контакт площадки,
    # на которой размещена карточка". help@2gis.ru встретился так у ~12
    # разных компаний подряд, support@maps.yandex.ru — у ~5. "vk-portal.net"
    # — технический хешированный адрес инфраструктуры ВКонтакте (виджеты/
    # пиксели), не человеческий контакт — тот же класс проблемы, что и с
    # "vk.com/rtrg"/"max.ru/u" (см. раздел про виджет-артефакты выше).
    "2gis.ru",
    "maps.yandex.ru",
    "vk-portal.net",
]
EMAIL_JUNK_LOCAL_PREFIXES = {
    "noreply",
    "no-reply",
    "donotreply",
    "do-not-reply",
    "postmaster",
    "mailer-daemon",
    "abuse",
}


def clean_snippet_prefix(s):
    """
    Найдено 27.08.2026 (пользователь прогнал ручную сверку по всему
    каталогу): сниппеты Google/DDG для статей и Telegram-каталогов часто
    начинаются со служебного префикса перед реальным текстом — дата
    ("Jan 31, 2026 · Официальный дилер...") или число подписчиков
    ("9 587 subscribers Мы профессионально..."). Ни то ни другое не
    описание компании — обрезаем префикс, если он есть, остальной текст
    не трогаем.
    """
    if not s:
        return s
    s = re.sub(
        r"^\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}\s*[·\-–]\s*",
        "",
        s,
    )
    s = re.sub(r"^\s*[\d\s ]+\s*subscribers\s*", "", s, flags=re.IGNORECASE)
    return s.strip()


def extract_email(text):
    """
    Первый похожий на реальный контактный email в тексте. Возвращает ""
    если ничего подходящего не нашлось — вызывающий код просто оставляет
    поле пустым, ничего не выдумываем (тот же принцип, что и у остальных
    extract_*/find_* в этом файле).
    """
    if not text:
        return ""
    for m in re.finditer(r"[A-Za-z0-9][A-Za-z0-9._%+\-]*@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", text):
        candidate = m.group(0)
        local, _, domain = candidate.partition("@")
        domain_l = domain.lower()
        ext = domain_l.rsplit(".", 1)[-1]
        if ext in EMAIL_JUNK_EXTENSIONS:
            continue
        if any(j in domain_l for j in EMAIL_JUNK_DOMAINS):
            continue
        if local.lower() in EMAIL_JUNK_LOCAL_PREFIXES:
            continue
        return candidate
    return ""


def is_probably_tagline(text):
    """
    Отличаем настоящее название компании от рекламного слогана/заголовка
    страницы. Найдено 09.08.2026: сайт autoshoot.ru не содержал ни
    og:site_name, ни разделителя в заголовке выдачи — в итоге в поле name
    целиком попал H1 "Подбор, покупка и доставка авто из Европы под ключ"
    (полное предложение, а не название компании). Настоящие названия
    компаний почти всегда короткие (1-3 слова, обычно без пробела вообще
    или с одним): "CarsKorea", "Japan Transit", "China Trade". Слоганы —
    длинные фразы из нескольких слов, часто с предлогами ("из", "под",
    "для") и знаками препинания.
    """
    if not text:
        return False
    words = text.split()
    return len(text) > 35 or len(words) > 4


def clean_name_from_title(title):
    """
    Заголовки в поисковой выдаче почти всегда содержат настоящее название
    компании первым сегментом: "CarsKorea — авто из Южной Кореи...",
    "Карсплюс Авто - честный автосалон...". Берём текст до первого
    разделителя-тире/палки — это и есть имя. Если разделителя нет или
    сегмент подозрительно короткий — не годится, пусть вызывающий код
    решает, что делать (обычно — fallback на домен).

    Если разделителя нет вообще (весь title — одна фраза) и эта фраза
    похожа на рекламный слоган (см. is_probably_tagline), а не на
    название — возвращаем "", а не сырой текст целиком: вызывающий код
    в этом случае падает на domain_name, что честнее, чем показывать
    целое предложение как "название компании".
    """
    if not title:
        return ""
    for sep in [" — ", " – ", " | ", " - ", " · "]:
        if sep in title:
            candidate = title.split(sep)[0].strip()
            if len(candidate) >= 2:
                return candidate
    stripped = title.strip()
    if is_probably_tagline(stripped):
        return ""
    return stripped


def extract_inn(text):
    # Ищем ИНН только рядом со словом "ИНН" — просто 10/12-значное число
    # в тексте слишком часто оказывается номером телефона или ОГРН.
    m = re.search(r"ИНН[:\s№]{0,5}(\d{10}|\d{12})", text, re.IGNORECASE)
    return m.group(1) if m else ""


def fetch_site_text(url):
    # Отдельно от check_site: тут нужен именно текст страницы, чтобы
    # поискать в нём ИНН/реквизиты компании. Если не получилось — не страшно,
    # просто не найдём ИНН для этой компании сейчас.
    html = ""
    try:
        r = requests.get(
            url, timeout=6, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}
        )
        if r.status_code == 200:
            # Баг найден 09.08.2026 (кодировка): если сервер не указал
            # charset в заголовке Content-Type (а полагается только на
            # <meta charset="utf-8"> внутри HTML, которую requests не
            # читает), requests по старому стандарту HTTP по умолчанию
            # считает текст ISO-8859-1 — реальный UTF-8 (кириллица) при
            # этом превращается в "кракозябры" (пример: имя компании с
            # ai-import.ru записалось в таблицу как "ÐÐ ÐÐ²ÑÐ¾" вместо
            # нормального русского названия). Если charset в заголовке не
            # объявлен явно — используем угаданную requests'ом кодировку
            # (apparent_encoding) вместо дефолтной ISO-8859-1.
            content_type = r.headers.get("Content-Type", "")
            if "charset" not in content_type.lower():
                r.encoding = r.apparent_encoding
            html = r.text
    except Exception:
        pass
    # T-89 (27.08.2026, по репорту пользователя: Delivery Cars/Fast Wheel/
    # Todes-Avto — телефон/email/telegram реально есть на сайте, но агент
    # их не видит): если голый requests.get() вернул похожий на пустой
    # SPA-каркас React/Next.js (см. _looks_like_js_shell) — пробуем
    # добрать содержимое headless-браузером (Playwright), который
    # реально дожидается отрисовки JS. Дороже по времени, поэтому НЕ
    # используется по умолчанию для всех сайтов подряд, только как
    # прицельный fallback для этого конкретного симптома.
    if _looks_like_js_shell(html):
        rendered = fetch_site_text_rendered(url)
        if rendered and len(rendered) > len(html):
            return rendered
    return html


# Признаки того, что requests.get() вернул не реальную страницу, а почти
# пустой каркас SPA (React/Next.js/Vue) — контакты/телефон/футер
# дорисовываются JS-ом уже в браузере, их просто нет в исходном HTML.
# ОТЛИЧАЕТСЯ от BOT_WALL_MARKERS ниже: там сайт СОЗНАТЕЛЬНО отдаёт
# заглушку ботам, здесь же сайт технически всегда так работает, для
# людей в браузере тоже — просто requests не выполняет JS вообще.
_SPA_ROOT_MARKER = re.compile(r'id=["\'](?:root|__next|app|__nuxt)["\']', re.IGNORECASE)


def _looks_like_js_shell(html):
    """True, если html похож на пустой SPA-каркас: есть характерный
    div#root/__next/app, но текста внутри почти нет (реальный контент
    добавляется JS-ом после загрузки, здесь его ещё не было)."""
    if not html or not _SPA_ROOT_MARKER.search(html):
        return False
    no_scripts = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text_only = re.sub(r"<[^>]+>", " ", no_scripts)
    text_only = re.sub(r"\s+", " ", text_only).strip()
    return len(text_only) < 400


def fetch_site_text_rendered(url):
    """
    T-89 (27.08.2026): то же самое, что fetch_site_text(), но через
    headless Chromium (Playwright) вместо голого HTTP-запроса — реально
    открывает страницу и ждёт отрисовки JS, поэтому видит контакты,
    которые обычный requests.get() не видит на сайтах-SPA.

    Требует предустановленных playwright + браузера Chromium:
        pip install playwright --break-system-packages
        playwright install --with-deps chromium
    Если playwright не установлен, браузера нет, или страница не
    открылась — тихо возвращает "" (тот же принцип "ничего не нашли —
    оставляем как было", что и у всех extract_*/fetch_* в этом файле).
    Пока не оптимизировано под массовый прогон: на каждый вызов заново
    поднимается и закрывается браузер (заметные накладные расходы) — это
    осознанный компромисс первой версии, вызывается только для явно
    подозрительных SPA-каркасов (см. _looks_like_js_shell), не на каждый
    сайт подряд. Если в проде окажется, что таких сайтов много и агент
    работает слишком медленно — следующий шаг: один браузер на весь
    прогон run_agent(), а не на каждый fetch отдельно.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("    ⚠️ playwright не установлен — пропускаю рендер JS для " + url)
        return ""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(user_agent="Mozilla/5.0")
                page.goto(url, timeout=15000, wait_until="networkidle")
                html = page.content()
            finally:
                browser.close()
            return html
    except Exception as e:
        print("    ⚠️ Playwright не смог открыть " + url + ": " + str(e))
        return ""


# Признаки того, что вместо реального содержимого страницы мы получили
# антибот-заглушку/капчу/чисто-JS-обёртку (реальный контент рендерится в
# браузере, а requests видит только "скелет"). Найдено 10.08.2026 на
# auto-auc.online: страница отдаёт только "Loading..." + "JavaScript
# отключен в вашем браузере" + ссылку на "Антибот Клауд", а при заходе
# через настоящий браузер там ещё и капча ("нажмите на похожий цвет").
# В таких случаях автоматически ничего не вытащить — компанию нужно
# ПОДСВЕТИТЬ для ручного ввода, а не молча пропустить/оставить как есть.
BOT_WALL_MARKERS = [
    "антибот",
    "antibot",
    "javascript отключен",
    "javascript is disabled",
    "enable javascript",
    "checking your browser",
    "just a moment",
    "attention required",
    "cloudflare",
    "verify you are human",
    "нажмите на похожий цвет",
    "подтвердите, что вы не робот",
    "captcha",
]


def looks_like_bot_wall(html):
    """True, если похоже, что requests получил антибот/капча-заглушку, а
    не реальный контент страницы — тогда искать в html ИНН/телефон/соцсети
    бессмысленно, компанию стоит явно пометить для ручной проверки."""
    if not html:
        return False
    t = html.lower()
    return any(marker in t for marker in BOT_WALL_MARKERS) and len(html) < 8000


# Слова-подсказки для поиска ссылок на "Контакты"/"О нас" и похожие
# подстраницы сайта. company_agent.py по умолчанию читает только главную
# страницу сайта — телефон, реквизиты (ИНН/ОГРН) и часть соцсетей у многих
# компаний лежат именно на этих подстраницах, а не в футере главной.
# Найдено 10.08.2026 на реальном примере: auto-asia25.ru ("Авто Азия") —
# на главной не было ни телефона, ни ИНН, ни правильного telegram, а на
# /contacts было всё сразу (пользователь прислал текст этой страницы и
# спросил "почему агент сам не вытащил?").
SUBPAGE_HINTS = [
    "contact",
    "contacts",
    "kontakt",
    "kontakty",
    "kontaktyi",
    "about",
    "o-nas",
    "onas",
    "o_nas",
    "o-kompanii",
    "o_kompanii",
    "company",
    "rekvizity",
    "requisites",
    "о нас",
    "контакт",
]


def find_subpage_urls(html, base_url, limit=3):
    """
    Ищем на главной странице ссылки на подстраницы вида "Контакты"/"О нас"
    (см. SUBPAGE_HINTS) — по href или по видимому тексту ссылки. Остаёмся
    на том же домене (не уходим по чужим ссылкам в футере) и берём не
    больше `limit` штук, чтобы не заваливать сайт компании лишними
    запросами.
    """
    if not html:
        return []
    base_domain = domain_of(base_url)
    if not base_domain:
        return []
    found = []
    seen = set()
    for m in re.finditer(
        r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL
    ):
        href, inner = m.group(1), m.group(2)
        link_text = re.sub(r"<[^>]+>", " ", inner).strip().lower()
        href_lower = href.lower()
        if not any(h in href_lower or h in link_text for h in SUBPAGE_HINTS):
            continue
        if href.startswith("http"):
            full = href
        elif href.startswith("/"):
            full = f"https://{base_domain}{href}"
        else:
            continue
        if domain_of(full) != base_domain:
            continue
        if full in seen:
            continue
        seen.add(full)
        found.append(full)
        if len(found) >= limit:
            break
    return found


def fetch_extra_site_text(html, base_url, limit=3):
    """
    Догружает и склеивает текст с подстраниц "Контакты"/"О нас" (см.
    find_subpage_urls). Вызывающий код решает, КОГДА это нужно (обычно —
    если с главной не хватило телефона/ИНН), чтобы не грузить сайты
    компаний лишними запросами без необходимости.
    """
    urls = find_subpage_urls(html, base_url, limit=limit)
    extra_text = ""
    for u in urls:
        t = fetch_site_text(u)
        if t:
            extra_text += " " + t
    return extra_text


def extract_brand_from_site(html):
    """
    Настоящее название бренда со страницы сайта — надёжнее, чем сырой
    <title> из поисковой выдачи (тот часто оказывается рекламным
    заголовком/SEO-текстом, а не именем компании: "Купить новое авто с
    доставкой" вместо "GazTormoz", "Японский аукцион автомобилей Toyota из
    Японии" вместо "ПримАвто"). Сайты обычно кладут настоящий бренд в
    og:site_name или apple-mobile-web-app-title — проверено вручную
    09.08.2026 на gaztormoz.ru (og:site_name: "GazTormoz") и tokidoki.su
    (apple-mobile-web-app-title: "ТокиДоки"). Если ни того ни другого нет —
    возвращаем "", вызывающий код падает обратно на clean_name_from_title.
    """
    if not html:
        return ""
    # Найдено 10.08.2026 (dryrun_reverify_sites.py по всей базе): страницы-
    # превью t.me/telegram.me и их зеркала-каталоги (уже частично отсечены
    # через BLACKLIST, но мало ли где ещё проскочит) отдают og:site_name
    # буквально "Telegram" — это НЕ бренд компании, а название платформы.
    # Такое значение отбрасываем, как будто его вообще не нашли.
    # T-90 (27.08.2026): та же болезнь нашлась у трёх живых карточек —
    # "Яндекс" (id 135, реальный сайт компании — estransit-premium.ru, но
    # og:site_name был взят со страницы-хаба на yandex.ru), "MAX" (id 122,
    # max.ru/dolgov_auto1 — реальное название "Долгов Авто", но og:site_name
    # мессенджера везде буквально "MAX") и "Tgsearch.Org" (id 120,
    # tgsearch.org/channel/... — это каталог-агрегатор тг-каналов, его
    # og:site_name везде "Tgsearch.Org", а не название конкретного канала).
    # Во всех трёх случаях страница-источник — не сайт самой компании, а
    # виджет/директория/мессенджер, чей og:site_name/apple-title указывает
    # на САМУ ПЛАТФОРМУ. Расширяем список так же, как раньше сделали для
    # Telegram/VK/Instagram/YouTube — если бренд буквально совпал с
    # известной платформой, откатываемся на title_name/domain_name.
    generic_brands = {
        "telegram", "вконтакте", "vkontakte", "instagram", "youtube",
        "яндекс", "yandex", "max", "макс", "tgsearch.org", "tgsearch",
        "2гис", "2gis", "авито", "avito", "дром", "drom",
        "авто.ру", "auto.ru", "autoru", "вк", "vk",
    }
    m = re.search(r'<meta property="og:site_name" content="([^"]+)"', html)
    if m and m.group(1).strip() and m.group(1).strip().lower() not in generic_brands:
        return m.group(1).strip()
    m = re.search(r'<meta name="apple-mobile-web-app-title" content="([^"]+)"', html)
    if m and m.group(1).strip() and m.group(1).strip().lower() not in generic_brands:
        return m.group(1).strip()
    return ""


def domain_of(url):
    """Домен без www/схемы/пути — для сравнения "это тот же сайт?" вместо
    точного совпадения полного URL (иначе japantransit.ru и
    japantransit.ru/japan/auctions считаются разными компаниями)."""
    m = re.search(r"https?://(?:www\.)?([^/]+)", url or "")
    return m.group(1).lower() if m else ""


def base_domain(url):
    """
    domain_of(), но дополнительно схлопывает поддомены до "базового"
    домена (последние 2 части) — иначе городской/региональный поддомен
    уже известного сайта считается НОВОЙ компанией. Баг найден 10.08.2026:
    "spb.westmotors.ru" (питерский поддомен уже существующего Westmotors,
    сайт которого westmotors.ru) прошёл дедуп как новая компания —
    domain_of() сравнивает домены буквально, без учёта поддоменов.
    Используем только для ДЕДУПА (не для is_real_profile_url и т.п.,
    где поддомен может быть значимым, например у 2ГИС/Дром).
    """
    d = domain_of(url)
    if not d:
        return ""
    parts = d.split(".")
    return ".".join(parts[-2:]) if len(parts) > 2 else d


def extract_years_experience(text):
    """
    Если у компании нет ИНН (или его проверка не даёт года регистрации),
    пробуем вытащить реальный стаж работы из текста самого сайта/канала:
    "с 2015 года", "работаем с 2015-го", "10 лет на рынке", "опыт 8+ лет".
    Возвращает int или None, если ничего похожего не нашли — в этом случае
    вызывающий код оставляет старый безопасный дефолт ("1" год), а не
    выдумывает цифру.
    """
    if not text:
        return None
    current_year = datetime.date.today().year
    m = re.search(r"с\s+(19\d{2}|20\d{2})[\s\-–]*(?:го)?\s*год", text, re.IGNORECASE)
    if m:
        year = int(m.group(1))
        if 1990 <= year <= current_year:
            return max(1, current_year - year)
    m = re.search(r"(\d{1,2})\+?\s*лет", text, re.IGNORECASE)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 40:
            return n
    return None


# Первые слова названий, которые слишком короткие или слишком общеупотребимы,
# чтобы одни, без остального названия, надёжно отличать "это точно ТА
# компания" от случайного совпадения на чужой странице. Баг найден
# 09.08.2026: "MY Avto" (id:1, компания САМОГО АВТОРА!) давала ключ "my" —
# обычное английское слово, встречается практически на любой странице с
# английским текстом; "Winner Auto Club" давала "winner" — тоже частое
# слово (казино/ставки/реклама и т.п.). Из-за этого find_platform_link при
# автопоиске недостающей карточки 2ГИС в fix_backfill_from_sources.py
# "подтвердил" СЛУЧАЙНУЮ карточку другой компании (2gis.ru/vladivostok/
# firm/70000001110946107 — не MY Avto), а раз карточка была принята,
# backfill_from_sources каскадно растащил из неё же ВСЕ остальные пустые
# поля (vk/instagram/telegram/avito/drom/autoru/max/youtube/rutube/
# whatsapp) — один неверный "якорь" заразил сразу много полей.
_GENERIC_NAME_WORDS = {
    "my",
    "the",
    "a",
    "auto",
    "avto",
    "car",
    "cars",
    "trade",
    "import",
    "impex",
    "group",
    "club",
    "center",
    "centre",
    "express",
    "asia",
    "east",
    "west",
    "north",
    "south",
    "global",
    "inter",
    "trans",
    "world",
    "winner",
    "premium",
    "elite",
    "prime",
    "star",
    "best",
    "top",
    "new",
    "first",
    "royal",
    "classic",
    "standard",
    # Кириллические аналоги — найдено 09.08.2026 на "Авто из Европы / Авто
    # Импорт ПРО": "авто" (4 символа — НЕ короче лимита в 4, поэтому не
    # ловилось прежним условием len(first)<4) — самое общеупотребимое
    # слово в этой нише вообще, встречается практически на любой странице
    # про машины. Из-за этого на карточку налипли telegram
    # @auto_import_cars_rus, vk antaresauto (.com и .ru), сайт
    # americanauto.ru?utm_source=2gis — явно чужие совпадения.
    "авто",
    "авта",
    "машина",
    "машины",
    "импорт",
    "экспорт",
    "групп",
    "клуб",
    "центр",
    "трейд",
    "трэйд",
    "сервис",
    "компания",
    "премиум",
    "элит",
    "топ",
    "новый",
    "новая",
    "первый",
    "классик",
    "стандарт",
}


def _name_key(name):
    """
    Ключ для сверки "это точно та компания?" в чужом тексте (сниппет DDG
    или содержимое страницы назначения). Обычно — первое слово названия
    ("CarsKorea" -> "carskorea"). Но если первое слово короче 4 символов
    ИЛИ входит в список общеупотребимых слов (_GENERIC_NAME_WORDS) — оно
    само по себе слишком ненадёжно (см. баг выше), берём первые ДВА слова
    вместе через пробел — такое сочетание уже гораздо специфичнее и
    случайно на чужой странице не совпадёт.
    """
    if not name:
        return ""
    words = [w for w in re.split(r"[\s.]+", name.lower()) if w]
    if not words:
        return ""
    first = words[0]
    if (len(first) < 4 or first in _GENERIC_NAME_WORDS) and len(words) > 1:
        return first + " " + words[1]
    return first


# VK: служебные разделы сайта (не группы/профили конкретной компании).
# Найдено 09.08.2026: "vk.com/js" (заглушка "включите JavaScript",
# отдаётся VK ботам без нормальных заголовков — по ошибке "подтвердилась"
# сразу для 4 РАЗНЫХ компаний, т.к. это общая страница, а не чья-то
# карточка), "vk.com/video"/"vk.com/clips" (общий раздел видео сайта, а не
# профиль компании).
VK_RESERVED_PATHS = {
    "js",
    "video",
    "videos",
    "wall",
    "photo",
    "photos",
    "clips",
    "away",
    "login",
    "join",
    "search",
    "catalog",
    "market",
    "games",
    "apps",
    "about",
    "help",
    "dev",
    "faq",
    "id",
    "feed",
    "audio",
    "music",
    "topic",
    "board",
    # "rtrg" — найдено 09.08.2026: это ссылка на РЕТАРГЕТИНГ-ПИКСЕЛЬ ВК
    # (vk.com/rtrg?...), техническая метка для рекламы, которую компании
    # вставляют себе на сайт как обычный <script>/<img> — не чей-то
    # профиль. Извлекалась напрямую с сайтов компаний (extract_social_
    # from_text доверяет прямым ссылкам с сайта без доп. проверки) и по
    # ошибке "подтвердилась" сразу для 3 РАЗНЫХ компаний (OTRADACARS,
    # Jplife, ТокиДоки) — тот же класс бага, что и "vk.com/js" раньше.
    "rtrg",
    "widget_comments",
    "share",
    "widget",
}

# Instagram: системные файлы/служебные разделы, не профиль компании.
# Найдено 09.08.2026: "instagram.com/favicon.ico" (иконка сайта!)
# "подтвердилась" как аккаунт компании.
INSTAGRAM_RESERVED_PATHS = {
    "favicon.ico",
    "p",
    "explore",
    "accounts",
    "reel",
    "reels",
    "stories",
    "tv",
    "about",
    "legal",
    "developer",
    "robots.txt",
}

# MAX: тот же класс бага — виджет "Поделиться в MAX"/кнопка подписки на
# сайте компании ведёт по общему техническому пути, а не на профиль
# компании. Найдено 09.08.2026: "max.ru/u" встретился СРАЗУ У СЕМИ разных
# компаний (DSS Group, Восток Транс Импорт, OTRADACARS, Autoimport.Group,
# CarsKorea, Es-Transit, Altais-Cars) — явно общий виджет-редирект, не
# профиль; "max.ru/join" тоже общее действие, не профиль.
MAX_RESERVED_PATHS = {"u", "join", "login", "share", "widget", "app", "id"}

# Прямые (без редиректов) ссылки на соцсети/маркетплейсы/мессенджеры —
# общий словарь для карточек 2ГИС, Яндекс.Карт и собственного сайта
# компании (везде, где такие ссылки могут встретиться в сыром HTML без
# площадко-специфичной обёртки вроде link.2gis.ru). Добавлено 09.08.2026.
DIRECT_CONTACT_PATTERNS = {
    "vk": r"https?://(?:www\.)?vk\.(?:com|ru)/[A-Za-z0-9_.\-]+",
    "instagram": r"https?://(?:www\.)?instagram\.com/[A-Za-z0-9_.\-]+",
    "avito": r"https?://(?:www\.)?avito\.ru/[A-Za-z0-9_/\-]+",
    "drom": r"https?://(?:www\.)?[a-z0-9\-]+\.drom\.ru/[A-Za-z0-9_/\-]*",
    "autoru": r"https?://(?:www\.)?auto\.ru/[A-Za-z0-9_/\-]+",
    # "+" добавлено 26.08.2026 (кейс Delivery Cars, delivery-cars.ru):
    # у части компаний ссылка на MAX — не юзернейм, а номер телефона вида
    # "max.ru/+79895653943", старая регулярка такие URL не матчила вообще
    # (в MAX_RESERVED_PATHS это тоже не попадает — это не служебный путь,
    # а просто другой формат профиля).
    "max": r"https?://(?:www\.)?max\.ru/[A-Za-z0-9_.+\-]+",
    "youtube": r"https?://(?:www\.)?youtube\.com/(?:@|channel/|c/)[A-Za-z0-9_.\-]+",
    "rutube": r"https?://(?:www\.)?rutube\.ru/(?:channel|u)/[A-Za-z0-9_.\-]+",
    # api.whatsapp.com/send?phone=... добавлено 14.08.2026 — реальный
    # пробел, найденный при ручной проверке China.Sferacar и Wanna-Car
    # (оба используют именно этот формат вместо короткого wa.me/, старый
    # регэксп его вообще не ловил, WhatsApp этих компаний был бы пропущен
    # даже несмотря на явное присутствие на сайте).
    # wa.me/message/<код> добавлено 27.08.2026 (кейс Fast Wheel,
    # fast-wheel.ru) — это отдельный формат короткой ссылки WhatsApp
    # Business (не номер телефона и не chat.whatsapp.com/код), тоже не
    # ловился ни одним из трёх старых вариантов.
    "whatsapp": r"https?://(?:chat\.whatsapp\.com/[A-Za-z0-9]+|wa\.me/message/[A-Za-z0-9]+|wa\.me/\d+|api\.whatsapp\.com/send\?phone=\d+[^\"'\s]*)",
    "yandex": r"https?://(?:www\.)?yandex\.\w+/maps/org/[A-Za-z0-9_\-]+/\d+",
    "gis2": r"https?://(?:www\.)?2gis\.\w+/[a-z\-]+/firm/\d+",
}

# Официальные соцсети/каналы самих площадок-агрегаторов (не компании!) —
# встречаются в футере/шапке их же карточек и по формату URL неотличимы от
# настоящего профиля компании. Найдено 09.08.2026 на живой карточке
# LikeAvto в Яндекс.Картах: внизу страницы — "vk.com/yandex.maps",
# "t.me/mapsyandex" — это соцсети самого Яндекс.Карт, не LikeAvto.
KNOWN_PLATFORM_OWN_ACCOUNTS = {
    "vk.com/yandex.maps",
    "vk.ru/yandex.maps",
    "t.me/mapsyandex",
    "vk.com/2gis",
    "vk.ru/2gis",
    "t.me/dvagis",
}


def _account_handle(url):
    """ "vk.com/likeavto_import" из полного URL — для сверки с
    KNOWN_PLATFORM_OWN_ACCOUNTS без привязки к схеме/query-строке."""
    m = re.search(r"https?://(?:www\.)?([^/]+/[^/?#]+)", url or "")
    return m.group(1).lower().rstrip("/") if m else ""


def normalize_whatsapp_link(url):
    """
    WhatsApp-ссылки встречаются в двух рабочих форматах на сайтах компаний:
    короткий "wa.me/<телефон>" и полный
    "api.whatsapp.com/send?phone=<телефон>&text=...". Оба одинаково рабочие,
    но полный обычно тащит за собой закодированный текст сообщения в query
    — хранить такое в таблице некрасиво и не нужно. Приводим оба варианта
    к единому чистому виду "https://wa.me/<цифры>".
    """
    m = re.search(r"(?:wa\.me/|whatsapp\.com/send\?phone=)(\d+)", url)
    return f"https://wa.me/{m.group(1)}" if m else url


def extract_direct_contacts(html):
    """
    Ищет прямые ссылки на все известные площадки (DIRECT_CONTACT_PATTERNS)
    в сыром HTML/тексте страницы — общая логика для карточек 2ГИС,
    Яндекс.Карт и собственного сайта компании. Берёт ПЕРВОЕ совпадение на
    каждую площадку, которое проходит is_real_profile_url И не является
    "родным" аккаунтом самой площадки-агрегатора (см.
    KNOWN_PLATFORM_OWN_ACCOUNTS). Ничего не выдумываем — не нашли, поле
    остаётся пустым.
    """
    result = {k: "" for k in DIRECT_CONTACT_PATTERNS}
    if not html:
        return result
    for kind, pattern in DIRECT_CONTACT_PATTERNS.items():
        for cand in re.findall(pattern, html):
            cl = cand.lower()
            if not is_real_profile_url(cl):
                continue
            if _account_handle(cl) in KNOWN_PLATFORM_OWN_ACCOUNTS:
                continue
            result[kind] = normalize_whatsapp_link(cand) if kind == "whatsapp" else cand
            break
    return result


# Найдено 14.08.2026 при ручной проверке нескольких компаний (ТамСямAUTO,
# Wanna-Car, Arnold-Auto, China.Sferacar, Jplife): у всех на собственном
# сайте была ссылка на t.me/<handle>, отдельная от Telegram-КАНАЛА — и
# каждый раз сайт сам явно её подписывал как контакт для переписки, не
# просто "наш канал". Универсальный принцип, не привязанный к нише авто —
# должен работать и для будущих направлений агента (см. обсуждение с
# пользователем 14.08.2026 про использование агента в других направлениях):
# ЛЮБАЯ компания, что бы она ни продавала, обычно различает у себя на
# сайте "подписывайтесь на канал" и "напишите нам" одинаково явно.
TG_CONTACT_LABEL_HINTS = [
    "написать",
    "message",
    "написать в telegram",
    "написать в тг",
    "написать менеджеру",
]


def extract_site_tg_contact(html):
    """
    Пытается найти на сайте компании личный/бот Telegram-контакт (не
    канал/группу) среди прямых ссылок на t.me — по двум независимым
    сигналам, оба найдены на реальных примерах 14.08.2026:
    1. Хэндл заканчивается на "bot" — практически всегда бот, принимающий
       сообщения (arnoldauto_bot, china_sferacar_web_bot — оба подтверждены
       вручную как messageable).
    2. Рядом со ссылкой (атрибут title/aria-label или видимый текст внутри
       <a>) есть слово из TG_CONTACT_LABEL_HINTS — сайты сами подписывают
       такие ссылки как "Написать в Telegram" (Wanna-Car: title="Написать в
       Telegram" у ссылки на WannaCarSales), в отличие от каналов, которые
       обычно подписаны "Подписывайтесь"/"Наш канал"/"Новости".

    Это ТОЛЬКО эвристика по разметке сайта, без похода на сам t.me (в
    отличие от fix_telegram_contact_check.py, который дополнительно
    проверяет subscribers/members) — вызывающий код может при желании
    дополнительно подтвердить находку отдельным запросом. Не нашли ни
    одного сигнала — возвращаем "", считаем все найденные t.me-ссылки
    каналами, добираем личный контакт другими путями (backfill/fix-скрипты).
    """
    if not html:
        return ""
    for m in re.finditer(
        r'<a\s+([^>]*)href=["\']https?://(?:www\.)?t\.me/([A-Za-z0-9_]+)["\']([^>]*)>(.*?)</a>',
        html,
        re.IGNORECASE | re.DOTALL,
    ):
        attrs_before, handle, attrs_after, inner = m.groups()
        if handle.lower().endswith("bot"):
            return handle
        surrounding = (
            attrs_before + " " + attrs_after + " " + re.sub(r"<[^>]+>", " ", inner)
        ).lower()
        if any(hint in surrounding for hint in TG_CONTACT_LABEL_HINTS):
            return handle
    return ""


def is_real_profile_url(link_lower):
    """
    Отсекаем ссылки, которые технически совпадают по домену, но заведомо
    НЕ являются карточкой/профилем компании: страница ПОИСКА (а не
    конкретной организации), отдельный пост/видео в чужой ленте VK, или
    служебный/общий раздел сайта (вроде "vk.com/js" — заглушка про
    JavaScript, не чей-то профиль; "instagram.com/favicon.ico" — иконка
    сайта). Найдено 09.08.2026 на реальных примерах в каталоге:
    yandex-кнопка у нескольких компаний вела на
    "yandex.ru/maps/search/{имя} {слово}" — это страница результатов
    поиска; VK-кнопка у другой компании вела на "vk.com/wall-.../123" —
    конкретный пост в чужом паблике; ещё у нескольких — на "vk.com/js"
    (общая заглушка) или "vk.com/video" (общий раздел, без ID) — ни то ни
    другое не относится к конкретной компании.
    """
    if "maps/search" in link_lower or "/search/" in link_lower or "?text=" in link_lower:
        return False
    if "vk.com" in link_lower or "vk.ru" in link_lower:
        if re.search(r"/(wall|video|photo|topic|board|clip)s?-?\d", link_lower):
            return False
        # Технические скрипты/пиксели VK (retargeting, openapi, share-виджеты
        # и т.п.) почти всегда отдаются как *.php — реальные профили/группы
        # никогда не заканчиваются на .php. Найдено 09.08.2026: "vk.com/
        # video_ext.php" (виджет встроенного видео) "подтвердился" как
        # профиль Worldcar — .php в пути был явным признаком, что это не
        # профиль, но старая проверка его не ловила.
        if ".php" in link_lower:
            return False
        m = re.search(r"vk\.(?:com|ru)/([a-z0-9_.\-]+)", link_lower)
        if m:
            first_seg = m.group(1).split("?")[0].rstrip("/")
            base = first_seg.split("-")[0]
            if base in VK_RESERVED_PATHS:
                return False
    if "instagram.com" in link_lower:
        if ".php" in link_lower:
            return False
        m = re.search(r"instagram\.com/([a-z0-9_.\-]+)", link_lower)
        if m:
            seg = m.group(1).split("?")[0].rstrip("/")
            if seg in INSTAGRAM_RESERVED_PATHS:
                return False
    if "max.ru" in link_lower:
        m = re.search(r"max\.ru/([a-z0-9_.+\-]+)", link_lower)
        if m:
            seg = m.group(1).split("?")[0].rstrip("/")
            if seg in MAX_RESERVED_PATHS:
                return False
    return True


def fetch_page_signal_text(url):
    """
    Для финальной проверки нужен текст СТРАНИЦЫ НАЗНАЧЕНИЯ, а не сниппет из
    поисковой выдачи. Берём и og:title/og:description (обычно рендерятся
    на сервере и присутствуют, даже если сама страница тяжёлая на JS вроде
    2ГИС/VK), и весь остальной HTML на всякий случай.
    """
    html = fetch_site_text(url)
    if not html:
        return ""
    parts = [html]
    for m in re.finditer(r'<meta property="og:(?:title|description)" content="([^"]*)"', html):
        parts.append(m.group(1))
    return " ".join(parts).lower()


def _matches_domain_filter(link_lower, filt):
    """
    Проверяем, что filt (домен площадки, возможно с путём вроде
    "yandex.ru/maps") встречается в link ИМЕННО как домен/поддомен, а не
    как случайная подстрока внутри СОВСЕМ ДРУГОГО домена.

    Баг найден 10.08.2026 (через dryrun_reverify_sites.py по всей базе):
    старая проверка "auto.ru" in link.lower() считала совпадением ссылки
    "http://intercityauto.ru" и "https://dolgov-auto.ru/" — это чужие/
    собственные домены компаний, просто оканчивающиеся на те же буквы, не
    имеющие отношения к площадке auto.ru. Из-за этого в поле "autoru" у
    двух разных компаний ("Авто из Европы / Авто Импорт" и "Долгов Авто")
    попали случайные (в одном случае — вообще чужой) сайты вместо ссылки
    на профиль auto.ru. Теперь домен-часть проверяется по границе
    поддомена (обязательная точка или начало строки перед ним), а не
    произвольной подстрокой.
    """
    if "/" in filt:
        domain_part, _, path_part = filt.partition("/")
    else:
        domain_part, path_part = filt, ""
    pattern = r"https?://(?:[a-z0-9\-]+\.)*" + re.escape(domain_part) + r"(?:/|\?|$)"
    if not re.search(pattern, link_lower):
        return False
    if path_part and path_part not in link_lower:
        return False
    return True


def find_platform_link(query, domain_filters, name_key="", phone_digits=""):
    """
    Ищем ссылку на конкретной площадке через DDG, привязываясь к домену
    (чтобы не взять случайную ссылку не по теме).

    История багов, которые это лечит (все найдены 09.08.2026 на реальных
    компаниях в каталоге):
    1. Раньше брали ПЕРВЫЙ результат с нужным доменом даже без
       подтверждения — чинили сверкой по сниппету поисковой выдачи.
    2. Но и сверка по сниппету ненадёжна сама по себе: сниппет DDG может
       обрезать текст или быть неточным, и формально "совпасть" по общему
       слову (например, часть названия), при этом сама ссылка на самом
       деле ведёт на СОВСЕМ ДРУГУЮ компанию — так были пойманы неверные
       2ГИС/VK-ссылки у Winner Auto Club, Artalex Group, Primorye China
       Export (2ГИС Артalex, например, реально вёл на другую фирму в том
       же доме в Москве — координаты в URL те же, компания другая).

    Поэтому проверка теперь в два шага: (а) сниппет — дешёвый
    предварительный фильтр, отсекает совсем не по теме результаты, (б)
    если сниппет прошёл — ОБЯЗАТЕЛЬНО фетчим саму ссылку и проверяем
    название/телефон уже в реальном содержимом страницы назначения
    (fetch_page_signal_text). Не удалось загрузить страницу или там нет
    совпадения — результат не считается подтверждённым, пробуем следующий.
    Возвращаем ссылку, только если ОБА шага прошли.
    """
    for r in search_ddgs(query, num=5):
        link = r.get("link") or ""
        link_lower = link.lower()
        if not any(_matches_domain_filter(link_lower, d) for d in domain_filters):
            continue
        if not is_real_profile_url(link_lower):
            continue
        snippet = ((r.get("title") or "") + " " + (r.get("snippet") or "")).lower()
        snippet_match = bool(
            (name_key and name_key in snippet)
            or (phone_digits and phone_digits in re.sub(r"\D", "", snippet))
        )
        if not snippet_match:
            continue
        page_text = fetch_page_signal_text(link)
        if not page_text:
            continue
        page_match = bool(
            (name_key and name_key in page_text)
            or (phone_digits and phone_digits in re.sub(r"\D", "", page_text))
        )
        if page_match:
            return link, True
    return "", False


def find_map_links(name, phone=""):
    """
    Ищем карточку компании на трёх картографических площадках. Никаких
    рейтингов отсюда не тянем (Google Maps/2ГИС отдают оценку только через
    JS, без платного API её надёжно не вытащить) — только ссылка, если
    карточка реально нашлась. Возвращает (yandex, google, gis2, verified) —
    verified=True, если хотя бы на одной площадке название/телефон реально
    совпали (используется как сигнал для проверки перед публикацией).
    """
    key = _name_key(name)
    pd = re.sub(r"\D", "", phone) if phone and phone != "-" else ""
    yandex, yv = find_platform_link(
        f"{name} отзывы", ["yandex.ru/maps", "yandex.com/maps"], key, pd
    )
    time.sleep(1)
    google, gv = find_platform_link(
        f"{name} отзывы", ["google.com/maps", "maps.app.goo.gl", "goo.gl/maps"], key, pd
    )
    time.sleep(1)
    gis2, g2v = find_platform_link(f"{name} отзывы 2гис", ["2gis.ru", "2gis.com"], key, pd)
    time.sleep(1)
    return yandex, google, gis2, (yv or gv or g2v)


def extract_social_from_text(text):
    """
    Ищем прямые ссылки на Instagram/VK в самом тексте страницы (обычно
    в футере сайта) — это надёжнее, чем поиск, если компания сама уже
    указала ссылку у себя на сайте.

    ВАЖНО: сайты часто встраивают виджет ВКонтакте (кнопка "Поделиться",
    комментарии) — его SDK грузится со скрипта вида
    "vk.com/js/api/openapi.js?169", и старый regex.search() (первое
    совпадение) хватал именно его, обрезая по первому "/" до "vk.com/js" —
    служебный путь, не профиль компании. Баг найден 09.08.2026: несколько
    компаний получили в поле VK именно "vk.com/js" вместо настоящей
    страницы (или вместо пустого поля, если настоящей ссылки на сайте
    нет). Теперь: собираем ВСЕ совпадения (re.findall), а не только первое,
    и берём первое, которое проходит is_real_profile_url — то есть реально
    похоже на профиль/группу, а не на служебный путь площадки.
    """
    insta, vk = "", ""
    if text:
        for cand in re.findall(r"https?://(?:www\.)?instagram\.com/[A-Za-z0-9_.\-]+", text):
            if is_real_profile_url(cand.lower()):
                insta = cand
                break
        # ВКонтакте переезжает на новый домен vk.ru — старый vk.com пока
        # тоже работает, но сайты компаний всё чаще ставят у себя именно
        # vk.ru-ссылку. Баг найден 09.08.2026 на EncarRus: на сайте прямым
        # текстом была ссылка на vk.ru/encarrus, но регэксп её не поймал
        # (искал только vk.com) — агент вместо неё нашёл что-то постороннее
        # через DDG-поиск. Ловим оба домена.
        for cand in re.findall(r"https?://(?:www\.)?vk\.(?:com|ru)/[A-Za-z0-9_.\-]+", text):
            if is_real_profile_url(cand.lower()):
                vk = cand
                break
    return insta, vk


def extract_extra_contacts_from_text(text):
    """
    То же самое, что extract_social_from_text, но для мессенджера MAX
    (max.ru/username), YouTube, RuTube и WhatsApp-группы — нужны для
    правила приоритета клика по карточке (см. update_site.py: site >
    telegram > instagram > vk > max > youtube > rutube > whatsapp).
    Добавлено 09.08.2026 по просьбе пользователя. Ищем прямые ссылки в
    тексте/футере сайта — компания сама их указала, это надёжнее поиска.
    """
    result = {"max": "", "youtube": "", "rutube": "", "whatsapp": ""}
    if not text:
        return result
    for cand in re.findall(r"https?://(?:www\.)?max\.ru/[A-Za-z0-9_.\-]+", text):
        if is_real_profile_url(cand.lower()):
            result["max"] = cand
            break
    for cand in re.findall(
        r"https?://(?:www\.)?youtube\.com/(?:@|channel/|c/)[A-Za-z0-9_.\-]+", text
    ):
        result["youtube"] = cand
        break
    for cand in re.findall(r"https?://(?:www\.)?rutube\.ru/(?:channel|u)/[A-Za-z0-9_.\-]+", text):
        result["rutube"] = cand
        break
    for cand in re.findall(r"https?://chat\.whatsapp\.com/[A-Za-z0-9]+", text):
        result["whatsapp"] = cand
        break
    if not result["whatsapp"]:
        for cand in re.findall(r"https?://wa\.me/\d+", text):
            result["whatsapp"] = cand
            break
    if not result["whatsapp"]:
        # api.whatsapp.com/send?phone=... — добавлено 14.08.2026, см.
        # normalize_whatsapp_link (тот же пробел, что чинили в
        # DIRECT_CONTACT_PATTERNS: реальные сайты China.Sferacar/Wanna-Car
        # используют именно этот формат, короткий wa.me/ у них не было).
        for cand in re.findall(r"https?://api\.whatsapp\.com/send\?phone=\d+[^\"'\s]*", text):
            result["whatsapp"] = normalize_whatsapp_link(cand)
            break
    return result


def find_social_links(name, text="", phone=""):
    """Instagram/VK компании — сначала пробуем достать прямо со страницы
    (см. extract_social_from_text — прямая ссылка от самой компании уже
    считается подтверждением), а если там нет — ищем через DDG. Возвращает
    (insta, vk, verified)."""
    insta, vk = extract_social_from_text(text)
    verified = bool(insta or vk)
    key = _name_key(name)
    pd = re.sub(r"\D", "", phone) if phone and phone != "-" else ""
    if not insta:
        insta, iv = find_platform_link(f"{name} instagram", ["instagram.com"], key, pd)
        verified = verified or iv
        time.sleep(1)
    if not vk:
        vk, vv = find_platform_link(f"{name} вконтакте", ["vk.com", "vk.ru"], key, pd)
        verified = verified or vv
        time.sleep(1)
    return insta, vk, verified


def find_marketplace_links(name, phone=""):
    """
    Ищем объявления/карточку компании на маркетплейсах (Авито, Дром,
    Авто.ру) — тоже только ссылка, без выдуманных цифр. Возвращает
    (avito, drom, autoru, verified).
    """
    key = _name_key(name)
    pd = re.sub(r"\D", "", phone) if phone and phone != "-" else ""
    avito, av = find_platform_link(f"{name} avito", ["avito.ru"], key, pd)
    time.sleep(1)
    drom, dv = find_platform_link(f"{name} drom", ["drom.ru"], key, pd)
    time.sleep(1)
    autoru, aruv = find_platform_link(f"{name} auto.ru", ["auto.ru"], key, pd)
    time.sleep(1)
    return avito, drom, autoru, (av or dv or aruv)


def extract_contacts_from_2gis(html):
    """
    2ГИС отдаёт карточку организации с серверным рендерингом (проверено
    вручную 09.08.2026 на живой карточке LikeAvto в Чите:
    2gis.ru/chita/firm/70000001039726563 — в HTML прямо лежат ссылка на
    сайт likeavto.ru, ВКонтакте, Telegram-канал, YouTube, WhatsApp). Раньше
    2ГИС использовался только как ПЛОЩАДКА ДЛЯ ПРОВЕРКИ уже найденных
    ссылок (find_map_links) — но не как ИСТОЧНИК для поиска сайта/соцсетей,
    хотя сама компания уже все их указала в своём профиле 2ГИС. Пользователь
    нашёл сайт LikeAvto именно так — вручную зайдя на карточку в 2ГИС,
    попросил добавить это в алгоритм агента.

    Сайт на карточке 2ГИС обычно обёрнут в редирект-ссылку вида
    "link.2gis.ru/.../?http://домен.ru" — настоящий адрес идёт после
    последнего "?http". Telegram/VK/Instagram/маркетплейсы бывают и в таких
    же обёртках, и прямыми ссылками — поэтому классифицируем ПО ДОМЕНУ
    целевого адреса, а не по порядку блоков на странице (порядок может
    отличаться от карточки к карточке).

    Возвращает dict {"site","telegram","vk","instagram","avito","drom",
    "autoru","max","youtube","rutube","whatsapp"} — пустая строка, если
    что-то не нашлось. Ничего не выдумываем: не смогли распарсить — поле
    просто остаётся пустым, вызывающий код может попробовать другие
    источники.

    max/youtube/rutube/whatsapp добавлены 09.08.2026 — нужны для правила
    приоритета клика по карточке на сайте (site > telegram > instagram >
    vk > max > youtube > rutube > whatsapp), карточка 2ГИС уже отдаёт
    YouTube/WhatsApp напрямую (видно на живом примере LikeAvto), раньше
    просто игнорировались.
    """
    result = {
        "site": "",
        "telegram": "",
        "vk": "",
        "instagram": "",
        "avito": "",
        "drom": "",
        "autoru": "",
        "max": "",
        "youtube": "",
        "rutube": "",
        "whatsapp": "",
    }
    if not html:
        return result

    def classify(url):
        u = url.lower()
        if "t.me" in u or "telegram.me" in u:
            return "telegram"
        if "vk.com" in u or "vk.ru" in u:
            return "vk"
        if "instagram.com" in u:
            return "instagram"
        if "avito.ru" in u:
            return "avito"
        if "drom.ru" in u:
            return "drom"
        if "auto.ru" in u:
            return "autoru"
        if "max.ru" in u:
            return "max"
        if "youtube.com" in u or "youtu.be" in u:
            return "youtube"
        if "rutube.ru" in u:
            return "rutube"
        if "wa.me" in u or "whatsapp.com" in u:
            return "whatsapp"
        if "2gis." in u:
            return None
        return "site"

    # Ссылки, обёрнутые в редирект 2ГИС (link.2gis.ru/...?http://...)
    for target in re.findall(r"link\.2gis\.ru/[^\"'<>\s]*?\?(https?://[^\"'<>\s&]+)", html):
        kind = classify(target)
        if not kind or result.get(kind):
            continue
        if kind == "telegram":
            m = re.search(r"t\.me/([A-Za-z0-9_]+)", target, re.IGNORECASE)
            if m:
                result["telegram"] = m.group(1)
        elif kind == "whatsapp":
            result[kind] = normalize_whatsapp_link(target)
        else:
            result[kind] = target

    # Прямые (без обёртки) ссылки на соцсети/маркетплейсы/мессенджеры в HTML —
    # общая функция extract_direct_contacts (см. выше), делит логику с
    # extract_contacts_from_yandex.
    direct = extract_direct_contacts(html)
    for kind, val in direct.items():
        if kind in result and val and not result[kind]:
            result[kind] = val

    if not result["telegram"]:
        m = re.search(r"https?://(?:www\.)?t\.me/([A-Za-z0-9_]+)", html, re.IGNORECASE)
        if m:
            result["telegram"] = m.group(1)

    return result


def extract_contacts_from_yandex(html):
    """
    Яндекс.Карты отдают карточку организации тоже с серверным рендерингом
    (проверено вручную 09.08.2026 на живой карточке LikeAvto:
    yandex.com/maps/org/likeavto/111072758131/ — в разделе "Contacts"
    прямым текстом лежат сайт likeavto.ru, t.me/likeavto_import,
    wa.me/79243878787, youtube.com/@likeavto_import, vk.com/likeavto_import
    — БЕЗ редиректной обёртки, в отличие от 2ГИС). Добавлено по просьбе
    пользователя: бэкофилл не должен ограничиваться только 2ГИС — если
    данные есть на Яндекс.Картах, надо брать их оттуда же.

    ВАЖНО: в футере той же страницы (уже за пределами карточки компании)
    Яндекс.Карты рекламируют СВОИ СОБСТВЕННЫЕ соцсети
    ("vk.com/yandex.maps", "t.me/mapsyandex") — по формату URL это
    неотличимо от настоящего профиля компании, но это НЕ компания.
    Отфильтровано через KNOWN_PLATFORM_OWN_ACCOUNTS в extract_direct_contacts.

    Сайт компании на Яндекс.Картах — обычная прямая ссылка вида
    `<a href="https://likeavto.ru/">likeavto.ru</a>` (текст ссылки — сам
    домен), без спецобёртки. Ищем анкор, где видимый текст совпадает с
    доменом из href — это надёжно отличает "официальный сайт" от любых
    других ссылок Яндекса на странице (внутренние ссылки на разделы карт
    так не оформлены).

    Возвращает тот же набор ключей, что и extract_contacts_from_2gis.
    """
    result = {
        "site": "",
        "telegram": "",
        "vk": "",
        "instagram": "",
        "avito": "",
        "drom": "",
        "autoru": "",
        "max": "",
        "youtube": "",
        "rutube": "",
        "whatsapp": "",
    }
    if not html:
        return result

    m = re.search(
        r'<a[^>]+href="(https?://(?:www\.)?([a-z0-9][a-z0-9\-]*\.[a-z]{2,})[^"]*)"[^>]*>\s*(?:<[^>]+>\s*)*\2',
        html,
        re.IGNORECASE,
    )
    if m and "yandex." not in m.group(2).lower():
        result["site"] = m.group(1)

    if not result["telegram"]:
        tm = re.search(r"https?://(?:www\.)?t\.me/([A-Za-z0-9_]+)", html, re.IGNORECASE)
        if tm and _account_handle(tm.group(0)) not in KNOWN_PLATFORM_OWN_ACCOUNTS:
            result["telegram"] = tm.group(1)

    direct = extract_direct_contacts(html)
    for kind, val in direct.items():
        if kind in result and val and not result[kind]:
            result[kind] = val

    return result


def backfill_from_2gis(gis2_url, current):
    """
    Дозаполняет ТОЛЬКО пустые поля из уже подтверждённой карточки 2ГИС
    (gis2_url должен быть результатом find_map_links с verified=True —
    сюда НЕ передаём непроверенные ссылки). Никогда не перезаписывает уже
    найденное другим путём значение — 2ГИС тут дополнительный источник,
    а не приоритетный.

    current — dict с текущими значениями (может не содержать всех ключей).
    Возвращает новый dict с теми же ключами, что и extract_contacts_from_2gis,
    дополненный тем, что уже было в current.
    """
    filled = dict(current)
    if not gis2_url or not gis2_url.startswith("http"):
        return filled
    html = fetch_site_text(gis2_url)
    found = extract_contacts_from_2gis(html)
    for key, val in found.items():
        if val and not filled.get(key):
            filled[key] = val
            print(f"    из карточки 2ГИС нашлось {key}: {val}")
    return filled


def backfill_from_sources(sources, current, content_check=None):
    """
    Обобщение backfill_from_2gis: дозаполняет пустые поля из НЕСКОЛЬКИХ
    подтверждённых источников подряд, а не только 2ГИС — по просьбе
    пользователя ("заполнять можно не только тугиз, а из известных
    источников карточки, если есть на яндексе данные то добираем оттуда,
    есть сайт — берём оттуда"). Идём по source'ам В ПОРЯДКЕ ПРИОРИТЕТА,
    пока не заполнены все поля; каждый следующий источник добавляет только
    то, что предыдущие не нашли — никогда не перезаписывает уже найденное.

    sources — список кортежей (kind, url), kind один из "site"/"2gis"/
    "yandex". Для "site" используется own-site-текст (компания не может
    указать сама себя как "сайт", это поле просто не заполняется этим
    источником, но заполняет все остальные — telegram/vk/instagram/
    max/youtube/rutube/whatsapp/маркетплейсы). url для "site" должен быть
    самим сайтом компании — используем ту же fetch_site_text.

    content_check — необязательная пара (name_key, phone_digits): если
    передана, каждый источник сначала проверяется на то, что страница
    реально про эту компанию (название/телефон встречаются в её тексте) —
    та же осторожность, что и в find_platform_link/content-верификации.
    Не прошло проверку — источник пропускается целиком, ничего из него не
    берём (может быть "чужая" карточка, которая случайно осталась в
    таблице от старой, менее строгой проверки).

    current — dict с текущими значениями. Возвращает новый dict.
    """
    filled = dict(current)
    for kind, url in sources:
        if not url or not url.startswith("http"):
            continue
        html = fetch_site_text(url)
        if not html:
            continue
        if content_check:
            name_key, phone_digits = content_check
            text_lower = html.lower()
            digits = "".join(ch for ch in text_lower if ch.isdigit())
            name_match = bool(name_key and name_key in text_lower)
            phone_match = bool(phone_digits and phone_digits in digits)
            if not (name_match or phone_match):
                print(f"    ⚠️ карточка {kind} не подтверждает название/телефон — пропускаю")
                continue
        if kind == "2gis":
            found = extract_contacts_from_2gis(html)
        elif kind == "yandex":
            found = extract_contacts_from_yandex(html)
        elif kind == "site":
            insta, vk = extract_social_from_text(html)
            extra = extract_extra_contacts_from_text(html)
            direct = extract_direct_contacts(html)
            found = {
                "telegram": "",
                "vk": vk,
                "instagram": insta,
                "avito": direct.get("avito", ""),
                "drom": direct.get("drom", ""),
                "autoru": direct.get("autoru", ""),
                "max": extra.get("max", ""),
                "youtube": extra.get("youtube", ""),
                "rutube": extra.get("rutube", ""),
                "whatsapp": extra.get("whatsapp", ""),
            }
            tm = re.search(r"https?://(?:www\.)?t\.me/([A-Za-z0-9_]+)", html, re.IGNORECASE)
            if tm:
                found["telegram"] = tm.group(1)
        else:
            continue
        for key, val in found.items():
            if val and not filled.get(key):
                filled[key] = val
                print(f"    из карточки {kind} нашлось {key}: {val}")
    return filled


def mentions_ukraine(text):
    # Ловит "Украина/Украину/Украины/украинский" и т.п. — любые формы
    # с корнем "укра". Сайт нацелен на СНГ (Россия, Казахстан, Беларусь...),
    # компании, которые возят машины в Украину, сюда не нужны.
    return bool(re.search(r"укра", text, re.IGNORECASE))


def is_vin_check_service(text):
    """
    Отсекаем сервисы/боты ПРОВЕРКИ авто по VIN/госномеру (SonarBot и
    похожие) — они почти всегда упоминают слово "авто" сколько угодно раз
    и формально проходят обычную проверку has_auto, но это НЕ компания по
    ИМПОРТУ авто, а инструмент проверки истории машины. Найдено
    09.08.2026 на живом прогоне через cron: "SonarBot" (Telegram-бот
    "Проверяйте автомобиль перед покупкой... Введите VIN или госномер")
    ошибочно попал в каталог как импортёр.

    Сигнал: одновременно упоминаются и "бот"/"сервис", и явная лексика
    проверки (VIN, госномер, пробив, история авто) — реальные компании по
    импорту иногда предлагают проверку авто ПЕРЕД покупкой как одну из
    услуг, но не строят вокруг этого всё описание и не называют себя
    "бот для пробива/проверки".
    """
    t = text.lower()
    has_bot_or_service = ("бот" in t) or ("сервис проверки" in t)
    has_check_lexicon = any(
        w in t
        for w in [
            "пробив авто",
            "пробив по vin",
            "пробить авто",
            "проверка vin",
            "проверить vin",
            "vin-check",
            "vin check",
            "по vin или",
            "введите vin",
            "госномер",
            "автокриминалист",
            # 13.08.2026: auto-praktis.vercel.app — статья "как бесплатно
            # проверить историю автомобиля через Telegram-боты: от VIN-кода
            # до штрафов" формально проходила старый список (ни одна фраза не
            # совпадала буквально).
            "vin-кода",
            "vin-код",
            "историю автомобиля",
        ]
    )
    return has_bot_or_service and has_check_lexicon


def is_customs_broker(text):
    """
    Отсекаем таможенных брокеров/представителей (оформление ЛЮБЫХ грузов,
    не именно покупка/доставка авто) — 13.08.2026, пользователь открыл на
    сайте отдельное направление "Таможенные брокеры" (каталог наполняется
    вручную, см. секцию #customs в index.html) и попросил не смешивать
    его с каталогом импортёров авто. Такие компании часто упоминают
    "авто"/"автомобили" как один из видов грузов и формально проходят
    has_auto, но сами себя называют не "импортёр"/"пригон", а
    "таможенный брокер"/"таможенный представитель"/"декларант" — это
    отдельная ниша. Сигнал узкий и специфичный: обычные компании по
    пригону авто себя так не называют, даже если растаможка — часть их
    услуги.
    """
    t = text.lower()
    return any(
        w in t
        for w in [
            "таможенный брокер",
            "таможенный представитель",
            "таможенного представителя",
            "таможенным представителем",
            "декларант",
            "услуги по таможенному оформлению",
            "склад временного хранения",
            " свх ",
        ]
    )


def get_directions(text):
    t = text.lower()
    dm = {
        "Китай": ["китай", "china", "byd", "haval", "geely", "chery", "далянь"],
        "Корея": ["корея", "korea", "kia", "hyundai", "genesis"],
        "Япония": ["япония", "japan", "toyota", "lexus", "honda", "nissan", "mazda"],
        "США": ["сша", "usa", "america", "tesla", "ford", "cadillac"],
        "ОАЭ": ["оаэ", "uae", "dubai", "эмираты"],
        "Европа": ["европа", "europe", "bmw", "mercedes", "audi", "volkswagen"],
        "Канада": ["канада", "canada"],
        "Грузия": ["грузия", "georgia"],
        "Армения": ["армения", "armenia"],
    }
    dirs = [d for d, kws in dm.items() if any(k in t for k in kws)]
    return dirs if dirs else ["Не указано"]


def get_tags(text):
    t = text.lower()
    tags = []
    if "под ключ" in t:
        tags.append("Под ключ")
    if "растаможк" in t:
        tags.append("Растаможка")
    if "аукцион" in t:
        tags.append("Аукционы")
    if "параллельн" in t:
        tags.append("Параллельный импорт")
    if "наличи" in t:
        tags.append("В наличии")
    # Ещё один частый продающий тезис в нише (см. SELLING_PHRASES) — "без
    # посредников"/"напрямую" — раньше никак не попадал в теги.
    if "без посредник" in t or "напрямую" in t:
        tags.append("Без посредников")
    return tags if tags else ["Импорт авто"]


def search_tgstat(query):
    url = "https://tgstat.ru/channels/search?q=" + requests.utils.quote(query) + "&country=ru"
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return []
        return list(set(re.findall(r"@([A-Za-z0-9_]{3,32})", r.text)))[:10]
    except Exception:  # T-73 (21.08.2026): было голое except:, см. check_site()
        return []


def _extract_tgstat_title(html):
    """
    Настоящее название канала (не @username) — пробуем og:title, потом
    обычный <title>. tgstat обычно кладёт туда что-то вроде
    "Название канала - Telegram канал статистика...", берём первый
    осмысленный сегмент через clean_name_from_title.
    """
    m = re.search(r'<meta property="og:title" content="([^"]+)"', html)
    if m:
        title = clean_name_from_title(m.group(1))
        if title:
            return title
    m = re.search(r"<title>([^<]+)</title>", html)
    if m:
        title = clean_name_from_title(m.group(1))
        if title:
            return title
    return ""


def parse_tgstat_channel(username):
    try:
        r = requests.get(
            "https://tgstat.ru/channel/@" + username,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if r.status_code != 200:
            return None
        html = r.text
        subs_m = re.search(r"(\d[\d\s]+)\s*подписчик", html)
        subs = int(subs_m.group(1).replace(" ", "")) if subs_m else 0
        desc_m = re.search(r"peer-description[^>]*>(.*?)</div>", html, re.DOTALL)
        desc = re.sub(r"<[^>]+>", "", desc_m.group(1)).strip()[:200] if desc_m else ""
        title = _extract_tgstat_title(html)
        return {"subscribers": subs, "description": desc, "title": title}
    except Exception:  # T-73 (21.08.2026): было голое except:, см. check_site()
        return None


def fetch_telegram_preview(username):
    """
    Резерв на случай, если tgstat.ru не проиндексировал канал (обычно —
    небольшие каналы, мало подписчиков). Публичная превью-страница
    t.me/<username> отдаёт og:title/og:description и число подписчиков
    без JS — этого достаточно, чтобы добавить канал, даже если tgstat
    его не знает.
    """
    try:
        r = requests.get(
            f"https://t.me/{username}",
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0"},
            proxies=PROXIES,
        )
        if r.status_code != 200:
            return None
        html = r.text
        title_m = re.search(r'<meta property="og:title" content="([^"]*)"', html)
        desc_m = re.search(r'<meta property="og:description" content="([^"]*)"', html)
        subs_m = re.search(r"([\d\s]+)\s*subscribers", html)
        title = title_m.group(1).strip() if title_m else ""
        desc = desc_m.group(1).strip() if desc_m else ""
        subs = int(subs_m.group(1).replace(" ", "")) if subs_m else 0
        if not title and not desc:
            return None
        return {"subscribers": subs, "description": desc, "title": clean_channel_title(title)}
    except Exception:
        return None


def _extract_vk_members(html):
    if not html:
        return 0
    m = re.search(r'"members_count"\s*:\s*(\d+)', html)
    if m:
        return int(m.group(1))
    m = re.search(r"([\d\s\xa0]+)\s*(?:подписчик|участник)", html)
    if m:
        digits = re.sub(r"[^\d]", "", m.group(1))
        return int(digits) if digits else 0
    return 0


def fetch_vk_members(url):
    """
    Число подписчиков паблика VK — T-92 (27.08.2026, статистика активности
    компаний по запросу пользователя: "рост подписчиков в соцсетях").
    Официального публичного API без токена нет, поэтому парсим саму
    HTML-страницу группы: число обычно зашито либо в инлайн-JSON
    ("members_count":N), либо прямым текстом ("12 345 подписчиков"/
    "12 345 участников" — старые/мобильные версии).

    Найдено на реальном прогоне 27.08.2026: из 61 компании с VK-ссылкой
    обычный requests.get() дал ненулевой результат только у ОДНОЙ — то
    есть VK, как и React/Next.js-сайты в T-89, требует JS для отрисовки
    этого числа в подавляющем большинстве случаев (проверено вручную
    через живой браузер: "members_count" реально есть в DOM ПОСЛЕ
    рендера, но не в сыром HTML с сервера). Поэтому та же тактика, что в
    fetch_site_text() — сначала дешёвый обычный запрос, и только если он
    не дал числа, дорогой Playwright-рендер как fallback (не платим
    стоимостью браузера, когда обычный запрос уже сработал).
    """
    if not url:
        return 0
    try:
        r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        html = r.text if r.status_code == 200 else ""
    except Exception:
        html = ""
    count = _extract_vk_members(html)
    if count:
        return count
    rendered = fetch_site_text_rendered(url)
    return _extract_vk_members(rendered)


def fetch_instagram_followers(url):
    """
    Число подписчиков Instagram — T-92 (27.08.2026). С 2020 года Meta
    агрессивно блокирует скрапинг (login wall почти на все запросы без
    авторизованной сессии) — это НЕ надёжный источник, best-effort через
    og:description (исторический формат "N Followers, M Following, K
    Posts", который иногда всё ещё отдаётся публичным профилям без
    логина). Часто будет молча возвращать 0 — это ожидаемо для Instagram,
    не баг конкретной компании, см. тот же safety-net принцип выше.
    """
    if not url:
        return 0
    try:
        r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return 0
        html = r.text
        m = re.search(r'content="([\d.,]+)\s*([KkMm]?)\s*[Ff]ollowers', html)
        if not m:
            return 0
        raw = m.group(1).replace(",", "")
        suffix = m.group(2).lower()
        mult = 1000 if suffix == "k" else 1000000 if suffix == "m" else 1
        return int(float(raw) * mult)
    except Exception:
        return 0


def fetch_url_og_title(url, use_proxy=False):
    """
    Универсальная выборка og:title с произвольной страницы (VK, Instagram,
    любой сайт) — 14.08.2026, для сверки имени компании сразу по нескольким
    источникам, а не по одному сайту (см. verify_company_name). og:title
    обычно рендерится на сервере, доступен даже на страницах, тяжёлых на
    JS (VK/Instagram/2ГИС) — та же логика, что уже используется в
    fetch_page_signal_text.
    """
    try:
        r = requests.get(
            url,
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0"},
            proxies=PROXIES if use_proxy else None,
        )
        if r.status_code != 200:
            return ""
        m = re.search(r'<meta property="og:title" content="([^"]*)"', r.text)
        return clean_name_from_title(m.group(1)) if m else ""
    except Exception:
        return ""


def _name_key_words(name):
    return {w for w in re.findall(r"[a-zа-я0-9]+", name.lower()) if len(w) >= 3}


def verify_company_name(name, tg="", vk="", instagram=""):
    """
    Сверяем выбранное имя компании по независимым источникам, прежде чем
    вносить в каталог — 14.08.2026, по просьбе пользователя после разбора
    карточек TGLand.ru/Zenstat/Free Telegram Groups/Телепот: во всех
    случаях `site` оказывался ЧУЖОЙ площадкой-каталогом (Telegram/Дзен-
    зеркалом), и og:site_name с неё называл каталог, а не саму компанию.
    Эти конкретные площадки теперь в BLACKLIST, но сама болезнь общая —
    любой будущий каталог-зеркало, ещё не попавший в BLACKLIST, наступит
    на те же грабли.

    Источники сверки — собственная страница компании на других площадках
    (Telegram-канал, VK, Instagram), если они уже известны на этот момент.
    Если хотя бы один источник даёт название БЕЗ общих слов с текущим
    (расхождение) и само по себе не похоже на рекламный слоган — считаем
    его более надёжным (это страница о САМОЙ компании, не о площадке,
    через которую её нашли) и подменяем имя. Если источников для сверки
    нет или все совпадают — оставляем как было.

    Не является железной гарантией (например, если у площадки-зеркала
    случайно нет ни телеграма, ни VK/Instagram в найденных полях — сверить
    не с чем), поэтому предупреждение "имя взято из домена" в вызывающем
    коде оставлено как есть — это доп. страховка, а не замена.
    """
    own_key = _name_key_words(name)
    checks = []
    if tg:
        checks.append(("telegram", fetch_url_og_title(f"https://t.me/{tg}", use_proxy=True)))
    if vk:
        checks.append(("vk", fetch_url_og_title(vk)))
    if instagram:
        checks.append(("instagram", fetch_url_og_title(instagram)))
    for source, cand_name in checks:
        if not cand_name or is_probably_tagline(cand_name):
            continue
        cand_key = _name_key_words(cand_name)
        if cand_key and not (cand_key & own_key):
            print(
                f"    ⚠️ имя разошлось с {source} ('{cand_name}' vs '{name}') — беру {source} как более надёжный источник (это страница самой компании)"
            )
            return cand_name
    return name


def clean_channel_title(title):
    """Название телеграм-канала часто обвешано эмодзи и уточнением в
    скобках ("🇯🇵🚘JAPANCARs-NVRSK(авто под заказ...)") — убираем эмодзи
    спереди и оставляем текст до открывающей скобки, уточнение и так
    попадёт в описание отдельным полем."""
    if not title:
        return ""
    t = re.sub(r"^[^\wА-Яа-яЁё]+", "", title).strip()
    m = re.match(r"^([^(]+)", t)
    if m:
        t = m.group(1).strip(" -")
    return t or title


def search_ddgs(query, num=5):
    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=num, region="ru-ru"):
                results.append(
                    {
                        "title": r.get("title", ""),
                        "snippet": r.get("body", ""),
                        "link": r.get("href", ""),
                    }
                )
        return results
    except Exception as e:
        print("Ошибка поиска: " + str(e))
        return []


def get_existing(ws):
    try:
        data = ws.get_all_values()
        ex = set()
        for row in data[1:]:
            if len(row) > 1 and row[1]:
                ex.add(row[1].lower().strip())
            if len(row) > 9 and row[9]:
                ex.add(row[9].lower().strip())
            if len(row) > 11 and row[11]:
                ex.add(row[11].lower().strip())
            # Домен сайта отдельно от полного URL — иначе одна и та же
            # компания под разными страницами (japantransit.ru vs
            # japantransit.ru/japan/auctions) считается двумя разными
            # компаниями (баг 09.08.2026: одна фирма добавилась дважды из
            # разных подстраниц одного сайта в разных поисковых запросах).
            if len(row) > 11 and row[11]:
                d = base_domain(row[11])
                if d:
                    ex.add(d)
        return ex
    except Exception:  # T-73 (21.08.2026): было голое except:, см. check_site()
        return set()


def add_company(ws, data, row_num):
    # Колонка 31 (AE) добавлена 14.08.2026 по просьбе пользователя: поле
    # "telegram" (колонка 10) — это КАНАЛ/ГРУППА компании (то, что находит
    # tgstat/поиск), у канала нет чата, написать в него нельзя. Новая колонка
    # "telegram_contact" — личный аккаунт/бот для переписки, если он вообще
    # известен. Агент пока не умеет сам искать личный контакт при добавлении
    # новой компании (это отдельная, более сложная задача) — колонка
    # заполняется только вручную/скриптом fix_telegram_contact_check.py.
    # Поле telegram при этом больше НЕ трогаем/не затираем — оно остаётся
    # полезным само по себе (иконка "подписаться на канал" на сайте).
    # Колонка 32 (AF) добавлена 14.08.2026 для email-рассылки при онбординге
    # компаний (см. onboarding_companies.xlsx, extract_email() выше) — как и
    # с telegram_contact, колонку нужно создать один раз (add_email_column.py)
    # ДО первого запуска с новым кодом, иначе email просто уедет в никуда
    # (append_row всё равно допишет по table_range='A1', колонка появится,
    # но БЕЗ заголовка, если её не завести заранее).
    # region раньше был жёстко "Россия" — не подходит для компаний из других
    # стран СНГ (найдено 14.08.2026 на примере ElectroCar, Минск, Беларусь).
    # Каталог задуман как "импорт авто в СНГ", не только Россия, так что
    # region теперь берётся из data, с "Россия" как дефолтом для обратной
    # совместимости (у большинства уже добавленных компаний он не указан).
    row = [
        str(row_num),
        data["name"],
        data.get("rating", "4.5"),
        data.get("reviews", "0"),
        data.get("years", "1"),
        data.get("delivered", "-"),
        data["description"][:200],
        ",".join(data["directions"]),
        ",".join(data["tags"]),
        data.get("telegram", ""),
        data.get("phone", "-"),
        data.get("site", ""),
        "-",
        data.get("region", "Россия"),
        "FALSE",
        data["name"][:3].upper(),
        "av-gray",
        data.get("yandex", ""),
        data.get("inn", ""),
        data.get("google", ""),
        data.get("gis2", ""),
        data.get("instagram", ""),
        data.get("vk", ""),
        data.get("avito", ""),
        data.get("drom", ""),
        data.get("autoru", ""),
        data.get("max", ""),
        data.get("youtube", ""),
        data.get("rutube", ""),
        data.get("whatsapp", ""),
        data.get("telegram_contact", ""),
        data.get("email", ""),
    ]
    # ВАЖНО: без table_range='A1' append_row без явного якоря может "уехать"
    # вправо — Sheets API ищет "таблицу" по всему листу и в редких случаях
    # (09.08.2026, найдено при разборе бага с 52 vs 82 строк) начинает
    # дописывать новые строки не с колонки A, а сразу за самой правой уже
    # занятой ячейкой на листе, со сдвигом, который растёт с каждым новым
    # вызовом (20 -> 44 -> 67 -> 89 -> 112 колонок вправо на реальном
    # прогоне). table_range='A1' явно фиксирует, что "таблица" начинается
    # с колонки A, и это гарантированно лечит сдвиг.
    ws.append_row(row, table_range="A1")
    subs = data.get("subscribers", 0)
    inn_note = " [ИНН найден]" if data.get("inn") else ""
    print(
        "  OK: "
        + data["name"]
        + (" (" + str(subs) + " подписчиков)" if subs > 0 else "")
        + inn_note
    )


BLACKLIST = [
    "avito",
    "drom",
    "auto.ru",
    "drive2",
    "vk.com",
    "vk.ru",
    "youtube",
    "instagram",
    "facebook",
    "tiktok",
    "yandex",
    "google",
    "wikipedia",
    "zhihu",
    "rutube",
    "tgstat",
    "nicegram",
    "telegramchannels",
    # Украинские площадки/сервисы — не имеют отношения к импорту авто в СНГ
    "auto.ria",
    "ria.com",
    # Найдено 09.08.2026 (прогон через cron, без присмотра): "tenchat.ru" —
    # блог-платформа (вроде LinkedIn), агент утащил ЧУЖУЮ СТАТЬЮ про личный
    # опыт с "мошенником" как если бы это была карточка компании (имя
    # получилось "Пробив авто перед покупкой: бесплатный бот для пробива в
    # Telegram" — заголовок статьи, а не название фирмы). "telagon.io" —
    # SEO-зеркало/аналитика Telegram-каналов (аналог tgstat), не сайт самой
    # компании — попал как "сайт" компании, хотя это просто чужой
    # каталог-зеркало чужого канала.
    "tenchat.ru",
    "telagon.io",
    # Найдено 10.08.2026 через dryrun_reverify_sites.py (пользователь
    # прогнал всю базу новым алгоритмом): та же болезнь, что и с
    # tenchat.ru/telagon.io, но с ДРУГИМИ площадками-зеркалами Telegram-
    # каналов — "telegram.menu", "telegram-dialogs.ru", "tele-finder.com",
    # "tgramlink.com" — все они каталогизируют/зеркалят чужие каналы,
    # НЕ являются сайтом самой компании. Из-за этого в таблице оказались
    # карточки "Telegram Dialogs" и "TeleFinder — Каталог Telegram-
    # каналов" — буквально название площадки-каталога вместо названия
    # компании (og:site_name зеркала). "otzovik.com" — отзовик (агент
    # утащил страницу отзыва о телеграм-канале как будто это сайт
    # компании). "autonews.ru" — крупный автомобильный новостной портал,
    # попал в таблицу как "компания" из-за одной конкретной новостной
    # статьи, а не из-за того, что автопортал — компания-импортёр.
    "telegram.menu",
    "telegram-dialogs.ru",
    "tele-finder.com",
    "tgramlink.com",
    "otzovik.com",
    "autonews.ru",
    # Найдено 10.08.2026 (следующий прогон после dryrun-отчёта, ~18 новых
    # строк, пользователь разбирал вручную): та же болезнь ещё раз, с
    # новыми конкретными площадками. "telno.ru" — ещё один каталог
    # telegram-каналов ("Telegram каналы", категория "auto"). "telderi.ru"
    # — маркетплейс продажи готового бизнеса/каналов/ботов (попал листинг
    # "Готовый бизнес: Telegram-бот для проверки истории авто" — это
    # ПРОДАЖА бота, а не сама компания-импортёр). "telegramcat.blog" —
    # блог-каталог про telegram-боты для проверки авто. "ixbt.com" —
    # крупный технический новостной портал (попала обычная новостная
    # статья про параллельный импорт — тот же класс бага, что и с
    # autonews.ru). "vagvin.ru" — известный самостоятельный сервис
    # расшифровки VIN (не импортёр, is_vin_check_service его не поймал —
    # лексикон у vagvin другой: "расшифровка VIN", а не "пробив авто").
    "telno.ru",
    "telderi.ru",
    "telegramcat.blog",
    "ixbt.com",
    "vagvin.ru",
    # Найдено 13.08.2026: та же болезнь (новостной/блог-портал принят за
    # компанию), но источник неожиданный — собственная статья автора на
    # vc.ru (tribuna/3075991) про этот же агрегатор. Агент нашёл её в
    # поиске (там ровно те же ключевые слова — "импорт авто",
    # "агрегатор", "Telegram-бот") и добавил "vc.ru" как компанию с
    # meta-description статьи вместо описания и мусорным телефоном.
    # vc.ru — крупная медиаплатформа, не импортёр, в чёрный список.
    "vc.ru",
    # Найдено 14.08.2026 (ревизия каталога по просьбе пользователя, после
    # добавления вертикали "Таможенные брокеры"): ещё четыре площадки той
    # же болезни, что tgstat/tenchat/telagon/telderi/telno/telepot —
    # каталоги-зеркала Telegram- и Дзен-каналов, попадающие в таблицу как
    # "сайт компании" вместо реального сайта/канала владельца.
    # "tgland.ru" — каталог Telegram-каналов (попал как "TGLand.ru",
    # реальный канал — "Авто Заказ", @auto_zakazz25). "zenstat.ru" —
    # аналитика Дзен-каналов (попал как "Zenstat", реальный канал —
    # "Растаможка Авто Под Ключ"). "freetelegramgroups.com" — каталог
    # Telegram-групп (попал как "Free Telegram Groups", реальный канал —
    # "AUTOCOM"). "telepot.ru" — ещё один каталог Telegram-каналов (попал
    # как "Телеграмм канал Tiger Cars...", реальный канал — "Tiger Cars",
    # @TJ_cars).
    "tgland.ru",
    "zenstat.ru",
    "freetelegramgroups.com",
    "telepot.ru",
    # "aaajapan.com" — аукционная площадка (не компания-импортёр/посредник,
    # см. auction_sites.md — отдельная база на будущее, в каталог
    # импортёров не идёт). "auto-praktis.vercel.app" — блог со статьёй про
    # проверку авто по VIN через Telegram-боты (тот же класс, что и
    # is_vin_check_service, просто другая формулировка — см. фикс лексикона
    # там же).
    "aaajapan.com",
    "auto-praktis.vercel.app",
    # Найдено 17.08.2026 (пользователь: "перепроверь последнее добавление
    # компаний, есть боты, есть статьи"), батч id 82-105 с ежедневного
    # cron-прогона на VPS. Та же болезнь новостных/блог-статей, что и
    # autonews.ru/ixbt.com/vc.ru выше, с новыми конкретными адресами:
    # "journal.sovcombank.ru" — блог банка Совкомбанк, попала статья
    # "как проверить авто перед покупкой" (журнал банка, не импортёр).
    # "zakon.ru" — юридический портал/блог, попала статья на ту же тему
    # ("как пробить авто перед покупкой"). "top-autoimport.ru" — это не
    # сайт компании, а страница-рейтинг "лучшие компании по привозу авто
    # из Европы" (/ratings/...) — сторонний рейтинг-агрегатор, не сама
    # компания-импортёр.
    "journal.sovcombank.ru",
    "zakon.ru",
    "top-autoimport.ru",
    # Найдено 25.08.2026 (пользователь: "по сайту добавились карточки, но
    # нужно чистить, сам проверь что удалить") — батч со 119 до 133 карточек
    # (см. cleanup_added_2026_08_25.py, T-79 в TASKS.md). "telega.in" —
    # маркетплейс покупки рекламы в чужих Telegram-каналах, попала страница
    # "закажите рекламу в этом канале", не сама компания. "tgramsearch.com"
    # — ещё один каталог-зеркало Telegram-каналов (та же болезнь, что
    # tgstat/tenchat/telagon/telderi/telno/tgland/zenstat/freetelegram-
    # groups/telepot выше) — попала карточка с именем "Илья" (взято из
    # контакта в описании канала, а не название бизнеса). "getcar.ru" —
    # общая площадка объявлений об автомобилях (любые марки/пробеги, свой
    # AI-контент) — не компания-импортёр под заказ, а маркетплейс, того же
    # рода, что avito/drom/auto.ru выше. "gar7.ru" ("Гараж 007") — авто-
    # журнал (тюнинг, шины, двигатель), попала статья про параллельный
    # импорт, сам портал не компания — тот же класс, что autonews.ru/
    # ixbt.com/vc.ru. "rox-aaron.ru" ("Аарон Авто") и позже, 26.08.2026,
    # "avtogermes.ru" ("Avtogermes") — официальные дилеры конкретных
    # брендов (машины в наличии, автокредит, трейд-ин) — это обычные
    # автосалоны, НЕ бизнес "импорт/пригон под заказ", который каталог
    # собирает; лексикон у них другой ("официальный дилер", "в наличии"),
    # эвристики продающих фраз (SELLING_PHRASES) их не отсеивают. "iphones.ru"
    # — сайт про гаджеты/смартфоны, попала статья "как проверить историю
    # автомобиля перед покупкой" (та же болезнь, что journal.sovcombank.ru/
    # zakon.ru — блог общей тематики, ловится на одну авто-статью). Найден
    # ДВАЖДЫ (25.08 и повторно 26.08 на следующем cron-прогоне) — то есть
    # без блэклиста агент реально переоткрывает одну и ту же мусорную
    # страницу заново при каждом запуске. "tadviser.ru" — отраслевая вики-
    # статья со статистикой рынка импорта (не компания, а аналитика).
    "telega.in",
    "tgramsearch.com",
    "getcar.ru",
    "gar7.ru",
    "rox-aaron.ru",
    "avtogermes.ru",
    "iphones.ru",
    "tadviser.ru",
    # Найдено 27.08.2026 (пользователь прогнал ручную сверку по ВСЕМ 134
    # карточкам каталога, не только по новым): "dzen.ru" — попала статья
    # "Основные способы проверки реального пробега авто с аукциона"
    # (карточка называлась буквально "Dzen" — имя платформы вместо
    # компании), тот же класс, что vc.ru/ixbt.com/autonews.ru выше — сама
    # платформа не компания-импортёр, просто там иногда публикуют статьи
    # про авто. "av.by" добавлен НЕ целиком (это крупный настоящий
    # каталог объявлений в Беларуси, весь домен блокировать нельзя) — см.
    # вместо этого точечное удаление конкретной страницы av.by/vin в
    # fix_manual_data_2026_08_27_batch2.py: это инструмент проверки VIN,
    # а не компания, но остальной av.by трогать не за что.
    "dzen.ru",
    "liautoofficial.ru",  # официальный сайт бренда Lixiang/Li Auto — не "импорт под заказ"
    # Найдено 27.08.2026 (пользователь продолжил ручную сверку живых карточек
    # на сайте, отдельными сообщениями): "rusdtp.ru" — автомобильный
    # новостной портал (попала статья про ужесточение ввоза Минпромторгом),
    # тот же класс, что autonews.ru/ixbt.com/vc.ru/dzen.ru выше — портал не
    # компания-импортёр. "autoimport.trade" — несмотря на говорящее название
    # домена, это B2B-поставщик расходников/электроники/автохимии для
    # автосалонов (укрывные материалы, автохимия) с офисами в Москве и
    # Казани — НЕ занимается импортом/пригоном автомобилей под заказ,
    # проверено вручную по /produkt.
    "rusdtp.ru",
    "autoimport.trade",
]

# Продающие фразы ниши — собраны 09.08.2026 по реальным сайтам/TG-каналам
# компаний-импортёров авто (WESTMOTORS, Япония Транзит, KoreaBlizko, ASIA
# EXPRESS AUTO, LimeeAuto, СБ Карго, Саха Джапан и др.): так они сами себя
# продают. Старые 5+5 запросов ловили компании только по направлению
# ("авто из Кореи", "пригон авто") — а многие небольшие каналы и сайты в
# заголовке/описании упирают именно на выгоду, а не на направление
# ("без переплат", "напрямую без посредников", "растаможка под ключ",
# "полное сопровождение сделки", "с гарантией", "проверка перед покупкой").
# Поиск по этим формулировкам должен находить компании, которые обычные
# направленческие запросы пропускают.
SELLING_PHRASES = [
    "авто под заказ без посредников",
    "авто напрямую без переплат",
    "растаможка авто под ключ",
    "полное сопровождение сделки авто",
    "проверка авто перед покупкой с аукциона",
    "авто с гарантией доставка под ключ",
    # Добавлено 12.08.2026 (кейс Faker Autogroup, fakerautogroup.ru): все
    # фразы выше заточены под брокеров/посредников ("под заказ без
    # посредников" и т.п.) — а есть отдельный вид игрока: гибридный
    # автосалон (шоурум + свой автопарк), который ПОПУТНО возит авто под
    # заказ из-за границы (Европа/Корея/США и т.п.), сам себя описывает
    # через "автосалон"/trade-in/кредит-лизинг, а не через "импорт"/
    # "пригон". Старые запросы такой формат пропускали.
    "автосалон авто под заказ из Европы Кореи США",
]


def run_agent():
    print("Запускаю агента v2...")
    try:
        ws = connect_sheets()
        print("Подключено к Google Sheets!")
    except Exception as e:
        print("Ошибка: " + str(e))
        return
    existing = get_existing(ws)
    # 18.08.2026: раньше next_id брался как len(ws.get_all_values()) — то есть
    # количество строк в таблице. Это ложное допущение "id всегда совпадает с
    # номером строки", которое ломается каждый раз, когда мы удаляем дубли
    # или переномеровываем строки (fix_dedupe_company_ids.py и подобные) —
    # количество строк после этого становится МЕНЬШЕ реального максимума id,
    # и агент начинает штамповать новые id, которые уже заняты (найдено
    # 18.08.2026: id 100,102,106,107,108,109,110 совпали со старыми
    # компаниями). Правильный next_id — максимум РЕАЛЬНО существующих id в
    # колонке + 1, не зависит от того, сколько строк физически в таблице.
    existing_ids = []
    for row in ws.get_all_values()[1:]:
        if row and row[0].strip():
            try:
                existing_ids.append(int(float(row[0].strip())))
            except ValueError:
                pass
    next_id = (max(existing_ids) + 1) if existing_ids else 1
    found = 0
    skipped = 0

    print("\nШаг 1: tgstat.ru...")
    tg_channels = set()
    # Направленческие запросы + продающие фразы (SELLING_PHRASES) — каналы
    # часто называют/описывают себя через выгоду ("без посредников",
    # "растаможка под ключ"), а не через направление, обычные запросы их
    # пропускают.
    for q in [
        "импорт авто",
        "авто из Кореи",
        "авто из Китая",
        "пригон авто",
        "авто под заказ",
    ] + SELLING_PHRASES:
        channels = search_tgstat(q)
        tg_channels.update(channels)
        print("  " + q + ": " + str(len(channels)) + " каналов")
        time.sleep(2)

    for username in tg_channels:
        if username.lower() in existing:
            skipped += 1
            continue
        info = parse_tgstat_channel(username)
        if not info:
            skipped += 1
            continue
        text = info["description"]
        has_auto = any(
            w in text.lower()
            for w in ["авто", "машин", "импорт", "корея", "китай", "япония", "пригон"]
        )
        if (
            not has_auto
            or mentions_ukraine(text)
            or is_vin_check_service(text)
            or is_customs_broker(text)
        ):
            skipped += 1
            continue
        years = extract_years_experience(text)
        phone = extract_phone(text)
        email = extract_email(text)
        # Настоящее название канала (не @username), если tgstat его отдал —
        # иначе fallback на username, отформатированный чуть приличнее сырого
        # нижнего регистра с подчёркиваниями.
        name = info.get("title") or username.replace("_", " ").title()
        if name.lower() in existing:
            skipped += 1
            continue
        yandex, google, gis2, maps_verified = find_map_links(name, phone)
        insta, vk, social_verified = find_social_links(name, text, phone)
        avito, drom, autoru, market_verified = find_marketplace_links(name, phone)
        extra = extract_extra_contacts_from_text(text)
        maxm, youtube, rutube, whatsapp = (
            extra["max"],
            extra["youtube"],
            extra["rutube"],
            extra["whatsapp"],
        )
        # Карточки на площадках (если нашлись и подтвердились) сами по себе
        # часто содержат сайт/соцсети/мессенджеры компании — дозаполняем то,
        # что выше не нашли другими способами. Не только 2ГИС — по просьбе
        # пользователя пробуем и Яндекс.Карты (см. backfill_from_sources).
        site = ""
        if maps_verified and (gis2 or yandex):
            filled = backfill_from_sources(
                [("2gis", gis2), ("yandex", yandex)],
                {
                    "site": site,
                    "telegram": username,
                    "vk": vk,
                    "instagram": insta,
                    "avito": avito,
                    "drom": drom,
                    "autoru": autoru,
                    "max": maxm,
                    "youtube": youtube,
                    "rutube": rutube,
                    "whatsapp": whatsapp,
                },
            )
            site = filled["site"]
            vk = vk or filled["vk"]
            insta = insta or filled["instagram"]
            avito = avito or filled["avito"]
            drom = drom or filled["drom"]
            autoru = autoru or filled["autoru"]
            maxm = maxm or filled["max"]
            youtube = youtube or filled["youtube"]
            rutube = rutube or filled["rutube"]
            whatsapp = whatsapp or filled["whatsapp"]
        # Раньше публиковали только при подтверждении хотя бы на одной
        # независимой площадке. Теперь добавляем и при единственном
        # источнике (сам тг-канал) — но название стараемся взять максимально
        # верное (см. title выше), а не сырой ник, и печатаем в лог, если
        # подтверждения нигде не нашлось — для ручного контроля.
        if not (maps_verified or social_verified or market_verified):
            print(f"    ⚠️ {name}: подтвердилось только в Telegram, добавляю как есть")
        # См. ту же проверку в DDG-ветке ниже (найдено 14.08.2026,
        # ТамСямAUTO) — здесь site обычно ещё не найден на этом этапе,
        # поэтому tgcontact не вычисляется, но принцип тот же: если
        # WhatsApp/VK тоже нет, а показать нечего кроме Instagram, кнопка
        # "Написать" на сайте ненадёжна.
        if insta and not whatsapp and not vk:
            print(
                f'    ⚠️ {name}: единственный контакт для кнопки "Написать" — Instagram '
                f"(ненадёжно, требует входа в приложение), стоит доискать WhatsApp/личный TG вручную"
            )
        next_id += 1
        add_company(
            ws,
            {
                "name": name,
                "description": clean_snippet_prefix(text) or "Telegram канал @" + username,
                "directions": get_directions(text),
                "tags": get_tags(text),
                "telegram": username,
                "phone": phone,
                "site": site,
                "subscribers": info["subscribers"],
                "years": str(years) if years else "1",
                "yandex": yandex,
                "google": google,
                "gis2": gis2,
                "instagram": insta,
                "vk": vk,
                "avito": avito,
                "drom": drom,
                "autoru": autoru,
                "max": maxm,
                "youtube": youtube,
                "rutube": rutube,
                "whatsapp": whatsapp,
                "email": email,
            },
            next_id,
        )
        existing.add(name.lower())
        existing.add(username.lower())
        found += 1
        time.sleep(1)

    print("\nШаг 2: DuckDuckGo...")
    # Те же продающие фразы, что и в шаге 1 (SELLING_PHRASES) — здесь с
    # добавкой "Telegram канал"/"сайт", как и у остальных DDG-запросов,
    # чтобы вытягивать именно карточки компаний, а не общие статьи.
    ddg_queries = [
        "импорт авто Telegram канал Россия",
        "авто из Кореи Китая под заказ Telegram",
        "пригон авто аукцион Япония сайт",
        "авто США ОАЭ Европа под заказ",
        "импорт авто официальный сайт Россия",
        # 24.08.2026 (диагностика diag_personal_brand.py, по вопросу
        # пользователя про "Лиса рулит"): проверено вживую на VPS — эта
        # формулировка даёт низкий шум и реальные новые сайты компаний
        # (gtk-auto.ru, favorit-motors.ru, car-spot.ru, nezavisimost.ru
        # среди прочего), которых раньше не было ни в одном из запросов
        # выше. НЕ про блогеров конкретно — просто фраза, которой не
        # хватало в списке.
        "автосалон параллельный импорт отзывы",
    ]
    ddg_queries += [p + " Telegram канал" for p in SELLING_PHRASES]
    for query in ddg_queries:
        print("  " + query)
        for item in search_ddgs(query, 5):
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            link = item.get("link", "")
            text = title + " " + snippet
            sl = link.lower()
            nl = title.lower()
            if any(b in sl or b in nl for b in BLACKLIST):
                skipped += 1
                continue
            has_auto = any(
                w in text.lower()
                for w in [
                    "авто",
                    "импорт",
                    "машин",
                    "автомобил",
                    "пригон",
                    "корея",
                    "китай",
                    "япония",
                ]
            )
            tg = extract_telegram(text)
            phone = extract_phone(text)
            if (
                not has_auto
                or mentions_ukraine(text)
                or is_vin_check_service(text)
                or is_customs_broker(text)
                or (not tg and phone == "-" and not link.startswith("http"))
            ):
                skipped += 1
                continue
            domain = re.search(r"https?://(?:www\.)?([^/]+)", link)
            domain_name = (
                domain.group(1).replace(".ru", "").replace(".com", "").title() if domain else ""
            )
            dom = base_domain(link)
            # Дедуп по домену, а не только по имени/точной ссылке — без
            # этого одна и та же компания под разными подстраницами сайта
            # (japantransit.ru vs japantransit.ru/japan/auctions) в разных
            # поисковых запросах добавлялась дважды под двумя разными
            # (оба неверными) названиями. base_domain (не domain_of) —
            # чтобы городской поддомен уже известного сайта (spb.westmotors.ru
            # при уже существующем westmotors.ru) тоже ловился как дубль,
            # см. баг 10.08.2026 у Westmotors/Spb.Westmotors. Проверяем ДО
            # похода на сайт, чтобы не тратить запрос впустую.
            if dom and dom in existing:
                skipped += 1
                continue
            title_name = clean_name_from_title(title)
            if domain and domain.group(1).lower() in ("t.me", "telegram.me"):
                # Ссылка на Telegram-канал/бота — домен "T.Me" бесполезен
                # как имя компании. Заголовок из DDG для t.me-ссылок тоже
                # часто бесполезен: это сырой <title> превью-страницы вида
                # "Telegram: View @auto_import_cars_ru", а не og:title с
                # настоящим названием канала (баг, из-за которого в каталог
                # однажды попала компания с именно таким именем). Поэтому
                # для t.me НЕ доверяем clean_name_from_title(title) вообще —
                # идём напрямую на превью-страницу канала за og:title, как
                # уже делаем в fetch_telegram_preview()/add_specific_channel.py.
                # 13.08.2026: для ссылки "https://t.me/s" регулярка ловила
                # "s" как будто это юзернейм канала — но "/s/" это служебный
                # путь Telegram (server-side превью, обычно t.me/s/<канал>),
                # не название. В каталог попала "Telegram – a new era of
                # messaging" (заголовок общей страницы t.me, а не канала).
                # Настоящие юзернеймы Telegram — от 5 символов, фильтруем
                # короткие/служебные совпадения ("s", "k", "iv" и т.п.).
                handle_m = re.search(r"(?:t|telegram)\.me/([A-Za-z0-9_]+)", link, re.IGNORECASE)
                if handle_m and not tg and len(handle_m.group(1)) >= 5:
                    tg = handle_m.group(1)
                if not tg:
                    # Ни @упоминания в тексте, ни валидного юзернейма из
                    # ссылки — карточку без способа связаться через Telegram
                    # добавлять бессмысленно (и рискованно, см. случай "s").
                    skipped += 1
                    continue
                if tg.lower().endswith("bot"):
                    # Найдено 17.08.2026: если сама выдача поиска указывает
                    # напрямую на t.me/<handle>_bot, это сам БОТ, а не канал
                    # компании — "auto_import_sale_bot" попал в каталог как
                    # компания с именем=хэндл бота. extract_site_tg_contact()
                    # (см. выше) уже умеет отличать бота как ЛИЧНЫЙ КОНТАКТ
                    # компании на её сайте — но здесь другая ветка: сам бот
                    # найден в поиске как будто он и есть компания. Ботов не
                    # компания-импортёр, пропускаем.
                    skipped += 1
                    continue
                preview = fetch_telegram_preview(tg) if tg else None
                name = (
                    (preview["title"] if preview and preview.get("title") else "")
                    or tg
                    or domain_name
                )
                site_text = ""
            elif domain and domain.group(1).lower() in ("vk.com", "vk.ru", "instagram.com"):
                # 14.08.2026, по просьбе пользователя: если у кандидата нет
                # собственного сайта и единственная найденная ссылка — его
                # страница VK/Instagram, берём имя оттуда (og:title), а не
                # с домена площадки ("Vk"/"Instagram" — бесполезно как имя,
                # та же болезнь, что раньше была с "T.Me"). Ссылки на
                # поиск/стену/пост (не сам профиль) отсекаем — как источник
                # имени они не годятся, is_real_profile_url это уже умеет
                # отличать (см. её докстринг).
                if not is_real_profile_url(link.lower()):
                    skipped += 1
                    continue
                soc_title = fetch_url_og_title(link)
                if not soc_title or is_probably_tagline(soc_title):
                    skipped += 1
                    continue
                name = soc_title
                site_text = ""
            else:
                # Идём на сайт ДО выбора имени (а не только потом за ИНН) —
                # у сайта обычно есть og:site_name/apple-mobile-web-app-title
                # с настоящим брендом, который надёжнее сырого SEO-заголовка
                # из выдачи ("Купить новое авто с доставкой" вместо
                # "GazTormoz", проверено вручную 09.08.2026 на gaztormoz.ru
                # и tokidoki.su). Приоритет: бренд с сайта > заголовок выдачи
                # > домен как последний fallback.
                site_text = fetch_site_text(link) if link.startswith("http") else ""
                if site_text and mentions_ukraine(site_text):
                    skipped += 1
                    continue
                if looks_like_bot_wall(site_text):
                    print(
                        f"    🚧 {name or domain_name}: сайт {link} защищён антиботом/капчей — "
                        f"автоматически не читается, нужен РУЧНОЙ ввод названия/соцсетей/ИНН/телефона"
                    )
                    site_text = ""
                brand_name = extract_brand_from_site(site_text)
                name = brand_name or title_name or domain_name or title[:30]
                if brand_name and brand_name != title_name:
                    print(
                        f"    имя со страницы сайта (og:site_name): '{brand_name}' (в выдаче было: '{title[:50]}')"
                    )
                elif not title_name and not brand_name:
                    print(f"    ⚠️ имя взято из домена ({name}) — стоит проверить вручную")
                # Сверка имени по независимым источникам (телеграм/VK/
                # Instagram компании) — см. verify_company_name, 14.08.2026.
                insta_check, vk_check = (
                    extract_social_from_text(site_text) if site_text else ("", "")
                )
                name = verify_company_name(name, tg=tg, vk=vk_check, instagram=insta_check)
                # Если с главной не хватает ИНН и телефона — пробуем
                # догрузить "Контакты"/"О нас" (см. find_subpage_urls,
                # 10.08.2026: auto-asia25.ru — телефон/ИНН/правильный
                # telegram были только на /contacts, агент их не видел).
                # Всё, что ищется ниже из site_text (ИНН, телефон, соцсети,
                # маркетплейсы, прямые ссылки на карты/2ГИС), автоматически
                # подхватит и добавленный текст подстраницы.
                if site_text and not (extract_inn(site_text) and extract_phone(site_text) != "-"):
                    extra_site_text = fetch_extra_site_text(site_text, link)
                    if extra_site_text:
                        print(
                            f"    догрузил доп. страницы (контакты/о нас): +{len(extra_site_text)} симв."
                        )
                        site_text += extra_site_text
            if name.lower() in existing or (link and link.lower() in existing):
                skipped += 1
                continue
            # ИНН — из уже загруженного текста сайта (см. выше), запрос
            # повторно не делаем.
            inn = extract_inn(site_text) if site_text else ""
            # Телефон из сниппета выдачи часто пустой ("-") — сайт компании
            # (включая догруженные "Контакты"/"О нас", см. выше) надёжнее.
            if phone == "-" and site_text:
                site_phone = extract_phone(site_text)
                if site_phone != "-":
                    phone = site_phone
            # Стаж ("N лет на рынке") и год регистрации по ЕГРЮЛ — РАЗНЫЕ
            # вещи (см. кейс Altais-Cars: сайт заявляет "с 1998", а
            # юрлицо переоформлено в 2025 — это два независимых факта,
            # update_site.py показывает оба честно). Раньше при найденном
            # ИНН стаж вообще не пытались достать из текста, оставляя
            # безопасный дефолт "1" — из-за этого на сайте появлялись
            # нелепые расхождения вида "1 год на рынке" рядом с зелёным
            # бейджем "в ЕГРЮЛ с 2024 года" (баг замечен 09.08.2026 на
            # China Trade). Теперь пробуем извлечь стаж из текста ВСЕГДА,
            # независимо от того, нашёлся ИНН или нет — не нашли ничего
            # в тексте, update_site.py на этапе рендера сам подставит
            # возраст по ЕГРЮЛ как более честный fallback, чем "1".
            years = extract_years_experience(text + " " + site_text)
            # Email — из сниппета выдачи и уже загруженного текста сайта
            # (включая догруженные "Контакты"/"О нас"), запрос повторно не
            # делаем. Добавлено 14.08.2026 для email-рассылки при онбординге.
            email = extract_email(text + " " + site_text)
            yandex, google, gis2, maps_verified = find_map_links(name, phone)
            insta, vk, social_verified = find_social_links(name, text + " " + site_text, phone)
            avito, drom, autoru, market_verified = find_marketplace_links(name, phone)
            extra = extract_extra_contacts_from_text(text + " " + site_text)
            maxm, youtube, rutube, whatsapp = (
                extra["max"],
                extra["youtube"],
                extra["rutube"],
                extra["whatsapp"],
            )
            # Баг найден 10.08.2026: link тут может оказаться ссылкой на
            # t.me/telegram.me (DDG иногда отдаёт превью-страницу канала
            # как "сайт" в выдаче, отдельно от ветки с t.me в начале блока
            # — например когда домен НЕ t.me/telegram.me, но сам текст
            # содержит telegram-ссылку, которую DDG вернул как основной
            # link). Без проверки такая ссылка попадала в site — поле
            # "сайт" не должно дублировать telegram (у telegram уже есть
            # своя колонка). Нашли на реальном примере: "Прим Автодилер",
            # site оказался telegram.me/prim_autodealer.
            link_domain = domain_of(link)
            site = (
                link
                if link.startswith("http") and link_domain not in ("t.me", "telegram.me")
                else ""
            )
            # Собственный сайт компании (уже загружен как site_text выше) —
            # тоже источник для маркетплейсов, если ссылки на них есть в
            # футере сайта (переиспользуем уже загруженный текст, не грузим
            # сайт повторно).
            # Личный/бот Telegram-контакт (не канал) — ищем прямо на сайте
            # компании эвристикой extract_site_tg_contact (см. выше, найдено
            # 14.08.2026 на реальных примерах). Раньше эта колонка (AE)
            # заполнялась ТОЛЬКО отдельным скриптом fix_telegram_contact_check.py
            # уже после добавления компании — теперь агент пробует найти её
            # сразу при первом прогоне, скрипт остаётся как дозаполнение для
            # случаев, которые эвристика на сайте не поймала.
            telegram_contact = extract_site_tg_contact(site_text) if site_text else ""
            if site_text:
                site_direct = extract_direct_contacts(site_text)
                avito = avito or site_direct.get("avito", "")
                drom = drom or site_direct.get("drom", "")
                autoru = autoru or site_direct.get("autoru", "")
                whatsapp = whatsapp or site_direct.get("whatsapp", "")
            # Карточки на площадках (2ГИС, Яндекс.Карты — если нашлись и
            # подтвердились) сами по себе часто содержат сайт/соцсети/
            # мессенджеры компании — дозаполняем то, что выше не нашли
            # другими способами. Не только 2ГИС — по просьбе пользователя
            # пробуем и Яндекс.Карты (добавлено 09.08.2026, после того как
            # пользователь нашёл сайт LikeAvto именно через карточку 2ГИС и
            # попросил не ограничиваться одной площадкой).
            if maps_verified and (gis2 or yandex):
                filled = backfill_from_sources(
                    [("2gis", gis2), ("yandex", yandex)],
                    {
                        "site": site,
                        "telegram": tg,
                        "vk": vk,
                        "instagram": insta,
                        "avito": avito,
                        "drom": drom,
                        "autoru": autoru,
                        "max": maxm,
                        "youtube": youtube,
                        "rutube": rutube,
                        "whatsapp": whatsapp,
                    },
                )
                site = site or filled["site"]
                tg = tg or filled["telegram"]
                vk = vk or filled["vk"]
                insta = insta or filled["instagram"]
                avito = avito or filled["avito"]
                drom = drom or filled["drom"]
                autoru = autoru or filled["autoru"]
                maxm = maxm or filled["max"]
                youtube = youtube or filled["youtube"]
                rutube = rutube or filled["rutube"]
                whatsapp = whatsapp or filled["whatsapp"]
            # Добавляем и при подтверждении только из одного источника —
            # но название уже взято максимально верно (title_name из
            # заголовка выдачи, а не домен, см. clean_name_from_title выше).
            # Печатаем в лог, если независимого подтверждения нигде не нашлось
            # — для ручного контроля, не блокирует публикацию.
            if not (inn or maps_verified or social_verified or market_verified):
                print(
                    f"    ⚠️ {name}: подтвердилось только по исходному источнику, добавляю как есть"
                )
            # Найдено 14.08.2026 (живой отчёт пользователя про ТамСямAUTO):
            # если единственный контакт для кнопки "Написать" на сайте — это
            # Instagram (telegram_contact/whatsapp/vk все пустые), кнопка
            # ненадёжна — Instagram не даёт написать без входа в приложение,
            # а на живом сайте это уже приводило к "ссылка не работает".
            # Печатаем предупреждение сразу при добавлении, а не только
            # постфактум при ручной проверке — та же логика применима к
            # будущим направлениям агента, не только авто.
            if insta and not (telegram_contact or whatsapp or vk):
                print(
                    f'    ⚠️ {name}: единственный контакт для кнопки "Написать" — Instagram '
                    f"(ненадёжно, требует входа в приложение), стоит доискать WhatsApp/личный TG вручную"
                )
            next_id += 1
            add_company(
                ws,
                {
                    "name": name,
                    "description": clean_snippet_prefix(snippet)[:200],
                    "directions": get_directions(text),
                    "tags": get_tags(text),
                    "telegram": tg,
                    "phone": phone,
                    "site": site,
                    "inn": inn,
                    "years": str(years) if years else "1",
                    "yandex": yandex,
                    "google": google,
                    "gis2": gis2,
                    "instagram": insta,
                    "vk": vk,
                    "avito": avito,
                    "drom": drom,
                    "autoru": autoru,
                    "max": maxm,
                    "youtube": youtube,
                    "rutube": rutube,
                    "whatsapp": whatsapp,
                    "email": email,
                    "telegram_contact": telegram_contact,
                },
                next_id,
            )
            existing.add(name.lower())
            if link:
                existing.add(link.lower())
            if dom:
                existing.add(dom)
            found += 1
            time.sleep(0.5)
        time.sleep(3)

    print("\nГотово! Добавлено: " + str(found) + ", пропущено: " + str(skipped))
    print("Запусти python3 update_site.py чтобы обновить сайт!")


if __name__ == "__main__":
    run_agent()
