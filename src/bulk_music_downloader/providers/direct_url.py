from __future__ import annotations

import ipaddress
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .base import MusicProvider, ProviderError
from ..models import SearchResult


AUDIO_EXTENSIONS = {
    ".mp3",
    ".ogg",
    ".flac",
    ".wav",
    ".m4a",
    ".aac",
    ".opus",
}

AUDIO_CONTENT_TYPES = (
    "audio/",
    "application/ogg",
    "application/octet-stream",
)


def _validate_media_url(url: str):
    """Validate a direct media URL before making a request."""

    try:
        parsed = urlparse(url)
        hostname = parsed.hostname

        if (
            parsed.scheme != "https"
            or not hostname
            or not parsed.netloc
        ):
            raise ProviderError(
                "Direct media URL must use HTTPS and have a hostname."
            )

        if parsed.username or parsed.password:
            raise ProviderError(
                "Direct media URL must not contain embedded credentials."
            )

        hostname = hostname.lower().rstrip(".")

        if hostname == "localhost" or hostname.endswith(".localhost"):
            raise ProviderError(
                "Localhost media URLs are not allowed."
            )

        # Reject literal IP addresses that are not globally routable.
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            address = None

        if address is not None and not address.is_global:
            raise ProviderError(
                "Private, reserved, and local IP addresses are not allowed."
            )

        if parsed.port not in (None, 443):
            raise ProviderError(
                "Direct media URL must use the standard HTTPS port."
            )

        return parsed

    except ProviderError:
        raise

    except ValueError as exc:
        raise ProviderError(
            "Direct media URL is malformed."
        ) from exc


class DirectURLProvider(MusicProvider):
    name = "direct_url"

    def __init__(
        self,
        user_agent: str = "BulkMusicDownloader/0.3",
    ):
        self.headers = {
            "User-Agent": user_agent,
            "Accept": "audio/*, application/octet-stream",
        }

    def search(
        self,
        title: str,
        artist: str,
        limit: int = 8,
    ) -> list[SearchResult]:
        return []

    def download(
        self,
        result: SearchResult,
        destination: Path,
        timeout: int,
    ) -> Path:

        if result.provider != self.name:
            raise ProviderError(
                "Direct URL provider cannot download another provider's result."
            )

        if (
            result.download_allowed is not True
            or result.rights_status != "permitted"
        ):
            raise ProviderError(
                "Direct URL download requires explicitly permitted rights."
            )

        if not result.media_url:
            raise ProviderError(
                "No authorized direct URL supplied for this track."
            )

        parsed = _validate_media_url(result.media_url)

        extension = Path(parsed.path).suffix.lower()

        if extension and extension not in AUDIO_EXTENSIONS:
            raise ProviderError(
                "Direct URL does not have a recognized audio extension."
            )

        if destination.suffix.lower() not in AUDIO_EXTENSIONS:
            destination = destination.with_suffix(
                extension or ".audio"
            )

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary = destination.with_suffix(
            destination.suffix + ".part"
        )

        try:
            # Redirects are deliberately disabled. A trusted HTTPS URL
            # must not silently redirect the downloader elsewhere.
            with httpx.stream(
                "GET",
                result.media_url,
                headers=self.headers,
                timeout=timeout,
                follow_redirects=False,
            ) as response:

                if response.status_code in {
                    301, 302, 303, 307, 308
                }:
                    raise ProviderError(
                        "Direct media URL redirected; redirects are not allowed."
                    )

                response.raise_for_status()

                content_type = response.headers.get(
                    "content-type",
                    "",
                ).lower()

                if not any(
                    content_type.startswith(value)
                    for value in AUDIO_CONTENT_TYPES
                ):
                    raise ProviderError(
                        "Direct URL returned an unexpected content type."
                    )

                with temporary.open("wb") as file:
                    for chunk in response.iter_bytes(128 * 1024):
                        file.write(chunk)

            if (
                not temporary.exists()
                or temporary.stat().st_size < 1024
            ):
                raise ProviderError(
                    "Direct URL download was empty or suspiciously small."
                )

            temporary.replace(destination)

            result.file_name = destination.name
            result.media_type = "audio"

            return destination

        except ProviderError:
            temporary.unlink(missing_ok=True)
            raise

        except Exception as exc:
            temporary.unlink(missing_ok=True)

            raise ProviderError(
                f"Direct URL download failed: {exc}"
            ) from exc