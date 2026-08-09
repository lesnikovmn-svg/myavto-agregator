"""
Полная повторная проверка ВСЕХ уже сохранённых ссылок-площадок
(yandex/google/2gis/instagram/vk/avito/drom/autoru) по всему каталогу —
не по формату URL (это уже делал fix_reverify_all_links.py), а по
РЕАЛЬНОМУ СОДЕРЖИМОМУ страницы назначения (fetch_page_signal_text из
company_agent.py — свежий фикс 09.08.2026).

Почему это нужно: на нескольких живых примерах (Winner Auto Club, Artalex
Group, Primorye China Export — все с подтверждением от пользователя,
переходил по ссылкам лично) выяснилось, что ссылка может быть технически
валидной карточкой/профилем (правильный формат URL, не страница поиска и
не отдельный пост), но вести на СОВСЕМ ДРУГУЮ компанию — сниппет из DDG
совпал по случайному общему слову, хотя реальная страница назначения
про другую фирму.

Логика: для каждого непустого поля-ссылки — фетчим страницу назначения,
ищем в её содержимом (og:title/og:description + весь текст) хотя бы
первое слово названия компании (или телефон, если есть). Не нашли — поле
считается неподтверждённым, чистим его. Дальше пробуем найти
подтверждённую замену той же функцией, что теперь используется при
поиске новых компаний (find_map_links/find_social_links/
find_marketplace_links) — она уже делает такую проверку "из коробки".

Долгий скрипт — на каждую компанию до 8 фетчей чужих страниц плюс паузы,
может занять 10-20+ минут на ~58 компаний. Ничего не удаляет из каталога,
только чистит/подтверждает отдельные ссылки-кнопки.

Запуск: python3 fix_full_content_reverify.py
После — python3 update_site.py.
"""
import time
import gspread
from google.oauth2.service_account import Credentials
from company_agent import (
    _name_key, fetch_page_signal_text, is_real_profile_url,
    find_map_links, find_social_links, find_marketplace_links, fetch_site_text,
)

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

NAME_COL, PHONE_COL, SITE_COL = 2, 11, 12
YANDEX_COL, GOOGLE_COL, GIS2_COL = 18, 20, 21
INSTAGRAM_COL, VK_COL = 22, 23
AVITO_COL, DROM_COL, AUTORU_COL = 24, 25, 26

FIELDS = [
    ("yandex", YANDEX_COL), ("google", GOOGLE_COL), ("2gis", GIS2_COL),
    ("instagram", INSTAGRAM_COL), ("vk", VK_COL),
    ("avito", AVITO_COL), ("drom", DROM_COL), ("autoru", AUTORU_COL),
]


def cell(row, col_1idx):
    idx = col_1idx - 1
    return row[idx].strip() if len(row) > idx and row[idx] else ""


def content_confirms(link, key, phone_digits):
    if not is_real_profile_url(link.lower()):
        return False
    text = fetch_page_signal_text(link)
    if not text:
        return False
    if key and key in text:
        return True
    if phone_digits and phone_digits in "".join(ch for ch in text if ch.isdigit()):
        return True
    return False


print("Подключаюсь к Google Sheets...")
all_values = ws.get_all_values()
rows = all_values[1:]
print(f"Всего компаний: {len(rows)}\n")

cleared_total = 0
refound_total = 0

for i, row in enumerate(rows, start=2):
    name = cell(row, NAME_COL)
    if not name:
        continue
    phone = cell(row, PHONE_COL)
    site = cell(row, SITE_COL)
    key = _name_key(name)
    pd = "".join(ch for ch in phone if ch.isdigit()) if phone and phone != "-" else ""

    cleared_here = []
    for field_name, col in FIELDS:
        val = cell(row, col)
        if not val:
            continue
        if not content_confirms(val, key, pd):
            ws.update_cell(i, col, "")
            cleared_here.append(field_name)
            cleared_total += 1
            print(f"[{i}] {name}: не подтвердилось содержимым — чищу {field_name} ({val})")
        time.sleep(0.5)

    if not cleared_here:
        continue

    need_maps = any(f in ("yandex", "google", "2gis") for f in cleared_here)
    need_social = any(f in ("instagram", "vk") for f in cleared_here)
    need_market = any(f in ("avito", "drom", "autoru") for f in cleared_here)

    if need_maps:
        y2, g2, gi2, _ = find_map_links(name, phone)
        for field_name, col, val in (("yandex", YANDEX_COL, y2), ("google", GOOGLE_COL, g2), ("2gis", GIS2_COL, gi2)):
            if field_name in cleared_here and val:
                ws.update_cell(i, col, val)
                print(f"    новый {field_name}: {val}")
                refound_total += 1
        time.sleep(1)

    if need_social:
        site_text = fetch_site_text(site) if site.startswith("http") else ""
        i2, v2, _ = find_social_links(name, site_text, phone)
        for field_name, col, val in (("instagram", INSTAGRAM_COL, i2), ("vk", VK_COL, v2)):
            if field_name in cleared_here and val:
                ws.update_cell(i, col, val)
                print(f"    новый {field_name}: {val}")
                refound_total += 1
        time.sleep(1)

    if need_market:
        a2, d2, ar2, _ = find_marketplace_links(name, phone)
        for field_name, col, val in (("avito", AVITO_COL, a2), ("drom", DROM_COL, d2), ("autoru", AUTORU_COL, ar2)):
            if field_name in cleared_here and val:
                ws.update_cell(i, col, val)
                print(f"    новый {field_name}: {val}")
                refound_total += 1
        time.sleep(1)

print(f"\nГотово. Очищено полей (не подтвердились содержимым): {cleared_total}, "
      f"найдено подтверждённых замен: {refound_total}.")
print("Теперь прогони python3 update_site.py.")
