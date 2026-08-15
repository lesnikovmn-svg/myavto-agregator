"""
Диагностика сбора email по каталогу — 15.08.2026, по запросу пользователя
("проверь что со сбором почты"). Только ЧИТАЕТ таблицу, ничего не меняет
(в отличие от fix_backfill_emails.py/fix_clean_junk_emails.py).

Показывает:
1. Сколько компаний всего / с заполненным email / без email.
2. Список компаний БЕЗ email — как раз кандидаты на повторный прогон
   fix_backfill_emails.py (он трогает только пустые ячейки, безопасно
   гонять поверх уже собранных).
3. Быстрая проверка на подозрительный мусор — email домены, которые
   раньше уже ловились как ложные срабатывания (2gis.ru, maps.yandex.ru,
   example.ru, vk-portal.net, см. EMAIL_JUNK_DOMAINS в company_agent.py) —
   если такие вдруг снова всплыли, значит где-то прошёл сбор мимо
   extract_email() (например, ручная правка) и стоит перепроверить.

Запуск: python3 check_email_stats.py
"""
from company_agent import connect_sheets, EMAIL_JUNK_DOMAINS

ID_COL = 1
NAME_COL = 2
EMAIL_COL = 32

ws = connect_sheets()
all_values = ws.get_all_values()

with_email, without_email, junk_looking = [], [], []

for i, row in enumerate(all_values[1:], start=2):
    def val(col):
        return row[col - 1].strip() if len(row) >= col else ""

    name = val(NAME_COL)
    email = val(EMAIL_COL)
    if not name:
        continue

    if email:
        with_email.append((name, email))
        domain = email.split("@")[-1].lower()
        if any(junk in domain for junk in EMAIL_JUNK_DOMAINS):
            junk_looking.append((i, name, email))
    else:
        without_email.append(name)

total = len(with_email) + len(without_email)
print(f"Итого компаний: {total}")
print(f"С email: {len(with_email)}")
print(f"Без email: {len(without_email)}\n")

if without_email:
    print(f"БЕЗ EMAIL ({len(without_email)}) — кандидаты на повторный прогон fix_backfill_emails.py:")
    for name in without_email:
        print(f"  — {name}")

if junk_looking:
    print(f"\n⚠️ ПОДОЗРИТЕЛЬНЫЕ (домен из EMAIL_JUNK_DOMAINS, но почему-то в таблице) — {len(junk_looking)}:")
    for row_i, name, email in junk_looking:
        print(f"  [{row_i}] {name}: {email!r}")
else:
    print("\nМусорных доменов (2gis.ru/maps.yandex.ru/example.ru/vk-portal.net) в текущих email не найдено — чисто.")
