from __future__ import annotations

import json
import sqlite3
import unicodedata

from .config import DATA_DIR


DB_PATH = DATA_DIR / "downloads.db"


# ---------------------------------------------------------------------
# Database schema
# ---------------------------------------------------------------------

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
    active_queue INTEGER NOT NULL DEFAULT 1,
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

CREATE TABLE IF NOT EXISTS download_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title_key TEXT NOT NULL,
    artist_key TEXT NOT NULL,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    source TEXT,
    file_path TEXT NOT NULL,
    version TEXT,
    downloaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    original_track_id INTEGER,
    UNIQUE(title_key, artist_key)
);

CREATE INDEX IF NOT EXISTS idx_download_history_downloaded_at
ON download_history(downloaded_at);

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


TRACK_MIGRATIONS = {
    "license_url": "TEXT",
    "rights_status": "TEXT NOT NULL DEFAULT 'unknown'",
    "download_allowed": "INTEGER",
    "attribution": "TEXT",
    "metadata_json": "TEXT",
    "active_queue": "INTEGER NOT NULL DEFAULT 1",
}


CANDIDATE_SCHEMA = """
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

    score REAL NOT NULL DEFAULT 0,
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

    UNIQUE(track_id, provider, identifier),

    CHECK (
        review_status IN (
            'available',
            'pending_review',
            'approved',
            'rejected'
        )
    ),

    CHECK (
        rights_status IN (
            'unknown',
            'permitted',
            'restricted',
            'review_required'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_candidates_track
ON candidates(track_id);

CREATE INDEX IF NOT EXISTS idx_candidates_review
ON candidates(review_status);

CREATE INDEX IF NOT EXISTS idx_candidates_rights
ON candidates(rights_status);
"""


# ---------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------

def _migrate_tracks(db: sqlite3.Connection) -> None:
    """Apply safe, additive migrations to the existing tracks table."""

    existing = {
        row["name"]
        for row in db.execute("PRAGMA table_info(tracks)").fetchall()
    }

    for column, definition in TRACK_MIGRATIONS.items():
        if column not in existing:
            db.execute(
                f"ALTER TABLE tracks ADD COLUMN {column} {definition}"
            )


def _normalize_track_value(value: str) -> str:
    """Normalize text for case- and whitespace-insensitive matching."""

    normalized = unicodedata.normalize("NFKC", str(value or ""))
    return " ".join(normalized.casefold().split())


def _track_key(title: str, artist: str) -> tuple[str, str]:
    return (
        _normalize_track_value(title),
        _normalize_track_value(artist),
    )


def _migrate_download_history(db: sqlite3.Connection) -> None:
    """
    Preserve previously completed downloads.

    Existing completed records with a non-empty file path are
    migrated into permanent download history.

    INSERT OR IGNORE makes this migration idempotent and preserves
    existing history timestamps.
    """

    rows = db.execute(
        """
        SELECT
            id,
            title,
            artist,
            source,
            file_path,
            version,
            updated_at
        FROM tracks
        WHERE status = 'completed'
          AND file_path IS NOT NULL
          AND TRIM(file_path) != ''
        ORDER BY updated_at DESC, id DESC
        """
    ).fetchall()

    for row in rows:
        title_key, artist_key = _track_key(
            row["title"],
            row["artist"],
        )

        if not title_key or not artist_key:
            continue

        db.execute(
            """
            INSERT OR IGNORE INTO download_history (
                title_key,
                artist_key,
                title,
                artist,
                source,
                file_path,
                version,
                downloaded_at,
                original_track_id
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?,
                COALESCE(?, CURRENT_TIMESTAMP),
                ?
            )
            """,
            (
                title_key,
                artist_key,
                row["title"],
                row["artist"],
                row["source"],
                row["file_path"],
                row["version"],
                row["updated_at"],
                row["id"],
            ),
        )


