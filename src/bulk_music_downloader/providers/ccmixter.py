from __future__ import annotations

from pathlib import Path
from urllib.parse import quote, urlparse

import httpx

from .base import MusicProvider, ProviderError
from ..matching import match_details, detect_version
from ..models import SearchResult


API = "https://ccmixter.org/api/query"


class CcMixterProvider(MusicProvider):
    name = "ccmixter"

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
        params: dict,
        timeout: int = 30,
    ):
        try:
            response = httpx.get(
                API,
                params=params,
                headers=self.headers,
                timeout=timeout,
                follow_redirects=True,
            )

            response.raise_for_status()
            return response.json()

        except Exception as exc:
            raise ProviderError(
                f"ccMixter API request failed: {exc}"
            ) from exc

    @staticmethod
    def _extract_rows(payload) -> list[dict]:
        """
        ccHost installations can return JSON in different shapes.
        Accept common list and dictionary response structures.
        """
        if isinstance(payload, list):
            return [
                item for item in payload
                if isinstance(item, dict)
            ]

        if not isinstance(payload, dict):
            return []

        for key in (
            "results",
            "data",
            "uploads",
            "items",
        ):
            value = payload.get(key)

            if isinstance(value, list):
                return [
                    item for item in value
                    if isinstance(item, dict)
                ]

            if isinstance(value, dict):
                nested = CcMixterProvider._extract_rows(value)
                if nested:
                    return nested

        # Some ccHost responses wrap the actual result list
        # in the first value of a numeric-keyed object.
        for value in payload.values():
            if isinstance(value, list):
                rows = [
                    item for item in value
                    if isinstance(item, dict)
                ]
                if rows:
                    return rows

        return []

    @staticmethod
    def _first_value(item: dict, *keys):
        for key in keys:
            value = item.get(key)

            if value not in (None, ""):
                return value

        return None

    @staticmethod
    def _license_url(item: dict) -> str | None:
        value = CcMixterProvider._first_value(
            item,
            "license_url",
            "licenseurl",
            "license",
            "license_uri",
        )

        if isinstance(value, dict):
            value = (
                value.get("url")
                or value.get("license_url")
            )

        if not isinstance(value, str):
            return None

        if value.startswith("https://creativecommons.org/"):
            return value

        if value.startswith("http://creativecommons.org/"):
            return value

        return None

    @staticmethod
    def _page_url(item: dict, identifier: str) -> str:
        value = CcMixterProvider._first_value(
            item,
            "url",
            "upload_url",
            "page_url",
            "permalink",
        )

        if isinstance(value, str) and value.startswith("https://"):
            return value

        return (
            "https://ccmixter.org/files/"
            + quote(identifier, safe="")
        )

    @staticmethod
    def _media_url(item: dict) -> str | None:
        value = CcMixterProvider._first_value(
            item,
            "download_url",
            "download",
            "file_url",
            "media_url",
            "download_link",
        )

        if isinstance(value, dict):
            value = value.get("url")

        if not isinstance(value, str):
            return None

        parsed = urlparse(value)

        if parsed.scheme != "https" or not parsed.netloc:
            return None

        return value

    def search(
        self,
        title: str,
        artist: str,
        limit: int = 8,
    ) -> list[SearchResult]:

        query = f"{title} {artist}".strip()

        payload = self._request(
            {
                "f": "json",
                "datasource": "uploads",
                "dataview": "info",
                "search": query,
                "search_type": "all",
                "limit": min(max(int(limit), 1), 100),
                "offset": 0,
            }
        )

        rows = self._extract_rows(payload)

        results = []

        for item in rows:
            identifier = self._first_value(
                item,
                "upload_id",
                "id",
                "file_id",
            )

            found_title = self._first_value(
                item,
                "upload_name",
                "name",
                "title",
                "file_name",
            )

            found_artist = self._first_value(
                item,
                "artist",
                "user_full_name",
                "fullname",
                "user_name",
                "username",
                "user",
            )

            if not identifier or not found_title:
                continue

            found_artist = str(found_artist or "Unknown")

            details = match_details(
                title,
                artist,
                str(found_title),
                found_artist,
            )

            license_url = self._license_url(item)
            media_url = self._media_url(item)

            # A result is considered downloadable only if the API
            # provides both a direct HTTPS media URL and a
            # recognizable Creative Commons license URL.
            if license_url and media_url:
                download_allowed = True
                rights_status = "review_required"
            elif license_url:
                download_allowed = False
                rights_status = "review_required"
            else:
                download_allowed = None
                rights_status = "unknown"

            attribution = self._first_value(
                item,
                "attribution",
                "credit",
                "artist",
                "user_full_name",
                "fullname",
            )

            results.append(
                SearchResult(
                    provider=self.name,
                    identifier=str(identifier),
                    title=str(found_title),
                    artist=found_artist,
                    url=self._page_url(item, str(identifier)),
                    media_url=media_url,
                    media_type="audio",
                    rights=license_url or "License not verified",
                    score=details["score"],
                    title_score=details["title_score"],
                    artist_score=details["artist_score"],
                    version=detect_version(str(found_title)),
                    version_match=details["version_match"],
                    download_allowed=download_allowed,
                    license_url=license_url,
                    attribution=(
                        str(attribution)
                        if attribution
                        else None
                    ),
                    rights_status=rights_status,
                    metadata=item,
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
                "ccMixter cannot download another provider's result."
            )

        if result.download_allowed is not True:
            raise ProviderError(
                "ccMixter has not established download permission."
            )

        if not result.license_url:
            raise ProviderError(
                "ccMixter result has no verified license URL."
            )

        if not result.media_url:
            raise ProviderError(
                "ccMixter result has no direct media URL."
            )

        license_host = urlparse(result.license_url).netloc.lower()

        if not license_host.endswith("creativecommons.org"):
            raise ProviderError(
                "ccMixter license URL is not a recognized Creative Commons URL."
            )

        media = urlparse(result.media_url)

        if media.scheme != "https" or not media.netloc:
            raise ProviderError(
                "ccMixter media URL is invalid."
            )

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        suffix = Path(media.path).suffix.lower()

        if suffix not in {
            ".mp3",
            ".ogg",
            ".wav",
            ".flac",
            ".m4a",
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
                        "ccMixter returned HTML instead of audio."
                    )

                with temporary.open("wb") as file:
                    for chunk in response.iter_bytes(128 * 1024):
                        file.write(chunk)

            if (
                not temporary.exists()
                or temporary.stat().st_size < 1024
            ):
                raise ProviderError(
                    "ccMixter download was empty or too small."
                )

            temporary.replace(destination)
            return destination

        except Exception as exc:
            temporary.unlink(missing_ok=True)

            if isinstance(exc, ProviderError):
                raise

            raise ProviderError(
                f"ccMixter download failed: {exc}"
            ) from exc
