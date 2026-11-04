from pathlib import Path
from .base import MusicProvider, ProviderError
from ..models import SearchResult

class TubidyProvider(MusicProvider):
    """Safe placeholder: no undocumented scraping or access-control bypass."""
    name = "tubidy"

    def search(self, title: str, artist: str, limit: int = 8) -> list[SearchResult]:
        raise ProviderError(
            "Tubidy automated search is not implemented: no supported public API "
            "or authorized integration was configured. Use an authorized provider "
            "or provide a permitted direct download URL."
        )

    def download(self, result: SearchResult, destination: Path, timeout: int) -> Path:
        raise ProviderError("Tubidy provider is not configured for automated downloads.")
