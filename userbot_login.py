"""
Одноразовый скрипт логина юзербота для парсинга ТГ-каналов (T-77).
Запускать вручную один раз (на VPS, там же где будет жить постоянный
парсер) — Telethon сам спросит код из Telegram/смс прямо в терминале при
первом запуске. Дальше сессия сохраняется в myavto_userbot.session и
переиспользуется без повторного логина.

Установка зависимости: pip install -r requirements.txt (добавлен telethon)
Перед запуском: userbot_config.env должен лежать в этой же папке, с
заполненными PHONE / API_ID / API_HASH (см. userbot_config.env.example).
НЕ коммитить userbot_config.env и *.session — оба в .gitignore.
"""
import asyncio
from pathlib import Path

from telethon import TelegramClient


def load_env(path="userbot_config.env"):
    env = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


async def main():
    env = load_env()
    phone = env.get("PHONE")
    api_id = env.get("API_ID")
    api_hash = env.get("API_HASH")
    if not (phone and api_id and api_hash):
        raise SystemExit(
            "userbot_config.env: заполните PHONE, API_ID, API_HASH перед запуском."
        )

    client = TelegramClient("myavto_userbot", int(api_id), api_hash)
    await client.start(phone=phone)
    me = await client.get_me()
    print(f"Успешный логин: {me.first_name} (@{me.username}), id={me.id}")
    print("Сессия сохранена в myavto_userbot.session — дальше логин не потребуется.")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
