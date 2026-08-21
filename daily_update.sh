#!/bin/bash
# Ежедневный автозапуск агента на VPS: ищет новые компании, синкает сайт, пушит.
cd /var/www/myavto-agregator || exit 1
LOG="daily_update.log"
echo "===== $(date '+%Y-%m-%d %H:%M:%S') =====" >> "$LOG"
# T-27 (21.08.2026): бэкап ДО того, как агент что-либо поменяет в таблице —
# если сегодняшний прогон испортит данные (баг агента/эвристики), вчерашний
# бэкап останется чистым снапшотом для отката.
python3 backup_sheets.py >> "$LOG" 2>&1
python3 company_agent.py >> "$LOG" 2>&1
python3 update_site.py >> "$LOG" 2>&1
echo "Готово: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG"
echo "" >> "$LOG"
