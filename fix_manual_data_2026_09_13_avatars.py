"""
T-168 (13.09.2026, по запросу пользователя: "на примере автошут проверь
каталог у кого нет бейджа то посмотри на сайте например" — после находки
T-167 про AutoShoot, где вместо реального лого стоял прокси
google.com/s2/favicons, который не смог сконвертировать их SVG-фавикон).

МАСШТАБ. Сверка свежего app.js показала: у 69 из 141 компаний (49%) поле
`avatar` — это прокси `google.com/s2/favicons?domain=...`, а не реальный
логотип. Проверено вручную (заход на каждый сайт, разметка `<link
rel="icon">` + поиск логотипа в шапке) 69 из 69 — с исключениями: 6 сайтов
недоступны технически (см. раздел "МЁРТВЫЕ САЙТЫ" ниже), 1 заблокирован
защитой от ботов (encarrus.ru — "Проверка пользователя...", содержимое не
проверено).

НАЙДЕНО И ИСПРАВЛЕНО В ЭТОМ СКРИПТЕ (22 компании) — у всех проверен
реальный логотип в шапке их сайта, URL проверен на доступность
(fetch, no-cors, соединение прошло успешно):

Та же поломка, что у AutoShoot (T-167) — собственный favicon сайта в
формате SVG, из-за которого google.com/s2/favicons отдаёт вместо лого
generic-заглушку:
  - Westmotors (id 8), West-Motors.De (id 77) — визуально один бренд,
    разные домены/направления (.ru и .de), у обоих сломан прокси и у
    обоих есть настоящий images/logo.svg на сайте.
  - ТокиДоки (id 63), Честный Импорт (id 66), СЕВЕР АВТО (id 112),
    АИ Авто (id 70), Телеграм канал Levcar (id 108), Азия Авто Микс
    (id 95) — тот же паттерн (favicon.svg подтверждён на самом сайте).

Не сломано (у Google получилось бы отдать нормальную маленькую иконку),
но у компании есть отдельный полноценный логотип, который на карточке
будет выглядеть солиднее иконки 16-32px, растянутой до 128px:
  - Carwin (id 33), Todes-Avto (id 37, ФИКС ТЕЛЕФОНА уже в T-167 —
    отдельный столбец, не конфликтует), CarsKorea (id 48), Юнион Авто
    (id 29), GazTormoz (id 67), Ярдрей - Авто (id 64), Долгов Авто -
    Машины из Кореи,Японии,Китая. (id 110), Авто Азия (id 109), JpAuc.ru
    (id 114), Avtoban.Org (id 75), KOREX (id 82), AVADGE (id 106),
    Autocapital (id 47).

НЕ ИСПРАВЛЕНО — нужна доп. проверка, не автоматизировано этим скриптом:
  - Es-Transit (id 51), Autoshtab.com (id 84), Emirate Cars (id 78),
    ЖеняВозит (id 102) — подтверждён SVG-фавикон (та же поломка), но в
    шапке сайта явного отдельного лого-файла не нашёл при беглом
    просмотре — возможно, лого встроено как часть спрайта/фона, нужно
    смотреть глубже руками.
  - InCars (id 89), Hotcar.Online (id 87), China Trade/jptrade.ru
    (id 74), Prim-Auto (id 31), Jplife (id 32) — формально сработал
    SVG-детектор, но это, скорее всего, ложное срабатывание на
    safari-pinned-tab.svg (отдельная, не основная иконка для Safari) —
    основной favicon у них обычный PNG/ICO, вероятно, конвертируется
    Google нормально. Не трогал без более глубокой проверки.
  - Exclusive cars (id 96) — есть картинка "avatarka-dlya-yutub" (лого
    для YouTube), но не уверен, что это тот же логотип, что на сайте —
    не стал подставлять не проверив визуально.

МЁРТВЫЕ/НЕРАБОЧИЕ САЙТЫ (обнаружено попутно, НЕ логотип — отдельная
проблема, ничего не менял, только фиксирую находку для решения
пользователем — возможно, эти карточки стоит скрыть или вернуть на
доработку):
  - autogermanika.ru (id 50) — "402 Please renew your subscription"
    (у хостинга/домена истекла подписка).
  - automotive-china.ru (id 52) — заголовок вкладки прямо гласит
    "САЙТ automotive-china.ru НЕ РАБОТАЕТ".
  - limeeauto-tg.ru (id 61, "Автомобили из Кореи и Китая на заказ") —
    "Сайт в разработке".
  - avtoimportrus.ru (id 117) — Chrome блокирует переход,
    "Ошибка нарушения конфиденциальности" (битый SSL-сертификат).
  - auto-auc.online (id 62, "Япония Экспорт") — пустая страница без
    заголовка, favicon = data:, (пустой data URI) — похоже на
    неработающий/заброшенный сайт, требует ручной проверки.
  - encarrus.ru (id 68) — открыл "Проверка пользователя..." (защита от
    ботов), реальное содержимое не проверено, возможно сайт рабочий.

Запускать НА VPS (нужен доступ к Google Sheets):
    cd /var/www/myavto-agregator
    python3 fix_manual_data_2026_09_13_avatars.py
    python3 update_site.py
"""

