import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sc_gr_app.errors import LockError


def now() -> datetime:
    return datetime.now(timezone.utc)


def encode_name(name: str) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "__", name)
    safe_name = safe_name.replace("..", "__").strip("._")
    return (safe_name or "lock") + ".lock"


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
                stale_payload = self._stale_payload()
                if stale_payload is None:
                    raise LockError(f"Lock is busy: {self.name}")
                if not self._delete_stale_payload(stale_payload):
                    raise LockError(f"Lock is busy: {self.name}")

            try:
                self._write_exclusive(payload)
            except FileExistsError:
                if self.path.exists() and self._stale_payload() is None:
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
        return self._stale_payload() is not None

    def _stale_payload(self) -> str | None:
        try:
            raw_payload = self.path.read_text(encoding="utf-8")
            payload = json.loads(raw_payload)
        except OSError:
            return ""
        except json.JSONDecodeError:
            return raw_payload

        try:
            expires_at_raw = payload.get("expires_at")
            if not expires_at_raw:
                return raw_payload
            expires_at = datetime.fromisoformat(expires_at_raw)
            if expires_at.tzinfo is None:
                return raw_payload
        except (ValueError, TypeError):
            return raw_payload

        if expires_at <= now():
            return raw_payload
        return None

    def _delete_stale_payload(self, stale_payload: str) -> bool:
        try:
            if self.path.read_text(encoding="utf-8") != stale_payload:
                return False
            self.path.unlink()
        except FileNotFoundError:
            return True
        except OSError:
            return False
        return True

    def renew(self) -> None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise LockError(f"Cannot renew lock not owned: {self.name}") from None
        except (json.JSONDecodeError, OSError):
            raise LockError(f"Cannot renew lock not owned: {self.name}") from None

        if payload.get("token") != self.token:
            raise LockError(f"Cannot renew lock not owned: {self.name}")

        expires_at_raw = payload.get("expires_at")
        try:
            expires_at = datetime.fromisoformat(expires_at_raw)
        except (TypeError, ValueError):
            raise LockError(f"Cannot renew expired lock: {self.name}") from None
        if expires_at.tzinfo is None or expires_at <= now():
            raise LockError(f"Cannot renew expired lock: {self.name}")

        heartbeat_at = now()
        payload["heartbeat_at"] = heartbeat_at.isoformat()
        payload["expires_at"] = (
            heartbeat_at + timedelta(seconds=self.ttl_seconds)
        ).isoformat()
        self.path.write_text(json.dumps(payload), encoding="utf-8")

    def __enter__(self) -> "LeaseLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.release()
