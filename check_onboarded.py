"""
Показывает, какие компании из каталога УЖЕ онбордились у Telegram-бота
(нажали /start, бот может им писать заявки), а какие ещё нет — 14.08.2026,
по запросу пользователя ("как посмотреть были ли онбоард?").

Онбординг компании = она хоть раз написала боту /start (см.
telegram_bot_service.py, handle_start() -> ветка "не заявка клиента,
username совпал с telegram-полем компании в таблице"). Список
онбордившихся хранится в bot_state.json НА VPS (chat_id клиентов/компаний
— оперативные данные бота, не в Google Sheets и не в git).

Этот скрипт запускать НА VPS (там лежит bot_state.json) — либо по SSH,
либо скопировать bot_state.json на Мак (scp root@89.108.70.185:/var/www/
myavto-agregator/bot_state.json .) и запустить локально рядом с ним.
Доступ к Google Sheets (для списка ВСЕХ компаний с telegram) нужен в
любом случае — credentials.json/agent_config.env должны быть в той же
папке, где запускается скрипт.

Запуск: python3 check_onboarded.py
"""
import json
import os

from company_agent import connect_sheets

STATE_FILE = "bot_state.json"
NAME_COL = 2
TELEGRAM_COL = 10

if not os.path.exists(STATE_FILE):
    print(f"Не нашёл {STATE_FILE} в текущей папке.\n"
          f"Он лежит на VPS: /var/www/myavto-agregator/bot_state.json\n"
          f"Либо запусти этот скрипт по SSH прямо на VPS, либо скачай файл:\n"
          f"  scp root@89.108.70.185:/var/www/myavto-agregator/bot_state.json .")
    raise SystemExit(1)

with open(STATE_FILE, encoding="utf-8") as f:
    state = json.load(f)

onboarded_handles = set(state.get("companies", {}).keys())

ws = connect_sheets()
all_values = ws.get_all_values()

onboarded, not_onboarded, no_telegram = [], [], []

for row in all_values[1:]:
    name = row[NAME_COL - 1].strip() if len(row) >= NAME_COL else ""
    handle = row[TELEGRAM_COL - 1].strip().lstrip("@").lower() if len(row) >= TELEGRAM_COL else ""
    if not name:
        continue
    if not handle:
        no_telegram.append(name)
    elif handle in onboarded_handles:
        onboarded.append((name, handle))
    else:
        not_onboarded.append((name, handle))

print(f"Онбордились ({len(onboarded)}):")
for name, handle in onboarded:
    print(f"  ✓ {name} (@{handle})")

print(f"\nЕЩЁ НЕ онбордились ({len(not_onboarded)}) — этим компаниям нужно "
      f"прислать ссылку на бота t.me/MyAvtoAgregator_bot и попросить нажать /start:")
for name, handle in not_onboarded:
    print(f"  ✗ {name} (@{handle})")

if no_telegram:
    print(f"\nБез telegram вообще ({len(no_telegram)}) — онбординг через бота "
          f"им пока недоступен:")
    for name in no_telegram:
        print(f"  — {name}")

print(f"\nИтого: {len(onboarded)} из {len(onboarded) + len(not_onboarded)} "
      f"компаний с telegram-каналом уже онбордились.")
