#!/usr/bin/env python3
"""
culture_registry.py
Scenario-agnostic canonical culture trait list and pairwise synergy table.

Loads from (and bootstraps) core/core.db. Provides:
  - The fixed list of all culture:... tags
  - synergy(tag_a, tag_b) -> float in [-1.0, 1.0]
  - is_canonical(tag) -> bool
"""

from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_CORE_DB = _PROJECT_ROOT / "core" / "core.db"


# ── Canonical culture trait list (order is display order) ────────────
CULTURE_TAGS: list[str] = [
    # Religious Practices
    "culture:ancestor_worship", "culture:animism",
    "culture:luminary_worship", "culture:demiurge_worship",
    "culture:nontheism", "culture:maltheism", "culture:void_worship",
    # Technological
    "culture:science", "culture:luddism",
    "culture:magic", "culture:superstition",
    "culture:industrialism", "culture:conservationism",
    # Rights and Internal Structure
    "culture:egalitarianism", "culture:hierarchy",
    "culture:cooperation", "culture:competition",
    # Societal Practices
    "culture:monogamy", "culture:polygamy", "culture:lab_breeding",
    "culture:slavery",
    "culture:sedentism", "culture:nomadism",
    "culture:agriculture", "culture:foraging",
    # External Relations
    "culture:conquest", "culture:isolationism",
    "culture:diplomacy", "culture:imperialism",
    "culture:xenophilia", "culture:xenophobia",
    "culture:commerce", "culture:protectionism",
    # Values & Virtues
    "culture:honesty", "culture:adaptability",
    "culture:moderation", "culture:indulgence",
    "culture:charity", "culture:prosperity",
    "culture:ambition", "culture:humility",
    "culture:wit", "culture:sincerity",
    "culture:patience", "culture:tenacity",
    "culture:idealism", "culture:pragmatism",
    "culture:erudition", "culture:folk_wisdom",
]

