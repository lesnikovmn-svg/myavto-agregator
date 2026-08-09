"""
Разовый скрипт: правит реальные данные MY Avto (id=1) прямо в Google Sheet —
источнике правды для сайта. Раньше эти цифры поправили только в index.html
руками, а update_site.py при каждом автозапуске (cron, 8:00 утра) перезаписывает
index.html заново из таблицы — поэтому старые значения (8 лет, 5000+) каждый
раз возвращались.

Правит:
  years:     8 -> 11   (работает с 2015 года)
  delivered: 5000+ -> 1000+
  yandex:    ссылка на реальные отзывы (https://yandex.ru/profile/-/CTvFvXPa)

Запуск: python3 fix_myavto_data.py
После — как обычно: python3 update_site.py, чтобы сразу пересобрать сайт
с исправленными данными (иначе подождёт следующего cron-запуска).
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

# Позиции колонок в таблице (1-индексация, как у gspread update_cell).
# id,name,rating,reviews,years,delivered,description,directions,tags,
# telegram,phone,site,manager,region,featured,avatar,color,yandex,inn
YEARS_COL = 5
DELIVERED_COL = 6
YANDEX_COL = 18

scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
client = gspread.authorize(creds)
ws = client.open_by_key(SHEET_ID).sheet1

rows = ws.get_all_values()
row_idx = None
for i, row in enumerate(rows[1:], start=2):  # строка 1 — заголовки
    if len(row) > 1 and row[1].strip() == "MY Avto":
        row_idx = i
        break

if row_idx is None:
    print("Компания 'MY Avto' не найдена в таблице — ничего не поменял.")
else:
    old_years = rows[row_idx - 1][YEARS_COL - 1] if len(rows[row_idx - 1]) >= YEARS_COL else ""
    old_delivered = rows[row_idx - 1][DELIVERED_COL - 1] if len(rows[row_idx - 1]) >= DELIVERED_COL else ""
    old_yandex = rows[row_idx - 1][YANDEX_COL - 1] if len(rows[row_idx - 1]) >= YANDEX_COL else ""
    ws.update_cell(row_idx, YEARS_COL, "11")
    ws.update_cell(row_idx, DELIVERED_COL, "1000+")
    ws.update_cell(row_idx, YANDEX_COL, "https://yandex.ru/profile/-/CTvFvXPa")
    print(f"Готово. Строка {row_idx}: years {old_years} -> 11, delivered {old_delivered} -> 1000+")
    print(f"  yandex: {old_yandex} -> https://yandex.ru/profile/-/CTvFvXPa")
    print("Теперь прогони python3 update_site.py, чтобы пересобрать сайт сразу.")
