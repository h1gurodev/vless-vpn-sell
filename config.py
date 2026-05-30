import os
from dotenv import load_dotenv

load_dotenv()


def _ids(v: str) -> set[int]:
    return {int(x) for x in v.replace(" ", "").split(",") if x}


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CRYPTO_PAY_TOKEN = os.getenv("CRYPTO_PAY_TOKEN", "").strip()
CRYPTO_PAY_TESTNET = os.getenv("CRYPTO_PAY_TESTNET", "false").lower() == "true"

VPN_API_URL = os.getenv("VPN_API_URL", "http://185.218.137.132:27018/api").rstrip("/")
VPN_API_TOKEN = os.getenv("VPN_API_TOKEN", "").strip()

CURRENCY = os.getenv("CURRENCY", "USDT").strip().upper()

PLANS = {
    "7d": {"days": 7, "title": "7 дней", "price": float(os.getenv("PRICE_7D", "1.5"))},
    "1m": {"days": 30, "title": "1 месяц", "price": float(os.getenv("PRICE_1M", "3"))},
    "3m": {"days": 90, "title": "3 месяца", "price": float(os.getenv("PRICE_3M", "5"))},
}

ADMIN_IDS = _ids(os.getenv("ADMIN_IDS", ""))

DB_PATH = os.getenv("DB_PATH", "bot.db")
