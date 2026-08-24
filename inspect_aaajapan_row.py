"""
Только ЧИТАЕТ, ничего не пишет. В карточке с id=71 name оказался буквально
"https://aaajapan.com/" (ссылка вместо названия) — не похоже на обычный
баг заполнения имени (там были бы либо og:site_name/apple-title, либо
Title-Cased домен, либо кусок заголовка выдачи — не сырая ссылка).
Похоже на сдвиг колонок (как история с 29 битыми строками, см.
PROJECT_STATE.md, задача #21) — печатаем ВСЕ поля строки целиком, чтобы
понять природу бага, прежде чем чинить.

Запуск: python3 inspect_aaajapan_row.py
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

HEADERS = [
    "id",
    "name",
    "rating",
    "reviews",
    "years",
    "delivered",
    "description",
    "directions",
    "tags",
    "telegram",
    "phone",
    "site",
    "manager",
    "region",
    "featured",
    "avatar",
    "color",
    "yandex",
    "inn",
    "google",
    "gis2",
    "instagram",
    "vk",
    "avito",
    "drom",
    "autoru",
    "max",
    "youtube",
    "rutube",
    "whatsapp",
]

all_values = ws.get_all_values()

for i, row in enumerate(all_values[1:], start=2):
    joined = " ".join(row).lower()
    if "aaajapan" in joined:
        print(f"[{i}] найдена строка (всего колонок: {len(row)}, ожидается {len(HEADERS)})\n")
        for idx in range(max(len(row), len(HEADERS))):
            header = HEADERS[idx] if idx < len(HEADERS) else f"col{idx+1}(лишняя!)"
            val = row[idx] if idx < len(row) else "(пусто/нет колонки)"
            print(f"  {idx+1:2d}. {header:12s}: {val!r}")
        print()
