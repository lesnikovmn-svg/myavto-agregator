"""
Смотрим историю версий таблицы через Drive API — нужно достать данные
удалённых строк (AviAuto, CarExport, LimCars, AutoImport Russia, EncarRus,
ПримАвто, ТокиДоки) ДО последнего запуска fix_generic_names_final.py,
похоже, у части восстановленных строк поля site/telegram были перепутаны
местами (отсюда странные "дубли" по домену: ПримАвто как будто совпала с
vk.ru, хотя её настоящий сайт prim-auto.com).

Запуск: python3 list_sheet_revisions.py
"""
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

r = requests.get(
    f"https://www.googleapis.com/drive/v3/files/{SHEET_ID}/revisions",
    params={"fields": "revisions(id,modifiedTime,size,exportLinks)"},
    headers=headers,
    timeout=15,  # T-73 (21.08.2026): без timeout запрос мог зависнуть навсегда
)
print("HTTP", r.status_code)
data = r.json()
if "revisions" not in data:
    print(data)
else:
    for rev in data["revisions"]:
        has_export = "exportLinks" in rev
        print(f"id={rev['id']}  modified={rev['modifiedTime']}  export_available={has_export}")
