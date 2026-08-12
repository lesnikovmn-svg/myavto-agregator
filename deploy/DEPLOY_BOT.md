# Деплой telegram_bot_service.py — пошагово

См. также PROJECT_STATE.md → «Бэкенд для приватных заявок».

## Шаг 1. Создать бота через @BotFather (делает пользователь в своём Telegram)

1. Открыть в Telegram [@BotFather](https://t.me/BotFather).
2. Отправить `/newbot`.
3. Ввести отображаемое имя бота (можно на русском, например «My Avto Agregator»).
4. Ввести username бота — обязательно латиницей и обязательно заканчивается на `bot`
   (например `MyAvtoAgregator_bot`). Должен быть свободен — BotFather предложит
   другой, если занят.
5. BotFather пришлёт токен вида `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`.
   **Токен — секрет, не публикуй его нигде** (ни в чат с Claude, ни в git).

## Шаг 2. Заполнить bot_config.env на Маке

Файл-шаблон уже лежит в `~/myavto-agregator/bot_config.env` (в git не попадает).
Открыть и вписать реальные значения:

```
BOT_TOKEN=<токен из шага 1>
BOT_USERNAME=<username без @, например MyAvtoAgregator_bot>
```

## Шаг 3. Задеплоить бэкенд на VPS (89.108.70.185)

На VPS уже стоит nginx для сайта и есть `/var/www/myavto-agregator` (туда
каждые 10 минут делает `git pull` cron). Но `bot_config.env`,
`agent_config.env` и `credentials.json` в git не попадают — их нужно
скопировать вручную (одноразово).

```bash
# с Мака: скопировать секреты на VPS (одноразово, руками)
scp ~/myavto-agregator/bot_config.env root@89.108.70.185:/var/www/myavto-agregator/
scp ~/myavto-agregator/agent_config.env root@89.108.70.185:/var/www/myavto-agregator/
scp ~/myavto-agregator/credentials.json root@89.108.70.185:/var/www/myavto-agregator/

# на VPS: зайти по ssh
ssh root@89.108.70.185

# поставить зависимости
pip3 install flask requests gspread google-auth

# скопировать systemd unit (telegram_bot_service.py уже там же, т.к. в git)
cp /var/www/myavto-agregator/deploy/telegram-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable telegram-bot
systemctl start telegram-bot
systemctl status telegram-bot   # проверить, что запустился без ошибок
journalctl -u telegram-bot -f   # живой лог, Ctrl+C чтобы выйти
```

Добавить в nginx проксирование `/api/` на бэкенд — см.
`deploy/nginx-api-snippet.conf` (вставить блок `location /api/` внутрь
существующего `server {}` для домена), затем:

```bash
nginx -t && systemctl reload nginx
```

Проверить, что API отвечает:

```bash
curl -X POST https://myavto-agregator.ru/api/mass-request \
  -H "Content-Type: application/json" \
  -d '{"name":"тест","phone":"+70000000000","email":"test@example.com","direction":"Китай"}'
# ожидаем {"request_id": "...", "bot_username": "..."}
```

## Шаг 4. Обновить BOT_USERNAME в index.html

В `index.html` заменить:
```js
const BOT_USERNAME = "My_Avto_Agregator"; // TODO: ...
```
на реальный username из шага 1, закоммитить и запушить — попросить Claude
сделать это после того, как username известен.

## Шаг 5. Онбординг существующих компаний

Бот не может писать компании первым, пока она сама не нажала `/start` у
бота. Разослать компаниям каталога (у кого заполнено поле telegram)
ссылку `t.me/<BOT_USERNAME>` с просьбой один раз нажать «Старт» — иначе
заявки на их направление будут проходить мимо них молча.
