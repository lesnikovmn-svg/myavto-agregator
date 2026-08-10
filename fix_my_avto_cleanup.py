"""
Пользователь сообщил: на карточке MY Avto (id:1, компания САМОГО АВТОРА)
всё ещё/снова показывались ДВЕ чужие ссылки:
- 2ГИС: https://2gis.ru/vladivostok/firm/70000001110946107 (та же
  владивостокская фирма, что уже помечалась как неверная)
- Сайт: https://my-auto.ru/ (чужой домен, случайно похожий на
  "myavto-agregator.ru" — почти наверняка это и есть САЙТ ТОЙ САМОЙ
  неверной владивостокской 2ГИС-карточки: когда первый (ещё незащищённый)
  прогон fix_backfill_from_sources.py ложно принял её как карточку MY
  Avto из-за слишком общего ключа "my", он заодно и утащил её "сайт" —
  ровно то, для чего и был задуман backfill_from_sources: дозаполнять
  ВСЁ, что не нашлось другими способами).

gis2 для MY Avto уже чистился в fix_reverify_after_key_fix.py — этот
скрипт чистит его ещё раз на всякий случай (идемпотентно, не страшно) и
ВПЕРВЫЕ чистит site — его раньше не трогали (fix_reverify_after_key_fix.py
не проверяет поле site вообще, а backfill-скрипты после этого случая уже
исключают id:1, но этот конкретный испорченный site остался с самого
первого, ещё незащищённого прогона).

MY Avto (id:1) — единственная компания с данными, подтверждёнными лично
владельцем, поэтому это ТОЧЕЧНЫЙ ручной фикс по конкретному репорту
пользователя, а не автоматический проход.

Запуск: python3 fix_my_avto_cleanup.py
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

ID_COL, NAME_COL, SITE_COL = 1, 2, 12
GIS2_COL = 21

BAD_GIS2_MARKER = "70000001110946107"
BAD_SITE_MARKER = "my-auto.ru"

all_values = ws.get_all_values()
row_i = None
for i, row in enumerate(all_values[1:], start=2):
    cid = row[0].strip() if len(row) > 0 else ""
    name = row[1].strip() if len(row) > 1 else ""
    if cid == "1" or name.strip().lower() == "my avto":
        row_i = i
        row_data = row
        break

if not row_i:
    print("MY Avto не найдена в таблице.")
else:
    gis2 = row_data[GIS2_COL - 1].strip() if len(row_data) >= GIS2_COL else ""
    site = row_data[SITE_COL - 1].strip() if len(row_data) >= SITE_COL else ""
    cleared = []
    if BAD_GIS2_MARKER in gis2:
        ws.update_cell(row_i, GIS2_COL, "")
        cleared.append(f"2gis ({gis2})")
    if BAD_SITE_MARKER in site.lower():
        ws.update_cell(row_i, SITE_COL, "")
        cleared.append(f"site ({site})")
    if cleared:
        print(f"Строка {row_i}: MY Avto — очищено: {', '.join(cleared)}")
    else:
        print(f"Строка {row_i}: MY Avto — текущие значения gis2='{gis2}', site='{site}' "
              "не совпадают с известным мусором, ничего не тронул (проверь вручную).")

print("\nТеперь прогони python3 update_site.py.")
print("Если у MY Avto есть реальный сайт — впиши его в таблицу вручную (колонка L, site) —")
print("это твоя компания, скрипт его специально не подбирает.")
