"""
Чистит конкретный мусор, который успел записать fix_full_content_reverify.py
ДО того, как is_real_profile_url научился отсекать служебные разделы
VK/Instagram: "vk.com/js"/"vk.ru/js" (заглушка "включите JavaScript",
ошибочно "подтвердилась" сразу для 4 разных компаний — Worldcar, OTRADACARS,
Jplife, ТокиДоки), "vk.com/video"/"vk.com/clips" (общие разделы, не
профиль), "instagram.com/favicon.ico" (иконка сайта, не аккаунт).

После чистки — пробует найти подтверждённую замену уже с исправленной
is_real_profile_url (обновлена в company_agent.py 09.08.2026).

Запуск: python3 fix_bad_reserved_paths.py
После — python3 update_site.py.
"""
import re
import time
import gspread
from google.oauth2.service_account import Credentials
from company_agent import find_social_links, fetch_site_text

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
INSTAGRAM_COL, VK_COL = 22, 23

BAD_VK = re.compile(r"vk\.(?:com|ru)/(js|video|videos|clips|wall|photo|photos)\b", re.IGNORECASE)
BAD_INSTA = re.compile(r"instagram\.com/(favicon\.ico|p|explore|accounts|reel|reels|stories|tv)\b", re.IGNORECASE)


def cell(row, col_1idx):
    idx = col_1idx - 1
    return row[idx].strip() if len(row) > idx and row[idx] else ""


all_values = ws.get_all_values()
cleaned = 0
refound = 0

for i, row in enumerate(all_values[1:], start=2):
    name = cell(row, NAME_COL)
    if not name:
        continue
    vk = cell(row, VK_COL)
    insta = cell(row, INSTAGRAM_COL)

    cleared_vk = cleared_insta = False
    if vk and BAD_VK.search(vk):
        ws.update_cell(i, VK_COL, "")
        print(f"[{i}] {name}: очищен мусорный vk ({vk})")
        cleared_vk = True
        cleaned += 1
    if insta and BAD_INSTA.search(insta):
        ws.update_cell(i, INSTAGRAM_COL, "")
        print(f"[{i}] {name}: очищен мусорный instagram ({insta})")
        cleared_insta = True
        cleaned += 1

    if not (cleared_vk or cleared_insta):
        continue

    time.sleep(0.3)
    phone = cell(row, PHONE_COL)
    site = cell(row, SITE_COL)
    site_text = fetch_site_text(site) if site.startswith("http") else ""
    insta2, vk2, _ = find_social_links(name, site_text, phone)
    if cleared_vk and vk2:
        ws.update_cell(i, VK_COL, vk2)
        print(f"    новый vk: {vk2}")
        refound += 1
    if cleared_insta and insta2:
        ws.update_cell(i, INSTAGRAM_COL, insta2)
        print(f"    новый instagram: {insta2}")
        refound += 1
    time.sleep(1)

print(f"\nГотово. Очищено: {cleaned}, найдено замен: {refound}.")
print("Теперь прогони python3 update_site.py.")
