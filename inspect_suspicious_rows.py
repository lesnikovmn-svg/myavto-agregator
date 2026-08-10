"""
Только ЧИТАЕТ, ничего не пишет. По отчёту dryrun_reverify_sites.py
(10.08.2026, прогон по всей базе) нашлось несколько подозрительных строк —
этот скрипт печатает ВСЕ их поля целиком, чтобы решить: удалить (не
компания вообще), поправить (реальная компания, но поле site битое) или
это дубль уже существующей карточки.

Строки и почему подозрительны:
  5  Winner Auto Club — site ведёт на langame.ru (компьютерный клуб в
     Челябинске) — совсем чужой бизнес, поле явно битое.
 50  "Авто из Европы / Авто Импорт" — site telegram-превью, og:site_name
     страницы = "Telegram" (не бренд, а название платформы).
 59  "AutoImport Russia" — site telegram.menu (зеркало-каталог, не сайт).
 60  "Telegram Dialogs" — site telegram-dialogs.ru (зеркало-каталог);
     само название "Telegram Dialogs" — это бренд ЗЕРКАЛА, не компании;
     канал в пути (@auto_import_cars_rus) подозрительно похож на уже
     существующую карточку "Авто из Европы / Авто Импорт ПРО" (fix
     делали 09-10.08.2026, fix_auto_import_cars_rus.py) — возможен дубль.
 65  "Autonews" — site autonews.ru/news/... — это новостная СТАТЬЯ на
     крупном автопортале, не компания.
 66  "Долгов Авто - Машины из Кореи,Японии,Китая." — site telegram.me/
     dolgov_auto/22193 — ссылка на КОНКРЕТНОЕ СООБЩЕНИЕ в канале, не сам
     канал; og:site_name = "Telegram".
 74  "TeleFinder — Каталог Telegram-каналов" — само название говорит само
     за себя, это каталог, не компания.
 75  "Otzovik" — site otzovik.com/reviews/... — страница отзыва об одном
     телеграм-канале на отзовике, не сайт компании.
 76  "Ссылка на Telegram-канал..." — site tgramlink.com/... — каталог
     ссылок на телеграм-каналы, не компания.

Запуск: python3 inspect_suspicious_rows.py
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

HEADERS = ["id","name","rating","reviews","years","delivered","description","directions",
    "tags","telegram","phone","site","manager","region","featured","avatar","color",
    "yandex","inn","google","gis2","instagram","vk","avito","drom","autoru","max",
    "youtube","rutube","whatsapp"]

TARGET_ROWS = [5, 50, 59, 60, 65, 66, 74, 75, 76]

all_values = ws.get_all_values()

for row_i in TARGET_ROWS:
    if row_i - 1 >= len(all_values):
        print(f"[{row_i}] строки нет (таблица короче) — пропускаю")
        continue
    row = all_values[row_i - 1]
    print(f"\n{'='*70}\n[{row_i}]")
    for idx, header in enumerate(HEADERS):
        val = row[idx] if idx < len(row) else ""
        if val:
            print(f"  {header}: {val}")
