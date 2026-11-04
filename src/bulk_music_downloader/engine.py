from __future__ import annotations
import re
from pathlib import Path
from rich.console import Console
from .database import get_tracks, set_status, record_attempt, is_paused
from .models import SearchResult
from .providers.base import ProviderError

console = Console()

def safe_filename(value: str) -> str:
    value = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    return value[:150] or "track"

def choose_result(results, title, artist, auto_accept):
    if not results:
        return None
    results = results[:8]
    if auto_accept:
        return results[0]
    console.print(f"\n[bold]Matches for {title} — {artist}[/bold]")
    for i, item in enumerate(results, 1):
        console.print(f" {i}. [{item.score:.0%}] {item.title} — {item.artist} "
                      f"[{item.version}] ({item.provider})")
        if item.rights:
            console.print(f"    Rights: {item.rights}")
        console.print(f"    {item.url}")
    while True:
        choice = console.input("Select match (1-8), s=skip this source, q=stop: ").strip().lower()
        if choice == "s":
            return None
        if choice == "q":
            raise KeyboardInterrupt
        if choice.isdigit() and 1 <= int(choice) <= len(results):
            return results[int(choice)-1]
        console.print("[yellow]Invalid selection.[/yellow]")

def run_queue(db, config, providers, auto_accept=False, only_failed=False):
    statuses = ["failed"] if only_failed else ["pending", "interrupted"]
    rows = get_tracks(db, statuses)
    if not rows:
        console.print("[yellow]No tracks in the selected queue.[/yellow]")
        return
    download_dir = Path(config["download_dir"]).expanduser()
    download_dir.mkdir(parents=True, exist_ok=True)
    completed = failed = skipped = 0
    for index, row in enumerate(rows, 1):
        if is_paused(db):
            console.print("[yellow]Pause requested. Stopping before next track.[/yellow]")
            break
        title, artist, track_id = row["title"], row["artist"], row["id"]
        console.rule(f"[bold cyan][{index}/{len(rows)}] {title} — {artist}")
        set_status(db, track_id, "searching")
        track_done = False
        track_skipped = False

        # Provider fallback: search, select, and attempt each provider in priority order.
        for provider in providers:
            if provider.name == "direct_url":
                continue
            try:
                results = provider.search(title, artist, int(config["max_search_results"]))
            except ProviderError as exc:
                record_attempt(db, track_id, provider.name, 0, "search_failed", str(exc))
                console.print(f"[yellow]{provider.name} search unavailable: {exc}[/yellow]")
                continue

            if not results:
                record_attempt(db, track_id, provider.name, 0, "no_match", "No results")
                continue

            selected = choose_result(results, title, artist, auto_accept)
            if selected is None:
                # In interactive mode, 'skip source' continues to the next provider.
                # In auto mode, no result means no selection.
                if not auto_accept:
                    continue
                continue

            # The match must be selected from this provider. A failed download advances
            # to the next provider and repeats search/matching there.
            for attempt in range(1, int(config["retries_per_provider"]) + 1):
                if is_paused(db):
                    console.print("[yellow]Pause requested; finishing current attempt boundary.[/yellow]")
                    break
                try:
                    set_status(db, track_id, "downloading", provider.name)
                    console.print(f"[cyan]Downloading via {provider.name} (attempt {attempt})...[/cyan]")
                    stem = safe_filename(f"{artist} - {title}")
                    destination = download_dir / (stem + ".audio")
                    path = provider.download(selected, destination, int(config["request_timeout"]))
                    if not path.exists() or path.stat().st_size < 1024:
                        raise ProviderError("Downloaded file failed basic size validation.")
                    try:
                        from mutagen import File as MutagenFile
                        audio = MutagenFile(str(path))
                        if audio is None:
                            raise ProviderError("File is not recognized as supported audio.")
                    except ImportError:
                        pass
                    set_status(db, track_id, "completed", provider.name, str(path), selected.version)
                    record_attempt(db, track_id, provider.name, attempt, "success", str(path))
                    completed += 1
                    track_done = True
                    console.print(f"[green]Completed: {path}[/green]")
                    break
                except Exception as exc:
                    record_attempt(db, track_id, provider.name, attempt, "download_failed", str(exc))
                    console.print(f"[red]{provider.name} attempt {attempt} failed: {exc}[/red]")
            if track_done:
                break
            if is_paused(db):
                break
            console.print(f"[yellow]Moving to next configured provider for: {title}[/yellow]")

        if track_done:
            continue
        if is_paused(db):
            set_status(db, track_id, "interrupted")
            break
        set_status(db, track_id, "failed")
        failed += 1
        console.print("[red]All configured providers exhausted. Track marked failed.[/red]")

    console.print(f"\n[bold]Run summary[/bold]  Completed: {completed}  Failed: {failed}  Skipped: {skipped}")
