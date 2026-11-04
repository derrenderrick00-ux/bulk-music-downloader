from __future__ import annotations
import sqlite3
from pathlib import Path
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
INSERT OR IGNORE INTO control(id, pause_requested) VALUES(1, 0);
"""

def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript(SCHEMA)
    return db

def add_track(db, title: str, artist: str) -> tuple[bool, int | None]:
    cur = db.execute(
        "INSERT OR IGNORE INTO tracks(title,artist) VALUES(?,?)",
        (title.strip(), artist.strip()),
    )
    db.commit()
    if cur.rowcount:
        return True, cur.lastrowid
    row = db.execute(
        "SELECT id FROM tracks WHERE title=? COLLATE NOCASE AND artist=? COLLATE NOCASE",
        (title.strip(), artist.strip()),
    ).fetchone()
    return False, row["id"] if row else None

def get_tracks(db, statuses=None):
    if statuses:
        marks = ",".join("?" for _ in statuses)
        return db.execute(f"SELECT * FROM tracks WHERE status IN ({marks}) ORDER BY id", statuses).fetchall()
    return db.execute("SELECT * FROM tracks ORDER BY id").fetchall()

def set_status(db, track_id, status, source=None, file_path=None, version=None):
    db.execute("""UPDATE tracks SET status=?, source=COALESCE(?,source),
        file_path=COALESCE(?,file_path), version=COALESCE(?,version),
        updated_at=CURRENT_TIMESTAMP WHERE id=?""",
        (status, source, file_path, version, track_id))
    db.commit()

def record_attempt(db, track_id, provider, attempt_number, outcome, detail=None):
    db.execute("""INSERT INTO attempts(track_id,provider,attempt_number,outcome,detail)
                  VALUES(?,?,?,?,?)""", (track_id, provider, attempt_number, outcome, detail))
    db.commit()

def is_paused(db):
    return bool(db.execute("SELECT pause_requested FROM control WHERE id=1").fetchone()[0])

def set_paused(db, paused: bool):
    db.execute("UPDATE control SET pause_requested=? WHERE id=1", (int(paused),))
    db.commit()
