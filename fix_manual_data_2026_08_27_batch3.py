"""
Третья волна ручной сверки за 27.08.2026 — пользователь продолжил находить
конкретные карточки на живом сайте отдельными сообщениями подряд ("давай уже
научи агента распозновать всё"). См. TASKS.md T-90 — там же разбор
СИСТЕМНОЙ причины (не только точечные фиксы ниже, но и правка
extract_brand_from_site() в company_agent.py, чтобы это не повторялось).

УДАЛИТЬ (4):
  - Autoimport.Trade (id 118) — проверено вручную на /produkt: это B2B-
    поставщик расходников для автосалонов (укрывные материалы, автохимия,
    автоэлектроника), НЕ занимается импортом/пригоном авто под заказ.
    Добавлен в BLACKLIST (company_agent.py).
  - RusDTP - Русские дороги (id 129) — новостная статья про ужесточение
    ввоза Минпромторгом, не компания. Добавлен в BLACKLIST.
  - Chinesecars.Sale (id 130) и Аукционы Японии (id 152, сайт vtransim.ru)
    — ОБА оказались той же самой компанией "Восток Транс Импорт", что и
    id 12 (koreacars.me): одинаковый шаблон сайта («18 лет опыта, 10 000+
    авто, 100+ площадок»), одинаковый телефон и Telegram (проверено вручную
    через живые сайты — vtransim.ru в футере даёт ровно тот же телефон
    +7(800)200-69-65 и тот же t.me/koreacarsme, что уже были у id 12).
    Компания просто держит отдельные лендинги под разные направления
    (Корея/Китай/Япония) — в каталоге это одна карточка, не три.

ОБНОВИТЬ (6):
  1) Восток Транс Импорт (id 12) — консолидация данных с vtransim.ru
     (официальный домен с полным футером контактов) + пользователь отметил
     "нет бейджа" (ЕГРЮЛ-бейдж не проставляется автоматически ни для одной
     карточки в каталоге — это отдельное системное ограничение, у сайта
     нет автопроверки по ЕГРЮЛ, egrulVerified нигде не вычисляется, см.
     TASKS.md T-90, требует отдельного решения, не трогаем в этом скрипте).
     Добавлены: сайт -> vtransim.ru, VK, email, MAX (все взяты из футера
     vtransim.ru вручную).
  2) EuroAutoTrade -> переименовано в "Элит Экспресс" — сайт euroautotrade.ru
     редиректит на приглашение в Telegram-группу, где реальное название
     "Элит Экспресс", контакты @igor_manaager / канал @ElitEkspress1.
  3) Fast Wheel — telegram (приватная инвайт-ссылка), WhatsApp, email —
     все взяты напрямую со страницы fast-wheel.ru/avto-iz-evropy (сайт на
     React, agent не видел JS-отрисованный футер до фикса T-89/Playwright).
  4) Todes-Avto — телефон, email, telegram взяты с todes-avto.ru (обычный
     server-rendered HTML, но агент почему-то не взял ни один контакт —
     возможно, сайт не индексировался DDG на момент первого обнаружения,
     карточка добавилась только с description).
  5) AutoEurope TOP -> переименовано в "Premium EuroAuto Russia" (реальное
     название телеграм-канала). Заодно поправлен год основания: тег "С 2008
     года" был неверным — сам канал прямо пишет "на рынке с 2024 года
     официально", исправлено на "С 2024 года" (и years=2). Контакт менеджера
     и WhatsApp взяты из закреплённых постов канала (у канала РОТИРУЮЩИЕСЯ
     контакты по разным постам — Ksenya_auto/+79047909341 и
     Kostya_managerr/+79012348255 оба встречались, в карточку взят первый).
  6) Яндекс (id 135) -> переименовано в "ES Transit Premium" — сайт
     estransit-premium.ru настоящий (не Яндекс, платформа просто попала в
     name/telegram по старому багу extract_brand_from_site, см. T-90).
     Реальный телефон, email, telegram канал (@estransitru, 44К подписчиков)
     и личный контакт менеджера (@estransitvip14) взяты с самого сайта.
  7) MAX (id 122) -> переименовано в "Долгов Авто" — та же болезнь, что
     "Яндекс" выше: og:site_name страницы-виджета max.ru/dolgov_auto1 был
     буквально "MAX" (название мессенджера), настоящее название — прямо в
     заголовке страницы ("Долгов Авто – авто из Китая, Кореи и Японии в
     мессенджере MAX").
  8) Tgsearch.Org (id 120) -> переименовано в "Solution Tracker Auto",
     telegram -> реальный хэндл "solutiontrackerauto" (был "tgschatbot" —
     это виджет "вступить через бота" каталога tgsearch.org, не хэндл
     самого канала). tgsearch.org — каталог-зеркало чужих Telegram-каналов
     (та же болезнь, что tgstat/tenchat/telagon и т.д. в BLACKLIST), НЕ
     добавлен в BLACKLIST целиком, т.к. в отличие от них не встречен ни
     разу как ложный источник статьи/бота — встречен один раз именно как
     источник неверного НАЗВАНИЯ, что уже чинит фикс extract_brand_from_site
     (T-90). Content компании (перекупщики авто) не проверен на соответствие
     нише "импорт под заказ" — оставлено на усмотрение пользователя.

НЕ ВОШЛО в этот скрипт (нужно решение пользователя, не просто фикс данных):
  - Стандарт (id 149, растаможка под ключ) — пользователь попросил
    "перенести в брокеры", но в текущей схеме сайта нет отдельной категории
    "Таможенные брокеры" (только направления-страны в фильтре) — нужна
    отдельная фича, не строчечный фикс.
  - ЕГРЮЛ-бейдж — egrulVerified нигде не вычисляется автоматически ни для
    одной карточки в каталоге, это системное ограничение, а не баг одной
    компании — нужно отдельное решение (ручная простановка/API ЕГРЮЛ).

Запускать НА VPS (нужен доступ к Google Sheets):
    cd /var/www/myavto-agregator
    python3 fix_manual_data_2026_08_27_batch3.py
    python3 update_site.py
"""

