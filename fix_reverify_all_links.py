"""
Проходит по ВСЕМ компаниям в таблице и:

1. Чистит заведомо фейковые ссылки на площадках (yandex/google/2gis/vk) —
   те, что технически лежат в нужном поле, но по факту не карточка
   компании: страницы ПОИСКА ("yandex.ru/maps/search/...") — похоже,
   наследие старой версии сайта до автоматизации поиска, где кнопка
   Яндекс всегда вела на конструированный поисковый URL, а не на
   найденную карточку; и отдельные посты/видео VK ("vk.com/wall-...",
   "vk.com/video-...") вместо профиля компании. Нашли на живых примерах
   09.08.2026 (ТамСямAUTO, Primorye China Export, Winner Auto Club,
   Artalex Group) — у Primorye China Export 2ГИС-ссылка вообще вела на
   совершенно другую компанию (B2B-China, тот же branch_id).

2. Для очищенных (и вообще всех пустых) полей — пробует найти замену
   через find_map_links/find_social_links/find_marketplace_links, но
   теперь эти функции возвращают ссылку, ТОЛЬКО если она реально
   подтвердилась (см. фикс is_real_profile_url + find_platform_link в
   company_agent.py) — поэтому новый бэкафилл не принесёт тех же самых
   проблем повторно. Если подтверждённой замены не нашлось — поле
   остаётся пустым, кнопка на сайте просто не будет показываться
   (честнее, чем вести на не ту компанию).

Ничего не трогает у полей, где ссылка выглядит нормально (не мусорного
формата) — их НЕ переспрашиваем даже без подтверждения задним числом,
чтобы не тратить время и не рисковать заменить рабочую ссылку на пустую
из-за случайного сбоя поиска. Если хочешь полную ре-верификацию вообще
всех ссылок — это отдельная, более медленная задача.

Запуск: python3 fix_reverify_all_links.py
После — python3 update_site.py.
"""
import re
import time
import gspread
from google.oauth2.service_account import Credentials
from company_agent import (
    find_map_links, find_social_links, find_marketplace_links,
    is_real_profile_url, fetch_site_text,
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


def cell(row, col_1idx):
    idx = col_1idx - 1
    return row[idx] if len(row) > idx else ""


def is_bad(link):
    if not link:
        return False
    return not is_real_profile_url(link.lower())


print("Подключаюсь к Google Sheets...")
all_values = ws.get_all_values()
rows = all_values[1:]
print(f"Всего компаний: {len(rows)}")

cleaned = 0
refound = 0

for i, row in enumerate(rows, start=2):
    name = cell(row, NAME_COL)
    if not name:
        continue

    phone = cell(row, PHONE_COL)
    site = cell(row, SITE_COL)
    yandex = cell(row, YANDEX_COL)
    google = cell(row, GOOGLE_COL)
    gis2 = cell(row, GIS2_COL)
    insta = cell(row, INSTAGRAM_COL)
    vk = cell(row, VK_COL)
    avito = cell(row, AVITO_COL)
    drom = cell(row, DROM_COL)
    autoru = cell(row, AUTORU_COL)

    bad_fields = []
    if is_bad(yandex):
        bad_fields.append(("yandex", YANDEX_COL))
        yandex = ""
    if is_bad(google):
        bad_fields.append(("google", GOOGLE_COL))
        google = ""
    if is_bad(gis2):
        bad_fields.append(("2gis", GIS2_COL))
        gis2 = ""
    if is_bad(vk):
        bad_fields.append(("vk", VK_COL))
        vk = ""

    if not bad_fields:
        continue

    print(f"[{i}] {name}: чищу {', '.join(f for f, _ in bad_fields)}")
    for _, col in bad_fields:
        ws.update_cell(i, col, "")
        cleaned += 1
    time.sleep(0.3)

    # Пробуем найти подтверждённую замену для того, что почистили.
    need_maps = any(f in ("yandex", "google", "2gis") for f, _ in bad_fields)
    need_vk = any(f == "vk" for f, _ in bad_fields)

    if need_maps:
        y2, g2, gi2, _ = find_map_links(name, phone)
        if not yandex and y2:
            ws.update_cell(i, YANDEX_COL, y2)
            print(f"    новый yandex: {y2}")
            refound += 1
        if not google and g2:
            ws.update_cell(i, GOOGLE_COL, g2)
            print(f"    новый google: {g2}")
            refound += 1
        if not gis2 and gi2:
            ws.update_cell(i, GIS2_COL, gi2)
            print(f"    новый 2gis: {gi2}")
            refound += 1
        time.sleep(1)

    if need_vk:
        site_text = fetch_site_text(site) if site.startswith("http") else ""
        _, v2, _ = find_social_links(name, site_text, phone)
        if v2:
            ws.update_cell(i, VK_COL, v2)
            print(f"    новый vk: {v2}")
            refound += 1
        time.sleep(1)

print(f"\nГотово. Очищено полей: {cleaned}, найдено подтверждённых замен: {refound}.")
print("Теперь прогони python3 update_site.py.")
