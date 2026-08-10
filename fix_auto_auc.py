"""
⚠️ ПЕРЕД ЗАПУСКОМ: поставь именованную версию в Google Sheets — Файл →
История версий → Назвать текущую версию → «до fix_auto_auc» → Сохранить.
(см. PROJECT_STATE.md, раздел "Конвенция: именованная версия перед
fix-скриптами" — так можно откатиться в один клик, если что-то не так).

Карточка "Auto-Auc" (site: auto-auc.online, id:62 в таблице) — сайт
защищён антиботом/капчей, агент не смог прочитать его сам (см. 🚧-пометку
в PROJECT_STATE.md), поэтому имя получилось из домена ("Auto-Auc"), а все
остальные поля остались пустыми.

Пользователь зашёл на сайт вручную и прислал содержимое страницы
"Контакты" (10.08.2026): адрес (г. Омск, Красноярский тракт, 53), ИП
Грудцына Полина Владимировна, ИНН 550114534690, ОГРНИП 325554300023791,
WhatsApp +7 995 354 57 25, ссылки на Яндекс.Карты, 2ГИС и VK.

Проверено по присланной 2ГИС-карточке (2gis.ru/omsk/firm/70000001074988575,
518 отзывов, оценка 5, "данные актуальны") — телефон и адрес СОВПАДАЮТ с
тем, что прислал пользователь, значит это точно та же компания:
- Настоящее название: "Япония Экспорт" (бренд одинаковый везде — VK
  vk.com/japanexport, Max max.ru/japanexport, домен japanexport55.ru;
  2ГИС в заголовке добавляет город: "Япония Экспорт Омск" — это SEO-
  суффикс листинга, не часть названия).
- YouTube: youtube.com/channel/UCuMPfSQkjN1r96fypL4N-hw
- Max: max.ru/japanexport
- Направления: Япония, Корея, Китай (аукционы) — совпадает и с описанием
  в самой таблице, и с 2ГИС.

Telegram НЕ заполняем — на 2ГИС и на сайте это просто инвайт-ссылка на
приватный чат (t.me/+79953545725), не публичный @username, под формат
колонки не подходит.

Сайт (auto-auc.online) не меняем — пользователь прислал это как реальный
сайт компании (страница "Контакты" с ИНН/ОГРНИП сходится), у компании
может быть и второй домен (japanexport55.ru), не наша забота выбирать,
какой основной.

Запуск: python3 fix_auto_auc.py
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

NAME_COL, DIRECTIONS_COL, PHONE_COL, SITE_COL = 2, 8, 11, 12
INN_COL = 19
YANDEX_COL, GIS2_COL, VK_COL = 18, 21, 23
MAX_COL, YOUTUBE_COL, WHATSAPP_COL = 27, 28, 30

UPDATES = {
    NAME_COL: "Япония Экспорт",
    DIRECTIONS_COL: "Япония,Корея,Китай",
    PHONE_COL: "+7 995 354 57 25",
    INN_COL: "550114534690",
    YANDEX_COL: "https://yandex.ru/maps/-/CTWUyH8j",
    GIS2_COL: "https://2gis.ru/omsk/firm/70000001074988575",
    VK_COL: "https://vk.ru/japanexport",
    MAX_COL: "https://max.ru/japanexport",
    YOUTUBE_COL: "https://youtube.com/channel/UCuMPfSQkjN1r96fypL4N-hw",
    WHATSAPP_COL: "https://wa.me/79953545725",
}

all_values = ws.get_all_values()
row_i = None
for i, row in enumerate(all_values[1:], start=2):
    site = row[SITE_COL - 1].strip().lower() if len(row) >= SITE_COL else ""
    if "auto-auc.online" in site:
        row_i = i
        old_row = row
        break

if not row_i:
    print("Карточку с сайтом auto-auc.online не нашёл.")
else:
    print(f"[{row_i}] найдена карточка, было name: '{old_row[1]}'\n")
    for col, new_val in UPDATES.items():
        old_val = old_row[col - 1].strip() if len(old_row) >= col and old_row[col - 1] else ""
        ws.update_cell(row_i, col, new_val)
        print(f"  col {col}: '{old_val}' -> '{new_val}'")
    print("\nSite и telegram не трогал (см. docstring).")

print("\nТеперь прогони python3 update_site.py.")
