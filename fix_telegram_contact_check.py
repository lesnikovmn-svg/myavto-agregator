"""
Заполнение колонки "Telegram (личный/бот)" — переписано 14.08.2026.

Была версия, которая при обнаружении канала/группы ЗАТИРАЛА поле telegram
(если не находила альтернативу) или ПОДМЕНЯЛА его найденным личным контактом.
По итогам обсуждения с пользователем решили иначе: поле telegram (колонка J,
10) — это канал/группа компании, само по себе полезно (человек может на него
подписаться), трогать его не нужно. Вместо этого используем отдельную
колонку 31 (AE, "Telegram (личный/бот)", см. add_tg_contact_column.py) —
именно её кнопка "Написать в TG" на сайте использует для отправки сообщения.
Эту колонку нужно создать один раз ДО первого запуска этого скрипта.

Что делает скрипт для каждой компании с непустым telegram (колонка J):
1. Идёт на https://t.me/<handle> (публичная превью-страница, без токена).
2. Смотрит, есть ли в тексте "N subscribers" (канал) или "N members"
   (группа) — если ни того ни другого нет, это, вероятнее всего, личный
   аккаунт или бот, то есть УЖЕ messageable. В этом случае просто копируем
   тот же handle и в колонку "личный/бот" — кнопка сайта сможет им
   пользоваться напрямую.
3. Если это канал/группа — ищет в og:description ДРУГОЙ @юзернейм
   (не сам канал), который часто указывают в описании как контакт для
   связи ("по вопросам: @ivan_avto"). Если находит — идёт и на НЕГО тоже,
   проверяет, что это НЕ ещё один канал/группа, и если подтвердилось —
   записывает его в колонку "личный/бот".
4. Если альтернативного контакта не нашлось — колонку "личный/бот" НЕ
   трогаем (оставляем пустой). Кнопка на сайте в этом случае сама
   откатится на WhatsApp/VK/Instagram/сайт/телефон — canal-поле при этом
   остаётся на месте как есть.

Ограничения: эвристика не идеальна — часть личных Telegram-аккаунтов тоже
НЕ показывает "subscribers"/"members" сразу (это нормально, считаем
messageable), но часть каналов может не попасть под регулярку и остаться
без личного контакта, хотя он в описании и есть в другом виде. Результат
стоит один раз проглядеть глазами по логу перед тем, как запускать
рассылку.

Делает паузы между запросами (1 сек), чтобы не долбить t.me слишком часто.

Запуск (после add_tg_contact_column.py): python3 fix_telegram_contact_check.py
После — python3 update_site.py.
"""
import re
import time
import requests
from company_agent import connect_sheets

TELEGRAM_COL = 10
TG_CONTACT_COL = 31
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

header = ws.cell(1, TG_CONTACT_COL).value
if not header:
    print(f"Колонка {TG_CONTACT_COL} (AE) ещё не создана — сначала запусти "
          f"python3 add_tg_contact_column.py")
    raise SystemExit(1)

already_contact, found_alt, no_alt, unknown = 0, 0, 0, 0

for i, row in enumerate(all_values[1:], start=2):
    handle = row[TELEGRAM_COL - 1].strip() if len(row) >= TELEGRAM_COL else ""
    name = row[NAME_COL - 1].strip() if len(row) >= NAME_COL else ""
    existing_contact = row[TG_CONTACT_COL - 1].strip() if len(row) >= TG_CONTACT_COL else ""
    if not handle or existing_contact:
        continue

    html = fetch_tg_page(handle)
    time.sleep(1)
    kind = classify(html)

    if kind == "contact":
        ws.update_cell(i, TG_CONTACT_COL, handle)
        print(f"[{i}] {name} (@{handle}): уже личный контакт/бот — скопировал в колонку AE")
        already_contact += 1
        continue
    if kind == "unknown":
        print(f"[{i}] {name} (@{handle}): не удалось загрузить превью, пропускаю")
        unknown += 1
        continue

    # channel/group — ищем альтернативу, поле telegram НЕ трогаем
    alt = find_alt_contact(html, handle)
    if alt:
        alt_html = fetch_tg_page(alt)
        time.sleep(1)
        alt_kind = classify(alt_html)
        if alt_kind == "contact":
            ws.update_cell(i, TG_CONTACT_COL, alt)
            print(f"[{i}] {name}: {kind} @{handle}, канал остаётся как есть, личный контакт @{alt} записан в AE")
            found_alt += 1
            continue
        else:
            print(f"[{i}] {name}: {kind} @{handle}, альтернатива @{alt} тоже оказалась {alt_kind} — не годится")

    print(f"[{i}] {name}: {kind} @{handle}, личного контакта не нашлось — колонка AE остаётся пустой, "
          f"кнопка сайта откатится на WhatsApp/VK/Instagram/сайт/телефон")
    no_alt += 1

print(f"\nИтого: уже был личный контакт (скопировано в AE) — {already_contact}, "
      f"найден альтернативный контакт — {found_alt}, "
      f"личного контакта не нашлось (AE пусто, канал не тронут) — {no_alt}, "
      f"не удалось проверить — {unknown}")
print("\nТеперь прогони python3 update_site.py.")
