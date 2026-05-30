# vpn-sell-bot

FOR API https://github.com/h1gurodev/h1cloud-vless

FOR API https://github.com/h1gurodev/h1cloud-vless

FOR API https://github.com/h1gurodev/h1cloud-vless

FOR API https://github.com/h1gurodev/h1cloud-vless


FOR API https://github.com/h1gurodev/h1cloud-vless
Telegram-бот для продажи доступа к VLESS VPN. Оплата через CryptoBot (Crypto Pay API).
FOR API https://github.com/h1gurodev/h1cloud-vless
## Стек

- Python 3.11+
- aiogram 3
- aiocryptopay
- SQLite

## Тарифы

7 дней / 1 месяц / 3 месяца. Цены и валюта настраиваются в `.env`.

## Установка

```bash
git clone <repo>
cd vpn-sell-bot
pip install -r requirements.txt
cp .env.example .env
# заполнить .env
python bot.py
```

## .env

| Переменная | Описание |
|------------|----------|
| `BOT_TOKEN` | токен от @BotFather |
| `CRYPTO_PAY_TOKEN` | токен Crypto Pay из @CryptoBot |
| `CRYPTO_PAY_TESTNET` | `true` для тестовой сети (@CryptoTestnetBot) |
| `VPN_API_URL` | базовый URL HTTP API VPN-сервера, оканчивается на `/api` |
| `VPN_API_TOKEN` | токен VPN API |
| `PRICE_7D`, `PRICE_1M`, `PRICE_3M` | цены за тарифы |
| `CURRENCY` | актив CryptoBot: `USDT`, `TON`, `BTC` и т.д. |
| `ADMIN_IDS` | Telegram ID админов через запятую |

## Команды

- `/start` — главное меню
- `/payinvoice [invoice_id]` — пометить активный счёт оплаченным (для тестов выдачи)
- `/stats` — количество активных клиентов VPN (только админы)

## VPN API

Бот ожидает HTTP API со следующими методами:

- `POST /create` `{name, days}` — создать клиента
- `PATCH /edit` `{name, days}` — продлить
- `GET /info?name=...` — данные клиента
- `GET /clients` — список клиентов
- `DELETE /clients/<name>` — удалить

Ответ `GET /info` должен содержать поля `subscription_url`, `links.ws`, `links.reality`, `expires_at`, `left_days`.

## Лицензия

MIT
