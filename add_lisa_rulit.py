"""
Ручное добавление автосалона "Лиса рулит" (lenalisa.ru, Елена Лисовская) —
24.08.2026, по вопросу пользователя "почему агент не нашел импортера Лиса
рулит?". Диагностика (diag_lisa_rulit.py) подтвердила: обычные поисковые
формулировки её не находят — компания живёт на личном бренде блогера
(1.8 млн подписчиков), а не на SEO, поэтому её нет в топ-5 DuckDuckGo по
общим запросам вроде "параллельный импорт Москва". Добавлять её название
в постоянный список запросов агента бессмысленно (нашёл бы только её),
поэтому — добавляем вручную, как и MY Avto (id:1).

Данные собраны вручную с https://lenalisa.ru/ (сайт открылся без антибота):
- сайт: lenalisa.ru, телефон продаж, Telegram/VK/YouTube из футера сайта.
- направления: Китай/Корея/Япония/Европа/США — по ассортименту марок в
  каталоге сайта (Geely/BYD/Chery — Китай, Hyundai/KIA — Корея,
  Toyota/Honda/Mazda — Япония, BMW/Audi/Mercedes/Volvo — Европа, GMC — США).

Запускать НА VPS (нужен доступ к Google Sheets):
    cd /var/www/myavto-agregator
    python3 add_lisa_rulit.py
"""

from company_agent import connect_sheets, get_existing, add_company

DATA = {
    "name": "Лиса рулит",
    "description": (
        "Автосалон «Лиса рулит» Елены Лисовской — параллельный импорт "
        "новых и б/у авто из Китая, Кореи, Японии, Европы и США, кредит, "
        "лизинг, трейд-ин, доставка под ключ."
    ),
    "directions": ["Китай", "Корея", "Япония", "Европа", "США"],
    "tags": ["Автосалон", "В наличии и под заказ"],
    "telegram": "lisarulitsales",
    "phone": "+7 (909) 999-08-70",
    "site": "https://lenalisa.ru",
    "region": "Москва",
    "vk": "https://vk.com/lisarulit777",
    "youtube": "https://www.youtube.com/@lenalisa33",
    "whatsapp": "https://wa.me/79099990870",
    "years": "4",  # параллельным импортом занимается с 2022 (после ухода брендов)
}

ws = connect_sheets()
existing = get_existing(ws)

check_keys = [DATA["name"].lower(), DATA["telegram"].lower(), "lenalisa.ru"]
if any(k in existing for k in check_keys):
    print("Уже есть в таблице — ничего не добавляю (проверка по имени/telegram/домену).")
    raise SystemExit(0)

all_values = ws.get_all_values()
existing_ids = [int(row[0]) for row in all_values[1:] if row and row[0].isdigit()]
next_id = max(existing_ids, default=0) + 1

add_company(ws, DATA, next_id)
print(f"Готово: «Лиса рулит» добавлена с id={next_id}.")
print("Дальше: python3 update_site.py — подтянуть на сайт (ЕГРЮЛ по ИНН не проверялся, ИНН не указан).")
