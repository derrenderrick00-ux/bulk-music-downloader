import pytest

from bulk_music_downloader.config import (
    DEFAULT_PROVIDERS,
    LEGACY_DEFAULT_PROVIDERS,
    load_config,
)

from bulk_music_downloader.models import SearchResult

from bulk_music_downloader.providers.base import ProviderError
from bulk_music_downloader.providers.freetouse import FreeToUseProvider
from bulk_music_downloader.providers.ccmixter import CcMixterProvider


def test_freetouse_maps_search_result(monkeypatch):
    def fake_request(self, endpoint, params=None, timeout=30):
        assert endpoint == "/music/tracks/search"
        assert params["query"] == "Test Song Test Artist"

        return {
            "ok": True,
            "data": [
                {
                    "id": "track-123",
                    "title": "Test Song",
                    "is_premium": False,
                    "artists": [
                        [0, {"id": "artist-1", "name": "Test Artist"}]
                    ],
                    "files": {
                        "mp3": "https://cdn.example.test/test.mp3"
                    },
                }
            ],
        }

    monkeypatch.setattr(
        FreeToUseProvider,
        "_request",
        fake_request,
    )

    results = FreeToUseProvider().search(
        "Test Song",
        "Test Artist",
    )

    assert len(results) == 1

    result = results[0]

    assert result.identifier == "track-123"
    assert result.title == "Test Song"
    assert result.artist == "Test Artist"
    assert result.score == 1.0
    assert result.download_allowed is True
    assert result.rights_status == "review_required"
    assert result.license_url == "https://freetouse.com/license"


def test_freetouse_premium_track_is_restricted(monkeypatch):
    def fake_request(self, endpoint, params=None, timeout=30):
        return {
            "ok": True,
            "data": [
                {
                    "id": "premium-1",
                    "title": "Test Song",
                    "is_premium": True,
                    "artists": [
                        [0, {"name": "Test Artist"}]
                    ],
                    "files": {
                        "mp3": "https://cdn.example.test/premium.mp3"
                    },
                }
            ],
        }

    monkeypatch.setattr(
        FreeToUseProvider,
        "_request",
        fake_request,
    )

    result = FreeToUseProvider().search(
        "Test Song",
        "Test Artist",
    )[0]

    assert result.download_allowed is False
    assert result.rights_status == "restricted"


def test_freetouse_unknown_premium_status_is_not_allowed(monkeypatch):
    def fake_request(self, endpoint, params=None, timeout=30):
        return {
            "ok": True,
            "data": [
                {
                    "id": "unknown-1",
                    "title": "Test Song",
                    "artists": [
                        [0, {"name": "Test Artist"}]
                    ],
                    "files": {
                        "mp3": "https://cdn.example.test/test.mp3"
                    },
                }
            ],
        }

    monkeypatch.setattr(
        FreeToUseProvider,
        "_request",
        fake_request,
    )

    result = FreeToUseProvider().search(
        "Test Song",
        "Test Artist",
    )[0]

    assert result.download_allowed is None
    assert result.rights_status == "unknown"


def test_freetouse_rejects_download_without_permission(tmp_path):
    result = SearchResult(
        provider="freetouse",
        identifier="track-1",
        title="Test Song",
        artist="Test Artist",
        url="https://freetouse.com/music/tracks/track-1",
        media_url="https://cdn.example.test/test.mp3",
        download_allowed=None,
    )

    with pytest.raises(ProviderError):
        FreeToUseProvider().download(
            result,
            tmp_path / "test.mp3",
            10,
        )


def test_freetouse_rejects_non_https_media_url(tmp_path):
    result = SearchResult(
        provider="freetouse",
        identifier="track-1",
        title="Test Song",
        artist="Test Artist",
        url="https://freetouse.com/music/tracks/track-1",
        media_url="http://cdn.example.test/test.mp3",
        download_allowed=True,
    )

    with pytest.raises(ProviderError):
        FreeToUseProvider().download(
            result,
            tmp_path / "test.mp3",
            10,
        )


