"""
НАПОМИНАНИЕ (конвенция проекта): перед запуском поставь именованную версию
в Google Таблице — Файл → История версий → Назвать текущую версию →
"до fix_add_or_update_electrocar" → Сохранить.

ElectroCar (electro-car.by) — 14.08.2026, по запросу пользователя (прислал
скриншот личного профиля @YanSharapov в Telegram с подписью "компания
ElectroCar", попросил добавить, если её ещё нет в каталоге).

Данные собраны вручную через реальный fetch/просмотр сайта (не выдумано):
- Юрлицо: ООО «ЯАР Групп», сайт electro-car.by (og:site_name "Electrocar").
- Основана в 2019 году (страница /o-kompanii/) → стаж 7 лет на 2026 год.
- Продажа электромобилей из Китая "под ключ": подбор, проверка, выкуп,
  доставка (ЖД/автовоз), таможня, предпродажная подготовка, кредит/лизинг.
  Работают БЕЗ ПОСРЕДНИКОВ — собственный офис в Китае (г. Ченду).
- Шоурум: г. Минск, ул. Свердлова, д.23/4-1. Регион — Беларусь, не Россия
  (add_company() поддерживает data["region"] с 14.08.2026, см.
  company_agent.py и раздел "Улучшения алгоритма" в PROJECT_STATE.md).
- Телефон компании (с сайта, не личный Яна): +375 (29) 649-99-43.
- Telegram-канал компании (официальный, со шапки сайта): @electrocarby.
- Личный контакт (владелец, подтверждён): @YanSharapov — проверено
  fetch'ом t.me/YanSharapov: title "Telegram: Contact @YanSharapov",
  кнопка "Send Message" — настоящий messageable-контакт, не канал.
- Instagram: instagram.com/electro_car.by
- YouTube: youtube.com/channel/UCYUPAOjZLRq_f2LS0VOYWVQ
- Яндекс.Карты: yandex.by/maps/-/CLfP4JNl (короткая ссылка с самого сайта)
- ИНН/УНП на сайте не нашёлся (Беларусь использует УНП, не ИНН — ЕГРЮЛ-
  проверка на такие компании всё равно не рассчитана, это ожидаемо).

Что делает скрипт:
1. Ищет существующую строку по имени (варианты "electrocar"/"electro-car"/
   "electro car", без учёta регистра/пробелов/дефисов) ИЛИ по домену
   electro-car.by в колонке site.
2. Если нашлась РОВНО ОДНА — дозаполняет только ПУСТЫЕ поля (никогда не
   перезаписывает), как в fix_contacts_verified_14082026.py.
3. Если нашлось 0 — добавляет новую строку через add_company() с полным
   набором данных выше.
4. Если нашлось больше 1 — ничего не делает, печатает предупреждение
   (проверить дубли вручную).

Запуск: python3 fix_add_or_update_electrocar.py
После — python3 update_site.py.
"""
import re

from company_agent import connect_sheets, add_company

NAME_COL = 2
TELEGRAM_COL = 10
PHONE_COL = 11
SITE_COL = 12
REGION_COL = 14
YANDEX_COL = 18
INSTAGRAM_COL = 22
YOUTUBE_COL = 28
TG_CONTACT_COL = 31

DATA = {
    "name": "ElectroCar",
    "description": "Electro-car.by (ООО «ЯАР Групп») — продажа и доставка "
                    "электромобилей \"под ключ\" из Китая: подбор, проверка, "
                    "выкуп, доставка, таможня, предпродажная подготовка. "
                    "Работают без посредников — собственный офис в Китае "
                    "(Ченду). Шоурум в Минске, основаны в 2019 году.",
    "directions": ["Китай"],
    "tags": ["Под ключ", "Без посредников", "В наличии"],
    "telegram": "electrocarby",
    "phone": "+375 (29) 649-99-43",
    "site": "https://electro-car.by/",
    "years": "7",
    "region": "Беларусь",
    "yandex": "https://yandex.by/maps/-/CLfP4JNl",
    "instagram": "https://www.instagram.com/electro_car.by/",
    "youtube": "https://www.youtube.com/channel/UCYUPAOjZLRq_f2LS0VOYWVQ",
    "telegram_contact": "YanSharapov",
}

FIELD_TO_COL = {
    "telegram": TELEGRAM_COL, "phone": PHONE_COL, "site": SITE_COL,
    "region": REGION_COL, "yandex": YANDEX_COL, "instagram": INSTAGRAM_COL,
    "youtube": YOUTUBE_COL, "telegram_contact": TG_CONTACT_COL,
}


def norm(s):
    return re.sub(r"[\s\-]", "", s).lower()


ws = connect_sheets()
all_values = ws.get_all_values()

target_variants = {norm("electrocar"), norm("electro-car"), norm("electro car")}

matches = []
for i, row in enumerate(all_values[1:], start=2):
    name = row[NAME_COL - 1].strip() if len(row) >= NAME_COL else ""
    site = row[SITE_COL - 1].strip() if len(row) >= SITE_COL else ""
    if norm(name) in target_variants or "electro-car.by" in site:
        matches.append(i)

if len(matches) > 1:
    print(f"Нашёл {len(matches)} строк, похожих на ElectroCar (строки {matches}) — "
          f"ничего не делаю, проверь дубли вручную.")
elif len(matches) == 1:
    row_idx = matches[0]
    row = all_values[row_idx - 1]
    print(f"ElectroCar уже есть в таблице (строка {row_idx}) — дозаполняю пустые поля.")
    written = 0
    for field, col in FIELD_TO_COL.items():
        current = row[col - 1].strip() if len(row) >= col else ""
        if current:
            continue
        ws.update_cell(row_idx, col, DATA[field])
        print(f"  {field} -> {DATA[field]}")
        written += 1
    print(f"Записано полей: {written}.")
else:
    print("ElectroCar в таблице не найден — добавляю новую компанию.")
    next_id = len(all_values) + 1
    add_company(ws, DATA, next_id)

print("\nТеперь прогони python3 update_site.py.")
