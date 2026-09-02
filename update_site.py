import json, re, subprocess

import datetime
import os
import sheets_client
import verify_egrul
from company_agent import connect_reviews_sheet, REVIEWS_HEADER
from fetch_cbr_rates import fetch_cbr_rates

# Раньше данные читались через публичный gviz/tq JSON-эндпоинт Google
# Sheets. У него есть собственный серверный кэш (не наш HTTP-кэш, повлиять
# на него заголовками Cache-Control нельзя) — 09.08.2026 это аукнулось:
# company_agent.py дописал 14 новых компаний через gspread, а update_site.py,
# запущенный сразу следом, всё равно увидел старые 52 — свежие строки в
# таблице реально были, просто gviz ещё не обновил кэш. Раз в даже обычном
# ручном прогоне это создаёт риск "потерять" сегодняшние добавления до
# следующего раза — а в daily_update.sh (cron) company_agent.py и
# update_site.py как раз запускаются один за другим без паузы, так что бага
# бы повторялся каждый день. Переключились на тот же способ чтения, что уже
# использует company_agent.py — авторизованный gspread без кэширующего слоя.
#
# T-72 (21.08.2026): сама авторизация (Credentials + gspread.authorize)
# теперь берётся из sheets_client.get_client() — тот же клиент, что
# использует company_agent.py. SHEET_ID здесь остаётся СВОЙ, с historic
# жёстко зашитым фолбэком (не sheets_client.SHEET_ID) — этот скрипт
# специально работает и без agent_config.env под рукой, дублировать
# фолбэк в sheets_client.py не стали, он специфичен именно для update_site.py.
config = sheets_client.load_env("agent_config.env")
SHEET_ID = os.environ.get("SHEET_ID") or config.get(
    "SHEET_ID", "1u3WuYo6Iyb4RJMQVbanx4YGm29B2V-DQMuKzVrtdcLY"
)

print("Загружаю данные из Google Sheets...")
ws = sheets_client.get_client().open_by_key(SHEET_ID).sheet1
all_rows = ws.get_all_values()[1:]  # без строки заголовков


# 18.08.2026 (T-01). Значения из таблицы попадают в index.html как есть, и
# 14.08.2026 это уже дало сбой: у компании "АИ Авто" в колонке avatar лежал
# моджибейк (кириллица "АИ", записанная как latin-1), внутри которого сидел
# управляющий символ U+0090. Он уезжал прямо в HTML и был единственной
# ошибкой парсинга во всём файле.
#
# Симптом ушёл сам, когда схема аватарок сменилась на URL логотипов, но
# причина осталась: агент тянет тексты с чужих сайтов и из Telegram, где
# встречается и битая кодировка, и невидимые символы (zero-width, BOM) —
# последние особенно неприятны, потому что ломают вёрстку молча, глазами
# их в таблице не видно.
#
# Чистим на входе, а не на выходе: один раз при чтении строки, чтобы дальше
# по коду везде были уже нормальные значения.
_CTRL = dict.fromkeys(
    # C0 (кроме таба) + DEL + C1 — непечатаемые, в тексте компании им не место
    [c for c in range(0x00, 0x20) if c != 0x09]
    + [0x7F]
    + list(range(0x80, 0xA0))
    # пробелы нулевой ширины и BOM — парсер не ломают, но рвут вёрстку
    + [0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF]
)


def clean_cell(text):
    """Убирает непечатаемые и невидимые символы из значения ячейки."""
    return text.translate(_CTRL).strip()


