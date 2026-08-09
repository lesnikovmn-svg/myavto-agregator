"""
Разовый фикс: у Altais-Cars агент почему-то не вытащил ни стаж, ни ИНН при
добавлении (years так и остался дефолтной "1"). На сайте altais-cars.ru
прямым текстом написано: "Компания Altais Cars с 1998 года предоставляет
клиентам..." — это 28 лет на 2026 год. В футере также указан реальный ИНН:
7716254778 (ООО "АЛЬТАИС-АВТО", ОГРН 1257700476516).

ИНН пишем в таблицу — update_site.py сам проверит его по ЕГРЮЛ/DaData и
решит, ставить ли зелёный бейдж (год из ЕГРЮЛ может отличаться от 1998,
если это переоформление юрлица — бейдж и "стаж работы" разные вещи).

Запуск: python3 fix_altais_cars.py
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

# id,name,rating,reviews,years,delivered,description,directions,tags,
# telegram,phone,site,manager,region,featured,avatar,color,yandex,inn
YEARS_COL = 5
INN_COL = 19

scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
client = gspread.authorize(creds)
ws = client.open_by_key(SHEET_ID).sheet1

rows = ws.get_all_values()
row_idx = None
for i, row in enumerate(rows[1:], start=2):
    if len(row) > 1 and row[1].strip() == "Altais-Cars":
        row_idx = i
        break

if row_idx is None:
    print("Компания 'Altais-Cars' не найдена — возможно, название изменилось.")
else:
    ws.update_cell(row_idx, YEARS_COL, "28")
    ws.update_cell(row_idx, INN_COL, "7716254778")
    print(f"Готово. Строка {row_idx}: years -> 28 (с 1998 года), ИНН -> 7716254778")
    print("Теперь прогони python3 update_site.py.")
