from __future__ import annotations

import re
from pathlib import Path

from rich.console import Console

from .database import (
    get_tracks,
    set_status,
    record_attempt,
    is_paused,
)

from .search import (
    search_all,
    is_download_eligible,
)


console = Console()

AUTO_ACCEPT_THRESHOLD = 0.82


def safe_filename(value: str) -> str:
    value = re.sub(
        r'[\\/:*?"<>|\x00-\x1f]',
        "_",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    ).strip(" .")

    return value[:150] or "track"


def _display_candidates(
    candidates,
    title: str,
    artist: str,
) -> None:
    console.print(
        f"\n[bold]Eligible candidates for "
        f"{title} — {artist}[/bold]"
    )

    for index, item in enumerate(candidates, 1):
        console.print(
            f"{index}. [{item.provider}] "
            f"{item.title} — {item.artist} "
            f"| score={item.score:.3f} "
            f"| title={item.title_score:.3f} "
            f"| artist={item.artist_score:.3f} "
            f"| version={item.version}"
        )


def choose_result(
    results,
    title,
    artist,
    auto_accept,
):
    """Only permit selection of candidates with verified rights."""

    eligible = [
        item
        for item in results
        if is_download_eligible(item)
    ]

    if not eligible:
        console.print(
            "[yellow]No candidate has verified "
            "automatic-download permission.[/yellow]"
        )
        return None

    eligible.sort(
        key=lambda item: item.score,
        reverse=True,
    )

    if auto_accept:
        best = eligible[0]

        if best.score >= AUTO_ACCEPT_THRESHOLD:
            return best

        console.print(
            f"[yellow]Best eligible match scored "
            f"{best.score:.3f}; automatic threshold is "
            f"{AUTO_ACCEPT_THRESHOLD:.2f}. Skipping.[/yellow]"
        )
        return None

    _display_candidates(
        eligible,
        title,
        artist,
    )

    while True:
        choice = console.input(
            "Select candidate number, [s]kip, or [q]uit: "
        ).strip().lower()

        if choice == "s":
            return None

        if choice == "q":
            raise KeyboardInterrupt

        if choice.isdigit():
            number = int(choice)

            if 1 <= number <= len(eligible):
                return eligible[number - 1]

        console.print(
            "[yellow]Invalid selection.[/yellow]"
        )


def _validate_audio(path: Path) -> None:
    if not path.exists() or not path.is_file():
        raise ValueError(
            "Provider did not create an output file."
        )

    if path.stat().st_size < 1024:
        raise ValueError(
            "Downloaded file is too small to be valid audio."
        )

    try:
        from mutagen import File as MutagenFile
    except ImportError:
        # Size validation remains available without Mutagen.
        return

    if MutagenFile(path) is None:
        raise ValueError(
            "Downloaded file is not recognized as a supported audio file."
        )


def _cleanup_partial_files(output_base: Path) -> int:
    """Remove partial files belonging to one track only."""

    removed = 0

    patterns = (
        f"{output_base.stem}.*.part",
        f"{output_base.name}.part",
    )

    candidates = set()

    for pattern in patterns:
        candidates.update(output_base.parent.glob(pattern))

    for path in candidates:
        try:
            if path.is_file():
                path.unlink()
                removed += 1
        except OSError as exc:
            console.print(
                f"[yellow]Could not remove partial file "
                f"{path.name}: {exc}[/yellow]"
            )

    return removed


