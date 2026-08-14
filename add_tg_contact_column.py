"""
14.08.2026: добавляем в таблицу новую колонку 31 (AE) — "Telegram
(личный/бот)". Раньше было одно поле telegram, куда агент писал КАНАЛ/ГРУППУ
компании (это то, что находит tgstat) — у канала нет чата, кнопка "Написать
в TG" на сайте вела в тупик. Вместо того чтобы затирать/подменять канал
(как делал старый вариант fix_telegram_contact_check.py), заводим отдельную
колонку для личного контакта/бота — канал остаётся как есть (полезен сам по
себе, показываем его отдельной иконкой), а кнопка "написать" на сайте берёт
данные из новой колонки.

Запуск один раз: python3 add_tg_contact_column.py
После — python3 fix_telegram_contact_check.py (заполнит колонку там, где
получится найти личный контакт), затем python3 update_site.py.
"""
from company_agent import connect_sheets

TG_CONTACT_COL = 31

ws = connect_sheets()
header = ws.cell(1, TG_CONTACT_COL).value
if header:
    print(f"Колонка {TG_CONTACT_COL} уже занята: '{header}' — ничего не делаю.")
else:
    ws.update_cell(1, TG_CONTACT_COL, "Telegram (личный/бот)")
    print(f"Заголовок колонки {TG_CONTACT_COL} (AE) установлен: 'Telegram (личный/бот)'.")
