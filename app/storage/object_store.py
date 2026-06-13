from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class StoredObject:
    key: str
    path: Path
    size_bytes: int
    content_type: str
    sha256: str


class ObjectStore(Protocol):
    def put_bytes(self, key: str, data: bytes, content_type: str) -> StoredObject:
        ...

    def put_text(self, key: str, text: str, content_type: str = "text/plain; charset=utf-8") -> StoredObject:
        ...

    def read_bytes(self, key: str) -> bytes:
        ...

    def read_text(self, key: str) -> str:
        ...


class LocalObjectStore:
    def __init__(self, root: Path | str = "var/object-store") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put_bytes(self, key: str, data: bytes, content_type: str) -> StoredObject:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return StoredObject(
            key=key,
            path=path,
            size_bytes=len(data),
            content_type=content_type,
            sha256=hashlib.sha256(data).hexdigest(),
        )

    def put_text(self, key: str, text: str, content_type: str = "text/plain; charset=utf-8") -> StoredObject:
        return self.put_bytes(key, text.encode("utf-8"), content_type)

    def read_bytes(self, key: str) -> bytes:
        return self._resolve(key).read_bytes()

    def read_text(self, key: str) -> str:
        return self.read_bytes(key).decode("utf-8")

    def _resolve(self, key: str) -> Path:
        clean_key = key.strip().lstrip("/")
        if not clean_key:
            raise ValueError("object key cannot be empty")
        resolved = (self.root / clean_key).resolve()
        root = self.root.resolve()
        if root != resolved and root not in resolved.parents:
            raise ValueError(f"object key escapes store root: {key}")
        return resolved

