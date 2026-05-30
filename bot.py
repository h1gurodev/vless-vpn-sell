import asyncio
import logging
import secrets
from datetime import datetime, timezone
from html import escape
from typing import Any

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

admin_states: dict[int, dict[str, Any]] = {}


def h(value: Any) -> str:
    return escape("" if value is None else str(value), quote=False)


def is_admin(user_id: int | None) -> bool:
    return bool(user_id and user_id in ADMIN_IDS)


def touch_user(tg_user: Any) -> None:
    if not tg_user:
        return
    db.register_user(
        user_id=tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name,
        last_name=tg_user.last_name,
    )


def fmt_amount(value: Any) -> str:
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return h(value)


def fmt_ts(ts: Any) -> str:
    if not ts:
        return "-"
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    except (TypeError, ValueError, OSError):
        return "-"


def fmt_expires(ts: int) -> str:
    return fmt_ts(ts)


def gen_vpn_name(user_id: int) -> str:
    return f"tg{user_id}{secrets.token_hex(2)}"


def status_title(status: str) -> str:
    return {
        "active": "ожидает оплаты",
        "paid": "оплачен",
        "canceled": "отменён",
    }.get(status, status)


def user_label(user: dict) -> str:
    return h(user_plain_label(user))


def user_plain_label(user: dict) -> str:
    username = user.get("username")
    if username:
        return f"@{username}"
    name = " ".join(part for part in [user.get("first_name"), user.get("last_name")] if part)
    return name if name else f"ID {user.get('user_id')}"


def main_menu(user_id: int | None = None) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="Купить VPN", callback_data="buy")],
        [InlineKeyboardButton(text="Мой ключ", callback_data="my")],
        [InlineKeyboardButton(text="Помощь", callback_data="help")],
    ]
    if is_admin(user_id):
        rows.append([InlineKeyboardButton(text="Админка", callback_data="adm:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def plans_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=f"{p['title']} - {fmt_amount(p['price'])} {CURRENCY}",
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


def client_kb(user_id: int | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Продлить", callback_data="buy")],
        [InlineKeyboardButton(text="Инструкция", callback_data="help")],
        [InlineKeyboardButton(text="Назад", callback_data="back")],
    ])


def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Статистика", callback_data="adm:stats")],
        [
            InlineKeyboardButton(text="Пользователи", callback_data="adm:users"),
            InlineKeyboardButton(text="Инвойсы", callback_data="adm:invoices"),
        ],
        [
            InlineKeyboardButton(text="Найти ID", callback_data="adm:find"),
            InlineKeyboardButton(text="Проверка API", callback_data="adm:health"),
        ],
        [InlineKeyboardButton(text="Рассылка", callback_data="adm:broadcast")],
        [InlineKeyboardButton(text="В меню бота", callback_data="back")],
    ])


def admin_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад в админку", callback_data="adm:home")]
    ])


