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


def test_stale_lock_can_be_replaced(app_config):
    first = LeaseLock(app_config.lock_dir, "sc:SC001", "MACHINE1", ttl_seconds=-1)
    second = LeaseLock(app_config.lock_dir, "sc:SC001", "MACHINE2", ttl_seconds=60)

    first.acquire()
    second.acquire()

    second.release()


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