def _record_download_history(
    db: sqlite3.Connection,
    track_id: int,
) -> None:
    """Record a successfully completed download permanently."""

    row = db.execute(
        """
        SELECT id, title, artist, source, file_path, version
        FROM tracks
        WHERE id = ?
        """,
        (track_id,),
    ).fetchone()

    if row is None:
        return

    if not row["file_path"] or not str(row["file_path"]).strip():
        return

    title_key, artist_key = _track_key(
        row["title"],
        row["artist"],
    )

    if not title_key or not artist_key:
        return

    db.execute(
        """
        INSERT INTO download_history (
            title_key,
            artist_key,
            title,
            artist,
            source,
            file_path,
            version,
            original_track_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)

        ON CONFLICT(title_key, artist_key)
        DO UPDATE SET
            title = excluded.title,
            artist = excluded.artist,
            source = excluded.source,
            file_path = excluded.file_path,
            version = excluded.version,
            original_track_id = excluded.original_track_id,
            downloaded_at = CURRENT_TIMESTAMP
        """,
        (
            title_key,
            artist_key,
            row["title"],
            row["artist"],
            row["source"],
            row["file_path"],
            row["version"],
            row["id"],
        ),
    )


# ---------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------

def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row

    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA journal_mode=WAL")

    db.executescript(SCHEMA)

    _migrate_tracks(db)
    _migrate_download_history(db)

    db.executescript(CANDIDATE_SCHEMA)

    db.commit()
    return db


# ---------------------------------------------------------------------
# Track management
# ---------------------------------------------------------------------

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


