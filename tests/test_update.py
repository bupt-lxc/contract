import hashlib
import json
import os
from pathlib import Path

import pytest

from sc_gr_app import __version__
from sc_gr_app.config import AppConfig
from sc_gr_app.update import (
    fetch_manifest,
    verify_manifest,
    is_update_available,
    sha256_file,
)


def make_config(tmp_path: Path) -> AppConfig:
    """Create an AppConfig with db_path at tmp_path/data/sc_gr.sqlite3."""
    return AppConfig(
        db_path=tmp_path / "data" / "sc_gr.sqlite3",
        lock_dir=tmp_path / "data" / "locks",
    )


class TestFetchManifest:
    def test_returns_none_in_dev_mode(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SC_GR_DEV", "1")
        config = make_config(tmp_path)
        assert fetch_manifest(config) is None

    def test_returns_none_when_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SC_GR_DEV", raising=False)
        config = make_config(tmp_path)
        assert fetch_manifest(config) is None

    def test_returns_dict_when_manifest_exists(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SC_GR_DEV", raising=False)
        config = make_config(tmp_path)
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir(parents=True)
        manifest = {
            "version": "2.0.0",
            "published_at": "2026-06-08T15:30:00Z",
            "changelog_cn": "测试",
            "gui": {"installer": "test-setup.exe", "sha256": "abc"},
            "notification": {"package": "test-notify.exe", "sha256": "def"},
        }
        (releases_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        result = fetch_manifest(config)
        assert result == manifest

    def test_returns_none_on_parse_error(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SC_GR_DEV", raising=False)
        config = make_config(tmp_path)
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir(parents=True)
        (releases_dir / "manifest.json").write_text("not json", encoding="utf-8")
        assert fetch_manifest(config) is None


class TestVerifyManifest:
    def test_valid_manifest(self):
        manifest = {
            "version": "2.0.0",
            "gui": {"installer": "test-setup.exe", "sha256": "abc"},
            "notification": {"package": "test-notify.exe", "sha256": "def"},
        }
        assert verify_manifest(manifest) is True

    def test_none_is_false(self):
        assert verify_manifest(None) is False

    def test_missing_gui_installer(self):
        manifest = {
            "version": "2.0.0",
            "gui": {"sha256": "abc"},
            "notification": {"package": "test.exe", "sha256": "def"},
        }
        assert verify_manifest(manifest) is False

    def test_missing_notification_package(self):
        manifest = {
            "version": "2.0.0",
            "gui": {"installer": "test-setup.exe", "sha256": "abc"},
            "notification": {"sha256": "def"},
        }
        assert verify_manifest(manifest) is False

    def test_missing_version(self):
        manifest = {
            "gui": {"installer": "test-setup.exe", "sha256": "abc"},
            "notification": {"package": "test.exe", "sha256": "def"},
        }
        assert verify_manifest(manifest) is False

    def test_version_not_string(self):
        manifest = {
            "version": 3,
            "gui": {"installer": "test-setup.exe", "sha256": "abc"},
            "notification": {"package": "test.exe", "sha256": "def"},
        }
        assert verify_manifest(manifest) is False


class TestIsUpdateAvailable:
    def test_different_version(self):
        manifest = {"version": "99.99.99"}
        other = __version__ != "99.99.99"
        assert is_update_available(manifest) is other

    def test_same_version(self):
        manifest = {"version": __version__}
        assert is_update_available(manifest) is False

    def test_none(self):
        assert is_update_available(None) is False

    def test_no_version_key(self):
        assert is_update_available({}) is False


class TestSha256File:
    def test_known_content(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"hello")
        digest = sha256_file(f)
        assert digest == hashlib.sha256(b"hello").hexdigest()

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.bin"
        f.write_bytes(b"")
        digest = sha256_file(f)
        assert digest == hashlib.sha256(b"").hexdigest()
