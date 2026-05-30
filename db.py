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
        _ensure_columns(c, "users", {
            "username": "TEXT",
            "first_name": "TEXT",
            "last_name": "TEXT",
            "last_seen": "INTEGER",
        })
        _ensure_columns(c, "invoices", {
            "paid_at": "INTEGER",
            "canceled_at": "INTEGER",
        })


@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _ensure_columns(c: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row["name"] for row in c.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, sql_type in columns.items():
        if name not in existing:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")


def _row(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row else None


def register_user(
    user_id: int,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
) -> None:
    with _conn() as c:
        c.execute(
            """
            INSERT INTO users(user_id, username, first_name, last_name, last_seen)
            VALUES(?, ?, ?, ?, strftime('%s','now'))
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name,
                last_name=excluded.last_name,
                last_seen=strftime('%s','now')
            """,
            (user_id, username, first_name, last_name),
        )


def get_user(user_id: int) -> dict | None:
    with _conn() as c:
        return _row(c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone())


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


def clear_vpn_name(user_id: int) -> None:
    with _conn() as c:
        c.execute("UPDATE users SET vpn_name=NULL WHERE user_id=?", (user_id,))


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
            "SELECT * FROM invoices WHERE invoice_id=? AND status IN ('active', 'canceled')",
            (invoice_id,),
        ).fetchone()
        if not row:
            return None
        c.execute(
            "UPDATE invoices SET status='paid', paid_at=strftime('%s','now') WHERE invoice_id=?",
            (invoice_id,),
        )
        return dict(row)


def cancel_invoice(invoice_id: int, user_id: int | None = None) -> dict | None:
    with _conn() as c:
        if user_id is None:
            row = c.execute(
                "SELECT * FROM invoices WHERE invoice_id=? AND status='active'",
                (invoice_id,),
            ).fetchone()
        else:
            row = c.execute(
                "SELECT * FROM invoices WHERE invoice_id=? AND user_id=? AND status='active'",
                (invoice_id, user_id),
            ).fetchone()
        if not row:
            return None
        c.execute(
            "UPDATE invoices SET status='canceled', canceled_at=strftime('%s','now') "
            "WHERE invoice_id=?",
            (invoice_id,),
        )
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


def recent_users(limit: int = 10) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            """
            SELECT
                u.*,
                COUNT(i.invoice_id) AS invoices_count,
                SUM(CASE WHEN i.status='paid' THEN 1 ELSE 0 END) AS paid_count
            FROM users u
            LEFT JOIN invoices i ON i.user_id = u.user_id
            GROUP BY u.user_id
            ORDER BY COALESCE(u.last_seen, u.created_at) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def all_user_ids() -> list[int]:
    with _conn() as c:
        rows = c.execute("SELECT user_id FROM users ORDER BY created_at ASC").fetchall()
        return [int(r["user_id"]) for r in rows]


def recent_invoices(limit: int = 10, user_id: int | None = None) -> list[dict]:
    with _conn() as c:
        if user_id is None:
            rows = c.execute(
                """
                SELECT i.*, u.username, u.first_name, u.vpn_name
                FROM invoices i
                LEFT JOIN users u ON u.user_id = i.user_id
                ORDER BY i.created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = c.execute(
                """
                SELECT i.*, u.username, u.first_name, u.vpn_name
                FROM invoices i
                LEFT JOIN users u ON u.user_id = i.user_id
                WHERE i.user_id=?
                ORDER BY i.created_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]


def user_invoice_stats(user_id: int) -> dict:
    with _conn() as c:
        row = c.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) AS active,
                SUM(CASE WHEN status='paid' THEN 1 ELSE 0 END) AS paid,
                SUM(CASE WHEN status='canceled' THEN 1 ELSE 0 END) AS canceled
            FROM invoices
            WHERE user_id=?
            """,
            (user_id,),
        ).fetchone()
        return dict(row) if row else {"total": 0, "active": 0, "paid": 0, "canceled": 0}


def sales_by_asset() -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            """
            SELECT asset, COUNT(*) AS count, SUM(CAST(amount AS REAL)) AS total
            FROM invoices
            WHERE status='paid'
            GROUP BY asset
            ORDER BY total DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]


def dashboard_stats() -> dict:
    with _conn() as c:
        users = c.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN vpn_name IS NOT NULL THEN 1 ELSE 0 END) AS with_vpn
            FROM users
            """
        ).fetchone()
        invoices = c.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) AS active,
                SUM(CASE WHEN status='paid' THEN 1 ELSE 0 END) AS paid,
                SUM(CASE WHEN status='canceled' THEN 1 ELSE 0 END) AS canceled
            FROM invoices
            """
        ).fetchone()
        sales = c.execute(
            """
            SELECT asset, COUNT(*) AS count, SUM(CAST(amount AS REAL)) AS total
            FROM invoices
            WHERE status='paid'
            GROUP BY asset
            ORDER BY total DESC
            """
        ).fetchall()
        return {
            "users": dict(users),
            "invoices": dict(invoices),
            "sales": [dict(r) for r in sales],
        }