# ── Pairwise synergy data ─────────────────────────────────────────────
# Each tuple: (tag_a, tag_b, synergy)
# Stored once per pair; symmetry applied at query time.
# Unlisted pairs default to 0.0.
_SYNERGY_DATA: list[tuple[str, str, float]] = [
    # Positives — reinforcing combinations
    ("culture:egalitarianism",   "culture:cooperation",       0.80),
    ("culture:sedentism",        "culture:agriculture",       0.80),
    ("culture:nomadism",         "culture:foraging",          0.75),
    ("culture:conquest",         "culture:imperialism",       0.70),
    ("culture:isolationism",     "culture:protectionism",     0.70),
    ("culture:diplomacy",        "culture:xenophilia",        0.65),
    ("culture:sedentism",        "culture:industrialism",     0.65),
    ("culture:diplomacy",        "culture:commerce",          0.60),
    ("culture:xenophobia",       "culture:isolationism",      0.60),
    ("culture:science",          "culture:industrialism",     0.60),
    ("culture:luminary_worship", "culture:demiurge_worship",  0.55),
    ("culture:egalitarianism",   "culture:diplomacy",         0.55),
    ("culture:cooperation",      "culture:diplomacy",         0.55),
    ("culture:hierarchy",        "culture:slavery",           0.55),
    ("culture:void_worship",     "culture:maltheism",         0.50),
    ("culture:ancestor_worship", "culture:animism",           0.50),
    ("culture:xenophilia",       "culture:commerce",          0.50),
    ("culture:honesty",          "culture:cooperation",       0.50),
    ("culture:industrialism",    "culture:commerce",          0.50),
    ("culture:hierarchy",        "culture:sedentism",         0.50),
    ("culture:luminary_worship", "culture:ancestor_worship",  0.45),
    ("culture:egalitarianism",   "culture:xenophilia",        0.45),
    ("culture:hierarchy",        "culture:conquest",          0.40),
    ("culture:nomadism",         "culture:conquest",          0.40),
    ("culture:nomadism",         "culture:animism",           0.40),
    ("culture:hierarchy",        "culture:commerce",          0.40),
    ("culture:honesty",          "culture:diplomacy",         0.40),
    ("culture:nontheism",        "culture:science",           0.40),
    ("culture:competition",      "culture:conquest",          0.40),
    ("culture:competition",      "culture:commerce",          0.40),
    ("culture:xenophobia",       "culture:protectionism",     0.40),
    # Negatives — conflicting combinations
    ("culture:luminary_worship", "culture:maltheism",         -0.90),
    ("culture:demiurge_worship", "culture:maltheism",         -0.90),
    ("culture:egalitarianism",   "culture:hierarchy",         -0.90),
    ("culture:egalitarianism",   "culture:slavery",           -0.90),
    ("culture:xenophilia",       "culture:xenophobia",        -0.90),
    ("culture:science",          "culture:luddism",           -0.90),
    ("culture:industrialism",    "culture:conservationism",   -0.80),
    ("culture:sedentism",        "culture:nomadism",          -0.80),
    ("culture:commerce",         "culture:protectionism",     -0.80),
    ("culture:luminary_worship", "culture:nontheism",         -0.80),
    ("culture:demiurge_worship", "culture:nontheism",         -0.80),
    ("culture:cooperation",      "culture:competition",       -0.75),
    ("culture:monogamy",         "culture:polygamy",          -0.70),
    ("culture:imperialism",      "culture:isolationism",      -0.70),
    ("culture:agriculture",      "culture:foraging",          -0.60),
    ("culture:conquest",         "culture:isolationism",      -0.60),
    ("culture:science",          "culture:superstition",      -0.60),
    ("culture:science",          "culture:magic",             -0.50),
    ("culture:monogamy",         "culture:lab_breeding",      -0.50),
    ("culture:protectionism",    "culture:xenophilia",        -0.50),
    ("culture:diplomacy",        "culture:imperialism",       -0.45),
    ("culture:diplomacy",        "culture:conquest",          -0.40),
    ("culture:nontheism",        "culture:animism",           -0.35),
    ("culture:polygamy",         "culture:lab_breeding",      -0.30),
    # ── Values & Virtues — within-cluster ────────────────────────────────
    # Strong reinforcing pairs
    ("culture:patience",         "culture:tenacity",           0.70),
    ("culture:honesty",          "culture:sincerity",          0.70),
    ("culture:pragmatism",       "culture:adaptability",       0.70),
    ("culture:erudition",        "culture:idealism",           0.55),
    ("culture:charity",          "culture:humility",           0.60),
    ("culture:wit",              "culture:erudition",          0.50),
    ("culture:ambition",         "culture:tenacity",           0.60),
    ("culture:prosperity",       "culture:ambition",           0.55),
    ("culture:folk_wisdom",      "culture:patience",           0.50),
    ("culture:folk_wisdom",      "culture:sincerity",          0.45),
    ("culture:idealism",         "culture:charity",            0.45),
    ("culture:adaptability",     "culture:wit",                0.40),
    # Weak or neutral reinforcements
    ("culture:pragmatism",       "culture:tenacity",           0.35),
    ("culture:erudition",        "culture:sincerity",          0.35),
    ("culture:prosperity",       "culture:tenacity",           0.30),
    ("culture:humility",         "culture:sincerity",          0.45),
    # Conflicts within V&V
    ("culture:moderation",       "culture:indulgence",        -0.85),
    ("culture:ambition",         "culture:humility",          -0.70),
    ("culture:pragmatism",       "culture:idealism",          -0.65),
    ("culture:erudition",        "culture:folk_wisdom",       -0.50),
    ("culture:prosperity",       "culture:charity",           -0.50),
    ("culture:wit",              "culture:sincerity",         -0.35),
    ("culture:patience",         "culture:ambition",          -0.35),
    # ── Values & Virtues — cross-cluster (Religious) ──────────────────────
    ("culture:idealism",         "culture:luminary_worship",   0.45),
    ("culture:idealism",         "culture:demiurge_worship",   0.40),
    ("culture:humility",         "culture:luminary_worship",   0.40),
    ("culture:humility",         "culture:ancestor_worship",   0.40),
    ("culture:humility",         "culture:animism",            0.35),
    ("culture:sincerity",        "culture:ancestor_worship",   0.35),
    ("culture:folk_wisdom",      "culture:ancestor_worship",   0.60),
    ("culture:folk_wisdom",      "culture:animism",            0.55),
    ("culture:folk_wisdom",      "culture:nontheism",         -0.35),
    ("culture:erudition",        "culture:nontheism",          0.40),
    ("culture:idealism",         "culture:maltheism",         -0.50),
    ("culture:pragmatism",       "culture:maltheism",          0.30),
    ("culture:charity",          "culture:void_worship",      -0.45),
    ("culture:indulgence",       "culture:void_worship",       0.30),
    # ── Values & Virtues — cross-cluster (Technological) ─────────────────
    ("culture:erudition",        "culture:science",            0.65),
    ("culture:erudition",        "culture:magic",              0.45),
    ("culture:erudition",        "culture:luddism",           -0.55),
    ("culture:folk_wisdom",      "culture:luddism",            0.40),
    ("culture:folk_wisdom",      "culture:superstition",       0.45),
    ("culture:folk_wisdom",      "culture:science",           -0.40),
    ("culture:pragmatism",       "culture:industrialism",      0.45),
    ("culture:pragmatism",       "culture:science",            0.40),
    ("culture:idealism",         "culture:conservationism",    0.45),
    ("culture:adaptability",     "culture:science",            0.35),
    ("culture:adaptability",     "culture:industrialism",      0.35),
    ("culture:moderation",       "culture:conservationism",    0.50),
    ("culture:indulgence",       "culture:industrialism",      0.30),
    # ── Values & Virtues — cross-cluster (Societal) ───────────────────────
    ("culture:idealism",         "culture:egalitarianism",     0.55),
    ("culture:idealism",         "culture:slavery",           -0.70),
    ("culture:charity",          "culture:egalitarianism",     0.50),
    ("culture:charity",          "culture:cooperation",        0.55),
    ("culture:charity",          "culture:slavery",           -0.65),
    ("culture:humility",         "culture:cooperation",        0.45),
    ("culture:ambition",         "culture:competition",        0.55),
    ("culture:ambition",         "culture:hierarchy",          0.40),
    ("culture:prosperity",       "culture:commerce",           0.50),
    ("culture:prosperity",       "culture:competition",        0.45),
    ("culture:moderation",       "culture:sedentism",          0.35),
    ("culture:indulgence",       "culture:polygamy",           0.35),
    ("culture:pragmatism",       "culture:cooperation",        0.35),
    ("culture:tenacity",         "culture:sedentism",          0.30),
    ("culture:adaptability",     "culture:nomadism",           0.45),
    # ── Values & Virtues — cross-cluster (External Relations) ─────────────
    ("culture:honesty",          "culture:xenophilia",         0.40),
    ("culture:wit",              "culture:diplomacy",          0.45),
    ("culture:wit",              "culture:commerce",           0.40),
    ("culture:ambition",         "culture:imperialism",        0.45),
    ("culture:ambition",         "culture:conquest",           0.40),
    ("culture:idealism",         "culture:diplomacy",          0.45),
    ("culture:idealism",         "culture:conquest",          -0.45),
    ("culture:pragmatism",       "culture:commerce",           0.40),
    ("culture:adaptability",     "culture:xenophilia",         0.40),
    ("culture:adaptability",     "culture:diplomacy",          0.35),
    ("culture:prosperity",       "culture:imperialism",        0.35),
    ("culture:moderation",       "culture:isolationism",       0.30),
]


