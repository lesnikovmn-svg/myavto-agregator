"""
T-27 (21.08.2026): бэкап Google Sheets — единственного источника правды по
компаниям. До этого скрипта восстановление после случайной порчи строки или
бага в fix-скрипте было возможно только вручную через именованные версии
Google Sheets (Файл -> История версий), если пользователь вообще догадается
туда зайти вовремя — реальный случай (см. PROJECT_STATE.md, инцидент с
колонкой telegram у 51 компании из 82) показал, что это ненадёжно.

Что делает:
1. Подключается к той же таблице, что company_agent.py/update_site.py
   (credentials.json, agent_config.env — ничего нового заводить не нужно).
2. Выгружает КАЖДУЮ вкладку (сейчас: главный лист компаний + "Отзывы") в
   CSV-файл — с ним можно тут же вручную восстановить данные через
   Файл -> Импорт в Google Sheets, не нужен никакой код для отката.
3. Кладёт файлы в backups/<YYYY-MM-DD_HH-MM>/, старые каталоги (кроме
   последних KEEP_BACKUPS) удаляет — бэкапы не должны бесконтрольно
   разрастаться на диске VPS.
4. Если рядом лежит mail_config.env (тот же, что уже используют
   send_onboarding_emails.py и telegram_bot_service.py) — по понедельникам
   дополнительно отправляет ZIP с бэкапом на ADMIN_EMAIL. Это единственная
   офсайт-копия (бэкап в п.2-3 живёт на том же VPS, что и сама таблица —
   при потере сервера бесполезен без этого). Раз в неделю, а не каждый
   день, чтобы не заваливать почту (тот же принцип, что и у notify_admin()
   в telegram_bot_service.py).

Использование:
    python3 backup_sheets.py          # вручную
Cron (см. daily_update.sh):           # автоматически, раз в день
    python3 backup_sheets.py >> daily_update.log 2>&1

Восстановление из бэкапа: открыть нужный backups/<дата>/<вкладка>.csv,
в Google Sheets — Файл -> Импорт -> Заменить текущий лист (или отдельным
листом, если нужно сверить построчно перед заменой).
"""
import csv
import datetime
import os
import shutil
import smtplib
import zipfile
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart

import gspread
from google.oauth2.service_account import Credentials

BACKUPS_DIR = "backups"
KEEP_BACKUPS = 14  # хранить последние 14 запусков (~2 недели при ежедневном cron)

config = {}
with open("agent_config.env") as f:
    for line in f:
        if "=" in line:
            k, v = line.strip().split("=", 1)
            config[k] = v
SHEET_ID = config["SHEET_ID"]

MAIL_CONFIG = {}
if os.path.exists("mail_config.env"):
    with open("mail_config.env") as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                MAIL_CONFIG[k.strip()] = v.strip()


def connect():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID)


def safe_filename(title):
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in title) + ".csv"


def dump_sheet(sh, out_dir):
    written = []
    for ws in sh.worksheets():
        rows = ws.get_all_values()
        path = os.path.join(out_dir, safe_filename(ws.title))
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerows(rows)
        written.append((ws.title, len(rows), path))
    return written


def rotate_old_backups():
    if not os.path.isdir(BACKUPS_DIR):
        return
    entries = sorted(
        (d for d in os.listdir(BACKUPS_DIR) if os.path.isdir(os.path.join(BACKUPS_DIR, d))),
    )
    stale = entries[:-KEEP_BACKUPS] if len(entries) > KEEP_BACKUPS else []
    for d in stale:
        shutil.rmtree(os.path.join(BACKUPS_DIR, d), ignore_errors=True)
    if stale:
        print(f"[backup] удалено старых бэкапов: {len(stale)}")


def email_offsite_copy(out_dir, label):
    if not MAIL_CONFIG:
        print("[backup] mail_config.env нет — офсайт-копия по почте пропущена (это ок, локальный бэкап уже сделан)")
        return
    if datetime.date.today().weekday() != 0:  # только по понедельникам
        return
    zip_path = out_dir + ".zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in os.listdir(out_dir):
            zf.write(os.path.join(out_dir, name), arcname=name)
    try:
        from_addr = MAIL_CONFIG["SMTP_USER"]
        to_addr = MAIL_CONFIG.get("ADMIN_EMAIL", "").strip() or from_addr
        msg = MIMEMultipart()
        msg["Subject"] = f"MyAvtoAgregator — еженедельный бэкап таблицы ({label})"
        msg["From"] = f"{MAIL_CONFIG.get('FROM_NAME', from_addr)} <{from_addr}>"
        msg["To"] = to_addr
        msg.attach(MIMEApplication(open(zip_path, "rb").read(), Name=os.path.basename(zip_path)))
        with smtplib.SMTP(MAIL_CONFIG["SMTP_HOST"], int(MAIL_CONFIG["SMTP_PORT"]), timeout=20) as server:
            server.starttls()
            server.login(from_addr, MAIL_CONFIG["SMTP_PASSWORD"])
            server.sendmail(from_addr, [to_addr], msg.as_string())
        print(f"[backup] офсайт-копия отправлена на {to_addr}")
    except Exception as e:
        print(f"[backup] не удалось отправить офсайт-копию: {e}")
    finally:
        os.remove(zip_path)


def main():
    label = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
    out_dir = os.path.join(BACKUPS_DIR, label)
    os.makedirs(out_dir, exist_ok=True)

    sh = connect()
    written = dump_sheet(sh, out_dir)
    for title, n_rows, path in written:
        print(f"[backup] {title}: {n_rows} строк -> {path}")

    rotate_old_backups()
    email_offsite_copy(out_dir, label)
    print(f"[backup] готово: {out_dir}")


if __name__ == "__main__":
    main()
