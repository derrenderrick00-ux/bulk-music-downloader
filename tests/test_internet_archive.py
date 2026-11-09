from pathlib import Path

import pytest

from bulk_music_downloader.models import SearchResult
from bulk_music_downloader.providers.base import ProviderError
from bulk_music_downloader.providers.internet_archive import (
    InternetArchiveProvider,
)


@pytest.fixture
def provider():
    return InternetArchiveProvider(
        user_agent="BulkMusicDownloader-Test/1.0"
    )


def test_search_maps_permissive_cc_license(provider, monkeypatch):
    monkeypatch.setattr(
        provider,
        "_request_json",
        lambda *args, **kwargs: {
            "response": {
                "docs": [
                    {
                        "identifier": "test-track",
                        "title": "Test Song",
                        "creator": "Test Artist",
                        "licenseurl": (
                            "https://creativecommons.org/licenses/by/4.0/"
                        ),
                    }
                ]
            }
        },
    )

    results = provider.search("Test Song", "Test Artist")

    assert len(results) == 1
    assert results[0].identifier == "test-track"
    assert results[0].rights_status == "permitted"
    assert results[0].download_allowed is True
    assert results[0].license_url.endswith("/by/4.0/")


def test_search_maps_public_domain(provider, monkeypatch):
    monkeypatch.setattr(
        provider,
        "_request_json",
        lambda *args, **kwargs: {
            "response": {
                "docs": [
                    {
                        "identifier": "public-track",
                        "title": "Test Song",
                        "creator": "Test Artist",
                        "rights": "Public Domain",
                    }
                ]
            }
        },
    )

    result = provider.search("Test Song", "Test Artist")[0]

    assert result.rights_status == "permitted"
    assert result.download_allowed is True


def test_search_requires_review_for_noncommercial_license(
    provider,
    monkeypatch,
):
    monkeypatch.setattr(
        provider,
        "_request_json",
        lambda *args, **kwargs: {
            "response": {
                "docs": [
                    {
                        "identifier": "nc-track",
                        "title": "Test Song",
                        "creator": "Test Artist",
                        "licenseurl": (
                            "https://creativecommons.org/licenses/by-nc/4.0/"
                        ),
                    }
                ]
            }
        },
    )

    result = provider.search("Test Song", "Test Artist")[0]

    assert result.rights_status == "review_required"
    assert result.download_allowed is True


def test_search_marks_missing_license_unknown(provider, monkeypatch):
    monkeypatch.setattr(
        provider,
        "_request_json",
        lambda *args, **kwargs: {
            "response": {
                "docs": [
                    {
                        "identifier": "unknown-track",
                        "title": "Test Song",
                        "creator": "Test Artist",
                    }
                ]
            }
        },
    )

    result = provider.search("Test Song", "Test Artist")[0]

    assert result.rights_status == "unknown"
    assert result.download_allowed is None


def test_search_marks_all_rights_reserved_restricted(
    provider,
    monkeypatch,
):
    monkeypatch.setattr(
        provider,
        "_request_json",
        lambda *args, **kwargs: {
            "response": {
                "docs": [
                    {
                        "identifier": "restricted-track",
                        "title": "Test Song",
                        "creator": "Test Artist",
                        "rights": "All Rights Reserved",
                    }
                ]
            }
        },
    )

    result = provider.search("Test Song", "Test Artist")[0]

    assert result.rights_status == "restricted"
    assert result.download_allowed is False


def test_search_falls_back_to_title_only(provider, monkeypatch):
    calls = []

    def fake_request(url, *, params=None, timeout=20):
        query = params["q"]
        calls.append(query)

        if len(calls) == 1:
            return {"response": {"docs": []}}

        return {
            "response": {
                "docs": [
                    {
                        "identifier": "fallback-track",
                        "title": "Test Song",
                        "creator": "Different Artist",
                        "rights": "Public Domain",
                    }
                ]
            }
        }

    monkeypatch.setattr(provider, "_request_json", fake_request)

    results = provider.search("Test Song", "Test Artist")

    assert len(calls) == 2
    assert "creator:" in calls[0]
    assert "creator:" not in calls[1]
    assert 'title:("Test Song")' in calls[1]
    assert len(results) == 1
    assert results[0].identifier == "fallback-track"


