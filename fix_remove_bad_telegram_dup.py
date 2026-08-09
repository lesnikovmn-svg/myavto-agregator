"""
Разовый фикс: последний прогон company_agent.py добавил один и тот же
Telegram-канал (@auto_import_cars_ru, 9590 подписчиков, "Авто из Европы /
Авто Импорт") ДВАЖДЫ под разными именами — одна запись с багованным именем
"Telegram: View @auto_import_cars_ru" (сырой <title> превью-страницы t.me,
а не og:title с настоящим названием) и одна с правильным именем "Авто из
Европы / Авто Импорт". Дедуп не сработал, т.к. сравнивал разные строки.

Причина бага в company_agent.py уже исправлена (для t.me-ссылок теперь
берём og:title через fetch_telegram_preview(), а не сырой заголовок из
поисковой выдачи) — это разовая ручная чистка уже попавшей в таблицу строки.

Удаляем только запись с багованным именем, вторую (корректную) оставляем.

Запуск: python3 fix_remove_bad_telegram_dup.py
После — python3 update_site.py.
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
BAD_NAME = "Telegram: View @auto_import_cars_ru"

scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
client = gspread.authorize(creds)
ws = client.open_by_key(SHEET_ID).sheet1

rows = ws.get_all_values()
row_idx = None
for i, row in enumerate(rows[1:], start=2):
    if len(row) > 1 and row[1].strip() == BAD_NAME:
        row_idx = i
        break

if row_idx is None:
    print(f"Строка с именем '{BAD_NAME}' не найдена — возможно, уже удалена.")
else:
    ws.delete_rows(row_idx)
    print(f"Удалена строка {row_idx} ('{BAD_NAME}') — дубликат канала @auto_import_cars_ru.")
    print("Правильная запись 'Авто из Европы / Авто Импорт' осталась в каталоге.")
    print("Теперь прогони python3 update_site.py.")
