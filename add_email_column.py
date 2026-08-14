"""
14.08.2026: добавляем в таблицу новую колонку 32 (AF) — "Email". Нужна для
запуска email-канала онбординга компаний (наравне с Telegram/WhatsApp-
рассылкой) — часть компаний либо не отвечают в мессенджерах, либо у них
вообще нет мессенджера, зато есть контактный email на сайте.

extract_email() в company_agent.py теперь ищет email в тексте сайта/канала
компании при каждом добавлении новой строки (см. run_agent()), но саму
колонку нужно завести один раз ДО первого запуска, иначе add_company()
допишет значение по table_range='A1' без заголовка сверху.

Запуск один раз: python3 add_email_column.py
После — python3 fix_backfill_emails.py (дозаполнит email для уже
существующих ~92 компаний), затем python3 update_site.py.
"""
from company_agent import connect_sheets

EMAIL_COL = 32

ws = connect_sheets()
header = ws.cell(1, EMAIL_COL).value
if header:
    print(f"Колонка {EMAIL_COL} уже занята: '{header}' — ничего не делаю.")
else:
    ws.update_cell(1, EMAIL_COL, "Email")
    print(f"Заголовок колонки {EMAIL_COL} (AF) установлен: 'Email'.")
