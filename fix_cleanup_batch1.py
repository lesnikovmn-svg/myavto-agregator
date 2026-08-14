"""
Ревизия каталога 13-14.08.2026 — пользователь прислал список из 19 карточек
(id 80-98, все добавлены недавними прогонами агента) и попросил проверить
их сайты/соцсети и почистить. Разбор:

УДАЛЯЕМ (не компании-импортёры авто):
- id:80 "Telegram – a new era of messaging" — баг: ссылка "t.me/s" (служебный
  путь Telegram, не канал) распозналась как юзернейм "s". Код-баг исправлен
  в company_agent.py (проверка длины юзернейма >=5 + skip без tg).
- site содержит "aaajapan.com" — аукционная площадка, не импортёр (см.
  auction_sites.md), теперь и в BLACKLIST.
- site содержит "auto-praktis.vercel.app" — статья про проверку авто по VIN
  через Telegram-боты, не компания (лексикон is_vin_check_service дополнен).
- site содержит "tamozhennyy-broker.ru" — "Стандарт Групп", настоящий
  таможенный брокер (общие грузы). ПЕРЕНОСИТСЯ в раздел "Таможенные
  брокеры" на сайте (карточка добавлена вручную в index.html #customs),
  из каталога импортёров авто убирается.

ПЕРЕИМЕНОВЫВАЕМ (реальная компания, name был мусорным — заголовок статьи
или бренд площадки-зеркала вместо названия компании):
- site содержит "tgland.ru" (зеркало-каталог Telegram-каналов, само в
  BLACKLIST) -> name "Авто Заказ", site/vk/instagram зеркала очищены
  (принадлежат TGLand, не каналу).
- site содержит "korex-auto.com" -> name "KOREX", telegram поправлен
  (было "onteco" — чужой/неверный, реальный "korex_official").
- site содержит "afpodbor.ru" -> name "Auto Fact", добавлен telegram
  "autofactpodbor" (было пусто).
- site содержит "zenstat.ru" (зеркало Дзен-статистики, само в BLACKLIST)
  -> name "Растаможка Авто Под Ключ" (название канала), site очищен,
  добавлен telegram "autodoc77_ru".
- site содержит "autoleg.ru" -> name "Autolegal" (og:title/лого сайта),
  добавлен telegram "autolegal" (было пусто). Это НЕ таможенный брокер
  общих грузов — специализация именно на авто (ЭПТС/СБКТС/растаможка
  машин), остаётся в каталоге импортёров.
- site содержит "freetelegramgroups.com" (зеркало-каталог, само в
  BLACKLIST) -> name "AUTOCOM", site очищен.
- site содержит "telepot.ru" (зеркало-каталог, само в BLACKLIST) ->
  name "Tiger Cars", site очищен (telegram TJ_cars уже был верный).

БЕЗ ИЗМЕНЕНИЙ (уже корректны): Autoshtab, Fast Wheel, Hotcar.Online,
InCars, TAT IMPORT AVTO, EuroAutoTrade, OkAuto, Азия Авто Микс.

Запуск: python3 fix_cleanup_batch1.py
После — python3 update_site.py.
"""
from company_agent import connect_sheets

NAME_COL, TELEGRAM_COL, SITE_COL = 2, 10, 12
INSTAGRAM_COL, VK_COL = 22, 23

RENAMES = [
    # (подстрока в site, {колонка: новое значение})
    ("tgland.ru", {NAME_COL: "Авто Заказ", SITE_COL: "", INSTAGRAM_COL: "", VK_COL: ""}),
    ("korex-auto.com", {NAME_COL: "KOREX", TELEGRAM_COL: "korex_official"}),
    ("afpodbor.ru", {NAME_COL: "Auto Fact", TELEGRAM_COL: "autofactpodbor"}),
    ("zenstat.ru", {NAME_COL: "Растаможка Авто Под Ключ", SITE_COL: "", TELEGRAM_COL: "autodoc77_ru"}),
    ("autoleg.ru", {NAME_COL: "Autolegal", TELEGRAM_COL: "autolegal"}),
    ("freetelegramgroups.com", {NAME_COL: "AUTOCOM", SITE_COL: ""}),
    ("telepot.ru", {NAME_COL: "Tiger Cars", SITE_COL: ""}),
]

DELETE_SITE_SUBSTR = ["aaajapan.com", "auto-praktis.vercel.app", "tamozhennyy-broker.ru"]
DELETE_EXACT_NAME = ["Telegram – a new era of messaging"]

ws = connect_sheets()
all_values = ws.get_all_values()

rows_to_delete = []

for i, row in enumerate(all_values[1:], start=2):
    name = row[NAME_COL - 1].strip() if len(row) >= NAME_COL else ""
    site = row[SITE_COL - 1].strip().lower() if len(row) >= SITE_COL else ""

    if name in DELETE_EXACT_NAME or any(s in site for s in DELETE_SITE_SUBSTR):
        rows_to_delete.append((i, name))
        continue

    for substr, updates in RENAMES:
        if substr in site:
            print(f"[{i}] '{name}' ({substr}):")
            for col, val in updates.items():
                old_val = row[col - 1].strip() if len(row) >= col else ""
                ws.update_cell(i, col, val)
                print(f"    col {col}: '{old_val}' -> '{val}'")
            break

for i, name in sorted(rows_to_delete, reverse=True):
    print(f"Удаляю [{i}] '{name}'")
    ws.delete_rows(i)

print("\nТеперь прогони python3 update_site.py.")
