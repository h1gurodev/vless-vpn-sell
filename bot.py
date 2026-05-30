import asyncio
import logging
import secrets
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiocryptopay import AioCryptoPay, Networks

import db
import vpn_api
from config import (
    ADMIN_IDS,
    BOT_TOKEN,
    CRYPTO_PAY_TESTNET,
    CRYPTO_PAY_TOKEN,
    CURRENCY,
    PLANS,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("vpnbot")

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
crypto = AioCryptoPay(
    token=CRYPTO_PAY_TOKEN,
    network=Networks.TEST_NET if CRYPTO_PAY_TESTNET else Networks.MAIN_NET,
)


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Купить VPN", callback_data="buy")],
        [InlineKeyboardButton(text="Мой ключ", callback_data="my")],
        [InlineKeyboardButton(text="Помощь", callback_data="help")],
    ])


def plans_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=f"{p['title']} — {p['price']} {CURRENCY}",
            callback_data=f"plan:{key}",
        )]
        for key, p in PLANS.items()
    ]
    rows.append([InlineKeyboardButton(text="Назад", callback_data="back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def invoice_kb(pay_url: str, invoice_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оплатить", url=pay_url)],
        [InlineKeyboardButton(text="Я оплатил", callback_data=f"check:{invoice_id}")],
        [InlineKeyboardButton(text="Отменить", callback_data=f"cancel:{invoice_id}")],
    ])


def fmt_expires(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%d.%m.%Y %H:%M UTC")


def gen_vpn_name(user_id: int) -> str:
    return f"tg{user_id}{secrets.token_hex(2)}"


def render_client(name: str, client: dict, title: str) -> str:
    sub = client.get("subscription_url")
    links = client.get("links") or {}
    ws_link = links.get("ws") or client.get("link") or "—"
    reality_link = links.get("reality")
    left = client.get("left_days", "?")
    exp = client.get("expires_at")

    lines = [
        f"<b>{title}</b>",
        "",
        f"Имя: <code>{name}</code>",
        f"Осталось дней: <b>{left}</b>",
        f"Истекает: {fmt_expires(exp) if exp else '—'}",
        "",
    ]
    if sub:
        lines += [f"<b>Подписка:</b>", f"<code>{sub}</code>", ""]
    lines += [f"<b>VLESS WS+TLS:</b>", f"<code>{ws_link}</code>"]
    if reality_link:
        lines += ["", f"<b>VLESS Reality:</b>", f"<code>{reality_link}</code>"]
    return "\n".join(lines)


@dp.message(CommandStart())
async def cmd_start(m: Message) -> None:
    await m.answer(
        "<b>Добро пожаловать!</b>\n\n"
        "Покупка VPN с оплатой криптовалютой через CryptoBot.\n\n"
        "Выберите действие:",
        reply_markup=main_menu(),
    )


@dp.callback_query(F.data == "back")
async def cb_back(c: CallbackQuery) -> None:
    await c.message.edit_text("Главное меню:", reply_markup=main_menu())
    await c.answer()


@dp.callback_query(F.data == "help")
async def cb_help(c: CallbackQuery) -> None:
    await c.message.edit_text(
        "<b>Как это работает</b>\n\n"
        "1. Нажмите «Купить VPN» и выберите тариф.\n"
        "2. Оплатите счёт в CryptoBot.\n"
        "3. Получите ссылку-подписку для подключения.\n\n"
        "Клиенты: v2rayNG (Android), Streisand / FoXray (iOS), Nekoray / v2rayN (Windows/Linux/Mac).\n\n"
        "Повторная покупка добавляет дни к существующему ключу.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Назад", callback_data="back")]
        ]),
    )
    await c.answer()


@dp.callback_query(F.data == "buy")
async def cb_buy(c: CallbackQuery) -> None:
    await c.message.edit_text("Выберите тариф:", reply_markup=plans_kb())
    await c.answer()


@dp.callback_query(F.data == "my")
async def cb_my(c: CallbackQuery) -> None:
    name = db.get_vpn_name(c.from_user.id)
    if not name:
        await c.answer("У вас ещё нет ключа", show_alert=True)
        return
    try:
        data = await vpn_api.get_client(name)
    except vpn_api.VPNAPIError as e:
        await c.answer(f"Ошибка: {e}", show_alert=True)
        return
    text = render_client(name, data.get("client") or data, title="Ваш VPN")
    await c.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Продлить", callback_data="buy")],
        [InlineKeyboardButton(text="Назад", callback_data="back")],
    ]))
    await c.answer()