def admin_user_kb(user_id: int, has_vpn: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="+7 дней", callback_data=f"adm:add:{user_id}:7"),
            InlineKeyboardButton(text="+30 дней", callback_data=f"adm:add:{user_id}:30"),
            InlineKeyboardButton(text="+90 дней", callback_data=f"adm:add:{user_id}:90"),
        ],
        [InlineKeyboardButton(text="Другой срок", callback_data=f"adm:extend:{user_id}")],
    ]
    if has_vpn:
        rows.append([InlineKeyboardButton(text="Удалить ключ", callback_data=f"adm:delete:{user_id}")])
    rows.append([InlineKeyboardButton(text="К пользователям", callback_data="adm:users")])
    rows.append([InlineKeyboardButton(text="В админку", callback_data="adm:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def render_client(name: str, client: dict, title: str) -> str:
    sub = client.get("subscription_url")
    links = client.get("links") or {}
    ws_link = links.get("ws") or client.get("link") or "-"
    reality_link = links.get("reality")
    left = client.get("left_days", "?")
    exp = client.get("expires_at")

    lines = [
        f"<b>{h(title)}</b>",
        "",
        f"Имя: <code>{h(name)}</code>",
        f"Осталось дней: <b>{h(left)}</b>",
        f"Истекает: {fmt_expires(exp) if exp else '-'}",
        "",
    ]
    if sub:
        lines += ["<b>Подписка:</b>", f"<code>{h(sub)}</code>", ""]
    lines += ["<b>VLESS WS+TLS:</b>", f"<code>{h(ws_link)}</code>"]
    if reality_link:
        lines += ["", "<b>VLESS Reality:</b>", f"<code>{h(reality_link)}</code>"]
    return "\n".join(lines)


async def show_panel(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    edit: bool = True,
) -> None:
    if edit:
        try:
            await message.edit_text(text, reply_markup=reply_markup)
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=reply_markup)


async def notify_admins(text: str) -> None:
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            log.exception("failed to notify admin %s", admin_id)


def render_admin_home() -> str:
    return (
        "<b>Админка</b>\n\n"
        "Здесь можно смотреть продажи, управлять пользователями, вручную выдавать дни, "
        "удалять ключи и делать рассылки."
    )


async def render_admin_stats() -> str:
    stats = db.dashboard_stats()
    users = stats["users"]
    invoices = stats["invoices"]
    sales = stats["sales"]

    try:
        vpn_data = await vpn_api.list_clients()
        vpn_line = f"VPN-клиентов в API: <b>{len(vpn_data.get('clients', []))}</b>"
    except vpn_api.VPNAPIError as e:
        vpn_line = f"VPN API: <code>{h(e)}</code>"

    sales_line = "Нет оплаченных счетов"
    if sales:
        sales_line = ", ".join(
            f"<b>{fmt_amount(row.get('total') or 0)} {h(row.get('asset'))}</b> ({row.get('count')})"
            for row in sales
        )

    return "\n".join([
        "<b>Статистика</b>",
        "",
        f"Пользователей: <b>{users.get('total') or 0}</b>",
        f"С VPN-ключом: <b>{users.get('with_vpn') or 0}</b>",
        "",
        f"Инвойсов всего: <b>{invoices.get('total') or 0}</b>",
        f"Ожидают оплаты: <b>{invoices.get('active') or 0}</b>",
        f"Оплачены: <b>{invoices.get('paid') or 0}</b>",
        f"Отменены: <b>{invoices.get('canceled') or 0}</b>",
        "",
        f"Продажи: {sales_line}",
        vpn_line,
    ])


def render_recent_users() -> tuple[str, InlineKeyboardMarkup]:
    users = db.recent_users(limit=10)
    if not users:
        text = "<b>Пользователи</b>\n\nПока никто не запускал бота."
        return text, InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Назад в админку", callback_data="adm:home")]
        ])

    lines = ["<b>Последние пользователи</b>", ""]
    rows: list[list[InlineKeyboardButton]] = []
    for user in users:
        uid = int(user["user_id"])
        vpn_mark = "есть VPN" if user.get("vpn_name") else "без VPN"
        paid = user.get("paid_count") or 0
        lines.append(f"{user_label(user)} - <code>{uid}</code>, {vpn_mark}, оплат: <b>{paid}</b>")
        rows.append([InlineKeyboardButton(text=f"{user_plain_label(user)} / {uid}", callback_data=f"adm:user:{uid}")])

    rows.append([InlineKeyboardButton(text="Найти по ID", callback_data="adm:find")])
    rows.append([InlineKeyboardButton(text="Назад в админку", callback_data="adm:home")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


def render_recent_invoices() -> str:
    rows = db.recent_invoices(limit=10)
    if not rows:
        return "<b>Инвойсы</b>\n\nСчетов пока нет."

    lines = ["<b>Последние инвойсы</b>", ""]
    for row in rows:
        user = user_label(row)
        lines.append(
            f"#{h(row['invoice_id'])} - <b>{status_title(row['status'])}</b>\n"
            f"{user}, {h(row['plan'])}, {fmt_amount(row['amount'])} {h(row['asset'])}, "
            f"{fmt_ts(row['created_at'])}"
        )
        lines.append("")
    return "\n".join(lines).strip()


async def render_admin_user(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    user = db.get_user(user_id)
    if not user:
        return (
            f"<b>Пользователь не найден</b>\n\nID <code>{h(user_id)}</code> не запускал бота.",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Найти другой ID", callback_data="adm:find")],
                [InlineKeyboardButton(text="К пользователям", callback_data="adm:users")],
            ]),
        )

    stats = db.user_invoice_stats(user_id)
    invoices = db.recent_invoices(limit=5, user_id=user_id)
    vpn_name = user.get("vpn_name")
    vpn_lines = [f"VPN: <code>{h(vpn_name)}</code>" if vpn_name else "VPN: нет ключа"]

    if vpn_name:
        try:
            data = await vpn_api.get_client(vpn_name)
            client = data.get("client") or data
            vpn_lines.append(f"Осталось дней: <b>{h(client.get('left_days', '?'))}</b>")
            vpn_lines.append(f"Истекает: {fmt_expires(client.get('expires_at')) if client.get('expires_at') else '-'}")
        except vpn_api.VPNAPIError as e:
            vpn_lines.append(f"VPN API: <code>{h(e)}</code>")

    invoice_lines = ["Последние счета: нет"]
    if invoices:
        invoice_lines = ["Последние счета:"]
        for inv in invoices:
            invoice_lines.append(
                f"#{h(inv['invoice_id'])} - {status_title(inv['status'])}, "
                f"{fmt_amount(inv['amount'])} {h(inv['asset'])}, {fmt_ts(inv['created_at'])}"
            )

    lines = [
        "<b>Пользователь</b>",
        "",
        f"ID: <code>{h(user_id)}</code>",
        f"Username: {('@' + h(user['username'])) if user.get('username') else '-'}",
        f"Имя: {h(' '.join(part for part in [user.get('first_name'), user.get('last_name')] if part)) or '-'}",
        f"Первый запуск: {fmt_ts(user.get('created_at'))}",
        f"Последний визит: {fmt_ts(user.get('last_seen'))}",
        "",
        *vpn_lines,
        "",
        f"Инвойсы: всего <b>{stats.get('total') or 0}</b>, "
        f"оплачено <b>{stats.get('paid') or 0}</b>, "
        f"активно <b>{stats.get('active') or 0}</b>",
        "",
        *invoice_lines,
    ]
    return "\n".join(lines), admin_user_kb(user_id, bool(vpn_name))


async def render_health() -> str:
    lines = ["<b>Проверка системы</b>", "", "База данных: работает"]

    try:
        data = await vpn_api.list_clients()
        lines.append(f"VPN API: работает, клиентов: <b>{len(data.get('clients', []))}</b>")
    except vpn_api.VPNAPIError as e:
        lines.append(f"VPN API: ошибка - <code>{h(e)}</code>")

    try:
        await crypto.get_invoices(count=1)
        network = "testnet" if CRYPTO_PAY_TESTNET else "mainnet"
        lines.append(f"Crypto Pay: работает ({network})")
    except Exception as e:
        lines.append(f"Crypto Pay: ошибка - <code>{h(e)}</code>")

    return "\n".join(lines)


async def admin_grant_days(user_id: int, days: int) -> str:
    user = db.get_user(user_id)
    if not user:
        return f"Пользователь <code>{h(user_id)}</code> не найден в базе."

    name = user.get("vpn_name")
    created = False
    try:
        if name:
            await vpn_api.extend_client(name, days)
        else:
            name = gen_vpn_name(user_id)
            await vpn_api.create_client(name, days)
            db.set_vpn_name(user_id, name)
            created = True
        data = await vpn_api.get_client(name)
    except vpn_api.VPNAPIError as e:
        return f"Не удалось выдать дни пользователю <code>{h(user_id)}</code>: <code>{h(e)}</code>"

    title = "VPN выдан администратором" if created else "VPN продлён администратором"
    client_text = render_client(name, data.get("client") or data, title=title)
    try:
        await bot.send_message(user_id, client_text, reply_markup=client_kb(user_id))
        send_line = "Пользователь получил сообщение."
    except Exception as e:
        log.warning("failed to send manual grant to %s: %s", user_id, e)
        send_line = "Ключ создан, но сообщение пользователю отправить не удалось."

    return f"{client_text}\n\n<b>Админ-действие:</b> +{days} дней. {send_line}"


async def admin_delete_key(user_id: int) -> str:
    user = db.get_user(user_id)
    if not user:
        return f"Пользователь <code>{h(user_id)}</code> не найден."

    name = user.get("vpn_name")
    if not name:
        return "У пользователя нет VPN-ключа."

    try:
        await vpn_api.delete_client(name)
    except vpn_api.VPNAPIError as e:
        return f"Не удалось удалить ключ <code>{h(name)}</code>: <code>{h(e)}</code>"

    db.clear_vpn_name(user_id)
    try:
        await bot.send_message(user_id, "Ваш VPN-ключ удалён администратором.")
    except Exception:
        pass
    return f"Ключ <code>{h(name)}</code> удалён у пользователя <code>{h(user_id)}</code>."


@dp.message(CommandStart())
async def cmd_start(m: Message) -> None:
    touch_user(m.from_user)
    await m.answer(
        "<b>VLESS VPN</b>\n\n"
        "Быстрая покупка VPN с оплатой через CryptoBot. После оплаты бот сразу выдаст "
        "ссылку-подписку и VLESS-ключи.\n\n"
        "Выберите действие:",
        reply_markup=main_menu(m.from_user.id),
    )


@dp.message(Command("admin"))
async def cmd_admin(m: Message) -> None:
    touch_user(m.from_user)
    if not is_admin(m.from_user.id):
        return
    await m.answer(render_admin_home(), reply_markup=admin_menu_kb())


@dp.callback_query(F.data == "back")
async def cb_back(c: CallbackQuery) -> None:
    touch_user(c.from_user)
    await c.message.edit_text("Главное меню:", reply_markup=main_menu(c.from_user.id))
    await c.answer()


@dp.callback_query(F.data == "help")
async def cb_help(c: CallbackQuery) -> None:
    touch_user(c.from_user)
    await c.message.edit_text(
        "<b>Как подключиться</b>\n\n"
        "1. Нажмите «Купить VPN» и выберите тариф.\n"
        "2. Оплатите счёт в CryptoBot.\n"
        "3. Откройте ссылку-подписку в приложении для VLESS.\n\n"
        "<b>Приложения</b>\n"
        "Android: v2rayNG\n"
        "iOS: Streisand или FoXray\n"
        "Windows/Linux/Mac: v2rayN или Nekoray\n\n"
        "Повторная покупка добавляет дни к существующему ключу.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Купить VPN", callback_data="buy")],
            [InlineKeyboardButton(text="Назад", callback_data="back")],
        ]),
    )
    await c.answer()