def replace_queue(db, songs) -> dict[str, int]:
    """
    Replace the active queue without deleting historical records.

    Previously downloaded tracks are restored as completed.
    Other tracks are restored as pending.

    Attempts, candidates, and download history are preserved.

    The operation is atomic: failure rolls back the replacement.
    """

    prepared = []
    seen = set()
    duplicates = 0

    # Validate and deduplicate before touching the database.
    for entry in songs:
        if not isinstance(entry, (tuple, list)) or len(entry) != 2:
            raise ValueError(
                "Every song must contain a title and artist."
            )

        title = str(entry[0] or "").strip()
        artist = str(entry[1] or "").strip()

        if not title or not artist:
            raise ValueError(
                "Track title and artist cannot be empty."
            )

        key = _track_key(title, artist)

        if not all(key):
            raise ValueError("Invalid track title or artist.")

        if key in seen:
            duplicates += 1
            continue

        seen.add(key)
        prepared.append((title, artist, key))

    if not prepared:
        raise ValueError(
            "Cannot replace the queue with an empty song list."
        )

    db.execute("SAVEPOINT replace_active_queue")

    try:
        history_rows = db.execute(
            "SELECT * FROM download_history"
        ).fetchall()

        history_by_key = {
            (row["title_key"], row["artist_key"]): row
            for row in history_rows
            if row["file_path"]
        }

        # Include inactive tracks so they can be reactivated.
        existing_rows = db.execute(
            "SELECT id, title, artist FROM tracks"
        ).fetchall()

        tracks_by_key = {}

        for row in existing_rows:
            key = _track_key(row["title"], row["artist"])
            tracks_by_key.setdefault(key, row)

        # Archive all existing tracks without deleting them.
        db.execute(
            """
            UPDATE tracks
            SET active_queue = 0
            """
        )

        queued = 0
        already_downloaded = 0

        for title, artist, key in prepared:
            history = history_by_key.get(key)
            existing = tracks_by_key.get(key)

            if history:
                status = "completed"
                source = history["source"]
                file_path = history["file_path"]
                version = history["version"]

                already_downloaded += 1
            else:
                status = "pending"
                source = None
                file_path = None
                version = None

                queued += 1

            if existing is not None:
                db.execute(
                    """
                    UPDATE tracks
                    SET active_queue = 1,
                        status = ?,
                        source = ?,
                        file_path = ?,
                        version = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        status,
                        source,
                        file_path,
                        version,
                        existing["id"],
                    ),
                )
            else:
                db.execute(
                    """
                    INSERT INTO tracks (
                        title,
                        artist,
                        status,
                        source,
                        file_path,
                        version,
                        active_queue
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 1)
                    """,
                    (
                        title,
                        artist,
                        status,
                        source,
                        file_path,
                        version,
                    ),
                )

        db.execute("RELEASE SAVEPOINT replace_active_queue")
        db.commit()

    except Exception:
        db.execute("ROLLBACK TO SAVEPOINT replace_active_queue")
        db.execute("RELEASE SAVEPOINT replace_active_queue")
        raise

    return {
        "queued": queued,
        "already_downloaded": already_downloaded,
        "duplicates": duplicates,
    }


def get_tracks(
    db,
    statuses=None,
    include_inactive: bool = False,
):
    """Retrieve active queue tracks by default."""

    clauses = []
    params = []

    if not include_inactive:
        clauses.append("active_queue = 1")

    if statuses:
        marks = ",".join("?" for _ in statuses)
        clauses.append(f"status IN ({marks})")
        params.extend(statuses)

    where = (
        "WHERE " + " AND ".join(clauses)
        if clauses
        else ""
    )

    return db.execute(
        f"""
        SELECT *
        FROM tracks
        {where}
        ORDER BY id
        """,
        tuple(params),
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

    if status == "completed":
        _record_download_history(db, track_id)

    db.commit()


# ---------------------------------------------------------------------
# Track rights
# ---------------------------------------------------------------------

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


# ---------------------------------------------------------------------
# Download attempts
# ---------------------------------------------------------------------

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
            "SELECT * FROM attempts ORDER BY id"
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


# ---------------------------------------------------------------------
# Queue controls
# ---------------------------------------------------------------------

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


# ---------------------------------------------------------------------
# Phase 2.6: persistent search candidates and review workflow
# ---------------------------------------------------------------------

def _bool_to_db(value: bool | None) -> int | None:
    if value is None:
        return None
    return int(bool(value))


def _bool_from_db(value: int | None) -> bool | None:
    if value is None:
        return None
    return bool(value)


def save_candidates(db, track_id: int, candidates) -> int:
    """
    Persist search results for a track.

    Safe candidates are marked 'available'. Other candidates require
    review. Existing approval/rejection decisions are preserved on
    re-search, except that a candidate which is no longer rights-safe
    loses its approval.
    """

    saved = 0

    for item in candidates:
        rights_status = getattr(item, "rights_status", "unknown")
        download_allowed = getattr(item, "download_allowed", None)

        if rights_status not in {
            "unknown",
            "permitted",
            "restricted",
            "review_required",
        }:
            rights_status = "unknown"

        safe_to_download = (
            rights_status == "permitted"
            and download_allowed is True
        )

        default_review_status = (
            "available" if safe_to_download else "pending_review"
        )

        metadata = getattr(item, "metadata", None)

        metadata_json = (
            json.dumps(metadata, ensure_ascii=False, default=str)
            if metadata is not None
            else None
        )

        db.execute(
            """
            INSERT INTO candidates (
                track_id,
                provider,
                identifier,
                title,
                artist,
                page_url,
                media_url,
                file_name,
                media_type,
                rights,
                rights_status,
                download_allowed,
                license_url,
                attribution,
                score,
                title_score,
                artist_score,
                version,
                version_match,
                metadata_json,
                review_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?)

            ON CONFLICT(track_id, provider, identifier)
            DO UPDATE SET
                title = excluded.title,
                artist = excluded.artist,
                page_url = excluded.page_url,
                media_url = excluded.media_url,
                file_name = excluded.file_name,
                media_type = excluded.media_type,
                rights = excluded.rights,
                rights_status = excluded.rights_status,
                download_allowed = excluded.download_allowed,
                license_url = excluded.license_url,
                attribution = excluded.attribution,
                score = excluded.score,
                title_score = excluded.title_score,
                artist_score = excluded.artist_score,
                version = excluded.version,
                version_match = excluded.version_match,
                metadata_json = excluded.metadata_json,
                review_status = CASE
                    WHEN excluded.rights_status != 'permitted'
                         OR excluded.download_allowed != 1
                    THEN 'pending_review'
                    WHEN candidates.review_status IN ('approved', 'rejected')
                    THEN candidates.review_status
                    ELSE excluded.review_status
                END,
                reviewed_at = CASE
                    WHEN excluded.rights_status != 'permitted'
                         OR excluded.download_allowed != 1
                    THEN NULL
                    ELSE candidates.reviewed_at
                END,
                review_note = CASE
                    WHEN excluded.rights_status != 'permitted'
                         OR excluded.download_allowed != 1
                    THEN NULL
                    ELSE candidates.review_note
                END,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                track_id,
                item.provider,
                item.identifier,
                item.title,
                item.artist,
                item.url,
                item.media_url,
                item.file_name,
                item.media_type,
                item.rights,
                rights_status,
                _bool_to_db(download_allowed),
                item.license_url,
                item.attribution,
                float(item.score),
                float(item.title_score),
                float(item.artist_score),
                item.version,
                _bool_to_db(item.version_match),
                metadata_json,
                default_review_status,
            ),
        )

        saved += 1

    db.commit()
    return saved


