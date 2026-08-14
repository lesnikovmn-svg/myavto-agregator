"""
НАПОМИНАНИЕ (конвенция проекта): перед запуском поставь именованную версию
в Google Таблице — Файл → История версий → Назвать текущую версию →
"до fix_clean_junk_emails" → Сохранить.

Чистка мусорных email, записанных первым прогоном fix_backfill_emails.py
— 14.08.2026. Пользователь прислал реальный список из колонки email, в
нём нашлись служебные адреса самих площадок (2ГИС/Яндекс.Карты), а не
контакты компаний: help@2gis.ru (~12 раз), support@maps.yandex.ru
(~5 раз), mail@example.ru (заглушка-пример), технический хеш-адрес
ВКонтакте (*@stacks.vk-portal.net). Причина и фикс самого алгоритма —
EMAIL_JUNK_DOMAINS в company_agent.py дополнен ("2gis.ru", "maps.yandex.ru",
"example.ru", "vk-portal.net") — новые email такого вида больше не
запишутся, но старые уже записанные нужно почистить отдельно.

Что делает скрипт: проходит по ВСЕЙ таблице, для каждой компании с
непустым email проверяет его через ТОТ ЖЕ extract_email() (уже с
исправленным фильтром) — если функция бы его отклонила как мусор,
значит он мусорный и сейчас, стираем ячейку (никогда не выдумывает
замену, просто освобождает поле). id:1 (MY Avto) исключён по обычной
причине (единственная компания с данными, подтверждёнными лично
владельцем).

После чистки часть компаний снова окажется с пустым email — чтобы
попробовать найти НАСТОЯЩИЙ адрес вместо стёртого мусора, повторно
прогони fix_backfill_emails.py (он трогает только пустые ячейки, так что
безопасно гонять поверх).

Запуск: python3 fix_clean_junk_emails.py
После — python3 fix_backfill_emails.py (повторно, для очищенных строк),
затем python3 update_site.py.
"""
from company_agent import connect_sheets, extract_email

ID_COL = 1
NAME_COL = 2
EMAIL_COL = 32

ws = connect_sheets()
all_values = ws.get_all_values()

cleaned, kept = 0, 0

for i, row in enumerate(all_values[1:], start=2):
    def val(col):
        return row[col - 1].strip() if len(row) >= col else ""

    company_id = val(ID_COL)
    name = val(NAME_COL)
    email = val(EMAIL_COL)
    if not name or not email or company_id == "1":
        continue

    # extract_email() возвращает "" для мусора — если то, что уже
    # записано, само по себе не проходит фильтр, значит это мусор.
    if extract_email(email) != email:
        ws.update_cell(i, EMAIL_COL, "")
        print(f"[{i}] {name}: убрал мусорный email {email!r}")
        cleaned += 1
    else:
        kept += 1

print(f"\nИтого: очищено — {cleaned}, оставлено как есть (прошли фильтр) — {kept}.")
print("\nТеперь прогони python3 fix_backfill_emails.py (повторно, для очищенных строк),")
print("затем python3 update_site.py.")