companies = []
for row in all_rows:

    def val(i):
        return clean_cell(row[i]) if i < len(row) and row[i] else ""

    # gspread отдаёт значения уже как обычные строки (в отличие от gviz,
    # который превращал длинные числа вроде ИНН во float "...​.0") — отдельная
    # чистка ИНН больше не нужна.
    company = dict(
        id=val(0),
        name=val(1),
        rating=val(2),
        reviews=val(3),
        years=val(4),
        delivered=val(5),
        description=val(6),
        directions=val(7),
        tags=val(8),
        telegram=val(9),
        phone=val(10),
        site=val(11),
        manager=val(12),
        region=val(13),
        featured=val(14),
        avatar=val(15),
        color=val(16),
        yandex=val(17),
        inn=val(18),
        google=val(19),
        gis2=val(20),
        instagram=val(21),
        vk=val(22),
        avito=val(23),
        drom=val(24),
        autoru=val(25),
        # Добавлено 09.08.2026 для правила приоритета клика по карточке
        # (см. clink ниже): мессенджер MAX, YouTube, RuTube, WhatsApp.
        max=val(26),
        youtube=val(27),
        rutube=val(28),
        whatsapp=val(29),
        # Добавлено 14.08.2026: telegram (val(9)) — это канал/группа
        # компании, tgcontact (val(30), колонка AE) — личный аккаунт/бот
        # для переписки, если найден (см. fix_telegram_contact_check.py).
        # Кнопка "Написать в TG" на сайте использует именно tgcontact, а не
        # telegram — у канала нет чата, писать в него нельзя.
        tgcontact=val(30),
        # Добавлено 14.08.2026 для ранжирования компаний на сайте (см.
        # PROJECT_STATE.md, "Ранжирование компаний"): онбордилась ли
        # компания в Telegram-боте (нажала /start). Само значение
        # приходит не отсюда, а из bot_state.json на VPS — колонка 33
        # (AG) синхронизируется отдельным sync_onboarded_to_sheet.py,
        # update_site.py её только читает.
        onboarded=val(32),
    )
    if company["name"]:
        companies.append(company)

print(f"Найдено компаний: {len(companies)}")

# Проверка по ЕГРЮЛ для компаний, у которых есть ИНН.
# Если ИНН нет или проверить не удалось — компания остаётся без бейджа
# "подтверждено по ЕГРЮЛ", это не блокирует синхронизацию сайта.
verified_count = 0
for c in companies:
    c["egrul_year"] = ""
    if c["inn"]:
        info = verify_egrul.lookup_inn(c["inn"])
        # Бейдж показываем только для действующих юрлиц/ИП. Если юрлицо
        # найдено, но деятельность прекращена — не показываем бейдж, чтобы
        # не вводить пользователя в заблуждение о текущем статусе компании.
        if info and info.get("registered_year") and info.get("active"):
            c["egrul_year"] = str(info["registered_year"])
            verified_count += 1
            print(f'  ЕГРЮЛ подтверждён (действующее): {c["name"]} — с {c["egrul_year"]} года')
        elif info and info.get("registered_year") and not info.get("active"):
            print(
                f'  ЕГРЮЛ: {c["name"]} — юрлицо найдено, но деятельность прекращена, бейдж не ставим'
            )

# 17.08.2026: нативные отзывы на сайте — подтягиваем в карточки только
# отзывы со статусом "approved" из вкладки "Отзывы" (модерация — через
# moderate_reviews.py, см. company_agent.py/connect_reviews_sheet).
# Матчим по НАЗВАНИЮ компании (не по id — в основной таблице встречаются
# дублирующиеся id, см. PROJECT_STATE.md), поэтому регистронезависимое
# совпадение по имени. Сбой чтения вкладки не должен ронять всю
# синхронизацию сайта — просто отзывы в этот раз не подтянутся.
reviews_by_company = {}
approved_total = 0
try:
    rws = connect_reviews_sheet()
    review_rows = rws.get_all_values()[1:]
    idx = {name: i for i, name in enumerate(REVIEWS_HEADER)}
    for r in review_rows:

        def rv(col):
            i = idx[col]
            return r[i].strip() if i < len(r) and r[i] else ""

        if rv("status").lower() != "approved":
            continue
        cname = rv("company_name")
        if not cname:
            continue
        reviews_by_company.setdefault(cname.lower(), []).append(
            {
                "author": rv("author_name"),
                "rating": rv("rating"),
                "text": rv("text"),
                "date": rv("created_at"),
            }
        )
    approved_total = sum(len(v) for v in reviews_by_company.values())
    print(f"Одобренных отзывов на сайте: {approved_total}")
