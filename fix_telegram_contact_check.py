"""
Проверка Telegram-контактов компаний — 14.08.2026, по просьбе пользователя:
кнопка "Написать в TG" на сайте использует поле telegram как есть, но
агент часто находит именно КАНАЛ компании (tgstat специально ищет
каналы) — у канала нет чата, написать напрямую нельзя. Кнопка на сайте
уже поправлена (приоритет WhatsApp > Telegram > сайт > телефон), но сами
данные в таблице это не чинит — если единственный контакт компании это
канал, кнопки "написать" всё равно не будет ни у кого, кроме WhatsApp.

Что делает скрипт для каждой компании с непустым telegram:
1. Идёт на https://t.me/<handle> (публичная превью-страница, без токена).
2. Смотрит, есть ли в тексте "N subscribers" (канал) или "N members"
   (группа) — если ни того ни другого нет, это, вероятнее всего, личный
   аккаунт или бот, то есть УЖЕ messageable — ничего не трогаем.
3. Если это канал/группа — ищет в og:description ДРУГОЙ @юзернейм
   (не сам канал), который часто указывают в описании как контакт для
   связи ("по вопросам: @ivan_avto"). Если находит — идёт и на НЕГО тоже,
   проверяет, что это НЕ ещё один канал/группа (чтобы не подменить один
   непрямой контакт на другой), и если подтвердилось — заменяет telegram
   на этот новый юзернейм.
4. Если альтернативного контакта не нашлось — ОЧИЩАЕТ поле telegram
   (пусто). Это осознанное решение: лучше честно откатиться на
   WhatsApp/сайт/телефон (уже реализовано в кнопке на сайте), чем вести
   посетителя в канал, где написать нельзя.

Ограничения (важно): эвристика не идеальна — часть личных Telegram-
аккаунтов тоже НЕ показывает "subscribers"/"members" сразу (это нормально,
считаем messageable), но часть каналов может не попасть под регулярку по
другой причине и остаться нетронутой. Результат стоит один раз проглядеть
глазами по логу перед тем, как запускать рассылку.

Делает паузы между запросами (1 сек), чтобы не долбить t.me слишком часто.

Запуск: python3 fix_telegram_contact_check.py
После — python3 update_site.py.
"""
import re
import time
import requests
from company_agent import connect_sheets

TELEGRAM_COL = 10
NAME_COL = 2

HEADERS = {"User-Agent": "Mozilla/5.0"}


def fetch_tg_page(handle):
    try:
        r = requests.get(f"https://t.me/{handle}", timeout=8, headers=HEADERS)
        if r.status_code != 200:
            return None
        return r.text
    except Exception:
        return None


def classify(html):
    """Возвращает 'channel', 'group' или 'contact' (личный/бот — messageable)."""
    if not html:
        return "unknown"
    if re.search(r"[\d\s]+\s*subscribers", html):
        return "channel"
    if re.search(r"[\d\s]+\s*members", html):
        return "group"
    return "contact"


def find_alt_contact(html, own_handle):
    desc_m = re.search(r'<meta property="og:description" content="([^"]*)"', html)
    desc = desc_m.group(1) if desc_m else ""
    for cand in re.findall(r"@([A-Za-z0-9_]{5,32})", desc):
        if cand.lower() != own_handle.lower():
            return cand
    return None


ws = connect_sheets()
all_values = ws.get_all_values()

kept, replaced, cleared, unknown = 0, 0, 0, 0

for i, row in enumerate(all_values[1:], start=2):
    handle = row[TELEGRAM_COL - 1].strip() if len(row) >= TELEGRAM_COL else ""
    name = row[NAME_COL - 1].strip() if len(row) >= NAME_COL else ""
    if not handle:
        continue

    html = fetch_tg_page(handle)
    time.sleep(1)
    kind = classify(html)

    if kind == "contact":
        kept += 1
        continue
    if kind == "unknown":
        print(f"[{i}] {name} (@{handle}): не удалось загрузить превью, оставляю как есть")
        unknown += 1
        continue

    # channel/group — ищем альтернативу
    alt = find_alt_contact(html, handle)
    if alt:
        alt_html = fetch_tg_page(alt)
        time.sleep(1)
        alt_kind = classify(alt_html)
        if alt_kind == "contact":
            ws.update_cell(i, TELEGRAM_COL, alt)
            print(f"[{i}] {name}: {kind} @{handle} -> найден личный контакт @{alt}, заменил")
            replaced += 1
            continue
        else:
            print(f"[{i}] {name}: {kind} @{handle}, альтернатива @{alt} тоже оказалась {alt_kind} — не годится")

    ws.update_cell(i, TELEGRAM_COL, "")
    print(f"[{i}] {name}: {kind} @{handle}, альтернативы не нашлось — очистил поле (сайт откатится на WhatsApp/сайт/телефон)")
    cleared += 1

print(f"\nИтого: оставлено как есть (уже контакт) — {kept}, заменено на личный контакт — {replaced}, "
      f"очищено (был канал/группа без альтернативы) — {cleared}, не удалось проверить — {unknown}")
print("\nТеперь прогони python3 update_site.py.")
