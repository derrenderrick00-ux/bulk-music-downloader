from dataclasses import dataclass
from pathlib import Path

@dataclass
class Track:
    id: int
    title: str
    artist: str
    status: str
    source: str | None = None
    file_path: str | None = None
    version: str | None = None
    direct_url: str | None = None

@dataclass
class SearchResult:
    provider: str
    identifier: str
    title: str
    artist: str
    url: str
    media_url: str | None = None
    file_name: str | None = None
    media_type: str | None = None
    rights: str | None = None
    score: float = 0.0
    version: str = "unspecified"
