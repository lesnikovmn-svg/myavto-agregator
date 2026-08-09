"""
Обобщение fix_backfill_from_2gis.py (09.08.2026): дозаполняет пустые поля
компании не ТОЛЬКО с карточки 2ГИС, а из НЕСКОЛЬКИХ известных источников
подряд, в порядке приоритета — по прямой просьбе пользователя: "заполнять
можно не только тугиз, а из известных источников карточки, если есть на
яндексе данные то добираем оттуда, есть сайт — берём оттуда и так далее".

Порядок источников на компанию: собственный сайт (если уже известен) →
карточка 2ГИС → карточка Яндекс.Карт. Каждый следующий источник
дозаполняет только то, что предыдущие не нашли — уже найденное никогда не
перезаписывается. Если карточки 2ГИС/Яндекс.Карт ещё нет в таблице, но
чего-то не хватает — пробуем один раз найти и подтвердить (та же логика,
что и find_map_links, по названию/телефону) и, если получилось, заодно
сохраняем в таблицу на будущее.

Перед тем, как брать данные из карточки, проверяем, что она реально про
эту компанию (название/телефон совпадают в её содержимом) — на случай,
если ссылка в таблице осталась от старой, менее строгой проверки
(content_check в backfill_from_sources).

Это ЗАМЕНА fix_backfill_from_2gis.py — используй этот скрипт вместо него.

Запуск: python3 fix_backfill_from_sources.py
После — python3 update_site.py.
"""
import time
import gspread
from google.oauth2.service_account import Credentials
from company_agent import backfill_from_sources, _name_key, find_platform_link

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

NAME_COL, TELEGRAM_COL, PHONE_COL, SITE_COL = 2, 10, 11, 12
YANDEX_COL, GOOGLE_COL, GIS2_COL = 18, 20, 21
INSTAGRAM_COL, VK_COL = 22, 23
AVITO_COL, DROM_COL, AUTORU_COL = 24, 25, 26
MAX_COL, YOUTUBE_COL, RUTUBE_COL, WHATSAPP_COL = 27, 28, 29, 30

FIELD_COLS = {
    "telegram": TELEGRAM_COL, "vk": VK_COL,
    "instagram": INSTAGRAM_COL, "avito": AVITO_COL, "drom": DROM_COL,
    "autoru": AUTORU_COL, "max": MAX_COL, "youtube": YOUTUBE_COL,
    "rutube": RUTUBE_COL, "whatsapp": WHATSAPP_COL,
}
# "site" обрабатывается отдельно — им может дозаполнить только 2ГИС/Яндекс
# (собственный сайт не может "найти сам себя").
ALL_FILL_FIELDS = dict(FIELD_COLS, site=SITE_COL)


def cell(row, col_1idx):
    idx = col_1idx - 1
    return row[idx].strip() if len(row) > idx and row[idx] else ""


print("Подключаюсь к Google Sheets...")
all_values = ws.get_all_values()
rows = all_values[1:]
print(f"Всего компаний: {len(rows)}\n")

filled_total = 0
checked = 0

for i, row in enumerate(rows, start=2):
    name = cell(row, NAME_COL)
    if not name:
        continue

    current = {f: cell(row, c) for f, c in ALL_FILL_FIELDS.items()}
    missing = [f for f, v in current.items() if not v]
    if not missing:
        continue

    phone = cell(row, PHONE_COL)
    key = _name_key(name)
    pd = "".join(ch for ch in phone if ch.isdigit()) if phone and phone != "-" else ""

    site = cell(row, SITE_COL)
    gis2 = cell(row, GIS2_COL)
    yandex = cell(row, YANDEX_COL)

    # Своих карточек 2ГИС/Яндекс ещё нет — пробуем один раз найти и
    # подтвердить, раз уж всё равно чего-то не хватает.
    if not gis2 or not gis2.startswith("http"):
        found_gis2, gv = find_platform_link(f"{name} отзывы 2гис", ["2gis.ru", "2gis.com"], key, pd)
        if found_gis2 and gv:
            gis2 = found_gis2
            ws.update_cell(i, GIS2_COL, gis2)
            print(f"[{i}] {name}: нашлась и подтвердилась карточка 2ГИС — сохраняю ({gis2})")
            time.sleep(1)
    if not yandex or not yandex.startswith("http"):
        found_yandex, yv = find_platform_link(f"{name} отзывы", ["yandex.ru/maps", "yandex.com/maps"], key, pd)
        if found_yandex and yv:
            yandex = found_yandex
            ws.update_cell(i, YANDEX_COL, yandex)
            print(f"[{i}] {name}: нашлась и подтвердилась карточка Яндекс.Карт — сохраняю ({yandex})")
            time.sleep(1)

    sources = []
    if site.startswith("http"):
        sources.append(("site", site))
    if gis2.startswith("http"):
        sources.append(("2gis", gis2))
    if yandex.startswith("http"):
        sources.append(("yandex", yandex))
    if not sources:
        continue

    checked += 1
    print(f"[{i}] {name}: пусто {missing}, источники: {[s[0] for s in sources]}...")
    filled = backfill_from_sources(sources, current, content_check=(key, pd))

    updates = []
    for field, col in ALL_FILL_FIELDS.items():
        if field in missing and filled.get(field):
            ws.update_cell(i, col, filled[field])
            updates.append(f"{field}={filled[field]}")
    if updates:
        filled_total += len(updates)
        print("    заполнено: " + ", ".join(updates))
    else:
        print("    ничего подходящего не нашлось")
    time.sleep(1)

print(f"\nГотово. Проверено компаний с хотя бы одним источником: {checked}, заполнено полей: {filled_total}.")
print("Теперь прогони python3 update_site.py.")
