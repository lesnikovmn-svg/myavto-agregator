"""
Ручное добавление компании "MY AUTO" (my-auto.ru) — 12.08.2026.

Как всплыла: её ссылка (http://my-auto.ru) по ошибке оказалась в поле
autoru (Авто.ру) у карточки id:1 (MY Avto, компания самого автора) — тот
самый старый баг с подстрочной проверкой домена ("auto.ru" in link.lower()
ложно ловил ЛЮБОЙ домен, оканчивающийся на "auto.ru"), давно исправленный
в коде (_matches_domain_filter), но не тронутый на строке id:1, т.к. она
намеренно исключена из всех автоматических ревериферов/бэкофиллеров (см.
PROJECT_STATE.md, раздел про MY Avto). Саму мусорную ссылку в id:1 чистит
пользователь вручную. MY AUTO при этом — реальная, отдельная компания
(проверено вручную, my-auto.ru + t.me/myauto_premium, 617 подписчиков,
og:title/описание канала совпадают с сайтом), никак не связанная с
MY Avto — до сих пор не было отдельной карточки для неё в каталоге, эта
добавляет её.

Собрано вручную (WebFetch на my-auto.ru, /page111137596.html, t.me/myauto_premium):
- name: MY AUTO
- description: с главной страницы (og-title/hero)
- directions: Япония, Корея, Китай (сайт явно фильтрует по этим трём)
- tags: по get_tags() на тексте сайта ("под ключ", "в наличии", "аукцион" —
  у них "Аукционная оценка" на карточках авто)
- telegram: myauto_premium — подтверждено через t.me-превью (617 подписчиков,
  og:description с точным текстом сайта и телефоном); НЕ myautopremium (это
  всплывало как href на телефоне/кнопке "Написать менеджеру" на их же сайте,
  похоже опечатка в их вёрстке — сам канал живёт по адресу myauto_premium)
- phone/site/email/max/youtube/rutube/whatsapp — с сайта напрямую
- НЕ добавлено (не подтвердилось): vk (только vkvideo.ru/@club235888744 —
  видеоканал, не сама группа; vk.com/club235888744 не открылся для проверки
  содержимого — не рискуем добавлять неподтверждённое, см. философию сайта:
  "лучше не показать кнопку, чем показать неверную"), instagram, avito/drom/
  autoru (компания их не использует), yandex/2gis-карточки (не искали
  отдельно), ИНН (на сайте не публикуют, только "ИП Юрков И. А." без
  реквизитов).

Запуск: python3 add_myauto.py
После — python3 update_site.py.
"""
from company_agent import connect_sheets, get_existing, add_company

ws = connect_sheets()
existing = get_existing(ws)

if "my-auto.ru" in existing or "myauto_premium" in existing or "my auto" in existing:
    print("Похоже, уже есть в таблице — прерываю, проверь вручную.")
else:
    next_id = len(ws.get_all_values())
    data = {
        "name": "MY AUTO",
        "description": "Подбор, покупка и доставка авто из Японии, Южной Кореи и Китая с полной прозрачностью и фиксированными этапами",
        "directions": ["Япония", "Корея", "Китай"],
        "tags": ["Под ключ", "В наличии", "Аукционы"],
        "telegram": "myauto_premium",
        "phone": "+7 (902) 077-77-53",
        "site": "https://my-auto.ru",
        "youtube": "https://www.youtube.com/@MYAUTO.GLOBAL",
        "rutube": "https://rutube.ru/channel/75613601",
        "whatsapp": "https://wa.me/79020777753",
        "max": "https://max.ru/id253911506450_biz",
    }
    add_company(ws, data, next_id)
    print("Добавлено. Теперь прогони python3 update_site.py.")
