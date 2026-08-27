"""
Ручная донастройка 4 карточек — 27.08.2026, по репорту пользователя после
самостоятельной проверки живого сайта ("почему агент не смотрит сайт
компании и вносит данные в карточку?"). Для каждой — открыл реальный
сайт/telegram через Claude in Chrome и нашёл настоящие данные, которые
агент не подхватил (см. TASKS.md T-87 — там же разбор ПОЧЕМУ агент их не
взял сам, по каждому случаю отдельно).

1) Global Car Trade — агент нашёл компанию через пост в Telegram-канале
   (@globalcartrade), а не через сайт: ветка кода для "источник — тг-канал"
   вообще не заходит на сайт компании, даже если он упомянут в описании
   канала. На сайте globalcartrade.ru нашлись: реальное название, ИНН/ОГРН,
   email, адрес офиса.
2) "Аукционы Японии" -> "Восток Транс Импорт" (vtransim.ru) — тот же класс
   бага, что "Premium Import"/"Стандарт" в T-79: настоящее название лежит
   обычным текстом в шапке сайта рядом с лого, а не в <title>/og:site_name,
   которые агент проверяет — попал фрагмент SEO-title вместо бренда.
3) Delivery Cars — сайт delivery-cars.ru визуально современный (похоже на
   React/Next.js), agent успешно взял название/описание/телефон с главной
   страницы (это server-rendered текст), но telegram-контакт менеджера,
   email и ссылка на MAX лежат в футере — возможно, дорисовываются JS после
   загрузки и не попадают в сырой HTML, который агент запрашивает обычным
   HTTP-запросом без исполнения JS (агент не открывает браузер, как это
   делает Claude in Chrome). Заодно нашли отдельный баг: ссылка на MAX была
   в формате "max.ru/+79895653943" (номер телефона), а не "max.ru/username"
   — старая регулярка такой формат не ловила вообще (см. правку
   DIRECT_CONTACT_PATTERNS в company_agent.py, уже исправлено).
4) AUTOCOM — описание было мусорной конкатенацией с сайта-каталога
   Telegram-каналов ("... - a Telegram channel with 3482 members - ...",
   английский фрагмент выдаёт источник) — не сама компания, домен этого
   каталога не установлен (агент не логирует, с какого URL взял текст).
   Реальная компания — autocom.by (Беларусь, 15 лет на рынке, офисы в
   Москве/Минске/Краснодаре), telegram-канал @AUTOCOMINFO.

Запускать НА VPS (нужен доступ к Google Sheets):
    cd /var/www/myavto-agregator
    python3 fix_manual_data_2026_08_27.py
    python3 update_site.py
"""

from company_agent import connect_sheets

# Индексы колонок (0-based, см. add_company() в company_agent.py):
COL_NAME = 1
COL_DESCRIPTION = 6
COL_DIRECTIONS = 7
COL_TAGS = 8
COL_TELEGRAM = 9
COL_PHONE = 10
COL_SITE = 11
COL_REGION = 13
COL_INN = 18
COL_MAX = 26
COL_YOUTUBE = 27
COL_WHATSAPP = 29
COL_TELEGRAM_CONTACT = 30
COL_EMAIL = 31

FIXES = {
    "Аукционы Японии": {
        COL_NAME: "Восток Транс Импорт",
        COL_PHONE: "+7 (800) 200-69-65",
    },
    "Авто под заказ - Global Car Trade": {
        COL_NAME: "Global Car Trade",
        COL_DESCRIPTION: (
            "Авто из Южной Кореи, Японии и Китая под заказ — прямой "
            "поставщик, опыт более 10 лет, своё представительство в "
            "Южной Корее (с 2024 года, ООО «Глобал Кар Трейд»). Двойная "
            "проверка авто перед покупкой, полное таможенное оформление."
        )[:200],
        COL_DIRECTIONS: "Корея,Япония,Китай",
        COL_PHONE: "8 (800) 350-36-20",
        COL_SITE: "https://globalcartrade.ru/",
        COL_REGION: "Владивосток",
        COL_INN: "2543182808",
        COL_EMAIL: "globalcartrade@internet.ru",
    },
    "Delivery Cars": {
        COL_TELEGRAM: "AutoDeliveryCars",
        COL_TELEGRAM_CONTACT: "DeliveryCars_Manager",
        COL_EMAIL: "manager@delivery-cars.ru",
        COL_MAX: "https://max.ru/+79895653943",
    },
    "AUTOCOM": {
        COL_DESCRIPTION: (
            "Авто под заказ из Европы, США, Кореи и Китая — 15 лет в "
            "автобизнесе, офисы-шоурумы в Москве, Минске и Краснодаре, "
            "более 10 менеджеров, работа без посредников напрямую с "
            "аукционами."
        )[:200],
        COL_DIRECTIONS: "Европа,США,Корея,Китай",
        COL_PHONE: "+375 29 639-85-33",
        COL_SITE: "https://autocom.by/",
        COL_REGION: "Беларусь",
        COL_TELEGRAM: "AUTOCOMINFO",
    },
}


def main():
    ws = connect_sheets()
    all_values = ws.get_all_values()

    for name, fields in FIXES.items():
        row_num = None
        for i, row in enumerate(all_values[1:], start=2):
            if len(row) > COL_NAME and row[COL_NAME].strip() == name:
                row_num = i
                break
        if row_num is None:
            print(f"ПРОПУСК (не найдена): {name}")
            continue
        for col_idx, value in fields.items():
            ws.update_cell(row_num, col_idx + 1, value)  # gspread — 1-based колонки
        new_name = fields.get(COL_NAME, name)
        print(f"Обновлена строка {row_num}: {name!r} -> полей изменено: {len(fields)} (имя: {new_name!r})")

    print("Готово. Дальше: python3 update_site.py")


if __name__ == "__main__":
    main()