def test_search_falls_back_when_first_results_are_unusable(
    provider,
    monkeypatch,
):
    calls = []

    def fake_request(url, *, params=None, timeout=20):
        calls.append(params["q"])

        if len(calls) == 1:
            return {
                "response": {
                    "docs": [
                        None,
                        {"title": "Missing identifier"},
                        {"identifier": ""},
                    ]
                }
            }

        return {
            "response": {
                "docs": [
                    {
                        "identifier": "usable-fallback",
                        "title": "Test Song",
                        "creator": "Test Artist",
                        "rights": "Public Domain",
                    }
                ]
            }
        }

    monkeypatch.setattr(provider, "_request_json", fake_request)

    results = provider.search("Test Song", "Test Artist")

    assert len(calls) == 2
    assert len(results) == 1
    assert results[0].identifier == "usable-fallback"


def test_search_uses_title_only_when_artist_is_missing(
    provider,
    monkeypatch,
):
    calls = []

    def fake_request(url, *, params=None, timeout=20):
        calls.append(params["q"])
        return {"response": {"docs": []}}

    monkeypatch.setattr(provider, "_request_json", fake_request)

    results = provider.search("Test Song", "")

    assert results == []
    assert len(calls) == 1
    assert "creator:" not in calls[0]
    assert 'title:("Test Song")' in calls[0]


def test_search_returns_empty_when_both_queries_find_nothing(
    provider,
    monkeypatch,
):
    calls = []

    def fake_request(url, *, params=None, timeout=20):
        calls.append(params["q"])
        return {"response": {"docs": []}}

    monkeypatch.setattr(provider, "_request_json", fake_request)

    results = provider.search("Test Song", "Test Artist")

    assert results == []
    assert len(calls) == 2


def test_search_rejects_invalid_response_structure(provider, monkeypatch):
    monkeypatch.setattr(
        provider,
        "_request_json",
        lambda *args, **kwargs: {"unexpected": []},
    )

    with pytest.raises(ProviderError, match="invalid search response"):
        provider.search("Test Song", "Test Artist")


def test_search_rejects_invalid_result_list(provider, monkeypatch):
    monkeypatch.setattr(
        provider,
        "_request_json",
        lambda *args, **kwargs: {
            "response": {"docs": "not-a-list"}
        },
    )

    with pytest.raises(ProviderError, match="invalid result list"):
        provider.search("Test Song", "Test Artist")


def test_download_rejects_another_provider(provider, tmp_path):
    result = SearchResult(
        provider="jamendo",
        identifier="123",
        title="Test Song",
        artist="Test Artist",
        url="https://example.test/song",
        download_allowed=True,
        rights_status="permitted",
    )

    with pytest.raises(ProviderError):
        provider.download(result, tmp_path / "song.mp3", 10)


@pytest.mark.parametrize(
    "rights_status, download_allowed",
    [
        ("unknown", None),
        ("restricted", False),
        ("review_required", True),
        ("permitted", False),
    ],
)
def test_download_rejects_unapproved_rights(
    provider,
    tmp_path,
    rights_status,
    download_allowed,
):
    result = SearchResult(
        provider="internet_archive",
        identifier="123",
        title="Test Song",
        artist="Test Artist",
        url="https://archive.org/details/123",
        download_allowed=download_allowed,
        rights_status=rights_status,
    )

    with pytest.raises(ProviderError):
        provider.download(result, tmp_path / "song.mp3", 10)


