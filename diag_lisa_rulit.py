"""
Диагностика: почему company_agent.py не находит автосалон "Лиса рулит"
(lenalisa.ru, Елена Лисовская) — по вопросу пользователя 24.08.2026.

Ничего не пишет в Google Sheets, только печатает результаты DuckDuckGo для
ТЕХ ЖЕ запросов, что использует run_agent() (Шаг 2), плюс несколько
дополнительных формулировок — чтобы увидеть глазами, попадает ли lenalisa.ru
в топ-5 и, если нет, какая фраза сработала бы лучше.

Запуск (на VPS, где есть доступ к DuckDuckGo — в песочнице Claude сети нет):
    python3 diag_lisa_rulit.py
"""

from company_agent import search_ddgs, SELLING_PHRASES

TARGET_MARKERS = ["lenalisa", "лиса рулит", "лисовская"]


def check(query, results):
    hit = False
    for r in results:
        blob = (r.get("title", "") + " " + r.get("snippet", "") + " " + r.get("link", "")).lower()
        if any(m in blob for m in TARGET_MARKERS):
            hit = True
    return hit


print("=" * 70)
print("ЧАСТЬ 1: те же запросы, что использует run_agent() (Шаг 2)")
print("=" * 70)

ddg_queries = [
    "импорт авто Telegram канал Россия",
    "авто из Кореи Китая под заказ Telegram",
    "пригон авто аукцион Япония сайт",
    "авто США ОАЭ Европа под заказ",
    "импорт авто официальный сайт Россия",
]
ddg_queries += [p + " Telegram канал" for p in SELLING_PHRASES]

any_hit = False
for q in ddg_queries:
    results = search_ddgs(q, 5)
    hit = check(q, results)
    any_hit = any_hit or hit
    mark = "✅ НАШЛОСЬ" if hit else "—"
    print(f"\n[{mark}] запрос: {q!r}")
    for r in results:
        print(f"    {r.get('title','')[:70]} | {r.get('link','')}")

print("\n" + "=" * 70)
print(f"ИТОГ ЧАСТИ 1: {'lenalisa.ru нашлась хотя бы раз' if any_hit else 'lenalisa.ru НЕ нашлась ни разу'}")
print("=" * 70)

print("\n" + "=" * 70)
print("ЧАСТЬ 2: альтернативные формулировки — есть ли запрос, который её находит")
print("=" * 70)

extra_queries = [
    "автосалон параллельный импорт Москва",
    "автосалон Лиса рулит",
    "купить авто параллельный импорт Москва в наличии",
    "автосалон авто в наличии параллельный импорт из Китая",
]
for q in extra_queries:
    results = search_ddgs(q, 5)
    hit = check(q, results)
    mark = "✅ НАШЛОСЬ" if hit else "—"
    print(f"\n[{mark}] запрос: {q!r}")
    for r in results:
        print(f"    {r.get('title','')[:70]} | {r.get('link','')}")
