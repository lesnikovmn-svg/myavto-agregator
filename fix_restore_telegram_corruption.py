"""
НАПОМИНАНИЕ (конвенция проекта, см. PROJECT_STATE.md): перед запуском
поставь именованную версию в Google Таблице — Файл → История версий →
Назвать текущую версию → "до fix_restore_telegram_corruption" → Сохранить.
Если что-то пойдёт не так — можно откатиться на неё.

Восстановление колонки J (telegram, канал компании) после порчи багованной
версией fix_telegram_contact_check.py — обнаружено 14.08.2026 пользователем
("почему то из каталога данные вылетели" на карточке ТамСямAUTO: карточка
на месте, Telegram-ссылка пропала).

Разбор: сравнение index.html из git-истории ДО (коммит e7cff4f, синк в
09:13) и ПОСЛЕ (коммит c61d771, синк в 09:23) показало, что за эти 10 минут
колонка telegram (J) была массово испорчена у 51 из 82 компаний. Причина —
в это же окно по живой таблице была запущена СТАРАЯ версия
fix_telegram_contact_check.py (та, что при обнаружении канала/группы либо
ЗАТИРАЛА поле telegram пустым значением, либо ПОДМЕНЯЛА его найденным
личным контактом — именно так описана "старая версия" в докстринге уже
исправленного скрипта, лежащего сейчас в рабочей копии). Исправленный
скрипт (пишет находки в отдельную колонку AE, поле telegram не трогает)
на момент порчи ещё не был закоммичен/запущен — рассинхрон по времени
между правкой кода и фактическим прогоном по таблице.

Последствия порчи (кроме дизайна сайта): бэкенд бота
(telegram_bot_service.py, get_companies()) сопоставляет заявки клиентов
с компаниями ИМЕННО по этому полю telegram — испорченные/пустые значения
у 51 компании означают, что бот их либо не найдёт вообще (пустое поле),
либо ищет их chat_id под ЧУЖИМ username (испорченное значение) и не сможет
разослать им заявку, даже если они онбордились по старому/правильному
хэндлу.

Что делает этот скрипт:
Для каждой из 51 захардкоженной записи (id, ожидаемое имя, правильное
значение telegram ДО порчи, испорченное значение ПОСЛЕ порчи) — ищет
строку в текущей Google Таблице по id (колонка A) и СВЕРЯЕТ имя (колонка B)
и текущее значение telegram (колонка J) с ожидаемым испорченным — если
что-то не совпало (значит строка успела измениться другим путём уже после
порчи), НЕ трогает её и печатает предупреждение. Если совпало:
1. Восстанавливает колонку J в правильное значение (из snapshot ДО порчи).
2. Если испорченное значение было НЕ пустым — это, судя по всему, реальная
   находка старого скрипта (личный контакт), просто записанная не в ту
   колонку (пример: у MY Avto "LesnikovM" — это подтверждённый в других
   местах проекта личный Telegram автора). Не выбрасывает эту работу, а
   переносит найденное значение в колонку AE (31, "Telegram (личный/бот)"),
   но ТОЛЬКО если AE там ещё пустая (не перезаписывает, если кто-то её уже
   заполнил другим путём). Значения переносятся БЕЗ повторной проверки
   через t.me (в отличие от штатного fix_telegram_contact_check.py) — это
   восстановление уже проделанной ранее работы, а не новый поиск. Стоит
   один раз проглядеть глазами по логу перед стартом рассылки/онбординга.
3. Если испорченное значение было пустым — AE просто не трогаем.

Запуск: python3 fix_restore_telegram_corruption.py
После — python3 update_site.py (синкнёт восстановленные данные на сайт
и запушит в GitHub — VPS подхватит через свой 10-минутный git pull).
"""
import time
from company_agent import connect_sheets

ID_COL = 1
NAME_COL = 2
TELEGRAM_COL = 10
TG_CONTACT_COL = 31

