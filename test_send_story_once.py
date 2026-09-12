"""T-165 (12.09.2026): ручная диагностика публикации НОВОЙ сторис в Telegram
(stories.sendStory через Telethon) — НЕ трогает боевой пайплайн/state
основного сервиса, только шлёт одну тестовую сторис на явно указанный peer.

Нужен, потому что stories.sendStory ни разу не проверялся на реальном
аккаунте — сама песочница, где писался код (см. car_specs_lookup.py про ту
же проблему с ultimatespecs.com), не может залогиниться в Telegram и
отправить настоящую сторис. Первая реальная проверка возможна только
отсюда, с VPS (или с любой машины, где лежит авторизованная сессия).

Использование (на VPS, из /var/www/myavto-agregator):
    python3 test_send_story_once.py me
    python3 test_send_story_once.py @MY_Avto5
    python3 test_send_story_once.py @My_Avto_Optimal
    python3 test_send_story_once.py me /path/to/своя_картинка.png

Без пути к картинке скрипт сам рисует маленькую тестовую PNG (просто
цветной прямоугольник с текстом "TEST STORY" + текущее время) — этого
достаточно, чтобы проверить сам факт публикации, не дожидаясь реального
"предложения дня".

Использует ОТДЕЛЬНЫЙ Telethon session-файл (копию основного, как и
test_montage_once.py/T-111) — можно запускать даже пока systemd-сервис
myavto-userbot работает, конфликта не будет.

Ожидаемые исходы (все варианты — НОРМАЛЬНЫЙ результат диагностики, не баг):
  - Успех -> сторис реально ушла на аккаунт/канал, id опубликованной сторис
    напечатан. Дальше её должен подхватить omni-poster/stories-sync
    (отдельный, уже работающий проект — см. TASKS.md T-165) и в течение
    ~5 минут перезалить в Instagram Stories.
  - PREMIUM_ACCOUNT_REQUIRED (для "me") -> на аккаунте почему-то не
    определяется Premium, хотя пользователь подтвердил, что он есть —
    возможно, другой аккаунт, чем ожидалось (сессия — не тот номер).
  - BOOSTS_REQUIRED (для канала) -> у канала не хватает буст-очков.
  - CHAT_ADMIN_REQUIRED (для канала) -> у аккаунта нет права "публиковать
    сторис" именно в этом канале (нужно выдать явно в правах администратора
    канала).
  - Любая другая ошибка -> текст выводится как есть, без интерпретации —
    разбираемся по факту, не гадаем заранее.
"""
import asyncio
import io
import os
import shutil
import sys
from datetime import datetime

from telethon import TelegramClient

try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from userbot_parser import load_env, build_proxy, _post_png_as_story  # noqa: E402

MAIN_SESSION = "myavto_userbot"
TEST_SESSION = "myavto_userbot_test165"


def _make_placeholder_png() -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (1080, 1920), color=(20, 24, 32))
    draw = ImageDraw.Draw(img)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    draw.rectangle([60, 800, 1020, 1120], outline=(255, 255, 255), width=6)
    draw.text((110, 880), "TEST STORY", fill=(255, 255, 255))
    draw.text((110, 960), f"T-165 diagnostic\n{now}", fill=(200, 200, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def main():
    if len(sys.argv) < 2:
        print("Использование: python3 test_send_story_once.py <peer: me | @channel> [путь_к_картинке.png]")
        return

    peer_arg = sys.argv[1].strip()
    peer = "me" if peer_arg.lower() == "me" else peer_arg
    image_path = sys.argv[2] if len(sys.argv) > 2 else None

    if image_path:
        if not os.path.exists(image_path):
            print(f"Файл не найден: {image_path}")
            return
        with open(image_path, "rb") as f:
            png_bytes = f.read()
        print(f"Использую переданную картинку: {image_path} ({len(png_bytes)} байт)")
    else:
        png_bytes = _make_placeholder_png()
        print(f"Картинка не передана — сгенерировал тестовую заглушку ({len(png_bytes)} байт)")

    env = load_env()
    api_id = env.get("API_ID")
    api_hash = env.get("API_HASH")
    proxy = build_proxy(env.get("PROXY_URL"))

    if not os.path.exists(f"{MAIN_SESSION}.session"):
        print(f"{MAIN_SESSION}.session не найден рядом со скриптом — запускать из /var/www/myavto-agregator")
        return
    if not os.path.exists(f"{TEST_SESSION}.session"):
        shutil.copy(f"{MAIN_SESSION}.session", f"{TEST_SESSION}.session")
        print(f"скопировал {MAIN_SESSION}.session -> {TEST_SESSION}.session (отдельная сессия для теста)")

    client = TelegramClient(TEST_SESSION, int(api_id), api_hash, proxy=proxy)
    await client.start()
    print("подключились к Telegram (тестовая сессия)")

    me = await client.get_me()
    print(f"аккаунт: {me.first_name} (@{me.username}), premium={getattr(me, 'premium', None)}")

    print(f"\nПубликую тестовую сторис -> peer={peer!r} ...")
    try:
        await _post_png_as_story(client, peer, png_bytes, caption="T-165 diagnostic")
        print(f"УСПЕХ: сторис опубликована на {peer!r}. Проверьте вручную в Telegram, что она реально появилась.")
    except Exception as e:
        print(f"ПРОВАЛ: {e!r}")
        print("Это ожидаемый (не аварийный) исход диагностики — см. докстринг файла про")
        print("PREMIUM_ACCOUNT_REQUIRED / BOOSTS_REQUIRED / CHAT_ADMIN_REQUIRED и что каждая значит.")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
