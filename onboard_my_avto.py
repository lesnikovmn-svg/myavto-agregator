"""
Ручной онбординг MY Avto (id:1, собственная компания пользователя) в
Telegram-боте — 14.08.2026, по вопросу "как май авто заонбордиться?".

Обычный механизм (см. telegram_bot_service.py, handle_start()): компания
онбордится, когда КТО-ТО со своим личным Telegram-username, совпадающим
с полем telegram компании в таблице (без @, без учёта регистра), пишет
боту /start. У MY Avto там "MY_Avto5" — отдельный бизнес-аккаунт/канал,
а не повседневный личный @LesnikovM пользователя, которым уже настроены
уведомления (ADMIN_CHAT_ID) — через обычный /start пришлось бы временно
менять личный юзернейм в Telegram, неудобно.

Личный chat_id пользователя уже известен (435849652, тот же, что
ADMIN_CHAT_ID, см. раздел про настройку уведомлений в PROJECT_STATE.md)
— проще прописать онбординг напрямую в bot_state.json, не дожидаясь
/start с нужного конкретного аккаунта.

ВАЖНО: после этого в тот же личный чат (куда уже приходят 🔔-уведомления)
начнут приходить ещё и пересланные заявки клиентов по направлениям
MY Avto — это ожидаемо, MY Avto участвует в рассылке наравне с
остальными компаниями каталога (не привилегия, а обычный эффект
онбординга).

Запускать НА VPS (там лежит bot_state.json):
  cd /var/www/myavto-agregator
  python3 onboard_my_avto.py

Перезапускать бота после этого не нужно — bot_state.json читается заново
на каждой итерации поллинга, эффект сразу.
"""

import json
import os

STATE_FILE = "bot_state.json"
MY_AVTO_TELEGRAM_HANDLE = "my_avto5"  # из таблицы, колонка J ("MY_Avto5"), без @, в нижнем регистре
MY_AVTO_CHAT_ID = 435849652  # личный chat_id владельца (тот же, что ADMIN_CHAT_ID)

if not os.path.exists(STATE_FILE):
    print(
        f"Не нашёл {STATE_FILE} в текущей папке — запусти скрипт прямо на VPS, "
        f"в /var/www/myavto-agregator."
    )
    raise SystemExit(1)

with open(STATE_FILE, encoding="utf-8") as f:
    state = json.load(f)

state.setdefault("companies", {})

if state["companies"].get(MY_AVTO_TELEGRAM_HANDLE) == MY_AVTO_CHAT_ID:
    print(f"MY Avto уже онбордилась (chat_id={MY_AVTO_CHAT_ID}) — ничего не делаю.")
else:
    state["companies"][MY_AVTO_TELEGRAM_HANDLE] = MY_AVTO_CHAT_ID
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    print(
        f"Готово: MY Avto онбордилась (telegram='{MY_AVTO_TELEGRAM_HANDLE}' -> chat_id={MY_AVTO_CHAT_ID})."
    )
    print(
        "Заявки по направлениям MY Avto теперь будут приходить тебе в личку вместе с 🔔-уведомлениями."
    )
