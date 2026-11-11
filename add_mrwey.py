"""
Ручное добавление MR. WEY (mrwey.ru) — 08.11.2026. Компания сама написала
Максиму письмом с просьбой о бесплатном добавлении в направление «Китай»
(платное размещение не рассматривают).

Данные проверены на самом сайте https://mrwey.ru/ (футер) и t.me/mr_wey,
а не взяты из письма:
- телефон/WhatsApp +7 995 108-86-11, личный Telegram @misterwey (кнопка
  «Связаться» на сайте), канал t.me/mr_wey (524 подписчика);
- реквизиты в футере: ИП Скляр Владислав Александрович, ИНН 254055668151,
  ОГРНИП 321253600038900 (ЕГРЮЛ/ЕГРИП-проверка пройдёт при update_site.py);
- «прямой агент и экспортёр», Китай → Россия, новые авто и с пробегом.
В письме указан email xw@mrwey.ru, на сайте — sales@mrwey.ru: в карточку
идёт тот, что на сайте. Регион не ставлю (ИНН 25.. — Приморский край, но
это вывод по коду региона, а не заявленный адрес).

Запускать НА VPS (нужен доступ к Google Sheets):
    cd /var/www/myavto-agregator
    python3 add_mrwey.py
    python3 update_site.py
"""

from company_agent import connect_sheets, get_existing, add_company

DATA = {
    "name": "MR. WEY",
    "description": (
        "Прямой агент и экспортёр авто из Китая в Россию: поиск, подбор, "
        "проверка (фото и видео до выкупа), покупка, экспорт и доставка. "
        "Новые автомобили и с пробегом, работа по договору."
    ),
    "directions": ["Китай"],
    "tags": ["Под заказ", "Проверка авто", "Полное сопровождение"],
    "telegram": "mr_wey",
    "telegram_contact": "misterwey",
    "phone": "+7 (995) 108-86-11",
    "whatsapp": "https://wa.me/79951088611",
    "site": "https://mrwey.ru",
    "inn": "254055668151",
    "email": "sales@mrwey.ru",
}

ws = connect_sheets()
existing = get_existing(ws)

check_keys = [DATA["name"].lower(), DATA["telegram"].lower(), "mrwey.ru"]
if any(k in existing for k in check_keys):
    print("Уже есть в таблице — ничего не добавляю (проверка по имени/telegram/домену).")
    raise SystemExit(0)

all_values = ws.get_all_values()
existing_ids = []
for row in all_values[1:]:
    if row and row[0].strip():
        try:
            existing_ids.append(int(float(row[0].strip())))
        except ValueError:
            pass
next_id = max(existing_ids, default=0) + 1

add_company(ws, DATA, next_id)
print(f"Готово: MR. WEY добавлена с id={next_id}.")
print("Дальше: python3 update_site.py. Лого и регион — проверить вручную.")
