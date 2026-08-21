#!/bin/bash
# T-23 (21.08.2026): раньше `git pull` на VPS подтягивал новый
# telegram_bot_service.py на диск, но systemd продолжал крутить в памяти
# старый процесс — новые роуты (например /api/visit) не работали, пока
# кто-то не вспоминал сделать `systemctl restart telegram-bot` руками.
# Этот скрипт — единая точка входа для деплоя на VPS: тянет изменения и
# сам перезапускает бота, только если поменялся именно тот файл, который
# бот реально исполняет (index.html и прочий статик рестарта не требуют,
# nginx отдаёт их с диска напрямую).
#
# Использование на VPS:
#   cd /var/www/myavto-agregator && ./deploy.sh
set -e
cd "$(dirname "$0")"

BEFORE=$(git rev-parse HEAD)
git pull
AFTER=$(git rev-parse HEAD)

if [ "$BEFORE" = "$AFTER" ]; then
  echo "Изменений нет, HEAD уже $AFTER."
  exit 0
fi

echo "Обновлено: $BEFORE -> $AFTER"

if git diff --name-only "$BEFORE" "$AFTER" | grep -q '^telegram_bot_service\.py$'; then
  echo "telegram_bot_service.py изменился — перезапускаю бота..."
  systemctl restart telegram-bot
  echo "Готово, бот перезапущен."
else
  echo "telegram_bot_service.py не менялся, рестарт не нужен."
fi
