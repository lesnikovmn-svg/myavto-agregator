"""
Карточка Fast Wheel (site: fast-wheel.ru/avto-iz-evropy, id:85) — тот же
класс бага, что у "Авто Азия"/autoshoot.ru: name стал рекламным
заголовком страницы ("Авто из Европы под ключ в Россию") вместо
настоящего названия компании "Fast Wheel". Пользователь попросил
переименовать (13.08.2026).

Правим только name. Остальные поля не трогаем — не проверялись отдельно.

Запуск: python3 fix_rename_fastwheel.py
После — python3 update_site.py.
"""
from company_agent import connect_sheets

NAME_COL, SITE_COL = 2, 12

ws = connect_sheets()
all_values = ws.get_all_values()

row_i = None
for i, row in enumerate(all_values[1:], start=2):
    site = row[SITE_COL - 1].strip().lower() if len(row) >= SITE_COL else ""
    if "fast-wheel.ru" in site:
        row_i = i
        old_name = row[NAME_COL - 1]
        break

if not row_i:
    print("Карточку с сайтом fast-wheel.ru не нашёл.")
else:
    ws.update_cell(row_i, NAME_COL, "Fast Wheel")
    print(f"[{row_i}] name: '{old_name}' -> 'Fast Wheel'")

print("\nТеперь прогони python3 update_site.py.")
