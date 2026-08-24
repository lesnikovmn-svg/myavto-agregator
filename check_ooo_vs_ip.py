"""
Диагностика (read-only): делит компании каталога на ООО/юрлица и ИП по
длине ИНН — стандарт ФНС: 10 цифр = юрлицо, 12 цифр = физлицо/ИП. Повод —
разговор про 152-ФЗ: данные ИП формально персональные (ИП = физлицо), у ООО
— нет. Нужно понимать, к скольким карточкам в каталоге это вообще
относится.

Ничего не меняет, только печатает три списка: ООО (юрлица), ИП, и компании
без ИНН вовсе (для них разделить нельзя, ЕГРЮЛ-проверка тоже не идёт — см.
verify_egrul.py/update_site.py).

Запуск: python3 check_ooo_vs_ip.py
"""

import re
from company_agent import connect_sheets

ID_COL = 1
NAME_COL = 2
INN_COL = 19

ws = connect_sheets()
all_values = ws.get_all_values()

ooo, ip, no_inn = [], [], []

for row in all_values[1:]:

    def val(col):
        return row[col - 1].strip() if len(row) >= col and row[col - 1] else ""

    name = val(NAME_COL)
    if not name:
        continue

    inn_raw = val(INN_COL)
    inn = re.sub(r"\D", "", inn_raw)

    if len(inn) == 10:
        ooo.append((val(ID_COL), name, inn))
    elif len(inn) == 12:
        ip.append((val(ID_COL), name, inn))
    else:
        no_inn.append((val(ID_COL), name))

print(f"ООО/юрлица (ИНН 10 цифр): {len(ooo)}")
for cid, name, inn in ooo:
    print(f"  [{cid}] {name} — ИНН {inn}")

print(f"\nИП (ИНН 12 цифр): {len(ip)}")
for cid, name, inn in ip:
    print(f"  [{cid}] {name} — ИНН {inn}")

print(f"\nБез ИНН (разделить нельзя): {len(no_inn)}")

total = len(ooo) + len(ip) + len(no_inn)
print(f"\nВсего компаний: {total}")
