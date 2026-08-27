"""
Четвёртая волна ручной сверки за 27.08.2026 (продолжение T-90, тот же
системный класс багов — см. TASKS.md).

УДАЛИТЬ (2):
  - "Авто из Китая" (id 154, сайт china.estransit.ru) — пользователь сам
    заметил ("это ес транзит дубль я так понимаю") и оказался прав:
    china.estransit.ru — ещё один поддомен ТОЙ ЖЕ компании, что и
    ES Transit Premium (id 135, estransit-premium.ru) — тот же паттерн,
    что уже был у "Восток Транс Импорт" (несколько лендингов под разные
    направления/страны на разных доменах одного бренда). Подтверждено:
    vk.com/estransit в футере china.estransit.ru — тот же паб, что у
    основной карточки. Перед удалением на канонической карточке (id 135)
    проставлен VK, которого там не было.
  - "Стандарт" (id 149, сайт стандарт.рф) — не импортёр авто, а компания
    по растаможке под ключ (СБКТС/ЭПТС/утильсбор, лицензия ФТС, лаборатория
    испытаний) — её место не в каталоге импортёров, а в уже существующей
    (с 13.08.2026) секции "Таможенные брокеры" на сайте (#customs в
    index.html). Добавлена туда вручную как "Стандарт.рф" — сайт
    xn--80aal9arbhf.xn--p1ai, telegram t.me/standart_rf. НЕ путать с уже
    висевшей там карточкой "Стандарт Групп" (tamozhennyy-broker.ru) — это
    другая, никак не связанная компания (грузовой таможенный брокер в
    аэропортах Москвы, не авто), совпадение только в названии.

ОБНОВИТЬ (2):
  1) "Цены, статистика, покупка авто из Японии" (id 105, mado.group) ->
     переименовано в "MADO" — заголовок выдачи попал в name целиком
     вместо названия бренда (тот же класс, что "Стандарт"/"Premium Import"
     в T-79), реальное название — в title страницы ("...компания MADO").
     Контакты (VK/telegram/whatsapp/email/телефон) взяты с самого сайта.
  2) "Winner Auto Club" (id 5) — уже был в каталоге с telegram/менеджером,
     пользователь сам прислал номер телефона менеджера (Артём,
     +995 511 29 92 99, Грузия) — раньше телефон был "-".

Запускать НА VPS (нужен доступ к Google Sheets):
    cd /var/www/myavto-agregator
    python3 fix_manual_data_2026_08_27_batch4.py
    python3 update_site.py
"""

from company_agent import connect_sheets

# Индексы колонок (0-based, см. add_company() в company_agent.py):
COL_NAME = 1
COL_TELEGRAM = 9
COL_PHONE = 10
COL_VK = 22
COL_WHATSAPP = 29
COL_EMAIL = 31

DELETE_NAMES = [
    "Авто из Китая",
    "Стандарт",
]

FIXES = {
    "ES Transit Premium": {
        COL_VK: "https://vk.com/estransit",
    },
    "Цены, статистика, покупка авто из Японии": {
        COL_NAME: "MADO",
        COL_TELEGRAM: "mado_asia_cars",
        COL_VK: "https://vk.com/mado_group",
        COL_WHATSAPP: "https://api.whatsapp.com/send?phone=79025240295",
        COL_EMAIL: "sales@mado.group",
        COL_PHONE: "8 (800) 700-23-18",
    },
    "Winner Auto Club": {
        COL_PHONE: "+995 511 29 92 99",
    },
}


def main():
    ws = connect_sheets()
    all_values = ws.get_all_values()

    rows_to_delete = []
    for i, row in enumerate(all_values[1:], start=2):
        name = row[COL_NAME].strip() if len(row) > COL_NAME else ""
        if name in DELETE_NAMES:
            rows_to_delete.append((i, name))
    found = {name for _, name in rows_to_delete}
    for name in set(DELETE_NAMES) - found:
        print(f"ПРОПУСК (не найдена для удаления): {name}")
    for row_num, name in sorted(rows_to_delete, key=lambda x: -x[0]):
        ws.delete_rows(row_num)
        print(f"Удалена строка {row_num}: {name}")

    all_values = ws.get_all_values()
    for name, fields in FIXES.items():
        row_num = None
        for i, row in enumerate(all_values[1:], start=2):
            if len(row) > COL_NAME and row[COL_NAME].strip() == name:
                row_num = i
                break
        if row_num is None:
            print(f"ПРОПУСК (не найдена для правки): {name}")
            continue
        for col_idx, value in fields.items():
            ws.update_cell(row_num, col_idx + 1, value)  # gspread — 1-based колонки
        new_name = fields.get(COL_NAME, name)
        print(f"Обновлена строка {row_num}: {name!r} -> полей изменено: {len(fields)} (имя: {new_name!r})")

    print("Готово. Дальше: python3 update_site.py")


if __name__ == "__main__":
    main()
