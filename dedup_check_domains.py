"""
Проверка: несколько восстановленных записей похожи на дубли уже
существующих в каталоге компаний по домену сайта (shapcars.ru, westmotors.ru,
likeavto.ru) — и japantransit.ru встречается дважды среди самих
восстановленных. Собираем ВСЕ компании с непустым сайтом, группируем по
домену (без www/схемы/пути) и печатаем все группы, где домен встречается
больше одного раза — с id/названием/ИНН каждой, чтобы решить, что удалить.

Запуск: python3 dedup_check_domains.py
"""
import re
from collections import defaultdict
import gspread
from google.oauth2.service_account import Credentials

config = {}
with open("agent_config.env") as f:
    for line in f:
        if "=" in line:
            k, v = line.strip().split("=", 1)
            config[k] = v
SHEET_ID = config["SHEET_ID"]

scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
client = gspread.authorize(creds)
ws = client.open_by_key(SHEET_ID).sheet1

all_values = ws.get_all_values()

def domain_of(url):
    m = re.search(r"https?://(?:www\.)?([^/]+)", url)
    return m.group(1).lower() if m else ""

groups = defaultdict(list)
for i, row in enumerate(all_values[1:], start=2):
    name = row[1].strip() if len(row) > 1 else ""
    site = row[11].strip() if len(row) > 11 else ""
    inn = row[18].strip() if len(row) > 18 else ""
    if not name or not site:
        continue
    d = domain_of(site)
    if d:
        groups[d].append((i, name, site, inn))

dupes = {d: rows for d, rows in groups.items() if len(rows) > 1}
print(f"Доменов с более чем одной записью: {len(dupes)}\n")
for d, rows in dupes.items():
    print(f"=== {d} ===")
    for i, name, site, inn in rows:
        print(f"  строка {i}: '{name}' | ИНН={inn or '-'} | {site}")
    print()

if not dupes:
    print("Дублей по домену не найдено.")
