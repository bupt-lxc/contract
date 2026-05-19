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
        if self.path.exists() and not self._is_stale():
            raise LockError(f"Lock is busy: {self.name}")

        acquired_at = now()
        expires_at = acquired_at + timedelta(seconds=self.ttl_seconds)
        payload = {
            "name": self.name,
            "owner": self.owner,
            "token": self.token,
            "acquired_at": acquired_at.isoformat(),
            "heartbeat_at": acquired_at.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
        temp_path = self.path.with_name(f"{self.path.name}.{self.token}.tmp")
        temp_path.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(temp_path, self.path)

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
