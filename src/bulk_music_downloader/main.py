from __future__ import annotations

import typer

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from .config import (
    load_config,
    save_config,
    DEFAULTS,
    CONFIG_FILE,
)
from .database import (
    connect,
    get_tracks,
    set_paused,
    replace_queue,
)
from .importer import parse_file
from .providers import build_providers
from .engine import run_queue


app = typer.Typer(
    help="Bulk Music Downloader — sequential, resumable audio downloads."
)

console = Console()

SUPPORTED_PROVIDERS = {
    "audius",
    "jamendo",
    "freetouse",
    "ccmixter",
    "internet_archive",
    "direct_url",
    "tubidy",
}


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        interactive()


@app.command("import")
def import_songs(
    file: str = typer.Argument(
        ...,
        help="TXT or CSV file containing title and artist.",
    )
):
    try:
        songs = parse_file(file)
        db = connect()
        result = replace_queue(db, songs)

        console.print(
            "\n[bold green]Queue replaced successfully.[/bold green]"
        )
        console.print(f"Pending tracks: {result['queued']}")
        console.print(
            f"Already downloaded: {result['already_downloaded']}"
        )
        console.print(
            f"Duplicate entries ignored: {result['duplicates']}"
        )

    except Exception as exc:
        raise typer.BadParameter(str(exc)) from exc


@app.command()
def review():
    db = connect()
    rows = get_tracks(db)

    table = Table("ID", "Title", "Artist", "Status", "Source")

    for row in rows:
        table.add_row(
            str(row["id"]),
            row["title"],
            row["artist"],
            row["status"],
            row["source"] or "—",
        )

    console.print(table)
    console.print(f"Total tracks: {len(rows)}")


@app.command()
def start(
    interactive: bool = typer.Option(
        False,
        "--interactive",
        help="Select each search result manually.",
    )
):
    db = connect()
    config = load_config()

    set_paused(db, False)

    return run_queue(
        db,
        config,
        build_providers(config),
        auto_accept=not interactive,
    )


@app.command()
def pause():
    set_paused(connect(), True)
    console.print(
        "[yellow]Pause requested; it will take effect between tracks.[/yellow]"
    )


@app.command()
def resume():
    db = connect()
    set_paused(db, False)

    console.print(
        "[green]Pause request cleared. Run 'music-batch start' to continue.[/green]"
    )


@app.command("retry-failed")
def retry_failed(
    yes: bool = typer.Option(False, "--yes")
):
    db = connect()
    config = load_config()

    return run_queue(
        db,
        config,
        build_providers(config),
        auto_accept=yes,
        only_failed=True,
    )


@app.command()
def status():
    db = connect()

    rows = db.execute(
        """
        SELECT status, COUNT(*) AS n
        FROM tracks
        WHERE active_queue = 1
        GROUP BY status
        """
    ).fetchall()

    counts = {
        row["status"]: row["n"]
        for row in rows
    }

    total = sum(counts.values())

    table = Table("Status", "Count")

    for name in (
        "pending",
        "searching",
        "downloading",
        "completed",
        "failed",
        "interrupted",
    ):
        table.add_row(
            name,
            str(counts.get(name, 0)),
        )

    console.print(table)
    console.print(f"Total: {total}")


