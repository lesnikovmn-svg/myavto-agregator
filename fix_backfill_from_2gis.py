"""
Новая возможность (09.08.2026, по просьбе пользователя): использовать
2ГИС не только как площадку для ПРОВЕРКИ уже найденных ссылок, но и как
ИСТОЧНИК для поиска сайта/соцсетей/мессенджера компании — сама компания
обычно уже всё это указала в своём профиле 2ГИС. Триггер: пользователь
вручную нашёл настоящий сайт LikeAvto (likeavto.ru) именно так, зайдя на
карточку в 2ГИС, хотя в таблице поле site у LikeAvto было пустым.

Этот скрипт проходит по ВСЕМ уже существующим компаниям в каталоге, у
которых пустые site/telegram/vk/instagram/avito/drom/autoru — и пробует
дозаполнить эти поля из карточки 2ГИС (extract_contacts_from_2gis в
company_agent.py). Если ссылка на карточку 2ГИС (gis2) уже есть в
таблице — используем её. Если её нет, но не хватает других полей —
пробуем один раз найти и подтвердить карточку 2ГИС тем же способом, что
и find_map_links (по названию/телефону), и, если получилось, заодно
сохраняем её в колонку gis2 на будущее.

Ничего не перезаписывает — только пустые поля. Перед использованием
карточки дополнительно проверяет, что она реально про эту компанию
(название или телефон совпадают в содержимом страницы) — на случай, если
ссылка gis2 в таблице осталась от старой, менее строгой проверки.

Запуск: python3 fix_backfill_from_2gis.py
После — python3 update_site.py.
"""
import time
import gspread
from google.oauth2.service_account import Credentials
from company_agent import extract_contacts_from_2gis, fetch_site_text, _name_key, find_platform_link

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
# Добавлено 09.08.2026 вместе с правилом приоритета клика по карточке.
MAX_COL, YOUTUBE_COL, RUTUBE_COL, WHATSAPP_COL = 27, 28, 29, 30

FIELD_COLS = {
    "site": SITE_COL, "telegram": TELEGRAM_COL, "vk": VK_COL,
    "instagram": INSTAGRAM_COL, "avito": AVITO_COL, "drom": DROM_COL,
    "autoru": AUTORU_COL, "max": MAX_COL, "youtube": YOUTUBE_COL,
    "rutube": RUTUBE_COL, "whatsapp": WHATSAPP_COL,
}


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
    gis2 = cell(row, GIS2_COL)
    current = {f: cell(row, c) for f, c in FIELD_COLS.items()}
    missing = [f for f, v in current.items() if not v]
    if not missing:
        continue

    phone = cell(row, PHONE_COL)
    key = _name_key(name)
    pd = "".join(ch for ch in phone if ch.isdigit()) if phone and phone != "-" else ""

    if not gis2 or not gis2.startswith("http"):
        # Своей карточки 2ГИС ещё нет — пробуем один раз найти и
        # подтвердить (та же логика, что и в find_map_links), раз уж всё
        # равно чего-то не хватает.
        gis2, verified = find_platform_link(f"{name} отзывы 2гис", ["2gis.ru", "2gis.com"], key, pd)
        if gis2 and verified:
            ws.update_cell(i, GIS2_COL, gis2)
            print(f"[{i}] {name}: нашлась и подтвердилась карточка 2ГИС — сохраняю ({gis2})")
            time.sleep(1)
        else:
            continue

    checked += 1
    print(f"[{i}] {name}: пусто {missing}, проверяю карточку 2ГИС ({gis2})...")
    html = fetch_site_text(gis2)
    if not html:
        print("    не удалось загрузить карточку 2ГИС — пропускаю")
        time.sleep(1)
        continue

    key = _name_key(name)
    phone = cell(row, PHONE_COL)
    pd = "".join(ch for ch in phone if ch.isdigit()) if phone and phone != "-" else ""
    text_lower = html.lower()
    html_digits = "".join(ch for ch in text_lower if ch.isdigit())
    name_match = bool(key and key in text_lower)
    phone_match = bool(pd and pd in html_digits)
    if not (name_match or phone_match):
        print("    ⚠️ карточка 2ГИС не подтверждает название/телефон компании — пропускаю (нужна ручная проверка)")
        time.sleep(1)
        continue

    found = extract_contacts_from_2gis(html)
    updates = []
    for field, col in FIELD_COLS.items():
        if field in missing and found.get(field):
            ws.update_cell(i, col, found[field])
            updates.append(f"{field}={found[field]}")
    if updates:
        filled_total += len(updates)
        print("    заполнено: " + ", ".join(updates))
    else:
        print("    в карточке 2ГИС ничего подходящего не нашлось")
    time.sleep(1)

print(f"\nГотово. Проверено компаний с gis2 и пропусками: {checked}, заполнено полей: {filled_total}.")
print("Теперь прогони python3 update_site.py.")
