from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import httpx

from .base import MusicProvider, ProviderError
from ..models import SearchResult
from ..matching import score_match, detect_version


API = "https://archive.org/advancedsearch.php"


def _safe_query_value(value: str) -> str:
    return value.replace("\\", " ").replace('"', " ").strip()


class InternetArchiveProvider(MusicProvider):
    name = "internet_archive"

    def __init__(self, user_agent: str):
        self.headers = {"User-Agent": user_agent}

    def search(
        self,
        title: str,
        artist: str,
        limit: int = 8,
    ) -> list[SearchResult]:

        safe_title = _safe_query_value(title)
        safe_artist = _safe_query_value(artist)

        query = (
            f'(title:("{safe_title}") OR subject:("{safe_title}")) '
            f'AND '
            f'(creator:("{safe_artist}") OR subject:("{safe_artist}")) '
            f'AND mediatype:audio'
        )

        params = {
            "q": query,
            "fl[]": [
                "identifier",
                "title",
                "creator",
                "licenseurl",
            ],
            "rows": limit,
            "page": 1,
            "output": "json",
        }

        try:
            response = httpx.get(
                API,
                params=params,
                headers=self.headers,
                timeout=20,
                follow_redirects=True,
            )
            response.raise_for_status()

            docs = response.json().get(
                "response", {}
            ).get("docs", [])

        except Exception as exc:
            raise ProviderError(
                f"Internet Archive search failed: {exc}"
            ) from exc

        results = []

        for doc in docs:
            identifier = doc.get("identifier")

            if not identifier:
                continue

            found_title = str(doc.get("title", identifier))

            creator = doc.get("creator", "Unknown")

            if isinstance(creator, list):
                found_artist = ", ".join(str(item) for item in creator)
            else:
                found_artist = str(creator)

            results.append(
                SearchResult(
                    provider=self.name,
                    identifier=identifier,
                    title=found_title,
                    artist=found_artist,
                    url=(
                        "https://archive.org/details/"
                        f"{quote(identifier)}"
                    ),
                    score=score_match(
                        title,
                        artist,
                        found_title,
                        found_artist,
                    ),
                    version=detect_version(found_title),
                    rights=str(
                        doc.get(
                            "licenseurl",
                            "Rights not verified by this application",
                        )
                    ),
                )
            )

        results.sort(
            key=lambda result: result.score,
            reverse=True,
        )

        return results

    def _metadata(self, identifier: str, timeout: int):
        url = (
            "https://archive.org/metadata/"
            f"{quote(identifier)}"
        )

        response = httpx.get(
            url,
            headers=self.headers,
            timeout=timeout,
            follow_redirects=True,
        )

        response.raise_for_status()

        return response.json()

    def download(
        self,
        result: SearchResult,
        destination: Path,
        timeout: int,
    ) -> Path:

        try:
            metadata = self._metadata(
                result.identifier,
                timeout,
            )

            files = metadata.get("files", [])
            audio = []

            for item in files:
                name = item.get("name", "")
                file_format = str(
                    item.get("format", "")
                ).lower()

                is_audio = (
                    file_format in {
                        "mp3",
                        "ogg vorbis",
                        "flac",
                        "wav",
                        "advanced audio coding",
                    }
                    or name.lower().endswith(
                        (
                            ".mp3",
                            ".ogg",
                            ".flac",
                            ".wav",
                            ".m4a",
                            ".aac",
                        )
                    )
                )

                if item.get("source") == "original" and is_audio:
                    audio.append(item)

            if not audio:
                raise ProviderError(
                    "No downloadable audio file exposed in item metadata."
                )

            preferred = sorted(
                audio,
                key=lambda item: (
                    0
                    if str(item.get("name", "")).lower().endswith(".mp3")
                    else 1,
                    int(item.get("size", 0))
                    if str(item.get("size", "0")).isdigit()
                    else 0,
                ),
            )[0]

            filename = Path(preferred["name"]).name
            result.file_name = filename

            media_url = (
                "https://archive.org/download/"
                f"{quote(result.identifier)}/{quote(filename)}"
            )

            destination = destination.with_suffix(
                Path(filename).suffix or ".audio"
            )

            destination.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            temporary_file = destination.with_suffix(
                destination.suffix + ".part"
            )

            with httpx.stream(
                "GET",
                media_url,
                headers=self.headers,
                timeout=timeout,
                follow_redirects=True,
            ) as response:

                response.raise_for_status()

                with temporary_file.open("wb") as file:
                    for chunk in response.iter_bytes(1024 * 128):
                        file.write(chunk)

            if (
                not temporary_file.exists()
                or temporary_file.stat().st_size < 1024
            ):
                temporary_file.unlink(missing_ok=True)

                raise ProviderError(
                    "Downloaded file is empty or suspiciously small."
                )

            temporary_file.replace(destination)

            result.media_url = media_url
            result.file_name = filename

            return destination

        except ProviderError:
            raise

        except Exception as exc:
            raise ProviderError(
                f"Internet Archive download failed: {exc}"
            ) from exc
