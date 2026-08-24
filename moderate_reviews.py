"""
Модерация отзывов (задача пользователя от 17.08.2026: нативные отзывы на
сайте вместо кнопки, ведущей на сторонние площадки — "с модерацией,
рекомендую"). Отзывы падают в статус "pending" через POST /api/review
(telegram_bot_service.py) в вкладку "Отзывы" Google Таблицы. Этот скрипт —
интерактивный: показывает каждый pending-отзыв и даёт решить, публиковать
его или нет.

Запуск: python3 moderate_reviews.py
Для каждого отзыва: a — одобрить, r — отклонить, Enter — пропустить (решить
позже), q — выйти.

После модерации нужно прогнать python3 update_site.py — он подтягивает
только status=approved в карточки на сайте, отклонённые и ещё не решённые
отзывы на сайт не попадают.
"""

from company_agent import connect_reviews_sheet, REVIEWS_HEADER

ID_COL = REVIEWS_HEADER.index("id") + 1
COMPANY_ID_COL = REVIEWS_HEADER.index("company_id") + 1
COMPANY_NAME_COL = REVIEWS_HEADER.index("company_name") + 1
AUTHOR_COL = REVIEWS_HEADER.index("author_name") + 1
RATING_COL = REVIEWS_HEADER.index("rating") + 1
TEXT_COL = REVIEWS_HEADER.index("text") + 1
STATUS_COL = REVIEWS_HEADER.index("status") + 1
CREATED_COL = REVIEWS_HEADER.index("created_at") + 1
CONTACT_COL = REVIEWS_HEADER.index("contact") + 1

ws = connect_reviews_sheet()
all_values = ws.get_all_values()
rows = all_values[1:]  # без заголовка

pending = []
for i, row in enumerate(rows, start=2):  # строка 1 — заголовок
    status = row[STATUS_COL - 1].strip() if len(row) >= STATUS_COL else ""
    if status.lower() == "pending" or not status:
        pending.append((i, row))

if not pending:
    print("Отзывов на модерации нет.")
    raise SystemExit(0)

print(f"На модерации: {len(pending)} отзыв(ов).\n")

approved, rejected, skipped = 0, 0, 0
for row_idx, row in pending:

    def cell(col):
        return row[col - 1].strip() if len(row) >= col and row[col - 1] else ""

    print("—" * 60)
    print(f"#{cell(ID_COL)} | {cell(CREATED_COL)}")
    print(f"Компания: {cell(COMPANY_NAME_COL)} (id={cell(COMPANY_ID_COL) or '—'})")
    print(f"Автор: {cell(AUTHOR_COL)}   Оценка: {cell(RATING_COL)}/5")
    if cell(CONTACT_COL):
        print(f"Контакт (не публикуется): {cell(CONTACT_COL)}")
    print(f"Текст: {cell(TEXT_COL)}")

    choice = (
        input("Одобрить (a) / Отклонить (r) / Пропустить (Enter) / Выход (q): ").strip().lower()
    )
    if choice == "q":
        print("Остановлено пользователем.")
        break
    elif choice == "a":
        ws.update_cell(row_idx, STATUS_COL, "approved")
        approved += 1
        print("→ одобрено.")
    elif choice == "r":
        ws.update_cell(row_idx, STATUS_COL, "rejected")
        rejected += 1
        print("→ отклонено.")
    else:
        skipped += 1
        print("→ пропущено (останется на модерации).")

print("—" * 60)
print(f"Итого: одобрено — {approved}, отклонено — {rejected}, пропущено — {skipped}.")
if approved:
    print("Теперь прогони python3 update_site.py, чтобы одобренные отзывы появились на сайте.")
