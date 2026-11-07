from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

import httpx

from .base import MusicProvider, ProviderError
from ..matching import match_details, detect_version
from ..models import SearchResult


API = "https://api.audius.co/v1"


class AudiusProvider(MusicProvider):
    name = "audius"

    def __init__(
        self,
        api_key: str = "",
        user_agent: str = "BulkMusicDownloader/0.2",
    ):
        self.api_key = api_key
        self.headers = {
            "User-Agent": user_agent,
        }

        if api_key:
            self.headers["x-api-key"] = api_key

    def _request(self, endpoint: str, params=None, timeout=30):
        try:
            response = httpx.get(
                f"{API}{endpoint}",
                params=params or {},
                headers=self.headers,
                timeout=timeout,
                follow_redirects=True,
            )

            response.raise_for_status()
            return response.json()

        except Exception as exc:
            raise ProviderError(
                f"Audius API request failed: {exc}"
            ) from exc

    def search(
        self,
        title: str,
        artist: str,
        limit: int = 8,
    ) -> list[SearchResult]:

        query = f"{title} {artist}".strip()

        payload = self._request(
            "/tracks/search",
            params={
                "query": query,
                "limit": min(max(int(limit), 1), 100),
            },
        )

        tracks = payload.get("data", [])

        if not isinstance(tracks, list):
            raise ProviderError(
                "Audius returned an unexpected search response."
            )

        results = []

        for track in tracks:
            if not isinstance(track, dict):
                continue

            identifier = track.get("id")
            found_title = track.get("title")

            user = track.get("user") or {}
            found_artist = (
                user.get("name")
                or user.get("handle")
                or ""
            )

            if not identifier or not found_title:
                continue

            details = match_details(
                title,
                artist,
                str(found_title),
                str(found_artist),
            )

            downloadable = track.get("is_downloadable")

            # Unknown permission is not equivalent to permission.
            if downloadable is True:
                rights_status = "permitted"
            elif downloadable is False:
                rights_status = "restricted"
            else:
                rights_status = "unknown"

            permalink = track.get("permalink")

            if permalink:
                page_url = (
                    "https://audius.co/"
                    + str(permalink).lstrip("/")
                )
            else:
                page_url = (
                    f"https://audius.co/track/{quote(str(identifier))}"
                )

            license_value = track.get("license")

            results.append(
                SearchResult(
                    provider=self.name,
                    identifier=str(identifier),
                    title=str(found_title),
                    artist=str(found_artist),
                    url=page_url,
                    media_type="audio",
                    rights=(
                        str(license_value)
                        if license_value
                        else "Audius download permission"
                    ),
                    score=details["score"],
                    title_score=details["title_score"],
                    artist_score=details["artist_score"],
                    version=detect_version(str(found_title)),
                    version_match=details["version_match"],
                    download_allowed=downloadable,
                    rights_status=rights_status,
                    metadata=track,
                )
            )

        return sorted(
            results,
            key=lambda item: item.score,
            reverse=True,
        )

    def download(
        self,
        result: SearchResult,
        destination: Path,
        timeout: int,
    ) -> Path:

        if result.provider != self.name:
            raise ProviderError(
                "Audius cannot download a result from another provider."
            )

        if result.download_allowed is not True:
            raise ProviderError(
                "Audius has not explicitly marked this track downloadable."
            )

        endpoint = (
            f"/tracks/{quote(result.identifier, safe='')}/download"
        )

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        metadata = result.metadata or {}
        original_name = str(
            metadata.get("orig_filename") or ""
        )

        suffix = Path(original_name).suffix.lower()

        if suffix not in {
            ".mp3",
            ".m4a",
            ".wav",
            ".flac",
            ".ogg",
            ".aac",
        }:
            suffix = ".audio"

        if destination.suffix == ".audio":
            destination = destination.with_suffix(suffix)

        temporary = destination.with_suffix(
            destination.suffix + ".part"
        )

        try:
            with httpx.stream(
                "GET",
                f"{API}{endpoint}",
                params={},
                headers=self.headers,
                timeout=timeout,
                follow_redirects=True,
            ) as response:

                response.raise_for_status()

                content_type = response.headers.get(
                    "content-type", ""
                ).lower()

                if "text/html" in content_type:
                    raise ProviderError(
                        "Audius returned HTML instead of audio."
                    )

                with temporary.open("wb") as file:
                    for chunk in response.iter_bytes(128 * 1024):
                        file.write(chunk)

            if (
                not temporary.exists()
                or temporary.stat().st_size < 1024
            ):
                raise ProviderError(
                    "Audius download was empty or too small."
                )

            temporary.replace(destination)

            return destination

        except Exception as exc:
            temporary.unlink(missing_ok=True)

            if isinstance(exc, ProviderError):
                raise

            raise ProviderError(
                f"Audius download failed: {exc}"
            ) from exc
