#!/usr/bin/env python3
"""
culture_registry.py
Scenario-agnostic canonical culture trait list and pairwise synergy table.

Loads from (and bootstraps) core/core.db. Provides:
  - Per-category tag lists (RELIGION_TAGS, TECHNO_TAGS, etc.)
  - ALL_CULTURE_TAGS: combined list in display order
  - CULTURE_CATEGORIES: dict mapping category label → tag list (for editor UI)
  - is_culture_tag(tag) -> bool
  - synergy(tag_a, tag_b) -> float in [-1.0, 1.0]
  - is_canonical(tag) -> bool
"""

from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_CORE_DB = _PROJECT_ROOT / "core" / "core.db"


# ── Per-category tag lists (order is display order) ──────────────────
RELIGION_TAGS: list[str] = [
    "religion:ancestor_worship", "religion:animism",
    "religion:luminary_worship", "religion:demiurge_worship",
    "religion:nontheism", "religion:maltheism", "religion:void_worship",
]
TECHNO_TAGS: list[str] = [
    "techno:science", "techno:luddism",
    "techno:magic", "techno:superstition",
    "techno:industrialism", "techno:conservationism",
]
STRUCTURE_TAGS: list[str] = [
    "structure:egalitarianism", "structure:hierarchy",
    "structure:cooperation", "structure:competition",
]
PRACTICE_TAGS: list[str] = [
    "practice:monogamy", "practice:polygamy", "practice:lab_breeding",
    "practice:slavery",
    "practice:sedentism", "practice:nomadism",
    "practice:agriculture", "practice:foraging",
    # Arts & performance
    "practice:music", "practice:dance", "practice:visual",
    "practice:theatre", "practice:lit", "practice:poetry",
    # Craft & food
    "practice:crafts", "practice:culinary",
    # Physical & ceremonial
    "practice:athletics", "practice:combat", "practice:ritual", "practice:revelry",
]
RELATIONS_TAGS: list[str] = [
    "relations:conquest", "relations:isolationism",
    "relations:diplomacy", "relations:imperialism",
    "relations:xenophilia", "relations:xenophobia",
    "relations:commerce", "relations:protectionism",
]
VALUES_TAGS: list[str] = [
    "values:honesty", "values:adaptability",
    "values:moderation", "values:indulgence",
    "values:charity", "values:prosperity",
    "values:ambition", "values:humility",
    "values:wit", "values:sincerity",
    "values:patience", "values:tenacity",
    "values:idealism", "values:pragmatism",
    "values:erudition", "values:folk_wisdom",
    # Canonical new values (replacing old aliases and adding new)
    "values:honor", "values:prowess",
    "values:hierarchy", "values:sedentism", "values:xenophilia",
    "values:meritocracy", "values:solidarity", "values:autonomy",
]

ALL_CULTURE_TAGS: list[str] = [
    *RELIGION_TAGS, *TECHNO_TAGS, *STRUCTURE_TAGS,
    *PRACTICE_TAGS, *RELATIONS_TAGS, *VALUES_TAGS,
]

# For editor UI: category label → tag list
CULTURE_CATEGORIES: dict[str, list[str]] = {
    "Religion":          RELIGION_TAGS,
    "Technology":        TECHNO_TAGS,
    "Structure":         STRUCTURE_TAGS,
    "Societal Practices": PRACTICE_TAGS,
    "Relations":         RELATIONS_TAGS,
    "Values & Virtues":  VALUES_TAGS,
}

_ALL_TAG_SET: set[str] = set(ALL_CULTURE_TAGS)

# Prefix → category tag list, for fast same-category lookup.
_PREFIX_TO_CATEGORY: dict[str, list[str]] = {
    "religion":  RELIGION_TAGS,
    "techno":    TECHNO_TAGS,
    "structure": STRUCTURE_TAGS,
    "practice":  PRACTICE_TAGS,
    "relations": RELATIONS_TAGS,
    "values":    VALUES_TAGS,
}


