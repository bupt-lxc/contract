import hashlib
import json
import os
from pathlib import Path

from sc_gr_app import __version__
from sc_gr_app.config import AppConfig

REQUIRED_MANIFEST_PATHS = [
    ("version",),
    ("gui", "installer"),
    ("gui", "sha256"),
    ("notification", "package"),
    ("notification", "sha256"),
]


def fetch_manifest(config: AppConfig) -> dict | None:
    if os.getenv("SC_GR_DEV") == "1":
        return None
    manifest_path = config.db_path.parent.parent / "releases" / "manifest.json"
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
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
