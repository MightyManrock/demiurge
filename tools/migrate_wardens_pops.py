"""One-shot migration: replace all Pops (and update mortals) on Neran Surface
and Neran Orbital Ring in wardens_compact.db, and update the Neran Confederacy
civilisation baseline, per docs/.dev/Scenarios/warden_compact_pops_revised.md.

Run once:
    venv/bin/python tools/migrate_wardens_pops.py [--dry-run]
"""
from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4, UUID

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.universe_core import Pop, SocialStratum
from utilities.scenario_loader import load_scenario
from utilities.scenario_exporter import export_scenario

SCENARIO = ROOT / "scenarios" / "wardens_compact.db"

DRY_RUN = "--dry-run" in sys.argv


# ── Civilisation baseline ──────────────────────────────────────────────────────

CIV_BELIEFS = {
    "order": 0.8, "mastery": 0.5, "community": 0.3,
    "truth": 0.25, "growth": 0.2, "light": 0.15,
}

CIV_CULTURE = {
    "sedentism": 0.9, "hierarchy": 0.85, "tenacity": 0.8,
    "relations:commerce": 0.75, "solidarity": 0.65, "erudition": 0.65,
    "luminary_worship": 0.6, "honor": 0.6, "ancestor_worship": 0.5,
    "pragmatism": 0.65, "meritocracy": 0.5, "prowess": 0.55,
    "prosperity": 0.45,
}


# ── Pop definitions ────────────────────────────────────────────────────────────
# Each entry: (social_class, occupation, size_fractional, mortal_name_or_None,
#              dominant_beliefs, culture_tags)

