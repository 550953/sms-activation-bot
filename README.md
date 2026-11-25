# SMS Gateway — Personal Telegram Bot

Минимальный личный бот для получения номеров через твой SMS API.  
Без базы, без платежей, только whitelist пользователей.

## Что умеет

- Список стран кнопками (пагинация)
- Если у страны несколько операторов — выбор кнопкой
- Номер в двух форматах (`+6399…` и `6399…`)
- Кнопки «Проверить SMS» / «Стоп»
- Автоматическое ожидание кода в фоне (до 8 мин)
- Доступ только для ID из `ALLOWED_USER_IDS`

## Быстрый старт локально

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# заполни BOT_TOKEN, SMS_API_KEY, ALLOWED_USER_IDS

python bot.py
```

Свой Telegram ID можно узнать у [@userinfobot](https://t.me/userinfobot).

## Деплой на Render (Free)

1. Создай **Web Service** (не Background Worker — на free он недоступен).
2. Подключи репозиторий.
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `python bot.py`
5. В **Environment** добавь:
   - `BOT_TOKEN`
   - `SMS_API_KEY`
   - `ALLOWED_USER_IDS` (через запятую)
6. После деплоя возьми URL сервиса (типа `https://xxx.onrender.com`) и повесь на него **cron** (cron-job.org / UptimeRobot / GitHub Actions), который раз в 10–14 минут делает `GET /`.  
   Это нужно, чтобы Render не усыплял сервис.

Если сервис всё-таки уснёт — при следующем пинге или сообщении боту он проснётся за ~30–60 секунд.

## Безопасность

- Ключи **только** через переменные окружения Render.
- В репозитории лежит только `.env.example`.
- Бот отвечает только пользователям из `ALLOWED_USER_IDS`.
- Никаких автоповторов заказа при сетевой ошибке (номер мог уже быть выдан).

## Структура

```
bot.py              — весь код
requirements.txt
.env.example
.gitignore
README.md
```
