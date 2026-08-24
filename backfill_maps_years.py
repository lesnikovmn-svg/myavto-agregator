"""
Разовый скрипт: прогоняет уже существующие в таблице компании через новую
схему — ищет карточки на Google Maps/2ГИС (и Яндексе, если там пусто) и,
если у компании нет ИНН, пробует вытащить реальный стаж работы из описания
и текста сайта вместо дефолтной "1" год.

Ничего не перезаписывает поверх уже заполненных вручную полей — только
дополняет пустые.

Запуск: python3 backfill_maps_years.py
После — python3 update_site.py, чтобы пересобрать сайт с новыми данными.

Может занять несколько минут — на каждую компанию до 3 поисковых запросов
(Яндекс/Google/2ГИС) плюс пауза между ними, чтобы не долбить DuckDuckGo.
"""

import time
import gspread
from google.oauth2.service_account import Credentials
from company_agent import (
    find_map_links,
    find_social_links,
    find_marketplace_links,
    extract_years_experience,
    fetch_site_text,
)

config = {}
with open("agent_config.env") as f:
    for line in f:
        if "=" in line:
            k, v = line.strip().split("=", 1)
            config[k] = v

SHEET_ID = config["SHEET_ID"]

# id,name,rating,reviews,years,delivered,description,directions,tags,
# telegram,phone,site,manager,region,featured,avatar,color,yandex,inn,
# google,gis2,instagram,vk,avito,drom,autoru
NAME_COL = 2
YEARS_COL = 5
DESC_COL = 7
PHONE_COL = 11
SITE_COL = 12
YANDEX_COL = 18
INN_COL = 19
GOOGLE_COL = 20
GIS2_COL = 21
INSTAGRAM_COL = 22
VK_COL = 23
AVITO_COL = 24
DROM_COL = 25
AUTORU_COL = 26


def connect_sheets():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).sheet1


def cell(row, col_1idx):
    idx = col_1idx - 1
    return row[idx] if len(row) > idx else ""


def run():
    print("Подключаюсь к Google Sheets...")
    ws = connect_sheets()
    rows = ws.get_all_values()
    print(f"Всего компаний: {len(rows) - 1}")

    updated_maps = 0
    updated_years = 0
    updated_social = 0
    updated_market = 0
    for i, row in enumerate(rows[1:], start=2):
        name = cell(row, NAME_COL)
        if not name:
            continue

        yandex = cell(row, YANDEX_COL)
        google = cell(row, GOOGLE_COL)
        gis2 = cell(row, GIS2_COL)
        inn = cell(row, INN_COL)
        years = cell(row, YEARS_COL)
        site = cell(row, SITE_COL)
        desc = cell(row, DESC_COL)
        insta = cell(row, INSTAGRAM_COL)
        vk = cell(row, VK_COL)
        phone = cell(row, PHONE_COL)
        avito = cell(row, AVITO_COL)
        drom = cell(row, DROM_COL)
        autoru = cell(row, AUTORU_COL)

        print(f"[{i - 1}] {name}")

        # 1) Карты — ищем только то, чего ещё нет, старое не трогаем.
        if not (yandex and google and gis2):
            try:
                y2, g2, gi2, _ = find_map_links(name, phone)
            except Exception as e:
                print(f"    ошибка поиска карт: {e}")
                y2, g2, gi2 = "", "", ""
            if not yandex and y2:
                ws.update_cell(i, YANDEX_COL, y2)
                yandex = y2
            if not google and g2:
                ws.update_cell(i, GOOGLE_COL, g2)
                google = g2
            if not gis2 and gi2:
                ws.update_cell(i, GIS2_COL, gi2)
                gis2 = gi2
            if y2 or g2 or gi2:
                updated_maps += 1
                print(
                    f"    карты: yandex={'✓' if y2 else '-'} google={'✓' if g2 else '-'} 2gis={'✓' if gi2 else '-'}"
                )

        # 1б) Instagram/VK — тоже только то, чего ещё нет.
        if not (insta and vk):
            site_text_for_social = ""
            if site and site.startswith("http"):
                site_text_for_social = fetch_site_text(site)
            try:
                i2, v2, _ = find_social_links(
                    name, (desc or "") + " " + site_text_for_social, phone
                )
            except Exception as e:
                print(f"    ошибка поиска соцсетей: {e}")
                i2, v2 = "", ""
            if not insta and i2:
                ws.update_cell(i, INSTAGRAM_COL, i2)
            if not vk and v2:
                ws.update_cell(i, VK_COL, v2)
            if i2 or v2:
                updated_social += 1
                print(f"    соцсети: instagram={'✓' if i2 else '-'} vk={'✓' if v2 else '-'}")

        # 1в) Авито/Дром/Авто.ру — тоже только то, чего ещё нет.
        if not (avito and drom and autoru):
            try:
                a2, d2, ar2, _ = find_marketplace_links(name, phone)
            except Exception as e:
                print(f"    ошибка поиска маркетплейсов: {e}")
                a2, d2, ar2 = "", "", ""
            if not avito and a2:
                ws.update_cell(i, AVITO_COL, a2)
            if not drom and d2:
                ws.update_cell(i, DROM_COL, d2)
            if not autoru and ar2:
                ws.update_cell(i, AUTORU_COL, ar2)
            if a2 or d2 or ar2:
                updated_market += 1
                print(
                    f"    маркетплейсы: avito={'✓' if a2 else '-'} drom={'✓' if d2 else '-'} auto.ru={'✓' if ar2 else '-'}"
                )

        # 2) Стаж — только если ИНН нет (и значит, год по ЕГРЮЛ не узнать)
        # и в years сейчас похоже на дефолтную заглушку.
        if not inn and (not years or years == "1"):
            text = desc
            if site and site.startswith("http"):
                site_text = fetch_site_text(site)
                if site_text:
                    text += " " + site_text
            found_years = extract_years_experience(text)
            if found_years:
                ws.update_cell(i, YEARS_COL, str(found_years))
                updated_years += 1
                print(f"    стаж найден: {found_years} лет")

        time.sleep(1)

    print(
        f"\nГотово. Карты дополнены у {updated_maps}, соцсети — у {updated_social}, маркетплейсы — у {updated_market}, стаж — у {updated_years}."
    )
    print("Теперь прогони python3 update_site.py, чтобы пересобрать сайт с новыми данными.")


if __name__ == "__main__":
    run()
