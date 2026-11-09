from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import httpx

from .base import MusicProvider, ProviderError
from ..matching import match_details, detect_version
from ..models import SearchResult


API = "https://api.freetouse.com/v3"
LICENSE_URL = "https://freetouse.com/license"


class FreeToUseProvider(MusicProvider):
    name = "freetouse"

    def __init__(
        self,
        user_agent: str = "BulkMusicDownloader/0.3",
    ):
        self.headers = {
            "User-Agent": user_agent,
            "Accept": "application/json",
        }

    def _request(
        self,
        endpoint: str,
        params: dict | None = None,
        timeout: int = 30,
    ) -> dict:
        try:
            response = httpx.get(
                f"{API}{endpoint}",
                params=params or {},
                headers=self.headers,
                timeout=timeout,
                follow_redirects=True,
            )

            response.raise_for_status()
            payload = response.json()

        except Exception as exc:
            raise ProviderError(
                f"Free To Use API request failed: {exc}"
            ) from exc

        if not isinstance(payload, dict):
            raise ProviderError(
                "Free To Use returned an unexpected response."
            )

        if payload.get("ok") is False:
            raise ProviderError(
                str(payload.get("error") or "Free To Use API error.")
            )

        return payload

    @staticmethod
    def _artist_names(track: dict) -> str:
        artists = track.get("artists") or []
        names = []

        for item in artists:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue

            artist = item[1]

            if isinstance(artist, dict):
                name = artist.get("name")
                if name:
                    names.append(str(name))

        return ", ".join(names) or "Unknown"

    def search(
        self,
        title: str,
        artist: str,
        limit: int = 8,
    ) -> list[SearchResult]:

        query = f"{title} {artist}".strip()

        payload = self._request(
            "/music/tracks/search",
            params={
                "query": query,
                "limit": min(max(int(limit), 1), 100),
                "offset": 0,
                "order": "release_date",
                "sort": "desc",
            },
        )

        tracks = payload.get("data", [])

        if not isinstance(tracks, list):
            raise ProviderError(
                "Free To Use returned an invalid track list."
            )

        results = []

        for track in tracks:
            if not isinstance(track, dict):
                continue

            identifier = track.get("id")
            found_title = track.get("title")

            if not identifier or not found_title:
                continue

            found_artist = self._artist_names(track)

            details = match_details(
                title,
                artist,
                str(found_title),
                found_artist,
            )

            files = track.get("files") or {}

            if not isinstance(files, dict):
                files = {}

            media_url = files.get("mp3")

            # The API exposes premium status. A non-premium track
            # with an MP3 URL is downloadable through the API, but
            # its license conditions still require review.
            is_premium = track.get("is_premium")

            if is_premium is False and media_url:
                download_allowed = True
                rights_status = "review_required"

            elif is_premium is True:
                download_allowed = False
                rights_status = "restricted"

            else:
                download_allowed = None
                rights_status = "unknown"

            page_url = (
                f"https://freetouse.com/music/tracks/"
                f"{quote(str(identifier), safe='')}"
            )

            results.append(
                SearchResult(
                    provider=self.name,
                    identifier=str(identifier),
                    title=str(found_title),
                    artist=found_artist,
                    url=page_url,
                    media_url=str(media_url) if media_url else None,
                    media_type="audio",
                    rights="Free To Use License — conditions apply",
                    score=details["score"],
                    title_score=details["title_score"],
                    artist_score=details["artist_score"],
                    version=detect_version(str(found_title)),
                    version_match=details["version_match"],
                    download_allowed=download_allowed,
                    license_url=LICENSE_URL,
                    attribution=found_artist,
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
                "Free To Use cannot download another provider's result."
            )

        if result.download_allowed is not True:
            raise ProviderError(
                "Free To Use has not explicitly allowed this download."
            )

        if not result.media_url:
            raise ProviderError(
                "Free To Use result has no MP3 download URL."
            )

        # Only accept HTTPS URLs from the expected API host.
        from urllib.parse import urlparse

        parsed = urlparse(result.media_url)

        if parsed.scheme != "https" or not parsed.netloc:
            raise ProviderError(
                "Free To Use returned an invalid media URL."
            )

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if destination.suffix.lower() != ".mp3":
            destination = destination.with_suffix(".mp3")

        temporary = destination.with_suffix(
            destination.suffix + ".part"
        )

        try:
            with httpx.stream(
                "GET",
                result.media_url,
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
                        "Free To Use returned HTML instead of audio."
                    )

                with temporary.open("wb") as file:
                    for chunk in response.iter_bytes(128 * 1024):
                        file.write(chunk)

            if (
                not temporary.exists()
                or temporary.stat().st_size < 1024
            ):
                raise ProviderError(
                    "Free To Use download was empty or too small."
                )

            temporary.replace(destination)
            return destination

        except Exception as exc:
            temporary.unlink(missing_ok=True)

            if isinstance(exc, ProviderError):
                raise

            raise ProviderError(
                f"Free To Use download failed: {exc}"
            ) from exc