NERAN_SURFACE_POPS = [
    (SocialStratum.ELITE, "poli_admin", 5.0, "Senna Vaur",
     {"order": 0.9, "mastery": 0.55, "community": 0.3, "truth": 0.25, "light": 0.2, "secrecy": 0.15},
     {"hierarchy": 0.9, "solidarity": 0.75, "honor": 0.7, "sedentism": 0.8, "prowess": 0.65,
      "pragmatism": 0.65, "meritocracy": 0.6, "relations:commerce": 0.55, "luminary_worship": 0.5,
      "prosperity": 0.4, "nontheism": 0.35, "ancestor_worship": 0.2,
      "practice:ritual": 0.7, "practice:lit": 0.5}),

    (SocialStratum.ELITE, "noble", 3.5, None,
     {"order": 0.85, "mastery": 0.6, "memory": 0.4, "light": 0.25, "secrecy": 0.2},
     {"hierarchy": 0.9, "honor": 0.85, "sedentism": 0.9, "ancestor_worship": 0.8,
      "luminary_worship": 0.6, "folk_wisdom": 0.55, "prowess": 0.65, "meritocracy": 0.2,
      "practice:lit": 0.7, "practice:ritual": 0.65}),

    (SocialStratum.SCHOLAR, "scientist", 6.5, None,
     {"truth": 0.7, "mastery": 0.65, "order": 0.4, "change": 0.3, "light": 0.35},
     {"erudition": 0.95, "tenacity": 0.6, "pragmatism": 0.6, "nontheism": 0.55, "prowess": 0.55,
      "autonomy": 0.6, "idealism": 0.4, "hierarchy": 0.2, "sedentism": 0.65, "folk_wisdom": -0.3,
      "luminary_worship": 0.2, "ancestor_worship": 0.05, "practice:lit": 0.75}),

    (SocialStratum.SCHOLAR, "academic", 6.2, None,
     {"truth": 0.65, "mastery": 0.5, "order": 0.45, "memory": 0.3, "light": 0.3, "water": 0.2},
     {"erudition": 0.95, "idealism": 0.6, "patience": 0.55, "solidarity": 0.45, "pragmatism": 0.45,
      "ancestor_worship": 0.4, "humility": 0.4, "nontheism": 0.4, "hierarchy": 0.3, "sedentism": 0.7,
      "luminary_worship": 0.3, "practice:lit": 0.9, "practice:theatre": 0.35}),

    (SocialStratum.SCHOLAR, "clergy", 4.5, "Veth Sarai",
     {"order": 0.7, "silence": 0.55, "truth": 0.45, "memory": 0.35, "sacrifice": 0.3, "growth": 0.2},
     {"luminary_worship": 0.85, "ancestor_worship": 0.7, "sedentism": 0.8, "humility": 0.75,
      "patience": 0.65, "solidarity": 0.65, "demiurge_worship": 0.5, "sincerity": 0.5,
      "hierarchy": 0.55, "folk_wisdom": 0.5, "indulgence": -0.25,
      "practice:ritual": 0.9, "practice:music": 0.6}),

    (SocialStratum.TRADER, "merchant", 6.7, "Durenn Vail",
     {"order": 0.65, "community": 0.6, "mastery": 0.4, "change": 0.3, "void": 0.2},
     {"relations:commerce": 0.9, "prosperity": 0.8, "solidarity": 0.65, "honor": 0.55,
      "pragmatism": 0.65, "nontheism": 0.6, "xenophilia": 0.6, "hierarchy": 0.4,
      "sedentism": -0.5, "indulgence": 0.45, "adaptability": 0.4, "prowess": 0.35,
      "idealism": -0.1, "luminary_worship": 0.35, "ancestor_worship": 0.15,
      "practice:revelry": 0.7}),

    (SocialStratum.TRADER, "executive", 6.5, None,
     {"order": 0.75, "mastery": 0.55, "community": 0.3, "change": 0.2, "light": 0.2},
     {"relations:commerce": 0.8, "hierarchy": 0.8, "prowess": 0.75, "pragmatism": 0.7,
      "solidarity": 0.55, "honor": 0.6, "sedentism": 0.75, "meritocracy": 0.65,
      "prosperity": 0.6, "autonomy": 0.5, "nontheism": 0.45, "luminary_worship": 0.4,
      "indulgence": 0.35, "ancestor_worship": 0.25, "practice:revelry": 0.55}),

    (SocialStratum.TRADER, "financier", 6.0, None,
     {"order": 0.8, "mastery": 0.55, "community": 0.3, "truth": 0.3, "secrecy": 0.25},
     {"relations:commerce": 0.85, "hierarchy": 0.85, "meritocracy": 0.7, "prosperity": 0.85,
      "pragmatism": 0.75, "sedentism": 0.9, "honor": 0.65, "nontheism": 0.5,
      "luminary_worship": 0.35, "ancestor_worship": 0.2, "practice:revelry": 0.5}),

    (SocialStratum.ARTISAN, "engineer", 7.5, "Thessal Dour",
     {"mastery": 0.75, "order": 0.5, "change": 0.4, "truth": 0.3, "growth": 0.2},
     {"erudition": 0.8, "tenacity": 0.85, "pragmatism": 0.6, "prowess": 0.65, "autonomy": 0.5,
      "hierarchy": 0.5, "sedentism": 0.7, "nontheism": 0.65, "luminary_worship": 0.25,
      "ancestor_worship": 0.2, "practice:crafts": 0.75}),

    (SocialStratum.ARTISAN, "technician", 7.8, "Orryn Vel",
     {"mastery": 0.7, "change": 0.45, "order": 0.4, "conflict": 0.25, "community": 0.3},
     {"tenacity": 0.75, "erudition": 0.6, "pragmatism": 0.6, "adaptability": 0.55, "solidarity": 0.5,
      "honor": 0.45, "hierarchy": 0.35, "sedentism": 0.7, "nontheism": 0.5, "luminary_worship": 0.5,
      "wit": 0.35, "ancestor_worship": 0.3, "practice:crafts": 0.8}),

    (SocialStratum.ARTISAN, "crafter", 7.0, None,
     {"mastery": 0.8, "order": 0.5, "growth": 0.25, "truth": 0.2},
     {"tenacity": 0.8, "prowess": 0.75, "pragmatism": 0.65, "erudition": 0.65, "sedentism": 0.75,
      "hierarchy": 0.55, "luminary_worship": 0.4, "nontheism": 0.45, "ancestor_worship": 0.35,
      "practice:crafts": 0.9}),

    (SocialStratum.ARTISAN, "builder", 6.0, None,
     {"mastery": 0.65, "order": 0.6, "growth": 0.35, "community": 0.3},
     {"tenacity": 0.85, "pragmatism": 0.7, "solidarity": 0.65, "hierarchy": 0.6, "sedentism": 0.8,
      "prowess": 0.6, "luminary_worship": 0.5, "ancestor_worship": 0.45, "practice:crafts": 0.65}),

    (SocialStratum.ARTISAN, "healer", 5.5, None,
     {"mastery": 0.7, "truth": 0.45, "growth": 0.5, "order": 0.5, "light": 0.3},
     {"erudition": 0.8, "pragmatism": 0.7, "solidarity": 0.7, "hierarchy": 0.65, "sedentism": 0.8,
      "nontheism": 0.55, "prowess": 0.6, "luminary_worship": 0.3, "practice:lit": 0.5}),

    (SocialStratum.ARTISAN, "artist", 5.5, None,
     {"mastery": 0.6, "change": 0.5, "truth": 0.35, "community": 0.35, "light": 0.35},
     {"autonomy": 0.75, "wit": 0.65, "sincerity": 0.65, "idealism": 0.55, "erudition": 0.7,
      "sedentism": 0.55, "hierarchy": 0.15, "prowess": 0.65, "nontheism": 0.5,
      "luminary_worship": 0.3, "practice:visual": 0.8, "practice:theatre": 0.75,
      "practice:music": 0.65, "practice:lit": 0.7, "practice:crafts": 0.55}),

    (SocialStratum.COMMON, "professional", 8.2, None,
     {"order": 0.75, "mastery": 0.45, "community": 0.35, "truth": 0.2},
     {"sedentism": 0.9, "hierarchy": 0.75, "meritocracy": 0.6, "relations:commerce": 0.65,
      "honor": 0.55, "erudition": 0.55, "luminary_worship": 0.55, "pragmatism": 0.65,
      "prosperity": 0.5, "prowess": 0.4, "nontheism": 0.4, "ancestor_worship": 0.25,
      "practice:lit": 0.4, "practice:revelry": 0.5}),

    (SocialStratum.COMMON, "producer", 7.8, None,
     {"order": 0.7, "community": 0.55, "growth": 0.5, "mastery": 0.3},
     {"sedentism": 0.95, "solidarity": 0.7, "folk_wisdom": 0.65, "luminary_worship": 0.7,
      "ancestor_worship": 0.7, "tenacity": 0.75, "hierarchy": 0.5, "nontheism": 0.05,
      "practice:ritual": 0.55}),

    (SocialStratum.COMMON, "transport", 7.0, None,
     {"order": 0.65, "community": 0.5, "mastery": 0.4, "change": 0.3, "void": 0.2},
     {"tenacity": 0.75, "solidarity": 0.65, "pragmatism": 0.7, "sedentism": -0.2,
      "xenophilia": 0.35, "hierarchy": 0.55, "relations:commerce": 0.6, "luminary_worship": 0.55,
      "ancestor_worship": 0.3, "practice:revelry": 0.65}),

    (SocialStratum.COMMON, "service", 9.0, "Maeva Sorn",
     {"order": 0.7, "community": 0.5, "silence": 0.35, "memory": 0.3, "growth": 0.2},
     {"sedentism": 0.9, "solidarity": 0.65, "hierarchy": 0.6, "luminary_worship": 0.7,
      "ancestor_worship": 0.65, "relations:commerce": 0.6, "pragmatism": 0.55, "folk_wisdom": 0.5,
      "humility": 0.4, "nontheism": 0.05, "practice:revelry": 0.75, "practice:music": 0.4,
      "practice:ritual": 0.6}),

    (SocialStratum.COMMON, "laborer", 8.5, None,
     {"order": 0.7, "community": 0.5, "mastery": 0.4, "sacrifice": 0.25, "growth": 0.2, "fire": 0.15},
     {"sedentism": 0.9, "tenacity": 0.85, "solidarity": 0.7, "luminary_worship": 0.75,
      "hierarchy": 0.45, "folk_wisdom": 0.55, "ancestor_worship": 0.55, "pragmatism": 0.5,
      "meritocracy": -0.15, "adaptability": -0.1, "practice:revelry": 0.7, "practice:athletics": 0.5}),

    (SocialStratum.WARRIOR, "officer", 4.0, None,
     {"order": 0.8, "mastery": 0.55, "conflict": 0.5, "sacrifice": 0.25, "light": 0.2},
     {"hierarchy": 0.9, "prowess": 0.75, "tenacity": 0.8, "honor": 0.7, "solidarity": 0.5,
      "sedentism": 0.75, "pragmatism": 0.65, "luminary_worship": 0.45, "ancestor_worship": 0.4,
      "practice:combat": 0.8, "practice:athletics": 0.75}),

    (SocialStratum.WARRIOR, "guard", 5.5, None,
     {"order": 0.85, "mastery": 0.5, "conflict": 0.3, "community": 0.4, "light": 0.2},
     {"hierarchy": 0.85, "honor": 0.75, "tenacity": 0.7, "solidarity": 0.7, "sedentism": 0.9,
      "pragmatism": 0.65, "luminary_worship": 0.55, "ancestor_worship": 0.35,
      "practice:athletics": 0.6}),

    (SocialStratum.WARRIOR, "soldier", 5.5, None,
     {"order": 0.75, "conflict": 0.55, "mastery": 0.4, "sacrifice": 0.35, "fire": 0.2},
     {"hierarchy": 0.8, "tenacity": 0.8, "honor": 0.65, "solidarity": 0.6, "sedentism": 0.8,
      "ancestor_worship": 0.6, "luminary_worship": 0.55, "pragmatism": 0.5, "folk_wisdom": 0.4,
      "practice:combat": 0.75, "practice:athletics": 0.7, "practice:revelry": 0.55}),

    (SocialStratum.UNDERCLASS, "dispossessed", 5.5, None,
     {"community": 0.5, "order": 0.5, "silence": 0.3, "sacrifice": 0.35, "decay": 0.2},
     {"solidarity": 0.65, "folk_wisdom": 0.65, "luminary_worship": 0.75, "ancestor_worship": 0.65,
      "sedentism": 0.75, "tenacity": 0.6, "adaptability": 0.45, "hierarchy": 0.25,
      "meritocracy": -0.35, "nontheism": 0.05, "practice:revelry": 0.6}),
]

