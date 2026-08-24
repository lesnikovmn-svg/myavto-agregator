"""
Диагностика: можно ли расширить поиск company_agent.py на компании,
раскрученные через личный бренд (блогеры), а не SEO — по вопросу
пользователя 24.08.2026, продолжение истории с "Лиса рулит"
(см. diag_lisa_rulit.py — обычные запросы её не нашли, только точный
запрос с её именем).

Идея (НЕ проверена вживую, сеть недоступна в песочнице Claude): раз таких
компаний теснят из топ-5 статьи/видео о них самих и карточки в каталогах
(Яндекс.Карты/2ГИС/Отзовик) — а не их собственный сайт, попробуем искать
ИМЕННО за счёт этого шума:
  1) запросы про "автоблогера"/YouTube-канал, а не про "импорт авто";
  2) запросы, нацеленные на карточки каталогов (Яндекс.Карты/2ГИС/Отзовик)
     по КАТЕГОРИИ бизнеса, а не по имени конкретной компании.

Ничего не пишет в Google Sheets. Для каждого запроса печатает результаты
И флаг: есть ли среди ссылок компании, КОТОРЫХ ЕЩЁ НЕТ в таблице (сверка
по домену через get_existing() — то же самое, что использует run_agent()
для дедупликации).

Запуск (на VPS, нужен доступ к Google Sheets + DuckDuckGo):
    python3 diag_personal_brand.py
"""

from company_agent import connect_sheets, get_existing, search_ddgs, base_domain

ws = connect_sheets()
existing = get_existing(ws)

CANDIDATE_QUERIES = [
    # 1) через блогерское/медийное освещение, а не через "импорт авто"
    "автоблогер обзор авто из Китая канал",
    "youtube канал перегон авто из Кореи Японии",
    "блогер продажа авто параллельный импорт",
    "инстаграм блогер авто на заказ из Европы",
    # 2) через карточки каталогов-агрегаторов, по категории
    "автосалон параллельный импорт отзывы",
    "site:2gis.ru автосалон параллельный импорт",
    "site:yandex.ru автосалон параллельный импорт отзывы",
]

print("=" * 70)
print("Новые кандидаты в запросы — ищем компании, которых ЕЩЁ НЕТ в таблице")
print("=" * 70)

for q in CANDIDATE_QUERIES:
    results = search_ddgs(q, 8)
    new_hits = []
    for r in results:
        link = r.get("link", "")
        if not link.startswith("http"):
            continue
        dom = base_domain(link)
        title = r.get("title", "")
        if dom and dom not in existing and title.lower() not in existing:
            new_hits.append(r)
    mark = f"✅ {len(new_hits)} новых" if new_hits else "— ничего нового"
    print(f"\n[{mark}] запрос: {q!r}")
    for r in results:
        dom = base_domain(r.get("link", ""))
        flag = "NEW" if (dom and dom not in existing) else "   "
        print(f"    [{flag}] {r.get('title','')[:65]} | {r.get('link','')}")

print("\n" + "=" * 70)
print("Готово. Если какая-то формулировка стабильно находит НОВЫЕ компании")
print("(не только шум/уже существующих) — можно добавить её в постоянный")
print("список ddg_queries в company_agent.py.")
print("=" * 70)
