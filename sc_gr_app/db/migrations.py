from datetime import datetime, timezone
from pathlib import Path

from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect


SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def migrate(config: AppConfig) -> None:
    schema_path = Path(__file__).with_name("schema.sql")
    schema_sql = schema_path.read_text(encoding="utf-8")

    with connect(config) as conn:
        conn.executescript(schema_sql)
        conn.execute(
            "insert or ignore into schema_migrations(version, applied_at) values (?, ?)",
            (SCHEMA_VERSION, utc_now()),
        )
        conn.commit()