@dp.callback_query(F.data == "buy")
async def cb_buy(c: CallbackQuery) -> None:
    touch_user(c.from_user)
    await c.message.edit_text(
        "<b>Выберите тариф</b>\n\n"
        "После оплаты ключ будет создан автоматически. Если ключ уже есть, дни добавятся к нему.",
        reply_markup=plans_kb(),
    )
    await c.answer()


@dp.callback_query(F.data == "my")
async def cb_my(c: CallbackQuery) -> None:
    touch_user(c.from_user)
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
    await c.message.edit_text(text, reply_markup=client_kb(c.from_user.id))
    await c.answer()


@dp.callback_query(F.data.startswith("plan:"))
async def cb_plan(c: CallbackQuery) -> None:
    touch_user(c.from_user)
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
        f"Тариф: <b>{h(plan['title'])}</b>\n"
        f"Сумма: <b>{fmt_amount(plan['price'])} {CURRENCY}</b>\n"
        f"Срок действия счёта: 30 минут\n\n"
        f"После оплаты нажмите «Я оплатил». Бот также проверяет оплаты автоматически.",
        reply_markup=invoice_kb(invoice.bot_invoice_url, invoice.invoice_id),
    )
    await c.answer()


@dp.callback_query(F.data.startswith("check:"))
async def cb_check(c: CallbackQuery) -> None:
    touch_user(c.from_user)
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
    touch_user(c.from_user)
    invoice_id = int(c.data.split(":", 1)[1])
    db.cancel_invoice(invoice_id, c.from_user.id)
    await c.message.edit_text(
        "Счёт закрыт в боте. Если вы уже оплатили его, бот всё равно увидит оплату и выдаст ключ.",
        reply_markup=main_menu(c.from_user.id),
    )
    await c.answer()


