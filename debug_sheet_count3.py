"""
Продолжение: строки 54-82 (29 штук) имеют пустые id/name/rating/reviews/years
(колонки A-E), но помечены как "есть другие данные" — значит что-то есть
правее, в колонках F+ (description и дальше). Печатаем ВСЕ 26 колонок для
первых нескольких таких строк, чтобы понять, что реально записалось и куда.

Запуск: python3 debug_sheet_count3.py
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

all_values = ws.get_all_values()
header = all_values[0]
print(f"Заголовки (колонка -> название): {list(enumerate(header))}\n")

for i in range(54, 60):
    row = all_values[i - 1]
    print(f"--- строка {i} (длина {len(row)}) ---")
    for col_idx, val in enumerate(row):
        if val.strip():
            col_name = header[col_idx] if col_idx < len(header) else f"col{col_idx}"
            print(f"    [{col_idx}] {col_name}: '{val}'")
    print()
