"""
Фикс дублирующихся id — 18.08.2026, найдено check_duplicate_ids.py: 10
значений id встречались по 2-3 раза на 21 строку (id=60,62,63,66,72,73,74,
77,94,97). Матчинг на сайте и во всех скриптах проекта идёт по НАЗВАНИЮ
компании, а не по id (см. PROJECT_STATE.md, sync_onboarded_to_sheet.py и
др.) — поэтому переномерация полностью безопасна для работы сайта, она
только делает сами id в таблице честными (один id = одна компания).

Правило: в каждой группе дублей id остаётся у строки, которая идёт в
таблице РАНЬШЕ (меньший номер строки); остальным присваивается новый
уникальный id начиная со 107 (максимальный текущий id на 18.08.2026 — 106).

Для подстраховки (таблица могла измениться со времени диагностики) каждая
строка проверяется по ИМЕНИ перед записью — если имя не совпадает с
ожидаемым, строка пропускается, а не переномеровывается вслепую.

Запуск: python3 fix_dedupe_company_ids.py
После — python3 update_site.py.
"""
from company_agent import connect_sheets

ID_COL = 1
NAME_COL = 2

# (номер строки в таблице, новый id, ожидаемое имя — из вывода check_duplicate_ids.py от 18.08.2026)
REASSIGN = [
    (60, 107, "AutoImport Russia"),
    (62, 108, "Телеграм канал Levcar"),
    (63, 109, "Авто Азия"),
    (65, 110, "Долгов Авто - Машины из Кореи,Японии,Китая."),
    (70, 111, "China.Sferacar"),
    (71, 112, "СЕВЕР АВТО"),
    (72, 113, "Japan Star"),
    (73, 114, "JpAuc.ru"),
    (79, 115, "MY AUTO"),
    (90, 116, "OkAuto"),
    (95, 117, "Avtoimportrus"),
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
