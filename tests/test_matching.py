from bulk_music_downloader.matching import score_match, detect_version

def test_matching_score():
    assert score_match("Song", "Artist", "Song", "Artist") == 1.0
    assert score_match("Song", "Artist", "Other", "Someone") < 0.5

def test_version_detection():
    assert detect_version("My Song (Live)") == "live"
    assert detect_version("My Song Remix") == "remix"