# ── Alias map: old tag → list of (canonical_tag, multiplier) ─────────
# Multiplier of -1.0 means the old tag maps to the *negative* of the new
# canonical (e.g. xenophobia → -1 × xenophilia).
CULTURE_TAG_ALIASES: dict[str, list[tuple[str, float]]] = {
    "values:honesty":           [("values:honor",      1.0)],
    "values:ambition":          [("values:prowess",    1.0)],
    "structure:hierarchy":      [("values:hierarchy",  1.0)],
    "structure:egalitarianism": [("values:hierarchy", -1.0)],
    "practice:sedentism":       [("values:sedentism",  1.0)],
    "practice:nomadism":        [("values:sedentism", -1.0)],
    "relations:xenophilia":     [("values:xenophilia",  1.0)],
    "relations:xenophobia":     [("values:xenophilia", -1.0)],
    "techno:science":           [("values:erudition",   1.0)],
    "techno:industrialism":     [
        ("values:tenacity",     0.7),
        ("values:adaptability", 0.7),
        ("values:moderation",  -0.3),
    ],
    "relations:diplomacy":      [
        ("values:solidarity",   0.5),
        ("values:honor",        0.5),
    ],
}


def expand_culture_tag(tag: str, delta: float) -> list[tuple[str, float]]:
    """Return (canonical_tag, adjusted_delta) pairs for a mutation.

    If `tag` is an alias, fans out to canonical targets with scaled deltas.
    Otherwise returns [(tag, delta)] unchanged.
    """
    if tag in CULTURE_TAG_ALIASES:
        return [(canonical, delta * mult) for canonical, mult in CULTURE_TAG_ALIASES[tag]]
    return [(tag, delta)]


def migrate_culture_tags(tags: dict[str, float]) -> dict[str, float]:
    """Convert a culture_tags dict from old keys to canonical new ones.

    Additive: if both old and new keys are present, values are summed and
    clamped to [-1.0, 1.0] for signed tags or [0.0, 1.0] for unsigned.
    Call this at load time to keep saves forward-compatible.
    """
    if not any(t in CULTURE_TAG_ALIASES for t in tags):
        return tags
    result: dict[str, float] = {}
    for tag, value in tags.items():
        for canonical, mult in CULTURE_TAG_ALIASES.get(tag, [(tag, 1.0)]):
            result[canonical] = result.get(canonical, 0.0) + value * mult
    _s_prefixes = ("values:", "practice:")
    for k, v in result.items():
        if k.startswith(_s_prefixes):
            result[k] = max(-1.0, min(1.0, v))
        else:
            result[k] = max(0.0, min(1.0, v))
    return result


def is_culture_tag(tag: str) -> bool:
    return tag in _ALL_TAG_SET


def peer_culture_tags(tag: str) -> list[str]:
    """All other canonical culture tags sharing `tag`'s category (its
    `prefix:` namespace), excluding `tag` itself. Empty list if `tag` is not
    a recognized culture tag. Used to substitute a tag for a random sibling
    of the same kind (e.g. one religion for another)."""
    prefix = tag.split(":", 1)[0] if ":" in tag else ""
    category = _PREFIX_TO_CATEGORY.get(prefix)
    if category is None:
        return []
    return [t for t in category if t != tag]


