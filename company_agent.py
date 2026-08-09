import requests
import json
import re
import time
import datetime
import gspread
from google.oauth2.service_account import Credentials
from ddgs import DDGS

config = {}
with open("agent_config.env") as f:
    for line in f:
        if "=" in line:
            k, v = line.strip().split("=", 1)
            config[k] = v

SHEET_ID = config["SHEET_ID"]

def connect_sheets():
    scopes = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).sheet1

def check_site(url):
    try:
        r = requests.get(url, timeout=5, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
        return r.status_code == 200
    except:
        return False

def extract_phone(text):
    m = re.search(r"[78][\s\-\(]?\d{3}[\s\-\(]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}", text)
    return m.group(0) if m else "-"

def extract_telegram(text):
    m = re.search(r"@([A-Za-z0-9_]{3,32})", text)
    return m.group(1) if m else ""

def clean_name_from_title(title):
    """
    Заголовки в поисковой выдаче почти всегда содержат настоящее название
    компании первым сегментом: "CarsKorea — авто из Южной Кореи...",
    "Карсплюс Авто - честный автосалон...". Берём текст до первого
    разделителя-тире/палки — это и есть имя. Если разделителя нет или
    сегмент подозрительно короткий — не годится, пусть вызывающий код
    решает, что делать (обычно — fallback на домен).
    """
    if not title:
        return ""
    for sep in [" — ", " – ", " | ", " - ", " · "]:
        if sep in title:
            candidate = title.split(sep)[0].strip()
            if len(candidate) >= 2:
                return candidate
    return title.strip()

def extract_inn(text):
    # Ищем ИНН только рядом со словом "ИНН" — просто 10/12-значное число
    # в тексте слишком часто оказывается номером телефона или ОГРН.
    m = re.search(r"ИНН[:\s№]{0,5}(\d{10}|\d{12})", text, re.IGNORECASE)
    return m.group(1) if m else ""

def fetch_site_text(url):
    # Отдельно от check_site: тут нужен именно текст страницы, чтобы
    # поискать в нём ИНН/реквизиты компании. Если не получилось — не страшно,
    # просто не найдём ИНН для этой компании сейчас.
    try:
        r = requests.get(url, timeout=6, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    return ""

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
    m = re.search(r'<meta property="og:site_name" content="([^"]+)"', html)
    if m and m.group(1).strip():
        return m.group(1).strip()
    m = re.search(r'<meta name="apple-mobile-web-app-title" content="([^"]+)"', html)
    if m and m.group(1).strip():
        return m.group(1).strip()
    return ""

def domain_of(url):
    """Домен без www/схемы/пути — для сравнения "это тот же сайт?" вместо
    точного совпадения полного URL (иначе japantransit.ru и
    japantransit.ru/japan/auctions считаются разными компаниями)."""
    m = re.search(r"https?://(?:www\.)?([^/]+)", url or "")
    return m.group(1).lower() if m else ""

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

def _name_key(name):
    # Первое "слово" названия (до пробела/точки) — по нему ищем совпадение
    # в чужих сниппетах. "CarsKorea" ищем как "carskorea", длинное название
    # с пунктуацией целиком слишком легко не совпадает буквально.
    if not name:
        return ""
    return re.split(r"[\s.]+", name.lower())[0]

# VK: служебные разделы сайта (не группы/профили конкретной компании).
# Найдено 09.08.2026: "vk.com/js" (заглушка "включите JavaScript",
# отдаётся VK ботам без нормальных заголовков — по ошибке "подтвердилась"
# сразу для 4 РАЗНЫХ компаний, т.к. это общая страница, а не чья-то
# карточка), "vk.com/video"/"vk.com/clips" (общий раздел видео сайта, а не
# профиль компании).
VK_RESERVED_PATHS = {"js","video","videos","wall","photo","photos","clips","away",
    "login","join","search","catalog","market","games","apps","about","help",
    "dev","faq","id","feed","audio","music","topic","board"}

# Instagram: системные файлы/служебные разделы, не профиль компании.
# Найдено 09.08.2026: "instagram.com/favicon.ico" (иконка сайта!)
# "подтвердилась" как аккаунт компании.
INSTAGRAM_RESERVED_PATHS = {"favicon.ico","p","explore","accounts","reel","reels",
    "stories","tv","about","legal","developer","robots.txt"}

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
        m = re.search(r"vk\.(?:com|ru)/([a-z0-9_.\-]+)", link_lower)
        if m:
            first_seg = m.group(1).split("?")[0].rstrip("/")
            base = first_seg.split("-")[0]
            if base in VK_RESERVED_PATHS:
                return False
    if "instagram.com" in link_lower:
        m = re.search(r"instagram\.com/([a-z0-9_.\-]+)", link_lower)
        if m:
            seg = m.group(1).split("?")[0].rstrip("/")
            if seg in INSTAGRAM_RESERVED_PATHS:
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
        if not any(d in link_lower for d in domain_filters):
            continue
        if not is_real_profile_url(link_lower):
            continue
        snippet = ((r.get("title") or "") + " " + (r.get("snippet") or "")).lower()
        snippet_match = bool(
            (name_key and name_key in snippet) or
            (phone_digits and phone_digits in re.sub(r"\D", "", snippet))
        )
        if not snippet_match:
            continue
        page_text = fetch_page_signal_text(link)
        if not page_text:
            continue
        page_match = bool(
            (name_key and name_key in page_text) or
            (phone_digits and phone_digits in re.sub(r"\D", "", page_text))
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
    yandex, yv = find_platform_link(f"{name} отзывы", ["yandex.ru/maps", "yandex.com/maps"], key, pd)
    time.sleep(1)
    google, gv = find_platform_link(f"{name} отзывы", ["google.com/maps", "maps.app.goo.gl", "goo.gl/maps"], key, pd)
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

def mentions_ukraine(text):
    # Ловит "Украина/Украину/Украины/украинский" и т.п. — любые формы
    # с корнем "укра". Сайт нацелен на СНГ (Россия, Казахстан, Беларусь...),
    # компании, которые возят машины в Украину, сюда не нужны.
    return bool(re.search(r"укра", text, re.IGNORECASE))

def get_directions(text):
    t = text.lower()
    dm = {"Китай":["китай","china","byd","haval","geely","chery","далянь"],"Корея":["корея","korea","kia","hyundai","genesis"],"Япония":["япония","japan","toyota","lexus","honda","nissan","mazda"],"США":["сша","usa","america","tesla","ford","cadillac"],"ОАЭ":["оаэ","uae","dubai","эмираты"],"Европа":["европа","europe","bmw","mercedes","audi","volkswagen"],"Канада":["канада","canada"],"Грузия":["грузия","georgia"],"Армения":["армения","armenia"]}
    dirs = [d for d,kws in dm.items() if any(k in t for k in kws)]
    return dirs if dirs else ["Не указано"]

def get_tags(text):
    t = text.lower()
    tags = []
    if "под ключ" in t: tags.append("Под ключ")
    if "растаможк" in t: tags.append("Растаможка")
    if "аукцион" in t: tags.append("Аукционы")
    if "параллельн" in t: tags.append("Параллельный импорт")
    if "наличи" in t: tags.append("В наличии")
    # Ещё один частый продающий тезис в нише (см. SELLING_PHRASES) — "без
    # посредников"/"напрямую" — раньше никак не попадал в теги.
    if "без посредник" in t or "напрямую" in t: tags.append("Без посредников")
    return tags if tags else ["Импорт авто"]

def search_tgstat(query):
    url = "https://tgstat.ru/channels/search?q=" + requests.utils.quote(query) + "&country=ru"
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200: return []
        return list(set(re.findall(r"@([A-Za-z0-9_]{3,32})", r.text)))[:10]
    except:
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
        r = requests.get("https://tgstat.ru/channel/@" + username, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200: return None
        html = r.text
        subs_m = re.search(r"(\d[\d\s]+)\s*подписчик", html)
        subs = int(subs_m.group(1).replace(" ","")) if subs_m else 0
        desc_m = re.search(r"peer-description[^>]*>(.*?)</div>", html, re.DOTALL)
        desc = re.sub(r"<[^>]+>","",desc_m.group(1)).strip()[:200] if desc_m else ""
        title = _extract_tgstat_title(html)
        return {"subscribers": subs, "description": desc, "title": title}
    except:
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
        r = requests.get(f"https://t.me/{username}", timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return None
        html = r.text
        title_m = re.search(r'<meta property="og:title" content="([^"]*)"', html)
        desc_m = re.search(r'<meta property="og:description" content="([^"]*)"', html)
        subs_m = re.search(r'([\d\s]+)\s*subscribers', html)
        title = title_m.group(1).strip() if title_m else ""
        desc = desc_m.group(1).strip() if desc_m else ""
        subs = int(subs_m.group(1).replace(" ", "")) if subs_m else 0
        if not title and not desc:
            return None
        return {"subscribers": subs, "description": desc, "title": clean_channel_title(title)}
    except Exception:
        return None

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
                results.append({"title":r.get("title",""),"snippet":r.get("body",""),"link":r.get("href","")})
        return results
    except Exception as e:
        print("Ошибка поиска: " + str(e))
        return []

def get_existing(ws):
    try:
        data = ws.get_all_values()
        ex = set()
        for row in data[1:]:
            if len(row) > 1 and row[1]: ex.add(row[1].lower().strip())
            if len(row) > 9 and row[9]: ex.add(row[9].lower().strip())
            if len(row) > 11 and row[11]: ex.add(row[11].lower().strip())
            # Домен сайта отдельно от полного URL — иначе одна и та же
            # компания под разными страницами (japantransit.ru vs
            # japantransit.ru/japan/auctions) считается двумя разными
            # компаниями (баг 09.08.2026: одна фирма добавилась дважды из
            # разных подстраниц одного сайта в разных поисковых запросах).
            if len(row) > 11 and row[11]:
                d = domain_of(row[11])
                if d:
                    ex.add(d)
        return ex
    except:
        return set()

def add_company(ws, data, row_num):
    row = [str(row_num),data["name"],data.get("rating","4.5"),data.get("reviews","0"),data.get("years","1"),data.get("delivered","-"),data["description"][:200],",".join(data["directions"]),",".join(data["tags"]),data.get("telegram",""),data.get("phone","-"),data.get("site",""),"-","Россия","FALSE",data["name"][:3].upper(),"av-gray",data.get("yandex",""),data.get("inn",""),data.get("google",""),data.get("gis2",""),data.get("instagram",""),data.get("vk",""),data.get("avito",""),data.get("drom",""),data.get("autoru","")]
    # ВАЖНО: без table_range='A1' append_row без явного якоря может "уехать"
    # вправо — Sheets API ищет "таблицу" по всему листу и в редких случаях
    # (09.08.2026, найдено при разборе бага с 52 vs 82 строк) начинает
    # дописывать новые строки не с колонки A, а сразу за самой правой уже
    # занятой ячейкой на листе, со сдвигом, который растёт с каждым новым
    # вызовом (20 -> 44 -> 67 -> 89 -> 112 колонок вправо на реальном
    # прогоне). table_range='A1' явно фиксирует, что "таблица" начинается
    # с колонки A, и это гарантированно лечит сдвиг.
    ws.append_row(row, table_range='A1')
    subs = data.get("subscribers",0)
    inn_note = " [ИНН найден]" if data.get("inn") else ""
    print("  OK: " + data["name"] + (" (" + str(subs) + " подписчиков)" if subs > 0 else "") + inn_note)

BLACKLIST = ["avito","drom","auto.ru","drive2","vk.com","vk.ru","youtube","instagram","facebook","tiktok","yandex","google","wikipedia","zhihu","rutube","tgstat","nicegram","telegramchannels",
    # Украинские площадки/сервисы — не имеют отношения к импорту авто в СНГ
    "auto.ria","ria.com"]

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
    next_id = len(ws.get_all_values())
    found = 0
    skipped = 0

    print("\nШаг 1: tgstat.ru...")
    tg_channels = set()
    # Направленческие запросы + продающие фразы (SELLING_PHRASES) — каналы
    # часто называют/описывают себя через выгоду ("без посредников",
    # "растаможка под ключ"), а не через направление, обычные запросы их
    # пропускают.
    for q in ["импорт авто","авто из Кореи","авто из Китая","пригон авто","авто под заказ"] + SELLING_PHRASES:
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
        has_auto = any(w in text.lower() for w in ["авто","машин","импорт","корея","китай","япония","пригон"])
        if not has_auto or mentions_ukraine(text):
            skipped += 1
            continue
        years = extract_years_experience(text)
        phone = extract_phone(text)
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
        # Раньше публиковали только при подтверждении хотя бы на одной
        # независимой площадке. Теперь добавляем и при единственном
        # источнике (сам тг-канал) — но название стараемся взять максимально
        # верное (см. title выше), а не сырой ник, и печатаем в лог, если
        # подтверждения нигде не нашлось — для ручного контроля.
        if not (maps_verified or social_verified or market_verified):
            print(f"    ⚠️ {name}: подтвердилось только в Telegram, добавляю как есть")
        next_id += 1
        add_company(ws, {"name":name,"description":text or "Telegram канал @"+username,"directions":get_directions(text),"tags":get_tags(text),"telegram":username,"phone":phone,"subscribers":info["subscribers"],"years":str(years) if years else "1","yandex":yandex,"google":google,"gis2":gis2,"instagram":insta,"vk":vk,"avito":avito,"drom":drom,"autoru":autoru}, next_id)
        existing.add(name.lower())
        existing.add(username.lower())
        found += 1
        time.sleep(1)

    print("\nШаг 2: DuckDuckGo...")
    # Те же продающие фразы, что и в шаге 1 (SELLING_PHRASES) — здесь с
    # добавкой "Telegram канал"/"сайт", как и у остальных DDG-запросов,
    # чтобы вытягивать именно карточки компаний, а не общие статьи.
    ddg_queries = ["импорт авто Telegram канал Россия","авто из Кореи Китая под заказ Telegram","пригон авто аукцион Япония сайт","авто США ОАЭ Европа под заказ","импорт авто официальный сайт Россия"]
    ddg_queries += [p + " Telegram канал" for p in SELLING_PHRASES]
    for query in ddg_queries:
        print("  " + query)
        for item in search_ddgs(query, 5):
            title = item.get("title","")
            snippet = item.get("snippet","")
            link = item.get("link","")
            text = title + " " + snippet
            sl = link.lower()
            nl = title.lower()
            if any(b in sl or b in nl for b in BLACKLIST):
                skipped += 1
                continue
            has_auto = any(w in text.lower() for w in ["авто","импорт","машин","автомобил","пригон","корея","китай","япония"])
            tg = extract_telegram(text)
            phone = extract_phone(text)
            if not has_auto or mentions_ukraine(text) or (not tg and phone == "-" and not link.startswith("http")):
                skipped += 1
                continue
            domain = re.search(r"https?://(?:www\.)?([^/]+)", link)
            domain_name = domain.group(1).replace(".ru","").replace(".com","").title() if domain else ""
            dom = domain_of(link)
            # Дедуп по домену, а не только по имени/точной ссылке — без
            # этого одна и та же компания под разными подстраницами сайта
            # (japantransit.ru vs japantransit.ru/japan/auctions) в разных
            # поисковых запросах добавлялась дважды под двумя разными
            # (оба неверными) названиями. Проверяем ДО похода на сайт, чтобы
            # не тратить запрос впустую.
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
                handle_m = re.search(r"(?:t|telegram)\.me/([A-Za-z0-9_]+)", link, re.IGNORECASE)
                if handle_m and not tg:
                    tg = handle_m.group(1)
                preview = fetch_telegram_preview(tg) if tg else None
                name = (preview["title"] if preview and preview.get("title") else "") or tg or domain_name
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
                brand_name = extract_brand_from_site(site_text)
                name = brand_name or title_name or domain_name or title[:30]
                if brand_name and brand_name != title_name:
                    print(f"    имя со страницы сайта (og:site_name): '{brand_name}' (в выдаче было: '{title[:50]}')")
                elif not title_name and not brand_name:
                    print(f"    ⚠️ имя взято из домена ({name}) — стоит проверить вручную")
            if name.lower() in existing or (link and link.lower() in existing):
                skipped += 1
                continue
            # ИНН — из уже загруженного текста сайта (см. выше), запрос
            # повторно не делаем.
            inn = extract_inn(site_text) if site_text else ""
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
            yandex, google, gis2, maps_verified = find_map_links(name, phone)
            insta, vk, social_verified = find_social_links(name, text + " " + site_text, phone)
            avito, drom, autoru, market_verified = find_marketplace_links(name, phone)
            # Добавляем и при подтверждении только из одного источника —
            # но название уже взято максимально верно (title_name из
            # заголовка выдачи, а не домен, см. clean_name_from_title выше).
            # Печатаем в лог, если независимого подтверждения нигде не нашлось
            # — для ручного контроля, не блокирует публикацию.
            if not (inn or maps_verified or social_verified or market_verified):
                print(f"    ⚠️ {name}: подтвердилось только по исходному источнику, добавляю как есть")
            next_id += 1
            add_company(ws, {"name":name,"description":snippet[:200],"directions":get_directions(text),"tags":get_tags(text),"telegram":tg,"phone":phone,"site":link if link.startswith("http") else "","inn":inn,"years":str(years) if years else "1","yandex":yandex,"google":google,"gis2":gis2,"instagram":insta,"vk":vk,"avito":avito,"drom":drom,"autoru":autoru}, next_id)
            existing.add(name.lower())
            if link: existing.add(link.lower())
            if dom: existing.add(dom)
            found += 1
            time.sleep(0.5)
        time.sleep(3)

    print("\nГотово! Добавлено: " + str(found) + ", пропущено: " + str(skipped))
    print("Запусти python3 update_site.py чтобы обновить сайт!")

if __name__ == "__main__":
    run_agent()
