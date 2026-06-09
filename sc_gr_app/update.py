import hashlib
import json
import logging
import os
from pathlib import Path

from sc_gr_app import __version__
from sc_gr_app.config import _resolve_base_dir

logger = logging.getLogger(__name__)

REQUIRED_MANIFEST_PATHS = [
    ("version",),
    ("gui", "installer"),
    ("gui", "sha256"),
    ("notification", "package"),
    ("notification", "sha256"),
]

# PowerShell Set-Content -Encoding UTF8 emits a BOM; utf-8-sig strips it.
_ENCODING = "utf-8-sig"


def _base_dir() -> Path:
    """Root directory that contains data/ and releases/. Matches default_config()
    logic so the update check follows the same path as the database."""
    env_data = os.getenv("SC_GR_DATA_DIR")
    if env_data:
        return Path(env_data)
    return _resolve_base_dir()


def _releases_dir() -> Path:
    return _base_dir() / "releases"


def _read_file(path: Path) -> str:
    """Read a file via os.open() → CreateFileW, the same Win32 code path
    SQLite uses."""
    path_str = str(path)
    fd = os.open(path_str, os.O_RDONLY | os.O_BINARY)
    try:
        chunks = []
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks).decode(_ENCODING)
    finally:
        os.close(fd)


def fetch_manifest() -> dict | None:
    if os.getenv("SC_GR_DEV") == "1":
        return None
    manifest_path = _releases_dir() / "manifest.json"
    try:
        return json.loads(_read_file(manifest_path))
    except FileNotFoundError:
        logger.warning("Update manifest not found at %s", manifest_path)
        return None
    except PermissionError:
        logger.warning("Permission denied reading update manifest at %s", manifest_path)
        return None
    except OSError:
        logger.warning("OS error reading update manifest at %s", manifest_path)
        return None
    except json.JSONDecodeError:
        logger.warning("Update manifest at %s is not valid JSON", manifest_path)
        return None


def verify_manifest(manifest: dict) -> bool:
    if manifest is None:
        return False
    try:
        for path in REQUIRED_MANIFEST_PATHS:
            node = manifest
            for key in path:
                node = node[key]
        return isinstance(manifest.get("version"), str)
    except (KeyError, TypeError):
        return False


def is_update_available(manifest: dict) -> bool:
    if manifest is None:
        return False
    current = manifest.get("version")
    return isinstance(current, str) and current != __version__


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
