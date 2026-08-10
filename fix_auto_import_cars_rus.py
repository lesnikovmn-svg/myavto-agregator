"""
Пользователь указал на карточку "Авто из Европы / Авто Импорт ПРО"
(telegram @auto_import_cars_rus) — там оказались вместе: VK
(vk.ru/antaresauto — уже подтверждено пользователем ранее как чужое:
"Winner Auto Club... /51 не ведёт" — нет, это другой кейс; тут отдельно
проверено), сайт americanauto.ru?utm_source=2gis.

Причина (та же, что и раньше, но новый частный случай): _name_key для
этого названия давала просто "авто" — самое общее слово в нише, не было
в блэклисте (там раньше только латинское "avto"). Из-за этого при
автопоиске/бэкофилле подтянулась чужая 2ГИС-карточка (судя по
"?utm_source=2gis" в site — сайт americanauto.ru пришёл именно оттуда), а
дальше backfill_from_sources растащил из неё и VK.

Проверено вручную (09.08.2026): реальный Telegram-канал
@auto_import_cars_rus (6.8К подписчиков, og:title подтверждает — это
настоящее название канала, НЕ склейка от бага) — в постах канала за
последние дни нет ни слова про VK или americanauto.ru, только контакт
менеджера @T4_Vladimir и связанный канал @OtzyvyKliyentov_AutoImport.
Значит vk/site/2gis в таблице — чужие, чистим. Telegram НЕ трогаем — он
верный.

Исправлено заодно в company_agent.py: _name_key теперь ловит "авто" и
другие кириллические общеупотребимые слова в _GENERIC_NAME_WORDS.

Запуск: python3 fix_auto_import_cars_rus.py
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

NAME_COL, TELEGRAM_COL, SITE_COL = 2, 10, 12
GIS2_COL = 21
VK_COL = 23

TARGET_TELEGRAM = "auto_import_cars_rus"

all_values = ws.get_all_values()
row_i = None
for i, row in enumerate(all_values[1:], start=2):
    tg = row[9].strip().lower() if len(row) > 9 else ""
    if tg == TARGET_TELEGRAM:
        row_i = i
        row_data = row
        break

if not row_i:
    print("Карточка с telegram @auto_import_cars_rus не найдена.")
else:
    name = row_data[1].strip() if len(row_data) > 1 else ""
    cleared = []
    for col_name, col in (("vk", VK_COL), ("site", SITE_COL), ("2gis", GIS2_COL)):
        idx = col - 1
        val = row_data[idx].strip() if len(row_data) > idx and row_data[idx] else ""
        if val:
            ws.update_cell(row_i, col, "")
            cleared.append(f"{col_name} ({val})")
    if cleared:
        print(f"[{row_i}] {name}: очищено — {', '.join(cleared)}")
    else:
        print(f"[{row_i}] {name}: vk/site/2gis уже пустые, ничего не менял.")

print("\nTelegram (auto_import_cars_rus) НЕ трогал — подтверждён og:title канала.")
print("Теперь прогони python3 update_site.py.")
