import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sc_gr_app.errors import LockError


def now() -> datetime:
    return datetime.now(timezone.utc)


def encode_name(name: str) -> str:
    return name.replace(":", "__") + ".lock"


class LeaseLock:
    def __init__(
        self, lock_dir: Path, name: str, owner: str, ttl_seconds: int = 30
    ) -> None:
        self.lock_dir = lock_dir
        self.name = name
        self.owner = owner
        self.ttl_seconds = ttl_seconds
        self.token = str(uuid.uuid4())
        self.path = self.lock_dir / encode_name(name)

    def acquire(self) -> None:
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        payload = self._payload()

        for _ in range(3):
            if self.path.exists():
                if not self._is_stale():
                    raise LockError(f"Lock is busy: {self.name}")
                self.path.unlink(missing_ok=True)

            try:
                self._write_exclusive(payload)
            except FileExistsError:
                if self.path.exists() and not self._is_stale():
                    raise LockError(f"Lock is busy: {self.name}")
                continue

            if self._owns_lock():
                return
            raise LockError(f"Failed to acquire lock: {self.name}")

        raise LockError(f"Lock is busy: {self.name}")

    def _payload(self) -> dict[str, str]:
        acquired_at = now()
        expires_at = acquired_at + timedelta(seconds=self.ttl_seconds)
        return {
            "name": self.name,
            "owner": self.owner,
            "token": self.token,
            "acquired_at": acquired_at.isoformat(),
            "heartbeat_at": acquired_at.isoformat(),
            "expires_at": expires_at.isoformat(),
        }

    def _write_exclusive(self, payload: dict[str, str]) -> None:
        fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(fd, json.dumps(payload).encode("utf-8"))
        finally:
            os.close(fd)

    def _owns_lock(self) -> bool:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return False
        return payload.get("token") == self.token

    def release(self) -> None:
        if not self.path.exists():
            return

        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return

        if payload.get("token") == self.token:
            self.path.unlink(missing_ok=True)

    def _is_stale(self) -> bool:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            expires_at_raw = payload.get("expires_at")
            if not expires_at_raw:
                return True
            expires_at = datetime.fromisoformat(expires_at_raw)
            if expires_at.tzinfo is None:
                return True
        except (json.JSONDecodeError, OSError, ValueError, TypeError):
            return True

        return expires_at <= now()

    def __enter__(self) -> "LeaseLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.release()
