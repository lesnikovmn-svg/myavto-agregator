"""
Продолжение диагностики: первый прогон (debug_sheet_count.py) показал —
82 строки всего, 52 с непустым именем, последние 20 (63-82) полностью
пустые. Нужно понять структуру целиком: где именно 52 именованные компании
расположены, есть ли "дыры" из пустых строк ДО 63-й, и что вообще лежит в
пустых строках (может, там всё-таки что-то есть — например, только ID без
имени, или формат ячейки без значения).

Запуск: python3 debug_sheet_count2.py
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
scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
client = gspread.authorize(creds)
ws = client.open_by_key(SHEET_ID).sheet1

all_values = ws.get_all_values()
print(f"Всего строк: {len(all_values)} (включая заголовок, строка 1)")

blank_rows = []
named_rows = []
for i, row in enumerate(all_values[1:], start=2):
    has_any_content = any(cell.strip() for cell in row) if row else False
    name = row[1].strip() if len(row) > 1 else ""
    if name:
        named_rows.append(i)
    elif has_any_content:
        print(f"  строка {i}: имя пустое, НО есть другие данные: {row[:5]}")
    else:
        blank_rows.append(i)

print(f"\nСтрок с именем: {len(named_rows)} (диапазон: {named_rows[0]}-{named_rows[-1]})")
print(f"Полностью пустых строк: {len(blank_rows)}")
if blank_rows:
    print(f"Диапазон пустых строк: {blank_rows[0]}-{blank_rows[-1]}")
    # Есть ли пустые строки ВНУТРИ диапазона именованных (не в самом хвосте)?
    gaps_inside = [r for r in blank_rows if r < named_rows[-1]]
    if gaps_inside:
        print(f"⚠️ Пустые строки ВНУТРИ диапазона данных (не в хвосте): {gaps_inside}")
    else:
        print("Все пустые строки идут одним блоком в хвосте после последней именованной.")

print(f"\nПоследние 5 именованных компаний (перед пустым хвостом):")
for i in named_rows[-5:]:
    row = all_values[i - 1]
    print(f"  строка {i}: id={row[0]} name='{row[1]}'")
