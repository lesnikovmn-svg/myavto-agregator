"""
Добавляет новую компанию "Антон Бай" по данным, которые пользователь
прислал вручную (Instagram-профиль, Telegram, телефон/WhatsApp) плюс то,
что нашлось в открытом поиске (подбор и доставка авто из Грузии/Армении в
Россию и СНГ). Официального сайта нет (два похожих домена в поиске не
отдали контент, пользователь подтвердил — сайта нет, только соцсети).

Источники:
- Instagram: https://www.instagram.com/anton_buy_auto/ (прислал пользователь)
- Telegram: https://t.me/antonbuyauto (прислал пользователь)
- Телефон/WhatsApp: +7 964 854 55 00 (из био Instagram, прислал пользователь:
  "По вопросам приобретения авто звонить и писать строго на What's App")
- Направления (Грузия/Армения) — из открытого поиска, не от пользователя
  напрямую, поэтому НЕ дозаполняем 2ГИС/Яндекс/VK — не искали и не
  подтверждали, честнее оставить пустыми, чем гадать.

Запуск: python3 add_anton_buy.py
После — python3 update_site.py.
"""
import gspread
from google.oauth2.service_account import Credentials
from company_agent import add_company

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
existing_names = {row[1].strip().lower() for row in all_values[1:] if len(row) > 1 and row[1]}
if "антон бай" in existing_names:
    print("«Антон Бай» уже есть в таблице — не добавляю повторно.")
else:
    next_id = len(all_values)  # header считается как строка 1, следующий id = текущее кол-во строк
    data = {
        "name": "Антон Бай",
        "description": ("Подбор и доставка автомобилей из Грузии и Армении в Россию и СНГ, "
                         "растаможка под ключ."),
        "directions": ["Грузия", "Армения"],
        "tags": ["Подбор авто", "Растаможка под ключ"],
        "telegram": "antonbuyauto",
        "phone": "+7 964 854 55 00",
        "site": "",
        "instagram": "https://www.instagram.com/anton_buy_auto/",
        "whatsapp": "https://wa.me/79648545500",
        "years": "1",
    }
    add_company(ws, data, next_id)
    print(f"Добавлена компания «Антон Бай» под id {next_id}.")

print("Теперь прогони python3 update_site.py.")
