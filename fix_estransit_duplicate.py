"""
⚠️ ПЕРЕД ЗАПУСКОМ: поставь именованную версию в Google Sheets (если ещё
не ставил для этого захода — Файл → История версий → Назвать текущую
версию → «до fix_estransit_duplicate»).

Пользователь подтвердил (10.08.2026): карточка "ES Transit"
(estransit-premium.ru) — дубль уже существующей карточки "Es-Transit"
(es-transit.ru). У дубля вдобавок битое поле telegram — там буквально
слово "yandex" вместо юзернейма (явный мусор). Удаляем дубль, оригинал
es-transit.ru не трогаем.

Запуск: python3 fix_estransit_duplicate.py
После — python3 update_site.py.
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

NAME_COL, SITE_COL = 2, 12

all_values = ws.get_all_values()
row_i = None
for i, row in enumerate(all_values[1:], start=2):
    site = row[SITE_COL - 1].strip().lower() if len(row) >= SITE_COL else ""
    if "estransit-premium.ru" in site:
        row_i = i
        name = row[NAME_COL - 1] if len(row) >= NAME_COL else ""
        break

if not row_i:
    print("Карточку с сайтом estransit-premium.ru не нашёл — возможно, уже удалена.")
else:
    ws.delete_rows(row_i)
    print(f"[{row_i}] удалено: {name} (estransit-premium.ru) — дубль Es-Transit (es-transit.ru)")

print("\nТеперь прогони python3 update_site.py.")
