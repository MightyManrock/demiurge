#!/usr/bin/env python3
"""
domain_registry.py
Scenario-agnostic canonical domain list and pairwise similarity table.

Loads from (and bootstraps) core/core.db. Provides:
  - The fixed list of all domain:... tags
  - similarity(tag_a, tag_b) -> float in [-1.0, 1.0]
  - accessible_from(seed_tags, threshold) -> list of reachable tags
  - luminary_approval(tag, lum_tags, fellow_lum_tags, temperament) -> float
"""

from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).parent
DEFAULT_CORE_DB = _PROJECT_ROOT / "core" / "core.db"

# ── Threshold constants ────────────────────────────────────────────────
LUMINARY_ACCESS_THRESHOLD = 0.40
# Tags at or above this similarity to any Luminary domain are accessible.

DEMIURGE_UNLOCK_THRESHOLD = 0.50
# Narrower threshold for access from Demiurge-unlocked (non-Luminary) domains.

# ── Canonical domain list (order is display order) ────────────────────
DOMAIN_TAGS: list[str] = [
    # Structure / Stillness
    "domain:order", "domain:law", "domain:silence", "domain:truth",
    # Upheaval / Conflict
    "domain:chaos", "domain:conflict", "domain:war", "domain:change",
    # Elemental
    "domain:fire", "domain:water", "domain:void",
    # Life Cycle
    "domain:life", "domain:growth", "domain:death", "domain:decay",
    # Mind / Spirit
    "domain:thought", "domain:memory", "domain:dreams",
    # Social / Ritual
    "domain:trade", "domain:sacrifice",
]

# ── Pairwise similarity data ───────────────────────────────────────────
# Each tuple: (tag_a, tag_b, similarity)
# Stored once per pair; symmetry applied at query time.
# Unlisted pairs default to 0.0.
_SIMILARITY_DATA: list[tuple[str, str, float]] = [
    # Positives
    ("domain:law",      "domain:order",     0.80),
    ("domain:thought",  "domain:truth",     0.75),
    ("domain:conflict", "domain:war",       0.75),
    ("domain:growth",   "domain:life",      0.70),
    ("domain:order",    "domain:silence",   0.60),
    ("domain:law",      "domain:truth",     0.60),
    ("domain:change",   "domain:chaos",     0.60),
    ("domain:decay",    "domain:death",     0.60),
    ("domain:order",    "domain:truth",     0.55),
    ("domain:change",   "domain:growth",    0.50),
    ("domain:death",    "domain:memory",    0.50),
    ("domain:death",    "domain:sacrifice", 0.50),
    ("domain:change",   "domain:fire",      0.50),
    ("domain:conflict", "domain:fire",      0.50),
    ("domain:death",    "domain:void",      0.50),
    ("domain:life",     "domain:water",     0.50),
    ("domain:silence",  "domain:void",      0.45),
    ("domain:change",   "domain:water",     0.40),
    ("domain:dreams",   "domain:water",     0.40),
    ("domain:law",      "domain:thought",   0.40),
    ("domain:memory",   "domain:sacrifice", 0.40),
    ("domain:growth",   "domain:trade",     0.40),
    ("domain:fire",     "domain:sacrifice", 0.40),
    ("domain:chaos",    "domain:dreams",    0.40),
    ("domain:memory",   "domain:silence",   0.30),
    ("domain:sacrifice","domain:war",       0.35),
    # Negatives
    ("domain:chaos",    "domain:order",     -0.90),
    ("domain:chaos",    "domain:law",       -0.80),
    ("domain:conflict", "domain:silence",   -0.70),
    ("domain:silence",  "domain:war",       -0.70),
    ("domain:life",     "domain:void",      -0.70),
    ("domain:change",   "domain:order",     -0.60),
    ("domain:chaos",    "domain:silence",   -0.60),
    ("domain:growth",   "domain:void",      -0.60),
    ("domain:decay",    "domain:life",      -0.50),
    ("domain:chaos",    "domain:truth",     -0.50),
    ("domain:change",   "domain:law",       -0.40),
    ("domain:conflict", "domain:order",     -0.40),
    ("domain:death",    "domain:life",      -0.40),
    ("domain:trade",    "domain:war",       -0.40),
]

# ── Realpolitik dampening: how much negative similarity is reduced
# when the opposing domain belongs to a fellow Luminary.
# Lower = more forgiving (the Luminary swallows their distaste).
REALPOLITIK_FACTOR: dict[str, float] = {
    "indifferent": 0.10,
    "patient":     0.15,
    "orderly":     0.40,
    "capricious":  0.40,
    "wrathful":    0.70,
    "zealous":     0.80,
}


