"""
Показывает полную карточку (сайт/телеграм/телефон/ИНН/описание) для
компаний с подозрительно "общими" названиями (похожими на рекламные
заголовки/статьи, а не на конкретный бренд) — чтобы решить по каждой
отдельно, реальная это компания или нет.

Запуск: python3 dump_generic_names_detail.py
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

TARGET_NAMES = {
    "Автомобили из Японии, Кореи и Китая под заказ",
    "Автомобили с аукционов Японии",
    "Авто под заказ из Японии, Кореи и Китая",
    "Статистика продаж автомобилей на аукционах Японии",
    "Купить авто из Кореи, Китая, ОАЭ, Европы под ключ. Автоблогер...",
    "Купить авто из ОАЭ в Россию, Москву под ключ",
    "Купить новое авто с доставкой",
    "Авто из Кореи под заказ",
    "Авто с аукционов Японии, Кореи и Китая под заказ",
    "Японский аукцион автомобилей Toyota из Японии",
    "Импорт авто из Кореи, Китая и Японии",
}

all_values = ws.get_all_values()
header = all_values[0]
col = {name: i for i, name in enumerate(header)}

for i, row in enumerate(all_values[1:], start=2):
    name = row[1].strip() if len(row) > 1 else ""
    if name not in TARGET_NAMES:
        continue

    def g(col_idx):
        return row[col_idx].strip() if col_idx < len(row) and row[col_idx] else ""

    print(f"--- строка {i}: '{name}' ---")
    print(f"  сайт:      {g(11)}")
    print(f"  telegram:  {('@' + g(9)) if g(9) else ''}")
    print(f"  телефон:   {g(10)}")
    print(f"  ИНН:       {g(18)}")
    print(f"  описание:  {g(6)}")
    print()
