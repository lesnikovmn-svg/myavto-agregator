"""
Разбор 9 подозрительных строк, найденных dryrun_reverify_sites.py
(10.08.2026, прогон по всей базе) и уточнённых inspect_suspicious_rows.py.
Корневые причины уже пофикшены в company_agent.py:
- BLACKLIST дополнен зеркалами/каталогами Telegram-каналов (telegram.menu,
  telegram-dialogs.ru, tele-finder.com, tgramlink.com, otzovik.com,
  autonews.ru).
- extract_brand_from_site больше не берёт og:site_name, если это буквально
  "Telegram" (общее название платформы, не бренд).
- _matches_domain_filter — главный найденный баг: find_platform_link
  считал совпадением ЛЮБОЙ домен, СОДЕРЖАЩИЙ подстроку "auto.ru" (например
  "intercityauto.ru", "dolgov-auto.ru" — оба НЕ являются auto.ru, просто
  оканчиваются на те же буквы). Теперь матчинг по границе поддомена.

Этот скрипт чинит уже попавшие в таблицу данные:

УДАЛЯЕМ (не компании / дубли, а мусор с зеркал-каталогов Telegram-каналов):
  - "Telegram Dialogs" (site: telegram-dialogs.ru) — telegram-хэндл
    "auto_import_cars_rus" ПОЛНОСТЬЮ совпадает с уже существующей в
    таблице карточкой "Авто из Европы / Авто Импорт ПРО" (её чинили
    09-10.08.2026, fix_auto_import_cars_rus.py) — чистый дубль-зеркало.
  - "Autonews" (site: autonews.ru/news/...) — новостная статья на крупном
    автопортале, не компания; инстаграм/вк/макс в карточке — это
    собственные соцсети РБК/Autonews, не импортёра авто.
  - "TeleFinder — Каталог Telegram-каналов" — сам каталог telegram-каналов.
  - "Otzovik" (site: otzovik.com) — страница отзыва об одном канале.
  - строка с site tgramlink.com — каталог ссылок на telegram-каналы.

ПРАВИМ (реальные компании, но конкретные поля битые):
  - Winner Auto Club — site вёл на langame.ru (компьютерный клуб в
    Челябинске, совсем другой бизнес) — чистим. phone начинался с "="
    (артефакт), убираем лишний символ.
  - "Авто из Европы / Авто Импорт" (site: t.me/auto_import_cars_ru, БЕЗ
    "s" на конце — судя по всему, отдельный от "...ПРО" канал, тот НЕ
    трогаем) — site вообще не должен был быть telegram-ссылкой (это поле
    для сайта, telegram уже отдельно в своей колонке) — чистим. drom вёл
    на GitHub-репозиторий (явно не карточка Дром) — чистим. autoru вёл на
    intercityauto.ru — чужой домен, попал из-за бага _matches_domain_filter
    (см. выше) — чистим.
  - "Долгов Авто" — site вёл на telegram.me/dolgov_auto/22193 (ссылка на
    КОНКРЕТНОЕ сообщение в канале, не сайт) — чистим. При этом поле autoru
    содержало "https://dolgov-auto.ru/" — похоже, это НАСТОЯЩИЙ сайт
    компании (совпадает с названием), просто попал не в ту колонку из-за
    того же бага — ПЕРЕНОСИМ его в site, а autoru очищаем.
  - "AutoImport Russia" (site: telegram.menu/@autoimportrussiarf) — чистим
    ТОЛЬКО site (зеркало, не сайт). inn/gis2/instagram/youtube в этой
    карточке НЕ трогаем — не факт, что они тоже битые (могли найтись
    независимо), но и не факт, что верные — стоит перепроверить вручную
    отдельно, скрипт только печатает предупреждение.

Запуск: python3 fix_dryrun_findings_batch1.py
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

NAME_COL, PHONE_COL, SITE_COL = 2, 11, 12
DROM_COL, AUTORU_COL = 25, 26


def cell(row, col_1idx):
    idx = col_1idx - 1
    return row[idx].strip() if len(row) > idx and row[idx] else ""


all_values = ws.get_all_values()
rows = all_values[1:]

DELETE_SITE_MARKERS = ["telegram-dialogs.ru", "autonews.ru", "tele-finder.com",
    "otzovik.com", "tgramlink.com"]

to_delete = []
fixed_count = 0

for i, row in enumerate(rows, start=2):
    name = cell(row, NAME_COL)
    site = cell(row, SITE_COL).lower()
    phone = cell(row, PHONE_COL)

    if any(m in site for m in DELETE_SITE_MARKERS):
        to_delete.append((i, name, site))
        continue

    if "langame.ru" in site:
        ws.update_cell(i, SITE_COL, "")
        print(f"[{i}] {name}: очищен site (langame.ru — чужой бизнес)")
        fixed_count += 1
        if phone.startswith("="):
            new_phone = phone.lstrip("=").strip()
            ws.update_cell(i, PHONE_COL, new_phone)
            print(f"[{i}] {name}: phone '{phone}' -> '{new_phone}'")
        continue

    if site == "https://t.me/auto_import_cars_ru":
        ws.update_cell(i, SITE_COL, "")
        drom_val = cell(row, DROM_COL)
        autoru_val = cell(row, AUTORU_COL)
        if drom_val:
            ws.update_cell(i, DROM_COL, "")
        if autoru_val:
            ws.update_cell(i, AUTORU_COL, "")
        print(f"[{i}] {name}: очищены site (был t.me-ссылкой), "
              f"drom ('{drom_val}' — GitHub, не Дром), autoru ('{autoru_val}' — чужой домен)")
        fixed_count += 1
        continue

    if "telegram.me/dolgov_auto" in site:
        autoru_val = cell(row, AUTORU_COL)
        if autoru_val and "dolgov-auto.ru" in autoru_val.lower():
            ws.update_cell(i, SITE_COL, autoru_val)
            ws.update_cell(i, AUTORU_COL, "")
            print(f"[{i}] {name}: site '{site}' -> '{autoru_val}' (похоже, настоящий сайт, "
                  f"просто был не в той колонке), autoru очищен")
        else:
            ws.update_cell(i, SITE_COL, "")
            print(f"[{i}] {name}: очищен site (ссылка на сообщение в канале, не сайт)")
        fixed_count += 1
        continue

    if "telegram.menu" in site:
        ws.update_cell(i, SITE_COL, "")
        print(f"[{i}] {name}: очищен site (telegram.menu — зеркало, не сайт компании). "
              f"⚠️ inn/gis2/instagram/youtube этой карточки НЕ трогал — перепроверь вручную.")
        fixed_count += 1
        continue

# Удаляем снизу вверх, чтобы номера строк не съезжали.
for i, name, site in sorted(to_delete, key=lambda x: -x[0]):
    ws.delete_rows(i)
    print(f"[{i}] удалено: {name} ({site})")

print(f"\nГотово. Исправлено карточек: {fixed_count}, удалено: {len(to_delete)}.")
print("Теперь прогони python3 update_site.py.")
