#!/bin/bash
# Ежедневный автозапуск агента: ищет новые компании, синкает сайт, пушит.
# Логи пишутся в daily_update.log рядом со скриптом.

cd "$(dirname "$0")" || exit 1

LOG="daily_update.log"
echo "===== $(date '+%Y-%m-%d %H:%M:%S') =====" >> "$LOG"

/usr/bin/python3 company_agent.py >> "$LOG" 2>&1
/usr/bin/python3 update_site.py >> "$LOG" 2>&1

echo "Готово: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG"
echo "" >> "$LOG"
