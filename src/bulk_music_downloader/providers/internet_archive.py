from __future__ import annotations
import re
from pathlib import Path
from urllib.parse import quote
import httpx
from .base import MusicProvider, ProviderError
from ..models import SearchResult
from ..matching import score_match, detect_version

API = "https://archive.org/advancedsearch.php"

class InternetArchiveProvider(MusicProvider):
    name = "internet_archive"

    def __init__(self, user_agent: str):
        self.headers = {"User-Agent": user_agent}

    def search(self, title: str, artist: str, limit: int = 8) -> list[SearchResult]:
        query = f'(title:("{title}") OR subject:("{title}")) AND mediatype:audio'
        params = {"q": query, "fl[]": ["identifier", "title", "creator", "licenseurl"],
                  "rows": limit, "page": 1, "output": "json"}
        try:
            response = httpx.get(API, params=params, headers=self.headers, timeout=20, follow_redirects=True)
            response.raise_for_status()
            docs = response.json().get("response", {}).get("docs", [])
        except Exception as exc:
            raise ProviderError(f"Internet Archive search failed: {exc}") from exc
        results = []
        for doc in docs:
            identifier = doc.get("identifier")
            if not identifier:
                continue
            found_title = str(doc.get("title", identifier))
            found_artist = str(doc.get("creator", "Unknown"))
            results.append(SearchResult(
                provider=self.name, identifier=identifier, title=found_title,
                artist=found_artist, url=f"https://archive.org/details/{quote(identifier)}",
                score=score_match(title, artist, found_title, found_artist),
                version=detect_version(found_title),
                rights=str(doc.get("licenseurl", "Rights not verified by this application")),
            ))
        results.sort(key=lambda x: x.score, reverse=True)
        return results

    def _metadata(self, identifier: str, timeout: int):
        url = f"https://archive.org/metadata/{quote(identifier)}"
        r = httpx.get(url, headers=self.headers, timeout=timeout, follow_redirects=True)
        r.raise_for_status()
        return r.json()

    def download(self, result: SearchResult, destination: Path, timeout: int) -> Path:
        try:
            metadata = self._metadata(result.identifier, timeout)
            files = metadata.get("files", [])
            audio = []
            for item in files:
                name = item.get("name", "")
                fmt = str(item.get("format", "")).lower()
                if item.get("source") == "original" and (
                    fmt in {"mp3", "ogg vorbis", "flac", "wav", "advanced audio coding"}
                    or name.lower().endswith((".mp3", ".ogg", ".flac", ".wav", ".m4a", ".aac"))
                ):
                    audio.append(item)
            if not audio:
                raise ProviderError("No downloadable audio file exposed in item metadata.")
            preferred = sorted(audio, key=lambda x: (
                0 if str(x.get("name", "")).lower().endswith(".mp3") else 1,
                int(x.get("size", 0)) if str(x.get("size", "0")).isdigit() else 0
            ))[0]
            filename = Path(preferred["name"]).name
            result.file_name = filename
            media_url = f"https://archive.org/download/{quote(result.identifier)}/{quote(filename)}"
            destination = destination.with_suffix(Path(filename).suffix or ".audio")
            destination.parent.mkdir(parents=True, exist_ok=True)
            temp = destination.with_suffix(destination.suffix + ".part")
            with httpx.stream("GET", media_url, headers=self.headers, timeout=timeout, follow_redirects=True) as resp:
                resp.raise_for_status()
                with temp.open("wb") as f:
                    for chunk in resp.iter_bytes(1024 * 128):
                        f.write(chunk)
            if not temp.exists() or temp.stat().st_size < 1024:
                temp.unlink(missing_ok=True)
                raise ProviderError("Downloaded file is empty or suspiciously small.")
            temp.replace(destination)
            result.media_url = media_url
            result.file_name = filename
            return destination
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"Internet Archive download failed: {exc}") from exc