def _process_track(
    db,
    track,
    config,
    providers,
    auto_accept,
    search_limit,
    retries,
    timeout,
    output_base,
):
    """Process one track and return completed, failed, or skipped."""

    track_id = track["id"]
    title = str(track["title"])
    artist = str(track["artist"])

    set_status(
        db,
        track_id,
        "searching",
    )

    console.print(
        f"\n[bold cyan]Searching: "
        f"{title} — {artist}[/bold cyan]"
    )

    # --------------------------------------------------
    # STEP 1: Search all providers.
    # --------------------------------------------------

    batch = search_all(
        providers,
        title,
        artist,
        search_limit,
    )

    attempt_number = 0

    for provider_name, count in batch.provider_counts.items():
        attempt_number += 1

        if provider_name in batch.provider_errors:
            outcome = "search_failed"
            detail = batch.provider_errors[provider_name][:500]

        elif count:
            outcome = "search_results"
            detail = f"{count} candidate(s) returned"

        else:
            outcome = "no_match"
            detail = "No valid candidates returned"

        record_attempt(
            db,
            track_id,
            provider_name,
            attempt_number,
            outcome,
            detail,
        )

    if not batch.candidates:
        console.print(
            "[yellow]No search candidates found.[/yellow]"
        )

        set_status(
            db,
            track_id,
            "failed",
        )
        return "failed"

    # --------------------------------------------------
    # STEP 2: Enforce eligibility.
    # --------------------------------------------------

    eligible = [
        item
        for item in batch.candidates
        if is_download_eligible(item)
    ]

    excluded = len(batch.candidates) - len(eligible)

    if excluded:
        console.print(
            f"[yellow]{excluded} candidate(s) withheld "
            "because download rights or version checks "
            "were not satisfied.[/yellow]"
        )

    if not eligible:
        console.print(
            "[yellow]Candidates found, but none are "
            "eligible for download.[/yellow]"
        )

        set_status(
            db,
            track_id,
            "failed",
        )
        return "failed"

    # --------------------------------------------------
    # STEP 3: Select a candidate.
    # --------------------------------------------------

    selected = choose_result(
        eligible,
        title,
        artist,
        auto_accept,
    )

    if selected is None:
        set_status(
            db,
            track_id,
            "pending",
        )
        return "skipped"

    candidates = (
        [selected]
        + [
            item
            for item in eligible
            if item is not selected
        ]
    )

    success = False

    # --------------------------------------------------
    # STEP 4: Download and fallback.
    # --------------------------------------------------

    for candidate in candidates:
        set_status(
            db,
            track_id,
            "downloading",
            source=candidate.provider,
        )

        for retry_number in range(1, retries + 1):
            attempt_number += 1

            try:
                provider = next(
                    p
                    for p in providers
                    if p.name == candidate.provider
                )

                output_path = Path(
                    provider.download(
                        candidate,
                        output_base,
                        timeout,
                    )
                )

                _validate_audio(output_path)

                record_attempt(
                    db,
                    track_id,
                    candidate.provider,
                    attempt_number,
                    "success",
                    (
                        "Downloaded and validated: "
                        f"{output_path.name}"
                    ),
                )

                set_status(
                    db,
                    track_id,
                    "completed",
                    source=candidate.provider,
                    file_path=str(output_path),
                    version=candidate.version,
                )

                console.print(
                    f"[green]Completed: {output_path}[/green]"
                )

                success = True
                break

            except Exception as exc:
                detail = (
                    f"{type(exc).__name__}: {exc}"
                )[:500]

                record_attempt(
                    db,
                    track_id,
                    candidate.provider,
                    attempt_number,
                    "download_failed",
                    (
                        f"Attempt {retry_number}/{retries}: "
                        f"{detail}"
                    ),
                )

                console.print(
                    f"[yellow]{candidate.provider} "
                    f"attempt {retry_number}/{retries} "
                    f"failed: {detail}[/yellow]"
                )

        if success:
            break

        console.print(
            f"[yellow]Trying the next eligible "
            f"candidate for {title}.[/yellow]"
        )

    # --------------------------------------------------
    # STEP 5: Final track status.
    # --------------------------------------------------

    if not success:
        set_status(
            db,
            track_id,
            "failed",
        )
        return "failed"

    return "completed"


def run_queue(
    db,
    config,
    providers,
    auto_accept=False,
    only_failed=False,
):
    """Search globally, select a permitted candidate, then fall back."""

    completed = 0
    failed = 0
    skipped = 0
    interrupted = 0

    # Recover tracks left in transient states by a previous
    # crash, forced shutdown, or interrupted run.
    stale_tracks = get_tracks(
        db,
        statuses=["searching", "downloading"],
    )

    recovered = 0

    for stale_track in stale_tracks:
        set_status(
            db,
            stale_track["id"],
            "interrupted",
        )
        recovered += 1

    if recovered:
        console.print(
            f"[yellow]Recovered {recovered} track(s) "
            "left in searching/downloading state. "
            "They are now marked interrupted.[/yellow]"
        )

    statuses = (
        ["failed"]
        if only_failed
        else ["pending", "interrupted"]
    )

    tracks = get_tracks(
        db,
        statuses=statuses,
    )

    search_limit = max(
        1,
        int(config.get("max_search_results", 8)),
    )

    retries = max(
        1,
        int(config.get("retries_per_provider", 1)),
    )

    timeout = max(
        1,
        int(config.get("request_timeout", 30)),
    )

    download_dir = Path(
        config["download_dir"]
    ).expanduser()

    for track in tracks:
        if is_paused(db):
            console.print(
                "[yellow]Pause requested; stopping before "
                "the next track.[/yellow]"
            )
            break

        track_id = track["id"]
        title = str(track["title"])
        artist = str(track["artist"])

        output_base = (
            download_dir
            / f"{safe_filename(f'{title} - {artist}')}.audio"
        )

        try:
            result = _process_track(
                db=db,
                track=track,
                config=config,
                providers=providers,
                auto_accept=auto_accept,
                search_limit=search_limit,
                retries=retries,
                timeout=timeout,
                output_base=output_base,
            )

            if result == "completed":
                completed += 1
            elif result == "failed":
                failed += 1
            elif result == "skipped":
                skipped += 1

        except KeyboardInterrupt:
            # KeyboardInterrupt inherits from BaseException, so it
            # must be handled separately from ordinary download errors.
            set_status(
                db,
                track_id,
                "interrupted",
            )

            removed = _cleanup_partial_files(output_base)

            interrupted += 1

            console.print(
                f"\n[yellow]Interrupted: {title} — {artist}.[/yellow]"
            )

            if removed:
                console.print(
                    f"[yellow]Removed {removed} partial file(s).[/yellow]"
                )

            console.print(
                "[yellow]The track can be resumed with "
                "'music-batch start'.[/yellow]"
            )
            break

    console.print(
        f"\n[bold]Queue summary:[/bold] "
        f"completed={completed}, "
        f"failed={failed}, "
        f"skipped={skipped}, "
        f"interrupted={interrupted}"
    )

    return {
        "completed": completed,
        "failed": failed,
        "skipped": skipped,
        "interrupted": interrupted,
    }
