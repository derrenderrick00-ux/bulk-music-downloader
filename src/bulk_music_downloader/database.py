from __future__ import annotations

import sqlite3

from .config import DATA_DIR


DB_PATH = DATA_DIR / "downloads.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    source TEXT,
    file_path TEXT,
    version TEXT,
    direct_url TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(title COLLATE NOCASE, artist COLLATE NOCASE)
);

CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id INTEGER NOT NULL REFERENCES tracks(id),
    provider TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    outcome TEXT NOT NULL,
    detail TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS control (
    id INTEGER PRIMARY KEY CHECK(id=1),
    pause_requested INTEGER NOT NULL DEFAULT 0
);

INSERT OR IGNORE INTO control(id, pause_requested)
VALUES(1, 0);
"""


# New fields are added without deleting or rewriting old records.
TRACK_MIGRATIONS = {
    "license_url": "TEXT",
    "rights_status": "TEXT NOT NULL DEFAULT 'unknown'",
    "download_allowed": "INTEGER",
    "attribution": "TEXT",
    "metadata_json": "TEXT",
}


def _migrate_tracks(db: sqlite3.Connection) -> None:
    """
    Apply safe, additive schema migrations.

    Existing columns and rows are preserved.
    """
    existing = {
        row["name"]
        for row in db.execute("PRAGMA table_info(tracks)").fetchall()
    }

    for column, definition in TRACK_MIGRATIONS.items():
        if column not in existing:
            db.execute(
                f"ALTER TABLE tracks ADD COLUMN {column} {definition}"
            )


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row

    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA journal_mode=WAL")

    db.executescript(SCHEMA)
    _migrate_tracks(db)

    db.commit()

    return db


def add_track(
    db,
    title: str,
    artist: str,
) -> tuple[bool, int | None]:
    title = title.strip()
    artist = artist.strip()

    if not title or not artist:
        raise ValueError("Track title and artist cannot be empty.")

    cur = db.execute(
        """
        INSERT OR IGNORE INTO tracks(title, artist)
        VALUES(?, ?)
        """,
        (title, artist),
    )

    db.commit()

    if cur.rowcount:
        return True, cur.lastrowid

    row = db.execute(
        """
        SELECT id
        FROM tracks
        WHERE title = ? COLLATE NOCASE
          AND artist = ? COLLATE NOCASE
        """,
        (title, artist),
    ).fetchone()

    return False, row["id"] if row else None


def get_tracks(db, statuses=None):
    if statuses:
        marks = ",".join("?" for _ in statuses)

        return db.execute(
            f"""
            SELECT *
            FROM tracks
            WHERE status IN ({marks})
            ORDER BY id
            """,
            tuple(statuses),
        ).fetchall()

    return db.execute(
        "SELECT * FROM tracks ORDER BY id"
    ).fetchall()


def set_status(
    db,
    track_id,
    status,
    source=None,
    file_path=None,
    version=None,
):
    db.execute(
        """
        UPDATE tracks
        SET status = ?,
            source = COALESCE(?, source),
            file_path = COALESCE(?, file_path),
            version = COALESCE(?, version),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (status, source, file_path, version, track_id),
    )

    db.commit()


def update_track_rights(
    db,
    track_id: int,
    *,
    license_url: str | None = None,
    rights_status: str = "unknown",
    download_allowed: bool | None = None,
    attribution: str | None = None,
    metadata_json: str | None = None,
) -> None:
    """
    Store rights and attribution information for a discovered track.

    download_allowed:
        True  = provider explicitly indicates download is allowed.
        False = provider explicitly indicates download is not allowed.
        None  = permission is unknown or has not been checked.
    """
    if rights_status not in {
        "unknown",
        "permitted",
        "restricted",
        "review_required",
    }:
        raise ValueError(f"Invalid rights status: {rights_status}")

    allowed_value = (
        None if download_allowed is None else int(download_allowed)
    )

    db.execute(
        """
        UPDATE tracks
        SET license_url = COALESCE(?, license_url),
            rights_status = ?,
            download_allowed = ?,
            attribution = COALESCE(?, attribution),
            metadata_json = COALESCE(?, metadata_json),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            license_url,
            rights_status,
            allowed_value,
            attribution,
            metadata_json,
            track_id,
        ),
    )

    db.commit()


def record_attempt(
    db,
    track_id,
    provider,
    attempt_number,
    outcome,
    detail=None,
):
    db.execute(
        """
        INSERT INTO attempts(
            track_id,
            provider,
            attempt_number,
            outcome,
            detail
        )
        VALUES(?, ?, ?, ?, ?)
        """,
        (
            track_id,
            provider,
            attempt_number,
            outcome,
            detail,
        ),
    )

    db.commit()


def get_attempts(db, track_id: int | None = None):
    if track_id is None:
        return db.execute(
            """
            SELECT *
            FROM attempts
            ORDER BY id
            """
        ).fetchall()

    return db.execute(
        """
        SELECT *
        FROM attempts
        WHERE track_id = ?
        ORDER BY id
        """,
        (track_id,),
    ).fetchall()


def is_paused(db) -> bool:
    row = db.execute(
        "SELECT pause_requested FROM control WHERE id = 1"
    ).fetchone()

    return bool(row[0]) if row else False


def set_paused(db, paused: bool):
    db.execute(
        """
        UPDATE control
        SET pause_requested = ?
        WHERE id = 1
        """,
        (int(paused),),
    )

    db.commit()
