import urllib.request, json, re, subprocess

import os
import verify_egrul

SHEET_ID = os.environ.get('SHEET_ID', '1u3WuYo6Iyb4RJMQVbanx4YGm29B2V-DQMuKzVrtdcLY')
URL = f'https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:json'

print('Загружаю данные из Google Sheets...')
req = urllib.request.Request(URL, headers={'User-Agent': 'Mozilla/5.0'})
raw = urllib.request.urlopen(req).read().decode('utf-8')
json_str = re.search(r'setResponse\((.*)\)', raw, re.DOTALL).group(1)
data = json.loads(json_str)
rows = data['table']['rows']

companies = []
for row in rows[0:]:
    c = row['c']
    def val(i):
        if i < len(c) and c[i] and c[i].get('v') is not None:
            return str(c[i]['v']).strip()
        return ''
    # gviz-API отдаёт длинные числовые ячейки (например ИНН) как float —
    # "6234062211" превращается в "6234062211.0". Если это не почистить,
    # verify_egrul потом вырежет только точку регэкспом и получит
    # "62340622110" — лишний ноль, ИНН не совпадёт ни с чем.
    raw_inn = val(18)
    inn = raw_inn[:-2] if raw_inn.endswith('.0') else raw_inn

    company = dict(id=val(0),name=val(1),rating=val(2),reviews=val(3),years=val(4),
        delivered=val(5),description=val(6),directions=val(7),tags=val(8),
        telegram=val(9),phone=val(10),site=val(11),manager=val(12),
        region=val(13),featured=val(14),avatar=val(15),color=val(16),yandex=val(17),
        inn=inn)
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
    cyrs = str(int(float(c['years']))) if c['years'] else '1'
    total_reviews += int(crev)
    clink = c['site'] if c['site'] else ('https://t.me/' + c['telegram'] if c['telegram'] else '#')
    egrul_verified = 'true' if c['egrul_year'] else 'false'
    js += (f'  {{id:{cid},name:"{c["name"]}",rating:{c["rating"]},reviews:{crev},years:{cyrs},'
           f'delivered:"{c["delivered"]}",description:"{desc}",directions:{dirs},tags:{tags},'
           f'telegram:"{c["telegram"]}",phone:"{c["phone"]}",site:"{c["site"]}",manager:"{c["manager"]}",'
           f'region:"{c["region"]}",featured:{featured},avatar:"{c["avatar"]}",color:"{c["color"]}",'
           f'yandex:"{c["yandex"]}",link:"{clink}",egrulVerified:{egrul_verified},egrulYear:"{c["egrul_year"]}"}},\n')
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
