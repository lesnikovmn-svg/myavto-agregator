"""T-165quater (12.09.2026): одноразовая ИНТЕРАКТИВНАЯ авторизация
отдельного Telegram-сеанса под личным аккаунтом @LesnikovM — специально
для публикации сторис (см. PERSONAL_STORY_SESSION в userbot_parser.py).

Почему это вообще понадобилось: основной юзербот-сеанс (myavto_userbot,
ведёт весь парсинг/постинг) авторизован под ТЕХНИЧЕСКИМ номером
(@les_nik_m), на котором нет Telegram Premium. Первая же ручная проверка
через test_send_story_once.py на реальном Telegram API показала
PremiumAccountRequiredError не только для peer="me", но и для
peer=@MY_Avto5/@My_Avto_Optimal — то есть Telegram требует Premium у
аккаунта, которым ВЫПОЛНЯЕТСЯ stories.sendStory, независимо от того, чья
это сторис. У @LesnikovM Premium есть (подтверждено пользователем) —
значит, ВСЕ сторис (и личная, и от каналов) должны публиковаться именно
этим сеансом, а не основным юзерботом.

Запускать РОВНО ОДИН РАЗ, вручную, в интерактивном терминале (не через
systemd/cron — здесь нужен реальный ввод кода подтверждения, который
придёт в Telegram на другое устройство или по SMS):

    python3 setup_personal_story_session.py

Спросит:
  1. Номер телефона @LesnikovM (международный формат, например +7...).
  2. Код подтверждения из Telegram.
  3. Облачный пароль (2FA) — только если он включён на аккаунте.

После успешного входа создаст файл myavto_story_personal.session рядом
со скриптом — дальше его сам подхватит основной сервис (userbot_parser.py,
функция _get_personal_story_client) и test_send_story_once.py.

Использует те же API_ID/API_HASH из userbot_config.env, что и основной
юзербот — это ключи ПРИЛОЖЕНИЯ (не привязаны к конкретному номеру),
под ними можно авторизовать любой аккаунт, включая другой номер.
"""
import asyncio
import os
import sys

from telethon import TelegramClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from userbot_parser import load_env, build_proxy, PERSONAL_STORY_SESSION  # noqa: E402


async def main():
    env = load_env()
    api_id = env.get("API_ID")
    api_hash = env.get("API_HASH")
    if not (api_id and api_hash):
        print("userbot_config.env: нужны API_ID/API_HASH — как и для основного юзербота")
        return
    proxy = build_proxy(env.get("PROXY_URL"))

    session_file = f"{PERSONAL_STORY_SESSION}.session"
    if os.path.exists(session_file):
        print(f"{session_file} уже существует.")
        answer = input("Пересоздать сеанс заново (например, если раньше залогинили не тот номер)? (да/нет): ").strip().lower()
        if answer not in ("да", "yes", "y", "д"):
            print("Отмена — существующий сеанс не тронут.")
            return

    client = TelegramClient(PERSONAL_STORY_SESSION, int(api_id), api_hash, proxy=proxy)
    print("Сейчас Telethon спросит номер телефона (в международном формате, например +7...),")
    print("затем код подтверждения из Telegram, и, если включена 2FA, облачный пароль.")
    print("Вводи номер именно @LesnikovM — не технический номер юзербота.\n")
    await client.start()

    me = await client.get_me()
    premium = getattr(me, "premium", None)
    print(f"\nГотово: авторизовались как {me.first_name} (@{me.username}), premium={premium}")

    if me.username and me.username.lower() != "lesnikovm":
        print(f"ВНИМАНИЕ: username @{me.username} не похож на @LesnikovM — проверь, тот ли номер ввёл.")
    if not premium:
        print("ВНИМАНИЕ: premium=False на этом аккаунте — сторис публиковаться НЕ будут (Telegram требует Premium), пока Premium не появится именно здесь.")
    else:
        print("Premium есть — можно запускать test_send_story_once.py для проверки самой публикации сторис.")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
