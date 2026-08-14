"""
Бэкофилл email для уже существующих ~92 компаний в каталоге — 14.08.2026.
Колонку 32 (AF, "Email") нужно завести один раз ДО запуска этого скрипта
(см. add_email_column.py) — сам этот скрипт колонку не создаёт, только
пишет в неё.

Для каждой компании с пустым email (кроме id:1, MY Avto — см. ниже) пробует
источники по очереди, останавливаясь на первом успехе:
1. Собственный сайт компании (site, колонка L) — главная страница, а если
   там email не нашёлся, догружает подстраницы "Контакты"/"О нас" (та же
   логика, что и в company_agent.py, find_subpage_urls/fetch_extra_site_text).
2. Карточка 2ГИС (gis2, колонка U), если есть — иногда компания указывает
   почту прямо в профиле площадки.
3. Карточка Яндекс.Карт (yandex, колонка R), если есть — аналогично.

Ничего не выдумывает: extract_email() (см. company_agent.py) уже фильтрует
явный мусор (retina-картинки вида logo@2x.png, сервисные адреса Wix/Sentry/
Google и т.п., плейсхолдеры example.com) — не нашли ничего похожего на
реальный контактный email, поле остаётся пустым, никаких предположений.

Сайты, защищённые антиботом/капчей (looks_like_bot_wall), пропускаются с
пометкой "нужна ручная проверка" — то же самое, что уже делает
dryrun_reverify_sites.py для аналогичного случая.

id:1 (MY Avto) исключён по той же причине, что и в других backfill-скриптах
(fix_backfill_from_sources.py и т.п.) — это единственная компания с данными,
подтверждёнными лично владельцем, автоматика её не трогает.

Запуск (после add_email_column.py): python3 fix_backfill_emails.py
После — python3 update_site.py (email нигде не отображается на самом
сайте — это приватное поле только для онбординга/рассылки, но
update_site.py всё равно нужно прогнать, если менялись другие поля).
"""
import time

from company_agent import (
    connect_sheets, extract_email, fetch_site_text, fetch_extra_site_text,
    looks_like_bot_wall,
)

ID_COL = 1
NAME_COL = 2
SITE_COL = 12
YANDEX_COL = 18
GIS2_COL = 21
EMAIL_COL = 32

ws = connect_sheets()

header = ws.cell(1, EMAIL_COL).value
if not header:
    print(f"Колонка {EMAIL_COL} (AF) ещё не создана — сначала запусти "
          f"python3 add_email_column.py")
    raise SystemExit(1)

all_values = ws.get_all_values()

found_site, found_2gis, found_yandex, bot_wall, not_found = 0, 0, 0, 0, 0

for i, row in enumerate(all_values[1:], start=2):
    def val(col):
        return row[col - 1].strip() if len(row) >= col else ""

    company_id = val(ID_COL)
    name = val(NAME_COL)
    existing_email = val(EMAIL_COL)
    if not name or existing_email:
        continue
    if company_id == "1":
        continue

    site = val(SITE_COL)
    gis2 = val(GIS2_COL)
    yandex = val(YANDEX_COL)

    email = ""
    source = ""

    if site:
        html = fetch_site_text(site)
        if html and looks_like_bot_wall(html):
            print(f"[{i}] {name}: сайт {site} защищён антиботом/капчей — нужна ручная проверка")
            bot_wall += 1
            continue
        if html:
            email = extract_email(html)
            if not email:
                extra = fetch_extra_site_text(html, site)
                if extra:
                    email = extract_email(extra)
            if email:
                source = "сайт"

    if not email and gis2:
        html = fetch_site_text(gis2)
        if html:
            email = extract_email(html)
            if email:
                source = "2ГИС"

    if not email and yandex:
        html = fetch_site_text(yandex)
        if html:
            email = extract_email(html)
            if email:
                source = "Яндекс.Карты"

    if email:
        ws.update_cell(i, EMAIL_COL, email)
        print(f"[{i}] {name}: {email} (источник: {source})")
        if source == "сайт":
            found_site += 1
        elif source == "2ГИС":
            found_2gis += 1
        else:
            found_yandex += 1
    else:
        not_found += 1

    time.sleep(0.5)

print(f"\nИтого: найдено на сайте — {found_site}, в 2ГИС — {found_2gis}, "
      f"в Яндекс.Картах — {found_yandex}, антибот/капча (нужна ручная проверка) — {bot_wall}, "
      f"не нашлось — {not_found}")
print("\nТеперь прогони python3 update_site.py.")
