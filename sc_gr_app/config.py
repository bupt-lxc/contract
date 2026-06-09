import os
from dataclasses import dataclass
from pathlib import Path


# Shared drive may be reached via UNC path or mapped drive letter (e.g. K:).
# Both point to the same network location — try each and use the first
# one that is actually accessible on this machine.
_SHARED_SUBPATH = (
    r"AUDI CHINA\Audi_China_RnD\R&D\EG\10_EG-V"
    r"\80000_EG_W\DMAS\01 Daily working files\contract"
)
SHARED_DRIVE_DIR = Path(r"\\ap.vwg\fileshare") / _SHARED_SUBPATH
K_DRIVE_DIR = Path("K:/") / _SHARED_SUBPATH

_CANDIDATE_DIRS = [SHARED_DRIVE_DIR, K_DRIVE_DIR]


def _resolve_base_dir() -> Path:
    """Return the first accessible shared-drive path, or UNC as fallback."""
    for candidate in _CANDIDATE_DIRS:
        if candidate.exists():
            return candidate
    return SHARED_DRIVE_DIR


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
        elif os.getenv("SC_GR_DEV") == "1":
            base_dir = Path(os.getenv("APPDATA", Path.home())) / "sc-gr-management-dev"
        else:
            base_dir = _resolve_base_dir()
    root = Path(base_dir)
    root.mkdir(parents=True, exist_ok=True)
    data_dir = root / "data"
    return AppConfig(
        db_path=data_dir / "sc_gr.sqlite3",
        lock_dir=data_dir / "locks",
    )
