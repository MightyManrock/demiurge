from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.universe_core import NotableMortal
    from core.agent_core import CivilianAgentState

from core.agent_core import MortalNeed

# ---------------------------------------------------------------------------
# Canonical need name constants
# ---------------------------------------------------------------------------

NEED_SUSTENANCE = "sustenance"
NEED_SAFETY     = "safety"
NEED_BELONGING  = "belonging"
NEED_STATUS     = "status"
NEED_PURPOSE    = "purpose"
NEED_LEISURE    = "leisure"

CANONICAL_NEEDS = (
    NEED_SUSTENANCE,
    NEED_SAFETY,
    NEED_BELONGING,
    NEED_STATUS,
    NEED_PURPOSE,
    NEED_LEISURE,
)

# ---------------------------------------------------------------------------
# Default parameters per need
# ---------------------------------------------------------------------------

NEED_DEFAULTS: dict[str, dict[str, float]] = {
    NEED_SUSTENANCE: {"decay_rate": 0.02,  "pressing_threshold": 0.55, "urgent_threshold": 0.20},
    NEED_SAFETY:     {"decay_rate": 0.01,  "pressing_threshold": 0.50, "urgent_threshold": 0.20},
    NEED_BELONGING:  {"decay_rate": 0.02,  "pressing_threshold": 0.65, "urgent_threshold": 0.30},
    NEED_STATUS:     {"decay_rate": 0.03,  "pressing_threshold": 0.60, "urgent_threshold": 0.25},
    NEED_PURPOSE:    {"decay_rate": 0.03,  "pressing_threshold": 0.60, "urgent_threshold": 0.25},
    NEED_LEISURE:    {"decay_rate": 0.02,  "pressing_threshold": 0.65, "urgent_threshold": 0.30},
}

# ---------------------------------------------------------------------------
# Trait modifier table
# NEED_TRAIT_MODIFIERS[need][trait] = (Δdecay, Δpressing, Δurgent) per 1.0 of signed trait value
# ---------------------------------------------------------------------------

NEED_TRAIT_MODIFIERS: dict[str, dict[str, tuple[float, float, float]]] = {
    NEED_SUSTENANCE: {
        "values:indulgence": ( 0.010,  0.050,  0.050),
        "values:moderation": (-0.010, -0.050, -0.050),
        "values:pragmatism": ( 0.000,  0.000, -0.050),
    },
    NEED_SAFETY: {
        "values:tenacity":   ( 0.000,  0.000, -0.050),
        "values:pragmatism": ( 0.000,  0.050,  0.050),
        "values:sedentism":  ( 0.005,  0.050,  0.000),
    },
    NEED_BELONGING: {
        "values:solidarity": ( 0.020,  0.100,  0.100),
        "values:autonomy":   (-0.020, -0.100, -0.100),
    },
    NEED_STATUS: {
        "values:prowess":    ( 0.015,  0.100,  0.100),
        "values:humility":   (-0.010, -0.100, -0.100),
        "values:hierarchy":  ( 0.010,  0.050,  0.050),
    },
    NEED_PURPOSE: {
        "values:idealism":   ( 0.015,  0.100,  0.100),
        "values:pragmatism": (-0.010, -0.050, -0.050),
        "values:prowess":    ( 0.010,  0.050,  0.000),
    },
    NEED_LEISURE: {
        "values:indulgence": ( 0.020,  0.100,  0.100),
        "values:moderation": (-0.010, -0.050, -0.050),
        "values:pragmatism": ( 0.000, -0.050,  0.000),
        "values:idealism":   ( 0.000, -0.050,  0.000),
    },
}

# ---------------------------------------------------------------------------
# Profile generator
# ---------------------------------------------------------------------------

def compute_need_profile(culture_tags: dict[str, float]) -> list[MortalNeed]:
    """Return a MortalNeed for every canonical need, parameters modulated by culture_tags."""
    needs = []
    for need_name in CANONICAL_NEEDS:
        defaults  = NEED_DEFAULTS[need_name]
        decay     = defaults["decay_rate"]
        pressing  = defaults["pressing_threshold"]
        urgent    = defaults["urgent_threshold"]

        for trait, (δd, δp, δu) in NEED_TRAIT_MODIFIERS.get(need_name, {}).items():
            v = culture_tags.get(trait, 0.0)
            if v:
                decay   += δd * v
                pressing += δp * v
                urgent   += δu * v

        # Clamp: decay ≥ 0.005; thresholds in (0.05, 0.9); urgent < pressing
        decay    = max(0.005, round(decay, 4))
        pressing = max(0.10, min(0.90, round(pressing, 3)))
        urgent   = max(0.05, min(pressing - 0.05, round(urgent, 3)))

        needs.append(MortalNeed(
            name=need_name,
            satisfaction=1.0,
            decay_rate=decay,
            pressing_threshold=pressing,
            urgent_threshold=urgent,
        ))
    return needs


def initialize_civilian_state(mortal: NotableMortal) -> CivilianAgentState:
    """Build a fresh CivilianAgentState (needs only) from the mortal's culture_tags.

    Inventory and knowledge_base must be populated separately.
    """
    from core.agent_core import CivilianAgentState
    return CivilianAgentState(needs=compute_need_profile(mortal.culture_tags))
