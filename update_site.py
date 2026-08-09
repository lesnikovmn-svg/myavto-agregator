import json, re, subprocess

import datetime
import os
import gspread
from google.oauth2.service_account import Credentials
import verify_egrul

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
config = {}
if os.path.exists('agent_config.env'):
    with open('agent_config.env') as f:
        for line in f:
            if '=' in line:
                k, v = line.strip().split('=', 1)
                config[k] = v
SHEET_ID = os.environ.get('SHEET_ID') or config.get('SHEET_ID', '1u3WuYo6Iyb4RJMQVbanx4YGm29B2V-DQMuKzVrtdcLY')

print('Загружаю данные из Google Sheets...')
scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_file('credentials.json', scopes=scopes)
client = gspread.authorize(creds)
ws = client.open_by_key(SHEET_ID).sheet1
all_rows = ws.get_all_values()[1:]  # без строки заголовков

companies = []
for row in all_rows:
    def val(i):
        return row[i].strip() if i < len(row) and row[i] else ''
    # gspread отдаёт значения уже как обычные строки (в отличие от gviz,
    # который превращал длинные числа вроде ИНН во float "...​.0") — отдельная
    # чистка ИНН больше не нужна.
    company = dict(id=val(0),name=val(1),rating=val(2),reviews=val(3),years=val(4),
        delivered=val(5),description=val(6),directions=val(7),tags=val(8),
        telegram=val(9),phone=val(10),site=val(11),manager=val(12),
        region=val(13),featured=val(14),avatar=val(15),color=val(16),yandex=val(17),
        inn=val(18),google=val(19),gis2=val(20),instagram=val(21),vk=val(22),
        avito=val(23),drom=val(24),autoru=val(25))
    if company['name']:
        companies.append(company)

print(f'Найдено компаний: {len(companies)}')

# Проверка по ЕГРЮЛ для компаний, у которых есть ИНН.
# Если ИНН нет или проверить не удалось — компания остаётся без бейджа
# "подтверждено по ЕГРЮЛ", это не блокирует синхронизацию сайта.
verified_count = 0
for c in companies:
    c['egrul_year'] = ''
    if c['inn']:
        info = verify_egrul.lookup_inn(c['inn'])
        # Бейдж показываем только для действующих юрлиц/ИП. Если юрлицо
        # найдено, но деятельность прекращена — не показываем бейдж, чтобы
        # не вводить пользователя в заблуждение о текущем статусе компании.
        if info and info.get('registered_year') and info.get('active'):
            c['egrul_year'] = str(info['registered_year'])
            verified_count += 1
            print(f'  ЕГРЮЛ подтверждён (действующее): {c["name"]} — с {c["egrul_year"]} года')
        elif info and info.get('registered_year') and not info.get('active'):
            print(f'  ЕГРЮЛ: {c["name"]} — юрлицо найдено, но деятельность прекращена, бейдж не ставим')

print(f'Подтверждено по ЕГРЮЛ: {verified_count} из {len(companies)}')

js = 'const COMPANIES = [\n'
total_reviews = 0
for c in companies:
    dirs = json.dumps([d.strip() for d in c['directions'].split(',') if d.strip()], ensure_ascii=False)
    tags = json.dumps([t.strip() for t in c['tags'].split(',') if t.strip()], ensure_ascii=False)
    featured = 'true' if c['featured'].upper() == 'TRUE' else 'false'
    desc = c['description'].replace('"', '\\"')
    cid = str(int(float(c['id']))) if c['id'] else '0'
    crev = str(int(float(c['reviews']))) if c['reviews'] else '0'
    # "Лет на рынке" (years) и год из ЕГРЮЛ — разные вещи (см. кейс
    # Altais-Cars: сайт заявляет "с 1998", а юрлицо перерегистрировано в
    # 2025), но если years так и остался неопределённым дефолтом "1"
    # (extract_years_experience в company_agent.py ничего не нашла в
    # тексте), а ЕГРЮЛ при этом подтверждён — честнее показать возраст
    # юрлица, чем откровенно заниженную "1 год" (баг замечен 09.08.2026 на
    # China Trade: years=1, хотя ЕГРЮЛ — с 2024 года).
    raw_years = c['years']
    if (not raw_years or raw_years == '1') and c['egrul_year']:
        try:
            cyrs = str(max(1, datetime.date.today().year - int(c['egrul_year'])))
        except ValueError:
            cyrs = str(int(float(raw_years))) if raw_years else '1'
    else:
        cyrs = str(int(float(raw_years))) if raw_years else '1'
    total_reviews += int(crev)
    clink = c['site'] if c['site'] else ('https://t.me/' + c['telegram'] if c['telegram'] else '#')
    egrul_verified = 'true' if c['egrul_year'] else 'false'
    js += (f'  {{id:{cid},name:"{c["name"]}",rating:{c["rating"]},reviews:{crev},years:{cyrs},'
           f'delivered:"{c["delivered"]}",description:"{desc}",directions:{dirs},tags:{tags},'
           f'telegram:"{c["telegram"]}",phone:"{c["phone"]}",site:"{c["site"]}",manager:"{c["manager"]}",'
           f'region:"{c["region"]}",featured:{featured},avatar:"{c["avatar"]}",color:"{c["color"]}",'
           f'yandex:"{c["yandex"]}",google:"{c["google"]}",gis2:"{c["gis2"]}",'
           f'instagram:"{c["instagram"]}",vk:"{c["vk"]}",'
           f'avito:"{c["avito"]}",drom:"{c["drom"]}",autoru:"{c["autoru"]}",'
           f'link:"{clink}",egrulVerified:{egrul_verified},egrulYear:"{c["egrul_year"]}"}},\n')
js = js.rstrip(',\n') + '\n];'

html = open('index.html').read()
s = html.find('const COMPANIES = [')
e = html.find('];', s) + 2
html = html[:s] + js + html[e:]

count = len(companies)

# Обновляем реальные цифры в статистике на главной (было: статичный
# плейсхолдер "500+", не совпадавший с фактическими данными).
html = re.sub(
    r'(<div class="stat-n">)[^<]*(</div><div class="stat-l">Компаний в каталоге</div>)',
    rf'\g<1>{count}\g<2>', html)
html = re.sub(
    r'(<div class="stat-n">)[^<]*(</div><div class="stat-l">Отзывов в каталоге</div>)',
    rf'\g<1>{total_reviews:,}'.replace(',', ' ') + r'\g<2>', html)

open('index.html', 'w').write(html)
print(f'Сайт обновлён! {count} компаний, {total_reviews} отзывов, {verified_count} подтверждены по ЕГРЮЛ.')
subprocess.run(['git','add','.'])
subprocess.run(['git','commit','-m',f'update: sync {count} companies from Google Sheets ({verified_count} ЕГРЮЛ-verified)'])
subprocess.run(['git','push','origin','main'])
