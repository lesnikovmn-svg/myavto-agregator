"""
Диагностика (read-only): показать последние добавленные компании для
ручной проверки — 17.08.2026, по запросу пользователя ("перепроверь
последнее добавление компаний, есть боты, есть статьи").

Та же болезнь, что уже несколько раз ловилась раньше (см. BLACKLIST в
company_agent.py, комментарии от 09.08/10.08/13.08/14.08): агент при
обычном поиске иногда утаскивает НЕ компанию, а:
  - новостную статью/блог-пост об импорте авто (сайт крупного портала),
  - каталог-зеркало Telegram-каналов (не сайт самой компании),
  - маркетплейс продажи готового Telegram-бота,
  - сам Telegram-бот (не канал компании, не человек) — если "телеграм"
    похож на @something_bot, это, скорее всего, бот, а не компания.
Ничего не меняет, только печатает — конкретные решения (удалить/
переименовать/оставить) принимает пользователь, как и в прошлые разы
(см. fix_new_batch_18.py — тот же формат работы).

Печатает последние N строк по id (самые свежедобавленные — id
присваивается по возрастанию в add_company()), для каждой: id, name,
site, telegram, gis2 — и отдельно помечает эвристически подозрительные
(telegram похож на бота, site содержит типичные для статей/каталогов
слова).

Запуск: python3 check_last_batch.py           # последние 25
        python3 check_last_batch.py 40         # последние 40
"""
import sys

from company_agent import connect_sheets

ID_COL = 1
NAME_COL = 2
SITE_COL = 12
TELEGRAM_COL = 10
GIS2_COL = 21

N = int(sys.argv[1]) if len(sys.argv) > 1 else 25

SUSPECT_SITE_WORDS = [
    "blog", "news", "статья", "novosti", "catalog", "каталог", "zеркал",
    "зеркал", "otzyv", "отзыв", "market", "маркет", "vc.ru", "habr.com",
    "dzen.ru", "zen.yandex", "tenchat", "42.tut.by",
]
SUSPECT_TG_SUFFIXES = ("bot", "_bot", "robot")

ws = connect_sheets()
all_values = ws.get_all_values()

rows = []
for row in all_values[1:]:
    def val(col):
        return row[col - 1].strip() if len(row) >= col else ""

    company_id = val(ID_COL)
    name = val(NAME_COL)
    if not name:
        continue
    try:
        id_num = int(company_id)
    except ValueError:
        id_num = -1
    rows.append({
        "id": company_id,
        "id_num": id_num,
        "name": name,
        "site": val(SITE_COL),
        "telegram": val(TELEGRAM_COL),
        "gis2": val(GIS2_COL),
    })

rows.sort(key=lambda r: r["id_num"], reverse=True)
last_n = rows[:N]

print(f"Последние {len(last_n)} компаний по id (самые свежедобавленные сверху):\n")
for r in last_n:
    tg = r["telegram"].lstrip("@").lower()
    site_l = r["site"].lower()

    flags = []
    if tg.endswith(SUSPECT_TG_SUFFIXES):
        flags.append("telegram похож на БОТА")
    if any(w in site_l for w in SUSPECT_SITE_WORDS):
        flags.append("сайт похож на статью/каталог/зеркало")
    if not r["site"] and not r["telegram"]:
        flags.append("нет ни сайта, ни telegram — нечем идентифицировать")

    flag_str = f"  ⚠️ {', '.join(flags)}" if flags else ""
    print(f"[{r['id']}] {r['name']!r} | site={r['site'] or '—'} | telegram={r['telegram'] or '—'}{flag_str}")

print(f"\nВсего компаний в таблице: {len(rows)}.")
print("Эвристика может пропустить реальный мусор или ложно пометить нормальную "
      "компанию (например, если в названии случайно есть 'market') — финальное "
      "решение по каждой строке за тобой, как и в прошлые разы (fix_new_batch_18.py).")
