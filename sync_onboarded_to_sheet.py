"""
Переносит статус онбординга из bot_state.json (VPS) в колонку 33 (AG,
"Онбордился в боте") основной таблицы — 14.08.2026, часть ранжирования
компаний на сайте (featured -> онбордился -> ЕГРЮЛ -> активность, см.
PROJECT_STATE.md). Без этой синхронизации сайт (index.html/update_site.py)
не может узнать про онбординг вообще — bot_state.json на сайт не попадает,
это отдельное оперативное хранилище бота.

Где запускать: лучше всего ПРЯМО НА VPS (там bot_state.json всегда
свежий) — тогда сразу после можно занести в cron рядом с существующим
`git pull` (например, тоже каждые 10 минут, или реже — раз в час
достаточно, онбординг не настолько частое событие). Если запускать на
Маке — сначала скопируй свежий файл:
  scp root@89.108.70.185:/var/www/myavto-agregator/bot_state.json .

Пишет TRUE только тем, у кого telegram-хэндл (колонка J) совпадает с
онбордившимся в bot_state.json — сверяет по нижнему регистру, без "@".
Если компания раньше была TRUE, а потом почему-то пропала из
bot_state.json (не должно случаться в норме) — колонку НЕ откатывает
обратно на FALSE, только дополняет новыми онбордившимися (осторожность
на случай временного сбоя бота/файла).

Запуск (после add_onboarded_column.py): python3 sync_onboarded_to_sheet.py
После — python3 update_site.py.
"""

import json
import os

from company_agent import connect_sheets

NAME_COL = 2
TELEGRAM_COL = 10
ONBOARDED_COL = 33
BOT_STATE_FILE = "bot_state.json"

if not os.path.exists(BOT_STATE_FILE):
    print(
        f"Не нашёл {BOT_STATE_FILE} в текущей папке.\n"
        f"Он лежит на VPS: /var/www/myavto-agregator/bot_state.json\n"
        f"Либо запусти этот скрипт по SSH прямо на VPS, либо скачай файл:\n"
        f"  scp root@89.108.70.185:/var/www/myavto-agregator/bot_state.json ."
    )
    raise SystemExit(1)

with open(BOT_STATE_FILE, encoding="utf-8") as f:
    state = json.load(f)

onboarded_handles = set(state.get("companies", {}).keys())

ws = connect_sheets()
header = ws.cell(1, ONBOARDED_COL).value
if not header:
    print(
        f"Колонка {ONBOARDED_COL} (AG) ещё не создана — сначала запусти "
        f"python3 add_onboarded_column.py"
    )
    raise SystemExit(1)

all_values = ws.get_all_values()
updated = 0

for i, row in enumerate(all_values[1:], start=2):
    name = row[NAME_COL - 1].strip() if len(row) >= NAME_COL else ""
    handle = row[TELEGRAM_COL - 1].strip().lstrip("@").lower() if len(row) >= TELEGRAM_COL else ""
    current = row[ONBOARDED_COL - 1].strip() if len(row) >= ONBOARDED_COL else ""
    if not name or not handle:
        continue
    if handle in onboarded_handles and current.upper() != "TRUE":
        ws.update_cell(i, ONBOARDED_COL, "TRUE")
        print(f"[{i}] {name}: онбордился -> TRUE")
        updated += 1

print(f"\nИтого обновлено: {updated} из {len(onboarded_handles)} онбордившихся в bot_state.json.")
print("Теперь прогони python3 update_site.py.")
