#!/bin/bash
# Ежедневный автозапуск агента: ищет новые компании, синкает сайт, пушит.
# Логи пишутся в daily_update.log рядом со скриптом.

cd "$(dirname "$0")" || exit 1

LOG="daily_update.log"
echo "===== $(date '+%Y-%m-%d %H:%M:%S') =====" >> "$LOG"

# Предпочитаем venv с современным Python/OpenSSL (создаётся отдельно,
# см. README/PROJECT_STATE.md) — старый системный /usr/bin/python3 на
# LibreSSL не может достучаться до части сайтов (TLS-ошибка 0x304).
# Если venv ещё не создан, работаем по-старому на системном Python.
if [ -x "venv/bin/python3" ]; then
  PY="venv/bin/python3"
else
  PY="/usr/bin/python3"
fi

"$PY" company_agent.py >> "$LOG" 2>&1
"$PY" update_site.py >> "$LOG" 2>&1

echo "Готово: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG"
echo "" >> "$LOG"
