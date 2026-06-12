import os
import sys
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv():
    """Load .env file from next to the executable (or _internal for PyInstaller).

    Only sets keys that aren't already in the environment, so OS-level
    overrides always win. Safe to call multiple times — first write wins.
    """
    exe_dir = Path(sys.executable).parent
    candidates = [exe_dir / ".env"]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / ".env")
    for env_path in candidates:
        try:
            if not env_path.is_file():
                continue
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                if key and key not in os.environ:
                    os.environ[key] = value
        except OSError:
            pass


_load_dotenv()


def _contract_folder() -> str:
    if os.getenv("SC_GR_BETA") == "1":
        return "pomp-beta"
    # Fallback for frozen executables: detect beta from the exe filename
    # so the notification exe always connects to the correct database
    # even when the .env file is missing from the deployment directory.
    if getattr(sys, "frozen", False):
        exe_name = Path(sys.executable).stem
        if "Beta" in exe_name or "beta" in exe_name:
            return "pomp-beta"
    return "pomp"


# Shared drive may be reached via UNC path or mapped drive letter (e.g. K:).
# Both point to the same network location — try each and use the first
# one that is actually accessible on this machine.
_SHARED_BASE = (
    r"AUDI CHINA\Audi_China_RnD\R&D\EG\10_EG-V"
    r"\80000_EG_W\DMAS\01 Daily working files"
)


def _shared_subpath() -> str:
    return f"{_SHARED_BASE}\\{_contract_folder()}"


def _make_candidates() -> list:
    subpath = _shared_subpath()
    return [Path(r"\\ap.vwg\fileshare") / subpath, Path("K:/") / subpath]


def _resolve_base_dir() -> Path:
    """Return the first accessible shared-drive path, or UNC as fallback."""
    candidates = _make_candidates()
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


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
            base_dir = Path(os.getenv("APPDATA", Path.home())) / "pomp-dev"
        else:
            base_dir = _resolve_base_dir()
    root = Path(base_dir)
    root.mkdir(parents=True, exist_ok=True)
    data_dir = root / "data"
    return AppConfig(
        db_path=data_dir / "sc_gr.sqlite3",
        lock_dir=data_dir / "locks",
    )