NERAN_ORBITAL_RING_POPS = [
    (SocialStratum.WARRIOR, "officer", 4.0, "Karath Omn",
     {"mastery": 0.8, "conflict": 0.65, "order": 0.55, "sacrifice": 0.3, "void": 0.2, "light": 0.2},
     {"hierarchy": 0.9, "prowess": 0.9, "tenacity": 0.85, "honor": 0.75, "solidarity": 0.55,
      "pragmatism": 0.6, "sedentism": 0.6, "nontheism": 0.5, "ancestor_worship": 0.35,
      "luminary_worship": 0.4, "practice:combat": 0.85, "practice:athletics": 0.7}),

    (SocialStratum.WARRIOR, "soldier", 3.5, None,
     {"order": 0.7, "conflict": 0.5, "mastery": 0.45, "sacrifice": 0.35, "void": 0.2},
     {"hierarchy": 0.8, "tenacity": 0.85, "honor": 0.6, "solidarity": 0.65, "sedentism": 0.65,
      "pragmatism": 0.55, "luminary_worship": 0.5, "ancestor_worship": 0.5, "folk_wisdom": 0.4,
      "nontheism": 0.25, "practice:combat": 0.7, "practice:athletics": 0.65}),

    (SocialStratum.WARRIOR, "guard", 4.0, None,
     {"order": 0.85, "mastery": 0.5, "conflict": 0.35, "community": 0.35, "void": 0.15},
     {"hierarchy": 0.85, "honor": 0.75, "tenacity": 0.75, "solidarity": 0.65, "sedentism": 0.8,
      "pragmatism": 0.6, "luminary_worship": 0.5, "ancestor_worship": 0.3,
      "practice:athletics": 0.55}),

    (SocialStratum.SCHOLAR, "scientist", 4.2, None,
     {"truth": 0.65, "mastery": 0.75, "order": 0.5, "change": 0.35, "void": 0.3, "light": 0.35},
     {"erudition": 0.95, "tenacity": 0.7, "hierarchy": 0.15, "nontheism": 0.7, "prowess": 0.7,
      "autonomy": 0.65, "idealism": 0.5, "pragmatism": 0.55, "folk_wisdom": -0.4,
      "sedentism": 0.5, "luminary_worship": 0.15, "ancestor_worship": 0.05,
      "practice:lit": 0.8}),

    (SocialStratum.ARTISAN, "engineer", 4.5, None,
     {"mastery": 0.8, "order": 0.55, "change": 0.4, "conflict": 0.3, "void": 0.2},
     {"tenacity": 0.85, "erudition": 0.65, "hierarchy": 0.7, "prowess": 0.7, "pragmatism": 0.55,
      "nontheism": 0.5, "solidarity": 0.45, "sedentism": 0.6, "luminary_worship": 0.4,
      "ancestor_worship": 0.1, "practice:crafts": 0.8}),

    (SocialStratum.ARTISAN, "technician", 5.2, None,
     {"mastery": 0.65, "order": 0.5, "change": 0.35, "community": 0.3, "void": 0.2},
     {"tenacity": 0.8, "erudition": 0.55, "hierarchy": 0.6, "sedentism": 0.65, "solidarity": 0.55,
      "pragmatism": 0.6, "luminary_worship": 0.45, "folk_wisdom": 0.4, "nontheism": 0.35,
      "ancestor_worship": 0.2, "practice:crafts": 0.7, "practice:revelry": 0.5}),

    (SocialStratum.ARTISAN, "healer", 3.5, None,
     {"mastery": 0.7, "truth": 0.5, "growth": 0.45, "order": 0.5, "void": 0.2},
     {"erudition": 0.8, "pragmatism": 0.75, "solidarity": 0.65, "hierarchy": 0.6, "nontheism": 0.6,
      "sedentism": 0.65, "prowess": 0.55, "luminary_worship": 0.25, "practice:lit": 0.4}),

    (SocialStratum.COMMON, "transport", 5.5, None,
     {"order": 0.65, "community": 0.5, "mastery": 0.4, "change": 0.35, "void": 0.35},
     {"tenacity": 0.8, "solidarity": 0.65, "pragmatism": 0.7, "sedentism": -0.3, "xenophilia": 0.4,
      "hierarchy": 0.5, "relations:commerce": 0.55, "luminary_worship": 0.5, "ancestor_worship": 0.25,
      "practice:revelry": 0.6}),

    (SocialStratum.COMMON, "service", 4.8, None,
     {"order": 0.65, "community": 0.5, "mastery": 0.35, "void": 0.15},
     {"sedentism": 0.7, "hierarchy": 0.7, "tenacity": 0.7, "solidarity": 0.6, "luminary_worship": 0.6,
      "pragmatism": 0.55, "ancestor_worship": 0.35, "folk_wisdom": 0.4, "nontheism": 0.2,
      "practice:revelry": 0.6}),

    (SocialStratum.COMMON, "laborer", 3.8, None,
     {"order": 0.65, "community": 0.45, "mastery": 0.4, "sacrifice": 0.3, "void": 0.2},
     {"tenacity": 0.85, "solidarity": 0.65, "sedentism": 0.7, "hierarchy": 0.5,
      "luminary_worship": 0.65, "folk_wisdom": 0.5, "pragmatism": 0.5, "ancestor_worship": 0.4,
      "meritocracy": -0.1, "nontheism": 0.05, "practice:revelry": 0.5}),
]