def test_ccmixter_maps_cc_licensed_result(monkeypatch):
    def fake_request(self, params, timeout=30):
        assert params["f"] == "json"
        assert params["datasource"] == "uploads"
        assert params["search"] == "Test Song Test Artist"

        return {
            "results": [
                {
                    "upload_id": "555",
                    "upload_name": "Test Song",
                    "artist": "Test Artist",
                    "license_url": (
                        "https://creativecommons.org/licenses/by/4.0/"
                    ),
                    "download_url": (
                        "https://ccmixter.org/content/test-song.mp3"
                    ),
                    "url": "https://ccmixter.org/files/testartist/555",
                    "attribution": "Test Artist",
                }
            ]
        }

    monkeypatch.setattr(
        CcMixterProvider,
        "_request",
        fake_request,
    )

    results = CcMixterProvider().search(
        "Test Song",
        "Test Artist",
    )

    assert len(results) == 1

    result = results[0]

    assert result.identifier == "555"
    assert result.title == "Test Song"
    assert result.artist == "Test Artist"
    assert result.score == 1.0
    assert result.download_allowed is True
    assert result.rights_status == "review_required"
    assert result.license_url.endswith("/by/4.0/")
    assert result.attribution == "Test Artist"


def test_ccmixter_without_license_is_not_downloadable(monkeypatch):
    def fake_request(self, params, timeout=30):
        return {
            "results": [
                {
                    "upload_id": "556",
                    "upload_name": "Test Song",
                    "artist": "Test Artist",
                    "download_url": (
                        "https://ccmixter.org/content/test-song.mp3"
                    ),
                }
            ]
        }

    monkeypatch.setattr(
        CcMixterProvider,
        "_request",
        fake_request,
    )

    result = CcMixterProvider().search(
        "Test Song",
        "Test Artist",
    )[0]

    assert result.license_url is None
    assert result.download_allowed is None
    assert result.rights_status == "unknown"


def test_ccmixter_without_direct_media_url_is_not_downloadable(monkeypatch):
    def fake_request(self, params, timeout=30):
        return {
            "results": [
                {
                    "upload_id": "557",
                    "upload_name": "Test Song",
                    "artist": "Test Artist",
                    "license_url": (
                        "https://creativecommons.org/licenses/by/4.0/"
                    ),
                }
            ]
        }

    monkeypatch.setattr(
        CcMixterProvider,
        "_request",
        fake_request,
    )

    result = CcMixterProvider().search(
        "Test Song",
        "Test Artist",
    )[0]

    assert result.download_allowed is False
    assert result.rights_status == "review_required"
    assert result.media_url is None


def test_ccmixter_rejects_unapproved_download(tmp_path):
    result = SearchResult(
        provider="ccmixter",
        identifier="555",
        title="Test Song",
        artist="Test Artist",
        url="https://ccmixter.org/files/testartist/555",
        media_url="https://ccmixter.org/content/test-song.mp3",
        download_allowed=None,
    )

    with pytest.raises(ProviderError):
        CcMixterProvider().download(
            result,
            tmp_path / "test.mp3",
            10,
        )


def test_config_migrates_legacy_provider_list(monkeypatch, tmp_path):
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    state_dir = tmp_path / "state"

    config_file = config_dir / "config.toml"

    config_dir.mkdir(parents=True)

    config_file.write_text(
        'download_dir = "~/Music/Test"\n'
        'providers = ["internet_archive", "tubidy", "direct_url"]\n'
        'retries_per_provider = 3\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "bulk_music_downloader.config.APP_DIR",
        config_dir,
    )
    monkeypatch.setattr(
        "bulk_music_downloader.config.DATA_DIR",
        data_dir,
    )
    monkeypatch.setattr(
        "bulk_music_downloader.config.STATE_DIR",
        state_dir,
    )
    monkeypatch.setattr(
        "bulk_music_downloader.config.CONFIG_FILE",
        config_file,
    )

    config = load_config()

    assert config["providers"] == DEFAULT_PROVIDERS
    assert "tubidy" not in config["providers"]


def test_config_preserves_custom_provider_list(monkeypatch, tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)

    config_file = config_dir / "config.toml"

    config_file.write_text(
        'download_dir = "~/Music/Test"\n'
        'providers = ["internet_archive", "direct_url"]\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "bulk_music_downloader.config.APP_DIR",
        config_dir,
    )
    monkeypatch.setattr(
        "bulk_music_downloader.config.DATA_DIR",
        tmp_path / "data",
    )
    monkeypatch.setattr(
        "bulk_music_downloader.config.STATE_DIR",
        tmp_path / "state",
    )
    monkeypatch.setattr(
        "bulk_music_downloader.config.CONFIG_FILE",
        config_file,
    )

    config = load_config()

    assert config["providers"] == [
        "internet_archive",
        "direct_url",
    ]


def test_legacy_provider_constant_is_expected():
    assert LEGACY_DEFAULT_PROVIDERS == [
        "internet_archive",
        "tubidy",
        "direct_url",
    ]
