"""
⚠️ ПЕРЕД ЗАПУСКОМ: поставь именованную версию в Google Sheets — Файл →
История версий → Назвать текущую версию → «до fix_new_batch_18» →
Сохранить (см. PROJECT_STATE.md, "Конвенция: именованная версия перед
fix-скриптами" — так можно откатиться в один клик).

Разбор ~18 новых строк, добавленных последним прогоном company_agent.py
(пользователь спросил "проверь добавились 15 компаний... все ли?").
Решения по каждой — от пользователя, вживую в диалоге 10.08.2026.
Корневые причины трёх из этих багов уже пофикшены в company_agent.py:
BLACKLIST дополнен (telno.ru/telderi.ru/telegramcat.blog/ixbt.com/
vagvin.ru), site больше не может стать telegram-ссылкой (t.me/telegram.me
исключены явно), дедуп по домену теперь понимает поддомены
(base_domain() схлопывает spb.westmotors.ru -> westmotors.ru).

УДАЛЯЕМ (мусор/не компании/дубли):
  - IXBT.com — новостная статья на техпортале, не компания.
  - "Telegram каналы" (telno.ru) — каталог telegram-каналов.
  - "Готовый бизнес: ...VIN..." (telderi.ru) — маркетплейс продажи бота,
    не сама компания.
  - VagVin (vagvin.ru) — сервис расшифровки VIN, не импортёр.
  - TELEGRAMCAT.BLOG — блог-каталог ботов проверки авто.
  - "Telegram – a new era of messaging" (t.me/s/auto_import_cars_ru) —
    дубль уже существующего канала (тот же handle встречается в других
    карточках каталога под нормальными именами).
  - Spb.Westmotors (spb.westmotors.ru) — питерский поддомен уже
    существующего Westmotors (westmotors.ru).
  - aaajapan (site ru.aaajapan.com/auctions) — по решению пользователя:
    это аукционная площадка, не компания-импортёр, удалить.

ПРАВИМ:
  - "Прим Автодилер | Заказ авто" -> имя "Прим Автодилер", site (был
    telegram.me/prim_autodealer — ссылка-мессенджер попала не в ту
    колонку, telegram уже верно указан отдельно) очищаем.
  - "Аукционы Японии Онлайн" -> переименовать в "Japan Star" (по
    решению пользователя, соответствует домену jpstar.ru).
  - "СЕВЕР АВТО" -> оставляем, чистим чужую 2ГИС-ссылку
    (2gis.ru/spb/firm/70000001066977769 — Питер, а сама компания
    северодвинская/дальневосточная judging по домену severdv.online,
    явно не её карточка).
  - "Emirate Cars" -> оставляем, регион помечаем "Баку, Азербайджан
    (офис)" — по данным пользователя компания физически в Баку.
  - "West-Motors.De" -> оставляем, регион помечаем "Берлин, Германия
    (офис)" — по данным пользователя.

НЕ ТРОГАЕМ (пока не было решения пользователя): China.Sferacar,
ES Transit (похож на дубль Es-Transit, но домен другой — нужно уточнить
отдельно), Avtoban.Org / JpAuc.ru / РОЛЬФ (пользователь уже сказал
"оставляем" — эти и так не трогаем, ничего чинить не нужно).

Запуск: python3 fix_new_batch_18.py
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

NAME_COL, SITE_COL, REGION_COL = 2, 12, 14
GIS2_COL = 21


def cell(row, col_1idx):
    idx = col_1idx - 1
    return row[idx].strip() if len(row) > idx and row[idx] else ""


all_values = ws.get_all_values()
rows = all_values[1:]

DELETE_SITE_MARKERS = [
    "ixbt.com", "telno.ru", "telderi.ru", "vagvin.ru", "telegramcat.blog",
    "t.me/s/auto_import_cars_ru", "spb.westmotors.ru", "ru.aaajapan.com/auctions",
]

to_delete = []
fixed_count = 0

for i, row in enumerate(rows, start=2):
    name = cell(row, NAME_COL)
    site = cell(row, SITE_COL).lower()
    gis2 = cell(row, GIS2_COL)

    if any(m in site for m in DELETE_SITE_MARKERS):
        to_delete.append((i, name, site))
        continue

    if site == "https://telegram.me/prim_autodealer":
        ws.update_cell(i, NAME_COL, "Прим Автодилер")
        ws.update_cell(i, SITE_COL, "")
        print(f"[{i}] '{name}' -> name='Прим Автодилер', site очищен (был telegram-ссылкой)")
        fixed_count += 1
        continue

    if "jpstar.ru/auktsiony" in site:
        ws.update_cell(i, NAME_COL, "Japan Star")
        print(f"[{i}] '{name}' -> name='Japan Star'")
        fixed_count += 1
        continue

    if "severdv.online" in site:
        if gis2:
            ws.update_cell(i, GIS2_COL, "")
            print(f"[{i}] '{name}': очищен gis2 ('{gis2}' — чужая карточка, Питер vs Дальний Восток)")
            fixed_count += 1
        continue

    if "emirate-cars.com" in site:
        old_region = cell(row, REGION_COL)
        ws.update_cell(i, REGION_COL, "Баку, Азербайджан (офис)")
        print(f"[{i}] '{name}': region '{old_region}' -> 'Баку, Азербайджан (офис)'")
        fixed_count += 1
        continue

    if "west-motors.de" in site:
        old_region = cell(row, REGION_COL)
        ws.update_cell(i, REGION_COL, "Берлин, Германия (офис)")
        print(f"[{i}] '{name}': region '{old_region}' -> 'Берлин, Германия (офис)'")
        fixed_count += 1
        continue

# Удаляем снизу вверх, чтобы номера строк не съезжали.
for i, name, site in sorted(to_delete, key=lambda x: -x[0]):
    ws.delete_rows(i)
    print(f"[{i}] удалено: {name} ({site})")

print(f"\nГотово. Исправлено карточек: {fixed_count}, удалено: {len(to_delete)}.")
print("Не трогал (нет решения пользователя): China.Sferacar, ES Transit.")
print("Теперь прогони python3 update_site.py.")
