import re
from difflib import SequenceMatcher


VERSION_PATTERNS = {
    "live": (
        r"\blive\b",
        r"\blive\s+at\b",
        r"\blive\s+from\b",
    ),
    "remix": (
        r"\bremix\b",
        r"\bremixed\b",
    ),
    "acoustic": (
        r"\bacoustic\b",
        r"\bunplugged\b",
    ),
    "instrumental": (
        r"\binstrumental\b",
        r"\bkaraoke\b",
        r"\bbacking\s+track\b",
    ),
    "cover": (
        r"\bcover\b",
        r"\bcovered\s+by\b",
    ),
    "demo": (
        r"\bdemo\b",
        r"\bdemonstration\b",
    ),
    "radio_edit": (
        r"\bradio\s+edit\b",
        r"\bradio\s+version\b",
    ),
    "extended": (
        r"\bextended\b",
        r"\bextended\s+mix\b",
    ),
}


def normalize(value: str | None) -> str:
    """
    Normalize text for comparison.

    Removes bracketed version notes, punctuation and repeated
    whitespace. Version information is evaluated separately.
    """
    if not value:
        return ""

    text = value.casefold()

    # Remove common bracketed release/version annotations.
    text = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", text)

    # Normalize common Unicode punctuation.
    text = text.replace("&", " and ")

    # Keep letters and numbers from all Unicode scripts.
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)

    return " ".join(text.split())


def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0

    if left == right:
        return 1.0

    return SequenceMatcher(None, left, right).ratio()


def _artist_tokens(value: str | None) -> set[str]:
    """
    Extract meaningful artist tokens.

    This allows comparisons such as:
      Artist A feat. Artist B
      Artist A featuring Artist B
      Artist A & Artist B

    It does not treat a completely different artist as a match.
    """
    if not value:
        return set()

    text = value.casefold()

    separators = (
        r"\bfeat\.?\b",
        r"\bfeaturing\b",
        r"\bft\.?\b",
        r"\bwith\b",
        r"\band\b",
        r"\bx\b",
        r"&",
        r",",
        r";",
        r"\|",
    )

    for separator in separators:
        text = re.sub(separator, "|", text)

    parts = []

    for part in text.split("|"):
        cleaned = normalize(part)

        if cleaned:
            parts.append(cleaned)

    return set(parts)


def artist_similarity(wanted_artist: str, found_artist: str) -> float:
    """
    Compare artist identities independently of title similarity.

    A candidate with an unrelated artist receives a low score
    even if its title is an exact match.
    """
    wanted = normalize(wanted_artist)
    found = normalize(found_artist)

    if not wanted or not found:
        return 0.0

    if wanted == found:
        return 1.0

    wanted_tokens = _artist_tokens(wanted_artist)
    found_tokens = _artist_tokens(found_artist)

    # Exact match of one artist credit in a multi-artist result.
    if wanted_tokens and found_tokens:
        if wanted_tokens.intersection(found_tokens):
            return 0.95

    direct = _similarity(wanted, found)

    # Token-level comparison helps with reordered artist credits.
    wanted_words = set(wanted.split())
    found_words = set(found.split())

    if wanted_words and found_words:
        overlap = len(wanted_words & found_words)
        union = len(wanted_words | found_words)
        token_score = overlap / union if union else 0.0
    else:
        token_score = 0.0

    return round(max(direct, token_score), 4)


def detect_version(title: str) -> str:
    """
    Identify a known recording version from its title.
    """
    text = (title or "").casefold()

    for version, patterns in VERSION_PATTERNS.items():
        if any(re.search(pattern, text) for pattern in patterns):
            return version

    return "studio_or_unspecified"


def compare_versions(
    wanted_title: str,
    found_title: str,
) -> bool | None:
    """
    Compare requested and discovered recording versions.

    True: compatible version.
    False: known mismatch.
    None: insufficient information.
    """
    wanted = detect_version(wanted_title)
    found = detect_version(found_title)

    if wanted == "studio_or_unspecified" and found == "studio_or_unspecified":
        return True

    if wanted == "studio_or_unspecified":
        return False

    if found == "studio_or_unspecified":
        return None

    return wanted == found


def match_details(
    wanted_title: str,
    wanted_artist: str,
    found_title: str,
    found_artist: str,
) -> dict:
    """
    Return independent title and artist scores plus a conservative
    overall confidence score.

    The artist gate prevents an exact title from making an unrelated
    artist look like a safe match.
    """
    title_score = _similarity(
        normalize(wanted_title),
        normalize(found_title),
    )

    artist_score = artist_similarity(
        wanted_artist,
        found_artist,
    )

    version_match = compare_versions(
        wanted_title,
        found_title,
    )

    combined = (title_score * 0.65) + (artist_score * 0.35)

    # A title match cannot override a poor artist match.
    if artist_score < 0.70:
        combined = min(combined, 0.69)

    # A known recording-version mismatch is not a safe match.
    if version_match is False:
        combined = min(combined, 0.49)

    return {
        "score": round(combined, 4),
        "title_score": round(title_score, 4),
        "artist_score": round(artist_score, 4),
        "version_match": version_match,
    }


def score_match(
    wanted_title: str,
    wanted_artist: str,
    found_title: str,
    found_artist: str,
) -> float:
    """
    Backwards-compatible scoring function.

    Existing engine code can continue calling score_match().
    """
    return match_details(
        wanted_title,
        wanted_artist,
        found_title,
        found_artist,
    )["score"]
