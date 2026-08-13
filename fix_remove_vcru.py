"""
Удаление мусорной строки "vc.ru" (id:80) — 13.08.2026.

Агент 13.08.2026 (обычный дневной прогон по крону) нашёл в поиске
собственную статью автора на vc.ru (tribuna/3075991-import-avtomobilej-
iz-zagranitsy) — она полна тех же ключевых слов, что ищет агент
("импорт авто", "агрегатор", "Telegram-бот"), — и принял саму площадку
vc.ru за компанию-импортёра: description стал meta-description статьи,
телефон — явный мусор (86860700000), а по ИНН случайно нашёлся реальный
(но не автомобильный) юрлицо vc.ru/Rambler, что дало ложный зелёный
бейдж ЕГРЮЛ. Та же болезнь, что раньше была с tenchat.ru/autonews.ru —
новостной/медиа-портал, у которого случайно совпали ключевые слова,
принят за компанию.

"vc.ru" добавлен в BLACKLIST в company_agent.py (не повторится), эта
разовая чистка убирает уже попавшую в таблицу строку.

Запуск: python3 fix_remove_vcru.py
После — python3 update_site.py.
"""
from company_agent import connect_sheets

ws = connect_sheets()
all_values = ws.get_all_values()

row_i = None
for i, row in enumerate(all_values[1:], start=2):
    name = row[1].strip() if len(row) > 1 else ""
    if name.lower() == "vc.ru":
        row_i = i
        break

if not row_i:
    print("Строку 'vc.ru' не нашёл — возможно, уже удалена.")
else:
    print(f"Найдена строка {row_i}: {all_values[row_i-1][:3]}")
    ws.delete_rows(row_i)
    print(f"Удалена строка {row_i}.")

print("\nТеперь прогони python3 update_site.py.")
