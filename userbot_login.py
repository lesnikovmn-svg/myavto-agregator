"""
Одноразовый скрипт логина юзербота для парсинга ТГ-каналов (T-77).
Запускать вручную один раз (на VPS, там же где будет жить постоянный
парсер) — Telethon сам спросит код из Telegram/смс прямо в терминале при
первом запуске. Дальше сессия сохраняется в myavto_userbot.session и
переиспользуется без повторного логина.

Прямой доступ с этого VPS к серверам Telegram (149.154.x.x) заблокирован
хостером (см. T-77 в TASKS.md) — используем тот же HTTP-прокси, что уже
работает для telegram_bot_service.py (PROXY_URL в конфиге).

Установка зависимостей: pip install -r requirements.txt (telethon +
python-socks — нужен именно python-socks, не PySocks, для HTTP-прокси
через asyncio в новых версиях Telethon).
Перед запуском: userbot_config.env должен лежать в этой же папке, с
заполненными PHONE / API_ID / API_HASH / (опционально) PROXY_URL —
см. userbot_config.env.example. НЕ коммитить userbot_config.env и
*.session — оба в .gitignore.
"""
import asyncio
from pathlib import Path
from urllib.parse import urlparse

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


def build_proxy(proxy_url):
    """PROXY_URL=http://user:pass@host:port -> кортеж для Telethon (python-socks)."""
    if not proxy_url:
        return None
    import python_socks

    parsed = urlparse(proxy_url)
    return (
        python_socks.ProxyType.HTTP,
        parsed.hostname,
        parsed.port,
        True,  # rdns
        parsed.username,
        parsed.password,
    )


async def main():
    env = load_env()
    phone = env.get("PHONE")
    api_id = env.get("API_ID")
    api_hash = env.get("API_HASH")
    proxy_url = env.get("PROXY_URL")
    if not (phone and api_id and api_hash):
        raise SystemExit(
            "userbot_config.env: заполните PHONE, API_ID, API_HASH перед запуском."
        )

    proxy = build_proxy(proxy_url)
    if proxy:
        print(f"Подключаюсь через прокси {proxy[1]}:{proxy[2]}...")
    else:
        print("PROXY_URL не задан — пробую подключиться напрямую (скорее всего не сработает с этого VPS).")

    client = TelegramClient("myavto_userbot", int(api_id), api_hash, proxy=proxy)
    await client.start(phone=phone)
    me = await client.get_me()
    print(f"Успешный логин: {me.first_name} (@{me.username}), id={me.id}")
    print("Сессия сохранена в myavto_userbot.session — дальше логин не потребуется.")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
