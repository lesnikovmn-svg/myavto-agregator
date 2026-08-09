"""
Два точечных фикса:

1. Удаляет "Auto.Ria" (auto.ria.com) — украинская площадка, пользователь
   уже просил её убрать раньше в этой сессии, но она почему-то осталась в
   таблице (возможно, тогдашнее удаление не сохранилось/строка вернулась).

2. Чинит VK-ссылку у EncarRus: на сайте encarrus.ru реально есть ссылка на
   https://vk.ru/encarrus, но агент её не поймал — extract_social_from_text
   в company_agent.py искал только домен vk.com, а не vk.ru (это уже
   исправлено в коде для будущих прогонов). Здесь просто вручную
   проставляем верную ссылку для уже существующей записи.

Запуск: python3 fix_autoria_and_encarrus_vk.py
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

VK_COL = 23  # 1-indexed: id,name,rating,reviews,years,delivered,description,
             # directions,tags,telegram,phone,site,manager,region,featured,
             # avatar,color,yandex,inn,google,gis2,instagram,vk,...

all_values = ws.get_all_values()
autoria_row = None
encarrus_row = None
for i, row in enumerate(all_values[1:], start=2):
    name = row[1].strip() if len(row) > 1 else ""
    if name == "Auto.Ria":
        autoria_row = i
    elif name == "EncarRus":
        encarrus_row = i

if autoria_row:
    ws.delete_rows(autoria_row)
    print(f"Удалена строка {autoria_row} (Auto.Ria)")
else:
    print("Auto.Ria не найдена — уже удалена.")

# Пересчитываем номера строк, если Auto.Ria была выше EncarRus в таблице.
if autoria_row and encarrus_row and autoria_row < encarrus_row:
    encarrus_row -= 1

if encarrus_row:
    ws.update_cell(encarrus_row, VK_COL, "https://vk.ru/encarrus")
    print(f"Строка {encarrus_row}: VK EncarRus -> https://vk.ru/encarrus")
else:
    print("EncarRus не найдена в таблице — VK не проставлен.")

print("\nГотово. Теперь прогони python3 update_site.py.")