# ── Pairwise synergy data ─────────────────────────────────────────────
# Each tuple: (tag_a, tag_b, synergy)
# Stored once per pair; symmetry applied at query time.
# Unlisted pairs default to 0.0.
_SYNERGY_DATA: list[tuple[str, str, float]] = [
    # Positives — reinforcing combinations
    ("structure:egalitarianism",   "structure:cooperation",       0.80),
    ("practice:sedentism",         "practice:agriculture",        0.80),
    ("practice:nomadism",          "practice:foraging",           0.75),
    ("relations:conquest",         "relations:imperialism",       0.70),
    ("relations:isolationism",     "relations:protectionism",     0.70),
    ("relations:diplomacy",        "relations:xenophilia",        0.65),
    ("practice:sedentism",         "techno:industrialism",        0.65),
    ("relations:diplomacy",        "relations:commerce",          0.60),
    ("relations:xenophobia",       "relations:isolationism",      0.60),
    ("techno:science",             "techno:industrialism",        0.60),
    ("religion:luminary_worship",  "religion:demiurge_worship",   0.55),
    ("structure:egalitarianism",   "relations:diplomacy",         0.55),
    ("structure:cooperation",      "relations:diplomacy",         0.55),
    ("structure:hierarchy",        "practice:slavery",            0.55),
    ("religion:void_worship",      "religion:maltheism",          0.50),
    ("religion:ancestor_worship",  "religion:animism",            0.50),
    ("relations:xenophilia",       "relations:commerce",          0.50),
    ("values:honesty",             "structure:cooperation",       0.50),
    ("techno:industrialism",       "relations:commerce",          0.50),
    ("structure:hierarchy",        "practice:sedentism",          0.50),
    ("religion:luminary_worship",  "religion:ancestor_worship",   0.45),
    ("structure:egalitarianism",   "relations:xenophilia",        0.45),
    ("structure:hierarchy",        "relations:conquest",          0.40),
    ("practice:nomadism",          "relations:conquest",          0.40),
    ("practice:nomadism",          "religion:animism",            0.40),
    ("structure:hierarchy",        "relations:commerce",          0.40),
    ("values:honesty",             "relations:diplomacy",         0.40),
    ("religion:nontheism",         "techno:science",              0.40),
    ("structure:competition",      "relations:conquest",          0.40),
    ("structure:competition",      "relations:commerce",          0.40),
    ("relations:xenophobia",       "relations:protectionism",     0.40),
    # Negatives — conflicting combinations
    ("religion:luminary_worship",  "religion:maltheism",          -0.90),
    ("religion:demiurge_worship",  "religion:maltheism",          -0.90),
    ("structure:egalitarianism",   "structure:hierarchy",         -0.90),
    ("structure:egalitarianism",   "practice:slavery",            -0.90),
    ("relations:xenophilia",       "relations:xenophobia",        -0.90),
    ("techno:science",             "techno:luddism",              -0.90),
    ("techno:industrialism",       "techno:conservationism",      -0.80),
    ("practice:sedentism",         "practice:nomadism",           -0.80),
    ("relations:commerce",         "relations:protectionism",     -0.80),
    ("religion:luminary_worship",  "religion:nontheism",          -0.80),
    ("religion:demiurge_worship",  "religion:nontheism",          -0.80),
    ("structure:cooperation",      "structure:competition",       -0.75),
    ("practice:monogamy",          "practice:polygamy",           -0.70),
    ("relations:imperialism",      "relations:isolationism",      -0.70),
    ("practice:agriculture",       "practice:foraging",           -0.60),
    ("relations:conquest",         "relations:isolationism",      -0.60),
    ("techno:science",             "techno:superstition",         -0.60),
    ("techno:science",             "techno:magic",                -0.50),
    ("practice:monogamy",          "practice:lab_breeding",       -0.50),
    ("relations:protectionism",    "relations:xenophilia",        -0.50),
    ("relations:diplomacy",        "relations:imperialism",       -0.45),
    ("relations:diplomacy",        "relations:conquest",          -0.40),
    ("religion:nontheism",         "religion:animism",            -0.35),
    ("practice:polygamy",          "practice:lab_breeding",       -0.30),
    # ── Values & Virtues — within-cluster ────────────────────────────────
    # Strong reinforcing pairs
    ("values:patience",            "values:tenacity",              0.70),
    ("values:honesty",             "values:sincerity",             0.70),
    ("values:pragmatism",          "values:adaptability",          0.70),
    ("values:erudition",           "values:idealism",              0.55),
    ("values:charity",             "values:humility",              0.60),
    ("values:wit",                 "values:erudition",             0.50),
    ("values:ambition",            "values:tenacity",              0.60),
    ("values:prosperity",          "values:ambition",              0.55),
    ("values:folk_wisdom",         "values:patience",              0.50),
    ("values:folk_wisdom",         "values:sincerity",             0.45),
    ("values:idealism",            "values:charity",               0.45),
    ("values:adaptability",        "values:wit",                   0.40),
    # Weak or neutral reinforcements
    ("values:pragmatism",          "values:tenacity",              0.35),
    ("values:erudition",           "values:sincerity",             0.35),
    ("values:prosperity",          "values:tenacity",              0.30),
    ("values:humility",            "values:sincerity",             0.45),
    # Conflicts within V&V
    ("values:moderation",          "values:indulgence",           -0.85),
    ("values:ambition",            "values:humility",             -0.70),
    ("values:pragmatism",          "values:idealism",             -0.65),
    ("values:erudition",           "values:folk_wisdom",          -0.50),
    ("values:prosperity",          "values:charity",              -0.50),
    ("values:wit",                 "values:sincerity",            -0.35),
    ("values:patience",            "values:ambition",             -0.35),
    # ── Values & Virtues — cross-cluster (Religious) ──────────────────────
    ("values:idealism",            "religion:luminary_worship",    0.45),
    ("values:idealism",            "religion:demiurge_worship",    0.40),
    ("values:humility",            "religion:luminary_worship",    0.40),
    ("values:humility",            "religion:ancestor_worship",    0.40),
    ("values:humility",            "religion:animism",             0.35),
    ("values:sincerity",           "religion:ancestor_worship",    0.35),
    ("values:folk_wisdom",         "religion:ancestor_worship",    0.60),
    ("values:folk_wisdom",         "religion:animism",             0.55),
    ("values:folk_wisdom",         "religion:nontheism",          -0.35),
    ("values:erudition",           "religion:nontheism",           0.40),
    ("values:idealism",            "religion:maltheism",          -0.50),
    ("values:pragmatism",          "religion:maltheism",           0.30),
    ("values:charity",             "religion:void_worship",       -0.45),
    ("values:indulgence",          "religion:void_worship",        0.30),
    # ── Values & Virtues — cross-cluster (Technological) ─────────────────
    ("values:erudition",           "techno:science",               0.65),
    ("values:erudition",           "techno:magic",                 0.45),
    ("values:erudition",           "techno:luddism",              -0.55),
    ("values:folk_wisdom",         "techno:luddism",               0.40),
    ("values:folk_wisdom",         "techno:superstition",          0.45),
    ("values:folk_wisdom",         "techno:science",              -0.40),
    ("values:pragmatism",          "techno:industrialism",         0.45),
    ("values:pragmatism",          "techno:science",               0.40),
    ("values:idealism",            "techno:conservationism",       0.45),
    ("values:adaptability",        "techno:science",               0.35),
    ("values:adaptability",        "techno:industrialism",         0.35),
    ("values:moderation",          "techno:conservationism",       0.50),
    ("values:indulgence",          "techno:industrialism",         0.30),
    # ── Values & Virtues — cross-cluster (Societal) ───────────────────────
    ("values:idealism",            "structure:egalitarianism",     0.55),
    ("values:idealism",            "practice:slavery",            -0.70),
    ("values:charity",             "structure:egalitarianism",     0.50),
    ("values:charity",             "structure:cooperation",        0.55),
    ("values:charity",             "practice:slavery",            -0.65),
    ("values:humility",            "structure:cooperation",        0.45),
    ("values:ambition",            "structure:competition",        0.55),
    ("values:ambition",            "structure:hierarchy",          0.40),
    ("values:prosperity",          "relations:commerce",           0.50),
    ("values:prosperity",          "structure:competition",        0.45),
    ("values:moderation",          "practice:sedentism",           0.35),
    ("values:indulgence",          "practice:polygamy",            0.35),
    ("values:pragmatism",          "structure:cooperation",        0.35),
    ("values:tenacity",            "practice:sedentism",           0.30),
    ("values:adaptability",        "practice:nomadism",            0.45),
    # ── Values & Virtues — cross-cluster (External Relations) ─────────────
    ("values:honesty",             "relations:xenophilia",         0.40),
    ("values:wit",                 "relations:diplomacy",          0.45),
    ("values:wit",                 "relations:commerce",           0.40),
    ("values:ambition",            "relations:imperialism",        0.45),
    ("values:ambition",            "relations:conquest",           0.40),
    ("values:idealism",            "relations:diplomacy",          0.45),
    ("values:idealism",            "relations:conquest",          -0.45),
    ("values:pragmatism",          "relations:commerce",           0.40),
    ("values:adaptability",        "relations:xenophilia",         0.40),
    ("values:adaptability",        "relations:diplomacy",          0.35),
    ("values:prosperity",          "relations:imperialism",        0.35),
    ("values:moderation",          "relations:isolationism",       0.30),
    # ── New canonical values ──────────────────────────────────────────────
    # values:honor (replaces values:honesty)
    ("values:honor",               "values:sincerity",             0.65),
    ("values:honor",               "structure:cooperation",        0.45),
    ("values:honor",               "relations:diplomacy",          0.40),
    ("values:honor",               "values:hierarchy",             0.40),
    ("values:honor",               "values:humility",              0.30),
    ("values:honor",               "values:solidarity",            0.45),
    # values:prowess (replaces values:ambition)
    ("values:prowess",             "values:tenacity",              0.60),
    ("values:prowess",             "values:prosperity",            0.50),
    ("values:prowess",             "structure:competition",        0.55),
    ("values:prowess",             "structure:hierarchy",          0.40),
    ("values:prowess",             "relations:imperialism",        0.45),
    ("values:prowess",             "values:meritocracy",           0.55),
    ("values:prowess",             "values:humility",             -0.65),
    ("values:prowess",             "values:solidarity",           -0.30),
    # values:hierarchy
    ("values:hierarchy",           "structure:hierarchy",          0.85),
    ("values:hierarchy",           "practice:slavery",             0.55),
    ("values:hierarchy",           "relations:conquest",           0.40),
    ("values:hierarchy",           "values:meritocracy",           0.40),
    ("values:hierarchy",           "values:autonomy",             -0.50),
    ("values:hierarchy",           "structure:egalitarianism",    -0.85),
    ("values:hierarchy",           "values:solidarity",           -0.35),
    # values:sedentism
    ("values:sedentism",           "practice:sedentism",           0.90),
    ("values:sedentism",           "practice:agriculture",         0.80),
    ("values:sedentism",           "techno:industrialism",         0.65),
    ("values:sedentism",           "structure:hierarchy",          0.50),
    ("values:sedentism",           "values:moderation",            0.35),
    ("values:sedentism",           "values:tenacity",              0.30),
    ("values:sedentism",           "practice:nomadism",           -0.80),
    ("values:sedentism",           "values:adaptability",         -0.30),
    # values:xenophilia
    ("values:xenophilia",          "relations:xenophilia",         0.90),
    ("values:xenophilia",          "relations:diplomacy",          0.65),
    ("values:xenophilia",          "relations:commerce",           0.50),
    ("values:xenophilia",          "structure:egalitarianism",     0.45),
    ("values:xenophilia",          "values:adaptability",          0.40),
    ("values:xenophilia",          "relations:xenophobia",        -0.90),
    ("values:xenophilia",          "relations:protectionism",     -0.50),
    # values:meritocracy
    ("values:meritocracy",         "structure:competition",        0.50),
    ("values:meritocracy",         "values:erudition",             0.45),
    ("values:meritocracy",         "structure:hierarchy",          0.35),
    ("values:meritocracy",         "values:pragmatism",            0.40),
    ("values:meritocracy",         "values:idealism",              0.30),
    # values:solidarity
    ("values:solidarity",          "values:charity",               0.65),
    ("values:solidarity",          "structure:cooperation",        0.70),
    ("values:solidarity",          "structure:egalitarianism",     0.55),
    ("values:solidarity",          "values:idealism",              0.40),
    ("values:solidarity",          "values:autonomy",             -0.50),
    # values:autonomy
    ("values:autonomy",            "structure:competition",        0.35),
    ("values:autonomy",            "values:adaptability",          0.45),
    ("values:autonomy",            "values:wit",                   0.30),
    ("values:autonomy",            "structure:cooperation",       -0.25),
    # ── New practice tags ─────────────────────────────────────────────────
    # Arts & performance inter-synergies
    ("practice:music",             "practice:dance",               0.70),
    ("practice:music",             "practice:ritual",              0.55),
    ("practice:music",             "practice:theatre",             0.50),
    ("practice:music",             "practice:revelry",             0.60),
    ("practice:music",             "practice:poetry",              0.45),
    ("practice:dance",             "practice:ritual",              0.50),
    ("practice:dance",             "practice:revelry",             0.65),
    ("practice:dance",             "practice:athletics",           0.40),
    ("practice:visual",            "practice:crafts",              0.60),
    ("practice:visual",            "practice:theatre",             0.45),
    ("practice:theatre",           "practice:lit",                 0.55),
    ("practice:theatre",           "practice:poetry",              0.50),
    ("practice:lit",               "practice:poetry",              0.65),
    ("practice:crafts",            "practice:culinary",            0.40),
    ("practice:athletics",         "practice:combat",              0.55),
    ("practice:ritual",            "practice:revelry",             0.50),
    # Practice × values cross-synergies
    ("values:erudition",           "practice:lit",                 0.55),
    ("values:erudition",           "practice:poetry",              0.40),
    ("values:erudition",           "practice:visual",              0.35),
    ("values:folk_wisdom",         "practice:crafts",              0.55),
    ("values:folk_wisdom",         "practice:culinary",            0.50),
    ("values:folk_wisdom",         "practice:ritual",              0.50),
    ("values:indulgence",          "practice:revelry",             0.60),
    ("values:indulgence",          "practice:culinary",            0.50),
    ("values:indulgence",          "practice:music",               0.40),
    ("values:prosperity",          "practice:crafts",              0.35),
    ("values:wit",                 "practice:theatre",             0.50),
    ("values:wit",                 "practice:poetry",              0.45),
    ("values:humility",            "practice:ritual",              0.35),
    ("values:pragmatism",          "practice:combat",              0.30),
    ("values:tenacity",            "practice:athletics",           0.45),
    ("values:tenacity",            "practice:combat",              0.40),
    ("values:idealism",            "practice:visual",              0.40),
    ("values:idealism",            "practice:poetry",              0.40),
    ("values:honor",               "practice:combat",              0.50),
    ("values:honor",               "practice:ritual",              0.40),
    ("values:solidarity",          "practice:ritual",              0.45),
    ("values:solidarity",          "practice:revelry",             0.40),
    ("values:prowess",             "practice:athletics",           0.55),
    ("values:prowess",             "practice:combat",              0.50),
]


