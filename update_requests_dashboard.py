"""
Отдельная вкладка "Заявки" в Google Таблице — сводка по заявкам клиентов
на просчёт (те, что приходят через POST /api/mass-request и живут в
bot_state.json на VPS, см. telegram_bot_service.py). 14.08.2026, по
запросу пользователя ("где мне отслеживать заявки клиентов на просчет?").

Сейчас единственное "хранилище" заявок — bot_state.json на VPS (поле
"requests" — ключи это request_id, значения включают имя/телефон/email/
направление/бюджет/что ищет/подтвердил ли клиент (client_chat_id)/каким
компаниям разослали). В саму Google Таблицу заявки не попадают вообще —
эта вкладка просто даёт человеческий, читаемый снимок того, что в
bot_state.json, по аналогии с "Онбординг" (update_onboarding_dashboard.py).

Также напоминание (см. docstring telegram_bot_service.py): если в
bot_config.env заполнить ADMIN_CHAT_ID (и/или ADMIN_GROUP_CHAT_ID) —
владелец получает копию каждого события (новая заявка, подтверждение
клиентом, ответ компании) прямо в Telegram В МОМЕНТ, когда это
происходит — не нужно ничего запускать руками. Эта вкладка полезна как
"снимок на сейчас"/архив, а не замена живым уведомлениям.

Запускать лучше НА VPS (там bot_state.json всегда свежий), либо скопировать
файл на Мак: scp root@89.108.70.185:/var/www/myavto-agregator/bot_state.json .

Каждый запуск полностью перезаписывает вкладку "Заявки" (безопасно гонять
повторно).

Запуск: python3 update_requests_dashboard.py
"""
import datetime
import json
import os

import gspread
from google.oauth2.service_account import Credentials

from company_agent import SHEET_ID

DASHBOARD_TITLE = "Заявки"
BOT_STATE_FILE = "bot_state.json"

HEADER = ["ID заявки", "Дата", "Имя клиента", "Телефон", "Email",
          "Направление", "Бюджет", "Что ищет", "Клиент подтвердил?",
          "Компаний уведомлено", "Кому разослано"]


def connect_spreadsheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID)


if not os.path.exists(BOT_STATE_FILE):
    print(f"Не нашёл {BOT_STATE_FILE} в текущей папке.\n"
          f"Он лежит на VPS: /var/www/myavto-agregator/bot_state.json\n"
          f"Либо запусти этот скрипт по SSH прямо на VPS, либо скачай файл:\n"
          f"  scp root@89.108.70.185:/var/www/myavto-agregator/bot_state.json .")
    raise SystemExit(1)

with open(BOT_STATE_FILE, encoding="utf-8") as f:
    state = json.load(f)

requests_data = state.get("requests", {})

rows = [HEADER]
for req_id, r in sorted(requests_data.items(), key=lambda kv: kv[1].get("created_at", 0), reverse=True):
    created = r.get("created_at")
    date_str = datetime.datetime.fromtimestamp(created).strftime("%d.%m.%Y %H:%M") if created else ""
    confirmed = "Да" if r.get("client_chat_id") else "Нет (ссылку не открыл)"
    notified = r.get("companies_notified", [])
    rows.append([
        req_id, date_str, r.get("name", ""), r.get("phone", ""), r.get("email", ""),
        r.get("direction", ""), r.get("budget", ""), r.get("model", ""),
        confirmed, str(len(notified)), ", ".join(notified),
    ])

sh = connect_spreadsheet()
try:
    dash_ws = sh.worksheet(DASHBOARD_TITLE)
    dash_ws.clear()
except gspread.WorksheetNotFound:
    dash_ws = sh.add_worksheet(title=DASHBOARD_TITLE, rows=len(rows) + 10, cols=len(HEADER) + 2)

dash_ws.update(range_name="A1", values=rows)
dash_ws.format("A1:K1", {"textFormat": {"bold": True}})
dash_ws.freeze(rows=1)

confirmed_count = sum(1 for r in rows[1:] if r[8] == "Да")
print(f"Готово: вкладка '{DASHBOARD_TITLE}' обновлена — {len(rows) - 1} заявок.")
print(f"Подтверждено клиентом: {confirmed_count} из {len(rows) - 1}.")
print(f"\nСовет: заполни ADMIN_CHAT_ID в bot_config.env (см. его docstring) — "
      f"тогда о каждой новой заявке будешь узнавать сразу в Telegram, "
      f"без необходимости запускать этот скрипт.")
