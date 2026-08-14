"""
Баг найден 14.08.2026 при сборке onboarding_companies.xlsx: у трёх компаний
телефон в Google Sheets буквально равен строке "#ERROR!" (осталось от
ошибки формулы — кто-то, видимо, вставил телефон в ячейку так, что Google
Sheets распознал его как формулу, и сохранилась ошибка вычисления вместо
номера). Затронуты: Winner Auto Club (id:4), Япония Экспорт (id:62),
Авто Азия (id:63).

Просто очищаем поле "телефон" у этих трёх строк (пусто — лучше, чем
мусорное значение, которое к тому же ломает формулы в любой выгрузке,
где телефон конкатенируется с чем-то ещё).

Запуск: python3 fix_error_phones.py
После — python3 update_site.py.
"""
from company_agent import connect_sheets

PHONE_COL = 11
TARGET_NAMES = {"Winner Auto Club", "Япония Экспорт", "Авто Азия"}

ws = connect_sheets()
all_values = ws.get_all_values()

fixed = 0
for i, row in enumerate(all_values[1:], start=2):
    name = row[1].strip() if len(row) > 1 else ""
    phone = row[PHONE_COL - 1].strip() if len(row) >= PHONE_COL else ""
    if name in TARGET_NAMES and phone.startswith("#"):
        ws.update_cell(i, PHONE_COL, "-")
        print(f"[{i}] {name}: '{phone}' -> '-'")
        fixed += 1

print(f"\nПочищено строк: {fixed}")
print("Теперь прогони python3 update_site.py.")
