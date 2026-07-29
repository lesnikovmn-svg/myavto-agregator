import requests
import json
import re
import time
import gspread
from ddgs import DDGS
from google.oauth2.service_account import Credentials

config = {}
with open("agent_config.env") as f:
    for line in f:
        if "=" in line:
            k, v = line.strip().split("=", 1)
            config[k] = v

GOOGLE_API_KEY = config["GOOGLE_API_KEY"]
SEARCH_ENGINE_ID = config["SEARCH_ENGINE_ID"]
SHEET_ID = config["SHEET_ID"]

def connect_sheets():
    scopes = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_ID)
    return sheet.sheet1

def search_companies(query, num=5):
    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=num, region="ru-ru"):
                results.append({
                    "title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                    "link": r.get("href", "")
                })
        return results
    except Exception as e:
        print("Ошибка поиска: " + str(e))
        return []

def check_site(url):
    try:
        r = requests.get(url, timeout=5, allow_redirects=True)
        return r.status_code == 200
    except:
        return False

def extract_company_data(item):
    title = item.get("title", "")
    snippet = item.get("snippet", "")
    link = item.get("link", "")
    phone_match = re.search(r"[78][\s\-\(]?\d{3}[\s\-\(]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}", snippet)
    phone = phone_match.group(0) if phone_match else "-"
    tg_match = re.search(r"@([A-Za-z0-9_]{3,})", snippet + " " + title)
    telegram = tg_match.group(1) if tg_match else ""
    directions = []
    direction_map = {
        "Китай": ["китай","china","byd","haval","geely","chery"],
        "Корея": ["корея","korea","kia","hyundai","genesis"],
        "Япония": ["япония","japan","toyota","lexus","honda","nissan"],
        "США": ["сша","usa","america","tesla","ford","cadillac"],
        "ОАЭ": ["оаэ","uae","dubai","эмираты"],
        "Европа": ["европа","europe","bmw","mercedes","audi","volkswagen"],
        "Канада": ["канада","canada"],
        "Грузия": ["грузия","georgia"],
    }
    text_lower = (title + " " + snippet).lower()
    for direction, keywords in direction_map.items():
        if any(kw in text_lower for kw in keywords):
            directions.append(direction)
    if not directions:
        directions = ["Не указано"]
    tags = []
    if "под ключ" in text_lower: tags.append("Под ключ")
    if "растаможк" in text_lower: tags.append("Растаможка")
    if "аукцион" in text_lower: tags.append("Аукционы")
    if "параллельн" in text_lower: tags.append("Параллельный импорт")
    if not tags: tags.append("Импорт авто")
    domain = re.search(r"https?://(?:www\.)?([^/]+)", link)
    company_name = domain.group(1).replace(".ru","").replace(".com","").title() if domain else title[:30]
    site = link if link.startswith("http") else ""
    is_active = check_site(link) if site else False
    return {"name": company_name, "directions": ",".join(directions), "tags": ",".join(tags), "telegram": telegram, "phone": phone, "site": site, "active": is_active, "snippet": snippet[:100]}

def get_existing_companies(worksheet):
    try:
        data = worksheet.get_all_values()
        existing = set()
        for row in data[1:]:
            if len(row) > 1 and row[1]: existing.add(row[1].lower().strip())
            if len(row) > 11 and row[11]: existing.add(row[11].lower().strip())
        return existing
    except:
        return set()

def add_to_sheet(worksheet, company, row_num):
    row = [str(row_num), company["name"], "4.5", "0", "1", "-", company["snippet"], company["directions"], company["tags"], company["telegram"], company["phone"], company["site"], "-", "Россия", "FALSE", company["name"][:3].upper(), "av-gray"]
    worksheet.append_row(row)
    print("  OK: " + company["name"])

def run_agent():
    print("Запускаю агента...")
    try:
        worksheet = connect_sheets()
        print("Подключено к Google Sheets!")
    except Exception as e:
        print(f"Ошибка подключения: {e}")
        return
    existing = get_existing_companies(worksheet)
    print(f"В таблице уже {len(existing)} записей")
    current_rows = len(worksheet.get_all_values())
    next_id = current_rows
    queries = [
        "авто под заказ Telegram импорт",
        "импорт авто Telegram канал",
        "авто из Кореи Китая под заказ Telegram WhatsApp",
        "пригон авто Японии аукцион Telegram",
        "авто в наличии склад Китай Корея Telegram",
        "параллельный импорт авто Telegram канал",
        "авто США ОАЭ Европа под заказ Telegram",
        "импорт авто Краснодар Telegram",
        "импорт авто Москва Telegram канал",
        "авто из Китая электромобили Telegram",
        "растаможка авто Армения Грузия Telegram",
        "авто аукцион Япония Корея Telegram",
        "авто под заказ WhatsApp импортёр",
        "автомобили под заказ из Кореи отзывы",
        "пригон авто отзывы компания Россия",
    ]
    found = 0
    skipped = 0
    for query in queries:
        print(f"Поиск: {query}")
        results = search_companies(query, num=5)
        if not results:
            print("  Нет результатов")
            continue
        for item in results:
            company = extract_company_data(item)
            if company["name"].lower() in existing or (company["site"] and company["site"].lower() in existing):
                skipped += 1
                continue
            # Фильтр: только русские сайты или с Telegram
            site = company["site"]
            is_russian = any(x in site for x in [".ru", ".рф", "t.me", "vk.com"])
            has_tg = bool(company["telegram"])
            has_auto_keywords = any(w in (company["snippet"]+company["name"]).lower() for w in ["авто","импорт","машин","автомобил","пригон","растаможк","корея","китай","япония"])
            if (is_russian or has_tg) and has_auto_keywords:
                next_id += 1
                add_to_sheet(worksheet, company, next_id)
                existing.add(company["name"].lower())
                if company["site"]: existing.add(company["site"].lower())
                found += 1
                time.sleep(0.5)
            else:
                skipped += 1
        time.sleep(1)
    print(f"Готово! Добавлено: {found}, пропущено: {skipped}")

run_agent()
