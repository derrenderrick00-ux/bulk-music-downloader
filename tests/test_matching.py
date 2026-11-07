from bulk_music_downloader.matching import (
    score_match,
    detect_version,
    match_details,
    artist_similarity,
    compare_versions,
)


def test_exact_match_scores_one():
    assert score_match(
        "Song",
        "Artist",
        "Song",
        "Artist",
    ) == 1.0


def test_unrelated_song_and_artist_score_low():
    assert score_match(
        "Song",
        "Artist",
        "Other",
        "Someone",
    ) < 0.5


def test_wrong_artist_cannot_pass_automatic_threshold():
    score = score_match(
        "Numb",
        "Linkin Park",
        "Numb",
        "Yuni Wa",
    )

    assert score < 0.82


def test_artist_similarity_is_independent():
    assert artist_similarity(
        "Linkin Park",
        "Yuni Wa",
    ) < 0.70


def test_multi_artist_credit():
    assert artist_similarity(
        "Artist A",
        "Artist A feat. Artist B",
    ) >= 0.95


def test_version_detection():
    assert detect_version("My Song (Live)") == "live"
    assert detect_version("My Song Remix") == "remix"
    assert detect_version("My Song (Acoustic)") == "acoustic"
    assert detect_version("My Song (Instrumental)") == "instrumental"


def test_version_mismatch_is_detected():
    assert compare_versions(
        "My Song",
        "My Song (Live)",
    ) is False


def test_same_version_is_compatible():
    assert compare_versions(
        "My Song (Live)",
        "My Song (Live)",
    ) is True


def test_match_details_returns_independent_scores():
    result = match_details(
        "Numb",
        "Linkin Park",
        "Numb",
        "Yuni Wa",
    )

    assert result["title_score"] == 1.0
    assert result["artist_score"] < 0.70
    assert result["score"] < 0.82
