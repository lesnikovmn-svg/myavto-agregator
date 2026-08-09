"""
Диагностика: 09.08.2026 company_agent.py отчитался "Добавлено: 14", но и
update_site.py через gviz, и update_site.py через gspread (после фикса)
видят всё те же 52 компании. Нужно понять, что реально в таблице — либо
добавления не сохранились, либо они там есть, но что-то их не считает.

Печатает: точное число строк с данными, последние 20 названий компаний по
порядку (чтобы увидеть, есть ли там новые компании из последнего прогона
агента), и есть ли пустые/битые строки среди последних 20.

Запуск: python3 debug_sheet_count.py
"""
import gspread
from google.oauth2.service_account import Credentials

config = {}
with open("agent_config.env") as f:
    for line in f:
        if "=" in line:
            k, v = line.strip().split("=", 1)
            config[k] = v

SHEET_ID = config["SHEET_ID"]
print(f"SHEET_ID из agent_config.env: {SHEET_ID}")

scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
client = gspread.authorize(creds)
sh = client.open_by_key(SHEET_ID)
print(f"Название таблицы: {sh.title}")
print(f"Листы в таблице: {[w.title for w in sh.worksheets()]}")

ws = sh.sheet1
print(f"Активный лист (sheet1): {ws.title}")
print(f"Row count (метаданные листа): {ws.row_count}")

all_values = ws.get_all_values()
print(f"\nВсего строк через get_all_values(): {len(all_values)} (включая заголовок)")
data_rows = [r for r in all_values[1:] if len(r) > 1 and r[1].strip()]
print(f"Строк с непустым именем компании (колонка B): {len(data_rows)}")

print("\nПоследние 20 компаний по порядку в таблице:")
for i, row in enumerate(all_values[-20:], start=len(all_values) - 19):
    name = row[1] if len(row) > 1 else "(пусто)"
    inn = row[18] if len(row) > 18 else ""
    print(f"  строка {i}: id={row[0] if row else ''} name='{name}' inn='{inn}'")
