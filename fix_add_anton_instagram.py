"""
Пользователь: "карточка уже была, добавь инстаграм" — то есть "Антон Бай"
уже есть в каталоге (не новая компания, как предполагалось раньше — тот
черновик add_anton_buy.py не запускать, он создал бы дубль).

Ищем существующую строку по совпадению телефона (+7 964 854 55 00) или
telegram-юзернейма (antonbuyauto) — это надёжнее, чем угадывать точное
название карточки. Если найдётся ровно одна — дозаполняем ТОЛЬКО instagram
(и, если он там пустой, заодно WhatsApp — тот же номер, что и телефон,
указан пользователем как "звонить и писать строго на WhatsApp" — но НЕ
трогаем telegram/phone/name, если они уже заполнены чем-то другим).

Instagram: https://www.instagram.com/anton_buy_auto/ (прислал пользователь).

Запуск: python3 fix_add_anton_instagram.py
После — python3 update_site.py.
"""
import re
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

NAME_COL, TELEGRAM_COL, PHONE_COL = 2, 10, 11
INSTAGRAM_COL = 22
WHATSAPP_COL = 30

TARGET_PHONE_DIGITS = "79648545500"
TARGET_TELEGRAM = "antonbuyauto"
INSTAGRAM_URL = "https://www.instagram.com/anton_buy_auto/"
WHATSAPP_URL = "https://wa.me/79648545500"

all_values = ws.get_all_values()


def cell(row, col_1idx):
    idx = col_1idx - 1
    return row[idx].strip() if len(row) > idx and row[idx] else ""


matches = []
for i, row in enumerate(all_values[1:], start=2):
    name = cell(row, NAME_COL)
    if not name:
        continue
    tg = cell(row, TELEGRAM_COL).lower()
    phone = cell(row, PHONE_COL)
    phone_digits = "".join(ch for ch in phone if ch.isdigit())
    if tg == TARGET_TELEGRAM or phone_digits == TARGET_PHONE_DIGITS:
        matches.append((i, name, row))

if not matches:
    print("Не нашёл существующую карточку ни по telegram (antonbuyauto), ни по телефону "
          "(+7 964 854 55 00). Уточни, пожалуйста, точное название карточки в каталоге.")
elif len(matches) > 1:
    print("Нашлось НЕСКОЛЬКО подходящих строк — не трогаю, разберись вручную:")
    for i, name, _ in matches:
        print(f"  [{i}] {name}")
else:
    i, name, row = matches[0]
    updates = []
    if not cell(row, INSTAGRAM_COL):
        ws.update_cell(i, INSTAGRAM_COL, INSTAGRAM_URL)
        updates.append("instagram")
    if not cell(row, WHATSAPP_COL):
        ws.update_cell(i, WHATSAPP_COL, WHATSAPP_URL)
        updates.append("whatsapp")
    if updates:
        print(f"[{i}] {name}: добавлено — {', '.join(updates)}")
    else:
        print(f"[{i}] {name}: instagram и whatsapp уже были заполнены, ничего не менял.")

print("\nТеперь прогони python3 update_site.py.")
