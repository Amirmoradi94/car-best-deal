from datetime import UTC, datetime

from app.scraping.contracts import SourceSnapshot
from app.services.source_snapshot_service import SourceSnapshotPersistence
from app.storage.object_store import LocalObjectStore


def test_source_snapshot_persistence_writes_html_metadata_and_screenshot(tmp_path) -> None:
    store = LocalObjectStore(tmp_path)
    service = SourceSnapshotPersistence(store, retention_days=90)
    snapshot = SourceSnapshot(
        source_name="kijiji",
        url="https://example.test/listing",
        html="<html>listing</html>",
        status_code=200,
        rendered=True,
        screenshot=b"png-bytes",
        metadata={"adapter": "test"},
    )

    persisted = service.persist(snapshot, captured_at=datetime(2026, 6, 12, tzinfo=UTC))

    assert persisted.source_name == "kijiji"
    assert persisted.screenshot_object_key is not None
    assert store.read_text(persisted.html_object_key) == "<html>listing</html>"
    assert store.read_bytes(persisted.screenshot_object_key) == b"png-bytes"
    metadata = store.read_text(persisted.metadata_object_key)
    assert '"source_name": "kijiji"' in metadata
    assert '"rendered": true' in metadata
    assert persisted.expires_at.year == 2026

