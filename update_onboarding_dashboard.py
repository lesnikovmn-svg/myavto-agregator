"""
Отдельная вкладка "Онбординг" в той же Google Таблице — сводная таблица
для отслеживания рассылки/онбординга компаний. 14.08.2026, по запросу
пользователя ("список получателей пришли, или нужна еще одна страница в
таблицах где можно видеть результаты рассылки, какая компания онборд,
а также личные контакты компаний для связи").

Собирает в одном месте (по каждой компании из основной вкладки):
- Название, телефон, email, TG-канал, личный TG-контакт (колонка AE —
  именно он нужен для "личные контакты компаний для связи").
- Отправлено ли ей email-приглашение (сверка с onboarding_emails_log.json
  — тем же логом, который ведёт send_onboarding_emails.py).
- Онбордилась ли она в боте, т.е. нажала ли /start (сверка с
  bot_state.json — тем же файлом, что и check_onboarded.py).

bot_state.json лежит только на VPS (/var/www/myavto-agregator/) — если
запускать этот скрипт на Маке без него рядом, колонка "Онбордился?" будет
показывать "Неизвестно" вместо "Да"/"Нет" (сама рассылка/сводка при этом
всё равно строится нормально). Чтобы видеть точный статус онбординга,
либо запускай на VPS, либо сначала скопируй файл на Мак:
  scp root@89.108.70.185:/var/www/myavto-agregator/bot_state.json .

Каждый запуск полностью перезаписывает вкладку "Онбординг" свежими
данными (безопасно гонять сколько угодно раз, вкладка — просто отчёт,
не источник данных).

Запуск: python3 update_onboarding_dashboard.py
"""

import json
import os

import gspread  # нужен для gspread.WorksheetNotFound ниже

# T-72 (21.08.2026): общий sheets_client.py вместо своей копии
# Credentials/gspread.authorize (см. его docstring).
from sheets_client import SHEET_ID, get_client

ID_COL = 1
NAME_COL = 2
TELEGRAM_COL = 10
PHONE_COL = 11
TG_CONTACT_COL = 31
EMAIL_COL = 32

DASHBOARD_TITLE = "Онбординг"
BOT_STATE_FILE = "bot_state.json"
LOG_FILE = "onboarding_emails_log.json"

HEADER = [
    "Компания",
    "Телефон",
    "Email",
    "TG-канал",
    "Личный TG-контакт",
    "Email отправлен?",
    "Онбордился в боте?",
]


def connect_spreadsheet():
    return get_client().open_by_key(SHEET_ID)


def load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


sh = connect_spreadsheet()
main_ws = sh.sheet1
all_values = main_ws.get_all_values()

bot_state_present = os.path.exists(BOT_STATE_FILE)
onboarded = set(load_json(BOT_STATE_FILE, {"companies": {}}).get("companies", {}).keys())
emailed = set(load_json(LOG_FILE, []))

rows = [HEADER]
for row in all_values[1:]:

    def val(col):
        return row[col - 1].strip() if len(row) >= col else ""

    company_id = val(ID_COL)
    name = val(NAME_COL)
    if not name or company_id == "1":
        continue

    phone = val(PHONE_COL)
    email = val(EMAIL_COL)
    telegram = val(TELEGRAM_COL)
    tgcontact = val(TG_CONTACT_COL)
    handle = telegram.lstrip("@").lower()

    email_sent = "Да" if email and email.lower() in emailed else "Нет"

    if not handle:
        onboard_status = "—"
    elif handle in onboarded:
        onboard_status = "Да"
    elif not bot_state_present:
        onboard_status = "Неизвестно (нет bot_state.json)"
    else:
        onboard_status = "Нет"

    rows.append([name, phone, email, telegram, tgcontact, email_sent, onboard_status])

try:
    dash_ws = sh.worksheet(DASHBOARD_TITLE)
    dash_ws.clear()
except gspread.WorksheetNotFound:
    dash_ws = sh.add_worksheet(title=DASHBOARD_TITLE, rows=len(rows) + 10, cols=len(HEADER) + 2)

dash_ws.update(range_name="A1", values=rows)
dash_ws.format("A1:G1", {"textFormat": {"bold": True}})
dash_ws.freeze(rows=1)

onboarded_count = sum(1 for r in rows[1:] if r[6] == "Да")
emailed_count = sum(1 for r in rows[1:] if r[5] == "Да")
print(f"Готово: вкладка '{DASHBOARD_TITLE}' обновлена — {len(rows) - 1} компаний.")
print(f"Email отправлен: {emailed_count}. Онбордились: {onboarded_count}.")
if not bot_state_present:
    print(
        f"\n({BOT_STATE_FILE} не найден рядом — колонка 'Онбордился?' "
        f"неточная, см. docstring про scp с VPS.)"
    )