except Exception as e:
    print(f"  Не удалось загрузить отзывы (пропущено): {e}")

print(f"Подтверждено по ЕГРЮЛ: {verified_count} из {len(companies)}")


def _to_float(s, default=0.0):
    try:
        return float(s)
    except (TypeError, ValueError):
        return default


# T-64 (21.08.2026, по запросу пользователя, "сначала собрать города, потом
# фильтр"): извлекаем город офиса из уже собранных текстовых полей —
# `region`/`description` — без нового похода в интернет и без новой
# колонки в таблице (полностью производное поле, пересчитывается каждый
# прогон). Проверил реальные данные на 21.08.2026: у 79 из 109 компаний
# (72%) `region` — просто "Россия"/"Вся Россия" без города вообще, у
# оставшихся город назван вперемешку с другим текстом ("Владивосток, вся
# Россия", "Берлин, Германия (офис)"). Это первый, самый дешёвый проход —
# сверяем текст со списком известных крупных городов СНГ/зарубежья.
# Не идеально (полагается на то, что город вообще упомянут текстом где-то
# в этих двух полях), но работает уже сейчас, не блокирует фильтр
# ожиданием отдельного сбора данных агентом. Список отсортирован длинными
# составными названиями вперёд ("Санкт-Петербург" раньше "Петербург" и
# т.п.), чтобы более специфичное совпадение не подрезалось общим.
KNOWN_CITIES = [
    "Санкт-Петербург",
    "Нижний Новгород",
    "Ростов-на-Дону",
    "Набережные Челны",
    "Йошкар-Ола",
    "Улан-Удэ",
    "Петропавловск-Камчатский",
    "Москва",
    "Владивосток",
    "Хабаровск",
    "Новосибирск",
    "Екатеринбург",
    "Казань",
    "Краснодар",
    "Челябинск",
    "Уфа",
    "Красноярск",
    "Пермь",
    "Волгоград",
    "Воронеж",
    "Саратов",
    "Тюмень",
    "Иркутск",
    "Барнаул",
    "Ульяновск",
    "Ижевск",
    "Ярославль",
    "Владимир",
    "Севастополь",
    "Чита",
    "Чебоксары",
    "Калининград",
    "Томск",
    "Кемерово",
    "Рязань",
    "Тольятти",
    "Астрахань",
    "Пенза",
    "Липецк",
    "Киров",
    "Махачкала",
    "Оренбург",
    "Симферополь",
    "Сочи",
    "Якутск",
    "Магадан",
    "Мурманск",
    "Архангельск",
    "Петрозаводск",
    "Курск",
    "Тула",
    "Смоленск",
    "Тверь",
    "Иваново",
    "Брянск",
    "Белгород",
    "Вологда",
    "Новороссийск",
    "Минск",
    "Алматы",
    "Астана",
    "Ташкент",
    "Бишкек",
    "Ереван",
    "Тбилиси",
    "Баку",
    "Кишинёв",
    "Берлин",
]


def extract_city(region, description):
    text = f"{region or ''} {description or ''}"
    for city in KNOWN_CITIES:
        if city in text:
            return city
    return None


