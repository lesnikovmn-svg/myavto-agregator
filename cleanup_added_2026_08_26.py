"""
Чистка карточек второй волны — ночной cron-прогон 26.08.2026 добавил ещё
7 карточек поверх T-79 (см. cleanup_added_2026_08_25.py), включая ПОВТОРНОЕ
появление "iPhones.ru" — той же мусорной страницы, что уже удаляли днём
раньше. Это и стало поводом завести постоянный BLACKLIST в company_agent.py
(см. правку там же), а не просто удалить руками ещё раз.

УДАЛИТЬ (проверено вживую, согласовано с пользователем через AskUserQuestion
"Удалить 3 + завести чёрный список"):
  - Импорт автомобилей в Россию -> tadviser.ru, отраслевая вики-статья со
    статистикой рынка, не компания.
  - Avtogermes               -> официальный дилер (машины в наличии,
                                 кредит, трейд-ин), не импорт под заказ —
                                 тот же случай, что "Аарон Авто" (T-79).
  - iPhones.ru — всё про Айфоны, смартфоны, нейросети, обзоры, инструкции
                              -> сайт про гаджеты, та же статья-ловушка,
                                 что удаляли 25.08 — теперь в BLACKLIST
                                 постоянно.

ОСТАВЛЕНЫ без изменений (данные в порядке): Аукционы Японии, Авто из Китая,
Авто под заказ - Global Car Trade, Прим Автодилер | Заказ авто.

Запускать НА VPS (нужен доступ к Google Sheets):
    cd /var/www/myavto-agregator
    python3 cleanup_added_2026_08_26.py
    python3 update_site.py
"""

from company_agent import connect_sheets

DELETE_NAMES = [
    "Импорт автомобилей в Россию",
    "Avtogermes",
    "iPhones.ru — всё про Айфоны, смартфоны, нейросети, обзоры, инструкции",
]


def main():
    ws = connect_sheets()
    all_values = ws.get_all_values()

    rows_to_delete = []
    for i, row in enumerate(all_values[1:], start=2):  # строка 1 — заголовок
        name = row[1].strip() if len(row) > 1 else ""
        if name in DELETE_NAMES:
            rows_to_delete.append((i, name))

    found = {name for _, name in rows_to_delete}
    for name in set(DELETE_NAMES) - found:
        print(f"ПРОПУСК (не найдена): {name}")

    for row_num, name in sorted(rows_to_delete, key=lambda x: -x[0]):
        ws.delete_rows(row_num)
        print(f"Удалена строка {row_num}: {name}")

    print("Готово. Дальше: python3 update_site.py")


if __name__ == "__main__":
    main()
