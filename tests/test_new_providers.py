from pathlib import Path

import pytest

from bulk_music_downloader.models import SearchResult
from bulk_music_downloader.providers.audius import AudiusProvider
from bulk_music_downloader.providers.jamendo import JamendoProvider
from bulk_music_downloader.providers.base import ProviderError


def test_audius_search_maps_downloadable_track(monkeypatch):
    def fake_request(self, endpoint, params=None, timeout=30):
        assert endpoint == "/tracks/search"

        return {
            "data": [
                {
                    "id": "123",
                    "title": "Test Song",
                    "permalink": "artist/test-song",
                    "is_downloadable": True,
                    "user": {
                        "name": "Test Artist",
                    },
                }
            ]
        }

    monkeypatch.setattr(
        AudiusProvider,
        "_request",
        fake_request,
    )

    provider = AudiusProvider()
    results = provider.search("Test Song", "Test Artist")

    assert len(results) == 1
    assert results[0].identifier == "123"
    assert results[0].download_allowed is True
    assert results[0].rights_status == "permitted"
    assert results[0].score == 1.0


def test_audius_search_preserves_restricted_permission(monkeypatch):
    def fake_request(self, endpoint, params=None, timeout=30):
        return {
            "data": [
                {
                    "id": "456",
                    "title": "Test Song",
                    "is_downloadable": False,
                    "user": {
                        "name": "Test Artist",
                    },
                }
            ]
        }

    monkeypatch.setattr(
        AudiusProvider,
        "_request",
        fake_request,
    )

    results = AudiusProvider().search(
        "Test Song",
        "Test Artist",
    )

    assert results[0].download_allowed is False
    assert results[0].rights_status == "restricted"


def test_audius_search_falls_back_to_title_only(monkeypatch):
    calls = []

    def fake_request(self, endpoint, params=None, timeout=30):
        calls.append(params["query"])

        if len(calls) == 1:
            return {"data": []}

        return {
            "data": [
                {
                    "id": "fallback-123",
                    "title": "Test Song",
                    "is_downloadable": True,
                    "user": {
                        "name": "Test Artist",
                    },
                }
            ]
        }

    monkeypatch.setattr(
        AudiusProvider,
        "_request",
        fake_request,
    )

    results = AudiusProvider().search(
        "Test Song",
        "Test Artist",
    )

    assert calls == [
        "Test Song Test Artist",
        "Test Song",
    ]

    assert len(results) == 1
    assert results[0].identifier == "fallback-123"
    assert results[0].download_allowed is True
    assert results[0].rights_status == "permitted"


def test_audius_search_handles_malformed_user_metadata(monkeypatch):
    def fake_request(self, endpoint, params=None, timeout=30):
        return {
            "data": [
                {
                    "id": "malformed-123",
                    "title": "Test Song",
                    "is_downloadable": True,
                    "user": "unexpected-value",
                }
            ]
        }

    monkeypatch.setattr(
        AudiusProvider,
        "_request",
        fake_request,
    )

    results = AudiusProvider().search(
        "Test Song",
        "Test Artist",
    )

    assert len(results) == 1
    assert results[0].identifier == "malformed-123"
    assert results[0].artist == ""
    assert results[0].download_allowed is True


def test_audius_download_rejects_unapproved_track(tmp_path):
    provider = AudiusProvider()

    result = SearchResult(
        provider="audius",
        identifier="123",
        title="Test",
        artist="Artist",
        url="https://audius.co/test",
        download_allowed=False,
    )

    with pytest.raises(ProviderError):
        provider.download(
            result,
            tmp_path / "test.audio",
            10,
        )


def test_jamendo_requires_client_id():
    provider = JamendoProvider(client_id="")

    with pytest.raises(ProviderError):
        provider.search("Test Song", "Test Artist")


def test_jamendo_search_maps_allowed_track(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "headers": {
                    "status": "success",
                },
                "results": [
                    {
                        "id": "789",
                        "name": "Test Song",
                        "artist_name": "Test Artist",
                        "audiodownload_allowed": True,
                        "audiodownload": "https://example.test/audio.mp3",
                        "license_ccurl": "https://creativecommons.org/licenses/by/4.0/",
                        "shareurl": "https://www.jamendo.com/track/789",
                    }
                ],
            }

    def fake_get(*args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr(
        "bulk_music_downloader.providers.jamendo.httpx.get",
        fake_get,
    )

    provider = JamendoProvider(client_id="test-client")
    results = provider.search("Test Song", "Test Artist")

    assert len(results) == 1
    assert results[0].identifier == "789"
    assert results[0].download_allowed is True
    assert results[0].rights_status == "permitted"
    assert results[0].media_url.endswith(".mp3")


def test_jamendo_search_rejects_download_permission_false(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "headers": {
                    "status": "success",
                },
                "results": [
                    {
                        "id": "790",
                        "name": "Test Song",
                        "artist_name": "Test Artist",
                        "audiodownload_allowed": False,
                        "audiodownload": "",
                        "license_ccurl": "",
                    }
                ],
            }

    monkeypatch.setattr(
        "bulk_music_downloader.providers.jamendo.httpx.get",
        lambda *args, **kwargs: FakeResponse(),
    )

    results = JamendoProvider(
        client_id="test-client"
    ).search("Test Song", "Test Artist")

    assert results[0].download_allowed is False
    assert results[0].rights_status == "restricted"
    assert results[0].media_url is None


def test_jamendo_download_rejects_unapproved_track(tmp_path):
    provider = JamendoProvider(client_id="test-client")

    result = SearchResult(
        provider="jamendo",
        identifier="789",
        title="Test",
        artist="Artist",
        url="https://www.jamendo.com/track/789",
        download_allowed=False,
    )

    with pytest.raises(ProviderError):
        provider.download(
            result,
            tmp_path / "test.audio",
            10,
        )
