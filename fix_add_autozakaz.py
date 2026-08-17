"""
НАПОМИНАНИЕ (конвенция проекта): перед запуском поставь именованную версию
в Google Таблице — Файл → История версий → Назвать текущую версию →
"до fix_add_autozakaz" → Сохранить.

Добавление новой компании "Автозаказ.ру" — 17.08.2026, по запросу
пользователя (прислал скриншот TG-канала @auto_zakazz25, 481К подписчиков,
"проштудируй сайт, собери всю информацию"). Все данные ниже проверены
вживую (fetch реального сайта autozakaz.ru + карточки Яндекс.Карт), никто
не выдуман:

  сайт:        https://autozakaz.ru/ (og:site_name "Автозаказ.ру")
  описание:    "Покупка и доставка авто из Японии, Кореи и Китая под заказ
               до вашего города." (meta-description сайта)
  направления: Япония, Корея, Китай (+ мотоциклы, отдельная категория
               менеджеров на сайте — вынесено в tags)
  регион:      Владивосток (адрес на сайте и в карточке Яндекс.Карт
               совпадает: ул. Днепровская, 21)
  ИНН:         250818340283 (ИП Селезнёв Максим Вячеславович, ОГРН
               317253600092564 — из футера сайта)
  телефон:     +7 953 215-38-88 — подтверждён ДВАЖДЫ независимо: и на
               самом сайте (менеджер по Японии Сергей), и как основной
               контакт в карточке Яндекс.Карт.
  рейтинг:     4.4, 782 отзыва — реальные цифры с карточки Яндекс.Карт
               (yandex.com/maps/org/autozakaz_ru/140791872893), не
               выдуманы.
  telegram (канал):   auto_zakazz25 — с присланного пользователем
               скриншота самого канала (там же указан дубль-хэндл
               auto_zakaz25, но текущая ссылка "ссылка" на канале — именно
               auto_zakazz25, его и берём).
  telegram_contact:   logistAZbot — с самого канала: "Бот для обратной
               связи и отслеживания вашего автомобиля" — ровно та
               категория контакта, что уже используется в проекте для
               ботов-контактов (см. extract_site_tg_contact() в
               company_agent.py).
  vk:          https://vk.com/auto_zakaz25 (совпадает на сайте и в
               карточке Яндекс.Карт)
  youtube:     https://www.youtube.com/@Autozakazru (с сайта)
  max:         https://max.ru/auto_zakazz25 (с сайта, мессенджер MAX)
  whatsapp:    https://wa.me/79644527888 (с карточки Яндекс.Карт)
  yandex:      https://yandex.com/maps/org/autozakaz_ru/140791872893/
               (канонический адрес карточки, короткая ссылка с сайта
               автоматически на него ведёт)
  google:      https://g.co/kgs/opDGBJW (ссылка "Отзывы в Google" с сайта)
  gis2:        https://go.2gis.com/Igal1 (ссылка на адрес с сайта,
               короткая — не резолвится без JS в песочнице, но это
               собственная ссылка компании, оставляем как есть)
  email:       не найден нигде на сайте — оставляем пустым, ничего не
               выдумываем.

Логотип (avatar) — 17.08.2026, по отдельной просьбе пользователя
("лейб можно брать с тг канала например, с сайта и прикреплять в
каталоге в карточке компании"): взял квадратный логотип с самого сайта
(meta msapplication-TileImage, уже обрезан в квадрат 270x270, тот же
дизайн — тёмно-синий круг с "AZ", что и на аватарке TG-канала).
Записываем прямую ссылку на изображение — рендеринг карточки (index.html,
renderCompanies()) теперь умеет отличать avatar-URL от avatar-инициалов
(см. avatarHtml, коммит этой же сессии) и показывает настоящую картинку
вместо цветных инициалов. Слушай: ссылка внешняя (хостится на сайте
компании, не у нас) — если компания поменяет/удалит файл, лого на карточке
пропадёт. Продублировать себе никогда не поздно, но осторожно
поменять/удалить файл, лого на карточке пропадёт.

Проверяет дубли по домену/telegram ПЕРЕД добавлением — если "autozakaz.ru"
или "auto_zakazz25"/"auto_zakaz25" уже есть в таблице, ничего не
добавляет, только предупреждает.

Запуск: python3 fix_add_autozakaz.py
После — python3 update_site.py.
"""
from company_agent import connect_sheets

ID_COL = 1
NAME_COL = 2
TELEGRAM_COL = 10
SITE_COL = 12

ws = connect_sheets()
all_values = ws.get_all_values()
rows = all_values[1:]


def cell(row, col_1idx):
    idx = col_1idx - 1
    return row[idx].strip() if len(row) > idx and row[idx] else ""


max_id = 0
for row in rows:
    cid = cell(row, ID_COL)
    if cid.isdigit():
        max_id = max(max_id, int(cid))

    site_l = cell(row, SITE_COL).lower()
    tg_l = cell(row, TELEGRAM_COL).lower()
    if "autozakaz.ru" in site_l or tg_l in ("auto_zakazz25", "auto_zakaz25"):
        print(f"Уже есть в таблице: {cell(row, NAME_COL)!r} (site={site_l!r}, "
              f"telegram={tg_l!r}) — ничего не добавляю, проверь вручную.")
        raise SystemExit(0)

new_id = max_id + 1

row = [
    str(new_id),                        # id
    "Автозаказ.ру",                     # name
    "4.4",                              # rating (Яндекс.Карты, реальное)
    "782",                              # reviews (Яндекс.Карты, реальное)
    "10",                               # years (работают с 2016)
    "-",                                # delivered
    "Покупка и доставка авто из Японии, Кореи и Китая под заказ до вашего города.",  # description
    "Япония,Корея,Китай",               # directions
    "Мотоциклы,Под ключ",               # tags
    "auto_zakazz25",                    # telegram (канал)
    "+7 953 215-38-88",                 # phone
    "https://autozakaz.ru/",            # site
    "-",                                # manager
    "Владивосток",                      # region
    "FALSE",                            # featured
    "https://autozakaz.ru/wp-content/uploads/2025/01/cropped-az-logo-minimal-270x270.webp",  # avatar (реальный логотип)
    "av-gray",                          # color (не используется, когда avatar — URL)
    "https://yandex.com/maps/org/autozakaz_ru/140791872893/",  # yandex
    "250818340283",                     # inn
    "https://g.co/kgs/opDGBJW",         # google
    "https://go.2gis.com/Igal1",        # gis2
    "",                                 # instagram
    "https://vk.com/auto_zakaz25",      # vk
    "",                                 # avito
    "",                                 # drom
    "",                                 # autoru
    "https://max.ru/auto_zakazz25",     # max
    "https://www.youtube.com/@Autozakazru",  # youtube
    "",                                 # rutube
    "https://wa.me/79644527888",        # whatsapp
    "logistAZbot",                      # telegram_contact (бот обратной связи)
    "",                                 # email (не найден)
]

ws.append_row(row, table_range='A1')
print(f"Добавлено: Автозаказ.ру (id {new_id})")
print("Теперь прогони python3 update_site.py.")
