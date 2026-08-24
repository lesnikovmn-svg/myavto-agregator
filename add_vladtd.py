"""
Ручное добавление VladTD (vladtd.ru) — 24.08.2026, найден через диагностику
diag_personal_brand.py (запрос "youtube канал перегон авто из Кореи
Японии") в рамках разбора вопроса "как находить компании с раскруткой
через личный бренд?" (см. также add_lisa_rulit.py — тот же класс проблемы).

Блогер-перегонщик (Владислав Кислицын, ИП, канал "Влад Трын Дын") —
с 2022 года команда возит авто под заказ из Японии/Китая/Кореи,
1000+ доставленных машин. Данные собраны вручную с https://vladtd.ru/
(сайт открылся без антибота) + поиском telegram-хэндла (на сайте виден
только счётчик подписчиков без ссылок в текстовом слепке).

Запускать НА VPS (нужен доступ к Google Sheets):
    cd /var/www/myavto-agregator
    python3 add_vladtd.py
"""

from company_agent import connect_sheets, get_existing, add_company

DATA = {
    "name": "VladTD",
    "description": (
        "Автомобили под заказ из Японии, Китая и Южной Кореи — команда "
        "блогера Владислава Кислицына, с 2022 года привезли 1000+ авто, "
        "честная комиссия без скрытых платежей, полное сопровождение сделки."
    ),
    "directions": ["Япония", "Китай", "Корея"],
    "tags": ["Под заказ", "Полное сопровождение"],
    "telegram": "VladTD_official",
    "telegram_contact": "zakaz_VladTD",
    "phone": "+7 (993) 955-01-27",
    "site": "https://vladtd.ru",
    "region": "Новосибирск",
    "inn": "540600572584",  # ИП Кислицын В.К., указан на сайте открыто
    "vk": "https://vk.com/vladTD",
    "youtube": "https://youtube.com/@vladTD",
    "years": "4",  # с 2022 года
}

ws = connect_sheets()
existing = get_existing(ws)

check_keys = [DATA["name"].lower(), DATA["telegram"].lower(), "vladtd.ru"]
if any(k in existing for k in check_keys):
    print("Уже есть в таблице — ничего не добавляю (проверка по имени/telegram/домену).")
    raise SystemExit(0)

all_values = ws.get_all_values()
existing_ids = [int(row[0]) for row in all_values[1:] if row and row[0].isdigit()]
next_id = max(existing_ids, default=0) + 1

add_company(ws, DATA, next_id)
print(f"Готово: VladTD добавлена с id={next_id}.")
print("Дальше: python3 update_site.py — подтянуть на сайт (ИНН указан, ЕГРЮЛ-проверка пройдёт автоматически).")
