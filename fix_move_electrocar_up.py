"""
НАПОМИНАНИЕ (конвенция проекта): перед запуском поставь именованную версию
в Google Таблице — Файл → История версий → Назвать текущую версию →
"до fix_move_electrocar_up" → Сохранить.

Поднять ElectroCar в первые 10 компаний на сайте — 14.08.2026, по прямому
запросу пользователя.

ВАЖНО про то, как вообще работает порядок на сайте: карточки на странице
рендерятся СТРОГО в том порядке, в котором строки идут в Google Таблице
(update_site.py просто копирует строки как есть в JS-массив COMPANIES,
никакой сортировки по рейтингу/featured сейчас в index.html нет — поле
featured сейчас влияет ТОЛЬКО на бейдж "★ Рекомендуем" и рамку слева,
но НЕ на порядок показа). Значит "поднять в топ-10" технически означает
"физически передвинуть строку компании ближе к началу таблицы".

Что делает скрипт:
1. Находит строку ElectroCar по имени (и на всякий случай проверяет сайт
   electro-car.by, если имя вдруг не совпадёт один-в-один).
2. Удаляет её с текущего места и вставляет строкой №3 — сразу после
   заголовка (строка 1) и MY Avto (строка 2, id:1, единственная компания
   с featured=true — это сама компания пользователя, её место всегда
   первое, трогать не нужно). ElectroCar становится 2-й компанией по
   порядку показа — точно в топ-10.
3. Заодно ставит featured=TRUE для ElectroCar (колонка 15/O) — на сайте
   появится бейдж "★ Рекомендуем", раз компания теперь в топе.

Запуск: python3 fix_move_electrocar_up.py
После — python3 update_site.py.
"""
from company_agent import connect_sheets

NAME_COL = 2
SITE_COL = 12
FEATURED_COL = 15
TARGET_ROW = 3  # сразу после заголовка (1) и MY Avto (2)

ws = connect_sheets()
all_values = ws.get_all_values()

matches = [i for i, row in enumerate(all_values[1:], start=2)
           if len(row) >= NAME_COL and (
               row[NAME_COL - 1].strip() == "ElectroCar"
               or (len(row) >= SITE_COL and "electro-car.by" in row[SITE_COL - 1])
           )]

if len(matches) == 0:
    print("ElectroCar не найден в таблице — сначала запусти "
          "fix_add_or_update_electrocar.py.")
    raise SystemExit(1)
if len(matches) > 1:
    print(f"Нашёл {len(matches)} подходящих строк ({matches}) — "
          f"проверь дубли вручную, ничего не трогаю.")
    raise SystemExit(1)

row_idx = matches[0]
row_data = all_values[row_idx - 1]

if row_idx == TARGET_ROW:
    print(f"ElectroCar уже на нужном месте (строка {TARGET_ROW}) — только выставляю featured.")
else:
    ws.delete_rows(row_idx)
    ws.insert_row(row_data, TARGET_ROW)
    print(f"ElectroCar перемещён со строки {row_idx} на строку {TARGET_ROW}.")

# featured — после перемещения строки индекс уже TARGET_ROW
ws.update_cell(TARGET_ROW, FEATURED_COL, "TRUE")
print(f"featured = TRUE для ElectroCar (строка {TARGET_ROW}).")

print("\nТеперь прогони python3 update_site.py.")
