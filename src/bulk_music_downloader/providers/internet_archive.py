from __future__ import annotations

from pathlib import Path
from urllib.parse import quote, urlparse

import httpx

from .base import MusicProvider, ProviderError
from ..matching import match_details, detect_version
from ..models import SearchResult


API = "https://archive.org/advancedsearch.php"
METADATA_API = "https://archive.org/metadata/"

AUDIO_EXTENSIONS = {
    ".mp3", ".ogg", ".flac", ".wav",
    ".m4a", ".aac", ".opus",
}

AUDIO_FORMATS = {
    "mp3",
    "ogg vorbis",
    "flac",
    "wav",
    "advanced audio coding",
    "aac",
    "mpeg audio",
    "opus",
}

AUDIO_CONTENT_TYPES = (
    "audio/",
    "application/ogg",
    "application/octet-stream",
)


def _safe_query_value(value: str) -> str:
    return value.replace("\\", " ").replace('"', " ").strip()


def _rights_decision(*values: object) -> tuple[str, bool | None]:
    """
    Return (rights_status, download_allowed).

    Only clear, recognized permissive licences are automatically
    permitted. Ambiguous and conditional licences require review.
    """
    text = " ".join(
        str(value).strip().lower()
        for value in values
        if value not in (None, "")
    )

    if not text:
        return "unknown", None

    normalized = text.replace("_", "-").replace(" ", "-")

    restricted_terms = (
        "all-rights-reserved",
        "copyrighted",
        "no-permission",
        "not-for-distribution",
    )

    if any(term in normalized for term in restricted_terms):
        return "restricted", False

    conditional_terms = (
        "by-nc",
        "by-nd",
        "noncommercial",
        "non-commercial",
        "no-derivatives",
    )

    if any(term in normalized for term in conditional_terms):
        return "review_required", True

    public_domain_terms = (
        "creativecommons.org/publicdomain/zero",
        "creativecommons.org/publicdomain/mark",
        "public domain",
        "public-domain",
        "cc0",
    )

    if any(term in normalized for term in public_domain_terms):
        return "permitted", True

    cc_hosts = (
        "creativecommons.org/licenses/by/",
        "creativecommons.org/licenses/by-sa/",
    )

    if any(host in normalized for host in cc_hosts):
        return "permitted", True

    return "unknown", None


def _is_safe_archive_host(url: str) -> bool:
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()

        return (
            parsed.scheme == "https"
            and (
                host == "archive.org"
                or host.endswith(".archive.org")
            )
        )
    except ValueError:
        return False