@app.command()
def sources():
    config = load_config()

    descriptions = {
        "audius": (
            "Search and download tracks explicitly marked downloadable"
        ),
        "jamendo": (
            "Search and download; requires a valid client ID"
        ),
        "freetouse": (
            "Search adapter; automatic downloads require rights review"
        ),
        "ccmixter": (
            "Creative Commons search adapter; automatic downloads require rights review"
        ),
        "internet_archive": (
            "Search and download verified permissive-licensed originals"
        ),
        "direct_url": (
            "Authorized HTTPS direct URL adapter; not searched automatically"
        ),
        "tubidy": (
            "Placeholder; no supported automated API configured"
        ),
    }

    table = Table("Priority", "Provider", "Availability")

    for index, name in enumerate(config["providers"], 1):
        table.add_row(
            str(index),
            name,
            descriptions.get(name, "Unknown provider"),
        )

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
        raise typer.BadParameter(
            f"Unknown setting. Choose: {', '.join(DEFAULTS)}"
        )

    default = DEFAULTS[key]

    try:
        if isinstance(default, bool):
            parsed = value.lower() in (
                "1",
                "true",
                "yes",
                "on",
            )

        elif isinstance(default, int):
            parsed = int(value)

        elif isinstance(default, float):
            parsed = float(value)

        elif isinstance(default, list):
            parsed = [
                item.strip()
                for item in value.split(",")
                if item.strip()
            ]

            invalid = set(parsed) - SUPPORTED_PROVIDERS

            if invalid:
                raise ValueError(
                    "Unsupported providers: "
                    + ", ".join(sorted(invalid))
                )

            if not parsed:
                raise ValueError(
                    "At least one provider must be configured."
                )

            # Preserve the user's provider order while removing duplicates.
            parsed = list(dict.fromkeys(parsed))

        else:
            parsed = value

        config[key] = parsed
        save_config(config)

        console.print(
            f"[green]Updated {key}.[/green]"
        )

    except Exception as exc:
        raise typer.BadParameter(str(exc)) from exc


@app.command()
def history(
    limit: int = typer.Option(
        30,
        min=1,
        max=500,
    )
):
    db = connect()

    rows = db.execute(
        """
        SELECT
            a.created_at,
            t.title,
            t.artist,
            a.provider,
            a.attempt_number,
            a.outcome,
            a.detail
        FROM attempts a
        JOIN tracks t ON t.id = a.track_id
        ORDER BY a.id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    table = Table(
        "Time",
        "Track",
        "Provider",
        "Try",
        "Outcome",
        "Detail",
    )

    for row in rows:
        table.add_row(
            row["created_at"],
            f'{row["title"]} — {row["artist"]}',
            row["provider"],
            str(row["attempt_number"]),
            row["outcome"],
            (row["detail"] or "")[:70],
        )

    console.print(table)


def interactive():
    console.print(
        Panel.fit(
            "[bold cyan]BULK MUSIC DOWNLOADER[/bold cyan]\n"
            "Ubuntu CLI • Sequential • Resumable"
        )
    )

    while True:
        console.print(
            "\n[bold]1.[/bold] Import music list\n"
            "[bold]2.[/bold] Review queue\n"
            "[bold]3.[/bold] Configure sources\n"
            "[bold]4.[/bold] Start downloads\n"
            "[bold]5.[/bold] Pause request\n"
            "[bold]6.[/bold] Resume\n"
            "[bold]7.[/bold] Status\n"
            "[bold]8.[/bold] Retry failed\n"
            "[bold]9.[/bold] History\n"
            "[bold]10.[/bold] Settings\n"
            "[bold]0.[/bold] Exit"
        )

        choice = console.input(
            "\nSelect option: "
        ).strip()

        if choice == "0":
            break

        elif choice == "1":
            path = console.input(
                "Path to TXT/CSV: "
            ).strip()

            try:
                import_songs(path)
            except Exception as exc:
                console.print(f"[red]{exc}[/red]")

        elif choice == "2":
            review()

        elif choice == "3":
            sources()

        elif choice == "4":
            yes = (
                console.input(
                    "Auto-accept top match? (y/N): "
                ).lower()
                == "y"
            )
            start(yes)

        elif choice == "5":
            pause()

        elif choice == "6":
            resume()

        elif choice == "7":
            status()

        elif choice == "8":
            yes = (
                console.input(
                    "Auto-accept top match? (y/N): "
                ).lower()
                == "y"
            )
            retry_failed(yes)

        elif choice == "9":
            history()

        elif choice == "10":
            config_show()

        else:
            console.print(
                "[yellow]Choose a listed option.[/yellow]"
            )


if __name__ == "__main__":
    app()
