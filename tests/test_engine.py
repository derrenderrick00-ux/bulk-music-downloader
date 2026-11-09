import sqlite3

from bulk_music_downloader.database import (
    SCHEMA,
    TRACK_MIGRATIONS,
    _migrate_tracks,
)
from bulk_music_downloader.models import SearchResult
from bulk_music_downloader.engine import run_queue


def make_db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript(SCHEMA)
    _migrate_tracks(db)

    db.executescript("""
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
            provider TEXT NOT NULL,
            identifier TEXT NOT NULL,
            title TEXT NOT NULL,
            artist TEXT,
            page_url TEXT,
            media_url TEXT,
            file_name TEXT,
            media_type TEXT,
            rights TEXT,
            rights_status TEXT NOT NULL DEFAULT 'unknown',
            download_allowed INTEGER,
            license_url TEXT,
            attribution TEXT,
            core REAL NOT NULL DEFAULT 0,
            title_score REAL NOT NULL DEFAULT 0,
            artist_score REAL NOT NULL DEFAULT 0,
            version TEXT,
            version_match INTEGER,
            metadata_json TEXT,
            review_status TEXT NOT NULL DEFAULT 'pending_review',
            review_note TEXT,
            reviewed_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(track_id, provider, identifier)
        );
    """)

    db.execute(
        """
        INSERT INTO tracks(title, artist)
        VALUES('Test Song', 'Test Artist')
        """
    )
    db.commit()
    return db


class Provider:

    def __init__(self, name, fail=False, rights_status="permitted"):
        self.name = name
        self.fail = fail
        self.rights_status = rights_status
        self.download_calls = 0

    def search(self, title, artist, limit):
        return [
            SearchResult(
                provider=self.name,
                identifier=f"{self.name}-1",
                title="Test Song",
                artist="Test Artist",
                url="https://example.test",
                rights_status=self.rights_status,
                download_allowed=True,
            )
        ]

    def download(self, result, destination, timeout):
        self.download_calls += 1

        if self.fail:
            raise RuntimeError("Simulated provider failure")

        destination.parent.mkdir(parents=True, exist_ok=True)
        output = destination.with_suffix(".mp3")
        output.write_bytes(b"x" * 2048)
        return output


def test_queue_falls_back_to_second_provider(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "bulk_music_downloader.engine._validate_audio",
        lambda path: None,
    )

    db = make_db()
    first = Provider("first", fail=True)
    second = Provider("second")

    result = run_queue(
        db,
        {
            "download_dir": str(tmp_path),
            "max_search_results": 8,
            "retries_per_provider": 1,
            "request_timeout": 5,
        },
        [first, second],
        auto_accept=True,
    )

    assert result["completed"] == 1
    assert first.download_calls == 1
    assert second.download_calls == 1

    row = db.execute(
        "SELECT status, source FROM tracks WHERE id = 1"
    ).fetchone()

    assert row["status"] == "completed"
    assert row["source"] == "second"
    history = db.execute(
        """
        SELECT *
        FROM download_history
        WHERE title_key = 'test song'
          AND artist_key = 'test artist'
        """
    ).fetchone()

    assert history is not None
    assert history["source"] == "second"
    assert history["file_path"]


def test_queue_does_not_download_unverified_rights(tmp_path):
    db = make_db()
    provider = Provider("unverified", rights_status="review_required")

    result = run_queue(
        db,
        {"download_dir": str(tmp_path)},
        [provider],
        auto_accept=True,
    )

    assert result["failed"] == 1
    assert provider.download_calls == 0


def test_queue_does_not_search_direct_url(tmp_path):
    class DirectProvider(Provider):

        def search(self, *args):
            raise AssertionError("Direct URL must not be searched")

    db = make_db()
    direct = DirectProvider("direct_url")

    result = run_queue(
        db,
        {"download_dir": str(tmp_path)},
        [direct],
        auto_accept=True,
    )

    assert result["failed"] == 1
    assert direct.download_calls == 0