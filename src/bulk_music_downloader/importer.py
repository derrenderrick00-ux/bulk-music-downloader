import csv
from pathlib import Path


def parse_file(path: str) -> list[tuple[str, str]]:
    p = Path(path)

    if not p.is_file():
        raise FileNotFoundError(path)

    rows = []

    if p.suffix.lower() == ".csv":
        with p.open(newline="", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)

            if not reader.fieldnames:
                raise ValueError(
                    "CSV must have a header row with title and artist columns."
                )

            fields = {
                field.strip().lower(): field
                for field in reader.fieldnames
                if field
            }

            if "title" not in fields or "artist" not in fields:
                raise ValueError(
                    "CSV requires columns named title and artist."
                )

            for row in reader:
                title = (row.get(fields["title"]) or "").strip()
                artist = (row.get(fields["artist"]) or "").strip()

                if title and artist:
                    rows.append((title, artist))

    else:
        for line_number, line in enumerate(
            p.read_text(encoding="utf-8-sig").splitlines(), 1
        ):
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            if "|" in line:
                title, artist = line.split("|", 1)
            elif "\t" in line:
                title, artist = line.split("\t", 1)
            elif " - " in line:
                title, artist = line.rsplit(" - ", 1)
            else:
                raise ValueError(
                    f"Line {line_number}: expected 'Title | Artist'."
                )

            title = title.strip()
            artist = artist.strip()

            if title and artist:
                rows.append((title, artist))

    if not rows:
        raise ValueError("No valid title/artist rows found.")

    return rows
