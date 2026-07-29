import urllib.request, json, re, subprocess

import os
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
    company = dict(id=val(0),name=val(1),rating=val(2),reviews=val(3),years=val(4),
        delivered=val(5),description=val(6),directions=val(7),tags=val(8),
        telegram=val(9),phone=val(10),site=val(11),manager=val(12),
        region=val(13),featured=val(14),avatar=val(15),color=val(16),yandex=val(17))
    if company['name']:
        companies.append(company)

print(f'Найдено компаний: {len(companies)}')

js = 'const COMPANIES = [\n'
for c in companies:
    dirs = json.dumps([d.strip() for d in c['directions'].split(',') if d.strip()], ensure_ascii=False)
    tags = json.dumps([t.strip() for t in c['tags'].split(',') if t.strip()], ensure_ascii=False)
    featured = 'true' if c['featured'].upper() == 'TRUE' else 'false'
    desc = c['description'].replace('"', '\\"')
    cid = str(int(float(c['id']))) if c['id'] else '0'
    crev = str(int(float(c['reviews']))) if c['reviews'] else '0'
    cyrs = str(int(float(c['years']))) if c['years'] else '1'
    js += f'  {{id:{cid},name:"{c["name"]}",rating:{c["rating"]},reviews:{crev},years:{cyrs},delivered:"{c["delivered"]}",description:"{desc}",directions:{dirs},tags:{tags},telegram:"{c["telegram"]}",phone:"{c["phone"]}",site:"{c["site"]}",manager:"{c["manager"]}",region:"{c["region"]}",featured:{featured},avatar:"{c["avatar"]}",color:"{c["color"]}",yandex:"{c["yandex"]}"}},\n'
js = js.rstrip(',\n') + '\n];'

html = open('index.html').read()
s = html.find('const COMPANIES = [')
e = html.find('];', s) + 2
html = html[:s] + js + html[e:]

count = len(companies)
import re as re2
html = re2.sub(r'<div class="stat-n">\d+</div><div class="stat-l">Компаний в каталоге</div>', f'<div class="stat-n">{count}</div><div class="stat-l">Компаний в каталоге</div>', html)
html = html.replace('10 проверенных компаний', f'{count} проверенных компаний')
html = html.replace('10 компаний-импортёров', f'{count} компаний-импортёров')

open('index.html', 'w').write(html)
print(f'Сайт обновлён! {count} компаний.')
subprocess.run(['git','add','.'])
subprocess.run(['git','commit','-m',f'update: sync {count} companies from Google Sheets'])
subprocess.run(['git','push','origin','main'])
