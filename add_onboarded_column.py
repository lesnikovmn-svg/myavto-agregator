"""
14.08.2026: добавляем в таблицу колонку 33 (AG) — "Онбордился в боте".
Нужна для ранжирования компаний на сайте (см. раздел PROJECT_STATE.md
"Ранжирование компаний на сайте" от 14.08.2026) — статус онбординга
(нажал ли /start у t.me/MyAvtoAgregator_bot) хранится в bot_state.json на
VPS, не в таблице, а сортировке на сайте нужно поле прямо в COMPANIES
(index.html не умеет читать bot_state.json — это статичный сгенерированный
JS-массив). Эта колонка — "зеркало" bot_state.json в таблице, обновляется
скриптом sync_onboarded_to_sheet.py.

Запуск один раз: python3 add_onboarded_column.py
После — python3 sync_onboarded_to_sheet.py, затем python3 update_site.py.
"""
from company_agent import connect_sheets

ONBOARDED_COL = 33

ws = connect_sheets()
header = ws.cell(1, ONBOARDED_COL).value
if header:
    print(f"Колонка {ONBOARDED_COL} уже занята: '{header}' — ничего не делаю.")
else:
    ws.update_cell(1, ONBOARDED_COL, "Онбордился в боте")
    print(f"Заголовок колонки {ONBOARDED_COL} (AG) установлен: 'Онбордился в боте'.")
