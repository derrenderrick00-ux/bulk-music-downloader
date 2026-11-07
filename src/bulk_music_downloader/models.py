from dataclasses import dataclass
from typing import Any


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

    # Rights and provenance metadata.
    license_url: str | None = None
    rights_status: str = "unknown"
    download_allowed: bool | None = None
    attribution: str | None = None


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

    # More detailed matching information.
    title_score: float = 0.0
    artist_score: float = 0.0
    version_match: bool | None = None

    # Download permission is separate from identity matching.
    download_allowed: bool | None = None
    license_url: str | None = None
    attribution: str | None = None
    rights_status: str = "unknown"

    # Provider-specific metadata can be retained without
    # changing the core model every time a provider is added.
    metadata: dict[str, Any] | None = None
