"""
Ручное добавление Lega Auto (t.me/LegaAuto) — 12.10.2026, по просьбе
пользователя: прислал скриншот канала ("есть в каталоге компания? ...
нужно добавить"). В каталоге не было (проверено по живому app.js: ни
названия, ни t.me/LegaAuto).

Данные ТОЛЬКО то, что подтверждено на t.me/LegaAuto и в закрепе канала
(название, описание, направления, контакты менеджеров, VK и YouTube).
Сайт, регион, ИНН НЕ найдены и НЕ выдуманы — оставлены пустыми/дефолтными
(по хэндлам менеджеров вроде @stass_ufa похоже на Уфу, но это догадка, не
факт — регион не ставлю). В описании канала VK обрезан ("vk.com/leg"), а в
закрепе — полная ссылка vk.com/legauto, взята оттуда.

Запускать НА VPS (нужен доступ к Google Sheets):
    cd /var/www/myavto-agregator
    python3 add_legaauto.py
    python3 update_site.py
"""

from company_agent import connect_sheets, get_existing, add_company

DATA = {
    "name": "Lega Auto",
    "description": (
        "Привоз авто из Кореи и Китая «под ключ»: расчёт стоимости, проверка "
        "перед покупкой, растаможка и оформление, юридическая чистота, "
        "доставка собственными автовозами по России."
    ),
    "directions": ["Корея", "Китай"],
    "tags": ["Под ключ", "Своя доставка"],
    "telegram": "LegaAuto",
    # Контакты — из закрепа канала (пользователь прислал текстом, 12.10.2026).
    # Менеджеров у компании много (Корея: Алексей @AlexTikhonoB, Вячеслав
    # @Kan080; Китай: Сергей @SergeyOko, Станислав, Николай, Дмитрий, Эдуард
    # и др.) — в карточку идёт ОДИН основной контакт (первый менеджер по
    # Корее с обычным телефоном, не MAX-номером). Поменять можно в таблице.
    "phone": "+7 (928) 229-96-26",
    "telegram_contact": "Kan080",
    "vk": "https://vk.com/legauto",
    "youtube": "https://youtube.com/@ZakazLegaAuto",
}

ws = connect_sheets()
existing = get_existing(ws)

check_keys = [DATA["name"].lower(), DATA["telegram"].lower()]
if any(k in existing for k in check_keys):
    print("Уже есть в таблице — ничего не добавляю (проверка по имени/telegram).")
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
print(f"Готово: Lega Auto добавлена с id={next_id}.")
print("Дальше: python3 update_site.py. Телефон/сайт/ВК/лого — доискать вручную.")
