"""
Разовый ремонт: найден баг в add_company() (company_agent.py) — ws.append_row()
без table_range='A1' в какой-то момент "уехал" вправо и с тех пор каждая
новая компания дописывалась во всё более дальние колонки листа вместо
колонки A (сдвиг рос: 20 -> 44 -> 67 -> 89 -> 112...). В итоге 29 компаний,
которые агент реально нашёл и "успешно" добавил (в логе были "OK: ..."),
физически лежат в таблице, но update_site.py их не видел, т.к. читает
только колонки A-Z (id..autoru) — а их данные не в тех колонках.

Баг в company_agent.py уже исправлен (add_company теперь всегда передаёт
table_range='A1'). Этот скрипт — разовое восстановление уже испорченных
строк:
  1. Находит все строки, где имя (колонка B) пустое, но где-то правее есть
     данные — это и есть "уехавшие" строки.
  2. Для каждой такой строки находит первую непустую ячейку — это и есть
     начало сдвинутого 26-колоночного блока (id..autoru) — и вырезает его.
  3. Чинит названия вида "Telegram: View @username" (тот же баг сырого
     <title> t.me-превью, что чинили в company_agent.py, но эти строки были
     добавлены до фикса) — достаёт настоящее название канала напрямую с
     t.me через fetch_telegram_preview().
  4. Обрезает названия с хвостом вида "Название (@handle ..." до первого
     "(@" — тоже вариант того же бага (описание/сниппет ошибочно взяты
     целиком за название).
  5. Убирает дубли по названию (без учёта регистра) — один и тот же канал
     иногда попадал в этот сбойный диапазон дважды под разными "битыми"
     именами.
  6. Проверяет на упоминание Украины (на случай, если что-то похожее
     проскочило).
  7. Удаляет все испорченные строки и дописывает уже починенные —
     обязательно через table_range='A1', чтобы не словить тот же баг снова.

Запуск: python3 fix_column_shift_bug.py
После — python3 update_site.py, чтобы пересобрать сайт с восстановленными
компаниями.
"""
import re
import time
import gspread
from google.oauth2.service_account import Credentials
from company_agent import fetch_telegram_preview, mentions_ukraine

config = {}
with open("agent_config.env") as f:
    for line in f:
        if "=" in line:
            k, v = line.strip().split("=", 1)
            config[k] = v
SHEET_ID = config["SHEET_ID"]

scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
client = gspread.authorize(creds)
ws = client.open_by_key(SHEET_ID).sheet1

NUM_COLS = 26  # id,name,rating,reviews,years,delivered,description,directions,
               # tags,telegram,phone,site,manager,region,featured,avatar,color,
               # yandex,inn,google,gis2,instagram,vk,avito,drom,autoru

all_values = ws.get_all_values()

broken_row_indices = []
recovered = []
for i, row in enumerate(all_values[1:], start=2):
    name = row[1].strip() if len(row) > 1 else ""
    if name:
        continue  # нормальная строка — не трогаем
    offset = next((j for j, v in enumerate(row) if v.strip()), None)
    if offset is None:
        continue  # реально пустая строка
    fields = row[offset:offset + NUM_COLS]
    fields += [""] * (NUM_COLS - len(fields))
    broken_row_indices.append(i)
    recovered.append(fields)

print(f"Найдено сдвинутых строк: {len(broken_row_indices)} -> {broken_row_indices}")

if not recovered:
    print("Нечего восстанавливать — сдвинутых строк нет.")
    raise SystemExit

TG_TITLE_RE = re.compile(r"^Telegram:\s*View\s*@(\w+)", re.IGNORECASE)
for fields in recovered:
    name = fields[1].strip()

    m = TG_TITLE_RE.match(name)
    if m:
        handle = m.group(1)
        print(f"  Чиню имя для @{handle} (было: '{name[:60]}')...")
        preview = fetch_telegram_preview(handle)
        if preview and preview.get("title"):
            name = preview["title"]
            print(f"    -> '{name}'")
        else:
            name = handle.replace("_", " ").title()
            print(f"    t.me недоступен, ставлю имя из хэндла: '{name}'")
        time.sleep(1)
    elif " (@" in name:
        name = name.split(" (@")[0].strip()
        print(f"  Обрезал хвост с хэндлом: '{name}'")

    fields[1] = name

# Убираем упоминания Украины на всякий случай.
before = len(recovered)
recovered = [f for f in recovered if not mentions_ukraine(f[6] + " " + f[1])]
if len(recovered) != before:
    print(f"Отфильтровано по 'Украина': {before - len(recovered)}")

# Дедуп по имени (без учёта регистра) — один и тот же канал иногда попадал
# в сбойный диапазон дважды под разными битыми именами.
seen = set()
deduped = []
for fields in recovered:
    key = fields[1].strip().lower()
    if not key or key in seen:
        print(f"  Дубликат, пропускаю: '{fields[1]}'")
        continue
    seen.add(key)
    deduped.append(fields)

print(f"\nК перезаписи: {len(deduped)} компаний (из {len(recovered)} восстановленных, "
      f"{len(recovered) - len(deduped)} дублей отброшено)")

# Удаляем испорченные строки снизу вверх, чтобы номера остальных строк не
# съезжали в процессе удаления.
for row_idx in sorted(broken_row_indices, reverse=True):
    ws.delete_rows(row_idx)
    time.sleep(0.3)
print(f"Удалено {len(broken_row_indices)} испорченных строк.")

# ID считаем от максимума уже существующих (а не от числа строк) — чтобы
# точно не столкнуться с уже занятыми id у существующих компаний.
existing_ids = []
for row in ws.get_all_values()[1:]:
    if row and row[0].strip():
        try:
            existing_ids.append(int(float(row[0])))
        except ValueError:
            pass
next_id = max(existing_ids) if existing_ids else len(ws.get_all_values())

for fields in deduped:
    next_id += 1
    fields[0] = str(next_id)
    ws.append_row(fields, table_range='A1')
    print(f"  OK: {fields[1]}")
    time.sleep(0.5)

print(f"\nГотово. Восстановлено и дописано {len(deduped)} компаний.")
print("Теперь прогони python3 update_site.py.")