def get_candidates(
    db,
    *,
    track_id: int | None = None,
    review_status: str | None = None,
):
    """Retrieve persisted candidates, optionally filtered."""

    clauses = []
    params = []

    if track_id is not None:
        clauses.append("track_id = ?")
        params.append(track_id)

    if review_status is not None:
        if review_status not in {
            "available",
            "pending_review",
            "approved",
            "rejected",
        }:
            raise ValueError(f"Invalid review status: {review_status}")

        clauses.append("review_status = ?")
        params.append(review_status)

    where = (
        "WHERE " + " AND ".join(clauses)
        if clauses
        else ""
    )

    return db.execute(
        f"""
        SELECT *
        FROM candidates
        {where}
        ORDER BY score DESC, id
        """,
        tuple(params),
    ).fetchall()


def get_candidate(db, candidate_id: int):
    return db.execute(
        "SELECT * FROM candidates WHERE id = ?",
        (candidate_id,),
    ).fetchone()


def review_candidate(
    db,
    candidate_id: int,
    decision: str,
    note: str | None = None,
) -> None:
    """
    Approve or reject a candidate.

    Approval is refused unless the provider has explicitly marked
    the candidate permitted and download_allowed=True.
    """

    if decision not in {"approved", "rejected"}:
        raise ValueError("Decision must be 'approved' or 'rejected'.")

    candidate = get_candidate(db, candidate_id)

    if candidate is None:
        raise ValueError(f"Candidate {candidate_id} does not exist.")

    if decision == "approved":
        if (
            candidate["rights_status"] != "permitted"
            or candidate["download_allowed"] != 1
        ):
            raise ValueError(
                "Cannot approve for download: rights are not verified "
                "as permitted by the provider."
            )

    db.execute(
        """
        UPDATE candidates
        SET review_status = ?,
            review_note = ?,
            reviewed_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (decision, note, candidate_id),
    )

    db.commit()


def get_downloadable_candidates(db, track_id: int):
    """
    Return only candidates that pass both rights and review checks.
    """

    return db.execute(
        """
        SELECT *
        FROM candidates
        WHERE track_id = ?
          AND rights_status = 'permitted'
          AND download_allowed = 1
          AND review_status IN ('available', 'approved')
        ORDER BY score DESC, id
        """,
        (track_id,),
    ).fetchall()


def candidate_row_to_dict(row) -> dict:
    """Convert a SQLite candidate row into a plain dictionary."""

    result = dict(row)

    result["download_allowed"] = _bool_from_db(
        result["download_allowed"]
    )

    result["version_match"] = _bool_from_db(
        result["version_match"]
    )

    try:
        result["metadata"] = (
            json.loads(result["metadata_json"])
            if result["metadata_json"]
            else None
        )
    except (TypeError, json.JSONDecodeError):
        result["metadata"] = None

    return result