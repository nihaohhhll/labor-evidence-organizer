"""Object storage abstraction.

Business code depends on the `Storage` protocol only; `local` is the dev
implementation and `s3` is the production target (docs/04_TECH_ARCHITECTURE).
Originals written through here are immutable — no method rewrites bytes.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StoredObject:
    key: str
    size: int
    sha256: str


@runtime_checkable
class Storage(Protocol):
    """Minimal storage contract used by the file service."""

    def put(self, key: str, data: bytes) -> StoredObject: ...

    def get(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None: ...


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class LocalStorage:
    """Filesystem-backed storage rooted at `settings.storage_local_root`.

    Keys are relative paths; `..` is rejected so a crafted key can never
    escape the root (docs/11_SECURITY.md 防止路径穿越).
    """

    def __init__(self, root: str | None = None) -> None:
        self.root = Path(root or settings.storage_local_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        """Map a storage key to an absolute path, refusing unsafe shapes.

        Two independent guards, deliberately:

        1. Shape check — reject traversal *outright* rather than letting the
           path normalise into a harmless-looking location. The previous
           version used `".." in key.split("/"), which is a **list membership**
           test, not a substring test: `..%2f..%2f` and `....//....//` both
           slipped past it. Checking each component for the substring is what
           that code was meant to do.
        2. Containment check — `resolve()` then `is_relative_to(root)`, which
           is what actually guarantees no escape even if a new shape appears.

        Backslashes are rejected too: they are a separator on Windows and
        would otherwise be an ordinary character here but a traversal there.
        """
        if not key or key.startswith("/"):
            raise ValueError(f"invalid storage key: {key!r}")
        if "\\" in key:
            raise ValueError(f"invalid storage key: {key!r}")
        for part in key.split("/"):
            if part == "..":
                raise ValueError(f"storage key traverses upward: {key!r}")
            if ".." in part:
                # Covers encoded (`..%2f`) and padded (`....//`) variants.
                raise ValueError(f"storage key traverses upward: {key!r}")
            if part.startswith("/"):
                raise ValueError(f"invalid storage key: {key!r}")

        target = (self.root / key).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError(f"storage key escapes root: {key!r}")
        return target

    def put(self, key: str, data: bytes) -> StoredObject:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            # Immutability guard: never silently overwrite an original.
            existing = path.read_bytes()
            if existing != data:
                raise FileExistsError(f"refusing to overwrite immutable object {key!r}")
            return StoredObject(key=key, size=len(data), sha256=sha256_hex(data))
        path.write_bytes(data)
        return StoredObject(key=key, size=len(data), sha256=sha256_hex(data))

    def get(self, key: str) -> bytes:
        path = self._resolve(key)
        if not path.exists():
            raise FileNotFoundError(key)
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        try:
            return self._resolve(key).exists()
        except ValueError:
            return False

    def delete(self, key: str) -> None:
        path = self._resolve(key)
        if path.exists():
            path.unlink()


class S3Storage:
    """S3-compatible storage. Requires boto3, which is an optional dependency."""

    def __init__(self) -> None:  # pragma: no cover - needs real S3 credentials
        try:
            import boto3  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "STORAGE_BACKEND=s3 requires boto3: pip install boto3"
            ) from exc
        self.bucket = settings.s3_bucket or ""
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            region_name=settings.s3_region,
        )

    def put(self, key: str, data: bytes) -> StoredObject:  # pragma: no cover
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data)
        return StoredObject(key=key, size=len(data), sha256=sha256_hex(data))

    def get(self, key: str) -> bytes:  # pragma: no cover
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def exists(self, key: str) -> bool:  # pragma: no cover
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def delete(self, key: str) -> None:  # pragma: no cover
        self.client.delete_object(Bucket=self.bucket, Key=key)


_storage: Storage | None = None


def get_storage() -> Storage:
    """Return the configured storage backend (cached)."""
    global _storage
    if _storage is None:
        _storage = S3Storage() if settings.storage_backend == "s3" else LocalStorage()
    return _storage


def reset_storage() -> None:
    """Drop the cached backend so tests can point at a temp directory."""
    global _storage
    _storage = None
