import json
from datetime import timedelta

import pytest

from sc_gr_app.errors import LockError
from sc_gr_app.services import lock_service
from sc_gr_app.services.lock_service import LeaseLock


def write_lock_file(path, name, owner, token="other-token", ttl_seconds=60):
    timestamp = lock_service.now()
    payload = {
        "name": name,
        "owner": owner,
        "token": token,
        "acquired_at": timestamp.isoformat(),
        "heartbeat_at": timestamp.isoformat(),
        "expires_at": (timestamp + timedelta(seconds=ttl_seconds)).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_lease_lock_blocks_second_owner(app_config):
    first = LeaseLock(app_config.lock_dir, "sc:SC001", "MACHINE1", ttl_seconds=60)
    second = LeaseLock(app_config.lock_dir, "sc:SC001", "MACHINE2", ttl_seconds=60)

    first.acquire()

    try:
        with pytest.raises(LockError, match="Lock is busy: sc:SC001"):
            second.acquire()
    finally:
        first.release()


def test_lock_name_encoding_keeps_path_inside_lock_directory(app_config):
    lock = LeaseLock(app_config.lock_dir, r"sc:..\SC/001", "MACHINE1")

    assert lock.path.parent == app_config.lock_dir
    assert "/" not in lock.path.name
    assert "\\" not in lock.path.name


def test_stale_lock_can_be_replaced(app_config):
    first = LeaseLock(app_config.lock_dir, "sc:SC001", "MACHINE1", ttl_seconds=-1)
    second = LeaseLock(app_config.lock_dir, "sc:SC001", "MACHINE2", ttl_seconds=60)

    first.acquire()
    second.acquire()

    second.release()


def test_stale_lock_replacement_does_not_delete_fresh_racing_lock(
    app_config, monkeypatch
):
    stale_owner = LeaseLock(
        app_config.lock_dir,
        "sc:SC001",
        "MACHINE1",
        ttl_seconds=-1,
    )
    contender = LeaseLock(
        app_config.lock_dir,
        "sc:SC001",
        "MACHINE2",
        ttl_seconds=60,
    )

    stale_owner.acquire()

    original_read_text = lock_service.Path.read_text
    read_count = 0

    def race_read_text(path, *args, **kwargs):
        nonlocal read_count
        if path == contender.path:
            read_count += 1
            if read_count == 2:
                write_lock_file(
                    contender.path,
                    "sc:SC001",
                    "MACHINE3",
                    ttl_seconds=60,
                )
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(lock_service.Path, "read_text", race_read_text)

    with pytest.raises(LockError, match="Lock is busy: sc:SC001"):
        contender.acquire()

    payload = json.loads(contender.path.read_text(encoding="utf-8"))
    assert payload["owner"] == "MACHINE3"
    assert payload["token"] != contender.token


def test_acquire_losing_exclusive_create_race_raises_lock_error(
    app_config, monkeypatch
):
    loser = LeaseLock(app_config.lock_dir, "sc:SC001", "MACHINE1", ttl_seconds=60)
    original_open = lock_service.os.open

    def race_open(path, flags, mode=0o777, *, dir_fd=None):
        if lock_service.os.fspath(path) == lock_service.os.fspath(loser.path):
            write_lock_file(loser.path, "sc:SC001", "MACHINE2")
            raise FileExistsError
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(lock_service.os, "open", race_open)

    with pytest.raises(LockError, match="Lock is busy: sc:SC001"):
        loser.acquire()


def test_acquire_verifies_final_lock_token_before_returning(app_config, monkeypatch):
    lock = LeaseLock(app_config.lock_dir, "sc:SC001", "MACHINE1", ttl_seconds=60)

    monkeypatch.setattr(lock, "_owns_lock", lambda: False)

    with pytest.raises(LockError, match="Failed to acquire lock: sc:SC001"):
        lock.acquire()


def test_renew_extends_owned_lock_expiry(app_config, monkeypatch):
    lock = LeaseLock(app_config.lock_dir, "sc:SC001", "MACHINE1", ttl_seconds=30)
    original_now = lock_service.now()
    later = original_now + timedelta(seconds=10)

    monkeypatch.setattr(lock_service, "now", lambda: original_now)
    lock.acquire()
    before = json.loads(lock.path.read_text(encoding="utf-8"))

    monkeypatch.setattr(lock_service, "now", lambda: later)
    lock.renew()

    after = json.loads(lock.path.read_text(encoding="utf-8"))
    assert after["token"] == lock.token
    assert after["heartbeat_at"] == later.isoformat()
    assert after["expires_at"] == (later + timedelta(seconds=30)).isoformat()
    assert after["expires_at"] > before["expires_at"]


def test_renew_requires_current_token_and_unexpired_lock(app_config):
    lock = LeaseLock(app_config.lock_dir, "sc:SC001", "MACHINE1", ttl_seconds=30)
    write_lock_file(lock.path, "sc:SC001", "MACHINE2", ttl_seconds=60)

    with pytest.raises(LockError, match="Cannot renew lock not owned"):
        lock.renew()

    write_lock_file(lock.path, "sc:SC001", "MACHINE1", token=lock.token, ttl_seconds=-1)

    with pytest.raises(LockError, match="Cannot renew expired lock"):
        lock.renew()
