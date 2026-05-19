import sqlite3

from sc_gr_app.config import AppConfig


def connect(config: AppConfig) -> sqlite3.Connection:
    config.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = DELETE")
    conn.execute(f"PRAGMA busy_timeout = {config.busy_timeout_ms}")
    return conn
