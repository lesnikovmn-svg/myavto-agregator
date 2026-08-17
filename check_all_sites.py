"""
Диагностика (read-only): полный список компаний с id/site/telegram/текущим
avatar — 17.08.2026, нужен для точечного скрипта проставления реальных
логотипов по всему каталогу (см. fix_add_autozakaz.py и avatarHtml в
index.html, тот же принцип: URL картинки в avatar вместо 2-3-буквенных
инициалов). Ничего не меняет, только печатает.

Печатает по одной строке на компанию: id, name, site, telegram, и есть ли
уже картиночный avatar (has_logo=True/False — True, если текущее значение
avatar уже начинается на "http").

Запуск: python3 check_all_sites.py
"""
from company_agent import connect_sheets

ID_COL = 1
NAME_COL = 2
SITE_COL = 12
TELEGRAM_COL = 10
AVATAR_COL = 16

ws = connect_sheets()
all_values = ws.get_all_values()

for row in all_values[1:]:
    def val(col):
        return row[col - 1].strip() if len(row) >= col else ""

    company_id = val(ID_COL)
    name = val(NAME_COL)
    if not name:
        continue

    site = val(SITE_COL)
    telegram = val(TELEGRAM_COL)
    avatar = val(AVATAR_COL)
    has_logo = avatar.lower().startswith("http")

    print(f"[{company_id}] {name} | site={site or '—'} | telegram={telegram or '—'} | has_logo={has_logo}")

print(f"\nВсего компаний: {sum(1 for row in all_values[1:] if row and row[1].strip())}")
