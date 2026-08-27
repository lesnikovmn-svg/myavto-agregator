"""
T-92 (27.08.2026): ежедневный сбор статистики подписчиков (Telegram/VK/
Instagram) по всем компаниям каталога — первая часть задачи "статистика
активности компаний" (по прямому запросу пользователя: "давай сначала
подписчики в соц сетях, тг, инста, вк, пересчёт давай в экселе отдельная
вкладка статистика, давай каждый день писать, если будет большая
загрузка сделаем реже"). Отзывы рядом с Яндекс/Google/2ГИС — вторая
часть задачи, будет отдельным скриптом позже (см. TASKS.md T-92).

Пишет ОДНУ строку в день на каждую компанию во вкладку "Статистика"
(создаётся сама при первом запуске, см. sheets_client.connect_stats_sheet)
— дата, id, название, подписчики Telegram/Instagram/VK. Сама таблица
компаний (sheet1) НЕ трогается, только читается. Со временем накопится
история — дальше рост считается как разница между строками за период,
без этого скрипта считать не из чего.

Запускать НА VPS (нужен доступ к Google Sheets):
    cd /var/www/myavto-agregator
    python3 collect_social_stats.py

Добавить в crontab для ежедневного запуска (например, в 04:00 МСК —
после ночного прогона company_agent.py, чтобы оба скрипта не долбили
Google Sheets API одновременно):
    0 4 * * * cd /var/www/myavto-agregator && python3 collect_social_stats.py >> logs/social_stats.log 2>&1

Если компаний станет много и прогон начнёт занимать слишком долго
(на каждую компанию — до 3 последовательных HTTP-запросов: tgstat/t.me,
vk.com, instagram.com, плюс sleep(1) между компаниями, чтобы не долбить
соцсети параллельно) — пользователь сам попросил в этом случае снизить
частоту (через день или раз в неделю), просто поменяв cron-выражение
выше, код менять не нужно.
"""

import datetime
import time

from sheets_client import connect_sheets, connect_stats_sheet
from company_agent import (
    parse_tgstat_channel,
    fetch_telegram_preview,
    fetch_vk_members,
    fetch_instagram_followers,
)

# Индексы колонок в главном листе компаний (0-based, см. add_company()
# в company_agent.py):
COL_ID = 0
COL_NAME = 1
COL_TELEGRAM = 9
COL_INSTAGRAM = 21
COL_VK = 22


def telegram_subscribers(username):
    """tgstat.ru обычно точнее и не требует прокси — пробуем первым,
    t.me/<username> как резерв (та же логика, что в run_agent())."""
    if not username:
        return 0
    info = parse_tgstat_channel(username)
    if info and info.get("subscribers"):
        return info["subscribers"]
    info = fetch_telegram_preview(username)
    return info["subscribers"] if info else 0


def main():
    ws = connect_sheets()
    stats_ws = connect_stats_sheet()
    rows = ws.get_all_values()[1:]
    today = datetime.date.today().isoformat()

    out_rows = []
    for row in rows:
        if len(row) <= COL_NAME or not row[COL_NAME].strip():
            continue
        cid = row[COL_ID].strip() if len(row) > COL_ID else ""
        name = row[COL_NAME].strip()
        telegram = row[COL_TELEGRAM].strip() if len(row) > COL_TELEGRAM else ""
        vk = row[COL_VK].strip() if len(row) > COL_VK else ""
        insta = row[COL_INSTAGRAM].strip() if len(row) > COL_INSTAGRAM else ""

        tg_subs = telegram_subscribers(telegram)
        vk_subs = fetch_vk_members(vk)
        insta_subs = fetch_instagram_followers(insta)

        out_rows.append([today, cid, name, tg_subs, insta_subs, vk_subs])
        print(f"  {name}: TG={tg_subs}, Insta={insta_subs}, VK={vk_subs}")
        time.sleep(1)  # не долбить соцсети параллельными запросами подряд

    if out_rows:
        stats_ws.append_rows(out_rows, table_range="A1")

    print(f"Готово: записано {len(out_rows)} строк за {today} во вкладку 'Статистика'.")


if __name__ == "__main__":
    main()
