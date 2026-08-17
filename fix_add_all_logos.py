"""
НАПОМИНАНИЕ (конвенция проекта): перед запуском поставь именованную версию
в Google Таблице — Файл → История версий → Назвать текущую версию →
"до fix_add_all_logos" → Сохранить.

Массовое проставление РЕАЛЬНЫХ логотипов во все карточки каталога —
17.08.2026, по запросу пользователя ("для всех компаний сделай логотип
в карточку по этому же принципу", продолжение работы с Автозаказ.ру).
index.html (renderCompanies(), см. avatarHtml) уже умеет отличать
avatar-URL от avatar-инициалов и рисует настоящую картинку.

ВАЖНО про метод сбора — честно про ограничение: постраничный fetch КАЖДОГО
из ~90 сайтов компаний оказался непрактично дорогим (один только
worldcar.ru — это десятки тысяч слов каталога легковых, не считово по
токенам на разбор всех сайтов). Поэтому три разных источника логотипа,
по убыванию качества:

1. KNOWN_GOOD_LOGOS — для этих компаний я живым fetch'ом реального сайта
   нашёл настоящий логотип (обычно msapplication-TileImage — уже готовый
   квадратный кроп — либо явный <img class=logo> в шапке сайта). Это
   лучший вариант, тот же принцип, что и для Автозаказ.ру.
2. TELEGRAM_LOGOS — для компаний БЕЗ собственного сайта (только
   Telegram-канал) взял og:image превью-страницы t.me/<handle> — это
   ровно аватарка канала, тоже настоящая, не выдумана.
3. Всё остальное (компании с сайтом, которые НЕ проверял руками вживую)
   — используется публичный сервис фавиконок Google
   (google.com/s2/favicons?domain=...&sz=128) БЕЗ похода на сам сайт.
   Это компромисс: сама иконка настоящая (её реально отдаёт домен
   компании), но по качеству это фавикон (маленькая иконка вкладки
   браузера), а не полноценный логотип — где-то это будет смотреться
   скромно. Если для конкретной компании захочешь логотип получше —
   скажи, вручную зайду на сайт и найду.

Компании БЕЗ сайта И БЕЗ telegram (например AUTOCOM) — логотип взять
неоткуда, остаются как есть (цветные инициалы).
АВТОЗАКАЗ.РУ / Авто Заказ — уже обработаны отдельным скриптом
(fix_dedupe_and_enrich_autozakaz.py), пропускаем здесь, чтобы не
перезаписать.

Пишет ТОЛЬКО если текущий avatar ещё не URL (safe гонять повторно).

Запуск: python3 fix_add_all_logos.py
После — python3 update_site.py.
"""
import time
from urllib.parse import urlparse

from company_agent import connect_sheets


def safe_update_cell(ws, row, col, value, retries=5):
    """
    Найдено 17.08.2026 на реальном прогоне: ~90 update_cell подряд без пауз
    упираются в лимит Google Sheets API 'Write requests per minute per
    user' (429), скрипт падал необработанным исключением на середине
    таблицы. Пауза 1.2с между записями (безопасно держит нас под ~50
    запросов/мин) + ретрай с более долгой паузой конкретно на 429, если
    квота всё же исчерпалась (например, из-за других скриптов, работающих
    параллельно с той же таблицей).
    """
    for attempt in range(retries):
        try:
            ws.update_cell(row, col, value)
            return
        except Exception as e:
            if "429" in str(e) and attempt < retries - 1:
                wait = 15 * (attempt + 1)
                print(f"    (лимit Google Sheets API, жду {wait}с и пробую снова...)")
                time.sleep(wait)
            else:
                raise

NAME_COL = 2
TELEGRAM_COL = 10
SITE_COL = 12
AVATAR_COL = 16

SKIP_NAMES = {"АВТОЗАКАЗ.РУ", "Авто Заказ"}

