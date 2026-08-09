"""
Точечная чистка 20 компаний, восстановленных fix_column_shift_bug.py:
1) Обрезает три названия до реального имени по разделителю (то же самое,
   что делает clean_name_from_title в company_agent.py — там уже добавлен
   разделитель "·", здесь просто применяем вручную к уже записанным строкам,
   которые были дописаны ДО этого фикса):
   "LikeAvto - Авто из Китая, Кореи, Японии" -> "LikeAvto"
   "LimCars - Авто напрямую из Кореи, Китая, Японии" -> "LimCars"
   "Честный Импорт · импорт авто из Кореи и Китая под ключ" -> "Честный Импорт"
2) Удаляет одну явно мусорную запись — "Telegram – a new era of messaging"
   это собственный слоган самого приложения Telegram, а не компания-импортёр,
   попал в каталог по ошибке (текст слогана как-то совпал с одним из
   ключевых слов-фильтров).

Остальные generic-названия ("Купить авто из Кореи...", "Статистика продаж
автомобилей на аукционах Японии" и т.п.) НЕ трогаем — непонятно, реальные
это компании или SEO-статьи/маркетинговые лендинги, нужно решение
пользователя.

Запуск: python3 fix_recovered_names_cleanup.py
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

RENAMES = {
    "LikeAvto - Авто из Китая, Кореи, Японии": "LikeAvto",
    "LimCars - Авто напрямую из Кореи, Китая, Японии": "LimCars",
    "Честный Импорт · импорт авто из Кореи и Китая под ключ": "Честный Импорт",
}
DELETE_NAMES = {"Telegram – a new era of messaging"}

all_values = ws.get_all_values()
renamed = 0
to_delete_rows = []
for i, row in enumerate(all_values[1:], start=2):
    name = row[1].strip() if len(row) > 1 else ""
    if name in DELETE_NAMES:
        to_delete_rows.append(i)
        continue
    if name in RENAMES:
        ws.update_cell(i, 2, RENAMES[name])
        print(f"Строка {i}: '{name}' -> '{RENAMES[name]}'")
        renamed += 1

for row_idx in sorted(to_delete_rows, reverse=True):
    ws.delete_rows(row_idx)
    print(f"Удалена строка {row_idx} (мусор, не компания)")

print(f"\nГотово: переименовано {renamed}, удалено {len(to_delete_rows)}.")
print("Теперь прогони python3 update_site.py.")
