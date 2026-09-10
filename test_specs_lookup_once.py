"""T-161 (10.09.2026): ручная диагностика car_specs_lookup.py на реальном
сайте — НЕ трогает Telegram/бота вообще, только requests. Нужен, потому
что вся разметка ultimatespecs.com в car_specs_lookup.py подобрана по
текстовому описанию (WebFetch), не по реальным байтам страницы (прямой
исходящий доступ к сайту из песочницы, где писался код, заблокирован
политикой организации) — первая настоящая проверка возможна только
отсюда, с VPS (или с любой машины с обычным доступом в интернет).

Использование:
    python3 test_specs_lookup_once.py BMW X7 2026 xDrive40d
    python3 test_specs_lookup_once.py Mercedes-Benz GLE 2025

Печатает КАЖДЫЙ шаг (хаб -> поколение -> версия -> ТТХ) отдельно, а не
только финальный результат — если что-то не находится, сразу видно, на
каком именно шаге (и что реально вернул сайт), чтобы можно было прислать
этот вывод обратно и поправить регулярки в car_specs_lookup.py по факту,
а не гадать заново."""
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0] if "/" in __file__ else ".")
import car_specs_lookup as csl


def main():
    if len(sys.argv) < 3:
        print("Использование: python3 test_specs_lookup_once.py <Бренд> <Модель> [Год] [Комплектация]")
        print('Пример: python3 test_specs_lookup_once.py BMW X7 2026 xDrive40d')
        return

    brand = sys.argv[1]
    model = sys.argv[2]
    year = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3].isdigit() else None
    trim_hint = sys.argv[4] if len(sys.argv) > 4 else (sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].isdigit() else None)

    print(f"Бренд={brand!r} Модель={model!r} Год={year!r} Комплектация-подсказка={trim_hint!r}")
    print()

    hub = csl.hub_url(brand, model)
    print(f"[1/4] Хаб-страница поколений: {hub}")
    hub_html = csl._get(hub)
    if not hub_html:
        print("  -> не удалось получить страницу (см. лог выше/ошибку сети) — СТОП")
        return
    print(f"  -> получено {len(hub_html)} байт HTML")

    generations = csl._find_generations(hub_html)
    print(f"  -> найдено поколений: {len(generations)}")
    for g in generations:
        print(f"     - {g['text']!r} ({g['year_from']}-{g['year_to'] or 'present'}) -> {g['href']}")
    if not generations:
        print("  Поколения не распознались — возможно, разметка хаб-страницы отличается от ожидаемой.")
        print("  Первые 2000 символов страницы (для ручного разбора):")
        print(hub_html[:2000])
        return

    gen = csl._pick_generation(generations, year)
    if not gen:
        print(f"  -> ни одно поколение не подходит под год {year} — СТОП")
        return
    print(f"\n[2/4] Выбранное поколение: {gen['text']!r} -> {gen['href']}")

    gen_html = csl._get(gen["href"])
    if not gen_html:
        print("  -> не удалось получить страницу поколения — СТОП")
        return
    print(f"  -> получено {len(gen_html)} байт HTML")

    versions = csl._find_versions(gen_html)
    print(f"  -> найдено версий/комплектаций: {len(versions)}")
    for href, text in versions:
        print(f"     - {text!r} -> {href}")
    if not versions:
        print("  Версии не распознались — возможно, разметка страницы поколения отличается от ожидаемой.")
        print("  Первые 2000 символов страницы (для ручного разбора):")
        print(gen_html[:2000])
        return

    picked = csl._pick_version(versions, trim_hint)
    if not picked:
        print(f"\n[3/4] Комплектация по подсказке {trim_hint!r} НЕ найдена однозначно — СТОП (см. список версий выше)")
        return
    version_href, version_text = picked
    print(f"\n[3/4] Выбранная версия: {version_text!r} -> {version_href}")

    spec_html = csl._get(version_href)
    if not spec_html:
        print("  -> не удалось получить страницу ТТХ — СТОП")
        return
    print(f"  -> получено {len(spec_html)} байт HTML")

    specs = csl._extract_specs_from_page(spec_html)
    print(f"\n[4/4] Распознанные характеристики: {specs}")
    if not specs or len(specs) < 3:
        print("  Мало/ничего не распозналось — вот первые 3000 символов страницы ТТХ (plain-текст после снятия тегов),")
        print("  пришлите этот кусок — поправлю метки в _FIELD_LABELS/_VALUE_PATTERNS по факту:")
        print("\n".join(csl._to_lines(spec_html)[:80]))

    print("\n--- Итог через lookup_specs() (с учётом кэша) ---")
    print(csl.lookup_specs(brand, model, year, trim_hint))


if __name__ == "__main__":
    main()
