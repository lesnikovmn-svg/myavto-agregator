"""
⚠️ ПЕРЕД ЗАПУСКОМ: поставь именованную версию в Google Sheets — Файл →
История версий → Назвать текущую версию → «до fix_batch_82_105_bots_articles»
→ Сохранить.

Разбор батча id 82-105 (последний прогон ежедневного cron-агента на VPS)
— 17.08.2026, по запросу пользователя ("перепроверь последнее добавление
компаний, есть боты, есть статьи"). См. check_last_batch.py для полного
списка с эвристическими пометками. Корневые причины уже пофикшены в
company_agent.py (BLACKLIST дополнен journal.sovcombank.ru/zakon.ru/
top-autoimport.ru, добавлен пропуск telegram-хэндлов, заканчивающихся на
"bot" при поиске компаний через t.me-ссылку) — этот скрипт чистит уже
попавшие в таблицу записи.

УДАЛЯЕМ (мусор/бот/дубль):
  - [104] journal.sovcombank.ru — статья в блоге банка, не компания.
  - [103] Zakon (zakon.ru) — статья на юридическом портале, та же тема
    ("как проверить авто перед покупкой").
  - [101] Top-Autoimport — не сайт компании, а страница-рейтинг
    "лучшие компании по привозу авто из Европы" (top-autoimport.ru/ratings/...).
  - [95] auto_import_sale_bot — это Telegram-бот, не компания.
  - [105] «Яндекс» / estransit-premium.ru — имя и telegram агент утащил
    с виджета Яндекс.Карт на странице (не реальные данные). Проверено
    вживую (fetch): og:url страницы указывает на es-transit.ru, email на
    странице (estransit23@yandex.ru) — тот же адрес, что уже есть у
    существующей компании ES Transit в каталоге. Это дубль уже
    существующей карточки под другим доменом, не новая компания.

ПРАВИМ (реальные компании, агент утащил заголовок страницы/домен вместо
названия — проверено вживую, fetch реального сайта):
  - [100] «Китайские автомобили в Москве - купить авто из Китая»
    (e-n-cars.ru) -> название "E.N.CARS" (og:title сайта), telegram
    -> "encarschat" (только если сейчас пусто; ссылка на канал с сайта
    tg://resolve?domain=encarschat).
  - [99] rus-auto-import.ru (имя = домен, баг фолбэка) -> название
    "RUS AUTO IMPORT" (так компания подписана в блоке отзывов на своём
    же сайте), telegram -> "isnefedov" (ссылка t.me/isnefedov на сайте),
    email -> "info@rus-auto-import.ru" (только если пусто).

ФИКСИМ дублирующийся id:
  - id=98 сейчас на двух разных строках (Tiger Cars и "Автосалон элитных
    премиум авто в Москве AVADGE"). Матчинг по всему проекту идёт по
    ИМЕНИ, не по id, так что на работу сайта это не влияет — но лучше
    не копить дубли. Строке AVADGE присваиваем новый уникальный id
    (максимальный существующий + 1), заодно чистим имя от SEO-заголовка
    до просто "AVADGE".

Запуск: python3 fix_batch_82_105_bots_articles.py
После — python3 update_site.py.
"""
from company_agent import connect_sheets

ID_COL = 1
NAME_COL = 2
TELEGRAM_COL = 10
SITE_COL = 12
EMAIL_COL = 32

ws = connect_sheets()
all_values = ws.get_all_values()
rows = all_values[1:]


def cell(row, col_1idx):
    idx = col_1idx - 1
    return row[idx].strip() if len(row) > idx and row[idx] else ""


to_delete = []
to_fix = []  # (row_idx, {col: value}, label)

max_id = 0
for i, row in enumerate(rows, start=2):
    cid = cell(row, ID_COL)
    if cid.isdigit():
        max_id = max(max_id, int(cid))

for i, row in enumerate(rows, start=2):
    cid = cell(row, ID_COL)
    name = cell(row, NAME_COL)
    site = cell(row, SITE_COL).lower()
    telegram = cell(row, TELEGRAM_COL).lower()

    if cid == "104" and "journal.sovcombank.ru" in site:
        to_delete.append((i, name, "статья в блоге банка"))
    elif cid == "103" and "zakon.ru" in site:
        to_delete.append((i, name, "статья на юридическом портале"))
    elif cid == "101" and "top-autoimport.ru" in site:
        to_delete.append((i, name, "страница-рейтинг, не компания"))
    elif cid == "95" and telegram == "auto_import_sale_bot":
        to_delete.append((i, name, "это Telegram-бот, не компания"))
    elif cid == "105" and "estransit-premium.ru" in site:
        to_delete.append((i, name, "дубль ES Transit под другим доменом"))
    elif cid == "100" and "e-n-cars.ru" in site:
        fields = {NAME_COL: "E.N.CARS"}
        if not telegram:
            fields[TELEGRAM_COL] = "encarschat"
        to_fix.append((i, fields, "E.N.CARS"))
    elif cid == "99" and "rus-auto-import.ru" in site:
        fields = {NAME_COL: "RUS AUTO IMPORT"}
        if not telegram:
            fields[TELEGRAM_COL] = "isnefedov"
        if not cell(row, EMAIL_COL):
            fields[EMAIL_COL] = "info@rus-auto-import.ru"
        to_fix.append((i, fields, "RUS AUTO IMPORT"))
    elif cid == "98" and "avadge" in site:
        max_id += 1
        fields = {ID_COL: str(max_id), NAME_COL: "AVADGE"}
        to_fix.append((i, fields, f"AVADGE (новый id {max_id})"))

for row_idx, fields, label in to_fix:
    for col, value in fields.items():
        ws.update_cell(row_idx, col, value)
    print(f"[{row_idx}] -> {label}: {fields}")

for row_idx, name, reason in sorted(to_delete, key=lambda x: -x[0]):
    ws.delete_rows(row_idx)
    print(f"[{row_idx}] удалено: {name!r} ({reason})")

print(f"\nГотово. Исправлено: {len(to_fix)}, удалено: {len(to_delete)}.")
print("Теперь прогони python3 update_site.py.")
