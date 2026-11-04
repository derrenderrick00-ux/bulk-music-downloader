# Bulk Music Downloader

A lightweight Ubuntu-first Python CLI for importing a large song list, searching configured sources, downloading sequentially, retrying, switching providers, and resuming batches.

## Important source / copyright note

This project deliberately does **not** scrape Tubidy, bypass access controls, defeat DRM, or extract audio from streaming services. Tubidy has no stable, officially supported public API documented here, so the included `TubidyProvider` is an explicit safe placeholder that reports it is not configured for automated access. Add Tubidy only if you have a permitted integration method or authorized direct download URLs.

The working provider included in this release is Internet Archive's public metadata/download interface. Search results are not guaranteed to be music or to be licensed for every intended use: check each item's rights/usage terms before downloading. The app filters for audio media and provides a manual confirmation step for uncertain matches. It does not attempt to evade restrictions.

## Requirements

- Ubuntu 22.04+ (tested target; not acceptance-tested on your machine)
- Python 3.10+
- Internet connection

## Install

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
unzip bulk-music-downloader.zip
cd bulk-music-downloader
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

Optional development dependencies:

```bash
python -m pip install -e ".[dev]"
pytest
```

## Quick start

Create a text file with one track per line:

```text
Blinding Lights | The Weeknd
Believer | Imagine Dragons
Counting Stars | OneRepublic
```

Then:

```bash
music-batch import songs.txt
music-batch review
music-batch sources
music-batch start
```

CSV imports accept columns named `title` and `artist` (case-insensitive). TXT accepts `Title | Artist`, `Title - Artist`, or `Title<TAB>Artist`.

Default downloads folder: `~/Music/BulkDownloads`

## Commands

```text
music-batch                 Interactive menu
music-batch import FILE     Import a TXT or CSV list
music-batch review          Review pending queue
music-batch start           Start / continue the queue
music-batch pause            Set a pause request (takes effect between tracks)
music-batch resume           Resume queue processing
music-batch status           Show batch totals
music-batch retry-failed     Requeue failed tracks
music-batch sources          Show configured providers
music-batch config-show      Show configuration
music-batch config-set KEY VALUE
music-batch history          Show recent attempts
```

`pause` is a cooperative pause request stored in SQLite. If a download is actively in progress, it finishes or times out before the next track boundary. `resume` clears the request.

## Sources and fallback

- `internet_archive`: working search/download adapter for audio files exposed by Internet Archive metadata. Check usage rights for each item.
- `tubidy`: placeholder adapter. Automated site scraping is intentionally not implemented.
- `direct_url`: supports an explicitly supplied, authorized direct audio URL for an individual track. This is useful for sources that provide direct download links.

Providers are tried in configured order. Each provider gets up to three attempts. After the configured retries fail for one provider, the engine searches the next provider; all failures mark the track failed without stopping the batch. Search matches are shown for confirmation unless `--yes` is passed. The `--yes` option accepts the top-ranked result and should only be used when you trust the configured source and matching quality.

## Configuration

Configuration is stored in `~/.config/bulk-music-downloader/config.toml`. Override defaults with:

```bash
music-batch config-set download_dir '~/Music/BulkDownloads'
music-batch config-set retries_per_provider 3
music-batch config-set providers 'internet_archive,tubidy,direct_url'
music-batch config-set request_timeout 30
```

`direct_url` is only usable when a track has a direct URL stored in the database. The initial import formats do not include URL columns; direct URLs can be added later through the database or a future importer extension.

## Data and recovery

- SQLite database: `~/.local/share/bulk-music-downloader/downloads.db`
- Logs: `~/.local/state/bulk-music-downloader/app.log`
- Queue state is committed after each track and each attempt.
- Existing completed tracks are not downloaded again.
- Downloads are written to `.part` files and renamed only after a successful response and basic audio validation.
- `retry-failed` requeues failed tracks.

## Known limitations in this build (Milestones 0–7)

1. No automated Tubidy integration; it has no documented supported API in this project. Do not use brittle scraping or bypass mechanisms.
2. Internet Archive search can return non-studio versions, live recordings, covers, and non-music audio. Review results carefully.
3. MP3 is preferred when available, but some public-domain/authorized archive items may be OGG, FLAC, WAV, or another audio format. The app preserves the source format rather than transcoding.
4. This release has not completed Milestone 8 acceptance testing. Test it on your Ubuntu machine and report issues before release hardening.
5. Pause is cooperative and does not interrupt an in-flight HTTP transfer.
