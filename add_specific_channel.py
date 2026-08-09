"""
Разовый скрипт: добавляет в каталог конкретный Telegram-канал по юзернейму,
минуя обычный поиск агента (полезно, когда канал не попал в стандартные
5 поисковых запросов company_agent.py, но пользователь точно знает, что он
существует и подходит).

Как и обычный агент — публикует даже при подтверждении из одного источника
(сам канал), порога по подписчикам нет. Если tgstat.ru не знает канал
(частый случай для небольших каналов), пробует получить название/описание
напрямую с t.me.

Запуск: python3 add_specific_channel.py <username>
Пример: python3 add_specific_channel.py japanautozakaz
После — python3 update_site.py, чтобы пересобрать сайт.
"""
import sys
from company_agent import (
    connect_sheets, get_existing, parse_tgstat_channel, fetch_telegram_preview,
    extract_phone, get_directions, get_tags, mentions_ukraine, extract_years_experience,
    find_map_links, find_social_links, find_marketplace_links, add_company,
)


def run(username):
    username = username.lstrip("@")
    print(f"Добавляю канал @{username}...")
    ws = connect_sheets()
    existing = get_existing(ws)
    if username.lower() in existing:
        print("Уже есть в каталоге — ничего не делаю.")
        return

    info = parse_tgstat_channel(username)
    if not info:
        print("tgstat.ru не знает такой канал (обычно — маленькие каналы, мало подписчиков).")
        print("Пробую напрямую через t.me...")
        info = fetch_telegram_preview(username)
    if not info:
        print("Не удалось получить данные канала ни с tgstat.ru, ни напрямую с t.me.")
        print("Либо канал закрытый/приватный, либо username введён неверно.")
        return

    text = info["description"] or ""
    has_auto = any(w in text.lower() for w in ["авто", "машин", "импорт", "корея", "китай", "япония", "пригон"])
    if not has_auto:
        print("В описании канала нет ничего про авто/импорт — похоже, не тот профиль. Не добавляю.")
        return
    if mentions_ukraine(text):
        print("В описании упоминается Украина — не подходит для этого каталога. Не добавляю.")
        return

    name = info.get("title") or username.replace("_", " ").title()
    if name.lower() in existing:
        print("Уже есть в каталоге под этим названием — ничего не делаю.")
        return

    phone = extract_phone(text)
    years = extract_years_experience(text)

    print("Ищу подтверждение на картах...")
    yandex, google, gis2, maps_verified = find_map_links(name, phone)
    print("Ищу подтверждение в соцсетях...")
    insta, vk, social_verified = find_social_links(name, text, phone)
    print("Ищу подтверждение на маркетплейсах...")
    avito, drom, autoru, market_verified = find_marketplace_links(name, phone)

    if not (maps_verified or social_verified or market_verified):
        print(f"  ⚠️ {name}: подтвердилось только в Telegram, добавляю как есть")

    row_num = len(ws.get_all_values()) + 1
    add_company(ws, {
        "name": name,
        "description": text or f"Telegram канал @{username}",
        "directions": get_directions(text),
        "tags": get_tags(text),
        "telegram": username,
        "phone": phone,
        "subscribers": info["subscribers"],
        "years": str(years) if years else "1",
        "yandex": yandex, "google": google, "gis2": gis2,
        "instagram": insta, "vk": vk,
        "avito": avito, "drom": drom, "autoru": autoru,
    }, row_num)
    print("\nДобавлено! Теперь прогони python3 update_site.py, чтобы обновить сайт.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python3 add_specific_channel.py <username>")
    else:
        run(sys.argv[1])
