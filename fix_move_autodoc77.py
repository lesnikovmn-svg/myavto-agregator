"""
"Растаможка Авто Под Ключ" (@autodoc77_ru) — пользователь указал 14.08.2026,
что это таможенный брокер, не компания-импортёр авто, хотя формально
описание ("ОФОРМЛЕНИЕ ВВОЗИМЫХ АВТО ... Растаможка -Лаборатория -СБКТС+ЭПТС
...ПОДБОР авто в Беларуси") не содержало явных фраз из is_customs_broker()
("таможенный брокер"/"таможенный представитель"/"декларант"/"СВХ" и т.п.) —
эвристика её не поймала. Карточка уже перенесена вручную в раздел
"Таможенные брокеры" на сайте (#customs, index.html), эта разовая чистка
убирает её из каталога импортёров в Google Sheets.

Запуск: python3 fix_move_autodoc77.py
После — python3 update_site.py.
"""
from company_agent import connect_sheets

NAME_COL, TELEGRAM_COL = 2, 10

ws = connect_sheets()
all_values = ws.get_all_values()

row_i = None
for i, row in enumerate(all_values[1:], start=2):
    telegram = row[TELEGRAM_COL - 1].strip().lower() if len(row) >= TELEGRAM_COL else ""
    name = row[NAME_COL - 1].strip() if len(row) >= NAME_COL else ""
    if telegram == "autodoc77_ru" or name == "Растаможка Авто Под Ключ":
        row_i = i
        break

if not row_i:
    print("Строку не нашёл — возможно, уже удалена.")
else:
    print(f"Найдена строка {row_i}: {all_values[row_i-1][:3]}")
    ws.delete_rows(row_i)
    print(f"Удалена строка {row_i}.")

print("\nТеперь прогони python3 update_site.py.")
