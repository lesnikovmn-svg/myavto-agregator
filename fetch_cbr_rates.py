"""
Курсы валют ЦБ РФ для калькулятора растаможки (index.html #calc).

Зачем: калькулятор (T-116) считает пошлину в EUR, а стоимость авто
пользователь может вводить в $, ¥ (юань) или ₩ (вона) — тем валютах, в
которых реально указана цена на Encar/китайских площадках/американских
аукционах. Раньше курс EUR был захардкожен в app.js вручную и не
обновлялся ("обновлять вручную", см. T-116) — это разовое решение не
масштабируется на 4 валюты сразу и будет тухнуть молча. Этот скрипт
берёт курсы из официального ежедневного XML ЦБ РФ (бесплатно, без ключа,
официальный источник, не сторонний реселлер) и update_site.py вшивает
результат в app.js при каждом обычном прогоне — то есть курс будет
свежим настолько, насколько часто вообще запускается update_site.py
(сейчас — daily_update.sh по крону), без отдельного расписания под это.

Источник: https://www.cbr.ru/scripts/XML_daily.asp — официальный XML
с ежедневными курсами ЦБ РФ, ID валют (R01235=USD, R01239=EUR,
R01375=CNY, R01815=KRW) стабильны и не меняются годами.

Если сеть недоступна или ЦБ отдал что-то не то — функция бросает
исключение, а НЕ возвращает выдуманные/нулевые курсы. Вызывающий код
(update_site.py) обязан поймать её и оставить в app.js предыдущие
известные курсы, а не затирать их нулями или ломать весь прогон
из-за этой не самой критичной части сайта.
"""

import re
import urllib.request
import xml.etree.ElementTree as ET

CBR_URL = "https://www.cbr.ru/scripts/XML_daily.asp"

# CharCode -> человекочитаемое имя, только для логов
WANTED = {"USD": "доллар", "EUR": "евро", "CNY": "юань", "KRW": "вона"}


def fetch_cbr_rates(timeout=15):
    """Возвращает {"USD": 86.38, "EUR": 100.57, "CNY": 12.90, "KRW": 0.0595,
    "_date": "02.09.2026"} — курс рубля за 1 единицу валюты (для KRW ЦБ
    публикует за 1000 — здесь уже поделено на номинал, дальше по коду
    везде "курс за 1 единицу").
    Бросает исключение при любой сетевой/парсинг-ошибке — намеренно,
    см. docstring файла."""
    req = urllib.request.Request(CBR_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    # ЦБ отдаёт windows-1251, не utf-8 — если раскодировать неправильно,
    # рубли в названиях валют превратятся в моджибейк, но сами числа
    # (Value/Nominal) от этого не портятся, декодируем по-честному всё равно.
    text = raw.decode("windows-1251")
    root = ET.fromstring(text)

    date = root.attrib.get("Date", "")
    rates = {"_date": date}
    for valute in root.findall("Valute"):
        code = valute.findtext("CharCode")
        if code not in WANTED:
            continue
        nominal = float(valute.findtext("Nominal").replace(",", "."))
        value = float(valute.findtext("Value").replace(",", "."))
        rates[code] = round(value / nominal, 6)

    missing = set(WANTED) - set(rates) - {"_date"}
    if missing:
        raise ValueError(f"ЦБ РФ не вернул курс для: {missing} (сайт мог изменить формат)")
    return rates


if __name__ == "__main__":
    # Разовый ручной прогон для проверки, что источник жив и парсится
    # правильно — как просил пользователь: "цены курс с цб сайта бери".
    rates = fetch_cbr_rates()
    print(f"Курсы ЦБ РФ на {rates['_date']}:")
    for code, name in WANTED.items():
        print(f"  {code} ({name}): {rates[code]} ₽")
