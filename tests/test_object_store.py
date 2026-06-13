from app.storage.object_store import LocalObjectStore


def test_local_object_store_writes_and_reads_text(tmp_path) -> None:
    store = LocalObjectStore(tmp_path)

    stored = store.put_text("snapshots/example.html", "<html>ok</html>", "text/html")

    assert stored.key == "snapshots/example.html"
    assert stored.size_bytes == len("<html>ok</html>".encode("utf-8"))
    assert store.read_text("snapshots/example.html") == "<html>ok</html>"


def test_local_object_store_rejects_path_traversal(tmp_path) -> None:
    store = LocalObjectStore(tmp_path)

    try:
        store.put_text("../escape.txt", "bad")
    except ValueError as exc:
        assert "escapes store root" in str(exc)
    else:
        raise AssertionError("expected ValueError")

