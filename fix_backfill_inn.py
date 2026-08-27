"""
T-93 (27.08.2026): добор ИНН для карточек без него — по запросу пользователя
("нужно бейджами заняться и добавить во все карточки, не везде есть").

Зелёный бейдж "✓ В ЕГРЮЛ с ... года" (вместо базового "✓ Проверена
активность") ставится в update_site.py ТОЛЬКО если у компании заполнен
ИНН и verify_egrul.lookup_inn() смог его подтвердить (см. verify_egrul.py).
Companies без ИНН вообще не участвуют в проверке — не "не прошли", а
никогда не пытались, потому что extract_inn() не нашёл ИНН при первом
добавлении (например, компания найдена через Telegram-канал, а не через
сайт — ветка кода вообще не заходит на сайт компании, тот же класс
причины, что был у Delivery Cars в T-87/T-89).

Этот скрипт НЕ трогает бейдж напрямую — он просто донаходит ИНН у уже
существующих компаний (у которых есть свой сайт, но пустая колонка ИНН),
перечитывая сайт + подстраницы (Контакты/О нас) тем же способом, что и
при первом добавлении (extract_inn + fetch_extra_site_text). Найденный
ИНН реально проверится и покажет бейдж только на следующем прогоне
update_site.py (там уже есть вся логика верификации).

Запускать НА VPS (нужен доступ к Google Sheets и к сайтам компаний):
    cd /var/www/myavto-agregator
    python3 fix_backfill_inn.py
    python3 update_site.py
"""

from sheets_client import connect_sheets
from company_agent import extract_inn, fetch_site_text, fetch_extra_site_text

COL_NAME = 1
COL_SITE = 11
COL_INN = 18


def main():
    ws = connect_sheets()
    all_values = ws.get_all_values()

    candidates = []
    for i, row in enumerate(all_values[1:], start=2):
        name = row[COL_NAME].strip() if len(row) > COL_NAME else ""
        site = row[COL_SITE].strip() if len(row) > COL_SITE else ""
        inn = row[COL_INN].strip() if len(row) > COL_INN else ""
        if name and site and site.startswith("http") and not inn:
            candidates.append((i, name, site))

    print(f"Компаний с сайтом, но без ИНН: {len(candidates)}")

    found = 0
    for row_num, name, site in candidates:
        try:
            html = fetch_site_text(site)
            inn = extract_inn(html) if html else ""
            if not inn and html:
                extra = fetch_extra_site_text(html, site)
                if extra:
                    inn = extract_inn(extra)
            if inn:
                ws.update_cell(row_num, COL_INN + 1, inn)
                print(f"  НАШЁЛ: {name} ({site}) -> ИНН {inn}")
                found += 1
            else:
                print(f"  не найден: {name} ({site})")
        except Exception as e:
            print(f"  ⚠️ ошибка на {name} ({site}): {e}")

    print(f"Готово: донайдено {found} из {len(candidates)}. Дальше: python3 update_site.py")


if __name__ == "__main__":
    main()
