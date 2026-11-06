from __future__ import annotations
import csv
import typer
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from .config import load_config, save_config, DEFAULTS, CONFIG_FILE
from .database import connect, add_track, get_tracks, set_paused, get_tracks
from .importer import parse_file
from .providers import build_providers
from .engine import run_queue

app = typer.Typer(help="Bulk Music Downloader — sequential, resumable audio downloads.")
console = Console()

@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        interactive()

@app.command("import")
def import_songs(file: str = typer.Argument(..., help="TXT or CSV file containing title and artist.")):
    try:
        songs = parse_file(file)
        db = connect()
        added = duplicates = 0
        for title, artist in songs:
            fresh, _ = add_track(db, title, artist)
            added += int(fresh)
            duplicates += int(not fresh)
        console.print(f"[green]Imported {added} new tracks.[/green] Duplicates ignored: {duplicates}.")
    except Exception as exc:
        raise typer.BadParameter(str(exc))

@app.command()
def review():
    db = connect()
    rows = get_tracks(db)
    table = Table("ID", "Title", "Artist", "Status", "Source")
    for r in rows:
        table.add_row(str(r["id"]), r["title"], r["artist"], r["status"], r["source"] or "—")
    console.print(table)
    console.print(f"Total tracks: {len(rows)}")

@app.command()
def start(
    interactive: bool = typer.Option(
        False,
        "--interactive",
        help="Ask me to select each search result instead of automatic matching.",
    )
):
    db, config = connect(), load_config()
    set_paused(db, False)

    run_queue(
        db,
        config,
        build_providers(config),
        auto_accept=not interactive,
    )

@app.command()
def pause():
    set_paused(connect(), True)
    console.print("[yellow]Pause requested; it will take effect between tracks.[/yellow]")

@app.command()
def resume():
    db = connect()
    set_paused(db, False)
    console.print("[green]Pause request cleared. Run 'music-batch start' to continue.[/green]")

@app.command("retry-failed")
def retry_failed(yes: bool = typer.Option(False, "--yes")):
    db, config = connect(), load_config()
    run_queue(db, config, build_providers(config), auto_accept=yes, only_failed=True)

@app.command()
def status():
    db = connect()
    rows = db.execute("SELECT status, COUNT(*) n FROM tracks GROUP BY status").fetchall()
    counts = {r["status"]: r["n"] for r in rows}
    total = sum(counts.values())
    table = Table("Status", "Count")
    for name in ("pending", "searching", "downloading", "completed", "failed", "interrupted"):
        table.add_row(name, str(counts.get(name, 0)))
    console.print(table)
    console.print(f"Total: {total}")

@app.command()
def sources():
    config = load_config()
    table = Table("Priority", "Provider", "Availability")
    descriptions = {
        "internet_archive": "Search/download adapter; verify item rights",
        "tubidy": "Placeholder; no supported automated API configured",
        "direct_url": "Authorized direct URL adapter; URL import not yet exposed",
    }
    for i, name in enumerate(config["providers"], 1):
        table.add_row(str(i), name, descriptions.get(name, "Unknown provider"))
    console.print(table)

@app.command()
def config_show():
    config = load_config()
    for key, value in config.items():
        console.print(f"[cyan]{key}[/cyan] = {value}")
    console.print(f"Config file: {CONFIG_FILE}")

@app.command("config-set")
def config_set(key: str, value: str):
    config = load_config()
    if key not in DEFAULTS:
        raise typer.BadParameter(f"Unknown setting. Choose: {', '.join(DEFAULTS)}")
    default = DEFAULTS[key]
    try:
        if isinstance(default, bool):
            parsed = value.lower() in ("1", "true", "yes", "on")
        elif isinstance(default, int):
            parsed = int(value)
        elif isinstance(default, float):
            parsed = float(value)
        elif isinstance(default, list):
            parsed = [x.strip() for x in value.split(",") if x.strip()]
            invalid = set(parsed) - {"internet_archive", "tubidy", "direct_url"}
            if invalid:
                raise ValueError(f"Unsupported providers: {invalid}")
        else:
            parsed = value
        config[key] = parsed
        save_config(config)
        console.print(f"[green]Updated {key}.[/green]")
    except Exception as exc:
        raise typer.BadParameter(str(exc))

@app.command()
def history(limit: int = typer.Option(30, min=1, max=500)):
    db = connect()
    rows = db.execute("""SELECT a.created_at,t.title,t.artist,a.provider,a.attempt_number,a.outcome,a.detail
                         FROM attempts a JOIN tracks t ON t.id=a.track_id
                         ORDER BY a.id DESC LIMIT ?""", (limit,)).fetchall()
    table = Table("Time", "Track", "Provider", "Try", "Outcome", "Detail")
    for r in rows:
        table.add_row(r["created_at"], f'{r["title"]} — {r["artist"]}', r["provider"],
                      str(r["attempt_number"]), r["outcome"], (r["detail"] or "")[:70])
    console.print(table)

def interactive():
    console.print(Panel.fit("[bold cyan]BULK MUSIC DOWNLOADER[/bold cyan]\\nUbuntu CLI • Sequential • Resumable"))
    actions = {
        "1": ("Import music list", lambda: import_songs(typer.Argument(...))), # handled separately
    }
    while True:
        console.print("\\n[bold]1.[/bold] Import music list\\n[bold]2.[/bold] Review queue\\n[bold]3.[/bold] Configure sources\\n[bold]4.[/bold] Start downloads\\n[bold]5.[/bold] Pause request\\n[bold]6.[/bold] Resume\\n[bold]7.[/bold] Status\\n[bold]8.[/bold] Retry failed\\n[bold]9.[/bold] History\\n[bold]10.[/bold] Settings\\n[bold]0.[/bold] Exit")
        choice = console.input("\\nSelect option: ").strip()
        if choice == "0":
            break
        elif choice == "1":
            path = console.input("Path to TXT/CSV: ").strip()
            try: import_songs(path)
            except Exception as e: console.print(f"[red]{e}[/red]")
        elif choice == "2": review()
        elif choice == "3": sources()
        elif choice == "4":
            yes = console.input("Auto-accept top match? (y/N): ").lower() == "y"
            start(yes)
        elif choice == "5": pause()
        elif choice == "6": resume()
        elif choice == "7": status()
        elif choice == "8":
            yes = console.input("Auto-accept top match? (y/N): ").lower() == "y"
            retry_failed(yes)
        elif choice == "9": history()
        elif choice == "10": config_show()
        else: console.print("[yellow]Choose a listed option.[/yellow]")

if __name__ == "__main__":
    app()