# T-07 (18.08.2026, аудит TASKS.md — самая опасная находка): раньше этот
# блок собирал JS-литерал f-строками, экранируя ТОЛЬКО одну кавычку и
# ТОЛЬКО в поле description — любое другое поле (name, manager, region,
# ссылки) с кавычкой или обратным слэшем ломало парсер (белый экран
# каталога), а специально составленное значение вида
# `X",x:alert(1)//` давало исполнение произвольного JS. Данные приходят
# автопарсингом чужих сайтов и Telegram-каналов — доверять им нельзя.
# Теперь весь массив собирается как обычные Python-словари и уходит через
# json.dumps() ОДНИМ вызовом — экранирование гарантированно правильное
# для всех полей сразу, забыть про новое поле в будущем невозможно.
companies_out = []
total_reviews = 0
for c in companies:
    dirs = [d.strip() for d in c["directions"].split(",") if d.strip()]
    tags = [t.strip() for t in c["tags"].split(",") if t.strip()]
    featured = c["featured"].upper() == "TRUE"
    cid = int(float(c["id"])) if c["id"] else 0
    crev = int(float(c["reviews"])) if c["reviews"] else 0
    # "Лет на рынке" (years) и год из ЕГРЮЛ — разные вещи (см. кейс
    # Altais-Cars: сайт заявляет "с 1998", а юрлицо перерегистрировано в
    # 2025), но если years так и остался неопределённым дефолтом "1"
    # (extract_years_experience в company_agent.py ничего не нашла в
    # тексте), а ЕГРЮЛ при этом подтверждён — честнее показать возраст
    # юрлица, чем откровенно заниженную "1 год" (баг замечен 09.08.2026 на
    # China Trade: years=1, хотя ЕГРЮЛ — с 2024 года).
    raw_years = c["years"]
    if (not raw_years or raw_years == "1") and c["egrul_year"]:
        try:
            cyrs = max(1, datetime.date.today().year - int(c["egrul_year"]))
        except ValueError:
            cyrs = int(float(raw_years)) if raw_years else 1
    else:
        cyrs = int(float(raw_years)) if raw_years else 1
    total_reviews += crev
    # Приоритет клика по всей карточке (не по конкретной иконке-кнопке) —
    # правило от 09.08.2026: сайт > telegram > instagram > vk > MAX >
    # YouTube > RuTube > WhatsApp-группа > ничего (раньше был только
    # site -> telegram -> '#', теперь полная цепочка по просьбе
    # пользователя, который нашёл несколько компаний без сайта, но с
    # соцсетями через карточку 2ГИС).
    # T-91 (27.08.2026, баг найден пользователем на Winner Auto Club): было
    # наоборот — tgcontact (личный менеджер) в приоритете над telegram
    # (канал) для клика по ВСЕЙ карточке. Из-за этого у компаний без сайта
    # клик по карточке уводил в личку незнакомому менеджеру вместо канала
    # компании — неожиданно и потенциально небезопасно для пользователя
    # (не то же самое, что нажать "Написать", это осознанное действие).
    # Клик по карточке — это "посмотреть компанию", а не "написать
    # человеку", поэтому канал компании логичнее личного контакта. Кнопка
    # "Написать в TG" (см. ниже, contact/c.tgcontact) не трогается — там
    # tgcontact по-прежнему в приоритете, это разные сценарии.
    tg_for_link = c["telegram"] or c["tgcontact"]
    clink = (
        c["site"]
        or (("https://t.me/" + tg_for_link) if tg_for_link else "")
        or c["instagram"]
        or c["vk"]
        or c["max"]
        or c["youtube"]
        or c["rutube"]
        or c["whatsapp"]
        or "#"
    )
    egrul_verified = bool(c["egrul_year"])
    onboarded = c["onboarded"].upper() == "TRUE"
    c_reviews = reviews_by_company.get(c["name"].strip().lower(), [])

    # 24.08.2026 (по запросу пользователя: людям, у которых был негативный
    # опыт с недобросовестными импортёрами, важно видеть, что компания
    # реально проверена отзывами, а не просто заявляет о себе). Тег
    # честный и производный — НЕ ставится вручную и не хранится в таблице
    # отдельной колонкой, а считается каждый раз заново по реальным
    # approved-отзывам компании (см. c_reviews выше): есть хотя бы один
    # отзыв, и ни один не негативный (рейтинг 1-2 из 5). Осознанно НЕ
    # делаем противоположный тег для компаний с плохими отзывами —
    # публично клеймить конкретные компании через тег репутационно и
    # юридически рискованно, задача агрегатора вознаграждать честных
    # игроков, а не устраивать чёрный список.
    company_tags = list(tags)
    if c_reviews:
        try:
            has_negative = any(float(r.get("rating") or 0) <= 2 for r in c_reviews)
        except (TypeError, ValueError):
            has_negative = False
        if not has_negative:
            # На карточке (renderPage() в app.js) показываются только
            # ПЕРВЫЕ 2 тега (c.tags.slice(0,2)) — ставим этот тег в начало
            # списка, а не в конец, иначе у компаний с уже заполненными
            # ручными тегами он рискует не влезть и никогда не показаться.
            company_tags.insert(0, "Без негативных отзывов")

    companies_out.append(
        {
            "id": cid,
            "name": c["name"],
            "rating": _to_float(c["rating"], 4.5),
            "reviews": crev,
            "years": cyrs,
            "delivered": c["delivered"],
            "description": c["description"],
            "directions": dirs,
            "tags": company_tags,
            "telegram": c["telegram"],
            "phone": c["phone"],
            "site": c["site"],
            "manager": c["manager"],
            "region": c["region"],
            "featured": featured,
            "avatar": c["avatar"],
            "color": c["color"],
            "yandex": c["yandex"],
            "google": c["google"],
            "gis2": c["gis2"],
            "instagram": c["instagram"],
            "vk": c["vk"],
            "avito": c["avito"],
            "drom": c["drom"],
            "autoru": c["autoru"],
            "max": c["max"],
            "youtube": c["youtube"],
            "rutube": c["rutube"],
            "whatsapp": c["whatsapp"],
            "tgcontact": c["tgcontact"],
            "onboarded": onboarded,
            "link": clink,
            "egrulVerified": egrul_verified,
            "egrulYear": c["egrul_year"],
            "reviewsList": c_reviews,
            "city": extract_city(c["region"], c["description"]),
        }
    )

