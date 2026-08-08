"""
Проверка компании по ИНН через ЕГРЮЛ/ЕГРИП.

Основной источник — бесплатное зеркало egrul.itsoft.ru без ключа.
ПОДТВЕРЖДЕНО НА ПРАКТИКЕ (08.08.2026): зеркало отдаёт 403 Forbidden на
реальный ИНН — либо блокирует по bot-detection, либо сменило политику
доступа. Добавлены браузерные заголовки (см. _fetch_itsoft), но
гарантий, что это исправит 403, нет.

Резервный источник — DaData Suggestions API (сработает без правок кода,
если задать токен):
  1. Зарегистрироваться на https://dadata.ru (бесплатно)
  2. Взять API-ключ в личном кабинете
  3. Добавить строку в agent_config.env:  DADATA_TOKEN=твой_ключ
  Бесплатного тарифа хватает на проверку каталога из 40-50 компаний.

Проверь после правок: python3 verify_egrul.py <реальный ИНН>

Результаты кэшируются в egrul_cache.json, чтобы не дёргать сервисы
повторно при каждом запуске update_site.py.
"""
import json, os, re, time, urllib.request

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'egrul_cache.json')
_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'agent_config.env')


def _load_env_file():
    """Подтягиваем agent_config.env в os.environ, если ключей там ещё нет
    (company_agent.py делает это по-своему в свой локальный dict — здесь
    нужно именно в os.environ, чтобы os.environ.get('DADATA_TOKEN') работал)."""
    if not os.path.exists(_CONFIG_FILE):
        return
    try:
        with open(_CONFIG_FILE, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    os.environ.setdefault(k.strip(), v.strip())
    except Exception:
        pass


_load_env_file()


def _load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_cache(cache):
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print('Не удалось сохранить кэш ЕГРЮЛ:', e)


def _extract_reg_date(data):
    """Пытаемся вытащить дату регистрации из разных возможных форм ответа."""
    candidates = []
    if isinstance(data, dict):
        for key in ('ДатаОГРН', 'reg_date', 'registration_date', 'ogrn_date'):
            if key in data:
                candidates.append(data[key])
        # вложенные структуры (data.state.registration_date и т.п.)
        for nested_key in ('data', 'state', 'СвОбрЮЛ', 'СвРегОрг'):
            nested = data.get(nested_key)
            if isinstance(nested, dict):
                for key in ('ДатаОГРН', 'reg_date', 'registration_date'):
                    if key in nested:
                        candidates.append(nested[key])
    for c in candidates:
        if c:
            return str(c)
    return None


def _extract_terminated(data):
    """
    Проверяем, не прекратила ли компания/ИП деятельность (закрыто, ликвидировано,
    исключено из реестра). Это важно: если юрлицо закрыто, нельзя показывать
    сайту зелёный бейдж "подтверждено ЕГРЮЛ" — это будет вводить в заблуждение
    так же, как непроверенный рейтинг 4.5 у новых компаний.
    """
    if not isinstance(data, dict):
        return False
    termination_keys = ('ДатаПрекращения', 'termination_date', 'ПрекрДеят',
                         'liquidation_date', 'ДеятПрекращена')
    for key in termination_keys:
        if data.get(key):
            return True
    status = str(data.get('status') or data.get('Статус') or '').lower()
    if any(word in status for word in ('прекращ', 'ликвид', 'закрыт', 'terminated', 'closed')):
        return True
    return False


def _fetch_itsoft(inn):
    url = f'https://egrul.itsoft.ru/{inn}.json'
    # Зеркало отдаёт 403 на "голые" запросы без браузероподобных заголовков —
    # добавляем Accept/Referer/Accept-Language, это обычно снимает блокировку
    # по простому bot-detection (не всегда, зеркало может быть нестабильным).
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                       '(KHTML, like Gecko) Chrome/124.0 Safari/537.36',
        'Accept': 'application/json,text/plain,*/*',
        'Accept-Language': 'ru-RU,ru;q=0.9',
        'Referer': 'https://egrul.itsoft.ru/',
    })
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode('utf-8'))


def _fetch_dadata(inn):
    """
    Резервный источник — DaData Suggestions API. Нужен бесплатный токен:
    зарегистрироваться на dadata.ru, взять API-ключ в личном кабинете,
    прописать в agent_config.env строку DADATA_TOKEN=...
    Бесплатного тарифа достаточно для проверки нескольких десятков ИНН.
    """
    token = os.environ.get('DADATA_TOKEN', '')
    if not token:
        return None
    url = 'https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party'
    body = json.dumps({'query': inn}).encode('utf-8')
    req = urllib.request.Request(url, data=body, method='POST', headers={
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Token {token}',
    })
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read().decode('utf-8'))
    suggestions = data.get('suggestions') or []
    if not suggestions:
        return None
    d = suggestions[0].get('data', {})
    state = d.get('state', {})
    reg_ms = state.get('registration_date')  # unix-время в миллисекундах
    year = None
    if reg_ms:
        try:
            year = time.gmtime(int(reg_ms) / 1000).tm_year
        except Exception:
            year = None
    status = str(state.get('status') or '').upper()  # ACTIVE | LIQUIDATED | LIQUIDATING | ...
    return {
        'registered_year': year,
        'active': status == 'ACTIVE',
        'name': (d.get('name') or {}).get('short_with_opf'),
    }


def lookup_inn(inn):
    """
    Возвращает {'registered_year': int, 'name': str, 'active': bool} или None,
    если проверить не удалось (это не факт мошенничества — просто нет данных).

    Если юрлицо/ИП найдено, но деятельность прекращена (ликвидация, закрытие
    ИП и т.п.) — active=False. Бейдж "подтверждено ЕГРЮЛ" на сайте должен
    показываться только когда active=True: компания могла честно работать
    годами и закрыть старое ИП, но текущий зелёный бейдж не должен создавать
    впечатление, что регистрация актуальна на сегодня, если это не так.
    """
    inn = re.sub(r'\D', '', str(inn or ''))
    if len(inn) not in (10, 12):
        return None

    cache = _load_cache()
    if inn in cache:
        return cache[inn]

    result = None

    # Источник 1: бесплатное зеркало без ключа. Может отдавать 403/бывать
    # нестабильным (bot-detection, смена формата) — тогда просто идём дальше.
    try:
        data = _fetch_itsoft(inn)
        reg_date = _extract_reg_date(data)
        terminated = _extract_terminated(data)
        name = None
        if isinstance(data, dict):
            name = data.get('НаимСокр') or data.get('НаимПолн') or data.get('name')
        if reg_date:
            year_match = re.search(r'(\d{4})', reg_date)
            if year_match:
                result = {
                    'registered_year': int(year_match.group(1)),
                    'name': name,
                    'active': not terminated,
                }
    except Exception as e:
        print(f'  ЕГРЮЛ (itsoft): не удалось проверить ИНН {inn}: {e}')

    # Источник 2 (резерв): DaData, если в itsoft не вышло и задан DADATA_TOKEN
    # в agent_config.env. Требует бесплатной регистрации на dadata.ru.
    if result is None:
        try:
            result = _fetch_dadata(inn)
            if result:
                print(f'  ЕГРЮЛ (DaData): {inn} — резервный источник сработал')
        except Exception as e:
            print(f'  ЕГРЮЛ (DaData): не удалось проверить ИНН {inn}: {e}')

    cache[inn] = result
    _save_cache(cache)
    time.sleep(1)
    return result


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        print(lookup_inn(sys.argv[1]))
    else:
        print('Использование: python3 verify_egrul.py <ИНН>')
        print('Пример: python3 verify_egrul.py 7707083893')
