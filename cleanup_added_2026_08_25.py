"""
Чистка карточек, добавленных агентом за последние сутки (119 -> 133,
коммит 816c2ff) — 25.08.2026, по просьбе пользователя ("по сайту
добавились карточки, но нужно чистить, сам проверь что удалить, потом
сверимся"). Каждая из 14 новых компаний проверена вручную (открыт
реальный сайт/telegram через Claude in Chrome) — результат согласован с
пользователем через AskUserQuestion ("Удалить 6, поправить 3").

УДАЛИТЬ — не компании по импорту авто под заказ, а разный мусор:
  - Telega            -> страница telega.in "купить рекламу в чужом
                          канале", не компания.
  - Илья               -> имя человека, взято с каталога Telegram-каналов
                          tgramsearch.com, реальная компания не ясна.
  - iPhones.ru — всё про Айфоны, смартфоны, нейросети, обзоры, инструкции
                       -> сайт про гаджеты, зацепился за одну статью
                          "как проверить авто перед покупкой".
  - GetCar.ru         -> общая площадка объявлений (19 234 любых авто),
                          не компания-импортёр под заказ.
  - Гараж 007          -> авто-журнал (тюнинг/шины/двигатель), не компания.
  - Аарон Авто          -> официальный дилер бренда ROX (новые авто в
                          наличии, кредит, трейд-ин) — не "импорт под
                          заказ", обычный автосалон.

ПОПРАВИТЬ (реальные компании, испорченные данные при автодобавлении):
  - Xn--80Aal9Arbhf.Xn--P1Ai -> "Стандарт" (сайт стандарт.рф, растаможка
    под ключ; punycode-домен не был раскодирован в название).
  - Автомобили из Японии, Кореи, Китая во Владивостоке -> "Premium Import"
    (агент взял целиком <title> страницы вместо названия бренда).
  - MOSPODBOR ИМПОРТ -> описание было случайным постом-поздравлением
    клиента с покупкой Audi Q5L, заменено на нейтральное честное описание
    (сайта у компании нет, только Telegram-канал).

Запускать НА VPS (нужен доступ к Google Sheets):
    cd /var/www/myavto-agregator
    python3 cleanup_added_2026_08_25.py
    python3 update_site.py   # подтянуть изменения на сайт
"""

from company_agent import connect_sheets

DELETE_NAMES = [
    "Telega",
    "Илья",
    "iPhones.ru — всё про Айфоны, смартфоны, нейросети, обзоры, инструкции",
    "GetCar.ru",
    "Гараж 007",
    "Аарон Авто",
]

RENAME_MAP = {
    "Xn--80Aal9Arbhf.Xn--P1Ai": "Стандарт",
    "Автомобили из Японии, Кореи, Китая во Владивостоке": "Premium Import",
}

NEW_DESCRIPTION = {
    "MOSPODBOR ИМПОРТ": (
        "Подбор и импорт автомобилей из Европы под заказ. Условия и "
        "актуальные предложения — в Telegram-канале."
    ),
}


def main():
    ws = connect_sheets()
    all_values = ws.get_all_values()

    # --- Удаление: сначала собрать номера строк, удалять с конца, чтобы
    # не сбить нумерацию оставшихся строк при последовательном delete_rows.
    rows_to_delete = []
    for i, row in enumerate(all_values[1:], start=2):  # строка 1 — заголовок
        name = row[1].strip() if len(row) > 1 else ""
        if name in DELETE_NAMES:
            rows_to_delete.append((i, name))

    found_delete_names = {name for _, name in rows_to_delete}
    missing_delete = set(DELETE_NAMES) - found_delete_names
    for name in missing_delete:
        print(f"ПРОПУСК (не найдена для удаления): {name}")

    for row_num, name in sorted(rows_to_delete, key=lambda x: -x[0]):
        ws.delete_rows(row_num)
        print(f"Удалена строка {row_num}: {name}")

    # --- Переименования и правка описания — перечитываем таблицу заново,
    # т.к. номера строк выше могли измениться после удаления.
    all_values = ws.get_all_values()

    for old_name, new_name in RENAME_MAP.items():
        row_num = None
        for i, row in enumerate(all_values[1:], start=2):
            if len(row) > 1 and row[1].strip() == old_name:
                row_num = i
                break
        if row_num is None:
            print(f"ПРОПУСК (не найдена для переименования): {old_name}")
            continue
        ws.update_cell(row_num, 2, new_name)
        print(f"Переименована строка {row_num}: {old_name!r} -> {new_name!r}")

    for name, new_desc in NEW_DESCRIPTION.items():
        row_num = None
        for i, row in enumerate(all_values[1:], start=2):
            if len(row) > 1 and row[1].strip() == name:
                row_num = i
                break
        if row_num is None:
            print(f"ПРОПУСК (не найдена для правки описания): {name}")
            continue
        ws.update_cell(row_num, 7, new_desc[:200])
        print(f"Обновлено описание строки {row_num}: {name}")

    print("Готово. Дальше: python3 update_site.py")


if __name__ == "__main__":
    main()
