"""
Правка 7 автодобавленных карточек (id 185–192) — 20.11.2026.

Что было не так (корень — company_agent берёт сниппеты поиска и мета-теги как есть):
- Авточекер (aboutauto.tech) — бот проверки VIN за 129 ₽, не компания по
  импорту авто → удалить.
- JapanAuc.com — японский аукционный агент (Кавасаки, оплата на счёт в Японии,
  40+ стран), не российский импортёр; телефон "80100012318" — мусор; в
  описании префикс "1 day ago ·" из сниппета → удалить из каталога.
- YUS-AVTO — настоящая компания (ООО «ЮС-АВТО», ИНН 7734450221, Москва,
  с 2022), но направления "Не указано" и телефон в кривом формате.
- «Заказать авто в Москву» — это og:site_name, а бренд на сайте «Заказ Авто
  Плюс»; направления взяты только США/ОАЭ, хотя на сайте шесть стран;
  телефон 77028133800 — казахстанский, основной РФ +7 (903) 181-22-50.
- idautos / zaiceVAvto / antaresavto — направления "Не указано", хотя в
  описании канала прямо написано Китай/Корея/Япония; в описании эмодзи и
  хвосты ссылок.

Данные сверены на сайтах yus-avto.ru и zakazautovplus.ru; для Telegram-каналов —
по текстам описаний из таблицы. Регион у каналов не ставим (не указан).

Запускать НА VPS:
    cd /var/www/myavto-agregator && git pull
    python3 fix_manual_data_2026_11_20_new_companies.py
    python3 update_site.py
"""

from company_agent import connect_sheets

COL_NAME, COL_YEARS, COL_DESC, COL_DIR, COL_TAGS = 1, 4, 6, 7, 8
COL_TG, COL_PHONE, COL_REGION, COL_INN = 9, 10, 13, 18
COL_WA, COL_EMAIL = 29, 31

DELETE_NAMES = ["Авточекер", "JapanAuc.com"]

FIXES = {
    "YUS-AVTO": {
        COL_DIR: "Европа, Китай, Корея, США, ОАЭ",
        COL_TAGS: "Под заказ, Проверка авто, Полное сопровождение",
        COL_PHONE: "+7 (925) 061-28-44",
        COL_REGION: "Москва",
        COL_INN: "7734450221",
        COL_EMAIL: "yusauto@gmail.com",
        COL_TG: "YUS_AVTO",
    },
    "Заказать авто в Москву": {
        COL_NAME: "Заказ Авто Плюс",
        COL_DESC: (
            "Авто под заказ из США, Европы, ОАЭ, Кореи, Китая и Канады: подбор, "
            "покупка, доставка и растаможка под ключ. Работают с 2006 года, "
            "доставка в Москву, по России и в Казахстан."
        ),
        COL_DIR: "США, Европа, ОАЭ, Корея, Китай",
        COL_PHONE: "+7 (903) 181-22-50",
        COL_REGION: "Москва",
        COL_WA: "https://wa.me/79031812250",
        COL_EMAIL: "aliger-pv@mail.ru",
        COL_TG: "autoVplus777",
    },
    # Japanexpert: сайт закрыт для автопроверки (robots.txt), поэтому правим
    # только очевидный мусор: префикс "2 days ago ·" и формат телефона.
    "Japanexpert": {
        COL_DESC: (
            "Онлайн-аукционы Японии (USS, TAA, ARAI, CAA, Honda, AUCNET, JU, NAA, "
            "LUM): цены, аукционные листы и фото."
        ),
        COL_PHONE: "+7 (924) 000-50-60",
    },
    "idautos": {
        COL_DESC: (
            "Привозят автомобили из Китая, Кореи и Японии «под ключ»: подбор, "
            "проверка, растаможка и доставка."
        ),
        COL_DIR: "Китай, Корея, Япония",
    },
    "zaiceVAvto": {
        COL_DESC: (
            "Авто под заказ из Кореи, Японии и Китая: экономия от 300 000 ₽, "
            "доставка 20–45 дней, бесплатный расчёт, охраняемая стоянка. "
            "Допуслуги: продажа авто, предпродажная подготовка, покраска."
        ),
        COL_DIR: "Корея, Япония, Китай",
    },
    "antaresavto": {
        COL_DESC: (
            "Привозят авто из Японии, Кореи и Китая: полное сопровождение от "
            "покупки до доставки, договор, гарантии, экономия до 30% от рыночной цены."
        ),
        COL_DIR: "Япония, Корея, Китай",
    },
}


def main():
    ws = connect_sheets()
    vals = ws.get_all_values()
    by_name = {}
    for i, row in enumerate(vals, start=1):
        if i > 1 and len(row) > COL_NAME:
            by_name.setdefault(row[COL_NAME].strip(), i)

    # 1. Правки (до удаления — номера строк ещё актуальны)
    for name, cols in FIXES.items():
        r = by_name.get(name)
        if not r:
            print(f"ПРОПУСК (нет в таблице): {name}")
            continue
        for c, v in cols.items():
            ws.update_cell(r, c + 1, v)
        print(f"OK правка: {name} (строка {r}), полей: {len(cols)}")

    # 2. Удаление, строки по убыванию
    rows = sorted((by_name[n], n) for n in DELETE_NAMES if n in by_name)
    for n in DELETE_NAMES:
        if n not in by_name:
            print(f"ПРОПУСК (нет в таблице): {n}")
    for r, n in reversed(rows):
        ws.delete_rows(r)
        print(f"OK удалено: {n} (строка {r})")

    print("Дальше: python3 update_site.py")


if __name__ == "__main__":
    main()