class InternetArchiveProvider(MusicProvider):
    name = "internet_archive"

    def __init__(self, user_agent: str):
        self.headers = {
            "User-Agent": user_agent,
            "Accept": "application/json",
        }

    def _request_json(
        self,
        url: str,
        *,
        params: dict | None = None,
        timeout: int = 20,
    ) -> dict:
        try:
            response = httpx.get(
                url,
                params=params,
                headers=self.headers,
                timeout=timeout,
                follow_redirects=False,
            )
            response.raise_for_status()
            payload = response.json()

        except Exception as exc:
            raise ProviderError(
                f"Internet Archive request failed: {exc}"
            ) from exc

        if not isinstance(payload, dict):
            raise ProviderError(
                "Internet Archive returned an invalid response."
            )

        return payload

    def _map_search_docs(
        self,
        docs: list,
        title: str,
        artist: str,
    ) -> list[SearchResult]:
        results = []

        for doc in docs:
            if not isinstance(doc, dict):
                continue

            identifier = doc.get("identifier")

            if not isinstance(identifier, str) or not identifier.strip():
                continue

            found_title = str(
                doc.get("title") or identifier
            )

            creator = doc.get("creator", "Unknown")

            found_artist = (
                ", ".join(str(item) for item in creator)
                if isinstance(creator, list)
                else str(creator)
            )

            license_url = doc.get("licenseurl")
            rights = doc.get("rights")

            rights_status, download_allowed = _rights_decision(
                license_url,
                rights,
            )

            details = match_details(
                title,
                artist,
                found_title,
                found_artist,
            )

            results.append(
                SearchResult(
                    provider=self.name,
                    identifier=identifier,
                    title=found_title,
                    artist=found_artist,
                    url=(
                        "https://archive.org/details/"
                        + quote(identifier, safe="")
                    ),
                    media_type="audio",
                    rights=(
                        str(rights)
                        if rights
                        else str(license_url or "Rights not verified")
                    ),
                    score=details["score"],
                    title_score=details["title_score"],
                    artist_score=details["artist_score"],
                    version=detect_version(found_title),
                    version_match=details["version_match"],
                    download_allowed=download_allowed,
                    license_url=(
                        str(license_url)
                        if license_url
                        else None
                    ),
                    attribution=found_artist,
                    rights_status=rights_status,
                    metadata=doc,
                )
            )

        return results

    def search(
        self,
        title: str,
        artist: str,
        limit: int = 8,
    ) -> list[SearchResult]:

        safe_title = _safe_query_value(title)
        safe_artist = _safe_query_value(artist)

        if not safe_title:
            return []

        # Try the more specific query first. If it produces no usable
        # results, retry with the title alone.
        queries = []

        if safe_artist:
            queries.append(
                (
                    f'(title:("{safe_title}") OR subject:("{safe_title}")) '
                    f'AND '
                    f'(creator:("{safe_artist}") OR subject:("{safe_artist}")) '
                    f'AND mediatype:audio'
                )
            )

        queries.append(
            f'(title:("{safe_title}") OR subject:("{safe_title}")) '
            f'AND mediatype:audio'
        )

        rows = min(max(int(limit), 1), 100)

        for query in queries:
            params = {
                "q": query,
                "fl[]": [
                    "identifier",
                    "title",
                    "creator",
                    "licenseurl",
                    "rights",
                    "description",
                    "mediatype",
                ],
                "rows": rows,
                "page": 1,
                "output": "json",
            }

            payload = self._request_json(
                API,
                params=params,
            )

            response_data = payload.get("response")

            if not isinstance(response_data, dict):
                raise ProviderError(
                    "Internet Archive returned an invalid search response."
                )

            docs = response_data.get("docs", [])

            if not isinstance(docs, list):
                raise ProviderError(
                    "Internet Archive returned an invalid result list."
                )

            results = self._map_search_docs(
                docs,
                title,
                artist,
            )

            if results:
                return sorted(
                    results,
                    key=lambda item: item.score,
                    reverse=True,
                )

        return []

    def _metadata(
        self,
        identifier: str,
        timeout: int,
    ) -> dict:

        if (
            not identifier
            or "/" in identifier
            or "\\" in identifier
            or identifier in {".", ".."}
        ):
            raise ProviderError(
                "Invalid Internet Archive identifier."
            )

        url = (
            METADATA_API
            + quote(identifier, safe="")
        )

        payload = self._request_json(
            url,
            timeout=timeout,
        )

        metadata_record = payload.get("metadata", {})

        if not isinstance(metadata_record, dict):
            raise ProviderError(
                "Internet Archive returned invalid item metadata."
            )

        metadata_identifier = metadata_record.get("identifier")

        if (
            metadata_identifier
            and metadata_identifier != identifier
        ):
            raise ProviderError(
                "Internet Archive metadata identifier mismatch."
            )

        return payload

    @staticmethod
    def _is_audio_file(item: dict) -> bool:
        name = str(item.get("name") or "")
        extension = Path(name).suffix.lower()
        file_format = str(item.get("format") or "").strip().lower()

        return (
            extension in AUDIO_EXTENSIONS
            or file_format in AUDIO_FORMATS
        )

    def download(
        self,
        result: SearchResult,
        destination: Path,
        timeout: int,
    ) -> Path:

        if result.provider != self.name:
            raise ProviderError(
                "Internet Archive cannot download another provider's result."
            )

        if (
            result.download_allowed is not True
            or result.rights_status != "permitted"
        ):
            raise ProviderError(
                "Internet Archive download requires explicitly permitted rights."
            )

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary = destination.with_suffix(
            destination.suffix + ".part"
        )

        try:
            # Re-check rights against fresh metadata before downloading.
            metadata = self._metadata(
                result.identifier,
                timeout,
            )

            metadata_record = metadata.get("metadata", {})

            if not isinstance(metadata_record, dict):
                raise ProviderError(
                    "Internet Archive returned invalid item metadata."
                )

            license_url = metadata_record.get("licenseurl")
            rights = metadata_record.get("rights")

            rights_status, download_allowed = _rights_decision(
                license_url,
                rights,
            )

            if (
                download_allowed is not True
                or rights_status != "permitted"
            ):
                raise ProviderError(
                    "Fresh Internet Archive metadata does not establish permitted rights."
                )

            files = metadata.get("files", [])

            if not isinstance(files, list):
                raise ProviderError(
                    "Internet Archive returned an invalid file list."
                )

            audio_files = []

            for item in files:
                if not isinstance(item, dict):
                    continue

                name = str(item.get("name") or "")
                source = str(item.get("source") or "").lower()
                private = str(item.get("private") or "").lower()

                # Download only original, public audio files.
                if source != "original":
                    continue

                if private in {"true", "1", "yes"}:
                    continue

                if not self._is_audio_file(item):
                    continue

                # Reject paths and traversal attempts.
                if (
                    not name
                    or Path(name).name != name
                    or name in {".", ".."}
                ):
                    continue

                audio_files.append(item)

            if not audio_files:
                raise ProviderError(
                    "No public original audio file was found."
                )

            # Prefer MP3, then smaller files.
            preferred = sorted(
                audio_files,
                key=lambda item: (
                    0
                    if Path(str(item.get("name", ""))).suffix.lower()
                    == ".mp3"
                    else 1,
                    (
                        int(item.get("size", 0))
                        if str(item.get("size", "0")).isdigit()
                        else 0
                    ),
                ),
            )[0]

            filename = str(preferred["name"])
            extension = Path(filename).suffix.lower()

            if extension not in AUDIO_EXTENSIONS:
                raise ProviderError(
                    "Internet Archive selected an unsupported audio extension."
                )

            media_url = (
                "https://archive.org/download/"
                + quote(result.identifier, safe="")
                + "/"
                + quote(filename, safe="")
            )

            if destination.suffix.lower() != extension:
                destination = destination.with_suffix(extension)

            temporary = destination.with_suffix(
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

                if not _is_safe_archive_host(str(response.url)):
                    raise ProviderError(
                        "Internet Archive redirected to an unexpected host."
                    )

                content_type = response.headers.get(
                    "content-type",
                    "",
                ).lower()

                if not any(
                    content_type.startswith(value)
                    for value in AUDIO_CONTENT_TYPES
                ):
                    raise ProviderError(
                        "Internet Archive returned an unexpected content type."
                    )

                with temporary.open("wb") as file:
                    for chunk in response.iter_bytes(128 * 1024):
                        file.write(chunk)

            if (
                not temporary.exists()
                or temporary.stat().st_size < 1024
            ):
                raise ProviderError(
                    "Internet Archive download was empty or suspiciously small."
                )

            temporary.replace(destination)

            result.media_url = media_url
            result.file_name = filename
            result.license_url = (
                str(license_url)
                if license_url
                else None
            )
            result.rights_status = rights_status
            result.download_allowed = download_allowed
            result.attribution = result.artist
            result.metadata = metadata

            return destination

        except ProviderError:
            temporary.unlink(missing_ok=True)
            raise

        except Exception as exc:
            temporary.unlink(missing_ok=True)

            raise ProviderError(
                f"Internet Archive download failed: {exc}"
            ) from exc
