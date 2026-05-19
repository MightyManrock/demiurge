"""
Naming helpers for the scenario builder.

  derive_initialism("The Warden's Compact") -> "WC"
  derive_db_filename("The Warden's Compact") -> "wardens_compact"
  validate_initialism("wc")  -> ("WC", None)
  validate_initialism("!!")  -> (None, "error message")
"""
from __future__ import annotations
import re

_INITIALISM_RE  = re.compile(r"^[A-Z0-9]{1,6}$")
_DB_FILENAME_RE = re.compile(r"^[a-z0-9_]+$")

# Filler words stripped when deriving the initialism / filename slug.
_LEADING_FILLERS = {"the", "a", "an"}


def _word_split(name: str) -> list[str]:
    """Split on whitespace and dashes; lowercase. Apostrophes are removed
    (not treated as separators) so "warden's" stays one word."""
    cleaned = name.replace("'", "").replace("’", "")  # straight + curly
    cleaned = re.sub(r"[^\w\s-]", " ", cleaned)
    return [w.lower() for w in re.split(r"[\s\-_]+", cleaned) if w]


def derive_initialism(name: str) -> str:
    words = _word_split(name)
    if words and words[0] in _LEADING_FILLERS:
        words = words[1:]
    if not words:
        return "NS"
    letters = "".join(w[0] for w in words if w).upper()
    return letters[:6] or "NS"


def derive_db_filename(name: str) -> str:
    words = _word_split(name)
    if words and words[0] in _LEADING_FILLERS:
        words = words[1:]
    if not words:
        return "new_scenario"
    return "_".join(words)


def validate_initialism(raw: str) -> tuple[str | None, str | None]:
    """Returns (normalized, None) on success or (None, error) on failure."""
    candidate = raw.strip().upper()
    if not candidate:
        return None, "Initialism cannot be empty."
    if not _INITIALISM_RE.match(candidate):
        return None, "Initialism must be 1–6 letters or digits (A–Z, 0–9)."
    return candidate, None


def validate_db_filename(raw: str) -> tuple[str | None, str | None]:
    """Returns (normalized_stem, None) on success or (None, error) on failure.
    Accepts the stem either with or without a trailing `.db`."""
    candidate = raw.strip().lower()
    if candidate.endswith(".db"):
        candidate = candidate[:-3]
    if not candidate:
        return None, "Filename cannot be empty."
    if not _DB_FILENAME_RE.match(candidate):
        return None, "Filename must use lowercase letters, digits, and underscores only."
    return candidate, None


def validate_scenario_name(raw: str) -> tuple[str | None, str | None]:
    candidate = raw.strip()
    if not candidate:
        return None, "Scenario name cannot be empty."
    if len(candidate) > 80:
        return None, "Scenario name must be 80 characters or fewer."
    return candidate, None
