"""
Пользователь заметил мусор в каталоге: 2ГИС у MY Avto и Winner Auto Club
вели на чужие компании (исправлено в fix_reverify_after_key_fix.py, см.
PROJECT_STATE.md). При переверификации тем скриптом обнаружился ЕЩЁ один
случай того же класса бага: "vk.com/rtrg" — это НЕ чья-то группа, а
технический пиксель ретаргетинга ВКонтакте (компании вставляют его себе
на сайт как обычный <script>/<img>) — но он оказался "подтверждён" как
VK-профиль СРАЗУ для 3 разных компаний (OTRADACARS, Jplife, ТокиДоки).

Общий принцип: реальный профиль/группа/канал/карточка на любой площадке
принадлежит РОВНО ОДНОЙ компании. Если одно и то же значение (полная
ссылка) записано у ДВУХ ИЛИ БОЛЕЕ разных компаний в одном и том же поле —
это почти наверняка не настоящие профили обеих компаний, а какой-то общий
технический артефакт (виджет, пиксель, редирект, заглушка), который
случайно прошёл проверку. Единичный точечный чёрный список (VK_RESERVED_
PATHS и т.п. в company_agent.py) ловит уже известные случаи, но не
защищает от новых, ещё не встречавшихся — а эта dedup-проверка ловит ЛЮБОЙ
повтор, независимо от того, знаем мы конкретную причину или нет.

Этот скрипт проходит по всем полям-ссылкам (yandex/google/2gis/telegram/
instagram/vk/avito/drom/autoru/max/youtube/rutube/whatsapp) у ВСЕХ
компаний (кроме MY Avto — id:1, не трогаем автоматически), находит
значения, повторяющиеся у 2+ компаний, и чистит ВСЕ повторы (не пытаемся
угадать, у какой из компаний "более правильное" совпадение — практика
показала, что чаще всего оно неверное у всех сразу, см. кейс rtrg/js/
video_ext.php/max.ru-u). После чистки ничего не подбирает взамен — сначала
нужно руками посмотреть на список, что вообще было задублировано, и
только потом решать, стоит ли перезапускать поиск.

Запуск: python3 fix_dedupe_reused_links.py
После просмотра результатов (и по желанию — python3 fix_reverify_after_key_fix.py
ещё раз, чтобы попробовать найти замену) — python3 update_site.py.
"""
import gspread
from google.oauth2.service_account import Credentials
from collections import defaultdict

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

ID_COL, NAME_COL = 1, 2
YANDEX_COL, GOOGLE_COL, GIS2_COL = 18, 20, 21
TELEGRAM_COL = 10
INSTAGRAM_COL, VK_COL = 22, 23
AVITO_COL, DROM_COL, AUTORU_COL = 24, 25, 26
MAX_COL, YOUTUBE_COL, RUTUBE_COL, WHATSAPP_COL = 27, 28, 29, 30

FIELDS = [
    ("yandex", YANDEX_COL), ("google", GOOGLE_COL), ("2gis", GIS2_COL),
    ("telegram", TELEGRAM_COL),
    ("instagram", INSTAGRAM_COL), ("vk", VK_COL),
    ("avito", AVITO_COL), ("drom", DROM_COL), ("autoru", AUTORU_COL),
    ("max", MAX_COL), ("youtube", YOUTUBE_COL), ("rutube", RUTUBE_COL),
    ("whatsapp", WHATSAPP_COL),
]


def cell(row, col_1idx):
    idx = col_1idx - 1
    return row[idx].strip() if len(row) > idx and row[idx] else ""


print("Подключаюсь к Google Sheets...")
all_values = ws.get_all_values()
rows = all_values[1:]
print(f"Всего компаний: {len(rows)}\n")

for field_name, col in FIELDS:
    by_value = defaultdict(list)
    for i, row in enumerate(rows, start=2):
        cid = cell(row, ID_COL)
        name = cell(row, NAME_COL)
        if not name or cid == "1" or name.strip().lower() == "my avto":
            continue
        val = cell(row, col)
        if val:
            by_value[val.lower()].append((i, name, val))

    for val_lower, entries in by_value.items():
        if len(entries) < 2:
            continue
        names = ", ".join(f"{name}[{i}]" for i, name, _ in entries)
        print(f"ДУБЛЬ в {field_name}: '{entries[0][2]}' встречается у {len(entries)} компаний: {names}")
        for i, name, val in entries:
            ws.update_cell(i, col, "")
            print(f"    [{i}] {name}: очищено")

print("\nГотово. Просмотри список выше — это либо общие технические артефакты")
print("(виджеты/пиксели/редиректы), либо реальная путаница, которую стоит разобрать вручную.")
print("Дальше можно прогнать python3 fix_reverify_after_key_fix.py ещё раз, чтобы")
print("попробовать найти подтверждённую замену, и python3 update_site.py.")
