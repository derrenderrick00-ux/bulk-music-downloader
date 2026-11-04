from abc import ABC, abstractmethod
from pathlib import Path
from ..models import SearchResult

class ProviderError(Exception):
    pass

class MusicProvider(ABC):
    name = "base"
    @abstractmethod
    def search(self, title: str, artist: str, limit: int = 8) -> list[SearchResult]:
        raise NotImplementedError
    @abstractmethod
    def download(self, result: SearchResult, destination: Path, timeout: int) -> Path:
        raise NotImplementedError