@dp.callback_query(F.data.startswith("adm:"))
async def cb_admin(c: CallbackQuery) -> None:
    touch_user(c.from_user)
    if not is_admin(c.from_user.id):
        await c.answer("Нет доступа", show_alert=True)
        return

    parts = c.data.split(":")
    action = parts[1]

    if action == "home":
        admin_states.pop(c.from_user.id, None)
        await show_panel(c.message, render_admin_home(), admin_menu_kb())
    elif action == "stats":
        await show_panel(c.message, await render_admin_stats(), admin_back_kb())
    elif action == "users":
        text, kb = render_recent_users()
        await show_panel(c.message, text, kb)
    elif action == "invoices":
        await show_panel(c.message, render_recent_invoices(), admin_back_kb())
    elif action == "health":
        await show_panel(c.message, await render_health(), admin_back_kb())
    elif action == "find":
        admin_states[c.from_user.id] = {"action": "find_user"}
        await show_panel(
            c.message,
            "<b>Поиск пользователя</b>\n\nОтправьте Telegram ID пользователя одним сообщением.",
            admin_back_kb(),
        )
    elif action == "user" and len(parts) >= 3:
        text, kb = await render_admin_user(int(parts[2]))
        await show_panel(c.message, text, kb)
    elif action == "add" and len(parts) >= 4:
        user_id = int(parts[2])
        days = int(parts[3])
        await c.answer("Выдаю дни...")
        text = await admin_grant_days(user_id, days)
        await show_panel(c.message, text, InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Открыть пользователя", callback_data=f"adm:user:{user_id}")],
            [InlineKeyboardButton(text="В админку", callback_data="adm:home")],
        ]))
        return
    elif action == "extend" and len(parts) >= 3:
        user_id = int(parts[2])
        admin_states[c.from_user.id] = {"action": "extend_user", "user_id": user_id}
        await show_panel(
            c.message,
            f"<b>Ручное продление</b>\n\nОтправьте количество дней для пользователя <code>{h(user_id)}</code>.",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Отмена", callback_data=f"adm:user:{user_id}")]
            ]),
        )
    elif action == "delete" and len(parts) >= 3:
        user_id = int(parts[2])
        await show_panel(
            c.message,
            f"<b>Удалить VPN-ключ?</b>\n\nПользователь: <code>{h(user_id)}</code>",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Да, удалить", callback_data=f"adm:delete_confirm:{user_id}")],
                [InlineKeyboardButton(text="Отмена", callback_data=f"adm:user:{user_id}")],
            ]),
        )
    elif action == "delete_confirm" and len(parts) >= 3:
        user_id = int(parts[2])
        text = await admin_delete_key(user_id)
        await show_panel(c.message, text, InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Открыть пользователя", callback_data=f"adm:user:{user_id}")],
            [InlineKeyboardButton(text="В админку", callback_data="adm:home")],
        ]))
    elif action == "broadcast":
        admin_states[c.from_user.id] = {"action": "broadcast"}
        await show_panel(
            c.message,
            "<b>Рассылка</b>\n\nОтправьте текст, который нужно разослать всем пользователям.",
            admin_back_kb(),
        )
    elif action == "broadcast_confirm":
        state = admin_states.pop(c.from_user.id, None)
        if not state or state.get("action") != "broadcast_confirm":
            await c.answer("Текст рассылки не найден", show_alert=True)
            return
        await c.answer("Рассылка запущена")
        text = state["text"]
        ok = 0
        failed = 0
        for user_id in db.all_user_ids():
            try:
                await bot.send_message(user_id, h(text))
                ok += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.04)
        await show_panel(
            c.message,
            f"<b>Рассылка завершена</b>\n\nУспешно: <b>{ok}</b>\nОшибок: <b>{failed}</b>",
            admin_back_kb(),
        )
        return
    elif action == "broadcast_cancel":
        admin_states.pop(c.from_user.id, None)
        await show_panel(c.message, render_admin_home(), admin_menu_kb())
    else:
        await c.answer("Неизвестное действие", show_alert=True)
        return

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
            f"Оплата получена, но при выдаче ключа произошла ошибка: <code>{h(e)}</code>\n"
            "Администратор уже получил уведомление.",
        )
        await notify_admins(
            "<b>Ошибка выдачи VPN</b>\n\n"
            f"Пользователь: <code>{h(user_id)}</code>\n"
            f"Инвойс: <code>{h(invoice_id)}</code>\n"
            f"Ошибка: <code>{h(e)}</code>"
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
                if row and row["status"] in {"active", "canceled"}:
                    await deliver(row["user_id"], inv.invoice_id)
        except Exception:
            log.exception("poll_invoices error")
        await asyncio.sleep(20)


@dp.message(Command("payinvoice"))
async def cmd_payinvoice(m: Message) -> None:
    touch_user(m.from_user)
    if not is_admin(m.from_user.id):
        return

    args = (m.text or "").split()[1:]
    invoice_id: int | None = None
    if not args:
        await m.answer("Использование: /payinvoice <invoice_id>")
        return
    try:
        invoice_id = int(args[0])
    except ValueError:
        await m.answer("Использование: /payinvoice <invoice_id>")
        return

    rows = db.active_invoices(invoice_id=invoice_id)
    if not rows:
        await m.answer("Активных инвойсов нет.")
        return

    await m.answer(f"Помечаю {len(rows)} инвойс(ов) как оплаченные.")
    for row in rows:
        await deliver(row["user_id"], row["invoice_id"])


@dp.message(Command("stats"))
async def cmd_stats(m: Message) -> None:
    touch_user(m.from_user)
    if not is_admin(m.from_user.id):
        return
    await m.answer(await render_admin_stats(), reply_markup=admin_back_kb())


@dp.message(F.text)
async def admin_text_state(m: Message) -> None:
    touch_user(m.from_user)
    if not is_admin(m.from_user.id):
        return

    state = admin_states.get(m.from_user.id)
    if not state:
        return

    action = state.get("action")
    text = (m.text or "").strip()

    if action == "find_user":
        if not text.isdigit():
            await m.answer("Отправьте числовой Telegram ID.")
            return
        admin_states.pop(m.from_user.id, None)
        panel, kb = await render_admin_user(int(text))
        await show_panel(m, panel, kb, edit=False)
        return

    if action == "extend_user":
        if not text.isdigit() or not (1 <= int(text) <= 3650):
            await m.answer("Отправьте число дней от 1 до 3650.")
            return
        admin_states.pop(m.from_user.id, None)
        user_id = int(state["user_id"])
        result = await admin_grant_days(user_id, int(text))
        await m.answer(result, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Открыть пользователя", callback_data=f"adm:user:{user_id}")],
            [InlineKeyboardButton(text="В админку", callback_data="adm:home")],
        ]))
        return

    if action == "broadcast":
        if not text:
            await m.answer("Текст рассылки пустой. Отправьте сообщение с текстом.")
            return
        admin_states[m.from_user.id] = {"action": "broadcast_confirm", "text": text}
        await m.answer(
            "<b>Подтвердите рассылку</b>\n\n"
            f"Получателей: <b>{len(db.all_user_ids())}</b>\n\n"
            f"<b>Текст:</b>\n{h(text)}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Запустить", callback_data="adm:broadcast_confirm")],
                [InlineKeyboardButton(text="Отмена", callback_data="adm:broadcast_cancel")],
            ]),
        )


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
