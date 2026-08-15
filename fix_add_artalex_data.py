"""
НАПОМИНАНИЕ (конвенция проекта): перед запуском поставь именованную версию
в Google Таблице — Файл → История версий → Назвать текущую версию →
"до fix_add_artalex_data" → Сохранить.

Точечное дозаполнение контактов для "Artalex Group" — 15.08.2026.
Компания была в списке "без Telegram вообще" (см. check_onboarded.py) —
пользователь вручную нашёл все данные прямо на сайте artalexgroup.com и
прислал их в чат:
  сайт:      https://artalexgroup.com/
  телефоны:  +375 (29) 363-93-34 (Беларусь), +375 (25) 917-28-06 (Беларусь),
             +48 794 574 013 (Польша) — в таблицу пишем первый как основной,
             остальные два — не потерять бы, но отдельного поля под них нет
             (см. предупреждение в конце скрипта).
  telegram:  t.me/artalexgroup — ГРУППА/канал компании (колонка telegram,
             НЕ личный контакт — та же логика различия каналов и личных
             контактов, что и везде в проекте).
  личный:    @mut1_dobr0 — колонка tgcontact (AE), то, что реально
             используется кнопкой "Написать" на карточке.
  email:     artalexgroupp@gmail.com

Пишет только в ПУСТЫЕ ячейки — если что-то уже заполнено (например, сайт
уже был указан), не перезаписывает, только предупреждает. Матчит строку
по ИМЕНИ (не по id — в таблице бывают дублирующиеся id).

Запуск: python3 fix_add_artalex_data.py
После — python3 update_site.py.
"""
from company_agent import connect_sheets

NAME_COL = 2
TELEGRAM_COL = 10
PHONE_COL = 11
SITE_COL = 12
TG_CONTACT_COL = 31
EMAIL_COL = 32

COMPANY_NAME = "Artalex Group"

FIELDS = {
    TELEGRAM_COL: "artalexgroup",
    PHONE_COL: "+375 (29) 363-93-34",
    SITE_COL: "https://artalexgroup.com/",
    TG_CONTACT_COL: "mut1_dobr0",
    EMAIL_COL: "artalexgroupp@gmail.com",
}
FIELD_NAMES = {
    TELEGRAM_COL: "telegram (канал)",
    PHONE_COL: "phone",
    SITE_COL: "site",
    TG_CONTACT_COL: "tgcontact (личный)",
    EMAIL_COL: "email",
}

ws = connect_sheets()
all_values = ws.get_all_values()

matches = [i for i, row in enumerate(all_values[1:], start=2)
           if len(row) >= NAME_COL and row[NAME_COL - 1].strip() == COMPANY_NAME]

if len(matches) == 0:
    print(f"{COMPANY_NAME}: не нашёл строку с таким именем — проверь точное "
          f"написание в таблице.")
elif len(matches) > 1:
    print(f"{COMPANY_NAME}: нашёл {len(matches)} строк с таким именем — "
          f"пропускаю, проверь дубли вручную.")
else:
    row_idx = matches[0]
    row = all_values[row_idx - 1]
    for col, value in FIELDS.items():
        current = row[col - 1].strip() if len(row) >= col else ""
        label = FIELD_NAMES[col]
        if current:
            print(f"{COMPANY_NAME}: {label} уже заполнено ({current!r}) — не перезаписываю.")
        else:
            ws.update_cell(row_idx, col, value)
            print(f"{COMPANY_NAME}: {label} -> {value}")

print("\n⚠️ Доп. телефоны, которые НЕ попали в таблицу (нет отдельного поля "
      "под несколько номеров) — держи под рукой на всякий случай:")
print("  +375 (25) 917-28-06 (Беларусь)")
print("  +48 794 574 013 (Польша)")
print("\nТеперь прогони python3 update_site.py.")