# (id, name, telegram_ДО_порчи (правильный), telegram_ПОСЛЕ_порчи (текущий, испорченный))
CORRUPTED = [
    (1, "MY Avto", "MY_Avto5", "LesnikovM"),
    (2, "ТамСямAUTO", "TamSyam26", ""),
    (3, "Primorye China Export", "bezpokrasa", "PrimoryeChinaExport"),
    (4, "Winner Auto Club", "Winner_Auto_Club", "Art_WAC"),
    (7, "Westmotors", "westmotorsru", "OFFICE_WESTMOTORS"),
    (8, "DSS Group", "dss_export", ""),
    (9, "LikeAvto", "likeatg", ""),
    (10, "Veles Auto", "VelesAutoDV_salecar", ""),
    (11, "Восток Транс Импорт", "koreacarsme", ""),
    (12, "Asia Express Auto", "asia_express_auto", ""),
    (13, "Auto Desk", "autodeskusa", "autodeskusabot"),
    (14, "Трансгрупп Авто", "transgroup_ru", ""),
    (15, "AviAuto", "AviAutoBel", "aviauto"),
    (16, "Япония Транзит", "japantransit", ""),
    (18, "AutoEurope TOP", "AutoEuropeTOP", ""),
    (19, "AUTOCARLINE", "AvtoEurope_RF", ""),
    (20, "KorRusMotors", "KoRusMotors", ""),
    (21, "АВТОЗАКАЗ.РУ", "auto_zakazz25", ""),
    (23, "Shapcars", "shapcars", "nikolay_s1"),
    (24, "Dolgov Auto", "dolgov_auto", ""),
    (26, "CarExport", "carexport", ""),
    (27, "OTRADACARS", "OTRADACARS", "olegzhibrovotradacars"),
    (29, "АвтоИмпорт", "avtoimport_russia", ""),
    (30, "Prim-Auto", "prim_auto", ""),
    (32, "Carwin", "carwin_ru", "carwin_official"),
    (35, "Autocreativ", "autocreativ_232", "AUTOCREATIV_bot"),
    (44, "Autoimport.Toyota-T", "autoimport31", "autoimport_sales"),
    (45, "Liautoofficial", "liautoofficial", ""),
    (47, "Autocapital", "autocapitalru", ""),
    (48, "CarsKorea", "carskoreashop", "carskoreasupport"),
    (49, "Anycar.Pro", "anycar123", ""),
    (50, "Autogermanika", "autogermanika", ""),
    (53, "Carsplus", "carsplus_sales", ""),
    (54, "Altais-Cars", "altais_cars", ""),
    (55, "Авто из Европы / Авто Импорт", "auto_import_cars_ru", ""),
    (56, "Авто из Европы / Авто Импорт ПРО", "auto_import_cars_rus", ""),
    (60, "AutoImport Russia", "autoimportrussiarf", "Andrey_AutoImportRussia"),
    (62, "Телеграм канал Levcar", "levcar_125", ""),
    (63, "Авто Азия", "autoasia25", ""),
    (64, "Ярдрей - Авто", "yardrey_auto", "yardrey_auto_reception"),
    (66, "Долгов Авто - Машины из Кореи,Японии,Китая.", "dolgov_auto", ""),
    (68, "EncarRus", "encarrus", "encarrus_manager_bot"),
    (77, "MY AUTO", "myauto_premium", "myautopremium"),
    (79, "MAJORKA IMPORT", "parallel_majorka_import", ""),
    (81, "Авто Заказ", "auto_zakazz25", ""),
    (82, "KOREX", "korex_official", "KorexKorea"),
    (88, "Auto Fact", "autofactpodbor", "autofact_work"),
    (90, "TAT IMPORT AVTO", "tatimoprtavto", ""),
    (92, "Autolegal", "autolegal", "autoleg_ru"),
    (95, "Азия Авто Микс", "asia_auto_mix", ""),
    (98, "Tiger Cars", "TJ_cars", "mistr_tigar"),
]

ws = connect_sheets()
all_values = ws.get_all_values()

restored, moved_to_ae, skipped = 0, 0, 0

for cid, name, correct_tg, corrupted_val in CORRUPTED:
    row_idx = None
    for i, row in enumerate(all_values[1:], start=2):
        row_id = row[ID_COL - 1].strip() if len(row) >= ID_COL else ""
        if row_id == str(cid):
            row_idx = i
            break
    if row_idx is None:
        print(f"[id {cid}] {name}: строка с этим id не найдена, пропускаю")
        skipped += 1
        continue

    row = all_values[row_idx - 1]
    current_name = row[NAME_COL - 1].strip() if len(row) >= NAME_COL else ""
    current_tg = row[TELEGRAM_COL - 1].strip() if len(row) >= TELEGRAM_COL else ""

    if current_name != name:
        print(f"[id {cid}] имя не совпало (в таблице: {current_name!r}, ожидалось: {name!r}) — пропускаю, не трогаю")
        skipped += 1
        continue
    if current_tg != corrupted_val:
        print(f"[id {cid}] {name}: текущий telegram ({current_tg!r}) не похож на испорченное значение "
              f"({corrupted_val!r} ожидалось) — похоже, уже исправлено или изменено кем-то ещё, пропускаю")
        skipped += 1
        continue

    ws.update_cell(row_idx, TELEGRAM_COL, correct_tg)
    restored += 1

    if corrupted_val:
        current_ae = row[TG_CONTACT_COL - 1].strip() if len(row) >= TG_CONTACT_COL else ""
        if not current_ae:
            ws.update_cell(row_idx, TG_CONTACT_COL, corrupted_val)
            moved_to_ae += 1
            print(f"[id {cid}] {name}: канал восстановлен -> {correct_tg}, "
                  f"личный контакт {corrupted_val} перенесён в AE")
        else:
            print(f"[id {cid}] {name}: канал восстановлен -> {correct_tg}, "
                  f"в AE уже что-то есть ({current_ae!r}) — не перезаписываю")
    else:
        print(f"[id {cid}] {name}: канал восстановлен -> {correct_tg}")
    time.sleep(0.3)

print(f"\nИтого: восстановлено каналов — {restored}, "
      f"личных контактов перенесено в AE — {moved_to_ae}, "
      f"пропущено (не совпало) — {skipped}")
print("\nТеперь прогони python3 update_site.py.")
