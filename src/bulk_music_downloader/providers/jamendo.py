from __future__ import annotations

from pathlib import Path
from urllib import response

import httpx

from .base import MusicProvider, ProviderError
from ..matching import match_details, detect_version
from ..models import SearchResult


API = "https://api.jamendo.com/v3.0/tracks/"

ROTATABLE_HTTP_STATUSES = {401, 403, 429}

ROTATABLE_ERROR_TERMS = (
    "invalid client",
    "client_id",
    "client id",
    "unauthorized",
    "forbidden",
    "authentication",
    "rate limit",
    "rate-limit",
    "too many requests",
    "quota exceeded",
)


class JamendoProvider(MusicProvider):
    name = "jamendo"

    def __init__(
        self,
        client_id: str = "",
        user_agent: str = "BulkMusicDownloader/0.2",
        client_ids: list[str] | None = None,
    ):
        self.client_ids = self._normalize_client_ids(
            client_ids or [client_id]
        )

        # Backward compatibility for code that reads client_id.
        self.client_id = (
            self.client_ids[0] if self.client_ids else ""
        )

        self.headers = {
            "User-Agent": user_agent,
        }

    @staticmethod
    def _normalize_client_ids(values) -> list[str]:
        cleaned = []
        seen = set()

        for value in values:
            if not isinstance(value, str):
                continue

            client_id = value.strip()

            if client_id and client_id not in seen:
                cleaned.append(client_id)
                seen.add(client_id)

        return cleaned

    @staticmethod
    def _is_rotatable_api_error(headers: dict) -> bool:
        message = str(
            headers.get("error_message", "")
        ).lower()

        code = str(
            headers.get("code", "")
        ).lower()

        combined = f"{message} {code}"

        return any(
            term in combined
            for term in ROTATABLE_ERROR_TERMS
        )

    def _request_payload(self, client_id: str, title: str, artist: str, limit: int):
        params = {
            "client_id": client_id,
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

        except httpx.HTTPError:
            raise ProviderError(
                "Jamendo search failed due to a network error."
            ) from None

        # Some existing test doubles do not expose status_code.
        # Treat those as successful responses for backward compatibility.
        status_code = getattr(response, "status_code", 200)

        if status_code in ROTATABLE_HTTP_STATUSES:
            return None, True

        if status_code >= 400:
            raise ProviderError(
                f"Jamendo search failed with HTTP {status_code}."
            )

        try:
            payload = response.json()

        except (ValueError, TypeError):
            raise ProviderError(
                "Jamendo returned invalid JSON."
            ) from None

        if not isinstance(payload, dict):
            raise ProviderError(
                "Jamendo returned an unexpected response."
            )

        headers = payload.get("headers", {})

        if not isinstance(headers, dict):
            raise ProviderError(
                "Jamendo returned malformed response headers."
            )

        if str(headers.get("status", "")).lower() == "failed":
            if self._is_rotatable_api_error(headers):
                return None, True

            raise ProviderError(
                "Jamendo reported a search failure."
            )

        return payload, False

    def search(
        self,
        title: str,
        artist: str,
        limit: int = 8,
    ) -> list[SearchResult]:

        if not self.client_ids:
            raise ProviderError(
                "Jamendo requires a developer client ID. "
                "Configure JAMENDO_CLIENT_ID or JAMENDO_CLIENT_IDS."
            )

        payload = None

        for index, client_id in enumerate(self.client_ids):
            payload, should_rotate = self._request_payload(
                client_id,
                title,
                artist,
                limit,
            )

            if not should_rotate:
                break

            # Every configured ID is attempted at most once.
            if index == len(self.client_ids) - 1:
                raise ProviderError(
                    "Jamendo rejected all configured client IDs."
                )

        if payload is None:
            raise ProviderError(
                "Jamendo search could not be completed."
            )

        tracks = payload.get("results", [])

        if not isinstance(tracks, list):
            raise ProviderError(
                "Jamendo returned an unexpected results structure."
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
                "Jamendo download failed."
            ) from None