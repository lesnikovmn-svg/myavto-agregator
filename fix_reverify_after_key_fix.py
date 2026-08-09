"""
Пользователь сообщил: после прогона fix_backfill_from_sources.py в
каталоге "добавилось мусора" — у MY Avto (id:1, КОМПАНИЯ САМОГО АВТОРА!)
и у Winner Auto Club 2ГИС снова ведёт на ДРУГУЮ компанию. Пользователь
лично проверил и подтвердил: https://2gis.ru/vladivostok/firm/
70000001110946107 — это НЕ MY Avto.

Причина (см. company_agent.py, _name_key): ключ для сверки "это точно та
компания?" брал просто первое слово названия — для "MY Avto" это "my"
(обычное английское слово, совпадает почти с любой страницей), для
"Winner Auto Club" — "winner" (тоже частое слово). При автопоиске
недостающей карточки 2ГИС в fix_backfill_from_sources.py это привело к
ложному "подтверждению" случайной чужой карточки — а раз карточка была
принята, backfill_from_sources каскадно растащил из неё же и другие
пустые поля (vk/instagram/telegram/avito/drom/autoru/max/youtube/rutube/
whatsapp). Один неверный "якорь" заразил сразу несколько полей.

Исправлено: _name_key() теперь для коротких/общеупотребимых первых слов
берёт сочетание первых ДВУХ слов ("my avto", "winner auto") — гораздо
специфичнее, случайно не совпадёт.

Этот скрипт:
1. Явно чистит известный мусор у MY Avto (2gis, ссылка на владивостокскую
   фирму 70000001110946107, подтверждено пользователем вручную).
2. Проходит по ВСЕМ компаниям и переверяет ВСЕ уже сохранённые ссылки
   (yandex/google/2gis/telegram/instagram/vk/avito/drom/autoru/max/
   youtube/rutube/whatsapp) уже ИСПРАВЛЕННЫМ строгим ключом — что не
   подтверждается содержимым страницы назначения, чистит. После чистки
   пробует найти подтверждённую замену (для yandex/google/2gis/instagram/
   vk/avito/drom/autoru — своей find-функцией; у telegram/max/youtube/
   rutube/whatsapp активного поиска нет, остаются пустыми, если стёрты).
3. MY Avto (id:1) ИСКЛЮЧЕНА из общего прохода — это единственная компания
   с данными, подтверждёнными лично владельцем (см. PROJECT_STATE.md), не
   должна попадать под автоматическую чистку/переподбор вообще. Явная
   чистка мусора (п.1) — отдельно, руками, по факту.

Запуск: python3 fix_reverify_after_key_fix.py
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

ID_COL, NAME_COL, TELEGRAM_COL, PHONE_COL, SITE_COL = 1, 2, 10, 11, 12
YANDEX_COL, GOOGLE_COL, GIS2_COL = 18, 20, 21
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


def full_url_for(field, val):
    # telegram хранится как голый юзернейм, не полный URL.
    if field == "telegram":
        return "https://t.me/" + val if val else ""
    return val


def content_confirms(url, key, phone_digits):
    if not url.startswith("http"):
        return False
    if not is_real_profile_url(url.lower()):
        return False
    text = fetch_page_signal_text(url)
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

# --- 1. Явная чистка подтверждённого мусора у MY Avto ---
BAD_MY_AVTO_GIS2_MARKER = "70000001110946107"
for i, row in enumerate(rows, start=2):
    cid = cell(row, ID_COL)
    name = cell(row, NAME_COL)
    if cid == "1" or name.strip().lower() == "my avto":
        gis2 = cell(row, GIS2_COL)
        if BAD_MY_AVTO_GIS2_MARKER in gis2:
            ws.update_cell(i, GIS2_COL, "")
            print(f"[{i}] {name}: очищен подтверждённо неверный 2ГИС ({gis2})")
        break

print()

# --- 2. Полная переверификация строгим ключом (кроме MY Avto — id:1) ---
cleared_total = 0
refound_total = 0

for i, row in enumerate(rows, start=2):
    cid = cell(row, ID_COL)
    name = cell(row, NAME_COL)
    if not name:
        continue
    if cid == "1" or name.strip().lower() == "my avto":
        print(f"[{i}] {name}: пропускаю (id:1, данные подтверждены владельцем вручную)")
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
        url = full_url_for(field_name, val)
        if not content_confirms(url, key, pd):
            ws.update_cell(i, col, "")
            cleared_here.append(field_name)
            cleared_total += 1
            print(f"[{i}] {name}: не подтвердилось строгим ключом '{key}' — чищу {field_name} ({val})")
        time.sleep(0.4)

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

print(f"\nГотово. Очищено: {cleared_total}, найдено подтверждённых замен: {refound_total}.")
print("Теперь прогони python3 update_site.py.")
