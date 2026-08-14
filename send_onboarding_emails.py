"""
Рассылка по email компаниям из каталога — приглашение онбордиться у
Telegram-бота (нажать /start у t.me/MyAvtoAgregator_bot), чтобы начать
получать заявки клиентов. 14.08.2026, по запросу пользователя
("давай попочте разошлем") — после того как check_onboarded.py показал
0 из 65 компаний онбордившихся.

ПЕРЕД ПЕРВЫМ ЗАПУСКОМ:
1. Email должен быть собран заранее — см. add_email_column.py +
   fix_backfill_emails.py (если ещё не запускал fix_backfill_emails.py,
   у большинства компаний колонка email(AF) будет пустая, слать будет
   почти некому — запусти его сначала).
2. Скопируй mail_config.env.example -> mail_config.env, впиши реальные
   SMTP-данные (инструкция для Gmail — прямо в mail_config.env.example).

Кому шлём: компании с непустым email И непустым telegram (телеграм нужен,
иначе бот всё равно не сможет их онбордить — email тут только способ
ДОСТУЧАТЬСЯ до компании, чтобы она сама нажала /start в Telegram).
id:1 (MY Avto, собственная компания пользователя) исключена.

Кого пропускаем автоматически:
- Уже онбордившихся — если рядом лежит bot_state.json (скопируй с VPS:
  scp root@89.108.70.185:/var/www/myavto-agregator/bot_state.json .),
  скрипт сверится с ним и не будет спамить тех, кто уже нажал /start.
  Если файла нет — просто пропускает эту проверку (не критично, письмо
  с просьбой онбордиться уже онбордившейся компании не страшно, но лучше
  не слать).
- Уже получивших это письмо раньше — ведётся локальный лог
  onboarding_emails_log.json (не в git, см. .gitignore), при повторном
  запуске те, кому уже отправляли, пропускаются автоматически. Если
  захочешь отправить кому-то ещё раз — удали его email из этого файла
  вручную (это простой JSON-список).

Перед реальной отправкой скрипт ПОКАЗЫВАЕТ пример письма и количество
получателей, и просит подтверждения (ввести "да") — чтобы не разослать
что-то по ошибке раньше времени.

Запуск: python3 send_onboarding_emails.py
"""
import json
import os
import smtplib
import time
from email.mime.text import MIMEText

from company_agent import connect_sheets

ID_COL = 1
NAME_COL = 2
TELEGRAM_COL = 10
EMAIL_COL = 32

BOT_USERNAME = "MyAvtoAgregator_bot"
BOT_STATE_FILE = "bot_state.json"
LOG_FILE = "onboarding_emails_log.json"
MAIL_CONFIG_FILE = "mail_config.env"

SUBJECT = "Бесплатное размещение в каталоге myavto-agregator.ru — активируйте приём заявок"

BODY_TEMPLATE = """Здравствуйте!

Меня зовут Максим, я собрал бесплатный каталог компаний по импорту авто \
(Китай, Корея, Япония, США, ОАЭ, Европа) — myavto-agregator.ru.

Ваша компания «{name}» уже есть в каталоге бесплатно, ничего платить не \
нужно. Чтобы начать получать заявки от клиентов сайта напрямую себе в \
Telegram, нужно один раз (10 секунд) нажать «Старт» у бота:

t.me/{bot_username}

После этого заявки клиентов по вашему направлению будут приходить лично \
вам в Telegram. Кто активируется раньше — тот раньше и начинает получать \
заявки.

Если есть вопросы — просто ответьте на это письмо.

С уважением,
Максим
myavto-agregator.ru
"""


def load_mail_config():
    if not os.path.exists(MAIL_CONFIG_FILE):
        print(f"Не нашёл {MAIL_CONFIG_FILE}. Скопируй mail_config.env.example "
              f"в {MAIL_CONFIG_FILE} и впиши реальные SMTP-данные (инструкция "
              f"для Gmail — прямо в примере).")
        raise SystemExit(1)
    cfg = {}
    with open(MAIL_CONFIG_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
    return cfg


def load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


cfg = load_mail_config()
already_onboarded = set(load_json(BOT_STATE_FILE, {"companies": {}}).get("companies", {}).keys())
already_emailed = set(load_json(LOG_FILE, []))

if not os.path.exists(BOT_STATE_FILE):
    print(f"({BOT_STATE_FILE} не найден рядом — пропускаю проверку "
          f"'уже онбордился', это не критично.)\n")

ws = connect_sheets()
all_values = ws.get_all_values()

recipients = []
skipped_no_email, skipped_no_telegram, skipped_onboarded, skipped_already_sent = 0, 0, 0, 0

for row in all_values[1:]:
    def val(col):
        return row[col - 1].strip() if len(row) >= col else ""

    company_id = val(ID_COL)
    name = val(NAME_COL)
    telegram = val(TELEGRAM_COL).lstrip("@").lower()
    email = val(EMAIL_COL)

    if not name or company_id == "1":
        continue
    if not email:
        skipped_no_email += 1
        continue
    if not telegram:
        skipped_no_telegram += 1
        continue
    if telegram in already_onboarded:
        skipped_onboarded += 1
        continue
    if email.lower() in already_emailed:
        skipped_already_sent += 1
        continue

    recipients.append({"name": name, "email": email, "telegram": telegram})

print(f"Найдено получателей: {len(recipients)}")
print(f"Пропущено: без email — {skipped_no_email}, без telegram — {skipped_no_telegram}, "
      f"уже онбордились — {skipped_onboarded}, уже отправляли письмо раньше — {skipped_already_sent}")

if not recipients:
    print("\nОтправлять некому — выйти.")
    raise SystemExit(0)

sample = recipients[0]
sample_body = BODY_TEMPLATE.format(name=sample["name"], bot_username=BOT_USERNAME)
print(f"\nПример письма (получателю {sample['name']} <{sample['email']}>):")
print("-" * 60)
print(f"Тема: {SUBJECT}\n")
print(sample_body)
print("-" * 60)

answer = input(f"\nОтправить это письмо (с подстановкой имени компании) "
               f"{len(recipients)} получателям? Введи 'да' для подтверждения: ")
if answer.strip().lower() != "да":
    print("Отменено, ничего не отправлено.")
    raise SystemExit(0)

sent, failed = 0, 0
with smtplib.SMTP(cfg["SMTP_HOST"], int(cfg["SMTP_PORT"])) as server:
    server.starttls()
    server.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
    for r in recipients:
        body = BODY_TEMPLATE.format(name=r["name"], bot_username=BOT_USERNAME)
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = SUBJECT
        msg["From"] = f"{cfg.get('FROM_NAME', cfg['SMTP_USER'])} <{cfg['SMTP_USER']}>"
        msg["To"] = r["email"]
        try:
            server.sendmail(cfg["SMTP_USER"], [r["email"]], msg.as_string())
            print(f"  OK: {r['name']} <{r['email']}>")
            already_emailed.add(r["email"].lower())
            sent += 1
        except Exception as e:
            print(f"  ОШИБКА: {r['name']} <{r['email']}> — {e}")
            failed += 1
        save_json(LOG_FILE, sorted(already_emailed))
        time.sleep(2)

print(f"\nИтого: отправлено — {sent}, ошибок — {failed}.")
print(f"Лог отправленных сохранён в {LOG_FILE} — при повторном запуске "
      f"эти адреса будут пропущены автоматически.")
