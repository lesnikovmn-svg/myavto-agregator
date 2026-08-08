"""
Проверка компании по ИНН через публичное бесплатное зеркало ЕГРЮЛ/ЕГРИП
(egrul.itsoft.ru — без API-ключа, неофициальный, но открытый источник).

ВАЖНО (прочитать перед использованием):
- Точный формат JSON-ответа зеркала не был протестирован live из песочницы
  Claude (внешняя сеть там ограничена allowlist'ом). Парсинг полей ниже
  сделан по документированному формату ЕГРЮЛ-выгрузок, но перед боевым
  использованием прогони lookup_inn() на 2-3 реальных ИНН локально
  (python3 verify_egrul.py <ИНН>) и проверь, что registered_year
  действительно совпадает с датой регистрации компании.
- Если сервис недоступен, изменил формат или ИНН не найден — функция
  возвращает None. Это не должно останавливать sync сайта: компания
  просто останется без бейджа "подтверждено по ЕГРЮЛ".
- Результаты кэшируются в egrul_cache.json, чтобы не дёргать сервис
  повторно при каждом запуске update_site.py.
"""
import json, os, re, time, urllib.request

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'egrul_cache.json')


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
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode('utf-8'))


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
        print(f'  ЕГРЮЛ: не удалось проверить ИНН {inn}: {e}')
        result = None

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
