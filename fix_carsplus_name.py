"""
Разовый фикс: компания с сайтом jtfgj.tb.ru была добавлена агентом под именем
"Jtfgj.Tb" (взял домен вместо реального названия — на сайте оно не лежало
в стандартном <title>-паттерне, который парсит company_agent.py).
Реальное название — Carsplus (Карсплюс), автосалон в Москве.

Запуск: python3 fix_carsplus_name.py
После — python3 update_site.py, чтобы сразу пересобрать сайт.
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
NAME_COL = 2  # id,name,rating,...

scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
client = gspread.authorize(creds)
ws = client.open_by_key(SHEET_ID).sheet1

rows = ws.get_all_values()
row_idx = None
for i, row in enumerate(rows[1:], start=2):
    if len(row) > 1 and row[1].strip() == "Jtfgj.Tb":
        row_idx = i
        break

if row_idx is None:
    print("Компания 'Jtfgj.Tb' не найдена — возможно, уже исправлена.")
else:
    ws.update_cell(row_idx, NAME_COL, "Carsplus")
    print(f"Готово. Строка {row_idx}: имя Jtfgj.Tb -> Carsplus")
    print("Теперь прогони python3 update_site.py, чтобы пересобрать сайт сразу.")
