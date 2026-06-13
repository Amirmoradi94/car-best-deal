from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from urllib.parse import urlparse

from app.scraping.contracts import SourceSnapshot
from app.storage.object_store import ObjectStore


@dataclass(frozen=True)
class PersistedSourceSnapshot:
    source_name: str
    source_url: str
    html_object_key: str
    metadata_object_key: str
    screenshot_object_key: str | None
    expires_at: datetime
    content_hash: str


class SourceSnapshotPersistence:
    def __init__(self, object_store: ObjectStore, retention_days: int = 90) -> None:
        self.object_store = object_store
        self.retention_days = retention_days

    def persist(self, snapshot: SourceSnapshot, captured_at: datetime | None = None) -> PersistedSourceSnapshot:
        captured = captured_at or datetime.now(UTC)
        prefix = _snapshot_prefix(snapshot, captured)
        html_key = f"{prefix}/page.html"
        metadata_key = f"{prefix}/metadata.json"
        screenshot_key = f"{prefix}/screenshot.png" if snapshot.screenshot else None

        self.object_store.put_text(html_key, snapshot.html, "text/html; charset=utf-8")
        if screenshot_key and snapshot.screenshot:
            self.object_store.put_bytes(screenshot_key, snapshot.screenshot, "image/png")

        content_hash = sha256(snapshot.html.encode("utf-8")).hexdigest()
        metadata = {
            "source_name": snapshot.source_name,
            "url": snapshot.url,
            "status_code": snapshot.status_code,
            "rendered": snapshot.rendered,
            "content_hash": content_hash,
            "captured_at": captured.isoformat(),
            "metadata": snapshot.metadata,
        }
        self.object_store.put_text(
            metadata_key,
            json.dumps(metadata, indent=2, sort_keys=True),
            "application/json; charset=utf-8",
        )

        return PersistedSourceSnapshot(
            source_name=snapshot.source_name,
            source_url=snapshot.url,
            html_object_key=html_key,
            metadata_object_key=metadata_key,
            screenshot_object_key=screenshot_key,
            expires_at=captured + timedelta(days=self.retention_days),
            content_hash=content_hash,
        )


def _snapshot_prefix(snapshot: SourceSnapshot, captured_at: datetime) -> str:
    parsed = urlparse(snapshot.url)
    url_hash = sha256(snapshot.url.encode("utf-8")).hexdigest()[:16]
    timestamp = captured_at.strftime("%Y%m%dT%H%M%SZ")
    host = parsed.netloc.replace(":", "_") or "unknown-host"
    return f"source-snapshots/{snapshot.source_name}/{timestamp}-{host}-{url_hash}"

