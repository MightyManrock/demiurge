#!/usr/bin/env python3
"""
domain_registry.py
Scenario-agnostic canonical domain list and pairwise similarity table.

Loads from (and bootstraps) core/core.db. Provides:
  - The fixed list of all domain:... tags
  - similarity(tag_a, tag_b) -> float in [-1.0, 1.0]
  - partner(tag) -> str  (the paired partner)
  - accessible_from(seed_tags, threshold) -> list of reachable tags
  - compute_personality(domains) -> LuminaryPersonality
  - luminary_approval(tag, lum_tags, fellow_lum_tags, personality) -> float
"""

from __future__ import annotations
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_CORE_DB = _PROJECT_ROOT / "core" / "core.db"

# ── Threshold constants ────────────────────────────────────────────────
LUMINARY_ACCESS_THRESHOLD = 0.10
# Tags at or above this similarity to any Luminary domain are accessible.

# ── Canonical domain data ──────────────────────────────────────────────
# Each entry: (tag, dynamic_score, partner_tag, icon,
#              authoritative_score, mercurial_score, wrathful_score)
# dynamic_score: −1.0 = pure results/stative focus → +1.0 = pure methods/dynamic focus
# authoritative_score: −1.0 = permissive → +1.0 = authoritative
# mercurial_score: −1.0 = stable → +1.0 = mercurial/capricious
# wrathful_score: −1.0 = sympathetic → +1.0 = wrathful/harsh
_DOMAIN_DATA: list[tuple[str, float, str, str, float, float, float]] = [
    # Structure / Stillness
    ("domain:truth",     -0.9, "domain:order",     "◈",  0.3, -0.5, -0.2),
    ("domain:order",      0.5, "domain:truth",     "⬡",  0.8, -0.7,  0.1),
    ("domain:silence",   -0.7, "domain:secrecy",   "◯", -0.6, -0.4, -0.3),
    # Upheaval
    ("domain:change",    -0.4, "domain:conflict",  "✷", -0.4,  0.8,  0.1),
    ("domain:conflict",   0.9, "domain:change",    "✖",  0.5,  0.4,  0.7),
    # Elemental
    ("domain:fire",       0.7, "domain:light",     "🜂",  0.3,  0.7,  0.5),
    ("domain:water",      0.6, "domain:growth",    "≋", -0.5,  0.3, -0.6),
    ("domain:void",      -0.8, "domain:decay",     "∅", -0.7, -0.3, -0.4),
    # Life Cycle
    ("domain:growth",    -0.6, "domain:water",     "✿", -0.2,  0.1, -0.4),
    ("domain:decay",      0.5, "domain:void",      "☋",  0.1,  0.5,  0.3),
    # Mind / Spirit
    ("domain:memory",    -0.8, "domain:mastery",   "◉",  0.2, -0.6, -0.1),
    ("domain:sacrifice",  0.3, "domain:community", "⚱",  0.6,  0.2,  0.6),
    # Illumination / Craft
    ("domain:light",     -0.7, "domain:fire",      "☼",  0.4, -0.3, -0.3),
    ("domain:mastery",    0.4, "domain:memory",    "⚙",  0.5, -0.2,  0.2),
    # Social
    ("domain:secrecy",    0.4, "domain:silence",   "⛉", -0.3,  0.3, -0.1),
    ("domain:community", -0.5, "domain:sacrifice", "♾", -0.1, -0.3, -0.7),
]

# Derived flat list — preserves call-site compatibility.
DOMAIN_TAGS: list[str] = [d[0] for d in _DOMAIN_DATA]

