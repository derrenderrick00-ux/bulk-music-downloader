import pytest

from bulk_music_downloader.models import SearchResult
from bulk_music_downloader.providers.base import ProviderError
from bulk_music_downloader.providers.direct_url import (
    DirectURLProvider,
    _validate_media_url,
)


@pytest.fixture
def provider():
    return DirectURLProvider()


def make_result(**overrides):
    values = {
        "provider": "direct_url",
        "identifier": "manual-1",
        "title": "Test Song",
        "artist": "Test Artist",
        "url": "https://example.test/song.mp3",
        "media_url": "https://example.test/song.mp3",
        "download_allowed": True,
        "rights_status": "permitted",
    }
    values.update(overrides)
    return SearchResult(**values)


def test_search_returns_empty_list(provider):
    assert provider.search("Test Song", "Test Artist") == []


@pytest.mark.parametrize(
    "url",
    [
        "http://example.test/song.mp3",
        "ftp://example.test/song.mp3",
        "https:///song.mp3",
        "https://localhost/song.mp3",
        "https://example.localhost/song.mp3",
        "https://127.0.0.1/song.mp3",
        "https://192.168.1.10/song.mp3",
        "https://10.0.0.1/song.mp3",
        "https://[::1]/song.mp3",
        "https://user:password@example.test/song.mp3",
        "https://example.test:8443/song.mp3",
    ],
)
def test_rejects_unsafe_urls(url):
    with pytest.raises(ProviderError):
        _validate_media_url(url)


def test_accepts_public_https_url():
    parsed = _validate_media_url(
        "https://cdn.example.test/music/song.mp3"
    )

    assert parsed.scheme == "https"
    assert parsed.hostname == "cdn.example.test"


def test_rejects_another_provider(provider, tmp_path):
    result = make_result(provider="jamendo")

    with pytest.raises(ProviderError, match="another provider"):
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
def test_rejects_unapproved_download(
    provider,
    tmp_path,
    rights_status,
    download_allowed,
):
    result = make_result(
        rights_status=rights_status,
        download_allowed=download_allowed,
    )

    with pytest.raises(ProviderError, match="explicitly permitted"):
        provider.download(result, tmp_path / "song.mp3", 10)


def test_rejects_missing_media_url(provider, tmp_path):
    result = make_result(media_url=None)

    with pytest.raises(ProviderError, match="No authorized direct URL"):
        provider.download(result, tmp_path / "song.mp3", 10)


def test_rejects_unknown_file_extension(provider, tmp_path):
    result = make_result(
        media_url="https://example.test/document.pdf"
    )

    with pytest.raises(ProviderError, match="audio extension"):
        provider.download(result, tmp_path / "song.mp3", 10)


def test_download_saves_audio(provider, tmp_path, monkeypatch):
    result = make_result()

    class FakeResponse:
        status_code = 200
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

    def fake_stream(method, url, **kwargs):
        assert method == "GET"
        assert url == result.media_url
        assert kwargs["follow_redirects"] is False
        return FakeResponse()

    monkeypatch.setattr(
        "bulk_music_downloader.providers.direct_url.httpx.stream",
        fake_stream,
    )

    destination = tmp_path / "song.mp3"

    downloaded = provider.download(result, destination, 10)

    assert downloaded == destination
    assert destination.exists()
    assert destination.stat().st_size == 2048
    assert result.file_name == "song.mp3"
    assert result.media_type == "audio"


def test_rejects_redirect(provider, tmp_path, monkeypatch):
    result = make_result()

    class FakeResponse:
        status_code = 302
        headers = {
            "location": "https://other.example.test/song.mp3",
            "content-type": "audio/mpeg",
        }

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self):
            pass

    monkeypatch.setattr(
        "bulk_music_downloader.providers.direct_url.httpx.stream",
        lambda *args, **kwargs: FakeResponse(),
    )

    with pytest.raises(ProviderError, match="redirected"):
        provider.download(result, tmp_path / "song.mp3", 10)

    assert not (tmp_path / "song.mp3.part").exists()


def test_rejects_html_response(provider, tmp_path, monkeypatch):
    result = make_result()

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self):
            pass

    monkeypatch.setattr(
        "bulk_music_downloader.providers.direct_url.httpx.stream",
        lambda *args, **kwargs: FakeResponse(),
    )

    with pytest.raises(ProviderError, match="content type"):
        provider.download(result, tmp_path / "song.mp3", 10)

    assert not (tmp_path / "song.mp3.part").exists()


def test_rejects_small_download(provider, tmp_path, monkeypatch):
    result = make_result()

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "audio/mpeg"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self):
            pass

        def iter_bytes(self, chunk_size):
            yield b"too small"

    monkeypatch.setattr(
        "bulk_music_downloader.providers.direct_url.httpx.stream",
        lambda *args, **kwargs: FakeResponse(),
    )

    with pytest.raises(ProviderError, match="suspiciously small"):
        provider.download(result, tmp_path / "song.mp3", 10)

    assert not (tmp_path / "song.mp3.part").exists()
    assert not (tmp_path / "song.mp3").exists()