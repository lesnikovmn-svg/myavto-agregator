"""
Вторая волна дублей id — 18.08.2026, найдено check_duplicate_ids.py сразу
после того, как fix_dedupe_company_ids.py (первая волна, id 107-117) уже
отработала. Причина — баг в company_agent.py: next_id считался как
len(ws.get_all_values()) (количество строк), а не как максимум реального
id + 1. После того как первая волна переномеровала дубли в 107-117, число
строк в таблице стало МЕНЬШЕ этих значений — и в тот же день агент,
добавляя новые компании, снова попал в уже занятые id (100,102,106,107,
108,109,110), в том числе прямо в те, что только что освободила первая
волна. Сам баг в company_agent.py уже исправлен (next_id = max(id)+1) —
этот скрипт чистит только уже накопленные последствия.

Правило то же: id остаётся у строки, что идёт в таблице раньше, второй
строке — новый уникальный id начиная с 118 (максимальный текущий id на
18.08.2026 — 117).

Проверка по имени перед записью — та же подстраховка, что и в первой волне.

Запуск: python3 fix_dedupe_company_ids_batch2.py
После — python3 update_site.py.
"""
from company_agent import connect_sheets

ID_COL = 1
NAME_COL = 2

# (номер строки, новый id, ожидаемое имя — из вывода check_duplicate_ids.py от 18.08.2026)
REASSIGN = [
    (100, 118, "Autoimport.Trade"),
    (102, 119, "Авто из Кореи и Китая CarsKorea"),
    (106, 120, "Tgsearch.Org"),
    (107, 121, "Dzen"),
    (108, 122, "MAX"),
    (109, 123, "Autocom — авто под заказ"),
    (110, 124, "FranceAuto"),
]

ws = connect_sheets()
all_values = ws.get_all_values()

updated, skipped = 0, 0
for row_idx, new_id, expected_name in REASSIGN:
    row = all_values[row_idx - 1] if row_idx - 1 < len(all_values) else []
    actual_name = row[NAME_COL - 1].strip() if len(row) >= NAME_COL else ""
    if actual_name != expected_name:
        print(f"[строка {row_idx}] ожидал '{expected_name}', нашёл '{actual_name}' — таблица изменилась, пропущено. Проверь вручную.")
        skipped += 1
        continue
    ws.update_cell(row_idx, ID_COL, new_id)
    print(f"[строка {row_idx}] {actual_name}: id -> {new_id}")
    updated += 1

print(f"\nИтого: переномеровано — {updated}, пропущено — {skipped}.")
if updated:
    print("Теперь прогони python3 update_site.py.")
