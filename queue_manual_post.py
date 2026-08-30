"""T-99 (30.08.2026). Кладёт вручную собранный пост (готовый текст + локальные
файлы) в очередь userbot_manual_queue.json — заберёт и отправит уже
запущенный на этом сервере myavto-userbot, тем же живым client, без второй
Telethon-сессии (см. queue_manual_post()/_manual_queue_flusher() в
userbot_parser.py).

ВАЖНО: запускать ЭТИМ CLI ПРЯМО НА СЕРВЕРЕ юзербота, рядом с
userbot_parser.py (нужен тот же venv с telethon). Файлы из --media должны
уже лежать на этом сервере по указанным путям — сам скрипт их никуда не
копирует, только кладёт путь в очередь.

Пример:
  cd /путь/до/проекта/на/сервере/юзербота
  python3 queue_manual_post.py \
      --text-file musso_post.md \
      --media final_short.mp4 \
      --targets @My_Avto_Optimal @MY_Avto5
"""
import argparse

from userbot_parser import queue_manual_post


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--text-file", required=True, help="путь к файлу с готовым текстом поста (markdown)")
    ap.add_argument("--media", nargs="*", default=[], help="пути к файлам НА ЭТОМ СЕРВЕРЕ (фото/видео)")
    ap.add_argument("--targets", nargs="+", required=True, help="каналы, например @My_Avto_Optimal @MY_Avto5")
    args = ap.parse_args()

    text = open(args.text_file, encoding="utf-8").read()
    item_id = queue_manual_post(text, args.media, args.targets)
    print(f"Поставлено в очередь: {item_id}")
    print("Заберёт и отправит уже запущенный myavto-userbot в течение ~60 секунд (следующий цикл _manual_queue_flusher).")
    print("Проверить: journalctl -u myavto-userbot -f  (искать строки '[manual#...]')")


if __name__ == "__main__":
    main()