class DomainRegistry:
    """
    The canonical, scenario-agnostic source of truth for domain:... tags
    and their pairwise similarity values.

    On first instantiation, bootstraps core/core.db from hardcoded data
    if the file does not exist or the tables are empty.
    """

    def __init__(self, db_path: Path = DEFAULT_CORE_DB) -> None:
        self._db_path = db_path
        self._similarity: dict[tuple[str, str], float] = {}
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

    def similarity(self, tag_a: str, tag_b: str) -> float:
        """
        Pairwise similarity between two domain tags.
        Returns 1.0 for identical tags, 0.0 for unknown/unlisted pairs.
        Range: [-1.0, 1.0].
        """
        if tag_a == tag_b:
            return 1.0
        key = (min(tag_a, tag_b), max(tag_a, tag_b))
        return self._similarity.get(key, 0.0)

    def accessible_from(
        self,
        seed_tags: list[str],
        threshold: float = LUMINARY_ACCESS_THRESHOLD,
    ) -> list[str]:
        """
        All domain tags reachable from seed_tags at or above threshold similarity.
        Does not include the seed tags themselves.
        Returns tags in canonical display order.
        """
        seed_set = set(seed_tags)
        return [
            t for t in self._all_tags
            if t not in seed_set
            and any(self.similarity(s, t) >= threshold for s in seed_tags)
        ]

    def demiurge_accessible(
        self,
        luminary_domain_tags: list[str],
        unlocked_tags: list[str],
    ) -> list[str]:
        """
        All domain tags the Demiurge may currently promote.
        Includes Luminary-origin tags + tags reachable from them at LUMINARY_ACCESS_THRESHOLD,
        plus tags reachable from unlocked_tags at the narrower DEMIURGE_UNLOCK_THRESHOLD.
        Does NOT include tags the Demiurge already has access to via Luminary grant.
        Returns tags in canonical display order, deduplicated.
        """
        lum_base = set(luminary_domain_tags)
        lum_adjacent = set(self.accessible_from(luminary_domain_tags, LUMINARY_ACCESS_THRESHOLD))
        base_accessible = lum_base | lum_adjacent

        unlock_adjacent: set[str] = set()
        if unlocked_tags:
            unlock_adjacent = set(
                self.accessible_from(unlocked_tags, DEMIURGE_UNLOCK_THRESHOLD)
            ) - base_accessible

        all_accessible = base_accessible | set(unlocked_tags) | unlock_adjacent
        return [t for t in self._all_tags if t in all_accessible]

    def luminary_approval(
        self,
        tag: str,
        lum_tags: list[str],
        own_tag_set: Optional[set[str]] = None,
        fellow_lum_tags: Optional[set[str]] = None,
        temperament: str = "orderly",
    ) -> float:
        """
        How much this Luminary approves of the domain 'tag' being promoted.
        Returns a score in [-1.0, 1.0]:
          - Positive: the tag aligns with their domains
          - Negative: the tag opposes their domains
          - 0.0: the tag is irrelevant to them

        Applies:
          - Internal contradiction bypass: if 'tag' is one of the Luminary's own
            domains, ignores negative similarity from their other domains to it.
          - Realpolitik: if 'tag' is held by a fellow Luminary, dampens negative score.
        """
        if not lum_tags:
            return 0.0

        own = own_tag_set if own_tag_set is not None else set(lum_tags)
        fellow = fellow_lum_tags or set()
        realpolitik = REALPOLITIK_FACTOR.get(temperament, 0.40)

        total = 0.0
        for lum_tag in lum_tags:
            raw = self.similarity(lum_tag, tag)
            if raw < 0:
                if tag in own:
                    raw = 0.0
                elif tag in fellow:
                    raw *= realpolitik
            total += raw

        return max(-1.0, min(1.0, total / len(lum_tags)))

    def similarity_influence(
        self,
        lum_tags: list[str],
        fellow_lum_tags: set[str],
        profile_scores: dict[str, float],
        temperament: str = "orderly",
    ) -> float:
        """
        Aggregate similarity-weighted results influence from expressed domains
        that are NOT in the Luminary's own domain list.

        Returns a float in roughly [-0.5, 0.5] to add to the primary alignment score.
        The influence is secondary — weighted at 40% of the primary.
        """
        if not lum_tags:
            return 0.0

        own = set(lum_tags)
        influence = 0.0
        count = 0

        for tag, strength in profile_scores.items():
            if tag in own or strength < 0.05:
                continue
            approval = self.luminary_approval(
                tag, lum_tags,
                own_tag_set=own,
                fellow_lum_tags=fellow_lum_tags,
                temperament=temperament,
            )
            if abs(approval) > 0.01:
                influence += approval * strength
                count += 1

        if count == 0:
            return 0.0

        return (influence / count) * 0.4

    # ── Internal ───────────────────────────────────────────────────────

    def _ensure_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS domain_registry (
                    tag          TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    sort_order   INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS domain_similarity (
                    tag_a      TEXT NOT NULL,
                    tag_b      TEXT NOT NULL,
                    similarity REAL NOT NULL,
                    PRIMARY KEY (tag_a, tag_b)
                );
            """)

            # Seed domain_registry if empty
            count = conn.execute("SELECT COUNT(*) FROM domain_registry").fetchone()[0]
            if count == 0:
                for i, tag in enumerate(DOMAIN_TAGS):
                    display = tag.split(":", 1)[1].replace("_", " ").title()
                    conn.execute(
                        "INSERT INTO domain_registry (tag, display_name, sort_order) VALUES (?,?,?)",
                        (tag, display, i),
                    )

            # Seed domain_similarity if empty
            count = conn.execute("SELECT COUNT(*) FROM domain_similarity").fetchone()[0]
            if count == 0:
                for tag_a, tag_b, sim in _SIMILARITY_DATA:
                    a, b = min(tag_a, tag_b), max(tag_a, tag_b)
                    conn.execute(
                        "INSERT OR IGNORE INTO domain_similarity (tag_a, tag_b, similarity) VALUES (?,?,?)",
                        (a, b, sim),
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
                    "SELECT tag FROM domain_registry ORDER BY sort_order"
                )
            ]
            self._tag_set = set(self._all_tags)

            for row in conn.execute("SELECT tag_a, tag_b, similarity FROM domain_similarity"):
                a, b = min(row["tag_a"], row["tag_b"]), max(row["tag_a"], row["tag_b"])
                self._similarity[(a, b)] = row["similarity"]
        finally:
            conn.close()


# ── Module-level singleton (lazy) ─────────────────────────────────────
_registry: Optional[DomainRegistry] = None


def get_registry(db_path: Path = DEFAULT_CORE_DB) -> DomainRegistry:
    """Return the module-level DomainRegistry singleton."""
    global _registry
    if _registry is None:
        _registry = DomainRegistry(db_path)
    return _registry
