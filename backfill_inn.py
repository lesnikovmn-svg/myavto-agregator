"""
Разовый скрипт: пытается найти ИНН у компаний, которые уже есть в таблице,
но были добавлены ДО того, как company_agent.py научился искать ИНН
(те самые первые ~40). Не трогает компании, у которых ИНН уже заполнен.

Логика та же, что и в основном агенте: берём сайт компании из колонки
"site", скачиваем текст страницы, ищем "ИНН <10 или 12 цифр>". Если сайта
нет (только Telegram) — компанию просто пропускаем, взять ИНН неоткуда.

Запуск: python3 backfill_inn.py
После — как обычно: python3 update_site.py, чтобы подтянуть ЕГРЮЛ-проверку
для всех вновь найденных ИНН.
"""
import time
import gspread
from google.oauth2.service_account import Credentials
from company_agent import extract_inn, fetch_site_text

config = {}
with open("agent_config.env") as f:
    for line in f:
        if "=" in line:
            k, v = line.strip().split("=", 1)
            config[k] = v

SHEET_ID = config["SHEET_ID"]

# Позиции колонок в таблице (1-индексация, как у gspread update_cell).
# Порядок совпадает со схемой в company_agent.py/update_site.py:
# id,name,rating,reviews,years,delivered,description,directions,tags,
# telegram,phone,site,manager,region,featured,avatar,color,yandex,inn
SITE_COL = 12
INN_COL = 19


def connect_sheets():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).sheet1


def run():
    print("Подключаюсь к Google Sheets...")
    ws = connect_sheets()
    rows = ws.get_all_values()
    print(f"Всего компаний в таблице: {len(rows) - 1}")

    checked = 0
    found = 0
    for i, row in enumerate(rows[1:], start=2):  # строка 1 — заголовки
        name = row[1] if len(row) > 1 else ""
        site = row[SITE_COL - 1] if len(row) >= SITE_COL else ""
        inn = row[INN_COL - 1] if len(row) >= INN_COL else ""

        if not name:
            continue
        if inn:
            continue  # ИНН уже есть — не трогаем
        if not site or not site.startswith("http"):
            continue  # брать ИНН неоткуда (только Telegram/пусто)

        checked += 1
        print(f"[{checked}] {name} — {site}")
        text = fetch_site_text(site)
        found_inn = extract_inn(text) if text else ""
        if found_inn:
            ws.update_cell(i, INN_COL, found_inn)
            print(f"    ИНН найден: {found_inn}")
            found += 1
        else:
            print("    ИНН на сайте не найден")
        time.sleep(1.5)  # не долбим чужие сайты слишком часто

    print(f"\nГотово. Проверено сайтов: {checked}, найдено ИНН: {found}")
    print("Теперь прогони python3 update_site.py — он проверит найденные ИНН по ЕГРЮЛ/DaData.")


if __name__ == "__main__":
    run()
