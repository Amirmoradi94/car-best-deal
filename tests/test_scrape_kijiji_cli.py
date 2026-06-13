from pathlib import Path

from app.cli import scrape_kijiji
from app.core.config import Settings


def test_cli_fixture_mode_saves_snapshots_and_fixture(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        scrape_kijiji,
        "get_settings",
        lambda: Settings(OBJECT_STORE_ROOT=str(tmp_path / "objects"), SCRAPING_FIXTURE_MODE=True),
    )
    fixture_path = tmp_path / "captured" / "search.html"

    exit_code = scrape_kijiji.main(
        [
            "2020 Honda Civic Montreal",
            "--fixture-mode",
            "--save-search-fixture",
            str(fixture_path),
            "--object-store-root",
            str(tmp_path / "objects"),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert '"listing_count": 2' in output
    assert fixture_path.exists()
    assert "2020 Honda Civic EX" in fixture_path.read_text()


def test_cli_live_mode_without_zyte_key_fails_safely(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        scrape_kijiji,
        "get_settings",
        lambda: Settings(ZYTE_API_KEY=None, OBJECT_STORE_ROOT=str(tmp_path / "objects")),
    )

    exit_code = scrape_kijiji.main(["2020 Honda Civic Montreal", "--object-store-root", str(tmp_path / "objects")])

    output = capsys.readouterr().out
    assert exit_code == 2
    assert '"error": "credentials_missing"' in output

