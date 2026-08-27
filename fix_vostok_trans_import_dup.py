"""
Точечный фикс за 27.08.2026, найден СРАЗУ после деплоя batch3/batch4 —
поймал сам, живой проверкой app.js на сайте (урок T-88: не доверять
кэшу браузера, тянуть свежий app.js с bust-параметром).

batch3 должен был удалить "Аукционы Японии" (id 152, vtransim.ru) как
дубль "Восток Транс Импорт" (id 12) — но лог деплоя показал "ПРОПУСК (не
найдена для удаления): Аукционы Японии". Причина: старый скрипт
fix_manual_data_2026_08_27.py (T-87, коммит от начала дня) уже
переименовал строку 152 в "Восток Транс Импорт" ДО того, как я это
проверял (тогда казалось, что переименование "не удержалось" — см.
TASKS.md T-87, это был ложный вывод из-за протухшей вкладки браузера,
тот же класс ошибки, что и в T-88). В реальности переименование
сработало, просто я не пересчитал у batch3 совпадение по СТАРОМУ имени.

Итог на сейчас: ДВЕ строки называются "Восток Транс Импорт" — id 12
(канонический, с vtransim.ru/telegram koreacarsme/VK, поправлен в
batch3) и id 152 (дубль, phone буквально "#ERROR!" — битое значение
формулы в самой Google Таблице, telegram/VK пустые). Удаляю дубль по id,
не по имени (оба совпадают).

Запускать НА VPS:
    cd /var/www/myavto-agregator
    python3 fix_vostok_trans_import_dup.py
    python3 update_site.py
"""

from company_agent import connect_sheets

COL_ID = 0
COL_NAME = 1


def main():
    ws = connect_sheets()
    all_values = ws.get_all_values()

    matches = []
    for i, row in enumerate(all_values[1:], start=2):
        if len(row) > COL_NAME and row[COL_NAME].strip() == "Восток Транс Импорт":
            matches.append((i, row[COL_ID].strip() if len(row) > COL_ID else ""))

    print(f"Найдено строк 'Восток Транс Импорт': {len(matches)} -> {matches}")

    to_delete = [row_num for row_num, id_val in matches if id_val == "152"]
    if not to_delete:
        print("ПРОПУСК: строка с id=152 не найдена (возможно, уже удалена)")
    for row_num in sorted(to_delete, reverse=True):
        ws.delete_rows(row_num)
        print(f"Удалена строка {row_num} (дубль id=152)")

    print("Готово. Дальше: python3 update_site.py")


if __name__ == "__main__":
    main()
