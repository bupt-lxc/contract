import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    db_path: Path
    lock_dir: Path
    busy_timeout_ms: int = 5000


def default_config(base_dir: Path | None = None) -> AppConfig:
    if base_dir is None:
        env_data = os.getenv("SC_GR_DATA_DIR")
        if env_data:
            base_dir = Path(env_data)
        else:
            base_dir = Path(os.getenv("APPDATA", Path.home())) / "sc-gr-management"
    root = Path(base_dir)
    root.mkdir(parents=True, exist_ok=True)
    data_dir = root / "data"
    return AppConfig(
        db_path=data_dir / "sc_gr.sqlite3",
        lock_dir=data_dir / "locks",
    )
