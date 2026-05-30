# vless-vpn-sell

Telegram-бот для продажи VLESS VPN с оплатой через CryptoBot и автоматической выдачей ключей через HTTP API.

API-сервер VPN: https://github.com/h1gurodev/h1cloud-vless

## Возможности

- Покупка VPN через Telegram.
- Оплата через Crypto Pay API.
- Автоматическое создание и продление VLESS-клиента.
- Выдача ссылки-подписки, WS+TLS и Reality ключей.
- Telegram-админка через `/admin`.
- Статистика пользователей, инвойсов и продаж.
- Ручная выдача/продление VPN пользователю.
- Удаление VPN-ключа.
- Рассылка по пользователям.
- Проверка состояния VPN API и Crypto Pay.

## Стек

- Python 3.11+
- aiogram 3
- aiocryptopay
- aiohttp
- SQLite

## Установка

```bash
git clone https://github.com/h1gurodev/vless-vpn-sell.git
cd vless-vpn-sell
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python bot.py
```

На Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python bot.py
```

## Настройка `.env`

| Переменная | Описание |
| --- | --- |
| `BOT_TOKEN` | токен Telegram-бота от @BotFather |
| `CRYPTO_PAY_TOKEN` | токен Crypto Pay из @CryptoBot |
| `CRYPTO_PAY_TESTNET` | `true` для тестовой сети @CryptoTestnetBot |
| `VPN_API_URL` | базовый URL VPN API, например `https://example.com/api` |
| `VPN_API_TOKEN` | Bearer-токен VPN API |
| `PRICE_7D`, `PRICE_1M`, `PRICE_3M` | цены тарифов |
| `CURRENCY` | валюта CryptoBot, например `USDT`, `TON`, `BTC` |
| `ADMIN_IDS` | Telegram ID админов через запятую |
| `DB_PATH` | путь к SQLite базе, по умолчанию `bot.db` |

## Команды

- `/start` - главное меню пользователя.
- `/admin` - Telegram-админка, только для `ADMIN_IDS`.
- `/stats` - быстрая статистика, только для админов.
- `/payinvoice <invoice_id>` - тестовая ручная выдача по инвойсу, только для админов.

## Админка

В `/admin` доступны:

- общая статистика;
- список последних пользователей;
- карточка пользователя;
- быстрые кнопки `+7`, `+30`, `+90` дней;
- ручная выдача произвольного количества дней;
- удаление VPN-ключа;
- последние инвойсы;
- поиск пользователя по Telegram ID;
- рассылка;
- проверка VPN API и Crypto Pay.

## VPN API

Бот ожидает HTTP API со следующими методами:

- `POST /create` с телом `{ "name": "...", "days": 30 }` - создать клиента;
- `PATCH /edit` с телом `{ "name": "...", "days": 30 }` - продлить клиента;
- `GET /info?name=...` - получить данные клиента;
- `GET /clients` - получить список клиентов;
- `DELETE /clients/<name>` - удалить клиента.

Ответ `GET /info` должен содержать:

- `subscription_url`;
- `links.ws`;
- `links.reality`;
- `expires_at`;
- `left_days`.

## Безопасность

Не загружайте в GitHub:

- `.env`;
- `bot.db`;
- `.venv`;
- `__pycache__`;
- любые токены и реальные базы.

Эти файлы уже закрыты в `.gitignore`.

## Лицензия

MIT