# ── Mortal updates ─────────────────────────────────────────────────────────────

MORTAL_UPDATES = {
    "Durenn Vail": {
        "occupation": "merchant",
        "belief_tags": {"mastery": 0.5, "community": 0.65, "order": 0.6, "change": 0.45, "void": 0.3},
        "culture_tags": {"relations:commerce": 0.95, "prosperity": 0.85, "sedentism": -0.7,
                         "xenophilia": 0.8, "indulgence": 0.7, "pragmatism": 0.75,
                         "solidarity": 0.7, "honor": 0.6, "adaptability": 0.55, "nontheism": 0.5,
                         "practice:revelry": 0.85, "practice:music": 0.75},
    },
    "Karath Omn": {
        "occupation": "officer",
        "belief_tags": {"mastery": 0.9, "conflict": 0.75, "order": 0.6, "sacrifice": 0.4,
                        "void": 0.35, "light": 0.25},
        "culture_tags": {"hierarchy": 0.95, "prowess": 0.95, "tenacity": 0.9, "honor": 0.85,
                         "pragmatism": 0.7, "nontheism": 0.6, "sedentism": 0.7, "solidarity": 0.45,
                         "ancestor_worship": 0.4, "luminary_worship": 0.35,
                         "practice:combat": 0.95, "practice:athletics": 0.8},
    },
    "Maeva Sorn": {
        "occupation": "service",
        "belief_tags": {"order": 0.65, "silence": 0.65, "community": 0.6, "memory": 0.5, "truth": 0.35},
        "culture_tags": {"luminary_worship": 0.92, "ancestor_worship": 0.85, "sedentism": 0.9,
                         "humility": 0.75, "patience": 0.65, "sincerity": 0.55, "solidarity": 0.65,
                         "folk_wisdom": 0.55, "practice:ritual": 0.8, "practice:music": 0.6},
    },
    "Orryn Vel": {
        "occupation": "technician",
        "belief_tags": {"change": 0.8, "conflict": 0.65, "truth": 0.5, "community": 0.55, "order": 0.1},
        "culture_tags": {"erudition": 0.85, "adaptability": 0.8, "autonomy": 0.75, "solidarity": 0.75,
                         "wit": 0.7, "hierarchy": -0.4, "sedentism": 0.55, "nontheism": 0.6,
                         "sincerity": 0.6, "idealism": 0.6, "practice:crafts": 0.9},
    },
    "Senna Vaur": {
        "occupation": "poli_admin",
        "belief_tags": {"order": 0.88, "mastery": 0.6, "community": 0.5, "truth": 0.3,
                        "light": 0.3, "secrecy": 0.25},
        "culture_tags": {"hierarchy": 0.95, "solidarity": 0.88, "honor": 0.82, "pragmatism": 0.78,
                         "prowess": 0.78, "meritocracy": 0.72, "sedentism": 0.85, "erudition": 0.65,
                         "luminary_worship": 0.5, "nontheism": 0.4,
                         "practice:ritual": 0.75, "practice:lit": 0.65},
    },
    "Thessal Dour": {
        "occupation": "engineer",
        "belief_tags": {"secrecy": 0.8, "silence": 0.6, "mastery": 0.65, "order": 0.15,
                        "truth": 0.2, "void": 0.35},
        "culture_tags": {"erudition": 0.92, "patience": 0.75, "autonomy": 0.75, "tenacity": 0.8,
                         "humility": 0.55, "hierarchy": 0.3, "sedentism": 0.75, "nontheism": 0.45,
                         "luminary_worship": 0.2, "practice:crafts": 0.88},
    },
    "Veth Sarai": {
        "occupation": "clergy",
        "belief_tags": {"silence": 0.75, "order": 0.7, "truth": 0.5, "memory": 0.45,
                        "sacrifice": 0.4, "growth": 0.25},
        "culture_tags": {"demiurge_worship": 0.92, "luminary_worship": 0.78, "sedentism": 0.85,
                         "humility": 0.82, "patience": 0.78, "sincerity": 0.6, "solidarity": 0.7,
                         "folk_wisdom": 0.6, "moderation": 0.55, "indulgence": -0.4,
                         "practice:ritual": 0.95, "practice:music": 0.72},
    },
}


