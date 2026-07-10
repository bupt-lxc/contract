"""Create the packaged empty initial SQLite database."""
import argparse
import gc
import shutil
import tempfile
from pathlib import Path

from sc_gr_app.config import AppConfig
from sc_gr_app.db.migrations import migrate
from sc_gr_app.services.user_service import seed_users


BUSINESS_TABLES = ("users", "vendors", "sc_records", "pos", "gr_requests")


def create_empty_initial_database(target_path: Path) -> bool:
    """Create a latest-schema empty template DB when target_path is missing.

    Returns True when a new file is created. Existing files are left untouched.
    """
    target_path = Path(target_path)
    if target_path.exists():
        return False

    target_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        temp_db = tmp_dir / "initial.sqlite3"
        temp_db.touch()
        migrate(AppConfig(db_path=temp_db, lock_dir=tmp_dir / "locks"))
        _assert_empty_business_tables(temp_db)
        shutil.copy2(temp_db, target_path)
        gc.collect()
    return True


def create_production_database_if_missing(target_path: Path) -> bool:
    """Create the shared production DB when it does not exist.

    The production DB starts with schema + default users, but no business data.
    Existing database files are never modified.
    """
    target_path = Path(target_path)
    if target_path.exists():
        return False

    target_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        temp_db = tmp_dir / "sc_gr.sqlite3"
        temp_db.touch()
        config = AppConfig(db_path=temp_db, lock_dir=tmp_dir / "locks")
        migrate(config)
        seed_users(config)
        _assert_empty_business_tables(temp_db, allow_users=True)
        shutil.copy2(temp_db, target_path)
        gc.collect()
    return True


def _assert_empty_business_tables(db_path: Path, allow_users: bool = False) -> None:
    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        for table in BUSINESS_TABLES:
            count = conn.execute(f"select count(*) from {table}").fetchone()[0]
            if allow_users and table == "users":
                continue
            if count != 0:
                raise RuntimeError(f"{table} must be empty in initial database")
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "target",
        nargs="?",
        default=Path(__file__).parent / "initial.sqlite3",
        type=Path,
    )
    parser.add_argument("--production", action="store_true")
    args = parser.parse_args(argv)
    if args.production:
        created = create_production_database_if_missing(args.target)
        if created:
            print(f"Created production database: {args.target}")
        else:
            print(f"Production database already exists, skipped: {args.target}")
    else:
        created = create_empty_initial_database(args.target)
        if created:
            print(f"Created empty initial database: {args.target}")
        else:
            print(f"Initial database already exists, skipped: {args.target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
