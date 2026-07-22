"""Buckets MusicBrainz's raw folksonomy tags (freeform, community-voted —
see music_genre_sync.py's module docstring) into a small set of broad
genres for browsing in Quail Music's Genres tab. Without this, "genre" in
practice meant hundreds of near-duplicate or outright junk tags
("contemporary r&b" vs "r&b" vs "canadian r&b", or nonsense like
"hummus"/"englisch"/"billboard hot 100" that aren't genres at all) —
too granular to actually browse by.

This is deliberately a coarse keyword classifier, not a precise
taxonomy — genre classification is inherently fuzzy, and the goal here is
"meaningfully fewer buckets a person would actually browse," not a
perfect answer for every edge case.
"""
from __future__ import annotations

UNKNOWN_GENRE = "Unknown Genre"

# Checked top to bottom, first match wins — order matters a lot here.
# More specific/identifying keywords go first (e.g. "hip hop" before
# "pop", so "alternative hip hop" lands in Hip Hop, not Alternative or
# Pop) since a raw tag is often a compound like "<qualifier> <genre>".
_RULES: list[tuple[str, list[str]]] = [
    ("Hip Hop", ["hip hop", "trap", "drill", "boom bap", "grime", "rap"]),
    ("R&B", ["r&b", "rnb", "soul", "funk"]),
    ("Reggae", ["reggae", "dancehall", "dub"]),
    ("Country", ["country"]),
    ("Latin", ["latin"]),
    ("K-Pop", ["k pop", "kpop"]),
    ("Afrobeats", ["afrobeat"]),
    ("Jazz", ["jazz"]),
    ("Classical", ["classical"]),
    ("Blues", ["blues"]),
    ("Folk", ["folk", "singer songwriter", "celtic"]),
    ("Rock", ["rock", "punk", "metal", "grunge"]),
    ("Electronic", ["electronic", "edm", "trance", "house", "techno", "trip hop", "idm"]),
    ("Pop", ["pop", "boy band"]),
    ("Alternative", ["alternative", "indie", "alt z"]),
]


def _normalize_text(value: str) -> str:
    # Plain substring matching, not word-boundary — this domain is genre
    # *tags*, not prose, and a lot of real tags are compound words with no
    # separator at all ("electropop", "afrobeats"), which a \bword\b regex
    # simply can't match against a keyword like "pop" or "afrobeat". False
    # positives from stray substrings ("trapeze" containing "rap") aren't
    # a real risk here since MusicBrainz tags are short, genre-specific
    # strings, not arbitrary text. Hyphens are folded to spaces on both
    # sides of the comparison so "trip-hop" and "trip hop" match the same
    # keyword regardless of which punctuation MusicBrainz used.
    return value.lower().replace("-", " ")


def normalize_genre(raw: str) -> str:
    if not raw or raw == UNKNOWN_GENRE:
        return UNKNOWN_GENRE
    text = _normalize_text(raw)
    for bucket, keywords in _RULES:
        if any(_normalize_text(kw) in text for kw in keywords):
            return bucket
    # Junk tags (decades, artist names, chart names, language labels,
    # aesthetic/mood words, etc.) that don't map to any real genre bucket
    # collapse into the same "Unknown Genre" the rest of the pipeline
    # already uses for tracks with no MusicBrainz genre data at all —
    # consistent rather than inventing a second catch-all category.
    return UNKNOWN_GENRE
