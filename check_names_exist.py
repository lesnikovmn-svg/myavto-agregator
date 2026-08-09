"""
Проверка: реально ли пропали конкретные компании из ТЕКУЩЕЙ таблицы, или
баг с индексацией в логе fix_generic_names_final.py просто НЕПРАВИЛЬНО их
подписал (реально удалилась соседняя строка, а не они).

Запуск: python3 check_names_exist.py
"""
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

CHECK_NAMES = [
    "MY Avto", "AviAuto", "CarExport", "LimCars - Авто напрямую из Кореи, Китая, Японии",
    "LimCars", "Telegram – a new era of messaging", "ТокиДоки", "Япония Транзит",
    "AutoImport Russia", "EncarRus", "Авто из Европы / Авто Импорт ПРО", "ПримАвто",
    "LikeAvto",
]

all_values = ws.get_all_values()
present = {}
for i, row in enumerate(all_values[1:], start=2):
    name = row[1].strip() if len(row) > 1 else ""
    if name:
        present.setdefault(name, []).append(i)

print(f"Всего компаний сейчас: {len([r for r in all_values[1:] if len(r) > 1 and r[1].strip()])}\n")
for name in CHECK_NAMES:
    if name in present:
        print(f"ЕСТЬ:  '{name}' -> строки {present[name]}")
    else:
        print(f"НЕТ:   '{name}'")

print("\nВсе текущие названия по порядку:")
for i, row in enumerate(all_values[1:], start=2):
    name = row[1].strip() if len(row) > 1 else ""
    site = row[11].strip() if len(row) > 11 else ""
    print(f"  {i}: {name}  |  {site}")
