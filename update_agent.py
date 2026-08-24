with open("company_agent.py", "r") as f:
    code = f.read()

# Новые запросы
new_queries = """    queries = [
        "авто под заказ Telegram импорт",
        "импорт авто Telegram канал",
        "авто из Кореи Китая под заказ Telegram WhatsApp",
        "пригон авто Японии аукцион Telegram",
        "авто в наличии склад Китай Корея Telegram",
        "параллельный импорт авто Telegram канал",
        "авто США ОАЭ Европа под заказ Telegram",
        "импорт авто Краснодар Telegram",
        "импорт авто Москва Telegram канал",
        "авто из Китая электромобили Telegram",
        "растаможка авто Армения Грузия Telegram",
        "авто аукцион Япония Корея Telegram",
        "авто под заказ WhatsApp импортёр",
        "автомобили под заказ из Кореи отзывы",
        "пригон авто отзывы компания Россия",
    ]"""

# Старые запросы для замены
old_queries = """    queries = [
        "импорт авто из Кореи Россия компания Telegram",
        "импорт авто из Китая под ключ Россия",
        "пригон авто из Японии аукцион Россия",
        "параллельный импорт авто США ОАЭ Россия",
        "авто из Европы под заказ Россия компания",
    ]"""

code = code.replace(old_queries, new_queries)

# Обновляем фильтр
old_filter = """            if company["active"] or company["telegram"]:"""
new_filter = """            has_auto = any(w in (company["snippet"]+company["name"]).lower() for w in ["авто","импорт","машин","автомобил","пригон","растаможк","корея","китай","япония","car","auto","korea","china","japan"])
            has_contact = bool(company["telegram"]) or company["phone"] != "-" or bool(company["site"])
            if has_auto and has_contact:"""

code = code.replace(old_filter, new_filter)

with open("company_agent.py", "w") as f:
    f.write(code)
print("Done!")
