"""
Финальный проход после разбора ложной тревоги с "удалёнными" компаниями:

1. Восстанавливает "AutoImport Russia" — единственную реально пропавшую
   запись (остальные "удаления" в логе fix_generic_names_final.py были
   неправильно подписаны из-за off-by-one бага в индексации при печати —
   сами компании остались на месте, подтверждено через check_names_exist.py).
   Данные для восстановления — из более ранней диагностики
   (debug_sheet_count3.py), сняты ДО того, как что-либо пошло не так:
   ИНН 2508148924, телефон/соцсети/маркетплейсы все настоящие.

2. Переименовывает "Авто из Китая, новые и б/у" (сайт jptrade.ru/chinacar/)
   в "China Trade" — пользователь лично зашёл на сайт и подтвердил
   настоящее название ("чайна тред").

3. Дочищает два названия, которые остались необрезанными по разделителю
   (fix_recovered_names_cleanup.py в своё время не запускали):
   "LimCars - Авто напрямую из Кореи, Китая, Японии" -> "LimCars"
   "Честный Импорт · импорт авто из Кореи и Китая под ключ" -> "Честный Импорт"

Запуск: python3 fix_final_restore_and_cleanup.py
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

# --- 1. восстановление AutoImport Russia ---
all_values = ws.get_all_values()
existing_names = {row[1].strip().lower() for row in all_values[1:] if len(row) > 1 and row[1].strip()}

if "autoimport russia" in existing_names:
    print("AutoImport Russia уже есть в таблице — восстанавливать не нужно.")
else:
    row_num = len(ws.get_all_values()) + 1
    row = [
        str(row_num),                          # id
        "AutoImport Russia",                   # name
        "4.5", "0", "1", "-",                  # rating, reviews, years, delivered
        "AutoImport Russia | Авто из Европы (@autoimportrussiarf) – Публичный Telegram-канал на русском языке в категории «Транспорт».",  # description
        "Не указано",                          # directions
        "Импорт авто",                         # tags
        "autoimportrussiarf",                  # telegram
        "-",                                    # phone
        "https://telegram.menu/@autoimportrussiarf",  # site
        "-", "Россия", "FALSE", "AUT", "av-gray",      # manager, region, featured, avatar, color
        "",                                     # yandex
        "2508148924",                           # inn
        "",                                     # google
        "https://2gis.ru/staroskol/firm/8444777582325860",  # gis2
        "https://www.instagram.com/auto_import_russia/",    # instagram
        "",                                     # vk
        "https://www.avito.ru/brands/b58faea7a67f53f45bfa27a8a300157a",  # avito
        "https://vin.drom.ru/",                 # drom
        "",                                     # autoru
    ]
    ws.append_row(row, table_range='A1')
    print("Восстановлена: AutoImport Russia (ИНН 2508148924)")

# --- 2 и 3: переименования ---
RENAMES = {
    "Авто из Китая, новые и б/у": "China Trade",
    "LimCars - Авто напрямую из Кореи, Китая, Японии": "LimCars",
    "Честный Импорт · импорт авто из Кореи и Китая под ключ": "Честный Импорт",
}

all_values = ws.get_all_values()
for i, row in enumerate(all_values[1:], start=2):
    name = row[1].strip() if len(row) > 1 else ""
    if name in RENAMES:
        ws.update_cell(i, 2, RENAMES[name])
        print(f"Строка {i}: '{name}' -> '{RENAMES[name]}'")

print("\nГотово. Теперь прогони python3 update_site.py.")
