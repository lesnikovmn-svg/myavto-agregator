"""
Диагностика (read-only): полный список компаний с ДУБЛИРУЮЩИМИСЯ id — тот
самый давно известный баг (см. PROJECT_STATE.md), замеченный ещё в
check_all_sites.py и снова всплывший в check_ooo_vs_ip.py (18.08.2026:
[62], [73], [74] встретились по два раза каждый). Матчинг на сайте и во
всех скриптах всегда идёт по НАЗВАНИЮ, не по id — поэтому сайт от этого не
ломается, но сами id в таблице всё равно нечестные (два разных id=62 —
это как два человека с одним паспортом).

Печатает группы дублей с полной строкой (id/name/site/telegram/inn), чтобы
решить, каким компаниям присвоить новый уникальный id. Ничего не меняет.

Запуск: python3 check_duplicate_ids.py
"""

from collections import defaultdict
from company_agent import connect_sheets

ID_COL = 1
NAME_COL = 2
SITE_COL = 12
TELEGRAM_COL = 10
INN_COL = 19

ws = connect_sheets()
all_values = ws.get_all_values()

by_id = defaultdict(list)
for i, row in enumerate(all_values[1:], start=2):

    def val(col):
        return row[col - 1].strip() if len(row) >= col and row[col - 1] else ""

    name = val(NAME_COL)
    if not name:
        continue
    cid = val(ID_COL)
    by_id[cid].append(
        {
            "row": i,
            "id": cid,
            "name": name,
            "site": val(SITE_COL),
            "telegram": val(TELEGRAM_COL),
            "inn": val(INN_COL),
        }
    )

dupes = {cid: rows for cid, rows in by_id.items() if len(rows) > 1}

if not dupes:
    print("Дублирующихся id не найдено.")
    raise SystemExit(0)

print(
    f"Найдено {len(dupes)} id-значений с дублями (всего {sum(len(v) for v in dupes.values())} строк):\n"
)
for cid, rows in sorted(dupes.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0):
    print(f"id={cid}:")
    for r in rows:
        print(
            f"  строка {r['row']}: {r['name']} | site={r['site'] or '—'} | telegram={r['telegram'] or '—'} | inn={r['inn'] or '—'}"
        )
    print()

max_id = max((int(v) for v in by_id if v.isdigit()), default=0)
print(
    f"Максимальный текущий id: {max_id}. Новым id для лишних дублей логично брать {max_id + 1}, {max_id + 2}, ..."
)