# 1. Логотипы, найденные вживую на реальном сайте компании.
KNOWN_GOOD_LOGOS = {
    "MY Avto": "https://myavto-agregator.ru/logo.jpg",
    "ElectroCar": "https://electro-car.by/wp-content/uploads/2024/10/fav.png",
    "ТамСямAUTO": "https://tamsyamauto.ru/assets/logo-CJuDQE1X.png",
    "Artalex Group": "https://artalexgroup.com/images/Logo.png",
    "DSS Group": "https://dss-g.com/wp-content/uploads/2024/11/cropped-favicon-270x270.png",
    "LikeAvto": "https://static.tildacdn.com/tild3036-6332-4461-b065-656266313966/android-chrome-512x5.png",
    "RUS AUTO IMPORT": "https://rus-auto-import.ru/images/site/premium-auto-logotype.png",
    "E.N.CARS": "https://e-n-cars.ru/ui/img/logo.svg",
}

# 2. Аватарки Telegram-каналов (og:image с t.me/<handle>) — для компаний
# без собственного сайта.
TELEGRAM_LOGOS = {
    "Primorye China Export": "https://cdn4.telesco.pe/file/SwYRbGyP0wkgq4K7s8j__4QbM9HKSL5obC5mRDzwx_ww3PLLIdmBYiQSkaezGdwb-32wXqyR1V-02mWYMrcybnAR6hM5u9SNAl991KyEKBkihxapZhbFhP-fK837If0bxXxRGq-hi6KJBWQ3GnEmhecpz9wiWawUGLcuvag9VDvFQsqfWr9jjku51Z9KrMUleB_ZgeGiHgGz5bawogqqxMCrJVVbh26D80NeQ7Hd7kxFCSHHQ4ZEG5SloFC-bXrnuoVwdFKAv1nU8V-uE7vcdMZL164ZCA8hRN0hWSVziOvSHXu1JnQF9TRMfQmB1pPcxEckzn9nNJ2hQGthGThkvg.jpg",
    "Winner Auto Club": "https://cdn4.telesco.pe/file/SjV99vUCxhaTynOVrasI6khWvUes36Kn9hbJ7fsU0tBheYbtQzbUN3LGx9fsbcrEBeukLQL_0AVc8EK78h8sJxb7hVU-cHI8tNF2d4n9aH3d2ot7lxccninwVhWHO7g2wcoP3WhSXGlJ0VXz4IWJ2rfyMQOPvxwxlJO_IFxiYRoRAwengthykYdnfMm-LpWxhKhkSygx4OgmI4_Ayw1dAcgQ-7aADKPBC8a4mmjq13tCKTdYuekIewt5p6iav1_JDOz-_sa7nxAWGnkUlhT4Tpt9U1tUAPpq7iSZLePFXKgZTkUsQ0EO-x7ejcZVpB166YTeLypUFZpxUA4X0sOYhQ.jpg",
    "Asia Express Auto": "https://cdn4.telesco.pe/file/S1T4sSYqpGF2Po0uLeO3T0qj3nzfOBHf3jYuPsrki8RzHyz85yi8poZ6bh-qGYVid573o6tnS4nnFB7nxya3L4bTAfSq-h4bdvUsH0c3KfZ8mRA7SGAvnah9jgiUYVDYYqqURL73HB41ByVPAdcW88nJMN81QasTKOuwiYgVzOZd4e6udYkZRYSn3h4UbojCR_HqMq0xJq6zSGRomTsG5fUaS8C50PCHLDwwfCiJACBVQ1oTBnfN5LP3KUNs1GNdCSac9q888jttik10Qjh9b7nwTYs4op6UbmU7ifwOcyzGDHvClx49NQ7YwDt8LrF45vJm06W_S2Xbsjl8FLoOGA.jpg",
    "AviAuto": "https://cdn4.telesco.pe/file/SyqgROLDYnj9TMxUN_YiMsf2TBwnWv5FWaxieRCh88o7oU3gkClXFUa3wmoDlkGd-mMZjx-SMJZUkdbImwgZeDS-ybA1Qdx2v6BDNXt4AJcsP5RjFH2UPCHM4yM9RwsPdl79r1xQhKiXLaspc3sWyHYg1s3LjzK7ssMKGraK7CLGrXVJL5D6axjrGQ-m74Iw3hNU1SM1RcTjckOS4g88wj_rm2l27E8sNzLZV1Ybsy34KGz2eR70UJtZ4uGVaGwNalddtEcDDV8lnUQcQTFcpZkVCv3q245dvxgXlxTa4hVh-_mCjdJ_icJJ5AHMT9K2AREtcjEwjX-hZGe1seQqEw.jpg",
    "AutoEuropeTOP": "https://cdn4.telesco.pe/file/eEy3BzAu33E-Ob2mMuH1uiX5trMESMS63INp4dZJAmBsKVkppH2B9GXUgKWKHpX1vTXRXmOA1rTBBuLpwhE1gk5tiAD78CEyzeodieD5HQ0_FkaTpR_m0nNBAfJc9k08pZ4O08bOyc1zhcJSzOEVX0XnfZcawFEYJVsLee4SONhL4mPfc0lAe7mxXLJNO5Mj7Ell60kR2u4s4RxGV6fFs5G2qFPfuWnrmrzIvbCBS3AR-53cWDSOF0LfjgxBF97FZTZtNm-b6hQPzZpjbicazQbLNi5Q_K4pM8fNAkMMh3gJaAy2EVFO-TujChTnyPtzIBEeB0qYyn2kAyqYBowqTQ.jpg",
    "AUTOCARLINE": "https://cdn4.telesco.pe/file/smFDYjnU_NSBsXoyfKjSi3E1bgFZBr3bHcLja1uKvbcbu-MgYKHhQ8hZlL8JG7NvCG4_G1qdc7p_r-i6yyJ8tKVFbn-qyBvIKSqbPl_ZHinl9zT7s1wDRfbjjxXhkxTFLxgjentYFxVztq7EHbOf6ooLyz5tXNFuShez2Tb15Rq0o2n8BeDzRqtoGblMUDYA0ONtYXOs8NsS8-txhcqnWbf44Z6Ri_Qyk5yme41bqGruSBWE9A934EfR7zXyydcWvwcyQ5wHcHzABh_HSbix4w6XkwS0lRc3liSdRrjQoWEpUBK063gmkeJnc8Jpx0Dsxx_A6tphcqPURIItCDzDWQ.jpg",
    "KorRusMotors": "https://cdn4.telesco.pe/file/XMb40sHx3IfUk4DwxrDGIXe71ZC5EAREbxO-6Chsjuz1Ta8A3NULC0pEbeJwh7YYYA1VaK0qg6GLscdQxKXcUU2EdQKvlB5bz8r1KHftu2PMlLEEx6SPmX6wpZ9vxn-8QFbZR_J4VZ2PFXht0yF7yzCNUy_r-stqQ9c3dDYyT4jPBQJVk7WrwHEK5gFE7JSE-nR74ZYRAP_8aChEKtYUrFHQEbkLADj5BMSNp6P2tisNdr5Z3acD0u5TykSHUyDM9591_36EwD-62xPverraidkV0wiGQ5KSTsl0XO2lxb9XPQXo7l_WRU29xbSYPmngbNONZqp4heHwh3H8QRILDA.jpg",
    "Antonbuyauto": "https://cdn4.telesco.pe/file/q2jW7tmoSpKIz1ijBSYi-OJWIyKpjkFP1QE7mQJ3gS0XNkah1RZGqFQGMP6PM0o3NeopLcfeVlxYvDo9zuaqfBJpZeS9TxJBF_1CDsEm_PMGSugkj1MQ-lFnQ7rRvIOKLNwFjclCoJoY484GjPKdcpv8_-W0vnc-dHjKvNy5ZhroGG1DCZkCAqaIVsMEInI5iBOo_xEIXSaPZx1MlQ9U3x6Cg6RnVwXcw0UzkqCKAkWn2Z9JdRz8L-n8H3UVJbEEqazFAMTaqfYHK22RjfB15HJWg6rR5rqjKJ88b-mM4PLQ_fqsMSl-kZZJc1qoVbjdjn1frlxACf8lvw3EHvS37w.jpg",
    "Авто из Европы / Авто Импорт": "https://cdn4.telesco.pe/file/oC0qGpWbTEfostt8bP0XYHHbnEdjcRTqYcF0guVSZc0yJygrGgKRpNkbiYAXXcQOrHax-GKgTFk9X3YH3ilrCCNmCSB63YDg_4KsRjPUOhyKdr3hCMFvqDXLGKtOUQVFjJAsTLmJf3GW6HsdvhkrM8wQhOu8eOUlF0qtuv24c57Mcks7rc5RrhYfHoVS5G6GGiw8X0M1LqQMcijTbknUt1i3H0PH_qVKEzRg5HjWWSXiOMHNGjLBQHOrGnnj6jkbn5MwU2RTle5IiD_psnlmHeBah0AkVOnz5btT36LfHpLeMetHB_BX82LYTPiTPHu9Ex1uJz0F0KvcJ7PqgjQUZw.jpg",
    "Авто из Европы / Авто Импорт ПРО": "https://cdn4.telesco.pe/file/Kds5xRD9qxZjvRmUP1najPiisalPuhhxNUbDAo5FsLP1MkjTHbwnh0R8qehG77X1ykybnFWPwCdWFKkpjwFRXEwRVB4MGWvql0oM3bIkQ-Rkdcp5--nbqWkwWgG5T9MMEl4puCqoMqt1RUWdL8FVDVfefL019JCl54BcTfDqa-CiQ-1czIUwx9fuq5949K52LzBvSmlSQDU_HLtgVB2jOmXzA-1ObufrtBNzsyBIVdbkyL_s0Vhvehvel8oaR7TAfRnvzkhlIGhVhmhzRof8dUzuaSCJAkY38f7YgAQet3hWl3WnwpLBLHxHmicoHPVjmbwZJOAeOd7PlhxOuGOCwQ.jpg",
    "AutoImport Russia": "https://cdn4.telesco.pe/file/aSNDtJSxjucrSkZblMg_xURlZXgl2mAxKd3orPYdcw0SG0Uuac1ZiSmGQlVGvSytgngtvHMXE_b4s2n0QI5UA8RhddEXNKQczJkCPOOu5oOM9PNPWt8uGXKYbvomsmnWmMzggGDb6j5nig4CMGeg2C10IVVPehj_B6P2cKwhYeLW5j63B5k8VDnfdU4Deh3mc75091OmzLHlMQgrsHREm4pFT0WCmVD1HqUKE62sIPVvkoKHvc_qqWlMqaS45gv9OCBnDcwCM3OIEg-ukIEnOp1c5AJ2zMTLqhtSctFSnTUXPv0s5fww3A9zpwEu-qDc1_XpanFNdNn4ikSTVcTL4Q.jpg",
    "Прим Автодилер": "https://cdn4.telesco.pe/file/ItDsXDyTw07dGEekg34AhXU_WjXwdWgfVZO38HLIVL9_9QxKkQoYZdnGf4lsse_ZrMtHO0O1RFOhauXIzd4h7VYTmjK5YXqwrLr4ej-F3vtXH-SQiRyafWIVHclW2NfWIKNJRrq8j5kQ_QB9mnfASPWik9c55O90oBCr0Ha-9jzOXdUYg8jh9rB1_BcpliGZonJXE26wyHafVgIOsUJReSGS9Vlvvcw6xJXEokJ9EAB-ARpNKvvxcHx2JqNeXhmExPqE8yOtC_GXugkipVmL8KI9KTX9DNV0Eu427vJxAQ9-KBb4YlVEoE4ZO8UTCKeEOd3Z0fXFya28b6vZfs9VEQ.jpg",
    "MAJORKA IMPORT": "https://cdn4.telesco.pe/file/Zo9VRKEnIRl9JSwTTSNOlmEq_1VKEk2abPuXukRyBKpkfE_nYqykQfm2F4wcvWBpmvISvKSk5N5h1mil2C2i5xU89TeyjKlMA6b3VO7GgNvgRZOFhKbBfRj0PLdqh_oS8jCIx7OhYQr7VVETFzFDFVnKaEyjDKrTuWEUvqfJtoDPqsXKr1-1ow9ygOSSdM9NkFo6keJGO55MFNrp2VR2bHlOHkqDaUGw9ApMnDW_i2fkZAG48Qx9uNJq5rpW0Zc5MwuHhfZq-VdoGvSDIR9PQjNtK8Ak9Mh3bMOGUhETjuyKnM--WpASLSRZ2QokpOGZcvfDm3D0UYb-kqafSOSoFA.jpg",
    "TAT IMPORT AVTO": "https://cdn4.telesco.pe/file/TTOOiCMnGGMfWkL6Gfp6wjiaZR15Bj-olU-jSmsJ149jP8sgcgSnDjxbU-46GAqa6PVcL-qu8ensQl0iHSOzGyQqRtjrvH_tdHRVZAZHNioRiGhr3RhMf7V1oXqbNN4fPKNs2ESGeVA7D90p44ZXv_C1pOLAHvARuj_6FOlffSckbcsMWXWTeUJe9JBRYrCZlMoJEzQ0aMi-zmpOKdsTIGjV9hNGjRZAUsexvIYyqYUZEsNDipn2Hwg16beEeZR6Bw2JrpAOrS18KUO6RdPqEQmMq-WRD1Sr3Iacxem9q3QyhULtEjedEx-jeI0hpgR5Tsal78Y_bE50XLonnWNCKg.jpg",
    "Tiger Cars": "https://cdn4.telesco.pe/file/mLOKNwRwNRmpepxHnnvimP9TPvvnteR-OjbBPGHHzgEY3EqoP5tOTzMb1yCMuvgL4y5NjhUbmcqA4qxGEwmgvtd8PPjEQou7_D1yxgsWE9pQGLqeEJuAXzKVA-ZtwryiJLz0RphDhduAILO6ia4fVZ2XpEaMceES0M_l5wVFJvF57yt8ZP0Q5asNELWMRRkPV3hjYRMp-sjv6_3kuhFG5h32KWrLs0MCHmwNKta7kPXesbeEhOdMzI1W0IE85uj4McsAcCs5u9r6e8yLYGVwekkp84-Yqff4tFNmPW_W4FNJMEuFYMIpvs5_OTH_LnqhWf5oriT90INV-J6D7U1tYQ.jpg",
}

