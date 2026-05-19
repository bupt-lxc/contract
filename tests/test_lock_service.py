import pytest

from sc_gr_app.errors import LockError
from sc_gr_app.services.lock_service import LeaseLock


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