# ── Culture × Domain affinity data ────────────────────────────────────
# How much a culture tag (religion, value, etc.) amplifies or dampens domain
# influence on beliefs, alignment, and Pop receptivity. Per-unit additive
# bonus to the multiplier per unit of culture-tag strength. Unlisted pairs
# default to 0.0.
_DOMAIN_AFFINITY_DATA: dict[str, dict[str, float]] = {
    # ── Religion ────────────────────────────────
    "religion:luminary_worship": {
        "domain:order": 0.30, "domain:light": 0.30, "domain:truth": 0.20,
        "domain:mastery": 0.20, "domain:community": 0.15,
        "domain:void": -0.20, "domain:conflict": -0.15, "domain:decay": -0.20,
        "domain:sacrifice": -0.15,
    },
    "religion:demiurge_worship": {
        "domain:mastery": 0.30, "domain:truth": 0.25, "domain:order": 0.20,
        "domain:light": 0.20, "domain:change": 0.10,
        "domain:void": -0.20, "domain:decay": -0.15,
    },
    "religion:animism": {
        "domain:growth": 0.30, "domain:water": 0.25, "domain:change": 0.25,
        "domain:fire": 0.20, "domain:sacrifice": 0.20, "domain:memory": 0.20,
        "domain:community": 0.15,
        "domain:mastery": -0.15, "domain:truth": -0.10,
    },
    "religion:ancestor_worship": {
        "domain:memory": 0.40, "domain:community": 0.20, "domain:order": 0.10,
        "domain:growth": 0.15,
        "domain:change": -0.20, "domain:conflict": -0.10, "domain:void": -0.15,
    },
    "religion:maltheism": {
        "domain:conflict": 0.30, "domain:void": 0.25, "domain:decay": 0.30,
        "domain:sacrifice": 0.25, "domain:change": 0.20,
        "domain:order": -0.25, "domain:light": -0.30, "domain:community": -0.20,
        "domain:truth": -0.15,
    },
    "religion:nontheism": {
        "domain:truth": 0.30, "domain:silence": 0.20, "domain:order": 0.15,
        "domain:void": 0.15,
        "domain:sacrifice": -0.20, "domain:mastery": -0.15, "domain:light": -0.10,
        "domain:decay": -0.10,
    },
    "religion:void_worship": {
        "domain:void": 0.40, "domain:secrecy": 0.25, "domain:silence": 0.25,
        "domain:decay": 0.25, "domain:conflict": 0.15,
        "domain:light": -0.35, "domain:community": -0.25, "domain:growth": -0.20,
        "domain:truth": -0.15,
    },
    # ── Values & Virtues ────────────────────────
    "values:honesty": {
        "domain:truth": 0.30, "domain:light": 0.20, "domain:order": 0.15,
        "domain:secrecy": -0.30, "domain:void": -0.15,
    },
    "values:adaptability": {
        "domain:change": 0.30, "domain:water": 0.15, "domain:fire": 0.10,
        "domain:order": -0.20, "domain:memory": -0.10,
    },
    "values:moderation": {
        "domain:order": 0.20, "domain:silence": 0.20, "domain:sacrifice": 0.10,
        "domain:community": 0.10,
        "domain:fire": -0.20, "domain:conflict": -0.15,
    },
    "values:indulgence": {
        "domain:fire": 0.25, "domain:growth": 0.15, "domain:water": 0.10,
        "domain:order": -0.40, "domain:sacrifice": -0.35, "domain:silence": -0.30,
    },
    "values:charity": {
        "domain:community": 0.30, "domain:light": 0.20, "domain:growth": 0.15,
        "domain:sacrifice": 0.10,
        "domain:mastery": -0.20, "domain:conflict": -0.10,
    },
    "values:prosperity": {
        "domain:growth": 0.25, "domain:mastery": 0.20, "domain:community": 0.10,
        "domain:sacrifice": -0.25, "domain:decay": -0.20,
    },
    "values:ambition": {
        "domain:mastery": 0.30, "domain:conflict": 0.20, "domain:fire": 0.15,
        "domain:silence": -0.30, "domain:community": -0.20, "domain:sacrifice": -0.15,
    },
    "values:humility": {
        "domain:silence": 0.25, "domain:community": 0.20, "domain:order": 0.15,
        "domain:sacrifice": 0.10,
        "domain:mastery": -0.30, "domain:conflict": -0.15,
    },
    "values:wit": {
        "domain:change": 0.20, "domain:truth": 0.15, "domain:secrecy": 0.10,
        "domain:silence": -0.15, "domain:order": -0.10,
    },
    "values:sincerity": {
        "domain:truth": 0.30, "domain:community": 0.20, "domain:light": 0.15,
        "domain:order": 0.10,
        "domain:secrecy": -0.30,
    },
    "values:patience": {
        "domain:silence": 0.25, "domain:order": 0.20, "domain:memory": 0.15,
        "domain:growth": 0.10,
        "domain:conflict": -0.20, "domain:fire": -0.15,
    },
    "values:tenacity": {
        "domain:conflict": 0.20, "domain:mastery": 0.20, "domain:fire": 0.15,
        "domain:memory": 0.15,
        "domain:change": -0.15,
    },
    "values:idealism": {
        "domain:light": 0.30, "domain:truth": 0.20, "domain:sacrifice": 0.15,
        "domain:change": 0.10,
        "domain:secrecy": -0.20, "domain:void": -0.20,
    },
    "values:pragmatism": {
        "domain:mastery": 0.25, "domain:order": 0.15, "domain:change": 0.15,
        "domain:sacrifice": -0.20, "domain:light": -0.10,
    },
    "values:erudition": {
        "domain:truth": 0.30, "domain:memory": 0.25, "domain:silence": 0.10,
        "domain:mastery": 0.10,
        "domain:conflict": -0.15,
    },
    "values:folk_wisdom": {
        "domain:memory": 0.30, "domain:community": 0.20, "domain:growth": 0.15,
        "domain:water": 0.10,
        "domain:mastery": -0.20,
    },
    # ── New canonical values ─────────────────────────────────────────────
    "values:honor": {
        "domain:truth": 0.25, "domain:order": 0.20, "domain:light": 0.20,
        "domain:community": 0.15,
        "domain:secrecy": -0.30, "domain:void": -0.10,
    },
    "values:prowess": {
        "domain:mastery": 0.35, "domain:conflict": 0.20, "domain:fire": 0.15,
        "domain:silence": -0.20, "domain:community": -0.15,
    },
    "values:hierarchy": {
        "domain:order": 0.35, "domain:mastery": 0.20, "domain:community": 0.10,
        "domain:conflict": 0.15,
        "domain:change": -0.15,
    },
    "values:sedentism": {
        "domain:memory": 0.25, "domain:order": 0.20, "domain:growth": 0.15,
        "domain:community": 0.15,
        "domain:change": -0.20, "domain:water": -0.10,
    },
    "values:xenophilia": {
        "domain:change": 0.30, "domain:water": 0.20, "domain:truth": 0.15,
        "domain:secrecy": -0.15, "domain:order": -0.10,
    },
    "values:meritocracy": {
        "domain:mastery": 0.30, "domain:truth": 0.20, "domain:order": 0.15,
        "domain:community": -0.10,
    },
    "values:solidarity": {
        "domain:community": 0.35, "domain:sacrifice": 0.20, "domain:light": 0.15,
        "domain:mastery": -0.20, "domain:secrecy": -0.15,
    },
    "values:autonomy": {
        "domain:change": 0.25, "domain:mastery": 0.20, "domain:fire": 0.15,
        "domain:order": -0.25, "domain:community": -0.20,
    },
    # ── New practice tags ────────────────────────────────────────────────
    "practice:music": {
        "domain:community": 0.25, "domain:memory": 0.20, "domain:fire": 0.15,
        "domain:change": 0.10,
        "domain:silence": -0.20,
    },
    "practice:dance": {
        "domain:fire": 0.25, "domain:change": 0.20, "domain:community": 0.20,
        "domain:silence": -0.20, "domain:order": -0.10,
    },
    "practice:visual": {
        "domain:truth": 0.20, "domain:light": 0.20, "domain:memory": 0.15,
        "domain:mastery": 0.15,
        "domain:void": -0.10,
    },
    "practice:theatre": {
        "domain:truth": 0.20, "domain:change": 0.20, "domain:community": 0.15,
        "domain:secrecy": 0.15,
        "domain:silence": -0.15,
    },
    "practice:lit": {
        "domain:truth": 0.25, "domain:memory": 0.25, "domain:mastery": 0.15,
        "domain:void": -0.10,
    },
    "practice:poetry": {
        "domain:truth": 0.20, "domain:memory": 0.15, "domain:change": 0.15,
        "domain:water": 0.10,
        "domain:silence": -0.10,
    },
    "practice:crafts": {
        "domain:mastery": 0.30, "domain:growth": 0.15, "domain:memory": 0.15,
        "domain:void": -0.10,
    },
    "practice:culinary": {
        "domain:growth": 0.20, "domain:fire": 0.20, "domain:community": 0.20,
        "domain:water": 0.10,
        "domain:decay": -0.10,
    },
    "practice:athletics": {
        "domain:mastery": 0.25, "domain:conflict": 0.20, "domain:fire": 0.15,
        "domain:silence": -0.10,
    },
    "practice:combat": {
        "domain:conflict": 0.30, "domain:mastery": 0.25, "domain:fire": 0.20,
        "domain:community": -0.20, "domain:light": -0.10,
    },
    "practice:ritual": {
        "domain:order": 0.25, "domain:memory": 0.20, "domain:community": 0.20,
        "domain:sacrifice": 0.20,
        "domain:change": -0.15,
    },
    "practice:revelry": {
        "domain:fire": 0.25, "domain:community": 0.30, "domain:change": 0.15,
        "domain:water": 0.10,
        "domain:silence": -0.25, "domain:order": -0.15,
    },
}