js = "const COMPANIES = " + json.dumps(companies_out, ensure_ascii=False) + ";"

# T-74 (24.08.2026): массив COMPANIES раньше лежал прямо внутри index.html
# (искали 'const COMPANIES = [' по тексту всего файла). После выноса JS в
# отдельный app.js (см. T-74 в TASKS.md) массив переехал туда же — здесь
# просто меняем файл, который патчим, сама логика поиска/замены та же.
app_js = open("app.js").read()
s = app_js.find("const COMPANIES = [")
e = app_js.find("];", s) + 2
app_js = app_js[:s] + js + app_js[e:]

# T-117 (01.09.2026): курсы валют ЦБ РФ для калькулятора (#calc) — тот же
# принцип, что и COMPANIES: вшиваем актуальные данные в app.js при каждом
# обычном прогоне update_site.py, не отдельным расписанием. Если ЦБ недоступен
# или отдал неожиданный формат — НЕ падаем и НЕ затираем старые курсы нулями,
# просто оставляем то, что уже было в app.js, и громко печатаем предупреждение
# в лог, чтобы это было видно в выводе daily_update.sh.
try:
    rates = fetch_cbr_rates()
    print(f"Курсы ЦБ РФ на {rates['_date']}: USD={rates['USD']} EUR={rates['EUR']} CNY={rates['CNY']} KRW={rates['KRW']}")
    cbr_js = "const CBR_RATES = " + json.dumps(rates, ensure_ascii=False) + ";"
    cs = app_js.find("const CBR_RATES = {")
    if cs == -1:
        raise ValueError("в app.js не найден маркер 'const CBR_RATES = {' — структура файла изменилась")
    ce = app_js.find("};", cs) + 2
    app_js = app_js[:cs] + cbr_js + app_js[ce:]
except Exception as e:
    print(f"[ВНИМАНИЕ] не удалось обновить курсы ЦБ РФ ({e}) — в app.js остались прежние курсы, калькулятор растаможки может показывать устаревшую валюту.")

open("app.js", "w").write(app_js)

html = open("index.html").read()

count = len(companies)

# T-26 (18.08.2026, по решению пользователя): плашка "Отзывов в каталоге"
# показывала сумму старой колонки reviews (29 110) — сид-данные по ~32
# компаниям, которые никто не проверял. С появлением нативных отзывов
# (17.08.2026) это стало видимым противоречием: сверху "29 110 отзывов",
# на каждой карточке при этом кнопка "Оставить отзыв", потому что реальных
# модерированных отзывов — 0. Решение: показывать только approved_total
# (честное число), а пока оно 0 — не показывать плашку вообще, а не врать
# нулём. Весь блок .stats-bar перестраивается с нуля при каждом прогоне
# (а не точечным regex по старому значению), чтобы плашка сама появлялась,
# как только approved_total станет > 0, без ручных правок HTML.
stats_rows = [(str(count), "Компаний в каталоге")]
if approved_total > 0:
    stats_rows.append((f"{approved_total:,}".replace(",", " "), "Отзывов в каталоге"))