# ── Pairwise similarity data ───────────────────────────────────────────
# Each tuple: (tag_a, tag_b, similarity)
# Stored once per pair; symmetry applied at query time.
# Unlisted pairs default to 0.0.
_SIMILARITY_DATA: list[tuple[str, str, float]] = [
    # Positives
    ("domain:light",     "domain:truth",      0.50),
    ("domain:fire",      "domain:light",      0.35),
    ("domain:secrecy",   "domain:silence",    0.35),
    ("domain:order",     "domain:silence",    0.35),
    ("domain:order",     "domain:truth",      0.30),
    ("domain:conflict",  "domain:fire",       0.30),
    ("domain:water",     "domain:growth",     0.30),
    ("domain:void",      "domain:silence",    0.25),
    ("domain:change",    "domain:growth",     0.25),
    ("domain:change",    "domain:fire",       0.25),
    ("domain:decay",     "domain:sacrifice",  0.25),
    ("domain:memory",    "domain:truth",      0.25),
    ("domain:mastery",   "domain:truth",      0.20),
    ("domain:order",     "domain:mastery",    0.20),
    ("domain:conflict",  "domain:change",     0.20),
    ("domain:change",    "domain:decay",      0.20),
    ("domain:void",      "domain:decay",      0.20),
    ("domain:growth",    "domain:community",  0.20),
    ("domain:memory",    "domain:sacrifice",  0.20),
    ("domain:sacrifice", "domain:community",  0.20),
    ("domain:fire",      "domain:sacrifice",  0.20),
    ("domain:fire",      "domain:mastery",    0.10),
    ("domain:change",    "domain:water",      0.10),
    ("domain:void",      "domain:secrecy",    0.10),
    ("domain:decay",     "domain:memory",     0.10),
    ("domain:memory",    "domain:community",  0.10),
    ("domain:order",     "domain:community",  0.10),
    ("domain:conflict",  "domain:mastery",    0.10),
    ("domain:memory",    "domain:silence",    0.05),
    ("domain:sacrifice", "domain:light",      0.05),
    # Negatives
    ("domain:light",     "domain:secrecy",    -0.50),
    ("domain:truth",     "domain:secrecy",    -0.45),
    ("domain:conflict",  "domain:silence",    -0.35),
    ("domain:growth",    "domain:void",       -0.35),
    ("domain:light",     "domain:void",       -0.30),
    ("domain:order",     "domain:change",     -0.25),
    ("domain:growth",    "domain:decay",      -0.25),
    ("domain:void",      "domain:community",  -0.25),
    ("domain:fire",      "domain:void",       -0.20),
    ("domain:order",     "domain:void",       -0.30),
    ("domain:order",     "domain:decay",      -0.25),
    ("domain:order",     "domain:secrecy",    -0.20),
    ("domain:secrecy",   "domain:community",  -0.10),
    ("domain:order",     "domain:conflict",   -0.05),
    ("domain:conflict",  "domain:community",  -0.05),
    ("domain:decay",     "domain:community",  -0.05),
    ("domain:memory",    "domain:change",     -0.05),
]

# Amplifies raw similarity when a Luminary evaluates a domain outside their own,
# keeping approval/opposition meaningful against moderate base values.
LUMINARY_APPROVAL_SCALE = 1.5


# ── Luminary personality ───────────────────────────────────────────────

