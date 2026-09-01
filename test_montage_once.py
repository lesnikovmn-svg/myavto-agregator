"""T-111 (01.09.2026, запрошено пользователем — "давай на видео из групп
возьмем для теста, перезапустим разово парсинг видео"): одноразовый ручной
тест auto_montage.build_short() на РЕАЛЬНОМ видео из artalexgroup/
bezpokrasa/winner_auto_club — без ожидания медленного бэкфилла/live-потока
(который на момент этой задачи спотыкался о сетевые таймауты, см. TASKS.md
T-109/T-108).

Что делает: берёт последнее сообщение с видео у каждого запрошенного
источника напрямую через iter_messages(), гоняет его через
auto_montage.build_short() (с тем же source-гейтингом OCR-детекта бейджа,
что и в проде — T-110: OCR только для winner_auto_club) и шлёт готовый
ролик прямо в тестовую группу (TEST_GROUP_INVITE из userbot_config.env).

НЕ трогает state/дедуп основного сервиса (userbot_state.json,
pending_queue) — это отдельный путь, не handle_group(), поэтому можно
гонять сколько угодно раз без риска для боевого потока. Использует
ОТДЕЛЬНЫЙ Telethon session-файл (копию основного) — можно запускать даже
пока systemd-сервис myavto-userbot работает, конфликта по файлу не будет
(Telegram поддерживает несколько параллельных сессий на один аккаунт).

Использование (на VPS, из /var/www/myavto-agregator):
    python3 test_montage_once.py                                    # все 3 источника
    python3 test_montage_once.py winner_auto_club                   # только один
    python3 test_montage_once.py artalexgroup bezpokrasa            # несколько

Первый запуск может попросить код подтверждения — это НЕ ожидается (сессия
копируется уже авторизованной), если это всё же произошло — сессия не
скопировалась, проверить, что рядом лежит myavto_userbot.session.
"""
import asyncio
import os
import shutil
import sys
import tempfile

from telethon import TelegramClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from userbot_parser import load_env, build_proxy, SOURCE_PARSERS, SOURCE_TG_HANDLE, ensure_test_group  # noqa: E402
import auto_montage  # noqa: E402

DEFAULT_SOURCES = ["artalexgroup", "bezpokrasa", "winner_auto_club"]
MAIN_SESSION = "myavto_userbot"
TEST_SESSION = "myavto_userbot_test111"


async def main():
    sources = [s.strip().lower() for s in sys.argv[1:]] or DEFAULT_SOURCES

    env = load_env()
    api_id = env.get("API_ID")
    api_hash = env.get("API_HASH")
    proxy = build_proxy(env.get("PROXY_URL"))
    test_group_invite = env.get("TEST_GROUP_INVITE", "").strip()
    if not test_group_invite:
        print("TEST_GROUP_INVITE не задан в userbot_config.env — некуда слать результат, стоп")
        return

    if not os.path.exists(f"{MAIN_SESSION}.session"):
        print(f"{MAIN_SESSION}.session не найден рядом со скриптом — запускать из /var/www/myavto-agregator")
        return
    if not os.path.exists(f"{TEST_SESSION}.session"):
        shutil.copy(f"{MAIN_SESSION}.session", f"{TEST_SESSION}.session")
        print(f"скопировал {MAIN_SESSION}.session -> {TEST_SESSION}.session (отдельная сессия для теста)")

    client = TelegramClient(TEST_SESSION, int(api_id), api_hash, proxy=proxy)
    await client.start()
    print("подключились к Telegram (тестовая сессия)")

    test_group = await ensure_test_group(client, test_group_invite)
    if not test_group:
        print("не удалось получить тестовую группу — стоп")
        await client.disconnect()
        return

    for source in sources:
        tg_handle = SOURCE_TG_HANDLE.get(source, source)
        print(f"\n[{source}] ищу последнее видео через @{tg_handle} (смотрю последние 50 сообщений)...")
        found = None
        try:
            async for m in client.iter_messages(tg_handle, limit=50):
                if m.video:
                    found = m
                    break
        except Exception as e:
            print(f"[{source}] не удалось получить историю: {e!r}")
            continue

        if not found:
            print(f"[{source}] видео не найдено в последних 50 сообщениях — пропускаю")
            continue

        print(f"[{source}] взял сообщение #{found.id}, скачиваю видео...")
        parser = SOURCE_PARSERS.get(source)
        parsed = None
        if parser and found.raw_text:
            try:
                parsed = parser(found.raw_text)
            except Exception:
                parsed = None
        title = (parsed or {}).get("title") or ""
        mileage = (parsed or {}).get("mileage") or ""

        with tempfile.TemporaryDirectory() as tmpdir:
            in_path = os.path.join(tmpdir, f"{source}_{found.id}_in.mp4")
            out_path = os.path.join(tmpdir, f"{source}_{found.id}_short.mp4")
            try:
                await client.download_media(found, file=in_path)
            except Exception as e:
                print(f"[{source}] не удалось скачать видео: {e!r}")
                continue

            try:
                auto_montage.build_short(
                    in_path, {"title": title, "mileage": mileage}, out_path,
                    log=print, source=source,
                )
            except Exception as e:
                print(f"[{source}] auto_montage упал: {e!r} — пропускаю (в проде это тоже fallback на оригинал, здесь просто пропуск)")
                continue

            caption = f"ТЕСТ T-111 ({source} #{found.id})\n{title}" + (f"\nПробег: {mileage}" if mileage else "")
            try:
                await client.send_message(test_group, caption, file=out_path)
                print(f"[{source}] отправлено в тестовую группу")
            except Exception as e:
                print(f"[{source}] не удалось отправить в тестовую группу: {e!r}")

    await client.disconnect()
    print("\nготово")


if __name__ == "__main__":
    asyncio.run(main())
