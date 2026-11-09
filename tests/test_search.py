from bulk_music_downloader.models import SearchResult

from bulk_music_downloader.search import (
    search_all,
    is_download_eligible,
)


class Provider:

    def __init__(
        self,
        name,
        results=None,
        error=None,
    ):
        self.name = name
        self.results = results or []
        self.error = error

    def search(self, *args):

        if self.error:
            raise self.error

        return self.results


def result(
    provider="audius",
    identifier="1",
    title="Test Song",
    artist="Test Artist",
    score=0,
    rights="permitted",
    allowed=True,
):

    return SearchResult(
        provider=provider,
        identifier=identifier,
        title=title,
        artist=artist,
        url="https://example.test/item",
        score=score,
        rights_status=rights,
        download_allowed=allowed,
    )


def test_search_aggregates_and_recalculates_provider_scores():

    batch = search_all(
        [
            Provider("audius", [result(score=0.01)]),
            Provider(
                "jamendo",
                [
                    result(
                        "jamendo",
                        "2",
                        score=0.99,
                    )
                ],
            ),
        ],
        "Test Song",
        "Test Artist",
    )

    assert len(batch.candidates) == 2

    assert all(
        candidate.score == 1.0
        for candidate in batch.candidates
    )


def test_provider_failure_does_not_stop_other_sources():

    batch = search_all(
        [
            Provider(
                "bad",
                error=RuntimeError("offline"),
            ),
            Provider(
                "good",
                [result("good")],
            ),
        ],
        "Test Song",
        "Test Artist",
    )

    assert "bad" in batch.provider_errors

    assert len(batch.candidates) == 1

    assert batch.candidates[0].provider == "good"


def test_same_provider_duplicate_is_removed_but_alternative_kept():

    batch = search_all(
        [
            Provider(
                "a",
                [
                    result("a", "same"),
                    result("a", "same"),
                ],
            ),
            Provider(
                "b",
                [result("b", "same")],
            ),
        ],
        "Test Song",
        "Test Artist",
    )

    assert [
        (item.provider, item.identifier)
        for item in batch.candidates
    ] == [
        ("a", "same"),
        ("b", "same"),
    ]


def test_rights_fail_closed():

    assert is_download_eligible(result())

    assert not is_download_eligible(
        result(
            rights="review_required",
            allowed=True,
        )
    )

    assert not is_download_eligible(
        result(
            rights="permitted",
            allowed=None,
        )
    )

    assert not is_download_eligible(
        result(
            rights="unknown",
            allowed=True,
        )
    )


def test_direct_url_is_not_searched():

    batch = search_all(
        [
            Provider(
                "direct_url",
                error=AssertionError(
                    "Must not call direct URL search"
                ),
            )
        ],
        "Test Song",
        "Test Artist",
    )

    assert not batch.provider_errors
    assert not batch.candidates


def test_wrong_provider_and_malformed_candidates_are_discarded():

    batch = search_all(
        [
            Provider(
                "a",
                [
                    result("other"),
                    object(),
                ],
            )
        ],
        "Test Song",
        "Test Artist",
    )

    assert not batch.candidates
    assert batch.malformed_counts["a"] == 2


def test_non_list_provider_response_is_isolated():

    class BadProvider:

        name = "bad"

        def search(self, *args):
            return {"oops": 1}

    batch = search_all(
        [
            BadProvider(),
            Provider("good", [result("good")]),
        ],
        "Test Song",
        "Test Artist",
    )

    assert "bad" in batch.provider_errors
    assert len(batch.candidates) == 1


def test_version_mismatch_is_not_download_eligible():

    wrong_version = result()

    wrong_version.version_match = False

    assert not is_download_eligible(wrong_version)