"""
Разовый фикс: убирает Northamcars (northamcars.com) из таблицы. Их реальные
направления доставки — Украина, ОАЭ, Польша, Прибалтика (номер +380,
украинский), России/СНГ там нет — не подходит для этого каталога.

Причина, почему агент вообще её добавил, устранена: в company_agent.py
теперь есть проверка mentions_ukraine() — если на сайте компании
встречается слово "Украина" в любой форме, агент такую компанию пропускает.

Запуск: python3 fix_remove_northamcars.py
После — python3 update_site.py, чтобы пересобрать сайт без этой записи.
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

rows = ws.get_all_values()
row_idx = None
for i, row in enumerate(rows[1:], start=2):
    if len(row) > 1 and row[1].strip() == "Northamcars":
        row_idx = i
        break

if row_idx is None:
    print("Компания 'Northamcars' не найдена — возможно, уже удалена.")
else:
    ws.delete_rows(row_idx)
    print(f"Готово. Строка {row_idx} (Northamcars) удалена из таблицы.")
    print("Теперь прогони python3 update_site.py, чтобы пересобрать сайт сразу.")
