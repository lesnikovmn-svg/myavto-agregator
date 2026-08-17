"""
НАПОМИНАНИЕ (конвенция проекта): перед запуском поставь именованную версию
в Google Таблице — Файл → История версий → Назвать текущую версию →
"до fix_dedupe_and_enrich_autozakaz" → Сохранить.

Важная поправка к предыдущему шагу — 17.08.2026. check_all_sites.py
показал, что "Автозаказ.ру" НЕ новая компания: она уже дважды сидит в
таблице под разными именами с одним и тем же telegram-каналом
"auto_zakazz25":
  [22] "АВТОЗАКАЗ.РУ" — site=autozakaz.ru, есть.
  [81] "Авто Заказ" — сайта нет, тот же telegram.
Классический дубль (тот же паттерн, что уже несколько раз ловился в
проекте — см. fix_new_batch_18.py, ES Transit и т.д.): агент дважды нашёл
одну и ту же компанию под разными названиями. fix_add_autozakaz.py
(написан этой же сессией) НЕ запускался — его дедуп-проверка бы это
поймала и просто отказалась добавлять, но лучше сразу почистить и
обогатить существующую запись, чем плодить скрипты.

Что делает этот скрипт:
1. Удаляет дублирующую строку [81] "Авто Заказ" (менее полные данные,
   нет сайта).
2. Дозаполняет строку [22] "АВТОЗАКАЗ.РУ" всеми данными, которые я нашёл
   живым fetch'ом сайта autozakaz.ru и карточки Яндекс.Карт (см.
   докстринг fix_add_autozakaz.py — та же информация, оттуда же):
   rating=4.4, reviews=782, inn=250818340283, yandex/google/gis2-ссылки,
   vk, youtube, max, whatsapp, telegram_contact=logistAZbot, avatar —
   реальный логотип с сайта. Пишет ТОЛЬКО в пустые поля — если что-то уже
   было в строке [22], не трогает.
3. fix_add_autozakaz.py больше не нужен — не запускай его, он попытается
   добавить дубль (хотя дедуп-проверка внутри него должна сама
   отказаться, полагаться на это не стоит).

Запуск: python3 fix_dedupe_and_enrich_autozakaz.py
После — python3 update_site.py.
"""
from company_agent import connect_sheets

ID_COL = 1
NAME_COL = 2
RATING_COL = 3
REVIEWS_COL = 4
TELEGRAM_COL = 10
SITE_COL = 12
AVATAR_COL = 16
YANDEX_COL = 18
INN_COL = 19
GOOGLE_COL = 20
GIS2_COL = 21
VK_COL = 23
MAX_COL = 27
YOUTUBE_COL = 28
WHATSAPP_COL = 30
TG_CONTACT_COL = 31

ENRICH = {
    RATING_COL: "4.4",
    REVIEWS_COL: "782",
    AVATAR_COL: "https://autozakaz.ru/wp-content/uploads/2025/01/cropped-az-logo-minimal-270x270.webp",
    YANDEX_COL: "https://yandex.com/maps/org/autozakaz_ru/140791872893/",
    INN_COL: "250818340283",
    GOOGLE_COL: "https://g.co/kgs/opDGBJW",
    GIS2_COL: "https://go.2gis.com/Igal1",
    VK_COL: "https://vk.com/auto_zakaz25",
    MAX_COL: "https://max.ru/auto_zakazz25",
    YOUTUBE_COL: "https://www.youtube.com/@Autozakazru",
    WHATSAPP_COL: "https://wa.me/79644527888",
    TG_CONTACT_COL: "logistAZbot",
}

ws = connect_sheets()
all_values = ws.get_all_values()
rows = all_values[1:]


def cell(row, col_1idx):
    idx = col_1idx - 1
    return row[idx].strip() if len(row) > idx and row[idx] else ""


row22_idx = None
row81_idx = None
for i, row in enumerate(rows, start=2):
    cid = cell(row, ID_COL)
    tg = cell(row, TELEGRAM_COL).lower()
    if cid == "22" and "autozakaz.ru" in cell(row, SITE_COL).lower():
        row22_idx = i
    elif cid == "81" and cell(row, NAME_COL) == "Авто Заказ" and tg == "auto_zakazz25":
        row81_idx = i

if row22_idx is None:
    print("Не нашёл строку [22] АВТОЗАКАЗ.РУ по ожидаемым признакам — прервано, проверь вручную.")
    raise SystemExit(1)

row22 = rows[row22_idx - 2]
filled, skipped = 0, 0
for col, value in ENRICH.items():
    current = cell(row22, col)
    if current:
        skipped += 1
        continue
    ws.update_cell(row22_idx, col, value)
    filled += 1

print(f"[{row22_idx}] АВТОЗАКАЗ.РУ: дозаполнено полей — {filled}, уже было заполнено (пропущено) — {skipped}.")

if row81_idx:
    ws.delete_rows(row81_idx)
    print(f"[{row81_idx}] удалена дублирующая строка 'Авто Заказ' (тот же telegram-канал, что и у [22]).")
else:
    print("Строка [81] 'Авто Заказ' не найдена (возможно, уже удалена) — пропущено.")

print("\nТеперь прогони python3 update_site.py.")
