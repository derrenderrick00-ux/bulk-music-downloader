import httpx
import pytest

from bulk_music_downloader.config import load_config
from bulk_music_downloader.providers.base import ProviderError
from bulk_music_downloader.providers.jamendo import JamendoProvider


class MockResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


def successful_payload():
    return {
        "headers": {
            "status": "success",
        },
        "results": [],
    }


def test_second_client_id_used_after_http_401(monkeypatch):
    attempted = []

    def fake_get(url, params, **kwargs):
        attempted.append(params["client_id"])

        if params["client_id"] == "first":
            return MockResponse(status_code=401)

        return MockResponse(payload=successful_payload())

    monkeypatch.setattr(
        "bulk_music_downloader.providers.jamendo.httpx.get",
        fake_get,
    )

    provider = JamendoProvider(
        client_ids=["first", "second"],
    )

    assert provider.search("Track", "Artist") == []
    assert attempted == ["first", "second"]


@pytest.mark.parametrize("status_code", [401, 403, 429])
def test_http_auth_and_rate_limit_statuses_rotate(
    monkeypatch,
    status_code,
):
    attempted = []

    def fake_get(url, params, **kwargs):
        attempted.append(params["client_id"])

        if params["client_id"] == "first":
            return MockResponse(status_code=status_code)

        return MockResponse(payload=successful_payload())

    monkeypatch.setattr(
        "bulk_music_downloader.providers.jamendo.httpx.get",
        fake_get,
    )

    provider = JamendoProvider(
        client_ids=["first", "second"],
    )

    provider.search("Track", "Artist")

    assert attempted == ["first", "second"]


def test_jamendo_api_auth_error_rotates(monkeypatch):
    attempted = []

    def fake_get(url, params, **kwargs):
        attempted.append(params["client_id"])

        if params["client_id"] == "first":
            return MockResponse(
                payload={
                    "headers": {
                        "status": "failed",
                        "error_message": "Invalid client_id",
                    },
                    "results": [],
                }
            )

        return MockResponse(payload=successful_payload())

    monkeypatch.setattr(
        "bulk_music_downloader.providers.jamendo.httpx.get",
        fake_get,
    )

    provider = JamendoProvider(
        client_ids=["first", "second"],
    )

    assert provider.search("Track", "Artist") == []
    assert attempted == ["first", "second"]


def test_all_rejected_ids_raise_without_leaking_ids(monkeypatch):
    attempted = []

    def fake_get(url, params, **kwargs):
        attempted.append(params["client_id"])
        return MockResponse(status_code=401)

    monkeypatch.setattr(
        "bulk_music_downloader.providers.jamendo.httpx.get",
        fake_get,
    )

    provider = JamendoProvider(
        client_ids=["secret-first", "secret-second"],
    )

    with pytest.raises(ProviderError) as error:
        provider.search("Track", "Artist")

    message = str(error.value)

    assert "secret-first" not in message
    assert "secret-second" not in message
    assert attempted == ["secret-first", "secret-second"]


def test_network_error_does_not_rotate(monkeypatch):
    attempted = []

    def fake_get(url, params, **kwargs):
        attempted.append(params["client_id"])

        raise httpx.ConnectError(
            "Connection failed",
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(
        "bulk_music_downloader.providers.jamendo.httpx.get",
        fake_get,
    )

    provider = JamendoProvider(
        client_ids=["first", "second"],
    )

    with pytest.raises(ProviderError):
        provider.search("Track", "Artist")

    assert attempted == ["first"]


def test_legacy_single_client_id_still_works(monkeypatch):
    attempted = []

    def fake_get(url, params, **kwargs):
        attempted.append(params["client_id"])
        return MockResponse(payload=successful_payload())

    monkeypatch.setattr(
        "bulk_music_downloader.providers.jamendo.httpx.get",
        fake_get,
    )

    provider = JamendoProvider(client_id="legacy-id")

    assert provider.search("Track", "Artist") == []
    assert attempted == ["legacy-id"]


def test_environment_client_ids_are_parsed_and_deduplicated(
    monkeypatch,
    tmp_path,
):
    config_file = tmp_path / "config.toml"

    config_file.write_text(
        'jamendo_client_id = "toml-single"\n'
        'jamendo_client_ids = ["toml-first", "toml-second"]\n'
        'providers = ["jamendo"]\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "bulk_music_downloader.config.CONFIG_FILE",
        config_file,
    )

    monkeypatch.setattr(
        "bulk_music_downloader.config.ensure_dirs",
        lambda: None,
    )

    monkeypatch.setenv(
        "JAMENDO_CLIENT_IDS",
        " env-first, env-second, env-first ,, ",
    )
    monkeypatch.setenv("JAMENDO_CLIENT_ID", "legacy-env")

    config = load_config()

    assert config["jamendo_client_ids"] == [
        "env-first",
        "env-second",
    ]
    assert config["jamendo_client_id"] == "env-first"


def test_toml_client_ids_work_without_environment_variables(
    monkeypatch,
    tmp_path,
):
    config_file = tmp_path / "config.toml"

    config_file.write_text(
        'jamendo_client_id = "legacy-toml"\n'
        'jamendo_client_ids = ["toml-first", "toml-second"]\n'
        'providers = ["jamendo"]\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "bulk_music_downloader.config.CONFIG_FILE",
        config_file,
    )

    monkeypatch.setattr(
        "bulk_music_downloader.config.ensure_dirs",
        lambda: None,
    )

    monkeypatch.delenv("JAMENDO_CLIENT_IDS", raising=False)
    monkeypatch.delenv("JAMENDO_CLIENT_ID", raising=False)

    config = load_config()

    assert config["jamendo_client_ids"] == [
        "toml-first",
        "toml-second",
    ]
    assert config["jamendo_client_id"] == "toml-first"