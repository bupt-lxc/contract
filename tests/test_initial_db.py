import sqlite3


def test_create_empty_initial_database_creates_latest_empty_business_db(tmp_path):
    from sc_gr_app.db.initial_db import create_empty_initial_database
    from sc_gr_app.db.migrations import SCHEMA_VERSION

    target = tmp_path / "initial.sqlite3"

    created = create_empty_initial_database(target)

    assert created is True
    assert target.exists()
    with sqlite3.connect(target) as conn:
        latest = conn.execute("select max(version) from schema_migrations").fetchone()[0]
        counts = {
            table: conn.execute(f"select count(*) from {table}").fetchone()[0]
            for table in ("users", "vendors", "sc_records", "pos", "gr_requests")
        }

    assert latest == SCHEMA_VERSION
    assert counts == {
        "users": 0,
        "vendors": 0,
        "sc_records": 0,
        "pos": 0,
        "gr_requests": 0,
    }


def test_create_empty_initial_database_does_not_overwrite_existing_file(tmp_path):
    from sc_gr_app.db.initial_db import create_empty_initial_database

    target = tmp_path / "initial.sqlite3"
    target.write_bytes(b"keep me")

    created = create_empty_initial_database(target)

    assert created is False
    assert target.read_bytes() == b"keep me"


def test_create_production_database_if_missing_seeds_users_only(tmp_path):
    from sc_gr_app.db.initial_db import create_production_database_if_missing
    from sc_gr_app.db.migrations import SCHEMA_VERSION

    target = tmp_path / "data" / "sc_gr.sqlite3"

    created = create_production_database_if_missing(target)

    assert created is True
    assert target.exists()
    with sqlite3.connect(target) as conn:
        latest = conn.execute("select max(version) from schema_migrations").fetchone()[0]
        counts = {
            table: conn.execute(f"select count(*) from {table}").fetchone()[0]
            for table in ("users", "vendors", "sc_records", "pos", "gr_requests")
        }

    assert latest == SCHEMA_VERSION
    assert counts["users"] > 0
    assert counts["vendors"] == 0
    assert counts["sc_records"] == 0
    assert counts["pos"] == 0
    assert counts["gr_requests"] == 0


def test_create_production_database_if_missing_does_not_overwrite_existing_file(tmp_path):
    from sc_gr_app.db.initial_db import create_production_database_if_missing

    target = tmp_path / "data" / "sc_gr.sqlite3"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"production data")

    created = create_production_database_if_missing(target)

    assert created is False
    assert target.read_bytes() == b"production data"
