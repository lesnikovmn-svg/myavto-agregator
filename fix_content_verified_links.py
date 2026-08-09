"""
Точечные фиксы по конкретным случаям, найденным пользователем вручную
(перешёл по ссылкам на живом сайте):

1. Primorye China Export — реальный телеграм @bezpokrasa (проверено:
   телефон на канале +7 995 866-40-82 совпадает 1-в-1 с тем, что уже в
   таблице). Проставляем.

2. MY Avto — 2ГИС-ссылка на firm/5348552840354892 (СПб) не ведёт на эту
   компанию. Чистим.

3. Winner Auto Club — 2ГИС (Челябинск, firm/70000001109608439) и VK
   (winnerauto) ведут на другие организации. Чистим оба.

4. Artalex Group — 2ГИС (Москва, firm/4504127918450447) и VK
   (artalex_group) ведут на другие организации. Чистим оба.

После чистки — пробуем найти замену уже НОВОЙ логикой проверки
(find_platform_link теперь сверяет не только сниппет DDG, но и реальное
содержимое страницы назначения, см. company_agent.py). Если подтверждённой
замены нет — оставляем пустым, кнопка просто не покажется.

Запуск: python3 fix_content_verified_links.py
После — python3 update_site.py.
"""
import time
import gspread
from google.oauth2.service_account import Credentials
from company_agent import find_map_links, find_social_links, fetch_site_text

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

TELEGRAM_COL, PHONE_COL, SITE_COL = 10, 11, 12
GIS2_COL, VK_COL = 21, 23

all_values = ws.get_all_values()
by_name = {}
for i, row in enumerate(all_values[1:], start=2):
    name = row[1].strip() if len(row) > 1 else ""
    if name:
        by_name[name] = (i, row)


def cell(row, col_1idx):
    idx = col_1idx - 1
    return row[idx].strip() if len(row) > idx and row[idx] else ""


# --- 1. Primorye China Export: реальный телеграм ---
if "Primorye China Export" in by_name:
    i, row = by_name["Primorye China Export"]
    ws.update_cell(i, TELEGRAM_COL, "bezpokrasa")
    print(f"Строка {i}: Primorye China Export — telegram -> bezpokrasa")
else:
    print("Primorye China Export не найдена.")

# --- 2-4. Чистка неверных ссылок ---
BAD_LINKS = {
    "MY Avto": {GIS2_COL: "5348552840354892"},
    "Winner Auto Club": {GIS2_COL: "70000001109608439", VK_COL: "winnerauto"},
    "Artalex Group": {GIS2_COL: "4504127918450447", VK_COL: "artalex_group"},
}

for name, bad_fields in BAD_LINKS.items():
    if name not in by_name:
        print(f"{name} не найдена — пропускаю.")
        continue
    i, row = by_name[name]
    cleared_gis2 = cleared_vk = False
    for col, marker in bad_fields.items():
        current = cell(row, col)
        if marker in current:
            ws.update_cell(i, col, "")
            print(f"Строка {i} ({name}): очищено поле col{col} (было '{current}')")
            if col == GIS2_COL:
                cleared_gis2 = True
            if col == VK_COL:
                cleared_vk = True
        else:
            print(f"Строка {i} ({name}): col{col} уже другое значение ('{current}') — не трогаю")
    time.sleep(0.3)

    if not (cleared_gis2 or cleared_vk):
        continue

    company_name = name
    phone = cell(row, PHONE_COL)
    site = cell(row, SITE_COL)

    if cleared_gis2:
        print(f"  ищу подтверждённую 2ГИС-замену для {company_name}...")
        yandex2, google2, gis2_new, _ = find_map_links(company_name, phone)
        if gis2_new:
            ws.update_cell(i, GIS2_COL, gis2_new)
            print(f"    новый 2gis: {gis2_new}")
        else:
            print("    подтверждённой замены не нашлось — оставляю пустым")
        time.sleep(1)

    if cleared_vk:
        print(f"  ищу подтверждённую VK-замену для {company_name}...")
        site_text = fetch_site_text(site) if site.startswith("http") else ""
        _, vk_new, _ = find_social_links(company_name, site_text, phone)
        if vk_new:
            ws.update_cell(i, VK_COL, vk_new)
            print(f"    новый vk: {vk_new}")
        else:
            print("    подтверждённой замены не нашлось — оставляю пустым")
        time.sleep(1)

print("\nГотово. Теперь прогони python3 update_site.py.")