@dataclass
class LuminaryPersonality:
    """
    Continuous personality derived from a Luminary's domain affinities.
    All axes are in [-1.0, +1.0].

    dynamic:       −1.0 = results/stative focus → +1.0 = methods/dynamic focus
    reactivity:    −1.0 = permissive            → +1.0 = authoritative
    capriciousness:−1.0 = stable                → +1.0 = mercurial
    harshness:     −1.0 = sympathetic           → +1.0 = wrathful
    """
    dynamic: float = 0.0
    reactivity: float = 0.0
    capriciousness: float = 0.0
    harshness: float = 0.0


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
        self._dynamic_score: dict[str, float] = {}
        self._authoritative_score: dict[str, float] = {}
        self._mercurial_score: dict[str, float] = {}
        self._wrathful_score: dict[str, float] = {}
        self._partner: dict[str, str] = {}
        self._icon: dict[str, str] = {}
        self._ensure_db()
        self._load()

    # ── Public interface ───────────────────────────────────────────────

    @property
    def all_tags(self) -> list[str]:
        return list(self._all_tags)

    def is_canonical(self, tag: str) -> bool:
        return tag in self._tag_set

    def partner(self, tag: str) -> Optional[str]:
        """The paired counterpart of this domain, or None if unknown."""
        return self._partner.get(tag)

    def icon(self, tag: str) -> str:
        """Unicode icon for this domain, or empty string if unknown."""
        return self._icon.get(tag, "")

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

    def compute_personality(self, domains: dict[str, float]) -> LuminaryPersonality:
        """
        Compute a LuminaryPersonality from affinity-weighted domain axis averages.
        domains: {domain_tag: affinity} — same format as Luminary.domains.
        """
        if not domains:
            return LuminaryPersonality()

        total_affinity = sum(domains.values())
        if total_affinity <= 0.0:
            return LuminaryPersonality()

        dynamic = 0.0
        reactivity = 0.0
        capriciousness = 0.0
        harshness = 0.0

        for tag, affinity in domains.items():
            w = affinity / total_affinity
            dynamic       += self._dynamic_score.get(tag, 0.0)       * w
            reactivity    += self._authoritative_score.get(tag, 0.0) * w
            capriciousness += self._mercurial_score.get(tag, 0.0)    * w
            harshness     += self._wrathful_score.get(tag, 0.0)      * w

        return LuminaryPersonality(
            dynamic=max(-1.0, min(1.0, dynamic)),
            reactivity=max(-1.0, min(1.0, reactivity)),
            capriciousness=max(-1.0, min(1.0, capriciousness)),
            harshness=max(-1.0, min(1.0, harshness)),
        )

    def realpolitik_factor(self, personality: LuminaryPersonality) -> float:
        """
        How much a Luminary dampens negative reactions to a domain held by
        a fellow Luminary. Maps harshness [-1, +1] to [0.10, 0.80].
        Lower = more forgiving (swallows distaste).
        """
        return 0.10 + (personality.harshness + 1.0) / 2.0 * 0.70

    def luminary_approval(
        self,
        tag: str,
        lum_tags: list[str],
        own_tag_set: Optional[set[str]] = None,
        fellow_lum_tags: Optional[set[str]] = None,
        personality: Optional[LuminaryPersonality] = None,
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
        p = personality or LuminaryPersonality()
        realpolitik = self.realpolitik_factor(p)

        total = 0.0
        for lum_tag in lum_tags:
            raw = self.similarity(lum_tag, tag) * LUMINARY_APPROVAL_SCALE
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
        personality: Optional[LuminaryPersonality] = None,
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
        p = personality or LuminaryPersonality()
        influence = 0.0
        count = 0

        for tag, strength in profile_scores.items():
            if tag in own or strength < 0.05:
                continue
            approval = self.luminary_approval(
                tag, lum_tags,
                own_tag_set=own,
                fellow_lum_tags=fellow_lum_tags,
                personality=p,
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
            try:
                already_seeded = conn.execute(
                    "SELECT COUNT(*) FROM domain_registry"
                ).fetchone()[0] > 0
            except sqlite3.OperationalError:
                already_seeded = False

            if already_seeded:
                return

            conn.executescript("""
                CREATE TABLE IF NOT EXISTS domain_registry (
                    tag                  TEXT PRIMARY KEY,
                    display_name         TEXT NOT NULL,
                    sort_order           INTEGER NOT NULL DEFAULT 0,
                    dynamic_score        REAL NOT NULL DEFAULT 0.0,
                    partner_tag          TEXT NOT NULL DEFAULT '',
                    icon                 TEXT NOT NULL DEFAULT '',
                    authoritative_score  REAL NOT NULL DEFAULT 0.0,
                    mercurial_score      REAL NOT NULL DEFAULT 0.0,
                    wrathful_score       REAL NOT NULL DEFAULT 0.0
                );
                CREATE TABLE IF NOT EXISTS domain_similarity (
                    tag_a      TEXT NOT NULL,
                    tag_b      TEXT NOT NULL,
                    similarity REAL NOT NULL,
                    PRIMARY KEY (tag_a, tag_b)
                );
            """)

            # Migrate existing DBs that predate these columns.
            for col_def in (
                "ADD COLUMN dynamic_score       REAL NOT NULL DEFAULT 0.0",
                "ADD COLUMN partner_tag         TEXT NOT NULL DEFAULT ''",
                "ADD COLUMN icon                TEXT NOT NULL DEFAULT ''",
                "ADD COLUMN authoritative_score REAL NOT NULL DEFAULT 0.0",
                "ADD COLUMN mercurial_score     REAL NOT NULL DEFAULT 0.0",
                "ADD COLUMN wrathful_score      REAL NOT NULL DEFAULT 0.0",
            ):
                try:
                    conn.execute(f"ALTER TABLE domain_registry {col_def}")
                except sqlite3.OperationalError:
                    pass  # column already present

            # Remove retired domains.
            conn.execute("DELETE FROM domain_registry WHERE tag IN ('domain:chaos','domain:discovery')")
            conn.execute(
                "DELETE FROM domain_similarity "
                "WHERE tag_a IN ('domain:chaos','domain:discovery') "
                "   OR tag_b IN ('domain:chaos','domain:discovery')"
            )

            # Upsert all canonical domains.
            for i, (tag, dynamic, partner, icon, auth, merc, wrath) in enumerate(_DOMAIN_DATA):
                display = tag.split(":", 1)[1].replace("_", " ").title()
                conn.execute(
                    "INSERT OR REPLACE INTO domain_registry "
                    "(tag, display_name, sort_order, dynamic_score, partner_tag, icon, "
                    " authoritative_score, mercurial_score, wrathful_score) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (tag, display, i, dynamic, partner, icon, auth, merc, wrath),
                )

            for tag_a, tag_b, sim in _SIMILARITY_DATA:
                a, b = min(tag_a, tag_b), max(tag_a, tag_b)
                conn.execute(
                    "INSERT OR REPLACE INTO domain_similarity (tag_a, tag_b, similarity) VALUES (?,?,?)",
                    (a, b, sim),
                )

            conn.commit()
        finally:
            conn.close()

    def _load(self) -> None:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            self._all_tags = []
            for row in conn.execute(
                "SELECT tag, dynamic_score, partner_tag, icon, "
                "authoritative_score, mercurial_score, wrathful_score "
                "FROM domain_registry ORDER BY sort_order"
            ):
                self._all_tags.append(row["tag"])
                self._dynamic_score[row["tag"]]       = row["dynamic_score"]
                self._authoritative_score[row["tag"]] = row["authoritative_score"]
                self._mercurial_score[row["tag"]]     = row["mercurial_score"]
                self._wrathful_score[row["tag"]]      = row["wrathful_score"]
                self._partner[row["tag"]]             = row["partner_tag"]
                self._icon[row["tag"]]                = row["icon"]
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


def reinstate(db_path: Path = DEFAULT_CORE_DB) -> DomainRegistry:
    """Drop and recreate domain tables from Python source data, then reload the singleton."""
    global _registry
    _registry = None
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript("""
            DROP TABLE IF EXISTS domain_similarity;
            DROP TABLE IF EXISTS domain_registry;
        """)
        conn.commit()
    finally:
        conn.close()
    return get_registry(db_path)
