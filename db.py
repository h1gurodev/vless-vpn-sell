import sqlite3
from contextlib import contextmanager
from config import DB_PATH


def init() -> None:
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id    INTEGER PRIMARY KEY,
                vpn_name   TEXT UNIQUE,
                created_at INTEGER DEFAULT (strftime('%s','now'))
            );
            CREATE TABLE IF NOT EXISTS invoices (
                invoice_id INTEGER PRIMARY KEY,
                user_id    INTEGER NOT NULL,
                plan       TEXT NOT NULL,
                days       INTEGER NOT NULL,
                amount     TEXT NOT NULL,
                asset      TEXT NOT NULL,
                status     TEXT NOT NULL DEFAULT 'active',
                created_at INTEGER DEFAULT (strftime('%s','now'))
            );
            """
        )


@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def get_vpn_name(user_id: int) -> str | None:
    with _conn() as c:
        row = c.execute("SELECT vpn_name FROM users WHERE user_id=?", (user_id,)).fetchone()
        return row["vpn_name"] if row else None


def set_vpn_name(user_id: int, vpn_name: str) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO users(user_id, vpn_name) VALUES(?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET vpn_name=excluded.vpn_name",
            (user_id, vpn_name),
        )


def save_invoice(invoice_id: int, user_id: int, plan: str, days: int, amount: str, asset: str) -> None:
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO invoices(invoice_id,user_id,plan,days,amount,asset,status) "
            "VALUES(?,?,?,?,?,?, 'active')",
            (invoice_id, user_id, plan, days, amount, asset),
        )


def mark_invoice_paid(invoice_id: int) -> dict | None:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM invoices WHERE invoice_id=? AND status='active'", (invoice_id,)
        ).fetchone()
        if not row:
            return None
        c.execute("UPDATE invoices SET status='paid' WHERE invoice_id=?", (invoice_id,))
        return dict(row)


def get_invoice(invoice_id: int) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM invoices WHERE invoice_id=?", (invoice_id,)).fetchone()
        return dict(row) if row else None


def active_invoices(user_id: int | None = None, invoice_id: int | None = None) -> list[dict]:
    with _conn() as c:
        if invoice_id is not None:
            rows = c.execute(
                "SELECT * FROM invoices WHERE invoice_id=? AND status='active'",
                (invoice_id,),
            ).fetchall()
        elif user_id is not None:
            rows = c.execute(
                "SELECT * FROM invoices WHERE user_id=? AND status='active' "
                "ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM invoices WHERE status='active' ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]
