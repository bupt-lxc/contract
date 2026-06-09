import hashlib
import json
import os
from pathlib import Path

import pytest

from sc_gr_app import __version__
from sc_gr_app.update import (
    fetch_manifest,
    verify_manifest,
    is_update_available,
    sha256_file,
)


@pytest.fixture
def patch_shared_drive(monkeypatch, tmp_path):
    """Redirect base-dir resolution to a temp path for isolated testing."""
    monkeypatch.setattr(
        "sc_gr_app.update._resolve_base_dir",
        lambda: tmp_path,
    )


class TestFetchManifest:
    def test_returns_none_in_dev_mode(self, monkeypatch):
        monkeypatch.setenv("SC_GR_DEV", "1")
        assert fetch_manifest() is None

    def test_returns_none_when_file_missing(self, patch_shared_drive, monkeypatch):
        monkeypatch.delenv("SC_GR_DEV", raising=False)
        assert fetch_manifest() is None

    def test_returns_dict_when_manifest_exists(self, patch_shared_drive, tmp_path, monkeypatch):
        monkeypatch.delenv("SC_GR_DEV", raising=False)
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()
        manifest = {
            "version": "2.0.0",
            "published_at": "2026-06-08T15:30:00Z",
            "changelog_cn": "test",
            "gui": {"installer": "test-setup.exe", "sha256": "abc"},
            "notification": {"package": "test-notify.exe", "sha256": "def"},
        }
        (releases_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        result = fetch_manifest()
        assert result == manifest

    def test_returns_none_on_parse_error(self, patch_shared_drive, tmp_path, monkeypatch):
        monkeypatch.delenv("SC_GR_DEV", raising=False)
        releases_dir = tmp_path / "releases"
        releases_dir.mkdir()
        (releases_dir / "manifest.json").write_text("not json", encoding="utf-8")
        assert fetch_manifest() is None


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
