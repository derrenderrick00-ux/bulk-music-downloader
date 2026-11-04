import csv
from pathlib import Path

def parse_file(path: str) -> list[tuple[str, str]]:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(path)
    if p.suffix.lower() == ".csv":
        with p.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                raise ValueError("CSV must have a header row with title and artist columns.")
            fields = {x.strip().lower(): x for x in reader.fieldnames if x}
            if "title" not in fields or "artist" not in fields:
                raise ValueError("CSV requires columns named title and artist.")
            rows = [(r.get(fields["title"], "").strip(), r.get(fields["artist"], "").strip()) for r in reader]
    else:
        rows = []
        for line_no, line in enumerate(p.read_text(encoding="utf-8-sig").splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "|" in line:
                title, artist = line.split("|", 1)
            elif "\\t" in line:
                title, artist = line.split("\\t", 1)
            elif " - " in line:
                title, artist = line.rsplit(" - ", 1)
            else:
                raise ValueError(f"Line {line_no}: expected 'Title | Artist'.")
            rows.append((title.strip(), artist.strip()))
    cleaned = [(t, a) for t, a in rows if t and a]
    if not cleaned:
        raise ValueError("No valid title/artist rows found.")
    return cleaned
