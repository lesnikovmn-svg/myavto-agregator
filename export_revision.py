"""
Экспортирует конкретную ревизию таблицы (Drive API) как CSV и печатает
строки для заданных названий компаний (или просто печатает всё, если имена
не переданы) — чтобы посмотреть, какие данные (сайт/телеграм) реально были
у компании до последних правок.

Запуск:
  python3 export_revision.py <revision_id> [имя1] [имя2] ...
Пример:
  python3 export_revision.py 209 AviAuto CarExport
  python3 export_revision.py 364          # напечатает все строки
"""
import sys
import csv
import io
import requests
import google.auth.transport.requests
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
creds.refresh(google.auth.transport.requests.Request())
headers = {"Authorization": f"Bearer {creds.token}"}

if len(sys.argv) < 2:
    print("Использование: python3 export_revision.py <revision_id> [имя1] [имя2] ...")
    raise SystemExit

revision_id = sys.argv[1]
target_names = [n.lower() for n in sys.argv[2:]]

meta = requests.get(
    f"https://www.googleapis.com/drive/v3/files/{SHEET_ID}/revisions/{revision_id}",
    params={"fields": "exportLinks,modifiedTime"},
    headers=headers,
    timeout=15,  # T-73 (21.08.2026): без timeout запрос мог зависнуть навсегда
).json()
print("Ревизия от", meta.get("modifiedTime"))
export_links = meta.get("exportLinks", {})
csv_url = export_links.get("text/csv")
if not csv_url:
    print("Нет ссылки на CSV-экспорт для этой ревизии.")
    print(meta)
    raise SystemExit

csv_resp = requests.get(csv_url, headers=headers, timeout=15)  # T-73: см. выше
reader = csv.reader(io.StringIO(csv_resp.text))
rows = list(reader)
print(f"Строк в ревизии: {len(rows)}")

header = rows[0] if rows else []
for i, row in enumerate(rows[1:], start=2):
    name = row[1].strip() if len(row) > 1 else ""
    if not name:
        continue
    if target_names and name.lower() not in target_names:
        continue
    print(f"\n--- строка {i}: '{name}' ---")
    for col_idx, val in enumerate(row):
        if val.strip():
            col_name = header[col_idx] if col_idx < len(header) else f"col{col_idx}"
            print(f"    [{col_idx}] {col_name}: '{val}'")
