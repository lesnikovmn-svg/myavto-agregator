"""T-174bis (17.09.2026, запрошено пользователем — сигнальное сообщение в
группу предпостинга, если карточки «Предложение дня» нет, хотя бот явно
не упал/не завис вотчдогом): отдельный скрипт, запускается РАЗ В СУТКИ
через systemd timer (check-daily-status-card.timer), спустя несколько
часов после STATUS_CARD_DAILY_HOUR (по умолчанию 20:00 МСК) — достаточно
времени, чтобы основной сервис успел отработать суточный подбор.

Проверяет journalctl самого myavto-userbot.service за последние
CHECK_WINDOW_HOURS часов: для каждого целевого канала (MY_Avto5,
My_Avto_Optimal) ищет строку "[status_card][<канал>]" — неважно, успех
("выбран лучший...") или честный, ожидаемый пропуск ("не нашлось поста,
подходящего для карточки"). Если НИ ОДНОЙ такой строки для канала нет —
суточная задача (_daily_status_card_task/_post_daily_best в
userbot_parser.py) для него вообще не добежала до выполнения — тот же
класс проблемы, что и T-174 (зависание на cross-DC media, которое чинит
и общий вотчдог myavto-userbot-watchdog), либо что-то ещё пока не
известное. Шлём предупреждение в группу предпостинга.

Намеренно НЕ делает отдельный запрос к Telegram "было ли реально
содержимое в канале за сутки" — избыточно: если задача реально
запустилась, она САМА логирует либо успех, либо честный пропуск с
причиной (см. _post_daily_best). "Контент был, а карточки нет" и "задача
вообще не запустилась" снаружи неразличимы иначе как по отсутствию этой
самой строки в логе — что этот скрипт и проверяет. Легитимный пропуск (в
канале правда не было подходящего поста) НЕ считается поводом для
алерта — он и так уже залогирован самим ботом с понятной причиной.

Отправка использует ТОТ ЖЕ Telegram-сеанс (myavto_userbot.session), что
и основной бот — только чтобы отправить одно сообщение в уже известную
группу предпостинга, куда сеанс и так уже вступил (PREPOSTING_GROUP_INVITE).
Кратковременный конфликт блокировки SQLite с основным процессом
маловероятен (запуск раз в сутки, однократное короткое подключение) — на
всякий случай сделано 3 попытки с паузой."""

import asyncio
import subprocess
import sys

from telethon import TelegramClient

from userbot_parser import build_proxy, ensure_test_group, load_env

SERVICE = "myavto-userbot"
CHECK_WINDOW_HOURS = 26
CHANNEL_LABELS = ["MY_Avto5", "My_Avto_Optimal"]


def _had_status_card_activity(label: str) -> bool:
    """True, если за последние CHECK_WINDOW_HOURS в логе сервиса встретилась
    хотя бы одна строка [status_card][<label>] (успех или честный
    пропуск — неважно, важно что задача реально выполнилась)."""
    result = subprocess.run(
        ["journalctl", "-u", SERVICE, "--since", f"-{CHECK_WINDOW_HOURS}h", "--no-pager", "-o", "cat"],
        capture_output=True, text=True, check=False,
    )
    marker = f"[status_card][{label}]"
    return marker in result.stdout


async def _send_alert(missing_labels):
    env = load_env()
    api_id = env.get("API_ID")
    api_hash = env.get("API_HASH")
    proxy = build_proxy(env.get("PROXY_URL"))
    preposting_group_invite = env.get("PREPOSTING_GROUP_INVITE", "").strip()
    if not preposting_group_invite:
        print("PREPOSTING_GROUP_INVITE не задан в userbot_config.env — некуда слать предупреждение", file=sys.stderr)
        return

    text = (
        "⚠️ Карточка «Предложение дня» не появилась за последние "
        f"{CHECK_WINDOW_HOURS}ч для: {', '.join(missing_labels)}.\n"
        "В логе нет ни строки об успехе, ни строки о честном пропуске "
        "(«не нашлось поста») — похоже, суточная задача вообще не "
        "отработала (юзербот завис или не дошёл до неё по другой причине). "
        "Проверь: sudo systemctl status myavto-userbot"
    )

    last_error = None
    for attempt in range(1, 4):
        client = TelegramClient("myavto_userbot", int(api_id), api_hash, proxy=proxy)
        try:
            await client.connect()
            group = await ensure_test_group(client, preposting_group_invite)
            await client.send_message(group, text)
            print("Предупреждение отправлено в группу предпостинга")
            return
        except Exception as e:
            last_error = e
            print(f"[попытка {attempt}/3] не удалось отправить предупреждение: {e}", file=sys.stderr)
            await asyncio.sleep(10)
        finally:
            await client.disconnect()
    print(f"Не удалось отправить предупреждение после 3 попыток: {last_error}", file=sys.stderr)


def main():
    missing = [label for label in CHANNEL_LABELS if not _had_status_card_activity(label)]
    if missing:
        asyncio.run(_send_alert(missing))
    else:
        print(f"ok — по обоим каналам была активность [status_card] за последние {CHECK_WINDOW_HOURS}ч")


if __name__ == "__main__":
    main()
