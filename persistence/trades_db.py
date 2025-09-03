import pathlib
import sqlite3

BASE_DIR = pathlib.Path(__file__).parent.parent
DB_PATH = BASE_DIR / "persistence" / "trades.db"


def init_db():
    """Initializes the database and creates the 'trades' table if it doesn't exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_iso TEXT NOT NULL,
            symbol TEXT NOT NULL,
            action TEXT NOT NULL,
            side TEXT NOT NULL,
            price REAL NOT NULL,
            qty REAL NOT NULL,
            reason TEXT,
            pnl_usdt REAL
        )
    """
    )
    con.commit()
    con.close()


def insert_trade(ts_iso, symbol, action, side, price, qty, reason, pnl_usdt):
    """Inserts a single trade record into the database."""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO trades (ts_iso, symbol, action, side, price, qty, reason, pnl_usdt)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (ts_iso, symbol, action, side, price, qty, reason, pnl_usdt),
    )
    con.commit()
    con.close()