# ── Migration ──────────────────────────────────────────────────────────────────

def migrate():
    state = load_scenario(SCENARIO)

    # Find Neran Confederacy civ
    neran_civ = next(
        (c for c in state.civilizations.values() if "neran" in c.name.lower()),
        None,
    )
    if neran_civ is None:
        raise RuntimeError("Could not find Neran Confederacy civilisation.")

    # Find target locations
    def find_loc(name: str):
        loc = next((l for l in state.locations.values() if getattr(l, "name", None) == name), None)
        if loc is None:
            raise RuntimeError(f"Location {name!r} not found.")
        return loc

    surface = find_loc("Neran Surface")
    orbital = find_loc("Neran Orbital Ring")

    # ── Step 1: collect mortals to preserve ───────────────────────────────────
    # Gather all mortals currently attached to pops at the two locations.
    all_pop_ids = set(str(pid) for pid in surface.pop_ids + orbital.pop_ids)
    preserved_mortals = {}   # name → mortal
    for pop_id in all_pop_ids:
        pop = state.pops.get(pop_id)
        if pop is None:
            continue
        for mid in pop.notable_mortal_ids:
            m = state.mortals.get(str(mid))
            if m:
                preserved_mortals[m.name] = m
                m.pop_id = None   # detach; we'll reattach below
        pop.notable_mortal_ids.clear()

    # ── Step 2: delete old pops ────────────────────────────────────────────────
    for loc in (surface, orbital):
        for pid in list(loc.pop_ids):
            pid_str = str(pid)
            if pid_str in state.pops:
                del state.pops[pid_str]
            # Remove from civ
            neran_civ.pop_ids = [p for p in neran_civ.pop_ids if str(p) != pid_str]
        loc.pop_ids.clear()

    # ── Step 3: update civ baseline ───────────────────────────────────────────
    neran_civ.dominant_beliefs = dict(CIV_BELIEFS)
    neran_civ.culture_tags = dict(CIV_CULTURE)

    # ── Step 4: create new pops and attach mortals ────────────────────────────
    def build_pops(loc, spec_list):
        for social_class, occupation, size, mortal_name, beliefs, culture in spec_list:
            pop = Pop(
                id=uuid4(),
                civilization_id=neran_civ.id,
                species_id=_neran_species_id(state, neran_civ),
                social_class=social_class,
                occupation=occupation,
                size_fractional=size,
                dominant_beliefs=dict(beliefs),
                culture_tags=dict(culture),
                current_location=loc.id,
            )
            state.pops[str(pop.id)] = pop
            loc.pop_ids.append(pop.id)
            neran_civ.pop_ids.append(pop.id)

            if mortal_name:
                m = preserved_mortals.get(mortal_name)
                if m is None:
                    print(f"  WARNING: mortal {mortal_name!r} not found — skipping attachment")
                    continue
                m.pop_id = pop.id
                pop.notable_mortal_ids.append(m.id)

    build_pops(surface, NERAN_SURFACE_POPS)
    build_pops(orbital, NERAN_ORBITAL_RING_POPS)

    # ── Step 4b: link surface ↔ orbital ring Pop pairs ────────────────────────
    # Base link factors authored from brainstorming/linked_pops.md.
    _NERAN_LINK_FACTORS: dict[str, float] = {
        "transport":  0.90,
        "officer":    0.80,
        "scientist":  0.75,
        "engineer":   0.70,
        "soldier":    0.70,
        "guard":      0.65,
        "technician": 0.65,
        "healer":     0.60,
        "service":    0.55,
        "laborer":    0.55,
    }
    surface_by_occ = {
        state.pops[str(pid)].occupation: state.pops[str(pid)]
        for pid in surface.pop_ids
    }
    orbital_by_occ = {
        state.pops[str(pid)].occupation: state.pops[str(pid)]
        for pid in orbital.pop_ids
    }
    for occ, base in _NERAN_LINK_FACTORS.items():
        s_pop = surface_by_occ.get(occ)
        o_pop = orbital_by_occ.get(occ)
        if s_pop and o_pop:
            s_pop.linked_pop_ids[str(o_pop.id)] = base
            o_pop.linked_pop_ids[str(s_pop.id)] = base
        else:
            print(f"  WARNING: no link pair found for occupation {occ!r}")

    # ── Step 5: update mortal data ─────────────────────────────────────────────
    for name, updates in MORTAL_UPDATES.items():
        m = preserved_mortals.get(name)
        if m is None:
            print(f"  WARNING: mortal {name!r} not found in state — skipping update")
            continue
        m.occupation = updates["occupation"]
        m.belief_tags = dict(updates["belief_tags"])
        m.culture_tags = dict(updates["culture_tags"])

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"Neran Surface:      {len(surface.pop_ids):2d} pops")
    print(f"Neran Orbital Ring: {len(orbital.pop_ids):2d} pops")
    print(f"Mortals updated:    {len(MORTAL_UPDATES)}")

    if DRY_RUN:
        print("\nDry run — no changes written.")
        return

    from utilities.scenario_migrator import _peek_scenario_meta
    name, description = _peek_scenario_meta(SCENARIO)
    export_scenario(state, SCENARIO, scenario_name=name, description=description)
    print(f"\nWritten → {SCENARIO}")


def _neran_species_id(state, civ):
    """Return the species_id used by the majority of existing Neran pops,
    or None if the civ has no pops yet (shouldn't happen but safe)."""
    for pid in civ.pop_ids:
        p = state.pops.get(str(pid))
        if p and p.species_id:
            return p.species_id
    # Fall back: look for any pop whose civilization_id matches
    for p in state.pops.values():
        if p.civilization_id == civ.id and p.species_id:
            return p.species_id
    return None


if __name__ == "__main__":
    migrate()
