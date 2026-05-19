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
