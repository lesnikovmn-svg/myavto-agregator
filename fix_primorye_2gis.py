"""
Точечный фикс: у "Primorye China Export" 2ГИС-ссылка технически валидна по
формату (настоящая карточка firm/id), поэтому её не поймал
fix_reverify_all_links.py (тот ловит только заведомо не-карточки — поиск/
пост/видео). Но по содержанию это чужая компания: branch_id
70000001075724035 совпадает с 2ГИС-виджетом на сайте b2bchina.info
(компания "B2B-China", СПб, товары из Китая вообще — не авто). Проверено
вручную 09.08.2026.

Просто чистим поле — новую подтверждённую замену через find_map_links не
нашли (перепробовано в fix_reverify_all_links.py для yandex/vk этой же
строки, 2ГИС отдельно не подтвердился), оставляем пустым, кнопка 2ГИС у
Primorye China Export просто не будет показываться на сайте — честнее, чем
вести на чужую компанию.

Запуск: python3 fix_primorye_2gis.py
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

GIS2_COL = 21

scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
client = gspread.authorize(creds)
ws = client.open_by_key(SHEET_ID).sheet1

all_values = ws.get_all_values()
row_idx = None
for i, row in enumerate(all_values[1:], start=2):
    if len(row) > 1 and row[1].strip() == "Primorye China Export":
        row_idx = i
        break

if row_idx is None:
    print("Primorye China Export не найдена.")
else:
    current = all_values[row_idx - 1][GIS2_COL - 1] if len(all_values[row_idx - 1]) >= GIS2_COL else ""
    if "70000001075724035" in current:
        ws.update_cell(row_idx, GIS2_COL, "")
        print(f"Строка {row_idx}: очищена неверная 2ГИС-ссылка (вела на B2B-China, не на эту компанию).")
    else:
        print(f"Строка {row_idx}: 2ГИС-поле уже другое ('{current}') — не трогаю, похоже, уже исправлено.")

print("\nГотово. Теперь прогони python3 update_site.py.")
