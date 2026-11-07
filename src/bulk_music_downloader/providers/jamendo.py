from __future__ import annotations

from pathlib import Path

import httpx

from .base import MusicProvider, ProviderError
from ..matching import match_details, detect_version
from ..models import SearchResult


API = "https://api.jamendo.com/v3.0/tracks/"


class JamendoProvider(MusicProvider):
    name = "jamendo"

    def __init__(
        self,
        client_id: str = "",
        user_agent: str = "BulkMusicDownloader/0.2",
    ):
        self.client_id = client_id
        self.headers = {
            "User-Agent": user_agent,
        }

    def search(
        self,
        title: str,
        artist: str,
        limit: int = 8,
    ) -> list[SearchResult]:

        if not self.client_id:
            raise ProviderError(
                "Jamendo requires a developer client ID. "
                "Set JAMENDO_CLIENT_ID before searching."
            )

        params = {
            "client_id": self.client_id,
            "format": "json",
            "namesearch": title,
            "artist_name": artist,
            "limit": min(max(int(limit), 1), 200),
            "include": "licenses",
            "audiodlformat": "mp32",
        }

        try:
            response = httpx.get(
                API,
                params=params,
                headers=self.headers,
                timeout=30,
                follow_redirects=True,
            )

            response.raise_for_status()
            payload = response.json()

        except Exception as exc:
            raise ProviderError(
                f"Jamendo search failed: {exc}"
            ) from exc

        headers = payload.get("headers", {})

        if headers.get("status") == "failed":
            raise ProviderError(
                headers.get("error_message")
                or "Jamendo reported a failed search."
            )

        tracks = payload.get("results", [])

        if not isinstance(tracks, list):
            raise ProviderError(
                "Jamendo returned an unexpected response."
            )

        results = []

        for track in tracks:
            if not isinstance(track, dict):
                continue

            identifier = track.get("id")
            found_title = track.get("name")
            found_artist = track.get("artist_name")

            if not identifier or not found_title or not found_artist:
                continue

            details = match_details(
                title,
                artist,
                str(found_title),
                str(found_artist),
            )

            allowed = track.get("audiodownload_allowed")
            download_url = track.get("audiodownload") or ""

            # Require both the explicit permission flag and URL.
            if allowed is True and download_url:
                rights_status = "permitted"
                permitted = True

            elif allowed is False:
                rights_status = "restricted"
                permitted = False

            else:
                rights_status = "unknown"
                permitted = None

            license_url = (
                track.get("license_ccurl")
                or track.get("license_url")
            )

            results.append(
                SearchResult(
                    provider=self.name,
                    identifier=str(identifier),
                    title=str(found_title),
                    artist=str(found_artist),
                    url=(
                        track.get("shareurl")
                        or f"https://www.jamendo.com/track/{identifier}"
                    ),
                    media_url=download_url or None,
                    media_type="audio",
                    rights=(
                        str(license_url)
                        if license_url
                        else "Jamendo download permission"
                    ),
                    score=details["score"],
                    title_score=details["title_score"],
                    artist_score=details["artist_score"],
                    version=detect_version(str(found_title)),
                    version_match=details["version_match"],
                    download_allowed=permitted,
                    license_url=license_url,
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
                "Jamendo cannot download a result from another provider."
            )

        if result.download_allowed is not True:
            raise ProviderError(
                "Jamendo has not explicitly permitted this download."
            )

        if not result.media_url:
            raise ProviderError(
                "Jamendo did not provide an authorized download URL."
            )

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

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
                        "Jamendo returned HTML instead of audio."
                    )

                with temporary.open("wb") as file:
                    for chunk in response.iter_bytes(128 * 1024):
                        file.write(chunk)

            if (
                not temporary.exists()
                or temporary.stat().st_size < 1024
            ):
                raise ProviderError(
                    "Jamendo download was empty or too small."
                )

            temporary.replace(destination)

            return destination

        except Exception as exc:
            temporary.unlink(missing_ok=True)

            if isinstance(exc, ProviderError):
                raise

            raise ProviderError(
                f"Jamendo download failed: {exc}"
            ) from exc
