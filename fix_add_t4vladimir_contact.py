"""
НАПОМИНАНИЕ (конвенция проекта): перед запуском поставь именованную версию
в Google Таблице — Файл → История версий → Назвать текущую версию →
"до fix_add_t4vladimir_contact" → Сохранить.

Точечное дозаполнение личного контакта для одной компании — 14.08.2026.
Пользователь прислал скриншот поста в Telegram-канале компании "Авто из
Европы / Авто Импорт ПРО" (канал @auto_import_cars_rus, 1636 подписчиков,
пост про доставленный автомобиль) — в посте указан менеджер @T4_Vladimir
("Связь с менеджером"), номер найден на самом канале.

Проверено fetch'ом t.me/T4_Vladimir (не вслепую): title
"Telegram: Contact @T4_Vladimir", og:description "You can contact
@T4_Vladimir right away", кнопка "Send Message" — подтверждённый личный
(messageable) контакт, не канал/группа.

Пишет ТОЛЬКО если колонка tgcontact (AE) сейчас пустая — если там уже
что-то есть, ничего не перезаписывает. Матчит строку по ИМЕНИ (не по id —
в таблице бывают дублирующиеся id, см. PROJECT_STATE.md), если найдётся
0 или больше 1 совпадения — пропускает с предупреждением.

Запуск: python3 fix_add_t4vladimir_contact.py
После — python3 update_site.py.
"""
from company_agent import connect_sheets

NAME_COL = 2
TG_CONTACT_COL = 31

COMPANY_NAME = "Авто из Европы / Авто Импорт ПРО"
CONTACT_HANDLE = "T4_Vladimir"

ws = connect_sheets()

header = ws.cell(1, TG_CONTACT_COL).value
if not header:
    print(f"Колонка {TG_CONTACT_COL} (AE) ещё не создана — сначала запусти "
          f"python3 add_tg_contact_column.py")
    raise SystemExit(1)

all_values = ws.get_all_values()

matches = [i for i, row in enumerate(all_values[1:], start=2)
           if len(row) >= NAME_COL and row[NAME_COL - 1].strip() == COMPANY_NAME]

if len(matches) == 0:
    print(f"{COMPANY_NAME}: не нашёл строку с таким именем — проверь точное "
          f"написание в таблице (могло отличаться от того, что записано в "
          f"PROJECT_STATE.md).")
elif len(matches) > 1:
    print(f"{COMPANY_NAME}: нашёл {len(matches)} строк с таким именем — "
          f"пропускаю, проверь дубли вручную.")
else:
    row_idx = matches[0]
    row = all_values[row_idx - 1]
    current = row[TG_CONTACT_COL - 1].strip() if len(row) >= TG_CONTACT_COL else ""
    if current:
        print(f"{COMPANY_NAME}: tgcontact уже заполнено ({current!r}) — не перезаписываю.")
    else:
        ws.update_cell(row_idx, TG_CONTACT_COL, CONTACT_HANDLE)
        print(f"{COMPANY_NAME}: tgcontact -> {CONTACT_HANDLE}")

print("\nТеперь прогони python3 update_site.py.")
