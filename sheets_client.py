"""
T-72 (21.08.2026): общий клиент для Google Sheets.

До этого модуля один и тот же блок — прочитать agent_config.env построчно
руками, собрать Credentials.from_service_account_file(...), сделать
gspread.authorize(...) — был скопипащен в 11+ файлах (company_agent.py,
telegram_bot_service.py, update_site.py, backup_sheets.py,
update_onboarding_dashboard.py, update_requests_dashboard.py и другие).
Любой фикс (смена scopes, добавление ретраев, кэширование клиента) нужно
было вносить в каждом файле отдельно — часть неизбежно забывалась бы.

Публичный API специально совпадает с тем, что раньше жило в
company_agent.py (connect_sheets/connect_reviews_sheet/SHEET_ID/
REVIEWS_HEADER), чтобы все существующие `from company_agent import ...`
в других файлах продолжали работать без изменений — company_agent.py
теперь просто реэкспортирует эти имена отсюда (см. его собственный
docstring рядом с импортом).

Использование:
    from sheets_client import connect_sheets, connect_reviews_sheet
    ws = connect_sheets()            # главный лист компаний (sheet1)
    reviews_ws = connect_reviews_sheet()  # вкладка "Отзывы"
"""
import os

import gspread
from google.oauth2.service_account import Credentials

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def load_env(path="agent_config.env"):
    """Тот же формат KEY=VALUE построчно, что уже использовался везде —
    не меняем формат конфигов, только убираем дублирование парсера."""
    config = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    config[k.strip()] = v.strip()
    return config


_config = load_env()
SHEET_ID = os.environ.get("SHEET_ID") or _config.get("SHEET_ID", "")

_client = None  # кэш авторизованного клиента на процесс — не переавторизуемся на каждый вызов


def get_client():
    global _client
    if _client is None:
        creds = Credentials.from_service_account_file("credentials.json", scopes=_SCOPES)
        _client = gspread.authorize(creds)
    return _client


def connect_sheets():
    """Главный лист компаний (первая вкладка таблицы, sheet1)."""
    return get_client().open_by_key(SHEET_ID).sheet1


# Отзывы — отдельная вкладка "Отзывы" той же таблицы (17.08.2026, нативные
# отзывы вместо редиректа на сторонние площадки). Схема не менялась при
# переносе сюда — только источник импорта.
REVIEWS_SHEET_TITLE = "Отзывы"
REVIEWS_HEADER = ["id", "company_id", "company_name", "author_name", "rating", "text", "status", "created_at", "contact"]


def connect_reviews_sheet():
    """Возвращает вкладку "Отзывы" — создаёт её с заголовком, если это
    первый запуск и вкладки ещё нет."""
    sh = get_client().open_by_key(SHEET_ID)
    try:
        ws = sh.worksheet(REVIEWS_SHEET_TITLE)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=REVIEWS_SHEET_TITLE, rows=500, cols=len(REVIEWS_HEADER))
        ws.append_row(REVIEWS_HEADER)
    return ws
