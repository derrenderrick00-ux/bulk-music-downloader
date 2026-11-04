from pathlib import Path
import httpx
from .base import MusicProvider, ProviderError
from ..models import SearchResult

class DirectURLProvider(MusicProvider):
    name = "direct_url"
    def search(self, title: str, artist: str, limit: int = 8) -> list[SearchResult]:
        return []

    def download(self, result: SearchResult, destination: Path, timeout: int) -> Path:
        if not result.media_url:
            raise ProviderError("No authorized direct URL supplied for this track.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp = destination.with_suffix(destination.suffix + ".part")
        try:
            with httpx.stream("GET", result.media_url, timeout=timeout, follow_redirects=True) as resp:
                resp.raise_for_status()
                ctype = resp.headers.get("content-type", "").lower()
                if "text/html" in ctype:
                    raise ProviderError("URL returned HTML, not an audio file.")
                with temp.open("wb") as f:
                    for chunk in resp.iter_bytes(128 * 1024):
                        f.write(chunk)
            if temp.stat().st_size < 1024:
                raise ProviderError("Downloaded file is empty or suspiciously small.")
            temp.replace(destination)
            return destination
        except Exception as exc:
            temp.unlink(missing_ok=True)
            if isinstance(exc, ProviderError):
                raise
            raise ProviderError(str(exc)) from exc
