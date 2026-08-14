"""
НАПОМИНАНИЕ (конвенция проекта): если ещё не сделал именованную версию в
Google Таблице для fix_restore_telegram_corruption.py — сделай сейчас
(Файл → История версий → Назвать текущую версию → Сохранить). Этот
скрипт — прямое продолжение того же восстановления, отдельной версии под
него ставить не обязательно.

Добивает 6 записей, которые fix_restore_telegram_corruption.py пропустил
14.08.2026 — не из-за расхождения данных, а из-за НОВОГО обнаруженного
бага: в таблице есть дублирующиеся id (напр. и "LimCars", и "AutoImport
Russia" числятся под id:60; и "ТокиДоки", и "Авто Азия" — под id:63, и
т.д. — это уже отмечалось раньше в PROJECT_STATE.md как "не критично", но
здесь как раз тот случай, когда критично). Старый скрипт брал ПЕРВУЮ
строку с нужным id, natыкался на ДРУГУЮ компанию, имя не совпадало — и
сдавался, не проверив вторую строку с тем же id.

Здесь матчинг сделан по ИМЕНИ (оно в этих 6 случаях уникально в таблице —
проверено вручную по текущему index.html после первого прогона), а не по
id. Та же логика безопасности: сверяет текущее значение telegram с
ожидаемым испорченным перед перезаписью, иначе не трогает.

Запуск: python3 fix_restore_telegram_corruption_batch2.py
После — python3 update_site.py.
"""
import time
from company_agent import connect_sheets

NAME_COL = 2
TELEGRAM_COL = 10
TG_CONTACT_COL = 31

# (name, telegram_ДО_порчи (правильный), telegram_ПОСЛЕ_порчи (текущий, испорченный))
CORRUPTED = [
    ("AutoImport Russia", "autoimportrussiarf", "Andrey_AutoImportRussia"),
    ("Телеграм канал Levcar", "levcar_125", ""),
    ("Авто Азия", "autoasia25", ""),
    ("Долгов Авто - Машины из Кореи,Японии,Китая.", "dolgov_auto", ""),
    ("MY AUTO", "myauto_premium", "myautopremium"),
    ("Авто Заказ", "auto_zakazz25", ""),
]

ws = connect_sheets()
all_values = ws.get_all_values()

restored, moved_to_ae, skipped = 0, 0, 0

for name, correct_tg, corrupted_val in CORRUPTED:
    row_idx = None
    for i, row in enumerate(all_values[1:], start=2):
        row_name = row[NAME_COL - 1].strip() if len(row) >= NAME_COL else ""
        row_tg = row[TELEGRAM_COL - 1].strip() if len(row) >= TELEGRAM_COL else ""
        if row_name == name and row_tg == corrupted_val:
            row_idx = i
            break
    if row_idx is None:
        print(f"{name}: не нашёл строку с этим именем И испорченным значением telegram "
              f"({corrupted_val!r}) — похоже, уже исправлено или изменено кем-то ещё, пропускаю")
        skipped += 1
        continue

    row = all_values[row_idx - 1]
    ws.update_cell(row_idx, TELEGRAM_COL, correct_tg)
    restored += 1

    if corrupted_val:
        current_ae = row[TG_CONTACT_COL - 1].strip() if len(row) >= TG_CONTACT_COL else ""
        if not current_ae:
            ws.update_cell(row_idx, TG_CONTACT_COL, corrupted_val)
            moved_to_ae += 1
            print(f"{name}: канал восстановлен -> {correct_tg}, личный контакт {corrupted_val} перенесён в AE")
        else:
            print(f"{name}: канал восстановлен -> {correct_tg}, в AE уже есть {current_ae!r} — не перезаписываю")
    else:
        print(f"{name}: канал восстановлен -> {correct_tg}")
    time.sleep(0.3)

print(f"\nИтого: восстановлено — {restored}, перенесено в AE — {moved_to_ae}, пропущено — {skipped}")
print("\nТеперь прогони python3 update_site.py.")
