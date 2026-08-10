"""
Карточка "Авто Азия" (site: auto-asia25.ru, id:63) — старая, попала в
таблицу ещё до нескольких фиксов, разобранных с пользователем позже, и
собрала сразу букет проблем того же класса багов:

1. name стал рекламным заголовком ("Автомобили с аукционов Японии с
   доставкой по России и странам СНГ") вместо настоящего названия
   "Авто Азия" (og:title сайта: 'Контакты компании "Авто Азия" —
   надёжный поставщик автомобилей с аукционов Японии") — тот же баг,
   что чинили для autoshoot.ru (is_probably_tagline), просто эта
   карточка старее фикса.
2. phone был пустым ("-") — реальный номер +7 994 102 24 49 лежит на
   странице /contacts, а не на главной; company_agent.py обходит только
   главную страницу сайта, вглубь (на /contacts и т.п.) не ходит — номер
   и юридические реквизиты (ИНН/ОГРН/БИК/адрес ИП) с таких подстраниц
   агент вообще не видит.
3. telegram оказался ЧУЖОЙ — "hotcar25". Это телеграм другой компании,
   "Нotcar.online" (подбор авто, отдельная карточка в 2ГИС по адресу
   Снеговая, 2Б — рядом с "Авто Азия"). vk (vk.com/public171545853) и
   2ГИС в текущей строке тоже принадлежат Нotcar.online, не "Авто Азия"
   — проверено напрямую на странице их 2ГИС-карточки.
4. avito/drom/autoru — тоже мусор, не профили компании: avito — ссылка
   на общий поиск ("...avtomobili?q=из+японии..."), drom — ссылка на
   листинг ("auto.drom.ru/all/page5/..."), autoru — вообще левый домен
   sunrise-auto.ru (не auto.ru).

Верно (подтверждено содержимым auto-asia25.ru/contacts): site, instagram
(auto_azia), youtube (channel/UC4VL7w6...), whatsapp (79941022449) —
эти поля не трогаем.

Правим: name, years (сайт: "© 2014-2025 Auto-Asia" — на рынке с 2014,
~12 лет), directions (было "Не указано" → "Япония"), telegram, phone,
inn. Чистим чужие/мусорные: gis2, vk, avito, drom, autoru — сначала
убираем чужое, потом (по желанию) можно будет заново подтвердить через
python3 fix_reverify_after_key_fix.py или вручную.

Запуск: python3 fix_avto_aziya.py
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

NAME_COL, YEARS_COL, DIRECTIONS_COL = 2, 5, 8
TELEGRAM_COL, PHONE_COL, SITE_COL = 10, 11, 12
INN_COL = 19
GIS2_COL, INSTAGRAM_COL, VK_COL = 21, 22, 23
AVITO_COL, DROM_COL, AUTORU_COL = 24, 25, 26

UPDATES = {
    NAME_COL: "Авто Азия",
    YEARS_COL: "12",
    DIRECTIONS_COL: "Япония",
    TELEGRAM_COL: "autoasia25",
    PHONE_COL: "+7 994 102 24 49",
    INN_COL: "253913363430",
    GIS2_COL: "",
    VK_COL: "",
    AVITO_COL: "",
    DROM_COL: "",
    AUTORU_COL: "",
}

all_values = ws.get_all_values()
row_i = None
for i, row in enumerate(all_values[1:], start=2):
    site = row[SITE_COL - 1].strip().lower() if len(row) >= SITE_COL else ""
    if "auto-asia25.ru" in site:
        row_i = i
        old_row = row
        break

if not row_i:
    print("Карточку с сайтом auto-asia25.ru не нашёл.")
else:
    print(f"[{row_i}] найдена карточка, было name: '{old_row[1]}'\n")
    for col, new_val in UPDATES.items():
        old_val = old_row[col - 1].strip() if len(old_row) >= col and old_row[col - 1] else ""
        ws.update_cell(row_i, col, new_val)
        print(f"  col {col}: '{old_val}' -> '{new_val}'")
    print("\nНе трогал: site, instagram, youtube, whatsapp — подтверждены содержимым сайта.")

print("\nТеперь прогони python3 update_site.py.")