from company_agent import connect_sheets

# Индексы колонок (0-based, см. add_company() в company_agent.py):
COL_NAME = 1
COL_YEARS = 4
COL_DESCRIPTION = 6
COL_DIRECTIONS = 7
COL_TAGS = 8
COL_TELEGRAM = 9
COL_PHONE = 10
COL_SITE = 11
COL_YANDEX = 17
COL_VK = 22
COL_MAX = 26
COL_WHATSAPP = 29
COL_TELEGRAM_CONTACT = 30
COL_EMAIL = 31

DELETE_NAMES = [
    "Autoimport.Trade",
    "RusDTP - Русские дороги",
    "Chinesecars.Sale",
    "Аукционы Японии",
]

FIXES = {
    "Восток Транс Импорт": {
        COL_SITE: "https://vtransim.ru/",
        COL_VK: "https://vk.com/vtransimm",
        COL_MAX: "https://max.ru/koreacarsme",
        COL_EMAIL: "mg5@vtransim.ru",
    },
    "EuroAutoTrade": {
        COL_NAME: "Элит Экспресс",
        COL_DESCRIPTION: (
            "Пригон авто из Европы в РФ. Подбор, проверка, таможня, "
            "доставка, постановка на учёт. Полное сопровождение, гарантия "
            "юридической чистоты. Лучшие цены на рынке!"
        )[:200],
        COL_TELEGRAM: "ElitEkspress1",
        COL_TELEGRAM_CONTACT: "igor_manaager",
    },
    "Fast Wheel": {
        COL_TELEGRAM: "+Ay_pqrjlFYs4NWYy",
        COL_WHATSAPP: "https://wa.me/message/XWA6EFI3QOH6F1",
        COL_EMAIL: "mail@fast-wheel.ru",
    },
    "Todes-Avto": {
        COL_PHONE: "+7 (499) 961-15-71",
        COL_EMAIL: "info@todes-avto.ru",
        COL_TELEGRAM: "todes_avto",
    },
    "AutoEurope TOP": {
        COL_NAME: "Premium EuroAuto Russia",
        COL_YEARS: "2",
        COL_TAGS: "С 2024 года,Трейд-ин,РБ и РФ",
        COL_DESCRIPTION: (
            "Пригон автомобилей из Европы под ключ. На рынке с 2024 года "
            "официально. Подбор, выкуп, доставка, трейд-ин. Сотни отзывов "
            "по РФ и РБ."
        )[:200],
        COL_TELEGRAM_CONTACT: "Ksenya_auto",
        COL_WHATSAPP: "https://wa.me/+79047909341",
    },
    "Яндекс": {
        COL_NAME: "ES Transit Premium",
        COL_TELEGRAM: "estransitru",
        COL_TELEGRAM_CONTACT: "estransitvip14",
        COL_PHONE: "+7 (908) 444-00-14",
        COL_EMAIL: "estransit23@yandex.ru",
    },
    "MAX": {
        COL_NAME: "Долгов Авто",
    },
    "Tgsearch.Org": {
        COL_NAME: "Solution Tracker Auto",
        COL_TELEGRAM: "solutiontrackerauto",
    },
}


def main():
    ws = connect_sheets()
    all_values = ws.get_all_values()

    rows_to_delete = []
    for i, row in enumerate(all_values[1:], start=2):
        name = row[COL_NAME].strip() if len(row) > COL_NAME else ""
        if name in DELETE_NAMES:
            rows_to_delete.append((i, name))
    found = {name for _, name in rows_to_delete}
    for name in set(DELETE_NAMES) - found:
        print(f"ПРОПУСК (не найдена для удаления): {name}")
    for row_num, name in sorted(rows_to_delete, key=lambda x: -x[0]):
        ws.delete_rows(row_num)
        print(f"Удалена строка {row_num}: {name}")

    all_values = ws.get_all_values()
    for name, fields in FIXES.items():
        row_num = None
        for i, row in enumerate(all_values[1:], start=2):
            if len(row) > COL_NAME and row[COL_NAME].strip() == name:
                row_num = i
                break
        if row_num is None:
            print(f"ПРОПУСК (не найдена для правки): {name}")
            continue
        for col_idx, value in fields.items():
            ws.update_cell(row_num, col_idx + 1, value)  # gspread — 1-based колонки
        new_name = fields.get(COL_NAME, name)
        print(f"Обновлена строка {row_num}: {name!r} -> полей изменено: {len(fields)} (имя: {new_name!r})")

    print("Готово. Дальше: python3 update_site.py")


if __name__ == "__main__":
    main()