@dp.callback_query(F.data.startswith("plan:"))
async def cb_plan(c: CallbackQuery) -> None:
    key = c.data.split(":", 1)[1]
    plan = PLANS.get(key)
    if not plan:
        await c.answer("Неизвестный тариф", show_alert=True)
        return

    try:
        invoice = await crypto.create_invoice(
            asset=CURRENCY,
            amount=plan["price"],
            description=f"VPN {plan['title']} для @{c.from_user.username or c.from_user.id}",
            payload=f"{c.from_user.id}:{key}",
            expires_in=1800,
        )
    except Exception as e:
        log.exception("create_invoice failed")
        await c.answer(f"Ошибка создания счёта: {e}", show_alert=True)
        return

    db.save_invoice(
        invoice_id=invoice.invoice_id,
        user_id=c.from_user.id,
        plan=key,
        days=plan["days"],
        amount=str(plan["price"]),
        asset=CURRENCY,
    )

    await c.message.edit_text(
        f"<b>Счёт создан</b>\n\n"
        f"Тариф: <b>{plan['title']}</b>\n"
        f"Сумма: <b>{plan['price']} {CURRENCY}</b>\n"
        f"Срок действия счёта: 30 минут\n\n"
        f"После оплаты нажмите «Я оплатил».",
        reply_markup=invoice_kb(invoice.bot_invoice_url, invoice.invoice_id),
    )
    await c.answer()


@dp.callback_query(F.data.startswith("check:"))
async def cb_check(c: CallbackQuery) -> None:
    invoice_id = int(c.data.split(":", 1)[1])
    inv = db.get_invoice(invoice_id)
    if not inv or inv["user_id"] != c.from_user.id:
        await c.answer("Счёт не найден", show_alert=True)
        return
    if inv["status"] == "paid":
        await c.answer("Уже оплачено", show_alert=True)
        return

    try:
        invoices = await crypto.get_invoices(invoice_ids=[invoice_id])
    except Exception as e:
        await c.answer(f"Ошибка: {e}", show_alert=True)
        return

    invoice = invoices[0] if isinstance(invoices, list) else invoices
    if invoice.status != "paid":
        await c.answer("Оплата ещё не поступила. Попробуйте позже.", show_alert=True)
        return

    await deliver(c.from_user.id, invoice_id, c.message)
    await c.answer("Оплата получена")


@dp.callback_query(F.data.startswith("cancel:"))
async def cb_cancel(c: CallbackQuery) -> None:
    await c.message.edit_text("Счёт отменён.", reply_markup=main_menu())
    await c.answer()


async def deliver(user_id: int, invoice_id: int, message: Message | None = None) -> None:
    inv = db.mark_invoice_paid(invoice_id)
    if not inv:
        return

    days = inv["days"]
    name = db.get_vpn_name(user_id)

    try:
        if name:
            await vpn_api.extend_client(name, days)
        else:
            name = gen_vpn_name(user_id)
            await vpn_api.create_client(name, days)
            db.set_vpn_name(user_id, name)
        data = await vpn_api.get_client(name)
    except vpn_api.VPNAPIError as e:
        log.error("vpn provisioning failed for user %s: %s", user_id, e)
        await bot.send_message(
            user_id,
            f"Оплата получена, но при выдаче ключа произошла ошибка: <code>{e}</code>\n"
            "Свяжитесь с поддержкой.",
        )
        return

    text = render_client(name, data.get("client") or data, title="Ключ активирован")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="В меню", callback_data="back")]
    ])
    if message:
        try:
            await message.edit_text(text, reply_markup=kb)
            return
        except Exception:
            pass
    await bot.send_message(user_id, text, reply_markup=kb)


async def poll_invoices() -> None:
    while True:
        try:
            invoices = await crypto.get_invoices(status="paid", count=100)
            for inv in invoices or []:
                row = db.get_invoice(inv.invoice_id)
                if row and row["status"] == "active":
                    await deliver(row["user_id"], inv.invoice_id)
        except Exception:
            log.exception("poll_invoices error")
        await asyncio.sleep(20)


@dp.message(Command("payinvoice"))
async def cmd_payinvoice(m: Message) -> None:
    args = (m.text or "").split()[1:]
    invoice_id: int | None = None
    if args:
        try:
            invoice_id = int(args[0])
        except ValueError:
            await m.answer("Использование: /payinvoice [invoice_id]")
            return

    rows = db.active_invoices(
        user_id=None if invoice_id else m.from_user.id,
        invoice_id=invoice_id,
    )
    if invoice_id and rows and rows[0]["user_id"] != m.from_user.id and m.from_user.id not in ADMIN_IDS:
        await m.answer("Это не ваш инвойс.")
        return

    if not rows:
        await m.answer("Активных инвойсов нет.")
        return

    await m.answer(f"Помечаю {len(rows)} инвойс(ов) как оплаченные.")
    for row in rows:
        await deliver(row["user_id"], row["invoice_id"])


@dp.message(Command("stats"))
async def cmd_stats(m: Message) -> None:
    if m.from_user.id not in ADMIN_IDS:
        return
    try:
        data = await vpn_api.list_clients()
    except vpn_api.VPNAPIError as e:
        await m.answer(f"Ошибка: {e}")
        return
    await m.answer(f"Активных клиентов: <b>{len(data.get('clients', []))}</b>")


async def main() -> None:
    if not BOT_TOKEN or not CRYPTO_PAY_TOKEN:
        raise SystemExit("Заполните BOT_TOKEN и CRYPTO_PAY_TOKEN в .env")
    db.init()
    asyncio.create_task(poll_invoices())
    log.info("bot started")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await crypto.close()


if __name__ == "__main__":
    asyncio.run(main())
