"""Cross-provider search aggregation and deterministic candidate ranking."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from .matching import match_details, detect_version
from .models import SearchResult


@dataclass
class SearchBatch:
    candidates: list[SearchResult] = field(default_factory=list)
    provider_errors: dict[str, str] = field(default_factory=dict)
    provider_counts: dict[str, int] = field(default_factory=dict)
    malformed_counts: dict[str, int] = field(default_factory=dict)


def is_download_eligible(result: SearchResult) -> bool:
    """Fail closed unless rights and version checks both pass."""

    return (
        result.rights_status == "permitted"
        and result.download_allowed is True
        and result.version_match is not False
    )


def _candidate_key(result: SearchResult) -> tuple[str, str]:
    """
    Identify repeated results from the same provider.

    Results from different providers are preserved because they
    represent alternative download sources.
    """

    return (
        result.provider.casefold(),
        result.identifier.strip().casefold(),
    )


def _rank_key(
    result: SearchResult,
    provider_order: dict[str, int],
) -> tuple[Any, ...]:

    return (
        not is_download_eligible(result),
        -result.score,
        -result.title_score,
        -result.artist_score,
        provider_order.get(result.provider, 10**6),
        result.identifier,
    )


def search_all(
    providers,
    title: str,
    artist: str,
    limit: int = 8,
) -> SearchBatch:

    """Search every configured searchable provider."""

    batch = SearchBatch()

    seen: set[tuple[str, str]] = set()
    provider_order: dict[str, int] = {}

    for index, provider in enumerate(providers):

        name = str(
            getattr(
                provider,
                "name",
                provider.__class__.__name__,
            )
        ).strip()

        provider_order.setdefault(name, index)

        # Direct URL is an import workflow, not a search provider.
        if name.casefold() == "direct_url":
            continue

        try:

            found = provider.search(
                title,
                artist,
                limit,
            )

            if not isinstance(found, (list, tuple)):
                raise TypeError(
                    "Provider search did not return a list."
                )

            valid_count = 0
            malformed_count = 0

            for item in found:

                if (
                    not isinstance(item, SearchResult)
                    or item.provider != name
                ):
                    malformed_count += 1
                    continue

                if not item.identifier or not item.title:
                    malformed_count += 1
                    continue

                key = _candidate_key(item)

                if key in seen:
                    continue

                seen.add(key)

                # Recalculate scores centrally.
                # Do not trust provider-supplied scores.
                details = match_details(
                    title,
                    artist,
                    item.title,
                    item.artist or "Unknown",
                )

                candidate = replace(
                    item,
                    score=details["score"],
                    title_score=details["title_score"],
                    artist_score=details["artist_score"],
                    version=detect_version(item.title),
                    version_match=details["version_match"],
                )

                batch.candidates.append(candidate)
                valid_count += 1

            batch.provider_counts[name] = valid_count

            if malformed_count:
                batch.malformed_counts[name] = malformed_count

        except Exception as exc:

            # One provider failure must not stop the remaining providers.
            batch.provider_errors[name] = (
                f"{type(exc).__name__}: {exc}"
            )

            batch.provider_counts.setdefault(name, 0)

    batch.candidates.sort(
        key=lambda result: _rank_key(
            result,
            provider_order,
        )
    )

    return batch