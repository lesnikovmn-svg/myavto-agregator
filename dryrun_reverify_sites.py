"""
DRY RUN — ничего не пишет в таблицу и не трогает сайт. Только печатает
отчёт: что новый алгоритм (обход "Контакты"/"О нас" + весь набор
извлечения — ИНН/телефон/vk/instagram/avito/drom/autoru/max/youtube/
rutube/whatsapp/яндекс/2ГИС, см. company_agent.py) нашёл бы для КАЖДОЙ
существующей компании с заполненным сайтом, и чем это отличается от
того, что уже есть в таблице — чтобы посмотреть глазами ПЕРЕД тем, как
что-то менять (по просьбе пользователя: "прогнать нашу базу по новому
алгоритму, только результат предварительно проверить не менять сайт").

Логика отчёта — максимально консервативная, чтобы не заваливать шумом:
- ПУСТЫЕ поля в таблице, для которых новый алгоритм что-то нашёл на
  сайте — предлагаем заполнить.
- НЕ предлагаем менять поля, которые уже чем-то заполнены (могут быть
  верны и без подтверждения с этого конкретного сайта — трогать руками).
- name — отдельно: если текущее имя выглядит как "тэглайн" (see
  is_probably_tagline) ИЛИ как имя, произведённое из домена (Title Case
  без пробелов вроде "Auto-Auc"), а сайт отдаёт другое og:site_name —
  предлагаем переименовать.

id:1 (MY Avto, собственная компания автора) пропускаем полностью — не
трогаем и не проверяем автоматически, как и в остальных fix-скриптах.

Некоторые сайты защищены антиботом/полностью на JS (пример, 10.08.2026:
auto-auc.online отдаёт страницу "Loading... JavaScript отключен" + ссылку
на "Антибот Клауд", а при заходе через браузер там ещё и капча — обходить
капчи агенту запрещено правилами безопасности). Такие компании раньше
молча проваливались в "ничего не нашлось"; теперь (looks_like_bot_wall)
явно ловятся и попадают в отдельный список "ТРЕБУЮТ РУЧНОЙ ПРОВЕРКИ" в
конце отчёта — по просьбе пользователя ("все такие компании тоже нужно
подсвечивать для ручного ввода"). Та же функция подключена и в
company_agent.py (run_agent, ветка DuckDuckGo) — при обычном прогоне
такие компании тоже явно помечаются в логе (🚧), а не тихо получают имя
из домена без пометки.

Запуск: python3 dryrun_reverify_sites.py > reverify_report.txt
Дальше — обсудить с Claude, что из отчёта применять, и только тогда
писать/запускать отдельный fix-скрипт на конкретные строки.
"""
import re
import time
import gspread
from google.oauth2.service_account import Credentials
from company_agent import (
    fetch_site_text, find_subpage_urls, fetch_extra_site_text,
    extract_brand_from_site, extract_inn, extract_phone,
    extract_direct_contacts, is_probably_tagline, domain_of,
    looks_like_bot_wall,
)

config = {}
with open("agent_config.env") as f:
    for line in f:
        if "=" in line:
            k, v = line.strip().split("=", 1)
            config[k] = v
SHEET_ID = config["SHEET_ID"]

scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
client = gspread.authorize(creds)
ws = client.open_by_key(SHEET_ID).sheet1

ID_COL, NAME_COL = 1, 2
TELEGRAM_COL, PHONE_COL, SITE_COL = 10, 11, 12
INN_COL = 19
GIS2_COL, INSTAGRAM_COL, VK_COL = 21, 22, 23
AVITO_COL, DROM_COL, AUTORU_COL = 24, 25, 26
MAX_COL, YOUTUBE_COL, RUTUBE_COL, WHATSAPP_COL = 27, 28, 29, 30

DIRECT_FIELDS = [
    ("vk", VK_COL), ("instagram", INSTAGRAM_COL),
    ("avito", AVITO_COL), ("drom", DROM_COL), ("autoru", AUTORU_COL),
    ("max", MAX_COL), ("youtube", YOUTUBE_COL), ("rutube", RUTUBE_COL),
    ("whatsapp", WHATSAPP_COL), ("gis2", GIS2_COL),
]


