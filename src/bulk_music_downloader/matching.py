import re
from difflib import SequenceMatcher


def normalize(s: str) -> str:
    # Remove version notes in parentheses and square brackets.
    s = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", s.lower())

    # Normalize punctuation and whitespace.
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def score_match(
    wanted_title: str,
    wanted_artist: str,
    found_title: str,
    found_artist: str,
) -> float:
    title = SequenceMatcher(
        None, normalize(wanted_title), normalize(found_title)
    ).ratio()

    artist = SequenceMatcher(
        None, normalize(wanted_artist), normalize(found_artist)
    ).ratio()

    return round(title * 0.65 + artist * 0.35, 4)


def detect_version(title: str) -> str:
    t = title.lower()

    for token, label in [
        ("live", "live"),
        ("remix", "remix"),
        ("acoustic", "acoustic"),
        ("instrumental", "instrumental"),
        ("cover", "cover"),
        ("karaoke", "karaoke"),
        ("demo", "demo"),
    ]:
        if token in t:
            return label

    return "studio_or_unspecified"
