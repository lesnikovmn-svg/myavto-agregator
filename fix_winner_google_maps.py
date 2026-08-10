"""
Пользователь прислал ссылку на карточку Winner Auto Club в Google Maps
(координаты 41.566, 44.952 — Рустави, Грузия, совпадает с уже
подтверждённой карточкой Яндекс.Карт, см. fix_winner_auto_club.py).
Дописываем поле google.

Запуск: python3 fix_winner_google_maps.py
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

NAME_COL, GOOGLE_COL = 2, 20

GOOGLE_MAPS_URL = ("https://www.google.com/maps/place/Winner+Auto+Club/"
    "@41.5663656,44.9499706,1585m/data=!3m2!1e3!4b1!4m6!3m5!"
    "1s0x4044070029c45a89:0xd09e51429b9bd97a!8m2!3d41.5663656!4d44.9525509")

all_values = ws.get_all_values()
row_i = None
for i, row in enumerate(all_values[1:], start=2):
    name = row[1].strip() if len(row) > 1 else ""
    if name == "Winner Auto Club":
        row_i = i
        break

if not row_i:
    print("Winner Auto Club не найдена в таблице.")
else:
    ws.update_cell(row_i, GOOGLE_COL, GOOGLE_MAPS_URL)
    print(f"Строка {row_i}: Winner Auto Club — google обновлён.")

print("Теперь прогони python3 update_site.py.")
