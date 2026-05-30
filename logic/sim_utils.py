from __future__ import annotations
from typing import TYPE_CHECKING

from core.universe_core import Pop, SignificantLocation, PopLocation
from utilities.culture_registry import get_registry as get_culture_registry

if TYPE_CHECKING:
    from logic.tick_logic import SimulationState


def resolve_world_id_for(state: "SimulationState", loc_id) -> "str | None":
    """Return the str id of the SignificantLocation (world) covering loc_id.

    If loc_id is already a SignificantLocation, returns it. If it's a
    PopLocation, walks up to its parent. Returns None for anything else."""
    if loc_id is None:
        return None
    loc = state.locations.get(str(loc_id))
    if isinstance(loc, SignificantLocation):
        return str(loc.id)
    if isinstance(loc, PopLocation) and loc.parent_id is not None:
        parent = state.locations.get(str(loc.parent_id))
        if isinstance(parent, SignificantLocation):
            return str(parent.id)
    return None


def resolve_world_for(state: "SimulationState", loc_id) -> "SignificantLocation | None":
    """Same as resolve_world_id_for but returns the SignificantLocation object."""
    wid = resolve_world_id_for(state, loc_id)
    return state.worlds.get(wid) if wid else None


def pop_domain_receptivity(pop, domain_tag: str) -> float:
    """Multiplier (≥ 0.2) for how receptive a Pop is to domain influence.

    Derived from all culture_tags (religion + values) crossing against
    CultureRegistry.domain_affinity.
    """
    creg = get_culture_registry()
    bonus = 0.0
    for tag, strength in pop.culture_tags.items():
        affinities = creg.domain_affinity(tag)
        bonus += affinities.get(domain_tag, 0.0) * strength
    return max(0.2, 1.0 + bonus)


def cosine_similarity(a: dict[str, float], b: dict[str, float]) -> float:
    """Cosine similarity between two belief/domain dicts. Returns 0.0–1.0."""
    if not a or not b:
        return 0.0
    tags = set(a) | set(b)
    dot = sum(a.get(t, 0.0) * b.get(t, 0.0) for t in tags)
    mag_a = sum(v * v for v in a.values()) ** 0.5
    mag_b = sum(v * v for v in b.values()) ** 0.5
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


# ── Linked-pop constants ────────────────────────────────────────────────────

LINK_STRATUM_BONUS    = 0.05   # flat bonus for shared social class
LINK_OCCUPATION_BONUS = 0.10   # flat bonus for shared occupation
LINK_COSINE_WEIGHT    = 0.20   # max cosine contribution to computed link factor
LINK_DRIFT_RATE       = 0.008  # per-stride lerp rate (half-life ≈ 87 strides)
LINK_BREAK_THRESHOLD  = 0.16   # computed factor below this → link dissolves
LINK_DRIFT_STRIDE     = 17     # ticks between link-drift passes
LINK_SPLASH_OWN_POP_SCALE     = 0.80  # belief cascade fraction for own-pop's linked pops
LINK_SPLASH_WORLD_POP_SCALE   = 0.40  # belief cascade fraction for world-splash pops' linked pops
LINK_VISIBILITY_CASCADE_SCALE = 0.60  # visibility cascade scale


def compute_link_factor(pop_a: Pop, pop_b: Pop, base: float) -> float:
    """Computed link factor between two Pops given a base link factor.

    Combines structural bonuses (shared stratum, shared occupation) with a
    cosine similarity component over merged belief+culture vectors.
    Returns a value clamped to [0.0, 1.0].
    """
    stratum_bonus = LINK_STRATUM_BONUS if pop_a.stratum == pop_b.stratum else 0.0
    occupation_bonus = LINK_OCCUPATION_BONUS if pop_a.occupation == pop_b.occupation else 0.0
    a_vec = {**pop_a.dominant_beliefs, **pop_a.culture_tags}
    b_vec = {**pop_b.dominant_beliefs, **pop_b.culture_tags}
    cosine = cosine_similarity(a_vec, b_vec)
    return min(1.0, max(0.0, base + stratum_bonus + occupation_bonus + LINK_COSINE_WEIGHT * cosine))
