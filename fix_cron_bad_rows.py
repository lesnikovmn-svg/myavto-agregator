"""
Разбор 5 "мусорных" карточек, добавленных безнадзорным ночным прогоном
company_agent.py по крону (пользователь: "проверь как попали в таблицу?").
Корневые причины уже пофикшены в company_agent.py — этот скрипт чинит уже
попавшие в таблицу данные:

1. SonarBot — сервис/бот ПРОВЕРКИ авто по VIN/госномеру, не импортёр авто,
   чужая ниша. УДАЛЯЕМ. Причина попадания: текст про "авто" в изобилии,
   но это VIN-check сервис — теперь отсекается is_vin_check_service().
2. Telagon — блогерский/юридический канал, хостится на telagon.io
   (площадка аналитики telegram-каналов, не сайт компании). УДАЛЯЕМ.
   Причина: telagon.io не был в BLACKLIST — добавлен.
3. tenchat.ru-статья — агент принял статью в блог-платформе tenchat.ru за
   карточку компании, в name попал заголовок статьи целиком. УДАЛЯЕМ.
   Причина: tenchat.ru не был в BLACKLIST — добавлен.
4. ai-import.ru — РЕАЛЬНАЯ компания "АИ Авто" (подтверждено пользователем:
   "https://ai-import.ru/ реальная компания АИ авто", и og:site_name на
   самом сайте). Name испортился в мусор ("ÐÐ ÐÐ²ÑÐ¾") из-за бага
   кодировки: fetch_site_text не определял charset страницы и requests
   декодировал UTF-8-текст как ISO-8859-1. Пофикшено (apparent_encoding
   fallback, когда сервер не прислал charset). ИСПРАВЛЯЕМ name на
   "АИ Авто" — остальные поля (vk/youtube/rutube/whatsapp и т.д.) уже
   верные, не трогаем.
5. autoshoot.ru — РЕАЛЬНАЯ компания, но name стал рекламным слоганом
   ("Подбор, покупка и доставка авто из Европы под ключ") вместо
   названия — на сайте нет og:site_name, отдельного бренда кроме домена
   не нашлось. Пофикшено на будущее (is_probably_tagline +
   clean_name_from_title теперь возвращает "" для таких заголовков →
   используется имя по домену). ИСПРАВЛЯЕМ name на "AutoShoot".

Запуск: python3 fix_cron_bad_rows.py
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

NAME_COL, SITE_COL = 2, 12


def cell(row, col_1idx):
    idx = col_1idx - 1
    return row[idx].strip() if len(row) > idx and row[idx] else ""


all_values = ws.get_all_values()
rows = all_values[1:]

to_delete = []       # (row_i, name, reason)
to_fix_name = {}     # row_i -> (new_name, old_name)

for i, row in enumerate(rows, start=2):
    name = cell(row, NAME_COL)
    site = cell(row, SITE_COL).lower()
    name_lower = name.lower()

    if "sonarbot" in name_lower or "sonarbot" in site:
        to_delete.append((i, name, "SonarBot — VIN-check бот, чужая ниша"))
    elif "telagon.io" in site or "telagon" in name_lower:
        to_delete.append((i, name, "Telagon — блогерский канал на telagon.io"))
    elif "tenchat.ru" in site:
        to_delete.append((i, name, "tenchat.ru — статья в блоге, не карточка компании"))
    elif "ai-import.ru" in site:
        to_fix_name[i] = ("АИ Авто", name)
    elif "autoshoot.ru" in site:
        to_fix_name[i] = ("AutoShoot", name)

if not to_delete and not to_fix_name:
    print("Ничего не нашёл — похоже, строки уже поправлены или сайты/названия изменились.")
else:
    for i, (new_name, old_name) in to_fix_name.items():
        ws.update_cell(i, NAME_COL, new_name)
        print(f"[{i}] name: '{old_name}' -> '{new_name}'")

    # удаляем снизу вверх, чтобы номера строк не съезжали при удалении
    for i, name, reason in sorted(to_delete, key=lambda x: -x[0]):
        ws.delete_rows(i)
        print(f"[{i}] удалено: {name} — {reason}")

print("\nТеперь прогони python3 update_site.py.")
