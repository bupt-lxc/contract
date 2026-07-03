from pathlib import Path

import pytest

from sc_gr_app.config import AppConfig


@pytest.fixture()
def app_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        db_path=tmp_path / "test.sqlite3",
        lock_dir=tmp_path / "locks",
        busy_timeout_ms=1000,
    )


@pytest.fixture()
def seeded_config(app_config: AppConfig) -> AppConfig:
    """Migrate + seed users, return config ready for tests."""
    from sc_gr_app.db.migrations import migrate
    from sc_gr_app.services.user_service import seed_users

    migrate(app_config)
    seed_users(app_config)
    return app_config