class CultureRegistry:
    """
    Canonical, scenario-agnostic source of truth for culture trait tags
    and their pairwise synergy values.

    On first instantiation, bootstraps core/core.db tables if absent.
    """

    def __init__(self, db_path: Path = DEFAULT_CORE_DB) -> None:
        self._db_path = db_path
        self._synergy: dict[tuple[str, str], float] = {}
        self._domain_affinity: dict[str, dict[str, float]] = {}
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

    def domain_affinity(self, culture_tag: str) -> dict[str, float]:
        """
        Per-domain affinity modifiers for a culture tag. Unlisted tags → {}.
        Callers should treat the result as read-only.
        """
        return self._domain_affinity.get(culture_tag, {})

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
                CREATE TABLE IF NOT EXISTS culture_domain_affinity (
                    culture_tag TEXT NOT NULL,
                    domain_tag  TEXT NOT NULL,
                    modifier    REAL NOT NULL,
                    PRIMARY KEY (culture_tag, domain_tag)
                );
            """)

            for i, tag in enumerate(ALL_CULTURE_TAGS):
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

            for culture_tag, affinities in _DOMAIN_AFFINITY_DATA.items():
                for domain_tag, mod in affinities.items():
                    conn.execute(
                        "INSERT OR IGNORE INTO culture_domain_affinity "
                        "(culture_tag, domain_tag, modifier) VALUES (?,?,?)",
                        (culture_tag, domain_tag, mod),
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

            for row in conn.execute(
                "SELECT culture_tag, domain_tag, modifier FROM culture_domain_affinity"
            ):
                self._domain_affinity.setdefault(row["culture_tag"], {})[
                    row["domain_tag"]
                ] = row["modifier"]
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


def reinstate(db_path: Path = DEFAULT_CORE_DB) -> CultureRegistry:
    """Drop and recreate culture tables from Python source data, then reload the singleton."""
    global _registry
    _registry = None
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript("""
            DROP TABLE IF EXISTS culture_domain_affinity;
            DROP TABLE IF EXISTS culture_synergy;
            DROP TABLE IF EXISTS culture_registry;
        """)
        conn.commit()
    finally:
        conn.close()
    return get_registry(db_path)
