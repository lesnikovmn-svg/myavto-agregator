"""
НАПОМИНАНИЕ (конвенция проекта): перед запуском поставь именованную версию
в Google Таблице — Файл → История версий → Назвать текущую версию →
"до fix_contacts_verified_14082026" → Сохранить.

Точечное дозаполнение контактов для 7 компаний — 14.08.2026, по запросу
пользователя ("у ТамСямыча исправь на написать в тг, ссылка инстаграм не
работает, так же проверь по остальным компаниям").

Разбор: у ТамСямAUTO кнопка "Написать" на сайте вела в Instagram (потому
что tgcontact пуст, whatsapp/vk тоже пусты — приоритет по цепочке
Telegram→WhatsApp→VK→Instagram дошёл до Instagram), а Instagram-ссылка не
работает у пользователя. Проверка t.me/TamSyam26 (fetch) показала: это
самый обычный КАНАЛ (7966 подписчиков), альтернативного личного контакта в
описании нет — открытые данные его не содержали. Добавлен и WhatsApp
(wa.me/79288198007, найден на официальном сайте tamsyamauto.ru) как
надёжный fallback. **Обновление (тем же вечером)**: пользователь прислал
личный контакт напрямую — @TamSyamAUTO. Проверено fetch'ом t.me/TamSyamAUTO:
title "Telegram: Contact @TamSyamAUTO" (не "View", как у канала), есть
кнопка "Send Message", в описании "Алексей" со ссылкой на канал
@TamSyam26 — подтверждённый личный аккаунт владельца, messageable.
Записан в tgcontact (AE) — кнопка станет "Написать в TG" на TamSyamAUTO,
как изначально и просили; WhatsApp остаётся дозаполненным на всякий
случай (более высокий приоритет у TG всё равно означает, что WhatsApp
просто не понадобится, пока tgcontact заполнен).

Заодно нашлось ещё 9 компаний в каталоге с той же структурной уязвимостью
(tgcontact/whatsapp/vk пустые, кнопка "Написать" держится на одном
Instagram) — из них удалось руками проверить сайты 6 (Wanna-Car, Jplife,
Arnold-Auto, Carsplus, China.Sferacar, Emirate Cars) и найти у них реальные
рабочие контакты (личные Telegram-боты, WhatsApp, email — некоторые
компании прямо на сайте подписывают ссылку как "Написать в Telegram", это
и есть надёжный сигнал, что это НЕ канал, а messageable-контакт).
Тачкиру (тачкиру.рф — кириллический домен, недоступен для fetch),
Japan Star (jpstar.ru — отдаёт "Отключите VPN, чтобы открыть сайт") и
Avtoban.Org (avtoban.org — "Sorry, your request has been denied", похоже
на бот-защиту) проверить не удалось — оставлены как есть, значит нужна
ручная проверка при случае.

Что делает скрипт: для каждой записи ниже — находит строку ПО ИМЕНИ
(если найдётся 0 или больше 1 совпадения — пропускает с предупреждением,
чтобы не перепутать с дублем), и для каждого поля пишет значение, ТОЛЬКО
если текущая ячейка пустая (никогда не перезаписывает уже заполненное).

Запуск: python3 fix_contacts_verified_14082026.py
После — python3 update_site.py.
"""
import time
from company_agent import connect_sheets

NAME_COL = 2
TELEGRAM_COL = 10
YANDEX_COL = 18
GIS2_COL = 21
WHATSAPP_COL = 30
TG_CONTACT_COL = 31
EMAIL_COL = 32

# (name, {col: value, ...})
FIXES = [
    ("ТамСямAUTO", {
        WHATSAPP_COL: "https://wa.me/79288198007",
        # Личный контакт прислал сам пользователь (14.08.2026) — проверено
        # fetch'ем t.me/TamSyamAUTO: title "Telegram: Contact @TamSyamAUTO"
        # (не "View", как у канала), есть кнопка "Send Message", в описании
        # прямым текстом "Алексей" со ссылкой на канал @TamSyam26 — то есть
        # это личный аккаунт владельца канала, действительно messageable.
        TG_CONTACT_COL: "TamSyamAUTO",
    }),
    ("Wanna-Car", {
        TELEGRAM_COL: "WannaCarSales",
        TG_CONTACT_COL: "WannaCarSales",
        WHATSAPP_COL: "https://wa.me/79256006777",
        EMAIL_COL: "wannacar77@gmail.com",
    }),
    ("Jplife", {
        TELEGRAM_COL: "JapanLife_answers",
        TG_CONTACT_COL: "JapanLife_answers",
        EMAIL_COL: "sales@japanlife.ru",
    }),
    ("Arnold-Auto", {
        TELEGRAM_COL: "arnoldauto_bot",
        TG_CONTACT_COL: "arnoldauto_bot",
        WHATSAPP_COL: "https://wa.me/79509456666",
    }),
    ("Carsplus", {
        WHATSAPP_COL: "https://wa.me/79123458841",
    }),
    ("China.Sferacar", {
        TELEGRAM_COL: "china_sferacar_web_bot",
        TG_CONTACT_COL: "china_sferacar_web_bot",
        WHATSAPP_COL: "https://wa.me/79586097071",
        EMAIL_COL: "sales@sferacar.ru",
    }),
    ("Emirate Cars", {
        WHATSAPP_COL: "https://wa.me/971502987269",
        EMAIL_COL: "emiratecars2025@gmail.com",
    }),
]

COL_NAMES = {
    TELEGRAM_COL: "telegram", WHATSAPP_COL: "whatsapp",
    TG_CONTACT_COL: "tgcontact(AE)", EMAIL_COL: "email(AF)",
}

ws = connect_sheets()

# email(AF)/tgcontact(AE) может понадобиться раньше, чем колонки заведены —
# проверяем заголовки перед стартом, а не падаем на первой же записи.
needed_cols = {c for _, fields in FIXES for c in fields}
for c in needed_cols:
    if c in (TG_CONTACT_COL, EMAIL_COL) and not ws.cell(1, c).value:
        label = "AE (add_tg_contact_column.py)" if c == TG_CONTACT_COL else "AF (add_email_column.py)"
        print(f"Колонка {label} ещё не создана — сначала запусти соответствующий add_*_column.py")
        raise SystemExit(1)

all_values = ws.get_all_values()

written, skipped_dup, skipped_notfound, skipped_filled = 0, 0, 0, 0

for name, fields in FIXES:
    matches = [i for i, row in enumerate(all_values[1:], start=2)
               if len(row) >= NAME_COL and row[NAME_COL - 1].strip() == name]
    if len(matches) == 0:
        print(f"{name}: не нашёл строку с таким именем — пропускаю")
        skipped_notfound += 1
        continue
    if len(matches) > 1:
        print(f"{name}: нашёл {len(matches)} строк с таким именем — пропускаю (проверь дубли вручную)")
        skipped_dup += 1
        continue

    row_idx = matches[0]
    row = all_values[row_idx - 1]
    for col, value in fields.items():
        current = row[col - 1].strip() if len(row) >= col else ""
        if current:
            print(f"{name}: {COL_NAMES[col]} уже заполнено ({current!r}) — не перезаписываю")
            skipped_filled += 1
            continue
        ws.update_cell(row_idx, col, value)
        print(f"{name}: {COL_NAMES[col]} -> {value}")
        written += 1
        time.sleep(0.3)

print(f"\nИтого: записано полей — {written}, уже было заполнено (пропущено) — {skipped_filled}, "
      f"не найдено по имени — {skipped_notfound}, дубли имени (пропущено) — {skipped_dup}")
print("\nТеперь прогони python3 update_site.py.")