def test_download_rechecks_fresh_metadata(provider, tmp_path, monkeypatch):
    result = SearchResult(
        provider="internet_archive",
        identifier="123",
        title="Test Song",
        artist="Test Artist",
        url="https://archive.org/details/123",
        download_allowed=True,
        rights_status="permitted",
    )

    monkeypatch.setattr(
        provider,
        "_metadata",
        lambda *args, **kwargs: {
            "metadata": {
                "identifier": "123",
                "rights": "All Rights Reserved",
            },
            "files": [],
        },
    )

    with pytest.raises(ProviderError, match="Fresh Internet Archive metadata"):
        provider.download(result, tmp_path / "song.mp3", 10)


def test_download_selects_original_audio_and_saves_file(
    provider,
    tmp_path,
    monkeypatch,
):
    result = SearchResult(
        provider="internet_archive",
        identifier="123",
        title="Test Song",
        artist="Test Artist",
        url="https://archive.org/details/123",
        download_allowed=True,
        rights_status="permitted",
    )

    monkeypatch.setattr(
        provider,
        "_metadata",
        lambda *args, **kwargs: {
            "metadata": {
                "identifier": "123",
                "licenseurl": (
                    "https://creativecommons.org/licenses/by/4.0/"
                ),
            },
            "files": [
                {
                    "name": "metadata.xml",
                    "format": "Metadata",
                    "source": "original",
                },
                {
                    "name": "preview.mp3",
                    "format": "MP3",
                    "source": "derivative",
                },
                {
                    "name": "song.mp3",
                    "format": "MP3",
                    "source": "original",
                    "size": "2048",
                },
            ],
        },
    )

    class FakeResponse:
        url = "https://archive.org/download/123/song.mp3"
        headers = {"content-type": "audio/mpeg"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self):
            pass

        def iter_bytes(self, chunk_size):
            assert chunk_size == 128 * 1024
            yield b"x" * 2048

    monkeypatch.setattr(
        "bulk_music_downloader.providers.internet_archive.httpx.stream",
        lambda *args, **kwargs: FakeResponse(),
    )

    destination = tmp_path / "song.audio"

    downloaded = provider.download(result, destination, 10)

    assert downloaded == tmp_path / "song.mp3"
    assert downloaded.exists()
    assert downloaded.stat().st_size == 2048
    assert result.file_name == "song.mp3"
    assert result.rights_status == "permitted"
    assert result.download_allowed is True


def test_download_rejects_html_response(
    provider,
    tmp_path,
    monkeypatch,
):
    result = SearchResult(
        provider="internet_archive",
        identifier="123",
        title="Test Song",
        artist="Test Artist",
        url="https://archive.org/details/123",
        download_allowed=True,
        rights_status="permitted",
    )

    monkeypatch.setattr(
        provider,
        "_metadata",
        lambda *args, **kwargs: {
            "metadata": {
                "identifier": "123",
                "rights": "Public Domain",
            },
            "files": [
                {
                    "name": "song.mp3",
                    "format": "MP3",
                    "source": "original",
                }
            ],
        },
    )

    class FakeResponse:
        url = "https://archive.org/download/123/song.mp3"
        headers = {"content-type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self):
            pass

    monkeypatch.setattr(
        "bulk_music_downloader.providers.internet_archive.httpx.stream",
        lambda *args, **kwargs: FakeResponse(),
    )

    with pytest.raises(ProviderError, match="content type"):
        provider.download(result, tmp_path / "song.mp3", 10)

    assert not (tmp_path / "song.mp3.part").exists()


def test_download_rejects_unsafe_filename(provider, tmp_path, monkeypatch):
    result = SearchResult(
        provider="internet_archive",
        identifier="123",
        title="Test Song",
        artist="Test Artist",
        url="https://archive.org/details/123",
        download_allowed=True,
        rights_status="permitted",
    )

    monkeypatch.setattr(
        provider,
        "_metadata",
        lambda *args, **kwargs: {
            "metadata": {
                "identifier": "123",
                "rights": "Public Domain",
            },
            "files": [
                {
                    "name": "../song.mp3",
                    "format": "MP3",
                    "source": "original",
                }
            ],
        },
    )

    with pytest.raises(ProviderError, match="No public original audio"):
        provider.download(result, tmp_path / "song.mp3", 10)