ws = connect_sheets()
all_values = ws.get_all_values()
rows = all_values[1:]

updated_known, updated_tg, updated_favicon = 0, 0, 0
skipped_has_logo, skipped_no_source = 0, 0

for i, row in enumerate(rows, start=2):
    def val(col):
        return row[col - 1].strip() if len(row) >= col else ""

    name = val(NAME_COL)
    if not name or name in SKIP_NAMES:
        continue

    current_avatar = val(AVATAR_COL)
    if current_avatar.lower().startswith("http"):
        skipped_has_logo += 1
        continue

    if name in KNOWN_GOOD_LOGOS:
        safe_update_cell(ws, i, AVATAR_COL, KNOWN_GOOD_LOGOS[name])
        print(f"[{i}] {name}: логотип с сайта (проверено вживую) -> {KNOWN_GOOD_LOGOS[name][:70]}...")
        updated_known += 1
        time.sleep(1.2)
        continue

    if name in TELEGRAM_LOGOS:
        safe_update_cell(ws, i, AVATAR_COL, TELEGRAM_LOGOS[name])
        print(f"[{i}] {name}: аватар Telegram-канала -> {TELEGRAM_LOGOS[name][:70]}...")
        updated_tg += 1
        time.sleep(1.2)
        continue

    site = val(SITE_COL)
    if not site:
        skipped_no_source += 1
        continue

    domain = urlparse(site if "://" in site else "http://" + site).netloc
    domain = domain.replace("www.", "")
    if not domain or "vk.ru" in domain or "vk.com" in domain:
        skipped_no_source += 1
        continue

    favicon_url = f"https://www.google.com/s2/favicons?domain={domain}&sz=128"
    safe_update_cell(ws, i, AVATAR_COL, favicon_url)
    print(f"[{i}] {name}: favicon ({domain}) -> {favicon_url}")
    updated_favicon += 1
    time.sleep(1.2)

print(f"\nИтого: логотипы с сайта — {updated_known}, аватарки TG-каналов — {updated_tg}, "
      f"favicon — {updated_favicon}, уже был логотип — {skipped_has_logo}, "
      f"нет ни сайта ни telegram (пропущено) — {skipped_no_source}.")
print("\nТеперь прогони python3 update_site.py.")
