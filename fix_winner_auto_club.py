"""
Пользователь лично подтвердил настоящие ссылки Winner Auto Club (после
того как автоматика ошибочно почистила VK/2ГИС и вписала мусор
"vk.com/rtrg" — см. PROJECT_STATE.md):
- VK: https://vk.ru/winnerautoclub
- Instagram: https://www.instagram.com/winner_auto_club/
- Яндекс.Карты: https://yandex.com/maps/-/CTSwuM8B
  (короткая ссылка разворачивается в
  https://yandex.com/maps/org/winner_auto_club/34609315219/ —
  проверено: Рустави, Грузия, телефон +995 511 29 92 99, совпадает с
  телефоном в Telegram/YouTube-канале компании +995 511 299 299)
- Telegram (найден отдельно, тоже с совпадающим телефоном): Winner_Auto_Club

2ГИС и старый VK (winnerautoclub — другой формат, не совпадал) НЕ трогаем —
их корректность не подтверждена, оставляем как есть/пустыми.

Запуск: python3 fix_winner_auto_club.py
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

scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
client = gspread.authorize(creds)
ws = client.open_by_key(SHEET_ID).sheet1

NAME_COL, TELEGRAM_COL = 2, 10
YANDEX_COL = 18
INSTAGRAM_COL, VK_COL = 22, 23

all_values = ws.get_all_values()
row_i = None
for i, row in enumerate(all_values[1:], start=2):
    name = row[1].strip() if len(row) > 1 else ""
    if name == "Winner Auto Club":
        row_i = i
        break

if not row_i:
    print("Winner Auto Club не найдена в таблице.")
else:
    ws.update_cell(row_i, TELEGRAM_COL, "Winner_Auto_Club")
    ws.update_cell(row_i, VK_COL, "https://vk.ru/winnerautoclub")
    ws.update_cell(row_i, INSTAGRAM_COL, "https://www.instagram.com/winner_auto_club/")
    ws.update_cell(row_i, YANDEX_COL, "https://yandex.com/maps/org/winner_auto_club/34609315219/")
    print(f"Строка {row_i}: Winner Auto Club — telegram/vk/instagram/yandex обновлены.")

print("Теперь прогони python3 update_site.py.")
