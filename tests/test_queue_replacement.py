import sqlite3

import pytest

from bulk_music_downloader.database import (
    SCHEMA,
    CANDIDATE_SCHEMA,
    _migrate_tracks,
    _migrate_download_history,
    replace_queue,
    get_tracks,
)


def make_db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row

    db.execute("PRAGMA foreign_keys=ON")

    db.executescript(SCHEMA)

    _migrate_tracks(db)
    _migrate_download_history(db)

    db.executescript(CANDIDATE_SCHEMA)

    return db


def test_replace_queue_preserves_history_and_archives_old_queue(tmp_path):
    db = make_db()

    completed_file = tmp_path / "completed.mp3"
    completed_file.write_bytes(b"x" * 2048)

    # Existing completed track.
    cursor = db.execute(
        """
        INSERT INTO tracks (
            title,
            artist,
            status,
            source,
            file_path,
            version
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "Song Done",
            "Artist",
            "completed",
            "audius",
            str(completed_file),
            "Original",
        ),
    )

    completed_id = cursor.lastrowid

    # Old pending track which should disappear from the active queue.
    db.execute(
        """
        INSERT INTO tracks(title, artist)
        VALUES (?, ?)
        """,
        ("Old Queue", "Old Artist"),
    )

    # Failed track which appears again in the new import.
    cursor = db.execute(
        """
        INSERT INTO tracks(title, artist, status)
        VALUES (?, ?, ?)
        """,
        ("Requeue Me", "Artist Two", "failed"),
    )

    requeue_id = cursor.lastrowid

    # Historical attempt.
    db.execute(
        """
        INSERT INTO attempts (
            track_id,
            provider,
            attempt_number,
            outcome,
            detail
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            completed_id,
            "audius",
            1,
            "success",
            "Previously downloaded",
        ),
    )

    # Historical candidate.
    db.execute(
        """
        INSERT INTO candidates (
            track_id,
            provider,
            identifier,
            title,
            artist
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            completed_id,
            "audius",
            "candidate-1",
            "Song Done",
            "Artist",
        ),
    )

    db.commit()

    # Migrate the previous completed track into permanent history.
    _migrate_download_history(db)
    db.commit()

    # Verify migration is idempotent.
    _migrate_download_history(db)
    db.commit()

    result = replace_queue(
        db,
        [
            ("  SONG   DONE ", "ARTIST"),
            ("Requeue Me", "Artist Two"),
            ("Brand New", "Artist Three"),
            ("brand new", "artist three"),
        ],
    )

    assert result == {
        "queued": 2,
        "already_downloaded": 1,
        "duplicates": 1,
    }

    active = get_tracks(db)

    assert len(active) == 3

    active_by_title = {
        row["title"]: row
        for row in active
    }

    # Completed song is recognized and not re-queued.
    completed = active_by_title["Song Done"]

    assert completed["id"] == completed_id
    assert completed["status"] == "completed"
    assert completed["file_path"] == str(completed_file)

    # Previously failed song is eligible again.
    requeued = active_by_title["Requeue Me"]

    assert requeued["id"] == requeue_id
    assert requeued["status"] == "pending"

    # New song is pending.
    assert active_by_title["Brand New"]["status"] == "pending"

    # Old queue entry is archived, not deleted.
    old = db.execute(
        """
        SELECT active_queue
        FROM tracks
        WHERE title = 'Old Queue'
        """
    ).fetchone()

    assert old["active_queue"] == 0

    # Existing attempts remain intact.
    attempts = db.execute(
        """
        SELECT COUNT(*)
        FROM attempts
        WHERE track_id = ?
        """,
        (completed_id,),
    ).fetchone()[0]

    assert attempts == 1

    # Existing candidates remain intact.
    candidates = db.execute(
        """
        SELECT COUNT(*)
        FROM candidates
        WHERE track_id = ?
        """,
        (completed_id,),
    ).fetchone()[0]

    assert candidates == 1

    # Permanent history contains exactly one record.
    history_count = db.execute(
        "SELECT COUNT(*) FROM download_history"
    ).fetchone()[0]

    assert history_count == 1

    # Archived records remain accessible.
    assert len(get_tracks(db, include_inactive=True)) == 4


def test_empty_import_does_not_destroy_existing_queue():
    db = make_db()

    db.execute(
        """
        INSERT INTO tracks(title, artist)
        VALUES (?, ?)
        """,
        ("Existing Song", "Existing Artist"),
    )

    db.commit()

    before = [
        (row["id"], row["title"])
        for row in get_tracks(db)
    ]

    with pytest.raises(ValueError):
        replace_queue(db, [])

    after = [
        (row["id"], row["title"])
        for row in get_tracks(db)
    ]

    assert after == before