def cell(row, col_1idx):
    idx = col_1idx - 1
    return row[idx].strip() if len(row) > idx and row[idx] else ""


def looks_domain_derived(name, site):
    """Похоже ли текущее имя на "сырое" имя из домена (Title Case из
    доменного имени, без пробелов/с дефисами) — например 'Auto-Auc' из
    auto-auc.online."""
    if not name or not site:
        return False
    dom = domain_of(site)
    if not dom:
        return False
    base = re.sub(r"\.(ru|com|online|net|su|org)$", "", dom)
    base_norm = re.sub(r"[\-_.]", "", base).lower()
    name_norm = re.sub(r"[\-_.\s]", "", name).lower()
    return base_norm == name_norm


all_values = ws.get_all_values()
rows = all_values[1:]
print(f"Всего компаний: {len(rows)}\n{'='*70}")

needs_manual = []  # (row_i, name, site, причина)

for i, row in enumerate(rows, start=2):
    cid = cell(row, ID_COL)
    name = cell(row, NAME_COL)
    site = cell(row, SITE_COL)
    if not name or cid == "1" or name.strip().lower() == "my avto":
        continue
    if not site.startswith("http"):
        continue

    print(f"[{i}] проверяю {name} ({site})...", flush=True)
    html = fetch_site_text(site)
    if not html:
        print(f"[{i}] {name} ({site}): сайт не ответил / пусто — пропускаю")
        needs_manual.append((i, name, site, "сайт не отвечает (недоступен/таймаут)"))
        time.sleep(1)
        continue

    if looks_like_bot_wall(html):
        print(f"[{i}] {name} ({site}): 🚧 антибот/капча — автоматически не читается")
        needs_manual.append((i, name, site, "антибот/капча — нужен ручной ввод"))
        time.sleep(1)
        continue

    have_inn = bool(extract_inn(html))
    have_phone = extract_phone(html) != "-"
    if not (have_inn and have_phone):
        extra = fetch_extra_site_text(html, site)
        if extra:
            html += extra

    findings = []

    brand = extract_brand_from_site(html)
    current_tagline = is_probably_tagline(name)
    current_domain_like = looks_domain_derived(name, site)
    if brand and brand.strip().lower() != name.strip().lower() and (current_tagline or current_domain_like):
        findings.append(f"name: '{name}' -> '{brand}' (og:site_name сайта)")

    if not cell(row, INN_COL):
        inn = extract_inn(html)
        if inn:
            findings.append(f"inn: '' -> '{inn}'")

    if not cell(row, PHONE_COL) or cell(row, PHONE_COL) == "-":
        phone = extract_phone(html)
        if phone != "-":
            findings.append(f"phone: '{cell(row, PHONE_COL) or '-'}' -> '{phone}'")

    if not cell(row, TELEGRAM_COL):
        tm = re.search(r"https?://(?:www\.)?t\.me/([A-Za-z0-9_]+)", html, re.IGNORECASE)
        if tm:
            findings.append(f"telegram: '' -> '{tm.group(1)}'")

    direct = extract_direct_contacts(html)
    for field_name, col in DIRECT_FIELDS:
        if not cell(row, col) and direct.get(field_name):
            findings.append(f"{field_name}: '' -> '{direct[field_name]}'")

    if findings:
        print(f"\n[{i}] {name} ({site})")
        for f in findings:
            print(f"    {f}")
    time.sleep(1)

print(f"\n{'='*70}")
if needs_manual:
    print(f"ТРЕБУЮТ РУЧНОЙ ПРОВЕРКИ ({len(needs_manual)}) — сайт не читается автоматически "
          f"(антибот/капча/недоступен), нужно зайти самому и прислать название + соцсети:")
    for i, name, site, reason in needs_manual:
        print(f"  [{i}] {name} ({site}) — {reason}")
else:
    print("Все сайты прочитались автоматически, ручная проверка не нужна.")
print(f"\nГотово. Это только ОТЧЁТ — в таблицу ничего не записано.")
