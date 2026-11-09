from __future__ import annotations

import os
import tomllib
from pathlib import Path

APP_DIR = Path.home() / ".config" / "bulk-music-downloader"
DATA_DIR = Path.home() / ".local" / "share" / "bulk-music-downloader"
STATE_DIR = Path.home() / ".local" / "state" / "bulk-music-downloader"
CONFIG_FILE = APP_DIR / "config.toml"

DEFAULT_PROVIDERS = [
    "audius",
    "jamendo",
    "freetouse",
    "ccmixter",
    "internet_archive",
    "direct_url",
]

LEGACY_DEFAULT_PROVIDERS = [
    "internet_archive",
    "tubidy",
    "direct_url",
]

DEFAULTS = {
    "download_dir": str(Path.home() / "Music" / "BulkDownloads"),
    "providers": DEFAULT_PROVIDERS,
    "retries_per_provider": 3,
    "request_timeout": 30,
    "max_search_results": 8,
    "user_agent": "BulkMusicDownloader/0.3",
    "jamendo_client_id": "",
    "jamendo_client_ids": [],
    "audius_api_key": "",
}


def _clean_ids(values) -> list[str]:
    """Normalize client IDs and remove duplicates."""
    if isinstance(values, str):
        values = values.split(",")

    if not isinstance(values, (list, tuple)):
        return []

    cleaned = []
    seen = set()

    for value in values:
        if not isinstance(value, str):
            continue

        client_id = value.strip()

        if client_id and client_id not in seen:
            cleaned.append(client_id)
            seen.add(client_id)

    return cleaned


def ensure_dirs() -> None:
    for path in (
        APP_DIR,
        DATA_DIR,
        STATE_DIR,
        Path(DEFAULTS["download_dir"]).expanduser(),
    ):
        path.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    ensure_dirs()

    if not CONFIG_FILE.exists():
        save_config(DEFAULTS)

    with CONFIG_FILE.open("rb") as file:
        loaded = tomllib.load(file)

    result = {
        **DEFAULTS,
        "providers": list(DEFAULT_PROVIDERS),
        "jamendo_client_ids": [],
    }
    result.update(loaded)

    configured_providers = result.get("providers")

    if not isinstance(configured_providers, list):
        raise ValueError(
            "The 'providers' setting must be a TOML list."
        )

    if configured_providers == LEGACY_DEFAULT_PROVIDERS:
        result["providers"] = list(DEFAULT_PROVIDERS)

    result["download_dir"] = str(
        Path(result["download_dir"]).expanduser()
    )

    # Jamendo credential precedence:
    # 1. JAMENDO_CLIENT_IDS
    # 2. JAMENDO_CLIENT_ID
    # 3. TOML jamendo_client_ids
    # 4. TOML jamendo_client_id

    environment_ids = os.getenv("JAMENDO_CLIENT_IDS", "").strip()
    environment_single = os.getenv("JAMENDO_CLIENT_ID", "").strip()

    if environment_ids:
        client_ids = _clean_ids(environment_ids)

    elif environment_single:
        client_ids = _clean_ids([environment_single])

    else:
        client_ids = _clean_ids(
            result.get("jamendo_client_ids", [])
        )

        if not client_ids:
            client_ids = _clean_ids(
                [result.get("jamendo_client_id", "")]
            )

    result["jamendo_client_ids"] = client_ids

    # Retain the legacy setting for existing code.
    result["jamendo_client_id"] = (
        client_ids[0] if client_ids else ""
    )

    # Environment variables take precedence over config.toml.
    result["audius_api_key"] = (
        os.getenv("AUDIUS_API_KEY")
        or result.get("audius_api_key", "")
    )

    return result


def save_config(config: dict) -> None:
    ensure_dirs()

    lines = []

    for key, value in config.items():
        if isinstance(value, bool):
            rendered = "true" if value else "false"

        elif isinstance(value, (int, float)):
            rendered = str(value)

        elif isinstance(value, list):
            rendered = "[" + ", ".join(
                _quote(str(item)) for item in value
            ) + "]"

        else:
            rendered = _quote(str(value))

        lines.append(f"{key} = {rendered}")

    CONFIG_FILE.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def _quote(value: str) -> str:
    return '"' + value.replace(
        "\\", "\\\\"
    ).replace('"', '\\"') + '"'