stats_rows += [("8", "Направлений импорта"), ("9 стран", "Покрытие СНГ")]
# T-60 (18.08.2026, по запросу пользователя): счётчик посетителей.
# Реальное число не из Google Sheets — оно живёт в visits.json на VPS
# (см. /api/visit в telegram_bot_service.py), сюда просто кладём
# плейсхолдер-span с известным id, JS на странице (fetch при загрузке)
# сам подставит актуальное число при каждом открытии сайта.
stats_rows.append(('<span id="visitCount">…</span>', "Посещений сайта"))
stats_inner = "\n".join(
    f'  <div class="stat"><div class="stat-n">{n}</div><div class="stat-l">{l}</div></div>'
    for n, l in stats_rows
)
new_stats_block = '<div class="stats-bar">\n' + stats_inner + "\n</div>\n"
html = re.sub(
    r'<div class="stats-bar">\n.*?\n</div>\n',
    lambda _m: new_stats_block,
    html,
    count=1,
    flags=re.DOTALL,
)

open("index.html", "w").write(html)
# 18.08.2026: раньше здесь печаталось total_reviews (сумма старой колонки
# reviews, 29110) — сбивало с толку рядом с approved_total=0 в логе чуть
# выше. Теперь в итоговой строке тоже approved_total, они не расходятся.
print(
    f"Сайт обновлён! {count} компаний, {approved_total} реальных отзывов, {verified_count} подтверждены по ЕГРЮЛ."
)


# T-70 (21.08.2026): раньше был `git add .` (подхватывал вообще всё в
# рабочей директории на VPS, не только index.html — если рядом лежал
# незакоммиченный черновик другого файла, он улетал в git под чужим
# сообщением коммита) и коды возврата subprocess.run() не проверялись
# (тихий провал git push из-за разошедшейся истории выглядел как успех).
# Это была прямая причина git-конфликтов и lock-файлов, с которыми
# разбирались весь день 21.08.2026 при параллельных ручных пушах с Мака.
# Теперь: 1) коммитим только файлы, которые этот скрипт реально пишет
# (index.html + app.js — см. T-74, массив COMPANIES переехал в app.js);
# 2) ничего не коммитим, если реальных изменений нет (пустые коммиты с
# одинаковым сообщением засоряли историю при каждом прогоне cron, даже
# когда в таблице ничего не менялось); 3) перед push делаем pull
# --no-rebase, чтобы забрать чужие изменения (например, ручной пуш с
# Мака) и смёрджиться автоматически, а не молча разойтись; 4) при ЛЮБОЙ
# ошибке печатаем её явно вместо тихого продолжения.
def run_git(args):
    r = subprocess.run(["git"] + args, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"[git] ОШИБКА: git {' '.join(args)}\n{r.stderr.strip()}")
    return r


TRACKED_FILES = ["index.html", "app.js"]
diff_check = subprocess.run(["git", "diff", "--quiet"] + TRACKED_FILES)
if diff_check.returncode == 0:
    print("[git] index.html/app.js не изменились — коммит не нужен.")
else:
    run_git(["add"] + TRACKED_FILES)
    commit_r = run_git(
        [
            "commit",
            "-m",
            f"update: sync {count} companies from Google Sheets ({verified_count} ЕГРЮЛ-verified)",
        ]
    )
    if commit_r.returncode == 0:
        pull_r = run_git(["pull", "--no-rebase"])
        if pull_r.returncode == 0:
            push_r = run_git(["push", "origin", "main"])
            if push_r.returncode == 0:
                print("[git] index.html/app.js закоммичены и запушены.")
        else:
            print(
                "[git] pull перед push не удался — push пропущен, разберитесь вручную (git status)."
            )