class CultureRegistry:
    """
    Canonical, scenario-agnostic source of truth for culture:... tags
    and their pairwise synergy values.

    On first instantiation, bootstraps core/core.db tables if absent.
    """

    def __init__(self, db_path: Path = DEFAULT_CORE_DB) -> None:
        self._db_path = db_path
        self._synergy: dict[tuple[str, str], float] = {}
        self._all_tags: list[str] = []
        self._tag_set: set[str] = set()
        self._ensure_db()
        self._load()

    # ── Public interface ───────────────────────────────────────────────

    @property
    def all_tags(self) -> list[str]:
        return list(self._all_tags)

    def is_canonical(self, tag: str) -> bool:
        return tag in self._tag_set

    def synergy(self, tag_a: str, tag_b: str) -> float:
        """
        Pairwise synergy between two culture tags.
        Returns 1.0 for identical tags, 0.0 for unknown/unlisted pairs.
        Range: [-1.0, 1.0].
        """
        if tag_a == tag_b:
            return 1.0
        key = (min(tag_a, tag_b), max(tag_a, tag_b))
        return self._synergy.get(key, 0.0)

    # ── Internal ───────────────────────────────────────────────────────

    def _ensure_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS culture_registry (
                    tag          TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    sort_order   INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS culture_synergy (
                    tag_a   TEXT NOT NULL,
                    tag_b   TEXT NOT NULL,
                    synergy REAL NOT NULL,
                    PRIMARY KEY (tag_a, tag_b)
                );
            """)

            for i, tag in enumerate(CULTURE_TAGS):
                display = tag.split(":", 1)[1].replace("_", " ").title()
                conn.execute(
                    "INSERT OR IGNORE INTO culture_registry (tag, display_name, sort_order) VALUES (?,?,?)",
                    (tag, display, i),
                )

            for tag_a, tag_b, syn in _SYNERGY_DATA:
                a, b = min(tag_a, tag_b), max(tag_a, tag_b)
                conn.execute(
                    "INSERT OR IGNORE INTO culture_synergy (tag_a, tag_b, synergy) VALUES (?,?,?)",
                    (a, b, syn),
                )

            conn.commit()
        finally:
            conn.close()

    def _load(self) -> None:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            self._all_tags = [
                row["tag"]
                for row in conn.execute(
                    "SELECT tag FROM culture_registry ORDER BY sort_order"
                )
            ]
            self._tag_set = set(self._all_tags)

            for row in conn.execute("SELECT tag_a, tag_b, synergy FROM culture_synergy"):
                a, b = min(row["tag_a"], row["tag_b"]), max(row["tag_a"], row["tag_b"])
                self._synergy[(a, b)] = row["synergy"]
        finally:
            conn.close()


# ── Module-level singleton (lazy) ─────────────────────────────────────
_registry: Optional[CultureRegistry] = None


def get_registry(db_path: Path = DEFAULT_CORE_DB) -> CultureRegistry:
    """Return the module-level CultureRegistry singleton."""
    global _registry
    if _registry is None:
        _registry = CultureRegistry(db_path)
    return _registry
