"""
Финальная чистка generic-названий из fix_column_shift_bug.py (20 компаний,
восстановленных из "уехавшего" диапазона). Разобрал каждую руками, открыв
сайты:

  gaztormoz.ru       -> настоящий бренд "GazTormoz" (og:site_name, реальный
                        сайт с соцсетями, 16 лет на рынке)
  prim-auto.com      -> "ПримАвто" (ООО «Примавто», указано в футере)
  tokidoki.su        -> "ТокиДоки" (apple-mobile-web-app-title)
  japantransit.ru    -> "Япония Транзит" (встретился дважды под разными
                        названиями из двух разных подстраниц сайта — дедуп
                        по домену ниже уберёт вторую копию)
  aziaavtoimport.ru  -> домен "протух"/перепродан, сайт теперь отдаёт
                        немецкий маркетплейс Kaufland, а не компанию-
                        импортёра — удаляем как мёртвую запись
  auto-auc.online,
  encarrus.ru        -> сайты блокируют бота (antibot/KillBot), название
                        подтвердить не удалось — ставим название по домену
                        как наименее плохой вариант, это лучше, чем
                        рекламный заголовок статьи

Плюс общая защита на будущее для УЖЕ существующих в каталоге дублей:
shapcars.ru/westmotors.ru совпадают с уже имеющимися в каталоге компаниями
Shapcars/Westmotors — их поймает дедуп по домену. likeavto.ru скорее всего
тот же бренд, что и телеграм-канал LikeAvto (сайт совпадает по названию), но
сам домен там записан как t.me/likeatg, а не likeavto.ru — дедуп по домену
это не поймает, поэтому единой строкой переименовываем оба варианта в
"LikeAvto" и дальше дедуп по ИМЕНИ подчистит.

Запуск: python3 fix_generic_names_final.py
После — python3 update_site.py.
"""
import gspread
from google.oauth2.service_account import Credentials
from company_agent import domain_of

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
    "Купить новое авто с доставкой": "GazTormoz",
    "Японский аукцион автомобилей Toyota из Японии": "ПримАвто",
    "Статистика продаж автомобилей на аукционах Японии": "ТокиДоки",
    "Автомобили с аукционов Японии": "Япония Транзит",
    "Авто с аукционов Японии, Кореи и Китая под заказ": "Япония Транзит",
    "Авто под заказ из Японии, Кореи и Китая": "Auto-Auc",
    "Авто из Кореи под заказ": "EncarRus",
    "Импорт авто из Кореи, Китая и Японии": "LikeAvto",
}
DELETE_NAMES = {"Автомобили из Японии, Кореи и Китая под заказ"}  # aziaavtoimport.ru — мёртвый домен

# --- шаг 1: явные переименования и удаление мёртвой записи ---
all_values = ws.get_all_values()
to_delete = []
for i, row in enumerate(all_values[1:], start=2):
    name = row[1].strip() if len(row) > 1 else ""
    if name in DELETE_NAMES:
        to_delete.append(i)
        continue
    if name in RENAMES:
        ws.update_cell(i, 2, RENAMES[name])
        print(f"Строка {i}: '{name}' -> '{RENAMES[name]}'")

for row_idx in sorted(to_delete, reverse=True):
    ws.delete_rows(row_idx)
    print(f"Удалена строка {row_idx} (мёртвый домен aziaavtoimport.ru)")

# --- шаг 2: дедуп по домену сайта (после переименований) ---
all_values = ws.get_all_values()
by_domain = {}
for i, row in enumerate(all_values[1:], start=2):
    site = row[11].strip() if len(row) > 11 else ""
    d = domain_of(site)
    if d:
        by_domain.setdefault(d, []).append(i)

domain_dupes_to_delete = []
for d, rows in by_domain.items():
    if len(rows) < 2:
        continue
    # оставляем строку с ИНН, если есть хоть у одной; иначе — с наименьшим
    # номером строки (была добавлена раньше остальных).
    def has_inn(row_idx):
        r = all_values[row_idx - 2]
        return bool(len(r) > 18 and r[18].strip())
    keeper = next((r for r in rows if has_inn(r)), rows[0])
    for r in rows:
        if r != keeper:
            domain_dupes_to_delete.append(r)
            name = all_values[r - 2][1] if len(all_values[r - 2]) > 1 else ""
            print(f"Дубль по домену {d}: строка {r} ('{name}') дублирует строку {keeper} — удаляю")

for row_idx in sorted(set(domain_dupes_to_delete), reverse=True):
    ws.delete_rows(row_idx)

# --- шаг 3: дедуп по имени (после переименований — например, LikeAvto) ---
all_values = ws.get_all_values()
by_name = {}
for i, row in enumerate(all_values[1:], start=2):
    name = row[1].strip().lower() if len(row) > 1 else ""
    if name:
        by_name.setdefault(name, []).append(i)

name_dupes_to_delete = []
for name, rows in by_name.items():
    if len(rows) < 2:
        continue
    def has_inn2(row_idx):
        r = all_values[row_idx - 2]
        return bool(len(r) > 18 and r[18].strip())
    keeper = next((r for r in rows if has_inn2(r)), rows[0])
    for r in rows:
        if r != keeper:
            name_dupes_to_delete.append(r)
            print(f"Дубль по имени '{name}': строка {r} дублирует строку {keeper} — удаляю")

for row_idx in sorted(set(name_dupes_to_delete), reverse=True):
    ws.delete_rows(row_idx)

print(f"\nГотово. Удалено дублей по домену: {len(set(domain_dupes_to_delete))}, "
      f"по имени: {len(set(name_dupes_to_delete))}.")
print("Теперь прогони python3 update_site.py.")
