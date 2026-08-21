# 🌸 nursery-order-bot

Telegram-бот для каталога и приёма заказов растений (питомник), плюс веб-слой: сайт и Telegram Mini App с общей базой заказов и реферальным учётом сотрудников.

## Запуск

```bash
git clone https://github.com/dlysenko-dev/nursery-order-bot
cd nursery-order-bot

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# отредактировать .env

python bot.py
```

## Веб: сайт + Mini App

```bash
# однократно: подготовить фото и описания
python scripts/prepare_web_photos.py      # фото из ../цветы -> web/static/photos
python scripts/generate_titles.py         # названия позиций
python scripts/fill_category_descriptions.py

# сервер (порт из WEB_PORT, по умолчанию 8000)
uvicorn web.app:app --port 8000
```

Сайт и Mini App — один фронтенд (`web/static/`): в Telegram включаются нативные элементы (expand, цвета), на сайте — обычная страница. Корзина — в localStorage, заказ создаётся через `POST /api/orders` и попадает в ту же админку бота (`/admin`).

Для Mini App в Telegram: задать `WEBAPP_URL` (https) и `WEBAPP_SHORT_NAME` в `.env`, зарегистрировать WebApp через @BotFather.

### Сотрудники и реферальные ссылки

Каждый сотрудник получает личные ссылки (бот / мини-ап / сайт). Клиент, пришедший по ссылке, закрепляется за сотрудником (первый источник побеждает); сотрудник видит своих клиентов и их заказы на экране «Мои клиенты» в Mini App.

```bash
python scripts/add_employee.py "Анна" --tg 123456789   # создать
python scripts/add_employee.py --list                  # список со ссылками
```

## Переменные окружения (.env)

| Переменная | Описание |
|---|---|
| `BOT_TOKEN` | Токен Telegram-бота от @BotFather |
| `ADMIN_IDS` | Telegram ID администраторов через запятую |
| `PAYMENT_REQUISITES` | Реквизиты для оплаты |
| `DELIVERY_COST` | Стоимость доставки по умолчанию (300) |
| `DATABASE_URL` | URL базы данных |
| `GOOGLE_SHEETS_ID` | ID Google таблицы |
| `GOOGLE_CREDENTIALS_FILE` | Путь к credentials.json |
| `WEBAPP_URL` | Публичный URL сайта/мини-апа (https) |
| `WEB_PORT` | Порт веб-сервера (по умолчанию 8000) |
| `BOT_USERNAME` | Username бота без @ (для реф-ссылок) |
| `WEBAPP_SHORT_NAME` | Short name мини-апа из @BotFather |