from company_agent import connect_sheets

# Индексы колонок (0-based, см. add_company() в company_agent.py):
COL_NAME = 1
COL_AVATAR = 15

FIXES = {
    "Westmotors": {
        COL_AVATAR: "https://westmotors.ru/images/logo.svg",
    },
    "West-Motors.De": {
        COL_AVATAR: "https://west-motors.de/images/logo.svg",
    },
    "ТокиДоки": {
        COL_AVATAR: "https://tokidoki.su/img/ui/logo.svg",
    },
    "Честный Импорт": {
        COL_AVATAR: "https://chest-import.com/logo.svg",
    },
    "СЕВЕР АВТО": {
        COL_AVATAR: "https://severdv.online/netcat_files/c/sever_avto_logo.svg",
    },
    "АИ Авто": {
        COL_AVATAR: "https://ai-import.ru/assets/logo.webp",
    },
    "Телеграм канал Levcar": {
        COL_AVATAR: "https://static.tildacdn.com/tild3435-3039-4631-b364-316364366461/logo.svg",
    },
    "Азия Авто Микс": {
        COL_AVATAR: "https://asia-auto-mix.ru/images/logo.svg",
    },
    "Carwin": {
        COL_AVATAR: "https://carwin.ru/templates_files/images/logo.png",
    },
    "Todes-Avto": {
        COL_AVATAR: "https://todes-avto.ru/assets/logo-full.png",
    },
    "CarsKorea": {
        COL_AVATAR: "https://carskorea.shop/images/logo.svg",
    },
    "Юнион Авто": {
        COL_AVATAR: "https://unionauto.org/static/img/admin/logo/logo.svg",
    },
    "GazTormoz": {
        COL_AVATAR: "https://gaztormoz.ru/logo.svg",
    },
    "Ярдрей - Авто": {
        COL_AVATAR: "https://auto.yardrey.ru/wp-content/uploads/yardrey-auto-1024x452.png",
    },
    "Долгов Авто - Машины из Кореи,Японии,Китая.": {
        COL_AVATAR: "https://dolgov-auto.ru/wp-content/uploads/2026/03/header_logo.svg",
    },
    "Авто Азия": {
        COL_AVATAR: "https://static.tildacdn.com/tild6637-3731-4332-b461-623632336563/logo_1.svg",
    },
    "JpAuc.ru": {
        COL_AVATAR: "https://jpauc.ru/logo3d.png",
    },
    "Avtoban.Org": {
        COL_AVATAR: "https://avtoban.org/netcat_files/c/logo_avtoban.svg",
    },
    "KOREX": {
        COL_AVATAR: "https://korex-auto.com/netcat_files/c/logo.svg",
    },
    "AVADGE": {
        COL_AVATAR: "https://avadge.com/assets/images/logo.webp",
    },
    "Autocapital": {
        COL_AVATAR: "https://autocapital.ru/wp-content/uploads/2022/12/autocapital-1.png",
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
        print(f"Обновлена строка {row_num}: {name!r} -> avatar исправлен")

    print("Готово. Дальше: python3 update_site.py")
    print()
    print("НЕ ЗАБЫТЬ (не автоматизировано): 6 компаний с нерабочими сайтами")
    print("(см. docstring) — решить, что с ними делать (скрыть/убрать/подождать),")
    print("это отдельный вопрос от логотипов.")


if __name__ == "__main__":
    main()
