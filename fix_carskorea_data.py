"""
Разовый фикс: компания попала в таблицу под именем "T.Me" — агент взял домен
ссылки (t.me/carskoreashop, канал компании) вместо реального названия.
Реальное название и реквизиты — с официального сайта carskorea.shop:
  Название: CarsKorea
  Сайт:     https://carskorea.shop
  Телефон:  8 (800) 505-35-43
  ИНН:      2721156632 (ООО «Айти-результат»)

Причина самой ошибки исправлена в company_agent.py (агент больше не будет
слепо брать имя из домена t.me) — это разовая правка уже добавленной записи.

Запуск: python3 fix_carskorea_data.py
После — python3 update_site.py, чтобы сразу пересобрать сайт и проверить
новый ИНН по ЕГРЮЛ/DaData.
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

# id,name,rating,reviews,years,delivered,description,directions,tags,
# telegram,phone,site,manager,region,featured,avatar,color,yandex,inn
NAME_COL = 2
PHONE_COL = 11
SITE_COL = 12
INN_COL = 19

scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
client = gspread.authorize(creds)
ws = client.open_by_key(SHEET_ID).sheet1

rows = ws.get_all_values()
row_idx = None
for i, row in enumerate(rows[1:], start=2):
    if len(row) > 1 and row[1].strip() == "T.Me":
        row_idx = i
        break

if row_idx is None:
    print("Компания 'T.Me' не найдена — возможно, уже исправлена.")
else:
    ws.update_cell(row_idx, NAME_COL, "CarsKorea")
    ws.update_cell(row_idx, PHONE_COL, "8 (800) 505-35-43")
    ws.update_cell(row_idx, SITE_COL, "https://carskorea.shop")
    ws.update_cell(row_idx, INN_COL, "2721156632")
    print(f"Готово. Строка {row_idx}: T.Me -> CarsKorea, сайт/телефон/ИНН заполнены.")
    print("Теперь прогони python3 update_site.py, чтобы пересобрать сайт сразу.")
