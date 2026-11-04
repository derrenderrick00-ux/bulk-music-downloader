from __future__ import annotations

import tomllib
from pathlib import Path

APP_DIR = Path.home() / ".config" / "bulk-music-downloader"
DATA_DIR = Path.home() / ".local" / "share" / "bulk-music-downloader"
STATE_DIR = Path.home() / ".local" / "state" / "bulk-music-downloader"
CONFIG_FILE = APP_DIR / "config.toml"

DEFAULTS = {
    "download_dir": str(Path.home() / "Music" / "BulkDownloads"),
    "providers": ["internet_archive", "tubidy", "direct_url"],
    "retries_per_provider": 3,
    "request_timeout": 30,
    "max_search_results": 8,
    "user_agent": "BulkMusicDownloader/0.1 (+local personal downloader)",
}


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

    with CONFIG_FILE.open("rb") as f:
        loaded = tomllib.load(f)

    result = DEFAULTS.copy()
    result.update(loaded)

    result["download_dir"] = str(
        Path(result["download_dir"]).expanduser()
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
                _quote(str(x)) for x in value
            ) + "]"

        else:
            rendered = _quote(str(value))

        lines.append(f"{key} = {rendered}")

    CONFIG_FILE.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8"
    )


def _quote(value: str) -> str:
    return '"' + value.replace(
        "\\", "\\\\"
    ).replace('"', '\\"') + '"'
