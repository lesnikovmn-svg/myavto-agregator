"""
Добавляет ДВЕ новые компании, найденные при разборе жалобы пользователя
на карточку "Авто из Европы / Авто Импорт ПРО" (там ошибочно оказались
чужие VK/сайт — см. fix_auto_import_cars_rus.py). Оба варианта оказались
реальными, но СОВЕРШЕННО ДРУГИМИ компаниями — проверено на их же
официальных сайтах (сайты сами перечисляют полный список своих соцсетей,
это максимально надёжный источник).

1. Antares Auto / Антарес Авто (antaresjp.ru) — авто из Японии/Кореи/Китая,
   Владивосток, на рынке с 2013 (ОГРН 1132537005061).
2. American Auto (americanauto.ru) — авто из США/Европы/Кореи, Москва,
   ООО «АмериканАвто», ИНН 9714022616, ОГРН 1237700697035, с 2013 года.

Запуск: python3 add_antares_and_american.py
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

NEW_COMPANIES = [
    {
        "name": "Antares Auto",
        "description": ("Доставка автомобилей с аукционов Японии, а также из Кореи и Китая. "
                         "Фиксированная комиссия, договор, юридическая чистота сделки. "
                         "На рынке с 2013 года."),
        "directions": ["Япония", "Корея", "Китай"],
        "tags": ["С аукциона", "Растаможка под ключ"],
        "telegram": "antaresavto",
        "phone": "8 (800) 550 21 91",
        "site": "https://antaresjp.ru/",
        "years": "13",
        "gis2": "https://2gis.ru/vladivostok/firm/70000001007465714",
        "instagram": "https://www.instagram.com/antaresauto/",
        "vk": "https://vk.com/antaresauto",
        "youtube": "https://www.youtube.com/antaresavto",
        "rutube": "https://rutube.ru/u/AntaresAvto/",
        "whatsapp": "https://wa.me/79025058595",
        "max": "https://max.ru/id253714921433_biz",
    },
    {
        "name": "American Auto",
        "description": ("Премиальные автомобили из США, Европы и Кореи под заказ, в наличии "
                         "и в пути. Подбор, расчёт стоимости, доставка, таможня и оформление. "
                         "Автосалон в Москве."),
        "directions": ["США", "Европа", "Корея"],
        "tags": ["В наличии", "Под заказ"],
        "telegram": "+vh2LRsR6Y4VjNzNi",
        "phone": "+7 991 640-51-59",
        "site": "https://americanauto.ru/",
        "inn": "9714022616",
        "years": "13",
        "vk": "https://vk.com/americanautomsk",
        "youtube": "https://www.youtube.com/@americanauto_msk",
        "rutube": "https://rutube.ru/channel/42939696/",
    },
]

next_id = len(all_values)
for data in NEW_COMPANIES:
    if data["name"].strip().lower() in existing_names:
        print(f"«{data['name']}» уже есть в таблице — пропускаю.")
        continue
    next_id += 1
    add_company(ws, data, next_id)
    existing_names.add(data["name"].strip().lower())

print("\nТеперь прогони python3 update_site.py.")
