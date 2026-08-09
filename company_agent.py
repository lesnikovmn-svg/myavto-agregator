import requests
import json
import re
import time
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
    for sep in [" — ", " – ", " | ", " - "]:
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
    return tags if tags else ["Импорт авто"]

def search_tgstat(query):
    url = "https://tgstat.ru/channels/search?q=" + requests.utils.quote(query) + "&country=ru"
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200: return []
        return list(set(re.findall(r"@([A-Za-z0-9_]{3,32})", r.text)))[:10]
    except:
        return []

def parse_tgstat_channel(username):
    try:
        r = requests.get("https://tgstat.ru/channel/@" + username, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200: return None
        html = r.text
        subs_m = re.search(r"(\d[\d\s]+)\s*подписчик", html)
        subs = int(subs_m.group(1).replace(" ","")) if subs_m else 0
        desc_m = re.search(r"peer-description[^>]*>(.*?)</div>", html, re.DOTALL)
        desc = re.sub(r"<[^>]+>","",desc_m.group(1)).strip()[:200] if desc_m else ""
        return {"subscribers": subs, "description": desc}
    except:
        return None

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
        return ex
    except:
        return set()

def add_company(ws, data, row_num):
    row = [str(row_num),data["name"],data.get("rating","4.5"),data.get("reviews","0"),data.get("years","1"),data.get("delivered","-"),data["description"][:200],",".join(data["directions"]),",".join(data["tags"]),data.get("telegram",""),data.get("phone","-"),data.get("site",""),"-","Россия","FALSE",data["name"][:3].upper(),"av-gray","",data.get("inn","")]
    ws.append_row(row)
    subs = data.get("subscribers",0)
    inn_note = " [ИНН найден]" if data.get("inn") else ""
    print("  OK: " + data["name"] + (" (" + str(subs) + " подписчиков)" if subs > 0 else "") + inn_note)

BLACKLIST = ["avito","drom","auto.ru","drive2","vk.com","youtube","instagram","facebook","tiktok","yandex","google","wikipedia","zhihu","rutube","tgstat","nicegram","telegramchannels",
    # Украинские площадки/сервисы — не имеют отношения к импорту авто в СНГ
    "auto.ria","ria.com"]

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
    for q in ["импорт авто","авто из Кореи","авто из Китая","пригон авто","авто под заказ"]:
        channels = search_tgstat(q)
        tg_channels.update(channels)
        print("  " + q + ": " + str(len(channels)) + " каналов")
        time.sleep(2)

    for username in tg_channels:
        if username.lower() in existing:
            skipped += 1
            continue
        info = parse_tgstat_channel(username)
        if not info or info["subscribers"] < 500:
            skipped += 1
            continue
        text = info["description"]
        has_auto = any(w in text.lower() for w in ["авто","машин","импорт","корея","китай","япония","пригон"])
        if not has_auto:
            skipped += 1
            continue
        next_id += 1
        add_company(ws, {"name":username,"description":text or "Telegram канал @"+username,"directions":get_directions(text),"tags":get_tags(text),"telegram":username,"phone":extract_phone(text),"subscribers":info["subscribers"]}, next_id)
        existing.add(username.lower())
        found += 1
        time.sleep(1)

    print("\nШаг 2: DuckDuckGo...")
    for query in ["импорт авто Telegram канал Россия","авто из Кореи Китая под заказ Telegram","пригон авто аукцион Япония сайт","авто США ОАЭ Европа под заказ","импорт авто официальный сайт Россия"]:
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
            if not has_auto or (not tg and phone == "-" and not link.startswith("http")):
                skipped += 1
                continue
            domain = re.search(r"https?://(?:www\.)?([^/]+)", link)
            domain_name = domain.group(1).replace(".ru","").replace(".com","").title() if domain else ""
            title_name = clean_name_from_title(title)
            if domain and domain.group(1).lower() in ("t.me", "telegram.me"):
                # Ссылка на Telegram-канал/бота — домен "T.Me" бесполезен
                # как имя компании. Достаём хэндл из самой ссылки и берём
                # имя из заголовка выдачи, а не из домена.
                handle_m = re.search(r"(?:t|telegram)\.me/([A-Za-z0-9_]+)", link, re.IGNORECASE)
                if handle_m and not tg:
                    tg = handle_m.group(1)
                name = title_name or tg or domain_name
            else:
                # Предпочитаем название из заголовка поисковой выдачи — это
                # почти всегда настоящее имя компании. Домен — запасной
                # вариант на случай, если заголовок пустой/бесполезный.
                name = title_name or domain_name or title[:30]
                if not title_name:
                    print(f"    ⚠️ имя взято из домена ({name}) — стоит проверить вручную")
            if name.lower() in existing or (link and link.lower() in existing):
                skipped += 1
                continue
            # Пробуем найти ИНН на самом сайте компании (обычно в футере
            # или на странице "Реквизиты"/"О компании"). Если не вышло —
            # не страшно, компания просто пока без бейджа ЕГРЮЛ.
            inn = ""
            if link.startswith("http"):
                site_text = fetch_site_text(link)
                if site_text:
                    inn = extract_inn(site_text)
            next_id += 1
            add_company(ws, {"name":name,"description":snippet[:200],"directions":get_directions(text),"tags":get_tags(text),"telegram":tg,"phone":phone,"site":link if link.startswith("http") else "","inn":inn}, next_id)
            existing.add(name.lower())
            if link: existing.add(link.lower())
            found += 1
            time.sleep(0.5)
        time.sleep(3)

    print("\nГотово! Добавлено: " + str(found) + ", пропущено: " + str(skipped))
    print("Запусти python3 update_site.py чтобы обновить сайт!")

if __name__ == "__main__":
    run_agent()
