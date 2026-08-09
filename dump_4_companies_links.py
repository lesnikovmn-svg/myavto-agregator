"""
Смотрим полные данные (все ссылки-площадки) у 4 конкретных компаний, где
пользователь заметил, что иконки Яндекс/2ГИС/VK ведут не на ту компанию:
ТамСямAUTO, Primorye China Export, Winner Auto Club, Artalex Group.

Запуск: python3 dump_4_companies_links.py
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

TARGET = {"ТамСямAUTO", "Primorye China Export", "Winner Auto Club", "Artalex Group"}

all_values = ws.get_all_values()
header = all_values[0]
for i, row in enumerate(all_values[1:], start=2):
    name = row[1].strip() if len(row) > 1 else ""
    if name not in TARGET:
        continue

    def g(col_idx):
        return row[col_idx].strip() if col_idx < len(row) and row[col_idx] else ""

    print(f"--- строка {i}: '{name}' ---")
    print(f"  сайт:       {g(11)}")
    print(f"  телефон:    {g(10)}")
    print(f"  направления:{g(7)}")
    print(f"  описание:   {g(6)}")
    print(f"  yandex:     {g(17)}")
    print(f"  google:     {g(19)}")
    print(f"  2gis:       {g(20)}")
    print(f"  instagram:  {g(21)}")
    print(f"  vk:         {g(22)}")
    print()
