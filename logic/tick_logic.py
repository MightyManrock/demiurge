from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from uuid import UUID, uuid4
import random
import math

from core.action_core import (
    DomainVector,
    StateMutation, MutationType,
    ActionOutcome,
    ActionInstance,
    OngoingAction,
    EssenceStockpile,
    build_action_library,
    ActionDefinition,
    ActionReliability,
    WhisperIntent, ShapeDreamIntent, OmenIntent, ProbabilityNudgeIntent,
    CultureVector, Framing,
    DevelopmentIntent, ProxiusDirectiveIntent,
    LuminaryPetitionIntent, EssenceHarvestIntent, SalvageIntent,
    SeedWorldIntent, UpliftSpeciesIntent, ExploreBeliefIntent,
    RevealImagoIntent, CommissionInquiryIntent,
    ChangeAffiliatedDomainsIntent, ScryIntent, ScryScope,
    TargetType,
)
from core.eval_core import (
    UniverseDomainProfile,
    LuminaryEvaluation,
    DialogueTrigger,
    EvaluationEngine,
    AttentionTrigger,
    FootprintAssessment,
    EssenceSuspicion,
    EssenceSatisfaction,
    evaluate_essence_satisfaction,
    DispositionDelta,
    DispositionDeltaReason,
)
from core.onto_core import (
    Demiurge, Pantheon, Luminary, FootprintConstraint, ResultsConstraint,
)
from core.universe_core import (
    Universe, Location, System, SignificantLocation, PopLocation,
    Civilization, NotableMortal,
    MortalRole, MortalStatus, MortalProminence, LocCondition,
    Species, SpeciesCondition,
    Pop, SocialClass, is_wild_civ,
)
from utilities.domain_registry import DomainRegistry, LuminaryPersonality, get_registry as get_domain_registry
from utilities.culture_registry import (
    CultureRegistry, get_registry as get_culture_registry, peer_culture_tags,
)
from utilities.imago_registry import get_registry as get_imago_registry
from core.event_core import Event, EventType, StrengthCurve
from core.agent_core import ProxiusGoal, AgentActionChoice


# ─────────────────────────────────────────
# VISIBILITY CONSTANTS
# ─────────────────────────────────────────

ENTITY_VISIBILITY_FLOOR = 0.05
# Below this, any entity (location, civilization, species, mortal) is out of the Window.

# ─────────────────────────────────────────
# PROXIUS POLICY CONSTANTS
# ─────────────────────────────────────────

# Fraction of the passive rate applied to each Proxius on a policy-compliant world.
# Compliant worlds have ≤ proxii_policy.max_per_world active Proxii.
PROXIUS_COMPLIANCE_FACTOR = 0.3

# ─────────────────────────────────────────
# BELIEF SYSTEM CONSTANTS
# ─────────────────────────────────────────

BELIEF_FLOOR = 0.02

CULTURE_FLOOR = 0.01
# Minimum durable strength for culture_tags. Lower than BELIEF_FLOOR (0.02)
# because culture-tag riders propagate at smaller per-tick magnitudes than
# Domain-belief shifts (Imago `culture:*` mechanics top out at ~0.20 even at
# T1, vs. ~0.35 for `domain:*`). The lower floor lets repeated whispers'
# fingerprints accumulate visibly on a Pop's culture even when a single
# whisper's per-tick contribution would have been pruned at BELIEF_FLOOR.
# Belief/domain-expression entries below this strength are
# silently pruned each passive phase. Keeps dicts clean of

BELIEF_CAP = 0.9
# Hard ceiling for positive belief/culture growth on Pops, Mortals, and
# Civilizations. Values can decay below 0.9 naturally; they just cannot
# grow past it. Location domain_expression is uncapped.
# ghost residue from many tiny-delta actions.

# ─────────────────────────────────────────
# POP SPLINTER CONSTANTS
# ─────────────────────────────────────────

SPLINTER_DIVERGENCE_THRESHOLD = 0.35
# Cosine distance (1 − similarity) at which a Pop's beliefs are divergent
# enough from civ.established_beliefs to trigger a population split.

SPLINTER_MIN_SIZE = 4.0
# Pop must be at least this large (size_fractional) to split.
# Prevents micro-Pops from fragmenting further.

SPLINTER_FRACTION = 0.35
# Fraction of the parent Pop's size that breaks away into the splinter.

WHISPER_POP_SPLASH = 0.20
# Fraction of a whisper's belief delta that ripples to the target mortal's
# Pop(s) on the same world.

WHISPER_OWN_POP_BASE_INFLUENCE = 0.5
WHISPER_OWN_POP_PROMINENCE_GAIN = 2.0
# Splash multiplier when the splash Pop is the mortal's own Pop:
#     base + prominence * gain
# Even an obscure mortal carries some weight in their immediate social context
# (the base), and prominence multiplies that further. Range [0.5, 2.5].

WHISPER_CROSS_POP_PROMINENCE_GAIN = 1.5
# Splash multiplier when the splash Pop is NOT the mortal's own Pop:
#     prominence * gain
# A nobody can't really push ideas onto other Pops on the world; only mortals
# others know about (high prominence) carry reputational reach. Range [0, 1.5].

OMEN_POP_SPLASH = 0.20
# Fraction of a development nudge's domain delta distributed across all
# Pops on the target world, weighted inversely by size (smaller = more impact).
# (No longer used by Manifest Omen — see the shotgun resolver below.)

# ── Manifest Omen "shotgun" interpretation ───────────────────────────
OMEN_BASE = 0.35
# Scales a raw omen vector `direction` into the effect magnitude E that gets
# subdivided across a Pop's interpretation checks. A fully-passed primary
# domain (raw 0.35) lands ~0.12.

OMEN_PASS_BASE_SUCCESS = 0.55   # base interpretation-check pass probability, SUCCESS outcome
OMEN_PASS_BASE_PARTIAL = 0.35   # base for PARTIAL / CHAOTIC outcomes
OMEN_FRAMING_WEIGHT     = 0.25  # how much framing resonance [-1,1] swings pass_prob
OMEN_RECEPTIVITY_WEIGHT = 0.20  # how much (domain receptivity - 1.0) swings pass_prob
OMEN_COHESION_WEIGHT    = 0.20  # how much (civ cohesion - 0.5) swings pass_prob
OMEN_AMBIGUOUS_PENALTY  = 0.15  # flat pass_prob reduction for AMBIGUOUS framing

# Per-framing culture-tag resonance. _framing_resonance() sums weight × the
# target's culture-tag strength, clamped to [-1, 1]. Drives how reliably a
# population reads an omen the way the Demiurge intended.
_OMEN_FRAMING_AFFINITY: dict[str, dict[str, float]] = {
    "prophetic": {
        "religion:luminary_worship": 0.8, "religion:demiurge_worship": 0.8,
        "religion:ancestor_worship": 0.6, "religion:animism": 0.5,
        "religion:maltheism": 0.4, "religion:void_worship": 0.4,
        "techno:superstition": 0.6, "techno:magic": 0.4,
        "religion:nontheism": -0.7, "techno:science": -0.5,
    },
    "natural": {
        "techno:science": 0.7, "religion:nontheism": 0.6,
        "values:pragmatism": 0.5, "values:erudition": 0.4,
        "techno:industrialism": 0.3,
        "religion:luminary_worship": -0.5, "religion:demiurge_worship": -0.5,
        "techno:superstition": -0.5,
    },
    "inspirational": {
        "values:ambition": 0.7, "values:idealism": 0.7,
        "values:tenacity": 0.4, "values:wit": 0.3, "values:prosperity": 0.3,
        "values:humility": -0.4, "values:moderation": -0.3,
    },
    "threatening": {
        "relations:xenophobia": 0.6, "relations:isolationism": 0.5,
        "relations:protectionism": 0.5, "values:tenacity": 0.5,
        "religion:maltheism": 0.5, "structure:hierarchy": 0.3,
        "relations:xenophilia": -0.5, "values:idealism": -0.4,
        "values:charity": -0.3,
    },
    "ambiguous": {
        "values:wit": 0.5, "values:erudition": 0.4, "values:folk_wisdom": 0.4,
        "religion:animism": 0.3,
        "values:pragmatism": -0.4, "values:sincerity": -0.3,
        "structure:hierarchy": -0.3,
    },
}

LINEAGE_BLEED_FRACTION = 0.20
# Fraction of a splash delta that bleeds further to a Pop's parent and children.
# Moderated by cosine similarity — diverged relatives resist the bleed.

RIDER_ATTRITION_BASE = 0.003
# Base decay rate per tick applied to culture_tags that conflict with a Pop's active rider_traits.
# Multiplied by (1.0 - synergy): syn=-1 → 2x, syn=0 → 1x, syn=+1 → 0x.


def compute_mortal_alignment_base(
    mortal,
    affiliated_domains: list,
    dreg,
) -> float:
    """
    Computes a mortal's natural alignment drift target from two sources:
      domain belief similarity  — weight 0.70
      culture tag affinity      — weight 0.30  (religion + values, via CultureRegistry.domain_affinity)
    Returns a value in [0.05, 0.95].
    Falls back to 0.5 if affiliated_domains is empty or mortal has no relevant data.

    Per-set normalization: the mean similarity for a maximally-aligned tag is
    bounded by how internally-coherent the affiliated set is (for a conflicted
    set like Warden's Compact the diagonal contributes 1/n_aff plus small
    cross-similarities). We divide by that ceiling so any tag perfectly matching
    one affiliated domain scores ~1.0.
    """
    if not affiliated_domains:
        return 0.5

    n_aff = len(affiliated_domains)

    def mean_sim_to_affiliated(tag: str) -> float:
        # Mean — not max — so a tag that aligns with one affiliated domain but
        # opposes the others scores near zero rather than always positive.
        return sum(dreg.similarity(tag, a) for a in affiliated_domains) / n_aff

    # Normalization ceiling: the highest mean-sim any affiliated domain itself
    # achieves against the affiliated set. Used so a fully-aligned belief
    # produces ~1.0 regardless of how mutually-coherent the set is.
    norm = max(mean_sim_to_affiliated(a) for a in affiliated_domains)
    if norm <= 0.0:
        norm = 1.0  # degenerate; avoid division blow-up

    # Belief tags — primary signal
    b_score = b_wt = 0.0
    for b_tag, strength in mortal.belief_tags.items():
        b_score += mean_sim_to_affiliated(b_tag) * strength
        b_wt    += strength
    belief_sim = (b_score / b_wt / norm) if b_wt else 0.0

    # Culture tags (religion + values) via CultureRegistry.domain_affinity.
    # No damping on negatives — opposing values/religions pull alignment down
    # at full weight, mirroring how synergistic ones lift it.
    creg = get_culture_registry()
    c_score = c_wt = 0.0
    for c_tag, c_strength in mortal.culture_tags.items():
        domain_affinities = creg.domain_affinity(c_tag)
        for d_tag, d_affinity in domain_affinities.items():
            c_score += mean_sim_to_affiliated(d_tag) * d_affinity * c_strength
            c_wt    += abs(d_affinity) * c_strength
    culture_sim = (c_score / c_wt / norm) if c_wt else 0.0

    combined = belief_sim * 0.70 + culture_sim * 0.30
    # Map combined [-1.0, +1.0] → [0.05, 0.95].
    return max(0.05, min(0.95, 0.5 + combined * 0.45))


# Essence generation: per-CivilizationScale multipliers applied to dominant_beliefs.
# Ordered so that inherent location weight (3.0) always exceeds even max-scale civ (1.60).
_CIV_SCALE_ESSENCE_MULT: dict[str, float] = {
    "nascent":        0.05,
    "tribal":         0.10,
    "city_state":     0.20,
    "regional":       0.35,
    "continental":    0.50,
    "planetary":      0.70,
    "interplanetary": 0.90,
    "interstellar":   1.20,
    "intergalactic":  1.60,
}

def is_in_window(entity: object) -> bool:
    """True if the Demiurge has this entity (location, civilization, or species) in the Window."""
    vis = getattr(entity, "visibility", 0.0)
    pinned = getattr(entity, "pinned", False)
    return pinned or vis > ENTITY_VISIBILITY_FLOOR

is_mortal_visible = is_in_window  # backward-compat alias


def _first_appointed_tick(mortal: object) -> "Optional[int]":
    """Return the earliest tick at which a mortal was elevated to any divine-appointment role."""
    ticks = [
        t for t in (
            getattr(mortal, "proxius_appointed_tick", None),
            getattr(mortal, "herald_appointed_tick", None),
        )
        if t is not None
    ]
    return min(ticks) if ticks else None


# ─────────────────────────────────────────
# REVELATION CONSTANTS
# ─────────────────────────────────────────

_REVELATION_BASE_COSTS: dict[int, int] = {1: 60, 2: 100, 3: 200, 4: 400}

# Weighted sum of domain expression across all civs + significant locations;
# considered "full expression" at this denominator value for normalization.
_REVELATION_EXPRESSION_FULL: float = 3.0

# ─────────────────────────────────────────
# PUISSANCE CONSTANTS
# ─────────────────────────────────────────

REV_SCALE    = 500.0   # lifetime_revelation saturation point (revelation component)
IMAGO_SCALE  = 40.0    # tier-weighted imago score saturation point
TICK_SCALE   = 200.0   # tick number saturation point (minor long-run contribution)
_IMAGO_TIER_WEIGHTS: dict[int, int] = {1: 1, 2: 2, 3: 4, 4: 8}

BASE_INFLUENCE       = 0.75   # floor success chance for Whisper / Shape Dream
PUISSANCE_WEIGHT     = 0.15   # max bonus from a fully mature Demiurge
VISIBILITY_WEIGHT    = 0.05   # max bonus from target visibility at 1.0
FRAMING_WEIGHT       = 0.04   # max bonus from perfect framing resonance
PUISSANCE_TIER_BONUS = 0.08   # max success-threshold shift for reliability-tier actions


def _compute_puissance(state: "SimulationState") -> float:
    """Compute Demiurge puissance [0, 1] from lifetime revelation, imago tier score, and tick count."""
    reg = get_imago_registry()
    tier_score = sum(
        _IMAGO_TIER_WEIGHTS.get(node.tier, 0)
        for nid in state.demiurge.unlocked_imagines
        if (node := reg.get_node(nid)) is not None
    )
    raw = (
        state.demiurge.lifetime_revelation / REV_SCALE * 0.50
        + tier_score / IMAGO_SCALE * 0.35
        + state.tick_number / TICK_SCALE * 0.15
    )
    return max(0.0, min(1.0, raw))


def _revelation_adjusted_cost(tier: int, revealed_count: int) -> int:
    base = _REVELATION_BASE_COSTS[tier]
    return math.floor(base * (1.0 + 0.003 * revealed_count))


def _compute_revelation_cap(state: "SimulationState", domain_tag: str) -> float:
    """Sum of adjusted costs for all unrevealed Imagines in the Domain's tree."""
    ireg = get_imago_registry()
    tree = domain_tag.split(":", 1)[1] if ":" in domain_tag else domain_tag
    revealed_count = state.demiurge.revealed_imagines
    unlocked = set(state.demiurge.unlocked_imagines)
    cap = 0.0
    for node in ireg.nodes_for_tree(tree):
        if node.node_id not in unlocked:
            cap += _revelation_adjusted_cost(node.tier, revealed_count)
    return cap


def _compute_universal_expression(state: "SimulationState", domain_tag: str) -> float:
    """
    Normalized domain expression across the whole universe: 0.1–1.0.
    Sums belief strength from civs (scale-weighted, once per world they inhabit) and
    domain_expression from all SignificantLocations, then normalizes against
    _REVELATION_EXPRESSION_FULL.

    Civ beliefs are counted per world presence rather than once per civilization so that
    a civ spanning multiple worlds contributes proportionally to its reach.
    TODO: deprecate this world-presence proxy once Pops are implemented and civ domain
    expression flows through Pop belief aggregation instead.
    """
    total = state.universe.universe_domain_expression.get(domain_tag, 0.1)
    for loc in state.locations.values():
        if not isinstance(loc, SignificantLocation):
            continue
        total += loc.domain_expression.get(domain_tag, 0.0)
        for civ_id in loc.civilization_ids:
            civ = state.civilizations.get(str(civ_id))
            if civ is None:
                continue
            scale_mult = _CIV_SCALE_ESSENCE_MULT.get(
                civ.scale.value if hasattr(civ.scale, "value") else str(civ.scale), 0.1
            )
            total += civ.dominant_beliefs.get(domain_tag, 0.0) * scale_mult
    normalized = total / _REVELATION_EXPRESSION_FULL
    return max(0.1, min(1.0, normalized))


def _resolve_world_id_for(state: "SimulationState", loc_id) -> "Optional[str]":
    """Return the id of the SignificantLocation (world) covering `loc_id`.

    If `loc_id` is already a SignificantLocation, returns it. If it's a
    PopLocation, walks up to its parent. Returns None for anything else
    (system, galaxy, unknown, etc.)."""
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


def _resolve_world_for(state: "SimulationState", loc_id) -> "Optional[SignificantLocation]":
    """Same as `_resolve_world_id_for` but returns the SignificantLocation object."""
    wid = _resolve_world_id_for(state, loc_id)
    return state.worlds.get(wid) if wid else None


def _location_distance_from_core(state: "SimulationState", loc_id) -> int:
    """Return the PopLocation's `distance_from_core` for `loc_id`, or 0 for any
    other location type (world surface, system, galaxy, unknown)."""
    if loc_id is None:
        return 0
    loc = state.locations.get(str(loc_id))
    if isinstance(loc, PopLocation):
        return int(getattr(loc, "distance_from_core", 0) or 0)
    return 0


def _pop_distance_factor(state: "SimulationState", src_loc_id, tgt_loc_id) -> float:
    """Symmetric distance-from-core penalty multiplier between two PopLocations
    on the same world. Compounds `0.7` per step of `|src.distance - tgt.distance|`.
    Same PopLocation → 1.0; surface ↔ orbital (d2) → 0.49; etc."""
    delta = abs(
        _location_distance_from_core(state, src_loc_id)
        - _location_distance_from_core(state, tgt_loc_id)
    )
    return 0.7 ** delta


def _framing_resonance(culture_tags: dict, framing) -> float:
    """How strongly a population's (or mortal's) culture predisposes it to
    read an omen of the given Framing the way it was intended. Sum of the
    framing's per-tag affinity weights × the target's culture-tag strengths,
    clamped to [-1.0, +1.0]. 0.0 when the framing or culture is unknown."""
    fr_key = framing.value if hasattr(framing, "value") else str(framing)
    affinity = _OMEN_FRAMING_AFFINITY.get(fr_key, {})
    if not affinity or not culture_tags:
        return 0.0
    total = sum(
        affinity.get(tag, 0.0) * strength
        for tag, strength in culture_tags.items()
    )
    return max(-1.0, min(1.0, total))


def _compute_local_expression(state: "SimulationState", domain_tag: str, loc_id: "UUID") -> float:
    """
    Normalized domain expression at a single SignificantLocation: 0.0–1.0.
    Used for Proxius Commission Inquiry bonus calculation. Accepts a PopLocation
    id and walks up to its parent world transparently.
    """
    world = _resolve_world_for(state, loc_id)
    if world is None:
        return 0.0
    raw = world.domain_expression.get(domain_tag, 0.0)
    return max(0.0, min(1.0, raw))


# ─────────────────────────────────────────
# POP CONTACT RANK TABLES
# Used by _pop_contact_resistance() for cross-stratum
# and cross-scale resistance calculations.
# ─────────────────────────────────────────

_SOCIAL_CLASS_RANK: dict[str, int] = {
    "wild":       -2,   # No social structure at all (pre-sapient pods, true wilderness).
    "feral":      -1,   # Partially or recently de-civilized — outside class but not pre-social.
    "underclass":  0, "common": 1, "artisan": 2, "merchant": 3,
    "warrior":     4, "priest": 5, "elite":   6,
}

_CIV_SCALE_CONTACT_RANK: dict[str, int] = {
    "non_sentient": -2,  # Reserved for future non-sentient Pops.
    "pre_sapient":  -1,  # Pop with no civilization_id (wild population).
    "nascent":       0, "tribal":  1, "city_state":     2, "regional":     3,
    "continental":   4, "planetary":     5, "interplanetary": 6,
    "interstellar":  7, "intergalactic": 8,
}

# Flat susceptibility modifier applied after all other resistance factors.
# Negative = more open to outside influence; positive = more closed.
_STRATUM_SUSCEPTIBILITY: dict[str, float] = {
    "merchant": -0.12,
    "elite":    -0.06,
    "warrior":  +0.06,
    "priest":   +0.12,
}

# ─────────────────────────────────────────
# TICK CONFIGURATION
# Tunable constants separated from logic.
# ─────────────────────────────────────────

class TickConfig(BaseModel):
    """
    Simulation parameters. Scenarios can override these
    to change pacing — a fast-burn scenario might have
    higher decay rates and more volatile civilization momentum.
    """

    # Time
    tick_duration: float = 1.0
    # One tick = this many universe time units.
    # Scenario defines what a time unit means narratively.

    # Footprint decay
    # Divine traces fade naturally each tick.
    footprint_decay_rate: float = 0.05
    # Subtracted from each footprint category per tick,
    # floor 0.0. Subtle influence fades faster than
    # direct creation — handled by per-category multipliers.
    footprint_decay_multipliers: dict[str, float] = Field(
        default_factory=lambda: {
            "overt_miracles":  1.0,
            "subtle_influence": 1.8,  # Fades faster — it's deniable by design
            "proxius_activity": 0.8,
            "direct_creation":  0.4,  # Reshaping a world doesn't unhappen quickly
        }
    )

    # Concealment degradation
    concealment_decay_rate: float = 0.02
    # concealment_integrity drops this much per tick passively.
    # Spending Essence adds on top of this.

    # Civilization momentum
    # How much a civilization's stats move on their own per tick.
    civ_momentum_rate: float = 0.02
    civ_noise_factor: float = 0.01
    # Small random perturbation each tick — civilizations
    # are not perfectly predictable.

    # Mortal alignment drift
    # Proxii and Heralds slowly drift toward their personal tags
    # and away from their patron's agenda unless directed.
    alignment_drift_rate: float = 0.01

    # Mortal visibility decay
    # Base rate; modulated by prominence: effective_decay = rate * (1.0 - prominence).
    mortal_visibility_decay_rate: float = 0.03

    # Window visibility decay for non-mortal entities
    location_visibility_decay_rate: float = 0.01
    civ_visibility_decay_rate: float = 0.01
    species_visibility_decay_rate: float = 0.01

    # Luminary attention decay
    # Attention naturally falls when nothing interesting happens.
    attention_decay_rate: float = 0.03

    # Passive Proxius footprint
    # Each active Proxius generates this much proxius_activity per tick.
    # Policy-compliant worlds (≤ max_per_world Proxii) contribute at
    # PROXIUS_COMPLIANCE_FACTOR of this rate; excess Proxii contribute at full rate.
    proxius_passive_footprint_rate: float = 0.03

    # Evaluation frequency
    # Not every tick triggers a full Luminary evaluation.
    # Evaluation happens when: attention crosses a threshold,
    # a constraint is breached, or this many ticks have elapsed.
    evaluation_interval: float = 10.0

    # Essence generation weights (tuning targets; adjust after playtesting)
    essence_location_weight: float = 3.0
    # Multiplier for SignificantLocation.domain_expression contributions.
    # Intentionally higher than the max civ scale multiplier so a world's
    # inherent character outweighs any single civilization.

    essence_mortal_weight: float = 0.05
    # Multiplier for NotableMortal.belief_tags contributions.

    essence_claiming_exponent: float = 0.40
    # Exponent applied to total pantheon affinity to derive the Luminary group's
    # claim fraction: lum_fraction = lum_total_aff ** essence_claiming_exponent.
    # At 0.40: aff=0.2→52.5%, aff=0.5→75.8%, aff=0.8→91.5%, aff=0.9→95.9%.
    # Demiurge gets 1 − lum_fraction of any affiliated domain pool.

    luminary_essence_baseline_rate: float = 1.0
    # Expected weighted domain production per effective-affinity-point per tick.
    # Threshold = effective_affinity × baseline_rate × ticks_since_last_eval,
    # where effective_affinity uses diminishing returns (see luminary_essence_decay).

    luminary_essence_decay: float = 0.65
    # Geometric decay applied to each successive domain affinity when computing
    # a Luminary's effective affinity for the satisfaction threshold.
    # Affinities are sorted descending (ties broken alphabetically); each rank i
    # is multiplied by decay**i.  At 0.65: a 3-domain Luminary at [0.7,0.7,0.5]
    # scores 0.700 + 0.455 + 0.211 = 1.366 instead of the raw sum 1.90.

    luminary_essence_recall: float = 0.20
    # Fraction of last-period excess above base threshold that persists as a raised
    # expectation this period.  At 0.20: giving a Luminary 14 units above their base
    # of 6 (excess=8) adds 8×0.20=1.6 to their expectation floor next period.
    # Raised expectations decay by 0.10 per two consecutive shortfall periods.

    # Pop dynamics
    pop_conformity_base: float = 0.005
    # Base rate at which Pops are nudged toward civ.established_beliefs per tick.
    # Scaled by scale_conformity_mult * civ.health.cohesion at runtime.

    pop_visibility_drift_rate: float = 0.02
    # Rate at which Pop.visibility converges toward min(civ.visibility, world.visibility).

    established_drift_base: float = 0.01
    # Base rate at which civ.established_beliefs drifts toward civ.dominant_beliefs per tick.
    # Scaled by civ.health.cohesion at runtime.

    # Cross-Pop contact (passive belief drift between co-located Pops of different civs)
    pop_contact_base_rate: float = 0.005
    cross_civ_contact_factor: float = 0.15
    cross_civ_scale_penalty: float = 0.08
    cross_species_contact_factor: float = 0.50
    cross_stratum_contact_factor: float = 0.70

    # `values:*` culture tags are stubborn — they resist being changed (in either
    # direction). Applied as an extra dampening multiplier on the delta of any
    # POP_CULTURE_SHIFT, MORTAL_CULTURE_SHIFT, or CIV_ESTABLISHED_CULTURE_SHIFT
    # whose field is a `values:*` tag, on top of normal belief_inertia.
    # 0.1 → values shifts happen at 0.9 of the rate of other culture-tag shifts
    # (~1.11× as "stubborn" at mid-zone). Just enough resistance for values to
    # be a touch slower than other culture tags, but not so much that single
    # whispers struggle to accumulate any visible effect.
    values_stubbornness_factor: float = 0.1
    # Core-loc weighting for civ aggregate belief/culture recomputation
    peripheral_pop_belief_weight: float = 0.25
    peripheral_pop_culture_weight: float = 0.25


# ─────────────────────────────────────────
# TICK PHASES
# ─────────────────────────────────────────

class TickPhase(str, Enum):
    PASSIVE_WORLD    = "passive_world"
    ACTION_PROCESSING = "action_processing"
    DOMAIN_PROFILING  = "domain_profiling"
    EVALUATION        = "evaluation"
    DISPOSITION_UPDATE = "disposition_update"
    TERMINAL_CHECK    = "terminal_check"


# ─────────────────────────────────────────
# PASSIVE CHANGES
# What happens without the Demiurge doing anything.
# ─────────────────────────────────────────

class CivilizationMomentum(BaseModel):
    """
    The direction a civilization is naturally trending.
    Set by recent history, current health, and any
    active subtle influence effects.
    Passive simulation moves it along this vector each tick.
    Belief drift is no longer stored here — it is handled by
    Pop-level conformity pressure in the passive phase.
    """
    civilization_id: UUID
    stability_delta:  float = 0.0
    prosperity_delta: float = 0.0
    cohesion_delta:   float = 0.0


class NarrativeEvent(BaseModel):
    """A passive-phase narrative line, tagged with whether its subject is in the Demiurge's Window."""
    text: str
    in_window: bool = True


class PassiveWorldResult(BaseModel):
    """What the passive simulation phase produced."""
    civilization_mutations: list["StateMutation"] = Field(default_factory=list)
    mortal_mutations:       list["StateMutation"] = Field(default_factory=list)
    entity_mutations:       list["StateMutation"] = Field(default_factory=list)
    footprint_mutations:    list["StateMutation"] = Field(default_factory=list)
    concealment_mutations:  list["StateMutation"] = Field(default_factory=list)
    attention_mutations:    list["StateMutation"] = Field(default_factory=list)
    narrative_events:       list["NarrativeEvent"] = Field(default_factory=list)
    # Brief descriptions of notable passive developments
    # e.g. "The Verath Confederation collapsed into civil war"
    #      "Proxius Aldren has begun acting outside their directive"

    # Death mutations held back until after Phase 2 so that a same-tick
    # appoint_proxius action can save a mortal before the death is committed.
    pending_death_mutations:  list["StateMutation"] = Field(default_factory=list)
    pending_death_narratives: list["NarrativeEvent"] = Field(default_factory=list)


# ─────────────────────────────────────────
# ACTION PROCESSING RESULT
# ─────────────────────────────────────────

class ActionProcessingResult(BaseModel):
    """
    Results from processing all queued actions this tick.
    One entry per action instance attempted.
    """
    class ActionEntry(BaseModel):
        action_instance_id: UUID
        outcome:   "ActionOutcome"
        mutations: list["StateMutation"] = Field(default_factory=list)
        narrative: str = ""

    entries: list[ActionEntry] = Field(default_factory=list)


# ─────────────────────────────────────────
# TERMINAL CONDITIONS
# ─────────────────────────────────────────

class TerminalConditionType(str, Enum):
    NONE               = "none"
    VICTORY_COMPLIANCE = "victory_compliance"
    # Met all Luminary demands to scenario end condition

    VICTORY_SUBVERSION = "victory_subversion"
    # Nominally satisfied demands while achieving a
    # contradictory hidden agenda

    VICTORY_OVERTHROW  = "victory_overthrow"
    # Successfully moved against one or more Luminaries

    DEFEAT_CAST_DOWN   = "defeat_cast_down"
    # Demoted to the Underreal

    DEFEAT_REPLACED    = "defeat_replaced"
    # Luminaries appointed a new Demiurge; you watch

    SCENARIO_EXPIRED   = "scenario_expired"
    # Time limit reached — evaluated against final state


class TerminalCheck(BaseModel):
    condition: TerminalConditionType = TerminalConditionType.NONE
    triggered: bool = False
    note: str = ""


# ─────────────────────────────────────────
# TICK RESULT
# The complete output of one tick.
# ─────────────────────────────────────────

class TickResult(BaseModel):
    """
    Everything that happened in one tick.
    The UI reads this, not raw state.
    The event log stores these.
    """
    tick_number: int
    universe_age_before: float
    universe_age_after:  float

    passive_result:     PassiveWorldResult
    action_result:      ActionProcessingResult
    domain_profile:     "UniverseDomainProfile"
    evaluations:        list["LuminaryEvaluation"] = Field(default_factory=list)
    disposition_changes: dict[str, tuple[float, float]] = Field(
        default_factory=dict
    )
    # luminary_id -> (results_new, methods_new)

    agent_narratives:   list[str] = Field(default_factory=list)
    # Proxius REPORT_TO_DEMIURGE entries surfaced this tick

    dialogue_triggers:  list["DialogueTrigger"] = Field(default_factory=list)
    # Unsuppressed triggers only — these go to the player

    terminal: TerminalCheck = Field(default_factory=TerminalCheck)

    essence_claimed_by_domain: dict[str, float] = Field(default_factory=dict)
    # domain tag -> Demiurge's claim this tick

    seed: int = 0
    # RNG seed used this tick — for reproducibility


# ─────────────────────────────────────────
# SIMULATION STATE
# Everything the tick loop needs in one place.
# ─────────────────────────────────────────

class SimulationState(BaseModel):
    """
    The full live state of a running simulation.
    Passed into and returned from each tick.
    Serializable — this is your save file.
    """
    universe:      "Universe"
    demiurge:      "Demiurge"
    essence:       "EssenceStockpile"
    pantheon:      "Pantheon"
    luminaries:    dict[str, "Luminary"]    # str(UUID) -> Luminary
    locations:     dict[str, "Location"]    # str(UUID) -> Location (all spatial entities)
    civilizations: dict[str, "Civilization"]
    pops:          dict[str, "Pop"] = Field(default_factory=dict)
    mortals:       dict[str, "NotableMortal"]
    species:       dict[str, "Species"] = Field(default_factory=dict)

    @property
    def worlds(self) -> "dict[str, SignificantLocation]":
        return {k: v for k, v in self.locations.items() if isinstance(v, SignificantLocation)}

    @property
    def galaxies(self) -> "dict[str, Location]":
        return {k: v for k, v in self.locations.items() if v.location_type == "galaxy"}

    @property
    def systems(self) -> "dict[str, System]":
        return {k: v for k, v in self.locations.items() if isinstance(v, System)}

    # Momentum vectors for each civilization
    # Updated by actions and passive simulation
    civ_momentum: dict[str, CivilizationMomentum] = Field(
        default_factory=dict
    )

    # Queued actions waiting to be processed this tick
    action_queue: list["ActionInstance"] = Field(default_factory=list)

    # Previous domain profile for trajectory calculation
    previous_domain_profile: Optional["UniverseDomainProfile"] = None

    # Per-Luminary attention float (separate from the enum)
    luminary_attention: dict[str, float] = Field(default_factory=dict)
    # str(UUID) -> 0.0-1.0

    # Ticks since last full evaluation per Luminary
    ticks_since_evaluation: dict[str, float] = Field(default_factory=dict)

    tick_number: int = 0
    config: TickConfig = Field(default_factory=TickConfig)

    # Consecutive ticks where essence.actual did not increase.
    # Used to stall passive concealment decay when the Demiurge goes quiet.
    ticks_without_essence_gain: int = 0

    # Persistent actions that auto-execute each tick.
    # Keyed by ActionCategory.value; appended to action_queue before Phase 2.
    # Manually queued actions in the same category take priority and block the ongoing one.
    ongoing_actions: dict[str, OngoingAction] = Field(default_factory=dict)

    # Active events: divine acts that continue to affect the world across multiple ticks.
    # Keyed by str(Event.id). Populated by EVENT_EMITTED mutations; pruned when expired.
    active_events: dict[str, Event] = Field(default_factory=dict)

    # Transient per-tick attention triggers accumulated during Phase 1 event processing.
    # Keyed by str(luminary UUID). Cleared after Phase 4 evaluations. Never persisted.
    pending_attention_triggers: dict[str, list[AttentionTrigger]] = Field(
        default_factory=dict
    )

    # Transient: mortal IDs audited during Phase 2 this tick. Cleared at tick start.
    # Phase 2.5 reads this to suppress REPORT_TO_DEMIURGE when an audit already ran.
    proxii_audited_this_tick: set[str] = Field(default_factory=set, exclude=True)

    # Weighted domain production accumulated per Luminary since their last evaluation.
    # Each tick adds sum(lum.domains[D] × universe_pool[D]) for that Luminary.
    # Keyed by str(luminary UUID). Reset per Luminary at evaluation time. Persisted.
    luminary_production_this_eval: dict[str, float] = Field(default_factory=dict)

    # Cumulative Demiurge Essence claimed per tracked domain (see Demiurge.tracked_essence_domains).
    # Persisted so the player can see long-run domain income.
    domain_essence_claimed: dict[str, float] = Field(default_factory=dict)

    # Per-tick breakdown of Demiurge Essence claims by domain (affiliated only).
    # Overwritten each tick by Phase 1 essence generation; surfaced in the Status tab.
    last_tick_essence_by_domain: dict[str, float] = Field(default_factory=dict)

    # Entity IDs (str(UUID)) that were pinned at scenario creation.
    # At tick 10 Phase 1, all are unpinned and this list is cleared.
    starting_pinned_ids: list[str] = Field(default_factory=list)


# ─────────────────────────────────────────
# TICK LOOP
# ─────────────────────────────────────────

class TickLoop:

    def __init__(self, rng_seed: Optional[int] = None):
        self.rng_seed = rng_seed or random.randint(0, 2**32)
        self._rng = random.Random(self.rng_seed)
        self._action_library = build_action_library()
        self._action_key_by_id: dict[str, str] = {
            str(v.id): k for k, v in self._action_library.items()
        }
        self._overthrow_this_tick: Optional[ActionOutcome] = None
        self._domain_registry: Optional[DomainRegistry] = get_domain_registry()
        self._culture_registry: Optional[CultureRegistry] = get_culture_registry()

    def advance(
        self,
        state: SimulationState,
    ) -> tuple[SimulationState, TickResult]:
        """
        Advance the simulation by one tick.
        Returns updated state and the tick result.
        Pure(-ish) function — state mutations are
        collected as StateMutation lists and applied
        at the end of each phase.
        """
        self._overthrow_this_tick = None
        state.proxii_audited_this_tick = set()
        cfg = state.config
        seed = self._rng.randint(0, 2**32)
        phase_rng = random.Random(seed)

        result = TickResult(
            tick_number=state.tick_number,
            universe_age_before=state.universe.current_age,
            universe_age_after=state.universe.current_age + cfg.tick_duration,
            passive_result=PassiveWorldResult(),
            action_result=ActionProcessingResult(),
            domain_profile=UniverseDomainProfile(
                timestamp=state.universe.current_age
            ),
            seed=seed,
        )

        # ── Puissance recomputation ────────────────────
        state.demiurge.puissance = _compute_puissance(state)

        # ── Phase 1: Passive World ─────────────────────
        passive = self._run_passive_phase(state, cfg, phase_rng)
        result.passive_result = passive

        # ── Active event continuation (Phase 1 extension) ─
        # Runs at offset ≥ 1; tick-0 effects are applied by the action handler directly.
        event_mutations = self._process_active_events(state)
        state = self._apply_mutations(state, event_mutations)

        state = self._apply_passive_mutations(state, passive)
        state = self._prune_weak_beliefs(state)

        # ── Essence generation (Phase 1 tail) ─────────
        essence_gen_mutations, essence_by_domain = self._process_essence_generation(state, cfg)
        state = self._apply_mutations(state, essence_gen_mutations)
        result.essence_claimed_by_domain = essence_by_domain
        state.last_tick_essence_by_domain = dict(essence_by_domain)

        # ── Inject ongoing actions (appended after manual queue) ──────────
        # Manually queued actions in the same category take priority;
        # _validate_and_filter_queue blocks any duplicate-category entry.
        # Map instance.id -> category so we can credit executed_ticks after.
        ongoing_instance_ids: dict[str, str] = {}
        for cat_val, ongoing in list(state.ongoing_actions.items()):
            defn = self._action_library.get(ongoing.action_key)
            if defn is None:
                continue
            instance = ActionInstance(
                action_definition_id=defn.id,
                target_type=ongoing.target_type,
                target_id=ongoing.target_id,
                timestamp=state.universe.current_age,
                demiurge_id=state.demiurge.id,
                proxius_id=ongoing.proxius_id,
                intent=ongoing.intent,
            )
            state.action_queue.append(instance)
            ongoing_instance_ids[str(instance.id)] = cat_val
            ongoing.ticks_active += 1

        # ── Phase 2: Action Processing ─────────────────
        _essence_before = state.essence.actual
        action_result = self._process_action_queue(state, cfg, phase_rng)
        result.action_result = action_result
        state = self._apply_action_mutations(state, action_result)
        state.action_queue = []

        # Credit executed_ticks for ongoing actions that weren't category-blocked.
        # Accepted entries keep their original instance.id; rejected entries get
        # a fresh uuid4(), so membership in this set is unambiguous.
        executed_ids = {str(e.action_instance_id) for e in action_result.entries}
        for iid, cat_val in ongoing_instance_ids.items():
            if iid in executed_ids:
                oa = state.ongoing_actions.get(cat_val)
                if oa:
                    oa.executed_ticks += 1

        # ── Deferred death check ───────────────────────
        # Applied after Phase 2 so a same-tick appoint_proxius saves the mortal.
        # pending_death_mutations and pending_death_narratives are parallel lists.
        for mut, narrative in zip(passive.pending_death_mutations, passive.pending_death_narratives):
            mortal = state.mortals.get(str(mut.target_id))
            if mortal and mortal.role in (MortalRole.PROXIUS, MortalRole.HERALD):
                continue  # appointment this tick saved them; suppress death
            if mortal and mortal.status != MortalStatus.DECEASED:
                mortal.status = MortalStatus.DECEASED
            result.passive_result.narrative_events.append(narrative)  # already a NarrativeEvent

        # Track how long since the Demiurge last gained Essence (for concealment stall)
        if state.essence.actual > _essence_before:
            state.ticks_without_essence_gain = 0
        else:
            state.ticks_without_essence_gain += 1

        # ── Explore Beliefs auto-stop ──────────────────
        # If ongoing Explore Beliefs has filled the pool to cap, cancel it automatically.
        from core.action_core import ActionCategory as _AC
        _sr_key = _AC.SELF_REFINEMENT.value
        if _sr_key in state.ongoing_actions:
            _oa = state.ongoing_actions[_sr_key]
            if _oa.action_key == "explore_beliefs" and isinstance(_oa.intent, ExploreBeliefIntent):
                _tag = _oa.intent.domain_tag
                _cap = _compute_revelation_cap(state, _tag)
                _pool = state.demiurge.revelation_pools.get(_tag, 0.0)
                if _cap == 0.0 or _pool >= _cap:
                    del state.ongoing_actions[_sr_key]
                    _short = _tag.split(":", 1)[1].title() if ":" in _tag else _tag.title()
                    result.passive_result.narrative_events.append(
                        f"[Revelation] Explore Beliefs on {_short} stopped: pool full ({_pool:.2f} / {_cap:.2f}). "
                        f"Use Reveal Imago to internalize Imagines."
                    )

        # ── Phase 2.5: Proxius Agent Actions ───────────
        agent_mutations, agent_narratives = self._resolve_proxius_agents(state, phase_rng)
        state = self._apply_mutations(state, agent_mutations)
        result.agent_narratives.extend(agent_narratives)

        # ── Pop aggregate recomputation ────────────────
        # Recompute Civilization.dominant_beliefs and culture_tags as size-weighted
        # averages of constituent Pop beliefs/tags. Peripheral (non-core) Pops are
        # weighted down so colony Pops don't over-influence the civ aggregate.
        self._recompute_civ_dominant_beliefs(state, cfg)
        self._recompute_civ_culture_tags(state, cfg)

        # ── Phase 3: Domain Profiling ──────────────────
        profile = self._build_domain_profile(state)
        result.domain_profile = profile

        # ── Phase 4: Evaluation ────────────────────────
        evaluations = self._run_evaluations(state, profile, cfg)
        result.evaluations = evaluations
        state.pending_attention_triggers = {}  # consumed by evaluations; clear for next tick

        # ── Phase 5: Disposition Update ───────────────
        state, disposition_changes = self._apply_disposition_deltas(
            state, evaluations
        )
        result.disposition_changes = disposition_changes

        # Collect unsuppressed dialogue triggers
        for ev in evaluations:
            result.dialogue_triggers.extend(
                t for t in ev.dialogue_triggers if not t.suppressed
            )

        # ── Phase 6: Terminal Check ────────────────────
        terminal = self._check_terminal_conditions(state, profile)
        result.terminal = terminal

        # ── Bookkeeping ────────────────────────────────
        state.universe.current_age += cfg.tick_duration
        state.previous_domain_profile = profile
        state.tick_number += 1

        return state, result

    # ─────────────────────────────────────────
    # PHASE 1: PASSIVE WORLD
    # ─────────────────────────────────────────

    def _run_passive_phase(
        self,
        state: SimulationState,
        cfg: TickConfig,
        rng: random.Random,
    ) -> PassiveWorldResult:

        result = PassiveWorldResult()

        # ── Civilization momentum ──────────────────────
        # Scale conformity multipliers: larger civs have stronger institutional pressure.
        _SCALE_CONFORMITY: dict[str, float] = {
            "nascent": 0.2, "tribal": 0.4, "city_state": 0.6,
            "regional": 0.8, "continental": 1.0, "planetary": 1.2,
            "interplanetary": 1.4, "interstellar": 1.6, "intergalactic": 2.0,
        }

        for cid, civ in state.civilizations.items():
            momentum = state.civ_momentum.get(
                cid,
                CivilizationMomentum(civilization_id=UUID(cid))
            )

            # prosperity and cohesion drift from momentum
            for stat, delta in [
                ("prosperity", momentum.prosperity_delta),
                ("cohesion",   momentum.cohesion_delta),
            ]:
                noise = rng.gauss(0, cfg.civ_noise_factor)
                effective_delta = (delta * cfg.civ_momentum_rate) + noise
                current = getattr(civ.health, stat)
                new_val = max(0.0, min(1.0, current + effective_delta))
                if abs(new_val - current) > 0.001:
                    result.civilization_mutations.append(StateMutation(
                        mutation_type=MutationType.CIVILIZATION_STAT,
                        target_id=UUID(cid),
                        field=f"health.{stat}",
                        delta=effective_delta,
                        note=f"{civ.name} {stat} passive drift",
                    ))

            # Stability: nudge toward cosine similarity between dominant and established beliefs.
            # When Pops diverge from the official profile, stability falls.
            if civ.dominant_beliefs and civ.established_beliefs:
                stability_target = self._cosine_similarity(
                    civ.dominant_beliefs, civ.established_beliefs
                )
            else:
                stability_target = civ.health.stability  # no change if no beliefs yet
            stability_delta = (stability_target - civ.health.stability) * cfg.civ_momentum_rate
            noise = rng.gauss(0, cfg.civ_noise_factor)
            if abs(stability_delta + noise) > 0.001:
                result.civilization_mutations.append(StateMutation(
                    mutation_type=MutationType.CIVILIZATION_STAT,
                    target_id=UUID(cid),
                    field="health.stability",
                    delta=stability_delta + noise,
                    note=f"{civ.name} stability from belief alignment",
                ))

            # established_beliefs drifts toward dominant_beliefs (institutional lag).
            established_rate = cfg.established_drift_base * civ.health.cohesion
            for tag in set(civ.dominant_beliefs) | set(civ.established_beliefs):
                dom_val = civ.dominant_beliefs.get(tag, 0.0)
                est_val = civ.established_beliefs.get(tag, 0.0)
                delta = (dom_val - est_val) * established_rate
                if abs(delta) > 0.0001:
                    result.civilization_mutations.append(StateMutation(
                        mutation_type=MutationType.CIV_ESTABLISHED_SHIFT,
                        target_id=UUID(cid),
                        field=tag,
                        new_value=tag,
                        delta=delta,
                        note=f"{civ.name} established belief drift: {tag}",
                    ))

            # established_culture_tags drifts toward culture_tags (same institutional lag).
            for tag in set(civ.culture_tags) | set(civ.established_culture_tags):
                dom_val = civ.culture_tags.get(tag, 0.0)
                est_val = civ.established_culture_tags.get(tag, 0.0)
                delta = (dom_val - est_val) * established_rate
                if abs(delta) > 0.0001:
                    result.civilization_mutations.append(StateMutation(
                        mutation_type=MutationType.CIV_ESTABLISHED_CULTURE_SHIFT,
                        target_id=UUID(cid),
                        field=tag,
                        new_value=tag,
                        delta=delta,
                        note=f"{civ.name} established culture drift: {tag}",
                    ))

            # Narrative event if stability crosses a threshold
            projected_stability = max(0.0, min(1.0, civ.health.stability + stability_delta))
            if projected_stability < 0.2 and civ.health.stability >= 0.2:
                result.narrative_events.append(NarrativeEvent(
                    text=f"{civ.name} has entered a state of critical instability.",
                    in_window=is_in_window(civ),
                ))
            elif projected_stability > 0.8 and civ.health.stability <= 0.8:
                result.narrative_events.append(NarrativeEvent(
                    text=f"{civ.name} has achieved remarkable stability.",
                    in_window=is_in_window(civ),
                ))

        # ── Civ → Pop conformity pressure ──────────────
        for pop in state.pops.values():
            if not pop.civilization_id:
                continue
            civ = state.civilizations.get(str(pop.civilization_id))
            if civ is None or not civ.established_beliefs:
                continue
            scale_key = civ.scale.value if hasattr(civ.scale, "value") else str(civ.scale)
            conformity_rate = (
                cfg.pop_conformity_base
                * _SCALE_CONFORMITY.get(scale_key, 1.0)
                * civ.health.cohesion
            )
            # Actively preached Pops (goal targets) resist institutional pull at half rate
            if pop.preaching_imago_id is not None:
                conformity_rate *= 0.5
            # Stratum susceptibility: priests and warriors resist institutional pull;
            # merchants are more responsive to it
            pop_class = pop.social_class.value if hasattr(pop.social_class, "value") else str(pop.social_class or "")
            susceptibility = _STRATUM_SUSCEPTIBILITY.get(pop_class, 0.0)
            conformity_rate *= max(0.1, 1.0 + susceptibility)
            for tag in set(civ.established_beliefs) | set(pop.dominant_beliefs):
                est_val = civ.established_beliefs.get(tag, 0.0)
                pop_val = pop.dominant_beliefs.get(tag, 0.0)
                delta = (est_val - pop_val) * conformity_rate
                if abs(delta) > 0.0001:
                    result.civilization_mutations.append(StateMutation(
                        mutation_type=MutationType.POP_BELIEF_SHIFT,
                        target_id=pop.id,
                        field=tag,
                        new_value=tag,
                        delta=delta,
                        note=f"{civ.name} conformity pressure on Pop ({tag})",
                    ))

            # Culture conformity: nudge Pop culture_tags toward civ.established_culture_tags
            if civ.established_culture_tags:
                for tag in set(civ.established_culture_tags) | set(pop.culture_tags):
                    est_val = civ.established_culture_tags.get(tag, 0.0)
                    pop_val = pop.culture_tags.get(tag, 0.0)
                    delta = (est_val - pop_val) * conformity_rate
                    if abs(delta) > 0.0001:
                        result.civilization_mutations.append(StateMutation(
                            mutation_type=MutationType.POP_CULTURE_SHIFT,
                            target_id=pop.id,
                            field=tag,
                            delta=delta,
                            note=f"{civ.name} culture conformity on Pop ({tag})",
                        ))

        # ── Rider trait → culture tag attrition ───────
        # Culture tags that conflict with a Pop's active rider traits decay passively.
        # Positively synergistic traits decay more slowly; negatively synergistic ones faster.
        creg = self._culture_registry
        if creg is not None:
            for pop in state.pops.values():
                if not pop.rider_traits:
                    continue
                for ctag, cstrength in list(pop.culture_tags.items()):
                    if cstrength <= 0.0:
                        continue
                    total_decay = 0.0
                    for rtag, rstrength in pop.rider_traits.items():
                        syn = creg.synergy(rtag, ctag)
                        # syn=-1 → mult=2.0; syn=0 → mult=1.0; syn=+1 → mult=0.0
                        mult = max(0.0, 1.0 - syn)
                        total_decay += RIDER_ATTRITION_BASE * rstrength * mult
                    if total_decay > 1e-5:
                        result.civilization_mutations.append(StateMutation(
                            mutation_type=MutationType.POP_CULTURE_SHIFT,
                            target_id=pop.id,
                            field=ctag,
                            delta=-total_decay,
                            note=f"Rider trait attrition on {ctag}",
                        ))

        # ── Mortal alignment drift ─────────────────────
        dreg = get_domain_registry()
        for mid, mortal in state.mortals.items():
            if mortal.status != "active":
                continue

            # Alignment drifts toward each mortal's computed natural base
            drift_toward = compute_mortal_alignment_base(
                mortal, state.demiurge.affiliated_domains, dreg
            )
            _rate = cfg.alignment_drift_rate * (0.5 if mortal.role == MortalRole.PROXIUS else 1.0)
            drift = (drift_toward - mortal.alignment) * _rate
            _align_cap = 1.0 if mortal.role == MortalRole.PROXIUS else 0.9
            new_alignment = max(0.01, min(_align_cap, mortal.alignment + drift))

            if abs(new_alignment - mortal.alignment) > 0.001:
                result.mortal_mutations.append(StateMutation(
                    mutation_type=MutationType.MORTAL_ALIGNMENT,
                    target_id=UUID(mid),
                    field="alignment",
                    delta=drift,
                    note=f"{mortal.name} alignment drift",
                ))

            # Flag a Proxius going significantly rogue
            if (mortal.role == "proxius"
                    and mortal.alignment < 0.4
                    and (mortal.alignment - drift) >= 0.4):
                result.narrative_events.append(NarrativeEvent(
                    text=f"Proxius {mortal.name} appears to be pursuing "
                         f"their own agenda more than yours.",
                    in_window=is_in_window(mortal),
                ))

        # ── Mortal aging ───────────────────────────────
        for mid, mortal in state.mortals.items():
            if mortal.status == MortalStatus.DECEASED:
                continue

            # chrono_age always increments
            result.mortal_mutations.append(StateMutation(
                mutation_type=MutationType.MORTAL_AGE,
                target_id=UUID(mid),
                field="chrono_age",
                delta=cfg.tick_duration,
                note=f"{mortal.name} chrono_age +{cfg.tick_duration}",
            ))

            # bio_age frozen for active Proxii/Heralds, slow for dormant Proxii
            if (mortal.status == MortalStatus.ACTIVE
                    and mortal.role in (MortalRole.PROXIUS, MortalRole.HERALD)):
                bio_delta = 0.0
            elif (mortal.status == MortalStatus.DORMANT
                    and mortal.role == MortalRole.PROXIUS):
                bio_delta = cfg.tick_duration / 5.0
            else:
                bio_delta = cfg.tick_duration

            if bio_delta > 0.0:
                new_bio_age = mortal.bio_age + bio_delta
                result.mortal_mutations.append(StateMutation(
                    mutation_type=MutationType.MORTAL_AGE,
                    target_id=UUID(mid),
                    field="bio_age",
                    delta=bio_delta,
                    note=f"{mortal.name} bio_age +{bio_delta}",
                ))

                # Death check fires once bio_age enters the species lifespan range
                sp = state.species.get(str(mortal.species_id)) if mortal.species_id else None
                if sp and new_bio_age >= sp.lifespan_min:
                    range_width = max(1.0, sp.lifespan_max - sp.lifespan_min)
                    progress = min(1.0, (new_bio_age - sp.lifespan_min) / range_width)
                    death_prob = progress * 0.3  # peaks at 30%/tick at lifespan_max
                    if rng.random() < death_prob:
                        result.pending_death_mutations.append(StateMutation(
                            mutation_type=MutationType.MORTAL_STATUS,
                            target_id=UUID(mid),
                            field="status",
                            new_value=MortalStatus.DECEASED.value,
                            note=f"{mortal.name} died of natural causes (bio_age {new_bio_age:.0f})",
                        ))
                        result.pending_death_narratives.append(NarrativeEvent(
                            text=f"{mortal.name} has died of natural causes at age {new_bio_age:.0f}.",
                            in_window=is_in_window(mortal),
                        ))

        # ── Pop affiliation age-out for divine appointments ───
        # An appointed mortal loses their Pop bond once their wall-clock tenure
        # (ticks × tick_duration, converted to UTUs) exceeds their species' lifespan_min.
        # They've outlived their cohort and no longer have common ground with them.
        for mid, mortal in state.mortals.items():
            if mortal.status == MortalStatus.DECEASED or mortal.pop_id is None:
                continue
            first_tick = _first_appointed_tick(mortal)
            if first_tick is None:
                continue
            tenure_utu = (state.tick_number - first_tick) * cfg.tick_duration
            sp = state.species.get(str(mortal.species_id)) if mortal.species_id else None
            if sp and tenure_utu >= sp.lifespan_min:
                result.entity_mutations.append(StateMutation(
                    mutation_type=MutationType.MORTAL_POP_AGED_OUT,
                    target_id=UUID(mid),
                    field="status",
                    note=f"{mortal.name} has aged beyond their origin community",
                ))
                result.narrative_events.append(NarrativeEvent(
                    text=f"{mortal.name} has lived so long beyond their origin community "
                         f"that the bond no longer holds — they stand apart from the people they were born among.",
                    in_window=is_in_window(mortal),
                ))

        # ── Mortal visibility decay ────────────────────
        for mid, mortal in state.mortals.items():
            if mortal.status == MortalStatus.DECEASED:
                continue
            if mortal.pinned:
                continue
            if mortal.visibility <= 0.0:
                continue
            effective_rate = cfg.mortal_visibility_decay_rate * (1.0 - mortal.prominence)
            new_vis = max(0.0, mortal.visibility - effective_rate)
            if mortal.visibility - new_vis > 0.0001:
                result.mortal_mutations.append(StateMutation(
                    mutation_type=MutationType.MORTAL_VISIBILITY,
                    target_id=UUID(mid),
                    field="visibility",
                    delta=-(mortal.visibility - new_vis),
                    note=f"{mortal.name} visibility decay",
                ))

        # ── Starting-pin expiry ────────────────────────
        # tick_number is pre-increment here; 9 means "this is the 10th tick processing".
        if state.tick_number == 9 and state.starting_pinned_ids:
            for eid in state.starting_pinned_ids:
                entity = (
                    state.mortals.get(eid)
                    or state.locations.get(eid)
                    or state.civilizations.get(eid)
                    or state.species.get(eid)
                )
                if entity is not None:
                    entity.pinned = False
            state.starting_pinned_ids.clear()

        # ── Location visibility decay ──────────────────
        for lid, loc in state.locations.items():
            if getattr(loc, "pinned", False) or loc.visibility <= 0.0:
                continue
            new_vis = max(0.0, loc.visibility - cfg.location_visibility_decay_rate)
            if loc.visibility - new_vis > 0.0001:
                result.entity_mutations.append(StateMutation(
                    mutation_type=MutationType.ENTITY_VISIBILITY,
                    target_id=UUID(lid),
                    field="visibility",
                    delta=-(loc.visibility - new_vis),
                    note=f"{loc.name} visibility decay",
                ))

        # ── Civilization visibility decay ──────────────
        for cid, civ in state.civilizations.items():
            if civ.pinned or civ.visibility <= 0.0:
                continue
            new_vis = max(0.0, civ.visibility - cfg.civ_visibility_decay_rate)
            if civ.visibility - new_vis > 0.0001:
                result.entity_mutations.append(StateMutation(
                    mutation_type=MutationType.ENTITY_VISIBILITY,
                    target_id=UUID(cid),
                    field="visibility",
                    delta=-(civ.visibility - new_vis),
                    note=f"{civ.name} visibility decay",
                ))

        # ── Species visibility decay ───────────────────
        for sid, sp in state.species.items():
            if sp.pinned or sp.visibility <= 0.0:
                continue
            new_vis = max(0.0, sp.visibility - cfg.species_visibility_decay_rate)
            if sp.visibility - new_vis > 0.0001:
                result.entity_mutations.append(StateMutation(
                    mutation_type=MutationType.ENTITY_VISIBILITY,
                    target_id=UUID(sid),
                    field="visibility",
                    delta=-(sp.visibility - new_vis),
                    note=f"{sp.name} visibility decay",
                ))

        # ── Pop visibility drift ───────────────────────
        # Pop visibility converges toward min(civ.visibility, world.visibility).
        # If the civilization or world goes dark, so do its Pops.
        _pop_loc_to_world: dict[str, str] = {}
        for wid, world in state.worlds.items():
            for cid in world.child_ids:
                loc = state.locations.get(str(cid))
                if loc and isinstance(loc, PopLocation):
                    _pop_loc_to_world[str(cid)] = wid

        for pid, pop in state.pops.items():
            if pop.pinned:
                continue
            civ = state.civilizations.get(str(pop.civilization_id)) if pop.civilization_id else None
            civ_vis = civ.visibility if civ else 0.0
            wid = _pop_loc_to_world.get(str(pop.current_location), str(pop.current_location))
            world_obj = state.worlds.get(wid)
            world_vis = world_obj.visibility if world_obj else 0.0
            baseline = min(civ_vis, world_vis)
            delta = (baseline - pop.visibility) * cfg.pop_visibility_drift_rate
            if abs(delta) > 0.0001:
                result.entity_mutations.append(StateMutation(
                    mutation_type=MutationType.POP_VISIBILITY,
                    target_id=UUID(pid),
                    field="visibility",
                    delta=delta,
                    note="Pop visibility drift",
                ))

        # ── Passive Proxius footprint accumulation ────────
        # Active Proxii generate proxius_activity each tick.
        # Policy-compliant worlds contribute at PROXIUS_COMPLIANCE_FACTOR of
        # the base rate; excess Proxii on a world contribute at full rate.
        if cfg.proxius_passive_footprint_rate > 0.0:
            policy = state.universe.rules.proxii_policy
            proxii_by_world: dict[str, int] = {}
            for mortal in state.mortals.values():
                if (mortal.role == MortalRole.PROXIUS
                        and mortal.status == MortalStatus.ACTIVE):
                    wid = _resolve_world_id_for(state, mortal.current_location)
                    if wid is None:
                        continue
                    proxii_by_world[wid] = proxii_by_world.get(wid, 0) + 1

            total_passive_fp = 0.0
            for count in proxii_by_world.values():
                if policy.max_per_world is not None:
                    compliant = min(count, policy.max_per_world)
                    excess    = max(0, count - policy.max_per_world)
                else:
                    compliant = count
                    excess    = 0
                total_passive_fp += (
                    compliant * cfg.proxius_passive_footprint_rate * PROXIUS_COMPLIANCE_FACTOR
                    + excess  * cfg.proxius_passive_footprint_rate
                )

            if total_passive_fp > 0.001:
                n_active = sum(proxii_by_world.values())
                result.footprint_mutations.append(StateMutation(
                    mutation_type=MutationType.FOOTPRINT_CHANGE,
                    target_id=state.demiurge.id,
                    field="proxius_activity",
                    delta=total_passive_fp,
                    note=f"Passive Proxius activity ({n_active} active)",
                ))

        # ── Footprint decay ────────────────────────────
        fp = state.demiurge.footprint
        for category, multiplier in cfg.footprint_decay_multipliers.items():
            current = getattr(fp, category)
            decay = cfg.footprint_decay_rate * multiplier
            new_val = max(0.0, current - decay)
            if abs(new_val - current) > 0.0001:
                result.footprint_mutations.append(StateMutation(
                    mutation_type=MutationType.FOOTPRINT_CHANGE,
                    target_id=state.demiurge.id,
                    field=category,
                    delta=-(current - new_val),
                    note=f"Footprint decay: {category}",
                ))

        # World-level footprint decay (same logic)
        for wid, world in state.worlds.items():
            for category, multiplier in cfg.footprint_decay_multipliers.items():
                current = getattr(world.local_footprint, category)
                decay = cfg.footprint_decay_rate * multiplier
                new_val = max(0.0, current - decay)
                if abs(new_val - current) > 0.0001:
                    result.footprint_mutations.append(StateMutation(
                        mutation_type=MutationType.FOOTPRINT_CHANGE,
                        target_id=UUID(wid),
                        field=f"local_footprint.{category}",
                        delta=-(current - new_val),
                        note=f"World footprint decay: {category}",
                    ))

        # ── Concealment degradation ────────────────────
        # Decay stalls when the Demiurge has gone quiet on Essence for several ticks.
        # 3+ quiet ticks → half rate; 6+ quiet ticks → full stall.
        if state.essence.concealment_integrity > 0.0:
            quiet = state.ticks_without_essence_gain
            if quiet >= 6:
                effective_decay = 0.0
            elif quiet >= 3:
                effective_decay = cfg.concealment_decay_rate * 0.5
            else:
                effective_decay = cfg.concealment_decay_rate

            if effective_decay > 0.0:
                new_integrity = max(
                    0.0,
                    state.essence.concealment_integrity - effective_decay
                )
                result.concealment_mutations.append(StateMutation(
                    mutation_type=MutationType.CONCEALMENT_CHANGE,
                    target_id=state.demiurge.id,
                    field="concealment_integrity",
                    delta=-(state.essence.concealment_integrity - new_integrity),
                    note="Passive concealment degradation",
                ))

        # ── Luminary attention decay ───────────────────
        for lid in state.luminaries:
            current_att = state.luminary_attention.get(lid, 0.2)
            new_att = max(0.0, current_att - cfg.attention_decay_rate)
            if abs(new_att - current_att) > 0.0001:
                result.attention_mutations.append(StateMutation(
                    mutation_type=MutationType.FOOTPRINT_CHANGE,
                    # Reusing mutation type; a dedicated ATTENTION_CHANGE
                    # type can be added later
                    target_id=UUID(lid),
                    field="attention",
                    delta=-(current_att - new_att),
                    note="Luminary attention decay",
                ))

        # ── Cross-Pop contact (passive cross-civ belief drift) ─────
        # Co-located Pops of different civs slowly drift toward each other's beliefs.
        # Resistance is applied for cross-civ scale gap, cross-species, and
        # cross-stratum. Omens are unaffected.
        for m in self._process_pop_contact(state, cfg):
            result.civilization_mutations.append(m)

        # ── Pop splinter check ─────────────────────────
        # A Pop splits when its beliefs diverge too far from civ.established_beliefs.
        # Runs after conformity pressure so we react to this tick's final belief state.
        for pid, pop in list(state.pops.items()):
            if pop.size_fractional < SPLINTER_MIN_SIZE:
                continue
            if pop.child_pop_ids:
                continue  # already has children; prevent cascade in one tick
            if not pop.civilization_id:
                continue
            civ = state.civilizations.get(str(pop.civilization_id))
            if civ is None or not civ.established_beliefs:
                continue
            divergence = 1.0 - self._cosine_similarity(pop.dominant_beliefs, civ.established_beliefs)
            if divergence < SPLINTER_DIVERGENCE_THRESHOLD:
                continue

            # Identify the primary divergent domain for the narrative log
            top_div_tag = max(
                (t for t in pop.dominant_beliefs),
                key=lambda t: abs(
                    pop.dominant_beliefs.get(t, 0.0)
                    - civ.established_beliefs.get(t, 0.0)
                ),
                default=None,
            )
            short_tag = top_div_tag.split(":", 1)[-1] if top_div_tag else "unknown"
            class_label = pop.stratum.title() if pop.stratum else "Pop"

            splinter = Pop(
                id=uuid4(),
                civilization_id=pop.civilization_id,
                species_id=pop.species_id,
                social_class=pop.social_class,
                wild_stratum=pop.wild_stratum,
                current_location=pop.current_location,
                size_fractional=pop.size_fractional * SPLINTER_FRACTION,
                dominant_beliefs=dict(pop.dominant_beliefs),
                culture_tags=dict(pop.culture_tags),
                rider_traits=dict(pop.rider_traits),
                parent_pop_id=pop.id,
                visibility=max(0.0, pop.visibility * 0.5),
                pinned=False,
            )
            note = (
                f"[Pop splinter] A faction within {civ.name}'s {class_label} class "
                f"broke away over {short_tag} (divergence {divergence:.2f})."
            )
            result.entity_mutations.append(StateMutation(
                mutation_type=MutationType.POP_SPLINTER,
                target_id=pop.id,
                field="pops",
                new_value=splinter,
                note=note,
            ))
            result.narrative_events.append(NarrativeEvent(
                text=note,
                in_window=is_in_window(pop) or is_in_window(civ),
            ))

        return result

    @staticmethod
    def _belief_match(pop_beliefs: dict[str, float], civ_established: dict[str, float]) -> float:
        """
        Weighted overlap: fraction of the civilization's established belief expression
        that this Pop's beliefs cover. Returns 0.0–1.0.
        Used to scale the civ scope bonus on Pop Essence contribution.
        """
        if not civ_established:
            return 1.0
        numerator = sum(
            min(pop_beliefs.get(tag, 0.0), strength)
            for tag, strength in civ_established.items()
        )
        denominator = sum(civ_established.values())
        return numerator / denominator if denominator > 0.0 else 0.0

    def _process_essence_generation(
        self,
        state: SimulationState,
        cfg: TickConfig,
    ) -> tuple[list["StateMutation"], dict[str, float]]:
        """
        Compute per-domain world pools → universe pool → claiming fractions.
        Adds Demiurge's share to essence.actual (no apparent/concealment impact).
        Accumulates each Luminary's share into state.luminary_essence_this_eval.
        Returns (ESSENCE_CHANGE mutations, per-domain claim amounts).

        Belief contributions come from Pop.dominant_beliefs, scaled by a scope
        bonus proportional to how well the Pop's beliefs match the civilization's
        established_beliefs (weighted overlap). This replaces the old civ-level
        dominant_beliefs * scale_mult approach.
        """
        universe_pool: dict[str, float] = {}

        # Build index: world_id → parent-world for PopLocations.
        # Pops live in PopLocations; we need to find which SignificantLocation world
        # each PopLocation belongs to so we can assign Pop contributions to the right world pool.
        pop_loc_to_world: dict[str, str] = {}
        for wid, world in state.worlds.items():
            for cid in world.child_ids:
                loc = state.locations.get(str(cid))
                if loc and isinstance(loc, PopLocation):
                    pop_loc_to_world[str(cid)] = wid

        # Build index: world_id → list of mortals currently there
        mortals_by_world: dict[str, list["NotableMortal"]] = {}
        for mortal in state.mortals.values():
            if mortal.status == "active":
                wid = _resolve_world_id_for(state, mortal.current_location)
                if wid is not None:
                    mortals_by_world.setdefault(wid, []).append(mortal)

        # World location weight: distribute each world's domain_expression contribution
        # evenly rather than per-Pop (location is an inherent property of the world).
        for wid, world in state.worlds.items():
            for tag, strength in world.domain_expression.items():
                amount = strength * cfg.essence_location_weight
                if amount > 0.0:
                    universe_pool[tag] = universe_pool.get(tag, 0.0) + amount

        # Pre-compute per-civ total Pop size so splitting a civ into multiple Pops
        # doesn't inflate its total essence output (contributions are size-weighted).
        civ_total_size: dict[str, float] = {}
        for pop in state.pops.values():
            if pop.civilization_id:
                cid = str(pop.civilization_id)
                civ_total_size[cid] = civ_total_size.get(cid, 0.0) + pop.size_fractional

        # Pop contributions: belief strength * size_weight * scope bonus
        for pop in state.pops.values():
            if not pop.dominant_beliefs:
                continue
            civ = state.civilizations.get(str(pop.civilization_id)) if pop.civilization_id else None
            cid = str(pop.civilization_id) if pop.civilization_id else None

            if civ is not None:
                scale_mult = _CIV_SCALE_ESSENCE_MULT.get(
                    civ.scale.value if hasattr(civ.scale, "value") else str(civ.scale), 0.1
                )
                match = self._belief_match(pop.dominant_beliefs, civ.established_beliefs)
                total_sz = civ_total_size.get(cid, pop.size_fractional)
                size_weight = pop.size_fractional / total_sz if total_sz > 0.0 else 1.0
            else:
                scale_mult = 0.05
                match = 0.0
                size_weight = 1.0

            for tag, strength in pop.dominant_beliefs.items():
                # Contribution weighted by Pop's share of civ total size so that
                # splitting one Pop into many doesn't multiply total essence output.
                amount = strength * size_weight * (1.0 + (scale_mult - 1.0) * match)
                if amount > 0.0:
                    universe_pool[tag] = universe_pool.get(tag, 0.0) + amount

        # Mortal contributions (unchanged)
        for mortal in state.mortals.values():
            if mortal.status != "active":
                continue
            for tag, strength in mortal.belief_tags.items():
                amount = strength * cfg.essence_mortal_weight
                if amount > 0.0:
                    universe_pool[tag] = universe_pool.get(tag, 0.0) + amount

        if not universe_pool:
            return []

        luminaries = list(state.luminaries.values())
        demiurge_affiliated = set(state.demiurge.affiliated_domains)
        tracked = set(state.demiurge.tracked_essence_domains)
        EXP = cfg.essence_claiming_exponent

        mutations: list[StateMutation] = []
        demiurge_total_claim = 0.0
        domain_claim_breakdown: dict[str, float] = {}

        for tag, pool in universe_pool.items():
            if pool <= 0.0:
                continue

            lum_total_aff = min(
                0.9, sum(lum.domains.get(tag, 0.0) for lum in luminaries)
            )

            # Accumulate weighted production for each Luminary that has affinity here.
            # This is the satisfaction metric: how much of their domain is being expressed.
            for lum in luminaries:
                lum_aff = min(0.8, lum.domains.get(tag, 0.0))
                if lum_aff <= 0.0:
                    continue
                lid = str(lum.id)
                state.luminary_production_this_eval[lid] = (
                    state.luminary_production_this_eval.get(lid, 0.0) + lum_aff * pool
                )

            if lum_total_aff == 0.0:
                # No Luminary claims this domain — Demiurge gets 100% if affiliated
                if tag in demiurge_affiliated:
                    demiurge_total_claim += pool
                    domain_claim_breakdown[tag] = domain_claim_breakdown.get(tag, 0.0) + pool
                    if tag in tracked:
                        state.domain_essence_claimed[tag] = (
                            state.domain_essence_claimed.get(tag, 0.0) + pool
                        )
                # else sinks to Underreal
                continue

            # lum_fraction = lum_total_aff ** EXP (concave curve; see TickConfig comment)
            lum_fraction = lum_total_aff ** EXP
            dem_fraction = 1.0 - lum_fraction

            dem_claim = pool * dem_fraction if tag in demiurge_affiliated else 0.0
            demiurge_total_claim += dem_claim
            if dem_claim > 0.0:
                domain_claim_breakdown[tag] = domain_claim_breakdown.get(tag, 0.0) + dem_claim
            if tag in tracked and dem_claim > 0.0:
                state.domain_essence_claimed[tag] = (
                    state.domain_essence_claimed.get(tag, 0.0) + dem_claim
                )

        if demiurge_total_claim > 0.001:
            mutations.append(StateMutation(
                mutation_type=MutationType.ESSENCE_CHANGE,
                target_id=state.demiurge.id,
                field="actual",
                delta=demiurge_total_claim,
                note=f"Domain-based Essence claim (+{demiurge_total_claim:.3f})",
            ))

        return mutations, domain_claim_breakdown

    def _apply_passive_mutations(
        self,
        state: SimulationState,
        passive: PassiveWorldResult,
    ) -> SimulationState:

        all_mutations = (
            passive.civilization_mutations
            + passive.mortal_mutations
            + passive.entity_mutations
            + passive.footprint_mutations
            + passive.concealment_mutations
            + passive.attention_mutations
        )
        return self._apply_mutations(state, all_mutations)

    # ─────────────────────────────────────────
    # PHASE 2: ACTION PROCESSING
    # ─────────────────────────────────────────

    def _validate_and_filter_queue(
        self,
        queue: list["ActionInstance"],
    ) -> tuple[list["ActionInstance"], list[str]]:
        """
        Enforce declarative action queue constraints. Returns (filtered_queue, rejection_messages).

        Rule: at most one action per ActionCategory per tick.
        """
        accepted: list[ActionInstance] = []
        rejected: list[str] = []
        seen_categories: dict[str, str] = {}  # category value -> name of action that claimed it

        for instance in queue:
            key = self._action_key_by_id.get(str(instance.action_definition_id))
            defn = self._action_library.get(key) if key else None
            if defn is None:
                continue

            cat = defn.category.value
            if cat in seen_categories:
                rejected.append(
                    f"{defn.name} blocked: a {cat.replace('_', ' ')} action "
                    f"({seen_categories[cat]}) is already queued this tick."
                )
                continue

            seen_categories[cat] = defn.name
            accepted.append(instance)

        return accepted, rejected

    def _process_action_queue(
        self,
        state: SimulationState,
        cfg: TickConfig,
        rng: random.Random,
    ) -> ActionProcessingResult:

        result = ActionProcessingResult()

        validated_queue, rejections = self._validate_and_filter_queue(state.action_queue)
        for msg in rejections:
            result.entries.append(ActionProcessingResult.ActionEntry(
                action_instance_id=uuid4(),
                outcome=ActionOutcome.FAILURE,
                mutations=[],
                narrative=msg,
            ))

        for instance in validated_queue:
            defn_id = str(instance.action_definition_id)
            defn = next(
                (v for v in self._action_library.values()
                 if str(v.id) == defn_id),
                None
            )
            if defn is None:
                continue

            outcome, mutations, narrative = self._execute_action(
                instance, defn, state, rng
            )

            if defn.name == "Move Against Luminary":
                self._overthrow_this_tick = outcome

            result.entries.append(
                ActionProcessingResult.ActionEntry(
                    action_instance_id=instance.id,
                    outcome=outcome,
                    mutations=mutations,
                    narrative=narrative,
                )
            )

        return result

    def _execute_action(
        self,
        instance: "ActionInstance",
        defn: "ActionDefinition",
        state: SimulationState,
        rng: random.Random,
    ) -> tuple["ActionOutcome", list["StateMutation"], str]:

        mutations: list[StateMutation] = []

        # ── Reliability roll ───────────────────────────
        if isinstance(instance.intent, (WhisperIntent, ShapeDreamIntent)):
            outcome = self._roll_influence(instance, state, rng)
        else:
            outcome = self._roll_reliability(defn.reliability, rng, state.demiurge.puissance)
        if outcome == ActionOutcome.FAILURE:
            return outcome, [], f"{defn.name} failed to produce any effect."

        partial = (outcome == ActionOutcome.PARTIAL)

        # ── Footprint application ──────────────────────
        scale = 0.5 if partial else 1.0

        for category in ["overt_miracles", "subtle_influence",
                          "proxius_activity", "direct_creation"]:
            cost = getattr(defn.footprint_cost, category) * scale
            if cost > 0.0:
                # Universe-wide footprint
                mutations.append(StateMutation(
                    mutation_type=MutationType.FOOTPRINT_CHANGE,
                    target_id=state.demiurge.id,
                    field=category,
                    delta=cost,
                    note=f"{defn.name}: footprint {category}",
                ))
                # World-level footprint if target is a world/civ/mortal
                world_id = self._resolve_world_id(instance, state)
                if world_id:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.FOOTPRINT_CHANGE,
                        target_id=world_id,
                        field=f"local_footprint.{category}",
                        delta=cost,
                        note=f"{defn.name}: local footprint {category}",
                    ))

        # ── Essence handling ───────────────────────────
        # Positive cost = spending; negative cost (harvests) are handled
        # entirely by the EssenceHarvestIntent handler to avoid double-counting.
        if defn.essence_cost > 0.0:
            effective_cost = defn.essence_cost * scale
            mutations.append(StateMutation(
                mutation_type=MutationType.ESSENCE_CHANGE,
                target_id=state.demiurge.id,
                field="actual",
                delta=-effective_cost,
                note=f"{defn.name}: essence spend",
            ))
            if defn.concealment_impact > 0.0:
                apparent_leak = defn.concealment_impact * scale
                mutations.append(StateMutation(
                    mutation_type=MutationType.CONCEALMENT_CHANGE,
                    target_id=state.demiurge.id,
                    field="apparent",
                    delta=apparent_leak,
                    note=f"{defn.name}: concealment leak",
                ))

        # ── Attention spike for high-footprint actions ─
        fp_total = defn.footprint_cost.total() * scale
        if fp_total > 0.3:
            for lid in state.luminaries:
                current = state.luminary_attention.get(lid, 0.2)
                spike = fp_total * 0.3
                mutations.append(StateMutation(
                    mutation_type=MutationType.FOOTPRINT_CHANGE,
                    target_id=UUID(lid),
                    field="attention",
                    delta=spike,
                    note=f"Attention spike from {defn.name}",
                ))

        # ── Intent-specific mutations ──────────────────
        intent_mutations, narrative = self._resolve_intent_mutations(
            instance, defn, state, outcome, rng
        )
        mutations.extend(intent_mutations)

        # ── Visibility refresh for mortal-targeted actions ─
        if instance.target_type == TargetType.MORTAL and instance.target_id:
            mortal = state.mortals.get(str(instance.target_id))
            if mortal and not mortal.pinned:
                mutations.append(StateMutation(
                    mutation_type=MutationType.MORTAL_VISIBILITY,
                    target_id=instance.target_id,
                    field="visibility",
                    new_value=1.0,
                    note=f"Visibility refreshed by {defn.name}",
                ))

        return outcome, mutations, narrative

    def _roll_reliability(
        self,
        reliability: "ActionReliability",
        rng: random.Random,
        puissance: float = 0.0,
    ) -> "ActionOutcome":

        roll = rng.random()
        bonus = puissance * PUISSANCE_TIER_BONUS
        if reliability == ActionReliability.CERTAIN:
            return ActionOutcome.SUCCESS
        elif reliability == ActionReliability.PROBABLE:
            s = 0.75 + bonus
            if roll < s:
                return ActionOutcome.SUCCESS
            elif roll < s + 0.15:
                return ActionOutcome.PARTIAL
            else:
                return ActionOutcome.FAILURE
        elif reliability == ActionReliability.UNCERTAIN:
            s = 0.50 + bonus
            if roll < s:
                return ActionOutcome.SUCCESS
            elif roll < s + 0.25:
                return ActionOutcome.PARTIAL
            else:
                return ActionOutcome.FAILURE
        else:  # CHAOTIC
            s = 0.30 + bonus
            if roll < s:
                return ActionOutcome.SUCCESS
            elif roll < s + 0.30:
                return ActionOutcome.PARTIAL
            elif roll < s + 0.50:
                return ActionOutcome.FAILURE
            else:
                return ActionOutcome.CHAOTIC_RESULT

    def _roll_influence(
        self,
        instance: "ActionInstance",
        state: "SimulationState",
        rng: random.Random,
    ) -> "ActionOutcome":
        """Success roll for Whisper / Shape Dream. Uses the 0.75–0.99 formula."""
        mortal = state.mortals.get(str(instance.target_id)) if instance.target_id else None
        visibility = mortal.visibility if mortal else 0.0
        framing = getattr(instance.intent, "framing", None)
        resonance = _framing_resonance(mortal.culture_tags if mortal else {}, framing) if framing else 0.0
        # Resonance from _framing_resonance is [-1, 1]; clamp to [0, 1] for influence
        # (AMBIGUOUS framing → 0; mismatched framing → 0, not a penalty here per spec)
        resonance = max(0.0, resonance)

        puissance = state.demiurge.puissance
        success_chance = max(BASE_INFLUENCE, min(0.99,
            BASE_INFLUENCE
            + puissance  * PUISSANCE_WEIGHT
            + visibility * VISIBILITY_WEIGHT
            + resonance  * FRAMING_WEIGHT
        ))
        roll = rng.random()
        if roll < success_chance:
            return ActionOutcome.SUCCESS
        elif roll < success_chance + 0.15:
            return ActionOutcome.PARTIAL
        else:
            return ActionOutcome.FAILURE

    def _resolve_intent_mutations(
        self,
        instance: "ActionInstance",
        defn: "ActionDefinition",
        state: SimulationState,
        outcome: "ActionOutcome",
        rng: random.Random,
    ) -> tuple[list[StateMutation], str]:
        """
        Produce state mutations from the action's specific intent.
        This is where WhisperIntent, OmenIntent, etc. are read
        and translated into belief shifts, stat changes, etc.
        """
        mutations: list[StateMutation] = []
        narrative = f"{defn.name} executed."

        intent = instance.intent

        # ── Intent-less actions with defined effects ───
        if intent is None:
            if defn.name == "Appoint Proxius":
                mortal = state.mortals.get(str(instance.target_id))
                if not mortal:
                    return mutations, "No mortal found to appoint."
                if mortal.role == MortalRole.PROXIUS:
                    return mutations, f"{mortal.name} is already a Proxius."
                if outcome != ActionOutcome.FAILURE:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.PROXIUS_APPOINTED,
                        target_id=mortal.id,
                        field="role",
                        new_value=MortalRole.PROXIUS.value,
                        note=f"{mortal.name} elevated to Proxius",
                    ))
                    narrative = f"{mortal.name} has been elevated to Proxius."
                else:
                    narrative = f"The elevation of {mortal.name} did not take hold."

            elif defn.name == "Dismiss Proxius":
                mortal = state.mortals.get(str(instance.target_id))
                if not mortal:
                    return mutations, "No mortal found to dismiss."
                if mortal.role != MortalRole.PROXIUS:
                    return mutations, f"{mortal.name} is not a Proxius."
                mutations.append(StateMutation(
                    mutation_type=MutationType.PROXIUS_DISMISSED,
                    target_id=mortal.id,
                    field="role",
                    new_value=MortalRole.OTHER.value,
                    note=f"{mortal.name} dismissed from Proxius role",
                ))
                narrative = f"{mortal.name} has been relieved of their Proxius appointment."

            elif defn.name == "Seed World with Life":
                return mutations, (
                    "Seed World requires a SeedWorldIntent specifying the species. "
                    "Use the action browser to provide species details."
                )

            elif defn.name == "Extinguish Civilization":
                civ = state.civilizations.get(str(instance.target_id))
                if not civ:
                    return mutations, "Target civilization not found."
                if outcome != ActionOutcome.FAILURE:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.ENTITY_DESTROYED,
                        target_id=civ.id,
                        field="",
                        note=f"{civ.name} extinguished by divine decree",
                    ))
                    narrative = (
                        f"{civ.name} has been extinguished. "
                        f"The world falls silent where they once stood."
                    )
                else:
                    narrative = f"The attempt to extinguish {civ.name} failed. They endure."

            elif defn.name == "Exile to Underreal":
                tid_str = str(instance.target_id) if instance.target_id else None
                target_name = "the target"
                for collection in (state.civilizations, state.mortals, state.locations):
                    if tid_str and tid_str in collection:
                        target_name = getattr(collection[tid_str], "name", target_name)
                        break
                if outcome != ActionOutcome.FAILURE:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.EXILED_TO_UNDERREAL,
                        target_id=instance.target_id,
                        field="",
                        note=f"{target_name} cast into the Underreal",
                    ))
                    narrative = (
                        f"{target_name} has been cast into the Underreal. "
                        f"A distinctive trace lingers where they were."
                    )
                else:
                    narrative = (
                        f"The exile of {target_name} failed — "
                        f"the target resisted the conceptual unraveling."
                    )

            elif defn.name == "Perform Direct Miracle":
                mortal = state.mortals.get(str(instance.target_id)) if instance.target_id else None
                if not mortal:
                    return mutations, "Target mortal not found."
                if outcome != ActionOutcome.FAILURE:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.MORTAL_ALIGNMENT,
                        target_id=mortal.id,
                        field="alignment",
                        delta=0.3 if outcome == ActionOutcome.SUCCESS else 0.1,
                        note=f"Direct miracle witnessed by {mortal.name}",
                    ))
                    if mortal.civilization_id:
                        mutations.append(StateMutation(
                            mutation_type=MutationType.CIVILIZATION_STAT,
                            target_id=mortal.civilization_id,
                            field="divine_awareness",
                            delta=0.15 if outcome == ActionOutcome.SUCCESS else 0.05,
                            note=f"Divine awareness spike from miracle on {mortal.name}",
                        ))
                    narrative = (
                        f"A direct miracle was performed for {mortal.name}. "
                        f"Their faith is confirmed; word will spread."
                    )
                else:
                    narrative = (
                        f"The miracle for {mortal.name} failed to manifest. "
                        f"They were left waiting."
                    )

            elif defn.name == "Empower Proxius":
                proxius = state.mortals.get(str(instance.target_id)) if instance.target_id else None
                if not proxius or proxius.role != MortalRole.PROXIUS:
                    return mutations, "No active Proxius found to empower."
                if outcome != ActionOutcome.FAILURE:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.MORTAL_ALIGNMENT,
                        target_id=proxius.id,
                        field="alignment",
                        delta=0.2 if outcome == ActionOutcome.SUCCESS else 0.08,
                        note=f"{proxius.name} granted temporary divine capability",
                    ))
                    narrative = (
                        f"{proxius.name} has been granted a surge of divine capability. "
                        f"Their alignment to your will is reinforced."
                    )
                else:
                    narrative = f"The empowerment of {proxius.name} failed to take hold."

            elif defn.name == "Reshape World Geography":
                world_obj = state.worlds.get(str(instance.target_id)) if instance.target_id else None
                if not world_obj:
                    return mutations, "Target world not found."
                if outcome == ActionOutcome.SUCCESS:
                    condition_ladder = [
                        LocCondition.DYING, LocCondition.BARREN,
                        LocCondition.STRESSED, LocCondition.STABLE,
                        LocCondition.THRIVING,
                    ]
                    try:
                        idx = condition_ladder.index(world_obj.condition)
                        new_condition = condition_ladder[min(idx + 1, len(condition_ladder) - 1)]
                    except ValueError:
                        new_condition = LocCondition.STABLE
                    mutations.append(StateMutation(
                        mutation_type=MutationType.WORLD_CONDITION,
                        target_id=world_obj.id,
                        field="condition",
                        new_value=new_condition.value,
                        note=f"Geography reshaped on {world_obj.name}",
                    ))
                    narrative = (
                        f"The geography of {world_obj.name} has been reshaped. "
                        f"Continents shifted; the world's condition improved."
                    )
                elif outcome == ActionOutcome.PARTIAL:
                    narrative = (
                        f"The reshaping of {world_obj.name} is complete, "
                        f"though the results are imperfect."
                    )
                else:
                    narrative = (
                        f"The attempt to reshape {world_obj.name} failed. "
                        f"The world resists divine remolding."
                    )

            elif defn.name == "Move Against Luminary":
                luminary = state.luminaries.get(str(instance.target_id)) if instance.target_id else None
                lum_name = luminary.name if luminary else "the Luminary"
                if outcome == ActionOutcome.SUCCESS:
                    narrative = (
                        f"The accumulated Essence unleashed against {lum_name} found its mark. "
                        f"Their hold on your universe shatters."
                    )
                elif outcome == ActionOutcome.PARTIAL:
                    narrative = (
                        f"The challenge to {lum_name} landed but did not sever. "
                        f"They will retaliate."
                    )
                else:
                    narrative = (
                        f"The move against {lum_name} was deflected. "
                        f"They are now aware of your intent."
                    )

            elif defn.name == "Maintain Concealment":
                if outcome == ActionOutcome.FAILURE:
                    return mutations, "The concealment maintenance failed to take hold."

                effectiveness = 1.0 if outcome == ActionOutcome.SUCCESS else 0.4
                current_integrity = state.essence.concealment_integrity
                # Diminishing returns: less useful when integrity is already high
                restore = 0.30 * effectiveness * (1.0 - current_integrity * 0.5)
                restore = max(0.0, restore)
                if restore > 0.0:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.CONCEALMENT_CHANGE,
                        target_id=state.demiurge.id,
                        field="concealment_integrity",
                        delta=restore,
                        note="Concealment integrity maintained",
                    ))
                narrative = (
                    f"Concealment reinforced. "
                    f"Integrity restored by {restore:.2f} "
                    f"(was {current_integrity:.2f}, "
                    f"now {min(1.0, current_integrity + restore):.2f})."
                )

            elif defn.name == "Go Quiet":
                mortal = state.mortals.get(str(instance.target_id)) if instance.target_id else None
                if not mortal or mortal.role != MortalRole.PROXIUS:
                    return mutations, "No Proxius found to go quiet."
                if mortal.status == MortalStatus.DORMANT:
                    return mutations, f"{mortal.name} is already dormant."
                mutations.append(StateMutation(
                    mutation_type=MutationType.MORTAL_STATUS,
                    target_id=mortal.id,
                    field="status",
                    new_value=MortalStatus.DORMANT.value,
                    note=f"{mortal.name} goes quiet — proxius_activity suspended",
                ))
                narrative = (
                    f"{mortal.name} has gone quiet. "
                    f"Their activity is suspended; bio-age resumes at reduced rate. "
                    f"Issue a directive to reactivate them."
                )

            elif defn.name == "Audit Proxius":
                mortal = state.mortals.get(str(instance.target_id)) if instance.target_id else None
                if not mortal or mortal.role != MortalRole.PROXIUS:
                    return mutations, "No Proxius found to audit."
                alignment_desc = (
                    "faithfully aligned"    if mortal.alignment > 0.7 else
                    "drifting"              if mortal.alignment > 0.4 else
                    "significantly divergent"
                )
                tags = ", ".join(mortal.personal_tags) if mortal.personal_tags else "none"
                goal_section = ""
                if mortal.active_goal:
                    g = mortal.active_goal
                    ticks_active = state.tick_number - g.started_at_tick
                    last_act = g.last_action.value.replace("_", " ") if g.last_action else "none yet"
                    directive_desc = g.label if g.label else f"imago [{g.imago_node_id}]"
                    goal_section = (
                        f" Active directive: {directive_desc}, "
                        f"{ticks_active} tick(s) active, "
                        f"last action: {last_act}"
                        + (f", streak: {g.consecutive_promote_count}" if g.consecutive_promote_count > 0 else "")
                        + (" [PETITION PENDING]" if g.petition_pending else "")
                        + ("." if not g.report_log else f". Last report: {g.report_log[-1]}")
                    )
                else:
                    goal_section = " No active directive."
                narrative = (
                    f"Silent audit of {mortal.name} complete. "
                    f"Alignment: {mortal.alignment:.2f} ({alignment_desc}). "
                    f"Status: {mortal.status.value}. "
                    f"Personal convictions: {tags}."
                    + goal_section
                )
                # Marks this Proxius as audited this tick so Phase 2.5 suppresses
                # a redundant REPORT_TO_DEMIURGE choice.
                mutations.append(StateMutation(
                    mutation_type=MutationType.PROXIUS_AUDITED,
                    target_id=mortal.id,
                    field="audited",
                    note=f"Audit of {mortal.name} this tick",
                ))
                # Persist the audit narrative on the mortal for the detail tab.
                mutations.append(StateMutation(
                    mutation_type=MutationType.PROXIUS_AUDIT_RECORDED,
                    target_id=mortal.id,
                    field=str(state.tick_number),
                    new_value=narrative,
                    note=f"Audit narrative captured for {mortal.name}",
                ))

            elif defn.name == "Read Divine Traces":
                target_world_id = str(instance.target_id) if instance.target_id else None
                world_obj = state.worlds.get(target_world_id) if target_world_id else None
                if not world_obj:
                    return mutations, "No world found to read traces on."

                # Find events associated with this world
                relevant: list[Event] = []
                for ev in state.active_events.values():
                    if ev.is_expired(state.tick_number):
                        continue
                    if str(ev.target_world_id) == target_world_id:
                        relevant.append(ev)
                        continue
                    if ev.target_civilization_id is not None:
                        civ = state.civilizations.get(str(ev.target_civilization_id))
                        if civ and str(civ.origin_location_id) == target_world_id:
                            relevant.append(ev)
                            continue
                    if ev.target_mortal_id is not None:
                        mortal = state.mortals.get(str(ev.target_mortal_id))
                        m_wid = _resolve_world_id_for(state, mortal.current_location) if mortal else None
                        if m_wid == target_world_id:
                            relevant.append(ev)

                if not relevant:
                    narrative = (
                        f"No divine traces discernible on {world_obj.name}. "
                        f"The world appears untouched by recent divine influence."
                    )
                elif outcome == ActionOutcome.PARTIAL:
                    strongest = max(relevant, key=lambda e: e.current_strength(state.tick_number))
                    age = state.tick_number - strongest.created_at_tick
                    narrative = (
                        f"{len(relevant)} active divine event(s) detected on {world_obj.name}. "
                        f"Dominant type: {strongest.event_type.value}, "
                        f"approximately {age} tick(s) old."
                    )
                else:
                    lines = [f"Divine traces on {world_obj.name} ({len(relevant)} active event(s)):"]
                    for ev in sorted(relevant, key=lambda e: -e.current_strength(state.tick_number)):
                        age = state.tick_number - ev.created_at_tick
                        strength = ev.current_strength(state.tick_number)
                        remaining = ev.duration - age
                        domains = ", ".join(dv.domain_tag for dv in ev.domain_vectors) or "none"
                        lines.append(
                            f"  [{ev.event_type.value}] age {age}, "
                            f"strength {strength:.2f}, "
                            f"{remaining} tick(s) remaining — domains: {domains}"
                        )
                    narrative = "\n".join(lines)
                # Purely observational — no mutations.

            elif defn.name == "Ask for Orders":
                luminary = state.luminaries.get(str(instance.target_id)) if instance.target_id else None
                if not luminary:
                    return mutations, "No Luminary found to petition."

                lid = str(luminary.id)
                cfg = state.config

                # Raise attention — asking for orders reminds them you're here
                mutations.append(StateMutation(
                    mutation_type=MutationType.FOOTPRINT_CHANGE,
                    target_id=luminary.id,
                    field="attention",
                    delta=0.06,
                    note=f"Ask for Orders: {luminary.name} attention raised",
                ))

                # Compute threshold parameters
                sorted_affs = [
                    min(0.8, v)
                    for _, v in sorted(luminary.domains.items(), key=lambda x: (-x[1], x[0]))
                ]
                effective_affinity = sum(
                    aff * (cfg.luminary_essence_decay ** i)
                    for i, aff in enumerate(sorted_affs)
                )
                ticks_since = state.ticks_since_evaluation.get(lid, cfg.evaluation_interval)
                base_threshold_so_far = effective_affinity * cfg.luminary_essence_baseline_rate * ticks_since
                raised = luminary.essence_expectation_raised
                threshold_so_far = base_threshold_so_far + raised

                # Project threshold at next evaluation (use eval_interval ticks as horizon)
                eval_interval = max(5.0, cfg.evaluation_interval)
                projected_threshold = effective_affinity * cfg.luminary_essence_baseline_rate * eval_interval + raised

                domain_production = state.luminary_production_this_eval.get(lid, 0.0)
                surplus = domain_production - threshold_so_far

                # Per-domain contribution from current universe expression
                profile = state.previous_domain_profile
                report = [f"Orders from {luminary.name}"]

                # Essence expectations section
                report.append("  Essence Expectations:")
                for tag, aff in sorted(luminary.domains.items(), key=lambda x: (-x[1], x[0])):
                    universe_pool = profile.scores.get(tag, 0.0) if profile else 0.0
                    short = tag.split(":", 1)[1] if ":" in tag else tag
                    report.append(f"    {short:<14} affinity {aff:.2f}  universe expression {universe_pool:.3f}")

                report.append(f"  Effective affinity: {effective_affinity:.3f}")
                report.append(
                    f"  Threshold so far:   {threshold_so_far:.3f}  "
                    f"(over {ticks_since:.0f} tick(s), +{raised:.3f} raised expectation)"
                )
                report.append(f"  Projected at eval:  {projected_threshold:.3f}")
                report.append(
                    f"  Produced this period: {domain_production:.3f}  "
                    f"({'above' if surplus >= 0 else 'below'} threshold by {abs(surplus):.3f})"
                )

                # Previous period trend
                if luminary.essence_received_log:
                    prev = luminary.essence_received_log[-1]
                    trend = "improving" if domain_production >= prev else "declining"
                    report.append(f"  Last period: {prev:.3f}  (trend: {trend})")

                # Disposition section
                disp = luminary.disposition
                def _disp_label(v: float, axis: str) -> str:
                    if axis == "results":
                        if v >= 0.4:   return "very pleased"
                        if v >= 0.15:  return "satisfied"
                        if v >= -0.15: return "neutral"
                        if v >= -0.4:  return "dissatisfied"
                        return "deeply displeased"
                    else:  # methods
                        if v >= 0.4:   return "fully approving"
                        if v >= 0.15:  return "comfortable"
                        if v >= -0.15: return "neutral"
                        if v >= -0.4:  return "uneasy"
                        return "strongly opposed"

                report.append("  Disposition:")
                report.append(
                    f"    Results:  {disp.results:+.3f}  ({_disp_label(disp.results, 'results')})"
                )
                report.append(
                    f"    Methods:  {disp.methods:+.3f}  ({_disp_label(disp.methods, 'methods')})"
                )
                report.append(
                    f"    Overall:  {disp.overall:+.3f}"
                )

                # Constraints context
                if luminary.constraints:
                    report.append(f"  Active Constraints: {len(luminary.constraints)}")
                    for con in luminary.constraints:
                        weight_str = f"weight {con.enforcement_weight:.2f}"
                        report.append(f"    · {con.name}  ({weight_str})")

                narrative = "\n".join(report)

                # Persist the orders text on the Luminary so the detail tab can show it.
                mutations.append(StateMutation(
                    mutation_type=MutationType.LUMINARY_ORDERS_RESPONSE,
                    target_id=luminary.id,
                    field=str(state.tick_number),
                    new_value=narrative,
                    note=f"Ask for Orders narrative captured for {luminary.name}",
                ))

            return mutations, narrative

        # ── Scry ─────────────────────────────────────
        if isinstance(intent, ScryIntent):
            scope = intent.scope

            scope_fp: dict[ScryScope, float] = {
                ScryScope.WORLD:    0.05,
                ScryScope.SYSTEM:   0.10,
                ScryScope.GALAXY:   0.20,
                ScryScope.UNIVERSE: 0.35,
            }
            fp_delta = scope_fp[scope] - 0.05  # definition already adds 0.05
            if fp_delta > 0.0:
                mutations.append(StateMutation(
                    mutation_type=MutationType.FOOTPRINT_CHANGE,
                    target_id=state.demiurge.id,
                    field="subtle_influence",
                    delta=fp_delta,
                    note=f"Scry ({scope.value}) extra footprint",
                ))

            scope_essence: dict[ScryScope, float] = {
                ScryScope.WORLD:    0.0,
                ScryScope.SYSTEM:   0.0,
                ScryScope.GALAXY:   0.3,
                ScryScope.UNIVERSE: 0.5,
            }
            scry_essence_cost = scope_essence[scope]
            if scry_essence_cost > 0.0:
                mutations.append(StateMutation(
                    mutation_type=MutationType.ESSENCE_CHANGE,
                    target_id=state.demiurge.id,
                    field="actual",
                    delta=-scry_essence_cost,
                    note=f"Scry ({scope.value}) essence cost",
                ))

            scope_anchor: dict[ScryScope, int] = {
                ScryScope.WORLD:    3,
                ScryScope.SYSTEM:   2,
                ScryScope.GALAXY:   1,
                ScryScope.UNIVERSE: 0,
            }
            anchor = scope_anchor[scope]

            scope_start_vis: dict[ScryScope, float] = {
                ScryScope.WORLD:    0.70,
                ScryScope.SYSTEM:   0.60,
                ScryScope.GALAXY:   0.45,
                ScryScope.UNIVERSE: 0.30,
            }
            start_vis = scope_start_vis[scope]

            def _depth_chance(delta: int) -> float:
                if delta == 0: return 0.85
                if delta == 1: return 0.55
                if delta == 2: return 0.30
                if delta == 3: return 0.06
                if delta == 4: return 0.02
                return 0.005

            # ── Spatial proximity ──────────────────────────────────────
            # Galaxy coordinates are multiplied by this factor so that
            # cross-galaxy distances dwarf intra-galaxy ones automatically.
            _GALAXY_SCALE = 1000.0
            # Distance at which the proximity factor drops to 0.5.
            _SPATIAL_SCALE = 8.0

            def _effective_pos(loc_id: str) -> tuple[float, float, float]:
                """Effective 3-D position accounting for galaxy-level offset."""
                loc = state.locations.get(loc_id)
                if loc is None:
                    return (0.0, 0.0, 0.0)
                cx, cy, cz = loc.coordinates.x, loc.coordinates.y, loc.coordinates.z
                if loc.parent_id is not None:
                    px, py, pz = _effective_pos(str(loc.parent_id))
                    return (px * _GALAXY_SCALE + cx,
                            py * _GALAXY_SCALE + cy,
                            pz * _GALAXY_SCALE + cz)
                return (cx, cy, cz)

            # Resolve the focus position for WORLD, SYSTEM, and GALAXY scopes.
            # UNIVERSE has no spatial focus — factor is always 1.0.
            _focus_pos: Optional[tuple[float, float, float]] = None
            if scope in (ScryScope.WORLD, ScryScope.SYSTEM, ScryScope.GALAXY) and instance.target_id:
                target_loc = state.locations.get(str(instance.target_id))
                if target_loc is not None:
                    if scope == ScryScope.WORLD and target_loc.parent_id is not None:
                        # Focus on the parent system of the targeted world
                        _focus_pos = _effective_pos(str(target_loc.parent_id))
                    else:
                        _focus_pos = _effective_pos(str(instance.target_id))

            def _spatial_factor(candidate_loc_id: str) -> float:
                """
                Distance-based multiplier on discovery probability.
                Returns 1.0 when there is no spatial focus (galaxy/universe scope).
                Uses the candidate's effective position at the system level —
                i.e., if the candidate is a world, its parent system's position.
                """
                if _focus_pos is None:
                    return 1.0
                loc = state.locations.get(candidate_loc_id)
                if loc is None:
                    return 1.0
                # Walk up to system level for the distance calculation
                if loc.location_type not in ("galaxy", "system"):
                    ref_id = str(loc.parent_id) if loc.parent_id else candidate_loc_id
                else:
                    ref_id = candidate_loc_id
                rx, ry, rz = _effective_pos(ref_id)
                fx, fy, fz = _focus_pos
                dist = math.sqrt((rx - fx) ** 2 + (ry - fy) ** 2 + (rz - fz) ** 2)
                return 1.0 / (1.0 + dist / _SPATIAL_SCALE)

            dreg = self._domain_registry
            affiliated = state.demiurge.affiliated_domains

            def _domain_bonus(entity_tags: list[str], base: float) -> float:
                """Domain affinity bonus, scaled down proportionally at high depths."""
                if not dreg or not affiliated or not entity_tags:
                    return 0.0
                total = 0.0
                for etag in entity_tags:
                    for atag in affiliated:
                        try:
                            total += max(0.0, dreg.similarity(etag, atag)) * 0.05
                        except Exception:
                            pass
                bonus_scale = min(1.0, base / 0.55)
                return min(0.20, total) * bonus_scale

            # eligible_locs: location IDs that are already in window OR discovered
            # this tick. Entities can only be found if their container is eligible.
            eligible_locs: set[str] = {
                lid for lid, loc in state.locations.items() if is_in_window(loc)
            }

            # First-contact carve-out: a GALAXY-scope scry on a galaxy whose
            # interior is wholly outside the Window bypasses the spatial-factor
            # falloff for systems inside it and applies a discovery bonus, so
            # an unexplored galaxy doesn't become a dead zone. (Without this,
            # _effective_pos's parent-scaling makes intra-galaxy systems sit
            # ~1000× their offset away from the focus point.)
            _uncharted_galaxy_id: Optional[str] = None
            if scope == ScryScope.GALAXY and instance.target_id:
                tgt_id = str(instance.target_id)
                tgt_loc = state.locations.get(tgt_id)
                if tgt_loc is not None and tgt_loc.location_type == "galaxy":
                    has_known_child = any(
                        loc.location_type == "system"
                        and loc.parent_id is not None
                        and str(loc.parent_id) == tgt_id
                        and lid in eligible_locs
                        for lid, loc in state.locations.items()
                    )
                    if not has_known_child:
                        _uncharted_galaxy_id = tgt_id

            # Build PopLocation → parent world index for Pop discovery gating
            _pop_loc_to_world: dict[str, str] = {}
            for wid, world in state.worlds.items():
                for cid in world.child_ids:
                    loc = state.locations.get(str(cid))
                    if loc and isinstance(loc, PopLocation):
                        _pop_loc_to_world[str(cid)] = wid

            discovered_locs:  list[str] = []
            discovered_civs:  list[str] = []
            discovered_sp:    list[str] = []
            discovered_mort:  list[str] = []
            discovered_pops:  list[str] = []
            refreshed_locs:   list[str] = []
            refreshed_civs:   list[str] = []
            refreshed_sp:     list[str] = []
            refreshed_mort:   list[str] = []

            # Civilization scale → effective discovery depth
            _CIV_SCALE_DEPTH: dict[str, int] = {
                "nascent": 4, "tribal": 4, "city_state": 4,
                "regional": 4, "continental": 4, "planetary": 4,
                "interplanetary": 3,
                "interstellar": 2,
                "intergalactic": 1,
            }

            def _civ_anchor(civ: "Civilization") -> tuple[Optional[str], int]:
                """Returns (anchor_location_id, depth) for a civilization."""
                depth = _CIV_SCALE_DEPTH.get(civ.scale.value, 4)
                if civ.origin_location_id is None:
                    return (None, depth)
                loc_id = str(civ.origin_location_id)
                # Walk up the hierarchy the required number of steps above the world
                for _ in range(4 - depth):
                    loc = state.locations.get(loc_id)
                    if loc is None or loc.parent_id is None:
                        break
                    loc_id = str(loc.parent_id)
                return (loc_id, depth)

            # ── Locations: process galaxy → system → world/plane to build eligible_locs
            # incrementally so container prerequisites cascade within a single tick.
            loc_passes = (
                [(lid, loc) for lid, loc in state.locations.items()
                 if loc.location_type == "galaxy"   and not getattr(loc, "pinned", False)],
                [(lid, loc) for lid, loc in state.locations.items()
                 if loc.location_type == "system"   and not getattr(loc, "pinned", False)],
                [(lid, loc) for lid, loc in state.locations.items()
                 if loc.location_type not in ("galaxy", "system") and not getattr(loc, "pinned", False)],
            )
            for pass_items in loc_passes:
                for lid, loc in pass_items:
                    depth = 1 if loc.location_type == "galaxy" else (2 if loc.location_type == "system" else 3)
                    # Galaxies have no parent entity; deeper locations require parent in window.
                    if depth > 1 and (loc.parent_id is None or str(loc.parent_id) not in eligible_locs):
                        continue
                    delta = abs(depth - anchor)
                    base = _depth_chance(delta)
                    sf = _spatial_factor(lid)
                    # Uncharted-galaxy carve-out: systems inside the targeted
                    # galaxy ignore the spatial falloff and get a bonus.
                    in_uncharted = (
                        _uncharted_galaxy_id is not None
                        and loc.location_type == "system"
                        and loc.parent_id is not None
                        and str(loc.parent_id) == _uncharted_galaxy_id
                    )
                    if in_uncharted:
                        sf = 1.0
                        base = min(0.95, base + 0.25)
                    expr_tags = list(getattr(loc, "domain_expression", {}).keys())
                    p = max(0.0, min(1.0, (base + _domain_bonus(expr_tags + loc.traits, base)) * sf))
                    if rng.random() < p:
                        was_visible = is_in_window(loc)
                        new_vis = max(loc.visibility, start_vis)
                        mutations.append(StateMutation(
                            mutation_type=MutationType.ENTITY_VISIBILITY,
                            target_id=UUID(lid),
                            field="visibility",
                            new_value=new_vis,
                            note=f"Scry ({scope.value}): {loc.name} sighted",
                        ))
                        eligible_locs.add(lid)
                        if was_visible:
                            refreshed_locs.append(loc.name)
                        else:
                            discovered_locs.append(loc.name)

            # ── Civilizations
            for cid, civ in state.civilizations.items():
                if civ.pinned:
                    continue
                if is_wild_civ(civ):
                    continue  # wild "civs" exist for bookkeeping only — not discoverable
                anchor_id, depth = _civ_anchor(civ)
                if anchor_id is not None and anchor_id not in eligible_locs:
                    continue
                delta = abs(depth - anchor)
                base = _depth_chance(delta)
                sf = _spatial_factor(anchor_id) if anchor_id else 1.0
                # Extra bonus if homeworld is already known, even for high-scale civs
                origin_prox = 0.0
                if depth < 4 and civ.origin_location_id is not None:
                    if str(civ.origin_location_id) in eligible_locs:
                        origin_prox = 0.15 * min(1.0, base / 0.55)
                p = max(0.0, min(1.0,
                    (base + _domain_bonus(list(civ.dominant_beliefs.keys()), base) + origin_prox) * sf
                ))
                if rng.random() < p:
                    was_visible = is_in_window(civ)
                    new_vis = max(civ.visibility, start_vis)
                    mutations.append(StateMutation(
                        mutation_type=MutationType.ENTITY_VISIBILITY,
                        target_id=UUID(cid),
                        field="visibility",
                        new_value=new_vis,
                        note=f"Scry ({scope.value}): {civ.name} sighted",
                    ))
                    if was_visible:
                        refreshed_civs.append(civ.name)
                    else:
                        discovered_civs.append(civ.name)

            # ── Species
            for sid, sp in state.species.items():
                if sp.pinned:
                    continue
                origin_id = str(sp.origin_world_id) if sp.origin_world_id else None
                if origin_id is not None and origin_id not in eligible_locs:
                    continue
                delta = abs(4 - anchor)
                base = _depth_chance(delta)
                sf = _spatial_factor(origin_id) if origin_id else 1.0
                p = max(0.0, min(1.0, (base + _domain_bonus(sp.domain_tags, base)) * sf))
                if rng.random() < p:
                    was_visible = is_in_window(sp)
                    new_vis = max(sp.visibility, start_vis)
                    mutations.append(StateMutation(
                        mutation_type=MutationType.ENTITY_VISIBILITY,
                        target_id=UUID(sid),
                        field="visibility",
                        new_value=new_vis,
                        note=f"Scry ({scope.value}): {sp.name} sighted",
                    ))
                    if was_visible:
                        refreshed_sp.append(sp.name)
                    else:
                        discovered_sp.append(sp.name)

            # ── Mortals
            for mid, mortal in state.mortals.items():
                if mortal.status == MortalStatus.DECEASED or mortal.pinned:
                    continue
                if str(mortal.current_location) not in eligible_locs:
                    continue
                # PopLocations distant from the world core are harder to scry.
                m_loc = state.locations.get(str(mortal.current_location))
                m_dist = m_loc.distance_from_core if isinstance(m_loc, PopLocation) else 0
                delta = abs(5 - anchor) + m_dist
                base = _depth_chance(delta)
                sf = _spatial_factor(str(mortal.current_location))
                p = max(0.0, min(1.0,
                    (base + _domain_bonus(list(mortal.belief_tags.keys()) + mortal.personal_tags, base)) * sf
                ))
                if rng.random() < p:
                    was_visible = mortal.visibility > ENTITY_VISIBILITY_FLOOR
                    new_vis = max(mortal.visibility, start_vis)
                    mutations.append(StateMutation(
                        mutation_type=MutationType.MORTAL_VISIBILITY,
                        target_id=UUID(mid),
                        field="visibility",
                        new_value=new_vis,
                        note=f"Scry ({scope.value}): {mortal.name} sighted",
                    ))
                    if was_visible:
                        refreshed_mort.append(mortal.name)
                    else:
                        discovered_mort.append(mortal.name)

            # ── Pops
            # Pops are gated on their civilization being in-window.
            # Discovery probability scales with Pop size and social class prominence.
            _PROMINENT_CLASSES = {"elite", "priest", "warrior"}
            for pid, pop in state.pops.items():
                if pop.pinned:
                    continue
                # Civ-bound pops require their civilization to be in-window; wild
                # (non-civ) pops anchor directly on their world's eligibility below.
                if pop.civilization_id:
                    civ = state.civilizations.get(str(pop.civilization_id))
                    if civ is None or not is_in_window(civ):
                        continue
                pop_loc = state.locations.get(str(pop.current_location))
                pop_world_id = (
                    _pop_loc_to_world.get(str(pop.current_location))
                    if pop_loc and isinstance(pop_loc, PopLocation)
                    else str(pop.current_location)
                )
                if pop_world_id not in eligible_locs:
                    continue
                size_factor = min(1.0, pop.size_fractional / 9.0)
                stratum_factor = 1.3 if (pop.social_class and pop.social_class.value in _PROMINENT_CLASSES) else 1.0
                world_scry_base = start_vis * 0.5  # Pops revealed at half start_vis
                # PopLocations distant from the world core are harder to scry.
                dist = pop_loc.distance_from_core if isinstance(pop_loc, PopLocation) else 0
                distance_factor = 0.7 ** dist
                p = min(1.0, world_scry_base * size_factor * stratum_factor * distance_factor)
                if rng.random() < p:
                    was_visible = pop.visibility > ENTITY_VISIBILITY_FLOOR
                    new_vis = max(pop.visibility, world_scry_base)
                    mutations.append(StateMutation(
                        mutation_type=MutationType.POP_VISIBILITY,
                        target_id=UUID(pid),
                        field="visibility",
                        new_value=new_vis,
                        note=f"Scry ({scope.value}): Pop of {civ.name} sighted",
                    ))
                    if not was_visible:
                        class_label = pop.stratum.title() if pop.stratum else "Pop"
                        discovered_pops.append(
                            f"{civ.name} {class_label} class (sz {pop.size_magnitude})"
                        )

            parts = [f"You scryed at {scope.value} scope."]
            all_discovered = discovered_locs + discovered_civs + discovered_sp + discovered_mort
            all_refreshed  = refreshed_locs  + refreshed_civs  + refreshed_sp  + refreshed_mort
            if discovered_locs:
                parts.append(f"Locations sighted: {', '.join(discovered_locs)}.")
            if discovered_civs:
                parts.append(f"Civilizations sighted: {', '.join(discovered_civs)}.")
            if discovered_sp:
                parts.append(f"Species sighted: {', '.join(discovered_sp)}.")
            if discovered_mort:
                parts.append(f"Mortals sighted: {', '.join(discovered_mort)}.")
            if discovered_pops:
                parts.append(f"Pops sighted: {', '.join(discovered_pops)}.")
            if all_refreshed and not all_discovered and not discovered_pops:
                parts.append(f"Sight maintained on: {', '.join(all_refreshed)}.")
            elif all_refreshed:
                parts.append(f"Also maintained: {', '.join(all_refreshed)}.")
            if not all_discovered and not all_refreshed and not discovered_pops:
                parts.append("Nothing new came into view.")
            return mutations, " ".join(parts)

        # ── Change Affiliated Domain ──────────────────
        if isinstance(intent, ChangeAffiliatedDomainsIntent):
            old_tag = intent.old_domain
            new_tag = intent.new_domain
            if old_tag not in state.demiurge.affiliated_domains:
                return mutations, f"{old_tag} is not one of your affiliated domains."
            if new_tag in state.demiurge.affiliated_domains:
                return mutations, f"{new_tag} is already one of your affiliated domains."
            mutations.append(StateMutation(
                mutation_type=MutationType.AFFILIATED_DOMAIN_CHANGE,
                target_id=state.demiurge.id,
                field="affiliated_domains",
                new_value=f"{old_tag}→{new_tag}",
                note=f"Demiurge reoriented affiliation: {old_tag} → {new_tag}",
            ))
            old_short = old_tag.split(":", 1)[1] if ":" in old_tag else old_tag
            new_short = new_tag.split(":", 1)[1] if ":" in new_tag else new_tag
            return mutations, (
                f"You release your conceptual hold on {old_short.title()} and turn your focus "
                f"toward {new_short.title()}. The reorientation settles into your nature."
            )

        # ── Explore Beliefs ───────────────────────────
        if isinstance(intent, ExploreBeliefIntent):
            tag = intent.domain_tag
            short = tag.split(":", 1)[1].title() if ":" in tag else tag.title()
            cap = _compute_revelation_cap(state, tag)
            if cap == 0.0:
                return mutations, f"All Imagines in {short} are already revealed — there is nothing left to research here."
            pool = state.demiurge.revelation_pools.get(tag, 0.0)
            if pool >= cap:
                return mutations, (
                    f"You have accumulated maximum Revelation for {short} ({pool:.2f} / {cap:.2f}). "
                    f"Use Reveal Imago to unlock Imagines before continuing."
                )
            base_rate = 10.0
            affinity_bonus = 7.0 if tag in state.demiurge.affiliated_domains else 0.0
            expr = _compute_universal_expression(state, tag)
            from_expression = round(max(0.0, (expr - 0.1) * (10 / 3)), 2)
            revelation_per_tick = round(base_rate + affinity_bonus + from_expression, 2)
            actual_gain = round(min(revelation_per_tick, cap - pool), 2)
            new_pool = round(pool + actual_gain, 2)
            mutations.append(StateMutation(
                mutation_type=MutationType.REVELATION_GAINED,
                target_id=state.demiurge.id,
                field=tag,
                delta=actual_gain,
                note=f"Explore Beliefs: +{actual_gain} Revelation for {tag}",
            ))
            # Check if any unlockable Imago just became affordable
            ireg = get_imago_registry()
            tree = tag.split(":", 1)[1] if ":" in tag else tag
            unlocked_set = set(state.demiurge.unlocked_imagines)
            newly_affordable: list[str] = []
            for node in ireg.nodes_for_tree(tree):
                if node.node_id in unlocked_set:
                    continue
                if not ireg.is_unlockable(node.node_id, unlocked_set):
                    continue
                cost = _revelation_adjusted_cost(node.tier, state.demiurge.revealed_imagines)
                if pool < cost <= new_pool:
                    newly_affordable.append(node.name)
            narrative = f"+{actual_gain} Revelation for {short} ({new_pool:.2f} / {cap:.2f})."
            if newly_affordable:
                names = ", ".join(newly_affordable)
                narrative += f" You have enough Revelation in {short} to reveal: {names}."
            return mutations, narrative

        # ── Reveal Imago ──────────────────────────────
        if isinstance(intent, RevealImagoIntent):
            tag = intent.domain_tag
            node_id = intent.node_id
            short = tag.split(":", 1)[1].title() if ":" in tag else tag.title()
            ireg = get_imago_registry()
            node = ireg.get_node(node_id)
            if node is None or node.tree != (tag.split(":", 1)[1] if ":" in tag else tag):
                return mutations, f"Invalid Imago node '{node_id}' for domain {tag}."
            unlocked_set = set(state.demiurge.unlocked_imagines)
            if node_id in unlocked_set:
                return mutations, f"{node.name} is already unlocked."
            if not ireg.is_unlockable(node_id, unlocked_set):
                prereqs = ireg.prerequisites_for(node_id)
                missing = [p for p in prereqs if p not in unlocked_set]
                return mutations, (
                    f"Prerequisites for {node.name} not met. "
                    f"Still needed: {', '.join(missing)}."
                )
            cost = _revelation_adjusted_cost(node.tier, state.demiurge.revealed_imagines)
            pool = state.demiurge.revelation_pools.get(tag, 0.0)
            if pool < cost:
                deficit = round(cost - pool, 2)
                return mutations, (
                    f"Insufficient Revelation for {node.name}. "
                    f"Need {cost}, have {pool:.2f} — {deficit:.2f} short."
                )
            mutations.append(StateMutation(
                mutation_type=MutationType.REVELATION_GAINED,
                target_id=state.demiurge.id,
                field=tag,
                delta=-float(cost),
                note=f"Reveal Imago: spent {cost} Revelation from {tag} for {node_id}",
            ))
            mutations.append(StateMutation(
                mutation_type=MutationType.IMAGO_REVEALED,
                target_id=state.demiurge.id,
                field=node_id,
                new_value=node_id,
                note=f"Demiurge revealed Imago: {node_id}",
            ))
            tier_names = {1: "Tier-1", 2: "Tier-2", 3: "Tier-3", 4: "Apex"}
            return mutations, (
                f"You have internalized {node.name}, a {tier_names.get(node.tier, 'Tier')} Imago "
                f"of {short}. {cost} Revelation spent."
            )

        # ── Commission Inquiry ────────────────────────
        if isinstance(intent, CommissionInquiryIntent):
            tag = intent.domain_tag
            short = tag.split(":", 1)[1].title() if ":" in tag else tag.title()
            proxius = state.mortals.get(str(intent.proxius_id))
            if proxius is None:
                return mutations, "The designated Proxius could not be found."
            if proxius.status != MortalStatus.ACTIVE:
                return mutations, f"{proxius.name} is not active and cannot conduct research."
            if proxius.active_goal is not None and proxius.active_goal.research_domain:
                return mutations, f"{proxius.name} is already conducting research into {proxius.active_goal.research_domain}."
            cap = _compute_revelation_cap(state, tag)
            if cap == 0.0:
                return mutations, f"All Imagines in {short} are already revealed — no research needed."
            pool = state.demiurge.revelation_pools.get(tag, 0.0)
            if pool >= cap:
                return mutations, f"Revelation for {short} is already at its cap. Reveal Imagines before commissioning further research."
            goal = ProxiusGoal(
                imago_node_id="",
                target_location_id=proxius.current_location,
                research_domain=tag,
                latitude=0.5,
                started_at_tick=state.tick_number,
            )
            mutations.append(StateMutation(
                mutation_type=MutationType.PROXIUS_GOAL_SET,
                target_id=proxius.id,
                field="active_goal",
                new_value=goal,
                note=f"Commission Inquiry: {proxius.name} → research {tag}",
            ))
            return mutations, (
                f"You commission {proxius.name} to study {short}. "
                f"Their mortal insight will contribute a trickle of Revelation each tick."
            )

        # ── Whisper / Dream ───────────────────────────
        if isinstance(intent, WhisperIntent):
            if outcome == ActionOutcome.FAILURE:
                return mutations, f"{defn.name} found no purchase in the mortal's mind."

            mortal = state.mortals.get(str(instance.target_id))
            if not mortal:
                return mutations, narrative

            effectiveness = 1.0 if outcome == ActionOutcome.SUCCESS else 0.4
            effectiveness *= mortal.alignment
            # A drifting Proxius is also harder to reach with whispers

            for dv in intent.domain_vectors:
                mutations.append(StateMutation(
                    mutation_type=MutationType.MORTAL_BELIEF_SHIFT,
                    target_id=mortal.id,
                    field=dv.domain_tag,
                    delta=dv.direction * effectiveness * 0.1,
                    new_value=dv.domain_tag,
                    note=(
                        f"Whisper to {mortal.name}: "
                        f"'{intent.concept[:40]}...'"
                    ),
                ))
            for cv in intent.culture_vectors:
                mutations.append(StateMutation(
                    mutation_type=MutationType.MORTAL_CULTURE_SHIFT,
                    target_id=mortal.id,
                    field=cv.culture_tag,
                    delta=cv.direction * effectiveness * 0.1,
                    new_value=cv.culture_tag,
                    note=(
                        f"Whisper culture rider to {mortal.name}: "
                        f"'{intent.concept[:40]}...'"
                    ),
                ))

            narrative = (
                f"You whispered to {mortal.name}: '{intent.concept}'. "
                f"Effectiveness: {effectiveness:.0%}."
            )

            # Emit a RAMP_FADE event so the whisper builds then fades over 4 ticks
            mutations.append(StateMutation(
                mutation_type=MutationType.EVENT_EMITTED,
                target_id=None,
                field="active_events",
                new_value=Event(
                    event_type=EventType.WHISPER,
                    curve=StrengthCurve.RAMP_FADE,
                    source_action_id=instance.action_definition_id,
                    created_at_tick=state.tick_number,
                    duration=4,
                    base_strength=effectiveness,
                    peak_offset=1,
                    target_mortal_id=instance.target_id,
                    target_civilization_id=mortal.civilization_id,
                    domain_vectors=intent.domain_vectors,
                    culture_vectors=intent.culture_vectors,
                    domain_shift_rate=0.06,
                    attention_per_tick=0.01,
                    imago_node_id=getattr(intent, "imago_node_id", None),
                    concept=intent.concept,
                ),
            ))

            # Splash to nearby Pops on the same world — see _emit_whisper_splash.
            self._emit_whisper_splash(
                mutations, state, mortal,
                domain_vectors=intent.domain_vectors,
                culture_vectors=intent.culture_vectors,
                per_unit_delta=effectiveness * 0.1,
                note_prefix="Whisper",
            )

        # ── Shape Dream ───────────────────────────────
        elif isinstance(intent, ShapeDreamIntent):
            if outcome == ActionOutcome.FAILURE:
                return mutations, f"{defn.name} dissipated before either Imāgō could root."

            mortal = state.mortals.get(str(instance.target_id))
            if not mortal:
                return mutations, narrative

            effectiveness = 1.0 if outcome == ActionOutcome.SUCCESS else 0.4
            effectiveness *= mortal.alignment

            # Random dominance: one Imago boosted ×1.15, the other suppressed ×0.60.
            dominant_a = self._rng.random() < 0.5
            mult_a = 1.15 if dominant_a else 0.60
            mult_b = 0.60 if dominant_a else 1.15

            combined_dvs = self._combine_shape_dream_vectors(
                intent.domain_vectors_a, intent.domain_vectors_b,
                mult_a, mult_b, "domain_tag",
            )
            combined_cvs = self._combine_shape_dream_vectors(
                intent.culture_vectors_a, intent.culture_vectors_b,
                mult_a, mult_b, "culture_tag",
            )

            for dv in combined_dvs:
                mutations.append(StateMutation(
                    mutation_type=MutationType.MORTAL_BELIEF_SHIFT,
                    target_id=mortal.id,
                    field=dv.domain_tag,
                    delta=dv.direction * effectiveness * 0.1,
                    new_value=dv.domain_tag,
                    note=f"Shape Dream → {mortal.name}",
                ))
            for cv in combined_cvs:
                mutations.append(StateMutation(
                    mutation_type=MutationType.MORTAL_CULTURE_SHIFT,
                    target_id=mortal.id,
                    field=cv.culture_tag,
                    delta=cv.direction * effectiveness * 0.1,
                    new_value=cv.culture_tag,
                    note=f"Shape Dream culture → {mortal.name}",
                ))

            dominant_id = intent.imago_node_id_a if dominant_a else intent.imago_node_id_b
            suppressed_id = intent.imago_node_id_b if dominant_a else intent.imago_node_id_a

            mutations.append(StateMutation(
                mutation_type=MutationType.EVENT_EMITTED,
                target_id=None,
                field="active_events",
                new_value=Event(
                    event_type=EventType.WHISPER,  # echo machinery is shared with Whisper
                    curve=StrengthCurve.RAMP_FADE,
                    source_action_id=instance.action_definition_id,
                    created_at_tick=state.tick_number,
                    duration=4,
                    base_strength=effectiveness,
                    peak_offset=1,
                    target_mortal_id=instance.target_id,
                    target_civilization_id=mortal.civilization_id,
                    domain_vectors=combined_dvs,
                    culture_vectors=combined_cvs,
                    domain_shift_rate=0.06,
                    attention_per_tick=0.01,
                    imago_node_id=dominant_id,  # dominant carries forward into echo
                    concept=intent.concept,
                ),
            ))

            self._emit_whisper_splash(
                mutations, state, mortal,
                domain_vectors=combined_dvs,
                culture_vectors=combined_cvs,
                per_unit_delta=effectiveness * 0.1,
                note_prefix="Shape Dream",
            )

            ireg = get_imago_registry()
            dom_node = ireg.get_node(dominant_id)
            sup_node = ireg.get_node(suppressed_id)
            dom_name = dom_node.name if dom_node else dominant_id
            sup_name = sup_node.name if sup_node else suppressed_id
            narrative = (
                f"You shaped {mortal.name}'s dreams around {dom_name} and {sup_name}. "
                f"In sleep, {dom_name} took stronger root than {sup_name}. "
                f"Effectiveness: {effectiveness:.0%}."
            )

        # ── Probability Nudge ─────────────────────────
        elif isinstance(intent, ProbabilityNudgeIntent):
            if outcome == ActionOutcome.FAILURE:
                return mutations, "The probability nudge dissipated without effect."

            effectiveness = intent.nudge_strength
            if outcome == ActionOutcome.PARTIAL:
                effectiveness *= 0.4

            target_id = instance.target_id
            for dv in intent.domain_vectors:
                mutations.append(StateMutation(
                    mutation_type=MutationType.BELIEF_SHIFT,
                    target_id=target_id,
                    field="dominant_beliefs",
                    delta=dv.direction * effectiveness * 0.15,
                    new_value=dv.domain_tag,
                    note=(
                        f"Probability nudge: '{intent.event_description[:40]}' "
                        f"toward '{intent.desired_outcome[:40]}'"
                    ),
                ))

            narrative = (
                f"You nudged the odds around '{intent.event_description}'. "
                f"Desired outcome: '{intent.desired_outcome}'. "
                f"Strength applied: {effectiveness:.0%}."
            )

        # ── Proxius Directive ─────────────────────────
        elif isinstance(intent, ProxiusDirectiveIntent):
            proxius = state.mortals.get(str(instance.proxius_id))
            if not proxius:
                return mutations, "No Proxius found to receive directive."

            # Reactivate a dormant Proxius when a directive is issued
            if proxius.status == MortalStatus.DORMANT:
                mutations.append(StateMutation(
                    mutation_type=MutationType.MORTAL_STATUS,
                    target_id=proxius.id,
                    field="status",
                    new_value=MortalStatus.ACTIVE.value,
                    note=f"{proxius.name} reactivated by directive",
                ))

            # Override reliability roll: alignment-modified low failure rate
            # 0% at align=1.0, 2% at align=0.5, 4% at align=0.0
            _fail_chance = max(0.0, 0.02 + (0.5 - proxius.alignment) * 0.04)
            outcome = ActionOutcome.FAILURE if rng.random() < _fail_chance else ActionOutcome.SUCCESS

            if outcome == ActionOutcome.FAILURE:
                narrative = (
                    f"The directive did not reach {proxius.name} clearly. "
                    f"They remain without guidance."
                )
            else:
                # Set goal on the Proxius — they will act autonomously each tick
                imago_id = intent.imago_node_id or ""
                # Build a human-readable label for audit/report narratives
                _ireg = get_imago_registry()
                _node = _ireg.get_node(imago_id) if imago_id else None
                _imago_name = _node.name if _node else (imago_id.split(":")[-1].title() if imago_id else "directive")
                _loc = state.locations.get(str(proxius.current_location))
                _loc_name = _loc.name if _loc else "unknown location"

                # If re-targeting the same Imāgō at the same source Pop, reuse the existing
                # goal Pop (Pop B) rather than creating a new splinter next tick.
                _existing_goal_pop_id: Optional[UUID] = None
                if intent.target_pop_id and imago_id:
                    _src_pop = state.pops.get(str(intent.target_pop_id))
                    if _src_pop:
                        for _child_id in _src_pop.child_pop_ids:
                            _child = state.pops.get(str(_child_id))
                            if _child and _child.preaching_imago_id == imago_id:
                                _existing_goal_pop_id = _child.id
                                break

                goal = ProxiusGoal(
                    imago_node_id=imago_id,
                    label=f"Preaching {_imago_name} in {_loc_name}",
                    target_location_id=proxius.current_location,
                    target_civilization_id=intent.target_civilization_id,
                    domain_vectors=list(intent.domain_vectors),
                    culture_vectors=list(intent.culture_vectors),
                    latitude=intent.latitude,
                    constraints=list(intent.constraints),
                    started_at_tick=state.tick_number,
                    source_pop_id=intent.target_pop_id,
                    goal_pop_id=_existing_goal_pop_id,
                    # Held until the splinter actually forms (or the directive
                    # ends, whichever happens first). Only set when there was
                    # no pre-existing splinter at directive time.
                    goal_pop_name=intent.goal_pop_name if _existing_goal_pop_id is None else None,
                )
                mutations.append(StateMutation(
                    mutation_type=MutationType.PROXIUS_GOAL_SET,
                    target_id=proxius.id,
                    field="active_goal",
                    new_value=goal,
                    note=f"Preach Imāgō: '{intent.imago_node_id or 'no imago'}'",
                ))

                dedication = proxius.alignment * (1.0 - intent.latitude * 0.3)
                if dedication > 0.7:
                    dedication_note = "with clear purpose"
                elif dedication > 0.4:
                    dedication_note = "with some reservation"
                else:
                    dedication_note = "reluctantly"
                if intent.imago_node_id:
                    ireg = get_imago_registry()
                    node = ireg.get_node(intent.imago_node_id)
                    imago_label = f" preach {node.name}" if node else ""
                else:
                    imago_label = ""
                narrative = (
                    f"Proxius {proxius.name} has been sent to {imago_label}. "
                    f"They will pursue it {dedication_note}."
                )

        # ── Essence Harvest ───────────────────────────
        elif isinstance(intent, EssenceHarvestIntent):
            if outcome == ActionOutcome.FAILURE:
                return mutations, "The Underreal offered nothing this time."

            # Yield modulated by concealment priority
            # High concealment = slower, but less apparent leak
            base_yield = 0.3
            if outcome == ActionOutcome.PARTIAL:
                base_yield *= 0.5
            concealment_factor = intent.concealment_priority
            actual_yield = base_yield * (0.5 + concealment_factor * 0.5)
            apparent_leak = base_yield * (1.0 - concealment_factor) * 0.5

            mutations.append(StateMutation(
                mutation_type=MutationType.ESSENCE_CHANGE,
                target_id=state.demiurge.id,
                field="actual",
                delta=actual_yield,
                note="Essence harvested from Underreal",
            ))
            if apparent_leak > 0.0:
                mutations.append(StateMutation(
                    mutation_type=MutationType.ESSENCE_CHANGE,
                    target_id=state.demiurge.id,
                    field="apparent",
                    delta=apparent_leak,
                    note="Essence concealment leak during harvest",
                ))

            narrative = (
                f"Harvested {actual_yield:.2f} Essence from the Underreal. "
                f"Apparent leak: {apparent_leak:.2f}. "
                f"Concealment integrity held at {intent.concealment_priority:.0%} priority."
            )

        # ── Omen / Manifestation ──────────────────────
        elif isinstance(intent, OmenIntent):
            if outcome == ActionOutcome.FAILURE:
                return mutations, "The omen dissipated — mortals found no meaning in it."

            base_pass = (
                OMEN_PASS_BASE_SUCCESS if outcome == ActionOutcome.SUCCESS
                else OMEN_PASS_BASE_PARTIAL
            )
            aware_eff = 1.0 if outcome == ActionOutcome.SUCCESS else 0.5

            omen_world_id = self._resolve_world_id(instance, state)
            scope_civ_id = str(intent.civilization_scope) if intent.civilization_scope else None

            # The omen's intended effect E — raw vector directions scaled by OMEN_BASE.
            domain_components = [
                (dv.domain_tag, dv.direction * OMEN_BASE) for dv in intent.domain_vectors
            ]
            culture_components = [
                (cv.culture_tag, cv.direction * OMEN_BASE) for cv in intent.culture_vectors
            ]

            # Targets: every Pop on the world (optionally civ-scoped) ...
            target_pops: list = []
            if omen_world_id:
                world_pops = self._pops_on_world(str(omen_world_id), state)
                target_pops = [
                    p for p in world_pops
                    if scope_civ_id is None or str(p.civilization_id) == scope_civ_id
                ]
            for pop in target_pops:
                self._resolve_omen_target(
                    mutations, state, pop, False,
                    domain_components, culture_components,
                    intent.framing, base_pass, intent.target_loc_id, rng,
                )

            # ... and every active mortal on the world (each a size-1 Pop).
            target_mortals: list = []
            if omen_world_id:
                for mortal in state.mortals.values():
                    if mortal.status != MortalStatus.ACTIVE:
                        continue
                    if _resolve_world_id_for(state, mortal.current_location) != str(omen_world_id):
                        continue
                    if scope_civ_id is not None and str(mortal.civilization_id) != scope_civ_id:
                        continue
                    target_mortals.append(mortal)
            for mortal in target_mortals:
                self._resolve_omen_target(
                    mutations, state, mortal, True,
                    domain_components, culture_components,
                    intent.framing, base_pass, intent.target_loc_id, rng,
                )

            # Divine awareness: raise for all civs represented in target Pops
            for cid in {str(p.civilization_id) for p in target_pops if p.civilization_id}:
                civ_obj = state.civilizations.get(cid)
                if civ_obj:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.CIVILIZATION_STAT,
                        target_id=civ_obj.id,
                        field="divine_awareness",
                        delta=0.1 * aware_eff,
                        note=f"Omen raises divine awareness in {civ_obj.name}",
                    ))

            scope_desc = (
                state.civilizations[scope_civ_id].name
                if scope_civ_id and scope_civ_id in state.civilizations
                else "all populations"
            )
            narrative = (
                f"The omen '{intent.sign_description}' manifested for {scope_desc}. "
                f"Intended: '{intent.intended_interpretation}'. "
                f"{len(target_pops)} population(s) and {len(target_mortals)} notable "
                f"mortal(s) each read it through their own lens."
            )

            # Social ripple: a SPIKE_FADE event carrying only the divine-awareness
            # and Luminary-attention echo. The belief/culture shotgun resolved
            # once, above — the event holds no domain/culture vectors.
            mutations.append(StateMutation(
                mutation_type=MutationType.EVENT_EMITTED,
                target_id=None,
                field="active_events",
                new_value=Event(
                    event_type=EventType.OMEN,
                    curve=StrengthCurve.SPIKE_FADE,
                    source_action_id=instance.action_definition_id,
                    created_at_tick=state.tick_number,
                    duration=5,
                    base_strength=aware_eff,
                    decay_rate=0.6,
                    target_civilization_id=None,
                    target_world_id=omen_world_id,
                    target_loc_id=intent.target_loc_id,
                    domain_vectors=[],
                    culture_vectors=[],
                    domain_shift_rate=0.0,
                    divine_awareness_rate=0.03,
                    attention_per_tick=0.04,
                    imago_node_id=getattr(intent, "imago_node_id", None),
                    sign_description=intent.sign_description,
                ),
            ))

        # ── Civilizational Development ────────────────
        elif isinstance(intent, DevelopmentIntent):
            if outcome == ActionOutcome.FAILURE:
                return mutations, "The developmental nudge failed to take root."

            effectiveness = 1.0 if outcome == ActionOutcome.SUCCESS else 0.4
            civ_obj = state.civilizations.get(str(instance.target_id)) if instance.target_id else None
            if not civ_obj:
                return mutations, "Target civilization not found."

            for dv in intent.domain_vectors:
                mutations.append(StateMutation(
                    mutation_type=MutationType.BELIEF_SHIFT,
                    target_id=civ_obj.id,
                    field="dominant_beliefs",
                    delta=dv.direction * effectiveness * 0.1,
                    new_value=dv.domain_tag,
                    note=f"Development nudge: '{intent.target_aspect[:40]}'",
                ))

            narrative = (
                f"Civilizational development nudge toward '{intent.target_aspect}' "
                f"applied to {civ_obj.name}. "
                f"Effectiveness: {effectiveness:.0%}."
            )

            # Emit a FLAT event for multi-tick continuation.
            # If an active DEVELOPMENT_NUDGE already targets this civ, give it a
            # sustained bonus instead of stacking a second event.
            existing_dev_event: Optional[Event] = None
            for ev in state.active_events.values():
                if (
                    ev.event_type == EventType.DEVELOPMENT_NUDGE
                    and ev.target_civilization_id == civ_obj.id
                    and not ev.is_expired(state.tick_number)
                ):
                    existing_dev_event = ev
                    break

            if existing_dev_event is not None:
                existing_dev_event.base_strength = min(
                    1.0, existing_dev_event.base_strength + 0.05
                )
            else:
                mutations.append(StateMutation(
                    mutation_type=MutationType.EVENT_EMITTED,
                    target_id=None,
                    field="active_events",
                    new_value=Event(
                        event_type=EventType.DEVELOPMENT_NUDGE,
                        curve=StrengthCurve.FLAT,
                        source_action_id=instance.action_definition_id,
                        created_at_tick=state.tick_number,
                        duration=6,
                        base_strength=effectiveness,
                        target_civilization_id=civ_obj.id,
                        domain_vectors=intent.domain_vectors,
                        domain_shift_rate=0.05,
                    ),
                ))

            # Splash: distribute fraction of development nudge across Pops on the civ's worlds.
            civ_pop_loc_ids = {str(p.current_location) for p in state.pops.values()
                               if str(p.civilization_id) == str(civ_obj.id)}
            dev_splash_pops = [
                p for p in state.pops.values()
                if str(p.civilization_id) == str(civ_obj.id)
                and str(p.current_location) in civ_pop_loc_ids
            ]
            if dev_splash_pops:
                total_inv = sum(1.0 / p.size_fractional for p in dev_splash_pops)
                for sp in dev_splash_pops:
                    inv_weight = (1.0 / sp.size_fractional) / total_inv if total_inv > 0 else 1.0
                    for dv in intent.domain_vectors:
                        splash_delta = dv.direction * effectiveness * 0.1 * OMEN_POP_SPLASH * inv_weight
                        if abs(splash_delta) > 1e-5:
                            mutations.append(StateMutation(
                                mutation_type=MutationType.POP_BELIEF_SHIFT,
                                target_id=sp.id,
                                field=dv.domain_tag,
                                delta=splash_delta,
                                note=f"Development nudge splash to {sp.stratum} Pop",
                            ))
                            self._emit_lineage_bleed(
                                mutations, state, sp, dv.domain_tag,
                                splash_delta, "development",
                            )

        # ── Luminary Petition ─────────────────────────
        elif isinstance(intent, LuminaryPetitionIntent):
            luminary = state.luminaries.get(str(instance.target_id)) if instance.target_id else None
            if not luminary:
                return mutations, "Target Luminary not found."

            if defn.name == "Report to Luminary":
                if outcome == ActionOutcome.SUCCESS:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.DISPOSITION_CHANGE,
                        target_id=luminary.id,
                        field="results",
                        delta=0.05,
                        note=f"Report to {luminary.name}: favorable reception",
                    ))
                    mutations.append(StateMutation(
                        mutation_type=MutationType.FOOTPRINT_CHANGE,
                        target_id=luminary.id,
                        field="attention",
                        delta=-0.07,
                        note=f"Report to {luminary.name}: attention eased",
                    ))
                    narrative = (
                        f"Your report on '{intent.subject}' was well received by {luminary.name}. "
                        f"Their attention eases slightly."
                    )
                elif outcome == ActionOutcome.PARTIAL:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.FOOTPRINT_CHANGE,
                        target_id=luminary.id,
                        field="attention",
                        delta=-0.03,
                        note=f"Report to {luminary.name}: partial acknowledgement",
                    ))
                    narrative = (
                        f"Your report on '{intent.subject}' was received without comment. "
                        f"{luminary.name} seems mildly satisfied."
                    )
                else:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.DISPOSITION_CHANGE,
                        target_id=luminary.id,
                        field="methods",
                        delta=-0.02,
                        note=f"Report to {luminary.name}: poorly received",
                    ))
                    mutations.append(StateMutation(
                        mutation_type=MutationType.FOOTPRINT_CHANGE,
                        target_id=luminary.id,
                        field="attention",
                        delta=0.05,
                        note=f"Report to {luminary.name}: raised suspicion",
                    ))
                    narrative = (
                        f"Your report on '{intent.subject}' was poorly received. "
                        f"{luminary.name} appears displeased."
                    )

            elif defn.name == "Dispute Demand":
                if outcome == ActionOutcome.SUCCESS:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.DISPOSITION_CHANGE,
                        target_id=luminary.id,
                        field="methods",
                        delta=0.04,
                        note=f"Dispute with {luminary.name}: argument accepted",
                    ))
                    narrative = (
                        f"Your dispute regarding '{intent.subject}' was acknowledged. "
                        f"{luminary.name} conceded the point."
                    )
                elif outcome == ActionOutcome.PARTIAL:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.DISPOSITION_CHANGE,
                        target_id=luminary.id,
                        field="methods",
                        delta=-0.03,
                        note=f"Dispute with {luminary.name}: poorly received",
                    ))
                    mutations.append(StateMutation(
                        mutation_type=MutationType.FOOTPRINT_CHANGE,
                        target_id=luminary.id,
                        field="attention",
                        delta=0.08,
                        note=f"Dispute with {luminary.name}: attention spike",
                    ))
                    narrative = (
                        f"Your dispute regarding '{intent.subject}' was heard but did not land well. "
                        f"{luminary.name} is watching more closely."
                    )
                else:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.DISPOSITION_CHANGE,
                        target_id=luminary.id,
                        field="methods",
                        delta=-0.10,
                        note=f"Dispute with {luminary.name}: infuriated",
                    ))
                    mutations.append(StateMutation(
                        mutation_type=MutationType.FOOTPRINT_CHANGE,
                        target_id=luminary.id,
                        field="attention",
                        delta=0.15,
                        note=f"Dispute with {luminary.name}: severe attention spike",
                    ))
                    narrative = (
                        f"Your dispute regarding '{intent.subject}' infuriated {luminary.name}. "
                        f"This has consequences."
                    )

            elif defn.name == "Petition for Constraint Relaxation":
                if outcome == ActionOutcome.SUCCESS:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.DISPOSITION_CHANGE,
                        target_id=luminary.id,
                        field="methods",
                        delta=0.02,
                        note=f"Constraint petition to {luminary.name}: acknowledged",
                    ))
                    mutations.append(StateMutation(
                        mutation_type=MutationType.DISPOSITION_CHANGE,
                        target_id=luminary.id,
                        field="results",
                        delta=-0.02,
                        note=f"Constraint petition: reveals strain against constraint",
                    ))
                    narrative = (
                        f"Your petition regarding '{intent.subject}' was acknowledged by {luminary.name}. "
                        f"The latitude may widen — though the petition itself signals you have been straining."
                    )
                elif outcome == ActionOutcome.PARTIAL:
                    narrative = (
                        f"{luminary.name} heard your petition regarding '{intent.subject}' "
                        f"but offered no commitments."
                    )
                else:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.DISPOSITION_CHANGE,
                        target_id=luminary.id,
                        field="methods",
                        delta=-0.05,
                        note=f"Constraint petition to {luminary.name}: impertinent",
                    ))
                    mutations.append(StateMutation(
                        mutation_type=MutationType.FOOTPRINT_CHANGE,
                        target_id=luminary.id,
                        field="attention",
                        delta=0.10,
                        note=f"Constraint petition rejected: scrutiny raised",
                    ))
                    narrative = (
                        f"{luminary.name} found your petition regarding '{intent.subject}' impertinent. "
                        f"The request has drawn greater scrutiny."
                    )

            elif outcome == ActionOutcome.SUCCESS:
                mutations.append(StateMutation(
                    mutation_type=MutationType.DISPOSITION_CHANGE,
                    target_id=luminary.id,
                    field="results",
                    delta=0.05,
                    note=f"Petition '{intent.subject[:40]}' received favorably",
                ))
                narrative = (
                    f"Your petition regarding '{intent.subject}' was received. "
                    f"{luminary.name} acknowledged your position ({intent.tone})."
                )
            elif outcome == ActionOutcome.PARTIAL:
                narrative = (
                    f"Your petition regarding '{intent.subject}' was heard but not acted upon. "
                    f"{luminary.name} remains noncommittal."
                )
            else:
                mutations.append(StateMutation(
                    mutation_type=MutationType.DISPOSITION_CHANGE,
                    target_id=luminary.id,
                    field="methods",
                    delta=-0.03,
                    note=f"Petition '{intent.subject[:40]}' dismissed",
                ))
                narrative = (
                    f"Your petition regarding '{intent.subject}' was dismissed. "
                    f"{luminary.name} appeared displeased by the request."
                )

        # ── Salvage from Underreal ────────────────────
        elif isinstance(intent, SalvageIntent):
            if outcome == ActionOutcome.FAILURE:
                return mutations, (
                    "The Underreal yielded nothing coherent. "
                    "The concept dissolved on contact."
                )

            target_world = state.worlds.get(str(intent.target_world_id))  # type: ignore[assignment]
            if not target_world:
                return mutations, "Target world for salvage not found."

            if outcome == ActionOutcome.CHAOTIC_RESULT:
                for dv in intent.domain_vectors:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.DOMAIN_EXPRESSION,
                        target_id=target_world.id,
                        field="domain_expression",
                        delta=-dv.direction * 0.2,
                        new_value=dv.domain_tag,
                        note=f"Chaotic salvage on {target_world.name}: concept inverted",
                    ))
                narrative = (
                    f"Something emerged from the Underreal, but not '{intent.desired_concept}'. "
                    f"The concept manifested on {target_world.name} in an unexpected form."
                )
            else:
                effectiveness = 1.0 if outcome == ActionOutcome.SUCCESS else 0.5
                for dv in intent.domain_vectors:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.DOMAIN_EXPRESSION,
                        target_id=target_world.id,
                        field="domain_expression",
                        delta=dv.direction * effectiveness * 0.2,
                        new_value=dv.domain_tag,
                        note=f"Salvaged '{intent.desired_concept[:40]}' on {target_world.name}",
                    ))
                narrative = (
                    f"Salvaged '{intent.desired_concept}' from the Underreal. "
                    f"The concept has taken root on {target_world.name}. "
                    f"Effectiveness: {effectiveness:.0%}."
                )

        # ── Seed World ────────────────────────────────
        elif isinstance(intent, SeedWorldIntent):
            world_obj = state.worlds.get(str(instance.target_id)) if instance.target_id else None
            if not world_obj:
                return mutations, "Target world not found."
            if world_obj.condition != LocCondition.BARREN:
                return mutations, (
                    f"{world_obj.name} already sustains life — seeding had no effect."
                )
            if outcome == ActionOutcome.FAILURE:
                return mutations, (
                    f"The seeding of {world_obj.name} failed to take hold. "
                    f"The world remains barren."
                )

            new_condition = (
                LocCondition.STABLE if outcome == ActionOutcome.SUCCESS
                else LocCondition.STRESSED
            )
            new_species = Species(
                name=intent.species_name,
                origin_world_id=world_obj.id,
                sapient=intent.sapient,
                transplanted=False,
                lifespan_min=intent.lifespan_min,
                lifespan_max=intent.lifespan_max,
                bio_tags=intent.bio_tags,
            )
            mutations.append(StateMutation(
                mutation_type=MutationType.WORLD_CONDITION,
                target_id=world_obj.id,
                field="condition",
                new_value=new_condition.value,
                note=f"Life seeded on {world_obj.name}",
            ))
            mutations.append(StateMutation(
                mutation_type=MutationType.SPECIES_CREATED,
                target_id=world_obj.id,
                field="",
                new_value=new_species,
                note=f"Species '{intent.species_name}' introduced to {world_obj.name}",
            ))
            sapient_note = " They are already sapient." if intent.sapient else ""
            if outcome == ActionOutcome.SUCCESS:
                narrative = (
                    f"Life has taken root on {world_obj.name}: the {intent.species_name}."
                    f"{sapient_note}"
                )
            else:
                narrative = (
                    f"Life clings to {world_obj.name} — the {intent.species_name} survive, "
                    f"but the world is stressed. They will need tending."
                )

        # ── Uplift Species ────────────────────────────
        elif isinstance(intent, UpliftSpeciesIntent):
            sp = state.species.get(str(intent.species_id))
            if not sp:
                return mutations, "Target species not found."
            if sp.sapient:
                return mutations, f"The {sp.name} are already sapient."
            if outcome == ActionOutcome.FAILURE:
                return mutations, (
                    f"The uplift of the {sp.name} failed to catalyze. "
                    f"They remain pre-sapient."
                )

            effectiveness = 1.0 if outcome == ActionOutcome.SUCCESS else 0.5
            mutations.append(StateMutation(
                mutation_type=MutationType.SPECIES_UPLIFTED,
                target_id=sp.id,
                field="sapient",
                new_value=True,
                note=f"{sp.name} uplifted to sapience",
            ))
            for dv in intent.domain_vectors:
                # Sapience flavor pushes domain expression on origin world
                if sp.origin_world_id:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.DOMAIN_EXPRESSION,
                        target_id=sp.origin_world_id,
                        field="domain_expression",
                        delta=dv.direction * effectiveness * 0.15,
                        new_value=dv.domain_tag,
                        note=f"Uplift of {sp.name}: emergent domain flavor",
                    ))
            narrative = (
                f"The {sp.name} have crossed the threshold into sapience. "
                f"A civilization will emerge from them in time."
            )
            if outcome == ActionOutcome.PARTIAL:
                narrative += " The transition is incomplete — they are fragile."

        return mutations, narrative

    def _apply_action_mutations(
        self,
        state: SimulationState,
        action_result: ActionProcessingResult,
    ) -> SimulationState:
        all_mutations = [
            m for entry in action_result.entries
            for m in entry.mutations
        ]
        return self._apply_mutations(state, all_mutations)

    # ─────────────────────────────────────────
    # PHASE 3: DOMAIN PROFILING
    # ─────────────────────────────────────────

    @staticmethod
    def _cosine_similarity(a: dict[str, float], b: dict[str, float]) -> float:
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

    def _emit_lineage_bleed(
        self,
        mutations: list,
        state: "SimulationState",
        pop: object,
        domain_tag: str,
        base_delta: float,
        source_note: str,
    ) -> None:
        """Bleed LINEAGE_BLEED_FRACTION × similarity of a splash delta to lineage relatives."""
        relatives = []
        parent_id = getattr(pop, "parent_pop_id", None)
        if parent_id:
            parent = state.pops.get(str(parent_id))
            if parent:
                relatives.append(parent)
        for child_id in getattr(pop, "child_pop_ids", []):
            child = state.pops.get(str(child_id))
            if child:
                relatives.append(child)
        for rel in relatives:
            sim = self._cosine_similarity(
                getattr(pop, "dominant_beliefs", {}),
                getattr(rel, "dominant_beliefs", {}),
            )
            bleed_delta = base_delta * LINEAGE_BLEED_FRACTION * sim
            if abs(bleed_delta) > 1e-5:
                mutations.append(StateMutation(
                    mutation_type=MutationType.POP_BELIEF_SHIFT,
                    target_id=rel.id,
                    field=domain_tag,
                    delta=bleed_delta,
                    note=f"Lineage bleed ({source_note} → {getattr(rel, 'stratum', 'Pop')})",
                ))

    def _recompute_civ_dominant_beliefs(self, state: SimulationState, cfg: TickConfig) -> None:
        """
        Overwrite each Civilization.dominant_beliefs with the size-fractional-weighted
        average of its constituent Pop beliefs. Prunes entries below BELIEF_FLOOR.
        Pops at non-core locations (not in civ.core_locs) are weighted down by
        cfg.peripheral_pop_belief_weight. Called once per tick after Phase 2.5.
        """

        # Build PopLocation → parent world index
        pop_loc_to_world: dict[str, str] = {}
        for wid, world in state.worlds.items():
            for cid in world.child_ids:
                loc = state.locations.get(str(cid))
                if loc is not None and hasattr(loc, "pop_ids"):
                    pop_loc_to_world[str(cid)] = wid

        for civ in state.civilizations.values():
            if not civ.pop_ids:
                continue

            core_loc_strs = {str(loc_id) for loc_id in civ.core_locs}

            weighted: dict[str, float] = {}
            total_weight = 0.0

            for pid in civ.pop_ids:
                pop = state.pops.get(str(pid))
                if pop is None:
                    continue
                world_id = pop_loc_to_world.get(str(pop.current_location), "")
                is_core = (not core_loc_strs) or (world_id in core_loc_strs)
                base_w = max(0.001, pop.size_fractional)
                w = base_w if is_core else base_w * cfg.peripheral_pop_belief_weight
                total_weight += w
                for tag, strength in pop.dominant_beliefs.items():
                    weighted[tag] = weighted.get(tag, 0.0) + strength * w

            if total_weight == 0.0:
                continue

            new_beliefs = {
                tag: min(1.0, val / total_weight)
                for tag, val in weighted.items()
                if val / total_weight > BELIEF_FLOOR
            }
            civ.dominant_beliefs = new_beliefs

    def _recompute_civ_culture_tags(self, state: SimulationState, cfg: TickConfig) -> None:
        """
        Overwrite each Civilization.culture_tags with the size-fractional-weighted
        average of its constituent Pop culture_tags. Pops at non-core locations are
        weighted down by cfg.peripheral_pop_culture_weight.
        """

        pop_loc_to_world: dict[str, str] = {}
        for wid, world in state.worlds.items():
            for cid in world.child_ids:
                loc = state.locations.get(str(cid))
                if loc is not None and hasattr(loc, "pop_ids"):
                    pop_loc_to_world[str(cid)] = wid

        for civ in state.civilizations.values():
            if not civ.pop_ids:
                continue

            core_loc_strs = {str(loc_id) for loc_id in civ.core_locs}

            weighted: dict[str, float] = {}
            total_weight = 0.0

            for pid in civ.pop_ids:
                pop = state.pops.get(str(pid))
                if pop is None:
                    continue
                world_id = pop_loc_to_world.get(str(pop.current_location), "")
                is_core = (not core_loc_strs) or (world_id in core_loc_strs)
                base_w = max(0.001, pop.size_fractional)
                w = base_w if is_core else base_w * cfg.peripheral_pop_culture_weight
                total_weight += w
                for tag, strength in pop.culture_tags.items():
                    weighted[tag] = weighted.get(tag, 0.0) + strength * w

            if total_weight == 0.0:
                continue

            civ.culture_tags = {
                tag: min(1.0, val / total_weight)
                for tag, val in weighted.items()
                if val / total_weight > CULTURE_FLOOR
            }

    def _build_domain_profile(
        self,
        state: SimulationState,
    ) -> "UniverseDomainProfile":
        """
        Survey all civilizations and aggregate their
        domain_expression and dominant_beliefs into a
        universe-wide profile. Weighted by civilization
        scale and health.
        """
        from collections import defaultdict

        scale_weights = {
            "nascent":        0.1,
            "tribal":         0.2,
            "city_state":     0.3,
            "regional":       0.5,
            "continental":    0.7,
            "planetary":      1.0,
            "interplanetary": 1.5,
            "interstellar":   2.0,
        }

        raw_scores: dict[str, float] = defaultdict(float)
        total_weight = 0.0

        for civ in state.civilizations.values():
            w = scale_weights.get(civ.scale, 0.5) * civ.health.overall()
            total_weight += w
            for belief_tag, strength in civ.dominant_beliefs.items():
                raw_scores[belief_tag] += w * strength

        # Also factor in world-level domain_expression
        for world in state.worlds.values():
            world_weight = 0.3  # Worlds contribute less than civilizations
            for tag, strength in world.domain_expression.items():
                raw_scores[tag] += world_weight * strength
                total_weight += world_weight * strength

        # Universe baseline: treat universe_domain_expression like a SignificantLocation.
        # Missing tags default to 0.1.
        universe_expr = state.universe.universe_domain_expression
        universe_weight = 0.3
        for tag in get_domain_registry().all_tags:
            strength = universe_expr.get(tag, 0.1)
            raw_scores[tag] += universe_weight * strength
            total_weight += universe_weight * strength

        if total_weight == 0.0:
            return UniverseDomainProfile(
                timestamp=state.universe.current_age
            )

        normalized = {
            tag: min(1.0, score / total_weight)
            for tag, score in raw_scores.items()
        }

        return UniverseDomainProfile(
            timestamp=state.universe.current_age,
            scores=normalized,
        )

    # ─────────────────────────────────────────
    # PHASE 4: EVALUATION
    # ─────────────────────────────────────────

    def _run_evaluations(
        self,
        state: SimulationState,
        profile: "UniverseDomainProfile",
        cfg: TickConfig,
    ) -> list["LuminaryEvaluation"]:

        evaluations = []
        engine = EvaluationEngine()
        prev_profile = state.previous_domain_profile or profile

        # Pre-collect domain tags for every Luminary for Realpolitik lookups.
        # Map: luminary_id_str -> list[str] of domain tags
        all_lum_domain_tags: dict[str, list[str]] = {}
        for lid_inner, lum_inner in state.luminaries.items():
            all_lum_domain_tags[lid_inner] = list(lum_inner.domains.keys())

        for lid, luminary in state.luminaries.items():
            ticks_since = state.ticks_since_evaluation.get(lid, cfg.evaluation_interval)
            current_att = state.luminary_attention.get(lid, 0.2)

            personality = (
                self._domain_registry.compute_personality(luminary.domains)
                if self._domain_registry else LuminaryPersonality()
            )

            # Evaluation interval scaled by reactivity: [5, 15]
            effective_interval = cfg.evaluation_interval * (1.0 - personality.reactivity * 0.5)
            if personality.capriciousness > 0:
                effective_interval += self._rng.gauss(0, personality.capriciousness * 1.5)
            effective_interval = max(5.0, effective_interval)

            # Attention threshold scaled by reactivity: [0.4, 0.8]
            effective_attention_threshold = 0.6 - personality.reactivity * 0.2

            should_evaluate = (
                ticks_since >= effective_interval
                or current_att > effective_attention_threshold
            )
            if not should_evaluate:
                state.ticks_since_evaluation[lid] = ticks_since + 1
                continue

            state.ticks_since_evaluation[lid] = 0.0

            luminary_domain_tags = all_lum_domain_tags[lid]

            # Combined domain tags of all fellow Luminaries (for Realpolitik)
            fellow_lum_tags: set[str] = set()
            for other_lid, other_tags in all_lum_domain_tags.items():
                if other_lid != lid:
                    fellow_lum_tags.update(other_tags)

            # Attention level — populated by active event continuation in Phase 1
            attention_triggers: list[AttentionTrigger] = (
                state.pending_attention_triggers.get(lid, [])
            )
            attention_level = engine.compute_attention_level(
                current_att, attention_triggers
            )

            # Domain alignment
            domain_scores, overall_alignment = engine.score_domain_alignment(
                luminary_domain_tags, profile, prev_profile
            )

            prev_overall = sum(
                prev_profile.scores.get(t, 0.0)
                for t in luminary_domain_tags
            ) / max(1, len(luminary_domain_tags))

            # Constraint evaluations — per-Luminary constraints
            constraint_evals = []
            for constraint in luminary.constraints:
                if isinstance(constraint, FootprintConstraint):
                    constraint_evals.extend(
                        engine.evaluate_footprint_constraint(
                            constraint, state.demiurge.footprint, attention_level
                        )
                    )
                elif isinstance(constraint, ResultsConstraint):
                    constraint_evals.extend(
                        engine.evaluate_results_constraint(constraint, luminary)
                    )

            # Pantheon collective constraints fan out to every Luminary
            for constraint in state.pantheon.collective_constraints:
                if isinstance(constraint, FootprintConstraint):
                    constraint_evals.extend(
                        engine.evaluate_footprint_constraint(
                            constraint, state.demiurge.footprint, attention_level
                        )
                    )
                elif isinstance(constraint, ResultsConstraint):
                    constraint_evals.extend(
                        engine.evaluate_results_constraint(constraint, luminary)
                    )

            # Footprint assessment
            fp_assessment = FootprintAssessment(
                luminary_id=luminary.id,
                perceived_footprint={},
                overall_methods_delta=sum(
                    ce.disposition_delta for ce in constraint_evals
                ),
            )

            # Essence suspicion
            recent_underreal = sum(
                1 for entry in []  # Would scan recent action log
                # Placeholder — real impl checks event log
            )
            essence_suspicion = engine.evaluate_essence_suspicion(
                luminary_id=luminary.id,
                apparent_stockpile=state.essence.apparent,
                concealment_integrity=state.essence.concealment_integrity,
                recent_underreal_actions=recent_underreal,
                attention_level=attention_level,
            )

            # Essence satisfaction — record period weighted production, reset accumulator
            domain_production = state.luminary_production_this_eval.get(lid, 0.0)
            sorted_affs = [
                min(0.8, v)
                for _, v in sorted(luminary.domains.items(), key=lambda x: (-x[1], x[0]))
            ]
            effective_affinity = sum(aff * (cfg.luminary_essence_decay ** i) for i, aff in enumerate(sorted_affs))
            base_threshold = effective_affinity * cfg.luminary_essence_baseline_rate * ticks_since
            lum_threshold = base_threshold + luminary.essence_expectation_raised
            essence_satisfaction = evaluate_essence_satisfaction(
                luminary_id=luminary.id,
                domain_production=domain_production,
                production_log=luminary.essence_received_log,
                threshold=lum_threshold,
            )
            luminary.essence_received_log.append(domain_production)
            if len(luminary.essence_received_log) > 2:
                luminary.essence_received_log = luminary.essence_received_log[-2:]
            state.luminary_production_this_eval[lid] = 0.0

            # Update raised expectations and shortfall counter
            if essence_satisfaction.above_threshold:
                excess = max(0.0, domain_production - base_threshold)
                luminary.essence_expectation_raised = excess * cfg.luminary_essence_recall
                luminary.consecutive_essence_shortfalls = 0
            else:
                luminary.consecutive_essence_shortfalls += 1
                if luminary.consecutive_essence_shortfalls >= 2:
                    luminary.essence_expectation_raised = max(
                        0.0, luminary.essence_expectation_raised - 0.10
                    )
                    luminary.consecutive_essence_shortfalls = 0

            # Disposition delta assembly
            delta = DispositionDelta()

            results_reason = engine.domain_alignment_to_results_delta(
                overall_alignment, prev_overall, personality
            )
            delta.results += results_reason.delta
            delta.reasons.append(results_reason)

            # Similarity-weighted influence from related/opposing expressed domains
            sim_modifier = engine.similarity_results_modifier(
                luminary_domain_tags=luminary_domain_tags,
                fellow_luminary_tags=fellow_lum_tags,
                current_profile=profile,
                personality=personality,
                registry=self._domain_registry,
            )
            if abs(sim_modifier) > 0.001:
                delta.results += sim_modifier
                delta.reasons.append(DispositionDeltaReason(
                    axis="results",
                    delta=sim_modifier,
                    source="domain_similarity_influence",
                    note="Expressed domains adjacent or opposing to Luminary domains",
                ))

            # Capriciousness: mercurial Luminaries add random variance to evaluations
            sigma = max(0.0, personality.capriciousness) * 0.1
            if sigma > 0.01:
                capricious_swing = self._rng.gauss(0, sigma)
                delta.results += capricious_swing
                delta.methods += capricious_swing * 0.5

            methods_delta = (
                fp_assessment.overall_methods_delta
                + essence_suspicion.disposition_delta
            )
            delta.methods += methods_delta
            delta.reasons.append(DispositionDeltaReason(
                axis="methods",
                delta=methods_delta,
                source="footprint_and_essence",
            ))

            # Essence satisfaction feeds results disposition
            if abs(essence_satisfaction.disposition_delta) > 0.001:
                delta.results += essence_satisfaction.disposition_delta
                delta.reasons.append(DispositionDeltaReason(
                    axis="results",
                    delta=essence_satisfaction.disposition_delta,
                    source="essence_satisfaction",
                    note=(
                        f"Domain production {domain_production:.2f} "
                        f"({'above' if essence_satisfaction.above_threshold else 'below'} threshold, "
                        f"{'growing' if essence_satisfaction.growing else 'flat/declining'})"
                    ),
                ))

            # Dialogue triggers
            triggers = engine.generate_dialogue_triggers(
                luminary_id=luminary.id,
                luminary_domain_tags=luminary_domain_tags,
                personality=personality,
                current_disposition=luminary.disposition,
                delta=delta,
                constraint_evals=constraint_evals,
                essence_suspicion=essence_suspicion,
                timestamp=state.universe.current_age,
            )

            ev = LuminaryEvaluation(
                luminary_id=luminary.id,
                timestamp=state.universe.current_age,
                attention_level=attention_level,
                attention_triggers=attention_triggers,
                domain_alignment_scores=domain_scores,
                overall_domain_alignment=overall_alignment,
                constraint_evaluations=constraint_evals,
                footprint_assessment=fp_assessment,
                essence_suspicion=essence_suspicion,
                essence_satisfaction=essence_satisfaction,
                disposition_delta=delta,
                dialogue_triggers=triggers,
                summary_note=self._summarize_evaluation(
                    luminary, delta, overall_alignment
                ),
            )
            evaluations.append(ev)

        return evaluations

    # ─────────────────────────────────────────
    # PHASE 5: DISPOSITION UPDATE
    # ─────────────────────────────────────────

    def _apply_disposition_deltas(
        self,
        state: SimulationState,
        evaluations: list["LuminaryEvaluation"],
    ) -> tuple[SimulationState, dict[str, tuple[float, float]]]:

        changes: dict[str, tuple[float, float]] = {}

        for ev in evaluations:
            lid = str(ev.luminary_id)
            luminary = state.luminaries.get(lid)
            if not luminary:
                continue

            new_results, new_methods = ev.disposition_delta.clamp_to(
                luminary.disposition.results,
                luminary.disposition.methods,
            )
            luminary.disposition.results = new_results
            luminary.disposition.methods = new_methods
            changes[lid] = (new_results, new_methods)

            # Snapshot the evaluation for the Luminary detail tab. Shift the prior
            # snapshot into previous_evaluation so the UI can show deltas.
            try:
                snap = ev.model_dump(mode="json")
            except Exception:
                snap = None
            if snap is not None:
                luminary.previous_evaluation = luminary.last_evaluation
                luminary.last_evaluation = snap
                luminary.last_evaluation_tick = state.tick_number

            # Update attention
            att_delta = sum(
                t.delta for t in ev.attention_triggers
            ) + ev.essence_suspicion.attention_delta
            current_att = state.luminary_attention.get(lid, 0.2)
            state.luminary_attention[lid] = max(
                0.0, min(1.0, current_att + att_delta)
            )

        return state, changes

    # ─────────────────────────────────────────
    # PHASE 6: TERMINAL CHECK
    # ─────────────────────────────────────────

    def _check_terminal_conditions(
        self,
        state: SimulationState,
        profile: "UniverseDomainProfile",
    ) -> TerminalCheck:

        # Victory: overthrow
        if self._overthrow_this_tick == ActionOutcome.SUCCESS:
            return TerminalCheck(
                condition=TerminalConditionType.VICTORY_OVERTHROW,
                triggered=True,
                note=(
                    "You have severed the Luminary's hold on your universe. "
                    "The throne is yours — for now."
                ),
            )
        if self._overthrow_this_tick == ActionOutcome.CHAOTIC_RESULT:
            return TerminalCheck(
                condition=TerminalConditionType.DEFEAT_CAST_DOWN,
                triggered=True,
                note=(
                    "The overthrow attempt unraveled catastrophically. "
                    "The Luminaries cast you into the Underreal."
                ),
            )

        # Defeat: all Luminaries hostile
        all_hostile = all(
            lum.disposition.overall < -0.8
            for lum in state.luminaries.values()
        )
        if all_hostile:
            return TerminalCheck(
                condition=TerminalConditionType.DEFEAT_CAST_DOWN,
                triggered=True,
                note=(
                    "Every liege Luminary has turned against you. "
                    "The Underreal awaits."
                ),
            )

        return TerminalCheck(condition=TerminalConditionType.NONE)

    # ─────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────

    def _prune_weak_beliefs(self, state: SimulationState) -> SimulationState:
        """
        Remove belief and domain-expression entries whose strength has fallen
        below BELIEF_FLOOR. Runs every passive phase to prevent ghost residue
        from accumulating via many small-delta mutations.

        Pop.dominant_beliefs and NotableMortal.belief_tags / culture_tags are
        pruned here too: their apply handlers permit sub-floor entries to
        persist within a single tick so multi-source contributions (e.g. a
        4-tick whisper echo's per-tick shifts when each is below floor) can
        compound across floor. Entries that fail to accumulate across floor
        by the next passive phase get cleared here.
        """
        for civ in state.civilizations.values():
            civ.dominant_beliefs = {
                tag: s for tag, s in civ.dominant_beliefs.items() if s > BELIEF_FLOOR
            }
        for world in state.worlds.values():
            world.domain_expression = {
                tag: s for tag, s in world.domain_expression.items() if s > BELIEF_FLOOR
            }
        for pop in state.pops.values():
            pop.dominant_beliefs = {
                tag: s for tag, s in pop.dominant_beliefs.items() if s > BELIEF_FLOOR
            }
            pop.culture_tags = {
                tag: s for tag, s in pop.culture_tags.items() if s > CULTURE_FLOOR
            }
        for mortal in state.mortals.values():
            mortal.belief_tags = {
                tag: s for tag, s in mortal.belief_tags.items() if s > BELIEF_FLOOR
            }
            mortal.culture_tags = {
                tag: s for tag, s in mortal.culture_tags.items() if s > CULTURE_FLOOR
            }
        return state

    def _process_active_events(
        self,
        state: SimulationState,
    ) -> list[StateMutation]:
        """
        Apply continuation effects from active_events for the current tick.
        Skips offset-0 (action handler covers that tick directly).
        Populates state.pending_attention_triggers for Phase 4 consumption.
        Prunes expired events.
        """
        mutations: list[StateMutation] = []
        expired_ids: list[str] = []

        for eid, event in state.active_events.items():
            if event.is_expired(state.tick_number):
                expired_ids.append(eid)
                continue

            offset = state.tick_number - event.created_at_tick
            if offset == 0:
                continue  # tick-0 handled by the action handler

            strength = event.current_strength(state.tick_number)

            # Omen events target Pops directly (Pop beliefs are the canonical store)
            if event.event_type == EventType.OMEN:
                # The belief/culture shotgun resolved once at cast time. The
                # omen echo carries only the social ripple — divine awareness
                # here, Luminary attention via the generic attention_per_tick
                # handler further below.
                wid = str(event.target_world_id) if event.target_world_id else None
                if event.divine_awareness_rate > 0.0 and wid:
                    for cid, civ in state.civilizations.items():
                        if str(civ.origin_location_id) == wid:
                            mutations.append(StateMutation(
                                mutation_type=MutationType.CIVILIZATION_STAT,
                                target_id=civ.id,
                                field="divine_awareness",
                                delta=event.divine_awareness_rate * strength,
                                note=f"Omen echo awareness",
                            ))
            elif event.event_type == EventType.WHISPER:
                # Whisper echo: continues to shift the target mortal's beliefs,
                # with the same Pop-splash pattern as the immediate action.
                # Civ.dominant_beliefs is recomputed from Pops each tick (line
                # 881), so civ-level writes would be clobbered — we go through
                # the canonical stores (mortal.belief_tags and Pop.dominant_beliefs)
                # instead.
                if event.target_mortal_id is None:
                    pass  # no mortal target; nothing to echo
                else:
                    mortal = state.mortals.get(str(event.target_mortal_id))
                    if mortal is None or mortal.status == MortalStatus.DECEASED:
                        expired_ids.append(eid)
                        continue
                    for dv in event.domain_vectors:
                        mutations.append(StateMutation(
                            mutation_type=MutationType.MORTAL_BELIEF_SHIFT,
                            target_id=mortal.id,
                            field=dv.domain_tag,
                            delta=dv.direction * strength * event.domain_shift_rate,
                            new_value=dv.domain_tag,
                            note=f"Whisper echo ({mortal.name}, offset {offset})",
                        ))
                    for cv in event.culture_vectors:
                        mutations.append(StateMutation(
                            mutation_type=MutationType.MORTAL_CULTURE_SHIFT,
                            target_id=mortal.id,
                            field=cv.culture_tag,
                            delta=cv.direction * strength * event.domain_shift_rate,
                            new_value=cv.culture_tag,
                            note=f"Whisper culture echo ({mortal.name}, offset {offset})",
                        ))
                    # Pop splash echo — same shape as the immediate splash.
                    self._emit_whisper_splash(
                        mutations, state, mortal,
                        domain_vectors=event.domain_vectors,
                        culture_vectors=event.culture_vectors,
                        per_unit_delta=strength * event.domain_shift_rate,
                        note_prefix=f"Whisper echo (offset {offset})",
                    )
            else:
                # Resolve target civilization IDs for all other event types
                target_civ_ids: list[str] = []
                if event.target_civilization_id is not None:
                    cid = str(event.target_civilization_id)
                    if cid in state.civilizations:
                        target_civ_ids.append(cid)
                    else:
                        expired_ids.append(eid)  # target gone; expire the event
                        continue
                elif event.target_mortal_id is not None:
                    mortal = state.mortals.get(str(event.target_mortal_id))
                    if mortal and mortal.civilization_id:
                        cid = str(mortal.civilization_id)
                        if cid in state.civilizations:
                            target_civ_ids.append(cid)
                elif event.target_world_id is not None:
                    wid = str(event.target_world_id)
                    for cid, civ in state.civilizations.items():
                        if str(civ.origin_location_id) == wid:
                            target_civ_ids.append(cid)
                else:
                    target_civ_ids = list(state.civilizations.keys())

                for cid in target_civ_ids:
                    civ_obj = state.civilizations[cid]
                    for dv in event.domain_vectors:
                        mutations.append(StateMutation(
                            mutation_type=MutationType.BELIEF_SHIFT,
                            target_id=civ_obj.id,
                            field="dominant_beliefs",
                            delta=dv.direction * strength * event.domain_shift_rate,
                            new_value=dv.domain_tag,
                            note=f"Event echo ({event.event_type}, offset {offset})",
                        ))
                    if event.divine_awareness_rate > 0.0:
                        mutations.append(StateMutation(
                            mutation_type=MutationType.CIVILIZATION_STAT,
                            target_id=civ_obj.id,
                            field="divine_awareness",
                            delta=event.divine_awareness_rate * strength,
                            note=f"Event echo ({event.event_type}) awareness",
                        ))

            # Populate attention triggers for Phase 4
            if event.attention_per_tick > 0.0:
                trigger = AttentionTrigger(
                    trigger_type=f"event_{event.event_type}",
                    delta=event.attention_per_tick * strength,
                    timestamp=float(state.tick_number),
                    note=f"{event.event_type} echo (offset {offset})",
                )
                for lid in state.luminaries:
                    state.pending_attention_triggers.setdefault(lid, []).append(trigger)

        for eid in expired_ids:
            state.active_events.pop(eid, None)

        return mutations

    def _resolve_proxius_agents(
        self,
        state: SimulationState,
        phase_rng: random.Random,
    ) -> tuple[list[StateMutation], list[str]]:
        """
        Phase 2.5 — autonomous Proxius agent actions.
        Each active Proxius with an active_goal chooses and executes one
        action per tick, weighted by dedication (alignment × leeway).
        Generates StateMutations directly; does not go through ActionInstance machinery.
        Returns (mutations, agent_narratives) where agent_narratives are REPORT_TO_DEMIURGE
        entries that should be surfaced in the tick log.
        """
        mutations: list[StateMutation] = []
        agent_narratives: list[str] = []

        for mortal in state.mortals.values():
            if mortal.role != MortalRole.PROXIUS:
                continue
            if mortal.status != MortalStatus.ACTIVE:
                continue
            goal = mortal.active_goal
            if goal is None:
                continue

            # ── Milestone checks (run every tick before the frequency gate) ──────
            # Individual flags fire once; combined-success fires and clears the goal.
            # Ordering: individual checks first (may reset petition clock), then
            # combined check, then petition abandonment — so a same-tick double
            # completion fires combined success before abandonment can fire.

            _pop_a_ms = state.pops.get(str(goal.source_pop_id)) if goal.source_pop_id else None
            _pop_b_ms = state.pops.get(str(goal.goal_pop_id))   if goal.goal_pop_id   else None
            _imago_short_ms = goal.imago_node_id.split(":")[-1] if goal.imago_node_id else "directive"

            # (A) Belief cap milestone
            if not goal.pop_b_belief_cap_reached and _pop_b_ms is not None and goal.domain_vectors:
                core_dv = max(
                    (dv for dv in goal.domain_vectors if dv.direction > 0),
                    key=lambda dv: dv.direction,
                    default=None,
                )
                # Threshold slightly below BELIEF_CAP: Phase 1 decay runs before
                # Phase 2.5, so the reading can sit ~0.01–0.02 below 0.9 even when
                # the cap was hit last tick.
                if core_dv and _pop_b_ms.dominant_beliefs.get(core_dv.domain_tag, 0.0) >= BELIEF_CAP - 0.02:
                    goal.pop_b_belief_cap_reached = True
                    goal.petition_pending         = True
                    goal.petition_pending_ticks   = 0
                    mutations.append(StateMutation(
                        mutation_type=MutationType.MORTAL_ALIGNMENT,
                        target_id=mortal.id,
                        field="alignment",
                        delta=+0.05,
                        note=f"{mortal.name} — Pop B core domain at belief cap",
                    ))
                    domain_short = core_dv.domain_tag.split(":", 1)[1]
                    agent_narratives.append(
                        f"[Tick {state.tick_number + 1}] {mortal.name}: "
                        f"The splinter community has fully embraced {domain_short} "
                        f"under [{_imago_short_ms}]. Still growing their numbers. "
                        f"Awaiting guidance."
                    )

            # (B) Size goal milestone — Pop B >= 55% of Pop A's current size
            if (
                not goal.pop_b_size_goal_reached
                and _pop_a_ms is not None
                and _pop_b_ms is not None
                and _pop_b_ms.size_fractional >= 0.55 * _pop_a_ms.size_fractional
            ):
                goal.pop_b_size_goal_reached  = True
                goal.petition_pending         = True
                goal.petition_pending_ticks   = 0
                mutations.append(StateMutation(
                    mutation_type=MutationType.MORTAL_ALIGNMENT,
                    target_id=mortal.id,
                    field="alignment",
                    delta=+0.05,
                    note=f"{mortal.name} — Pop B has reached 55% of Pop A's size",
                ))
                agent_narratives.append(
                    f"[Tick {state.tick_number + 1}] {mortal.name}: "
                    f"The [{_imago_short_ms}] community has grown to a self-sustaining size. "
                    f"Awaiting new orders."
                )

            # (C) Combined success — both milestones met: immediate clearance
            if goal.pop_b_belief_cap_reached and goal.pop_b_size_goal_reached:
                mutations.append(StateMutation(
                    mutation_type=MutationType.MORTAL_ALIGNMENT,
                    target_id=mortal.id,
                    field="alignment",
                    delta=+0.08,
                    note=f"{mortal.name} — full mission success",
                ))
                mutations.append(StateMutation(
                    mutation_type=MutationType.PROXIUS_GOAL_CLEARED,
                    target_id=mortal.id,
                    field="active_goal",
                    note=f"{mortal.name} mission complete — goal cleared",
                ))
                agent_narratives.append(
                    f"[Tick {state.tick_number + 1}] {mortal.name} reports: "
                    f"The [{_imago_short_ms}] directive is fulfilled — "
                    f"the community is established and their convictions run deep. "
                    f"Standing by for a new purpose."
                )
                continue

            # Petition abandonment: after milestones so a same-tick completion
            # fires combined success before the 5-tick clock can trigger.
            if goal.petition_pending:
                goal.petition_pending_ticks += 1
                if goal.petition_pending_ticks >= 5:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.PROXIUS_GOAL_CLEARED,
                        target_id=mortal.id,
                        field="active_goal",
                        note=f"{mortal.name} abandoned goal after petition ignored for 5 ticks",
                    ))
                    agent_narratives.append(
                        f"[Tick {state.tick_number + 1}] {mortal.name} has abandoned their directive — "
                        f"no response to petition for {goal.petition_pending_ticks} ticks."
                    )
                    continue

            # Dedication: high alignment + low latitude → near-certain, frequent action
            dedication = mortal.alignment * (1.0 - goal.latitude * 0.3)
            dedication = max(0.0, min(1.0, dedication))

            # Frequency gate — probabilistic skip
            if phase_rng.random() > dedication:
                goal.last_action = AgentActionChoice.NOTHING
                goal.last_action_tick = state.tick_number
                goal.consecutive_promote_count = 0
                goal.effectiveness_bonus = max(0.0, goal.effectiveness_bonus - 0.05)
                continue

            # ── Research goal branch (Commission Inquiry) ──
            if goal.research_domain:
                tag = goal.research_domain
                cap = _compute_revelation_cap(state, tag)
                pool = state.demiurge.revelation_pools.get(tag, 0.0)
                if cap == 0.0 or pool >= cap:
                    # Tree complete or pool full — clear goal
                    mutations.append(StateMutation(
                        mutation_type=MutationType.PROXIUS_GOAL_CLEARED,
                        target_id=mortal.id,
                        field="active_goal",
                        note=f"{mortal.name} completed Domain research on {tag}",
                    ))
                    short = tag.split(":", 1)[1].title() if ":" in tag else tag.title()
                    goal.report_log = (goal.report_log + [
                        f"[Tick {state.tick_number + 1}] {mortal.name}: Research on {short} is complete. Awaiting a new directive."
                    ])[-5:]
                    goal.last_action = AgentActionChoice.RESEARCH_DOMAIN
                    goal.last_action_tick = state.tick_number
                else:
                    base_rev = 2.0
                    expr = _compute_local_expression(state, tag, mortal.current_location)
                    loc_bonus = round(expr * 2.0, 2)
                    belief_bonus = 1.0 if mortal.belief_tags.get(tag, 0.0) >= 0.4 else 0.0
                    delta = round(min(base_rev + loc_bonus + belief_bonus, cap - pool), 2)
                    mutations.append(StateMutation(
                        mutation_type=MutationType.REVELATION_GAINED,
                        target_id=state.demiurge.id,
                        field=tag,
                        delta=delta,
                        note=f"{mortal.name} research on {tag}: +{delta} Revelation",
                    ))
                    goal.last_action = AgentActionChoice.RESEARCH_DOMAIN
                    goal.last_action_tick = state.tick_number
                continue

            # Action weight table
            already_audited = str(mortal.id) in state.proxii_audited_this_tick
            has_goal_pop    = goal.goal_pop_id is not None
            if has_goal_pop:
                _bcr = goal.pop_b_belief_cap_reached
                _sgr = goal.pop_b_size_goal_reached
                if _bcr and not _sgr:
                    # Beliefs at cap but still growing: shift weight toward size drain
                    promote_w = 0.50
                    bolster_w = 0.15
                elif _sgr and not _bcr:
                    # Size met but beliefs still building: shift weight toward bolstering
                    promote_w = 0.15
                    bolster_w = 0.50
                elif _bcr and _sgr:
                    # Both met — combined-success should have fired; defensive fallback
                    promote_w = 0.10
                    bolster_w = 0.10
                else:
                    # Normal: balanced between deepening beliefs and growing size
                    promote_w = 0.30
                    bolster_w = 0.40
                take_stock_w = 0.08
                report_w     = 0.0 if already_audited else (0.08 + (1.0 - goal.latitude) * 0.10)
                petition_w   = (
                    min(0.25, 0.03 + goal.stagnation_counter * 0.03)
                    if not goal.petition_pending else 0.0
                )
                nothing_w    = max(0.0, 0.09 - dedication * 0.06)
            else:
                # No splinter yet: laser-focused on creating the first split
                promote_w    = 0.75
                bolster_w    = 0.0
                take_stock_w = 0.06
                report_w     = 0.0 if already_audited else (0.06 + (1.0 - goal.latitude) * 0.08)
                petition_w   = 0.03 if not goal.petition_pending else 0.0
                nothing_w    = max(0.0, 0.10 - dedication * 0.08)

            weights = [promote_w, bolster_w, take_stock_w, report_w, petition_w, nothing_w]
            choices = [
                AgentActionChoice.PROMOTE_DOMAIN,
                AgentActionChoice.BOLSTER_BELIEFS,
                AgentActionChoice.TAKE_STOCK,
                AgentActionChoice.REPORT_TO_DEMIURGE,
                AgentActionChoice.PETITION_FOR_RELIEF,
                AgentActionChoice.NOTHING,
            ]
            chosen = phase_rng.choices(choices, weights=weights, k=1)[0]
            goal.last_action = chosen
            goal.last_action_tick = state.tick_number

            if chosen == AgentActionChoice.PROMOTE_DOMAIN and goal.domain_vectors:
                goal.consecutive_promote_count += 1
                goal.effectiveness_bonus = min(0.30, goal.consecutive_promote_count * 0.05)
                base_rate = 0.06

                if goal.source_pop_id:
                    # ── Pop-level preaching path ──────────────────────────
                    pop_a = state.pops.get(str(goal.source_pop_id))
                    # Cross-civ preaching: half effectiveness when Proxius preaches to a
                    # community outside their own civilization.
                    _proxius_origin_pop = state.pops.get(str(mortal.pop_id)) if mortal.pop_id else None
                    _proxius_civ = str(_proxius_origin_pop.civilization_id) if _proxius_origin_pop and _proxius_origin_pop.civilization_id else None
                    if pop_a and _proxius_civ and str(pop_a.civilization_id) != _proxius_civ:
                        base_rate *= 0.5
                    if pop_a is None:
                        # Source Pop gone — force petition
                        goal.petition_pending = True
                        goal.consecutive_promote_count = 0
                        goal.effectiveness_bonus = 0.0
                    elif goal.goal_pop_id is None:
                        # ── First success: create Pop B ───────────────────
                        # 5-tick escalating pre-shift applied to Pop A's beliefs
                        # plus culture synergy bonus from Imāgō node mechanics
                        ireg = get_imago_registry()
                        imago_node = ireg.get_node(goal.imago_node_id) if goal.imago_node_id else None
                        culture_mechanics = {}
                        if imago_node:
                            culture_mechanics = {
                                k: v for k, v in imago_node.mechanics.items()
                                if k.startswith("culture:")
                            }

                        new_beliefs = dict(pop_a.dominant_beliefs)
                        for dv in goal.domain_vectors:
                            belief_affinity = mortal.belief_tags.get(dv.domain_tag, 0.0)
                            # Culture synergy bonus: sum strength × pop A's culture level
                            culture_bonus = sum(
                                c_strength * pop_a.culture_tags.get(c_tag, 0.0)
                                for c_tag, c_strength in culture_mechanics.items()
                                if dv.direction > 0
                            )
                            # Apply 2 escalating tick-steps with inertia at each step
                            # so the initial state respects the same resistance as live bolstering.
                            current = new_beliefs.get(dv.domain_tag, 0.0)
                            for i in range(1, 3):
                                tick_rate = base_rate * (1.0 + i * 0.05) + belief_affinity * 0.02
                                raw_delta = (tick_rate + culture_bonus / 5) * dv.direction
                                raw_delta *= self._belief_inertia(current, raw_delta)
                                cap = BELIEF_CAP if raw_delta > 0 else 1.0
                                current = max(0.0, min(cap, current + raw_delta))
                            new_beliefs[dv.domain_tag] = current

                        # Prune sub-floor entries
                        new_beliefs = {
                            k: v for k, v in new_beliefs.items() if v > BELIEF_FLOOR
                        }

                        # Apply the Imago's culture-tag riders to the splinter's
                        # starting culture_tags — same 2-step escalating pre-shift
                        # pattern as the belief pre-shift above, respecting inertia
                        # and the values:* stubbornness multiplier.
                        new_culture = dict(pop_a.culture_tags)
                        _stub_mult = max(0.05, 1.0 - state.config.values_stubbornness_factor)
                        for cv in goal.culture_vectors:
                            current = new_culture.get(cv.culture_tag, 0.0)
                            for i in range(1, 3):
                                tick_rate = base_rate * (1.0 + i * 0.05)
                                raw_delta = tick_rate * cv.direction
                                if cv.culture_tag.startswith("values:"):
                                    raw_delta *= _stub_mult
                                raw_delta *= self._belief_inertia(current, raw_delta)
                                cap = BELIEF_CAP if raw_delta > 0 else 1.0
                                current = max(0.0, min(cap, current + raw_delta))
                            new_culture[cv.culture_tag] = current
                        new_culture = {
                            k: v for k, v in new_culture.items() if v > CULTURE_FLOOR
                        }

                        pop_b = Pop(
                            id=uuid4(),
                            name=goal.goal_pop_name,
                            # Splinters formed via Proxius preaching are
                            # Demiurge-authored — grants the player naming
                            # rights via the in-game [ Rename ] button.
                            demiurge_authored=True,
                            civilization_id=pop_a.civilization_id,
                            species_id=pop_a.species_id,
                            social_class=pop_a.social_class,
                            wild_stratum=pop_a.wild_stratum,
                            current_location=pop_a.current_location,
                            size_fractional=1.0,
                            dominant_beliefs=new_beliefs,
                            culture_tags=new_culture,
                            rider_traits={
                                dv.domain_tag: 0.30
                                for dv in goal.domain_vectors
                                if dv.direction > 0
                            },
                            parent_pop_id=pop_a.id,
                            preaching_imago_id=goal.imago_node_id,
                            pinned=True,
                            visibility=pop_a.visibility * 0.5,
                        )
                        # Wire goal_pop_id now so next tick uses the ongoing path.
                        # Also clear goal_pop_name — the name has been applied; if
                        # the goal continues, we don't want to re-apply it.
                        goal.goal_pop_id = pop_b.id
                        goal.goal_pop_last_size = pop_b.size_fractional
                        goal.goal_pop_name = None
                        mutations.append(StateMutation(
                            mutation_type=MutationType.POP_SPLINTER,
                            target_id=pop_a.id,
                            field="",
                            new_value=pop_b,
                            note=f"Directed Preach Imāgō splinter by {mortal.name}",
                        ))
                        agent_narratives.append(
                            f"[Tick {state.tick_number + 1}] {mortal.name}'s preaching of "
                            f"[{goal.imago_node_id if goal.imago_node_id else 'directive'}] has drawn a new group "
                            f"apart from their parent community."
                        )
                    else:
                        # ── Ongoing: drain Pop A into Pop B (beliefs unchanged here;
                        # Pop A only shifts via splash during BOLSTER_BELIEFS) ──
                        pop_b = state.pops.get(str(goal.goal_pop_id))
                        if pop_b is None:
                            goal.stagnation_counter = min(10, goal.stagnation_counter + 1)
                        else:
                            # Clear petition once Proxius achieves a streak of 2+
                            if goal.petition_pending and goal.consecutive_promote_count >= 2:
                                goal.petition_pending = False
                                goal.petition_pending_ticks = 0

                            size_delta = round(0.05 * (1.0 + goal.effectiveness_bonus), 3)
                            if pop_a.size_fractional - size_delta <= 0.0:
                                # Pop A fully absorbed
                                mutations.append(StateMutation(
                                    mutation_type=MutationType.POP_ABSORBED,
                                    target_id=pop_a.id,
                                    field="",
                                    new_value=str(pop_b.id),
                                    note=f"Pop A absorbed into goal Pop by {mortal.name}",
                                ))
                                goal.petition_pending = True
                                agent_narratives.append(
                                    f"[Tick {state.tick_number + 1}] {mortal.name} reports: "
                                    f"the source community has been fully drawn into the new group. "
                                    f"Directive complete — awaiting new orders."
                                )
                            else:
                                mutations.append(StateMutation(
                                    mutation_type=MutationType.POP_SIZE_CHANGE,
                                    target_id=pop_a.id,
                                    field="",
                                    delta=-size_delta,
                                    note=f"Members leaving for goal Pop (Proxius {mortal.name})",
                                ))
                                mutations.append(StateMutation(
                                    mutation_type=MutationType.POP_SIZE_CHANGE,
                                    target_id=pop_b.id,
                                    field="",
                                    delta=size_delta,
                                    note=f"Members joining goal Pop (Proxius {mortal.name})",
                                ))
                                # Stagnation tracking against last known size
                                if pop_b.size_fractional + size_delta <= goal.goal_pop_last_size:
                                    goal.stagnation_counter = min(10, goal.stagnation_counter + 1)
                                else:
                                    goal.stagnation_counter = max(0, goal.stagnation_counter - 1)
                                goal.goal_pop_last_size = pop_b.size_fractional + size_delta
                else:
                    # ── Legacy civ-level path (goals without source_pop_id) ──
                    target_civ_ids: list[str] = []
                    if goal.target_civilization_id:
                        cid = str(goal.target_civilization_id)
                        if cid in state.civilizations:
                            target_civ_ids.append(cid)
                    else:
                        # goal.target_location_id may be a PopLocation; resolve
                        # to its parent world so it matches civ.origin_location_id.
                        loc_id = (
                            _resolve_world_id_for(state, goal.target_location_id)
                            or str(goal.target_location_id)
                        )
                        target_civ_ids = [
                            cid for cid, civ in state.civilizations.items()
                            if str(civ.origin_location_id) == loc_id
                        ]
                    for cid in target_civ_ids:
                        for dv in goal.domain_vectors:
                            belief_affinity = mortal.belief_tags.get(dv.domain_tag, 0.0)
                            rate = base_rate * (1.0 + goal.effectiveness_bonus) + belief_affinity * 0.02
                            mutations.append(StateMutation(
                                mutation_type=MutationType.BELIEF_SHIFT,
                                target_id=UUID(cid),
                                field="dominant_beliefs",
                                delta=dv.direction * rate,
                                new_value=dv.domain_tag,
                                note=f"Proxius {mortal.name} promoting {dv.domain_tag} (streak {goal.consecutive_promote_count})",
                            ))

                # Footprint regardless of path
                mutations.append(StateMutation(
                    mutation_type=MutationType.FOOTPRINT_CHANGE,
                    target_id=state.demiurge.id,
                    field="proxius_activity",
                    delta=0.02,
                    note=f"Proxius {mortal.name} promoting domain",
                ))

            elif chosen == AgentActionChoice.BOLSTER_BELIEFS and goal.domain_vectors:
                # Strengthen Pop B's distinctive beliefs directly
                pop_a = state.pops.get(str(goal.source_pop_id)) if goal.source_pop_id else None
                pop_b = state.pops.get(str(goal.goal_pop_id)) if goal.goal_pop_id else None
                if pop_b is None:
                    goal.stagnation_counter = min(10, goal.stagnation_counter + 1)
                else:
                    goal.consecutive_promote_count += 1
                    goal.effectiveness_bonus = min(0.30, goal.consecutive_promote_count * 0.05)
                    base_rate = 0.12
                    # Clear petition once Proxius achieves a streak of 2+
                    if goal.petition_pending and goal.consecutive_promote_count >= 2:
                        goal.petition_pending = False
                        goal.petition_pending_ticks = 0
                    for dv in goal.domain_vectors:
                        belief_affinity = mortal.belief_tags.get(dv.domain_tag, 0.0)
                        rate = base_rate * (1.0 + goal.effectiveness_bonus) + belief_affinity * 0.02
                        receptivity = self._pop_domain_receptivity(pop_b, dv.domain_tag)
                        mutations.append(StateMutation(
                            mutation_type=MutationType.POP_BELIEF_SHIFT,
                            target_id=pop_b.id,
                            field=dv.domain_tag,
                            delta=dv.direction * rate * receptivity,
                            note=f"Proxius {mortal.name} bolstering goal Pop beliefs",
                        ))
                        mutations.append(StateMutation(
                            mutation_type=MutationType.POP_RIDER_TRAIT,
                            target_id=pop_b.id,
                            field=dv.domain_tag,
                            delta=dv.direction * rate * 0.5,
                            note=f"Rider trait from {goal.imago_node_id or 'directive'}",
                        ))
                    for cv in goal.culture_vectors:
                        rate = base_rate * (1.0 + goal.effectiveness_bonus)
                        mutations.append(StateMutation(
                            mutation_type=MutationType.POP_CULTURE_SHIFT,
                            target_id=pop_b.id,
                            field=cv.culture_tag,
                            delta=cv.direction * rate,
                            note=f"Proxius {mortal.name} preaching culture rider",
                        ))
                    # Splash: Proxius actively bridges Pop B's new beliefs back to Pop A.
                    # No size dampening here — this is directed preaching, not passive contact.
                    if pop_a is not None:
                        for dv in goal.domain_vectors:
                            if dv.direction > 0:
                                _pop_a_receptivity = self._pop_domain_receptivity(pop_a, dv.domain_tag)
                                splash_delta = dv.direction * base_rate * 0.6 * _pop_a_receptivity
                                mutations.append(StateMutation(
                                    mutation_type=MutationType.POP_BELIEF_SHIFT,
                                    target_id=pop_a.id,
                                    field=dv.domain_tag,
                                    delta=splash_delta,
                                    note=f"Belief splash to Pop A from {mortal.name} bolstering goal Pop",
                                ))
                        for cv in goal.culture_vectors:
                            if cv.direction > 0:
                                splash_delta = cv.direction * base_rate * 0.6
                                mutations.append(StateMutation(
                                    mutation_type=MutationType.POP_CULTURE_SHIFT,
                                    target_id=pop_a.id,
                                    field=cv.culture_tag,
                                    delta=splash_delta,
                                    note=f"Culture splash to Pop A from {mortal.name} preaching",
                                ))
                    mutations.append(StateMutation(
                        mutation_type=MutationType.FOOTPRINT_CHANGE,
                        target_id=state.demiurge.id,
                        field="proxius_activity",
                        delta=0.02,
                        note=f"Proxius {mortal.name} bolstering goal Pop",
                    ))

            elif chosen == AgentActionChoice.TAKE_STOCK:
                goal.consecutive_promote_count = 0
                goal.effectiveness_bonus = max(0.0, goal.effectiveness_bonus - 0.02)
                mutations.append(StateMutation(
                    mutation_type=MutationType.MORTAL_ALIGNMENT,
                    target_id=mortal.id,
                    field="alignment",
                    delta=0.01,
                    note=f"{mortal.name} taking stock of their work",
                ))

            elif chosen == AgentActionChoice.REPORT_TO_DEMIURGE:
                tick = state.tick_number + 1  # tick_number increments after Phase 2.5
                streak = goal.consecutive_promote_count
                ticks_active = state.tick_number + 1 - goal.started_at_tick
                imago_short = goal.imago_node_id.split(":")[-1] if goal.imago_node_id else "directive"
                if streak >= 3:
                    progress = f"momentum is building — {streak} consecutive pushes of [{imago_short}]"
                elif streak > 0:
                    progress = f"work on [{imago_short}] is underway, {streak} push(es) this stretch"
                elif goal.effectiveness_bonus > 0:
                    progress = f"[{imago_short}] work has stalled momentarily; prior gains hold"
                else:
                    progress = f"no meaningful progress on [{imago_short}] yet"
                entry = (
                    f"[Tick {tick}] {mortal.name} reports after {ticks_active} tick(s): "
                    + progress
                    + (f"; effectiveness at +{goal.effectiveness_bonus:.0%}" if goal.effectiveness_bonus > 0 else "")
                    + "."
                )
                goal.report_log = (goal.report_log + [entry])[-5:]
                agent_narratives.append(entry)

            elif chosen == AgentActionChoice.PETITION_FOR_RELIEF:
                goal.petition_pending = True
                goal.petition_pending_ticks = 0  # 5-tick abandonment clock starts now
                goal.consecutive_promote_count = 0
                goal.effectiveness_bonus = 0.0
                goal.stagnation_counter = 0  # fresh start after petition
                tick = state.tick_number + 1
                ticks_active = state.tick_number + 1 - goal.started_at_tick
                imago_short = goal.imago_node_id.split(":")[-1] if goal.imago_node_id else "directive"
                if goal.goal_pop_id is not None:
                    reason = "the splinter population has stalled — they may be losing ground."
                else:
                    reason = "directive yields diminishing returns."
                entry = (
                    f"[Tick {tick}] {mortal.name} petitions after {ticks_active} tick(s): "
                    f"[{imago_short}] {reason} Requesting new orders."
                )
                goal.report_log = (goal.report_log + [entry])[-5:]
                if not (goal.pop_b_belief_cap_reached or goal.pop_b_size_goal_reached):
                    mutations.append(StateMutation(
                        mutation_type=MutationType.MORTAL_ALIGNMENT,
                        target_id=mortal.id,
                        field="alignment",
                        delta=-0.02,
                        note=f"{mortal.name} frustrated with current directive",
                    ))

            elif chosen == AgentActionChoice.NOTHING:
                goal.consecutive_promote_count = 0
                goal.effectiveness_bonus = max(0.0, goal.effectiveness_bonus - 0.05)
                mutations.append(StateMutation(
                    mutation_type=MutationType.MORTAL_ALIGNMENT,
                    target_id=mortal.id,
                    field="alignment",
                    delta=+0.01,
                    note=f"{mortal.name} idle recovery",
                ))

        return mutations, agent_narratives

    def _resolve_world_id(
        self,
        instance: "ActionInstance",
        state: SimulationState,
    ) -> Optional[UUID]:
        """Find the world ID associated with an action target."""
        if instance.target_type == TargetType.WORLD:
            return instance.target_id
        elif instance.target_type == TargetType.CIVILIZATION:
            civ = state.civilizations.get(str(instance.target_id))
            return civ.origin_location_id if civ else None
        elif instance.target_type == TargetType.MORTAL:
            mortal = state.mortals.get(str(instance.target_id))
            if mortal is None:
                return None
            # Mortals live at PopLocations; walk up to the parent world.
            wid = _resolve_world_id_for(state, mortal.current_location)
            return UUID(wid) if wid else None
        return None

    def _pop_domain_receptivity(self, pop: "Pop", domain_tag: str) -> float:
        """
        Returns a multiplier (≥ 0.2) for how receptive a Pop is to domain influence.
        Derived from all culture_tags (religion + values) crossing against
        CultureRegistry.domain_affinity.
        """
        creg = self._culture_registry or get_culture_registry()
        bonus = 0.0
        for tag, strength in pop.culture_tags.items():
            affinities = creg.domain_affinity(tag)
            bonus += affinities.get(domain_tag, 0.0) * strength
        return max(0.2, 1.0 + bonus)

    @staticmethod
    def _belief_inertia(current: float, delta: float) -> float:
        """
        Returns a [0.0, 1.0] multiplier that slows belief/culture changes at extremes.

        High zone  (current > 0.7, pushing up):   1.0 → ~0.40 at cap.
        High zone  (current > 0.7, pushing down):  1.0 → ~0.65 at cap  (entrenched but not immovable).
        Low zone   (current < 0.2, pushing up):    0.65 → 1.0  (unfamiliar ideas face friction).
        Floor zone (current ≤ 0.1, pushing down):  0.75 → 1.0  (tiny remnants cling).
        Mid range  (0.2–0.7): multiplier = 1.0.
        """
        if delta > 0:
            if current >= 0.7:
                # Linear from 1.0 at 0.7 down to 0.40 at 0.9+
                t = min(1.0, (current - 0.7) / 0.2)
                return 1.0 - t * 0.60
            if current < 0.2:
                # Linear from 0.65 at 0.0 up to 1.0 at 0.2
                return 0.65 + (current / 0.2) * 0.35
        else:  # delta < 0 (downward pressure)
            if current >= 0.7:
                t = min(1.0, (current - 0.7) / 0.2)
                return 1.0 - t * 0.35
            if current <= 0.1:
                # Linear from 0.75 at 0.0 up to 1.0 at 0.1
                return 0.75 + (current / 0.1) * 0.25
        return 1.0

    def _combine_shape_dream_vectors(
        self,
        vectors_a: list,
        vectors_b: list,
        mult_a: float,
        mult_b: float,
        tag_attr: str,
    ) -> list:
        """
        Combine two lists of DomainVector or CultureVector per the Shape Dream
        resolution rules:

          1. Apply the per-Imago multiplier (boost or suppress) to each
             vector — but ONLY for entries whose direction is positive.
             Negative-direction riders pass through at full strength
             regardless of which side they came from (you can't dream away
             an Imago's downside).
          2. For tags appearing in BOTH lists (after multipliers):
               * both positive → mean of the two directions
               * both negative → sum
               * mixed sign    → sum (they offset naturally)
          3. Tags present in only one list contribute as-is (post-multiplier).

        `tag_attr` is the field name to key by — "domain_tag" or "culture_tag".
        Returns a new list of vectors of the same type as the inputs.
        """
        def apply_mult(vec, mult):
            if vec.direction < 0:
                return vec
            cls = type(vec)
            data = vec.model_dump()
            data["direction"] = max(-1.0, min(1.0, vec.direction * mult))
            return cls(**data)

        multiplied_a = [apply_mult(v, mult_a) for v in vectors_a]
        multiplied_b = [apply_mult(v, mult_b) for v in vectors_b]

        by_tag_a = {getattr(v, tag_attr): v for v in multiplied_a}
        by_tag_b = {getattr(v, tag_attr): v for v in multiplied_b}

        result = []
        for tag in set(by_tag_a) | set(by_tag_b):
            va = by_tag_a.get(tag)
            vb = by_tag_b.get(tag)
            if va is not None and vb is not None:
                if va.direction > 0 and vb.direction > 0:
                    combined = (va.direction + vb.direction) / 2.0
                else:
                    combined = va.direction + vb.direction
                combined = max(-1.0, min(1.0, combined))
                cls = type(va)
                data = va.model_dump()
                data["direction"] = combined
                result.append(cls(**data))
            else:
                result.append(va if va is not None else vb)
        return result

    def _resolve_omen_target(
        self,
        mutations: list,
        state: "SimulationState",
        target,
        is_mortal: bool,
        domain_components: list,
        culture_components: list,
        framing,
        base_pass: float,
        omen_loc_id,
        rng: random.Random,
    ) -> None:
        """
        Resolve a Manifest Omen's "shotgun" interpretation for a single Pop
        (or a mortal treated as a size-1 Pop) and emit the composite
        belief/culture mutations.

        `domain_components` / `culture_components` are lists of
        (tag, signed_magnitude) — the omen's effect E, already scaled by
        OMEN_BASE. The target runs one check per unit of its size; a passed
        check delivers E/n to the true tags, a failed check delivers E/n to
        random same-category substitute tags. The composite is distance-
        shielded and emitted as POP_/MORTAL_ belief and culture shifts.
        """
        if not domain_components and not culture_components:
            return

        n_checks = 1 if is_mortal else max(1, int(getattr(target, "size_magnitude", 1) or 1))

        # ── interpretation-check pass probability ─────
        culture_tags = getattr(target, "culture_tags", {}) or {}
        fr = _framing_resonance(culture_tags, framing)
        if domain_components:
            rec = sum(
                self._pop_domain_receptivity(target, tag)
                for tag, _ in domain_components
            ) / len(domain_components)
        else:
            rec = 1.0
        civ = (
            state.civilizations.get(str(target.civilization_id))
            if getattr(target, "civilization_id", None) else None
        )
        coh = civ.health.cohesion if civ else 0.5

        pass_prob = (
            base_pass
            + fr * OMEN_FRAMING_WEIGHT
            + (rec - 1.0) * OMEN_RECEPTIVITY_WEIGHT
            + (coh - 0.5) * OMEN_COHESION_WEIGHT
        )
        if framing == Framing.AMBIGUOUS:
            pass_prob -= OMEN_AMBIGUOUS_PENALTY
        pass_prob = max(0.05, min(0.95, pass_prob))

        # ── run n checks; accumulate the composite ────
        belief_composite: dict[str, float] = {}
        culture_composite: dict[str, float] = {}
        domain_pool = get_domain_registry().all_tags

        for _ in range(n_checks):
            passed = rng.random() < pass_prob
            for tag, mag in domain_components:
                e = mag / n_checks
                if passed:
                    dest = tag
                else:
                    pool = [d for d in domain_pool if d != tag]
                    dest = rng.choice(pool) if pool else tag
                belief_composite[dest] = belief_composite.get(dest, 0.0) + e
            for tag, mag in culture_components:
                e = mag / n_checks
                if passed:
                    dest = tag
                else:
                    peers = peer_culture_tags(tag)
                    dest = rng.choice(peers) if peers else tag
                culture_composite[dest] = culture_composite.get(dest, 0.0) + e

        # ── distance shielding, then emit ────────────
        dist_factor = _pop_distance_factor(state, omen_loc_id, target.current_location)
        belief_mut = (MutationType.MORTAL_BELIEF_SHIFT if is_mortal
                      else MutationType.POP_BELIEF_SHIFT)
        culture_mut = (MutationType.MORTAL_CULTURE_SHIFT if is_mortal
                       else MutationType.POP_CULTURE_SHIFT)
        kind = "mortal" if is_mortal else "Pop"

        for tag, total in belief_composite.items():
            delta = total * dist_factor
            if abs(delta) > 1e-5:
                mutations.append(StateMutation(
                    mutation_type=belief_mut,
                    target_id=target.id,
                    field=tag,
                    new_value=tag,
                    delta=delta,
                    note=f"Omen interpretation ({kind})",
                ))
        for tag, total in culture_composite.items():
            delta = total * dist_factor
            if abs(delta) > 1e-5:
                mutations.append(StateMutation(
                    mutation_type=culture_mut,
                    target_id=target.id,
                    field=tag,
                    new_value=tag,
                    delta=delta,
                    note=f"Omen interpretation ({kind})",
                ))

    def _emit_whisper_splash(
        self,
        mutations: list,
        state: "SimulationState",
        mortal,
        domain_vectors,
        culture_vectors,
        per_unit_delta: float,
        note_prefix: str,
    ) -> None:
        """
        Emit POP_BELIEF_SHIFT (one per domain_vector) and POP_CULTURE_SHIFT
        (one per culture_vector) splash mutations rippling a whisper from a
        single mortal out to nearby Pops on the same world.

        `per_unit_delta` is the per-`direction=1` belief delta the whisper
        applies to the mortal — splash to each Pop is a fraction of that
        (WHISPER_POP_SPLASH), scaled by:
          - contact resistance (cross-civ/cross-species/cross-stratum dampening)
          - PopLocation distance from the mortal's current location
          - the Pop's domain receptivity (for domain vectors only — culture
            shifts don't pass through the culture×domain affinity machinery)
          - a prominence-derived influence multiplier (own-Pop uses a base
            plus prominence; cross-Pop scales linearly with prominence)

        Recipient Pop `size_fractional` is intentionally NOT a factor here:
        size-weighting is a Pop→Pop influence concept (a big Pop pushes
        harder on its neighbors), not relevant when the source is a single
        mortal.
        """
        if not mortal or (not domain_vectors and not culture_vectors):
            return
        world_id = _resolve_world_id_for(state, mortal.current_location)
        if not world_id:
            return
        splash_pops = self._pops_on_world(world_id, state)
        if not splash_pops:
            return

        cfg = state.config
        src_civ_id = str(mortal.civilization_id) if mortal.civilization_id else None
        src_species_id = str(mortal.species_id) if mortal.species_id else None
        src_pop = state.pops.get(str(mortal.pop_id)) if mortal.pop_id else None
        src_class = (
            (src_pop.social_class.value if hasattr(src_pop.social_class, "value")
             else str(src_pop.social_class or "")) if src_pop else None
        ) or None
        src_size = src_pop.size_fractional if src_pop else 1.0
        src_loc_id = mortal.current_location
        own_pop_id = str(mortal.pop_id) if mortal.pop_id else None
        prominence = float(mortal.prominence)

        own_influence = (
            WHISPER_OWN_POP_BASE_INFLUENCE
            + prominence * WHISPER_OWN_POP_PROMINENCE_GAIN
        )
        cross_influence = prominence * WHISPER_CROSS_POP_PROMINENCE_GAIN

        for sp in splash_pops:
            is_own = own_pop_id is not None and str(sp.id) == own_pop_id
            influence = own_influence if is_own else cross_influence
            if influence <= 0.0:
                continue
            resistance = self._pop_contact_resistance(
                sp, src_civ_id, src_species_id, src_class, state, cfg,
                src_size=src_size,
            )
            dist_factor = _pop_distance_factor(state, src_loc_id, sp.current_location)
            for dv in domain_vectors:
                receptivity = self._pop_domain_receptivity(sp, dv.domain_tag)
                splash_delta = (
                    dv.direction * per_unit_delta * WHISPER_POP_SPLASH
                    * receptivity * resistance * dist_factor * influence
                )
                if abs(splash_delta) > 1e-5:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.POP_BELIEF_SHIFT,
                        target_id=sp.id,
                        field=dv.domain_tag,
                        delta=splash_delta,
                        note=(
                            f"{note_prefix} splash to {sp.stratum} Pop"
                            + (" (own pop)" if is_own else "")
                        ),
                    ))
                    self._emit_lineage_bleed(
                        mutations, state, sp, dv.domain_tag,
                        splash_delta, "whisper",
                    )
            for cv in culture_vectors:
                splash_delta = (
                    cv.direction * per_unit_delta * WHISPER_POP_SPLASH
                    * resistance * dist_factor * influence
                )
                if abs(splash_delta) > 1e-5:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.POP_CULTURE_SHIFT,
                        target_id=sp.id,
                        field=cv.culture_tag,
                        delta=splash_delta,
                        note=(
                            f"{note_prefix} culture splash to {sp.stratum} Pop"
                            + (" (own pop)" if is_own else "")
                        ),
                    ))

    def _pops_on_world(self, world_id: str, state: "SimulationState") -> list["Pop"]:
        """Return all Pops whose current_location is a PopLocation whose parent
        is `world_id`. Authoritative source is `pop.current_location` (not
        `PopLocation.pop_ids` or any home reference), so a Pop's presence on a
        world is decided solely by where it currently is."""
        wid = str(world_id)
        pops: list = []
        for pop in state.pops.values():
            ploc = state.locations.get(str(pop.current_location)) if pop.current_location else None
            if not isinstance(ploc, PopLocation):
                continue
            if str(ploc.parent_id) == wid:
                pops.append(pop)
        return pops

    def _pop_contact_resistance(
        self,
        target_pop: "Pop",
        src_civ_id: str | None,
        src_species_id: str | None,
        src_class: str | None,
        state: "SimulationState",
        cfg: TickConfig,
        src_size: float = 1.0,
    ) -> float:
        """
        Returns a resistance multiplier in [0.0, 1.0] representing how much
        cross-boundary friction slows belief drift from a source Pop/mortal
        onto target_pop.  Same-civ Pops return 1.0 (no reduction).
        """
        r = 1.0

        # Cross-civ resistance
        target_civ_id = str(target_pop.civilization_id) if target_pop.civilization_id else None
        if target_civ_id != src_civ_id:
            r *= cfg.cross_civ_contact_factor
            # Scale-gap penalty: civilizations have ranks; wild populations
            # (no civ_id) are treated as one step below `nascent`. This makes
            # wild→civ drift face the gap penalty too, since the conceptual
            # distance from a pre-sapient pod to a starfaring empire is at
            # least as large as the distance between any two civ scales.
            def _scale_rank_for(civ_id: str | None) -> int:
                if not civ_id:
                    return _CIV_SCALE_CONTACT_RANK["pre_sapient"]
                civ = state.civilizations.get(civ_id)
                if civ is None:
                    return _CIV_SCALE_CONTACT_RANK["pre_sapient"]
                scale = civ.scale.value if hasattr(civ.scale, "value") else str(civ.scale)
                return _CIV_SCALE_CONTACT_RANK.get(scale, 0)
            src_rank = _scale_rank_for(src_civ_id)
            tgt_rank = _scale_rank_for(target_civ_id)
            scale_gap = max(0, tgt_rank - src_rank)
            r *= max(0.05, 1.0 - scale_gap * cfg.cross_civ_scale_penalty)

        # Cross-species resistance
        target_species_id = str(target_pop.species_id) if target_pop.species_id else None
        if src_species_id and target_species_id and target_species_id != src_species_id:
            r *= cfg.cross_species_contact_factor

        # Cross-stratum resistance — wild populations (no social_class) are
        # assigned the `wild` rank, one step below `underclass`, so a wild Pop
        # talking to any actual stratum gets a distance-based penalty.
        tgt_class_str = target_pop.social_class.value if hasattr(target_pop.social_class, "value") else str(target_pop.social_class or "")
        src_rank = _SOCIAL_CLASS_RANK.get(src_class or "wild", _SOCIAL_CLASS_RANK["wild"])
        tgt_rank = _SOCIAL_CLASS_RANK.get(tgt_class_str or "wild", _SOCIAL_CLASS_RANK["wild"])
        stratum_distance = abs(tgt_rank - src_rank)
        if stratum_distance > 0:
            r *= cfg.cross_stratum_contact_factor ** stratum_distance

        # NOTE: `values:*` stubbornness used to be applied here, but it's
        # really about how hard values:* tags themselves are to change — not
        # about a Pop's general resistance to ideas. It now lives in the
        # POP_CULTURE_SHIFT / CIV_ESTABLISHED_CULTURE_SHIFT apply handlers
        # (which is where culture-tag values actually mutate).

        # Size ratio: a smaller source Pop has proportionally less sway over a larger target
        tgt_size = max(0.001, target_pop.size_fractional)
        r *= min(1.0, src_size / tgt_size)

        # Stratum susceptibility: applied last as a flat modifier to total resistance
        susceptibility = _STRATUM_SUSCEPTIBILITY.get(tgt_class_str, 0.0)
        r *= (1.0 + susceptibility)

        return max(0.0, min(1.0, r))

    def _process_pop_contact(
        self,
        state: "SimulationState",
        cfg: TickConfig,
    ) -> list["StateMutation"]:
        """
        Passive belief drift between all co-located Pops.
        For each world, iterates ordered pairs (a→b) and emits POP_BELIEF_SHIFT
        mutations scaled by _pop_contact_resistance(). Same-civ pairs are included;
        the resistance function applies cross-civ and cross-stratum factors as appropriate.
        """
        mutations: list[StateMutation] = []
        for world_id in state.worlds:
            world_pops = self._pops_on_world(world_id, state)
            if len(world_pops) < 2:
                continue
            for i, pop_a in enumerate(world_pops):
                for pop_b in world_pops:
                    if pop_a is pop_b:
                        continue
                    src_civ_id = str(pop_a.civilization_id) if pop_a.civilization_id else None
                    src_species_id = str(pop_a.species_id) if pop_a.species_id else None
                    src_class = (pop_a.social_class.value if hasattr(pop_a.social_class, "value") else str(pop_a.social_class or "")) or None
                    resistance = self._pop_contact_resistance(
                        pop_b, src_civ_id, src_species_id, src_class, state, cfg,
                        src_size=pop_a.size_fractional,
                    )
                    # PopLocation distance penalty: bridges across orbital/abyssal
                    # PopLocations still contact, just at diminished strength.
                    dist_factor = _pop_distance_factor(
                        state, pop_a.current_location, pop_b.current_location,
                    )
                    for tag, a_strength in pop_a.dominant_beliefs.items():
                        if a_strength <= BELIEF_FLOOR:
                            continue
                        b_strength = pop_b.dominant_beliefs.get(tag, 0.0)
                        raw_delta = (a_strength - b_strength) * cfg.pop_contact_base_rate
                        delta = raw_delta * resistance * dist_factor
                        if abs(delta) > 1e-5:
                            mutations.append(StateMutation(
                                mutation_type=MutationType.POP_BELIEF_SHIFT,
                                target_id=pop_b.id,
                                field=tag,
                                delta=delta,
                                note=f"Pop contact drift ({tag})",
                            ))
        return mutations

    def _summarize_evaluation(
        self,
        luminary: "Luminary",
        delta: DispositionDelta,
        alignment: float,
    ) -> str:
        direction = "improving" if delta.results > 0 else "declining"
        return (
            f"{luminary.name}: domain alignment {alignment:.2f} ({direction}), "
            f"results Δ{delta.results:+.2f}, methods Δ{delta.methods:+.2f}."
        )

    def _apply_mutations(
        self,
        state: SimulationState,
        mutations: list["StateMutation"],
    ) -> SimulationState:
        """
        Apply a list of StateMutations to state.
        Numeric deltas are additive; new_value assignments
        are direct sets.
        """
        for m in mutations:
            tid = str(m.target_id) if m.target_id else None

            if m.mutation_type == MutationType.FOOTPRINT_CHANGE:
                if tid == str(state.demiurge.id):
                    obj = state.demiurge.footprint
                    current = getattr(obj, m.field, 0.0)
                    setattr(obj, m.field, max(0.0, min(1.0, current + (m.delta or 0))))
                elif tid in state.locations:
                    # e.g. field = "local_footprint.overt_miracles"
                    parts = m.field.split(".")
                    if len(parts) == 2:
                        # PopLocations don't carry footprint themselves; redirect
                        # to their parent SignificantLocation (world).
                        loc = state.locations[tid]
                        if isinstance(loc, PopLocation) and loc.parent_id is not None:
                            loc = state.locations.get(str(loc.parent_id), loc)
                        obj = getattr(loc, parts[0], None)
                        if obj is not None:
                            current = getattr(obj, parts[1], 0.0)
                            setattr(obj, parts[1], max(0.0, min(1.0, current + (m.delta or 0))))
                elif tid in state.luminary_attention:
                    current = state.luminary_attention[tid]
                    state.luminary_attention[tid] = max(0.0, min(1.0, current + (m.delta or 0)))
                elif tid in state.luminaries:
                    current = state.luminary_attention.get(tid, 0.2)
                    state.luminary_attention[tid] = max(0.0, min(1.0, current + (m.delta or 0)))

            elif m.mutation_type == MutationType.ESSENCE_CHANGE:
                current = getattr(state.essence, m.field, 0.0)
                setattr(state.essence, m.field, max(0.0, current + (m.delta or 0)))
                # Enforce apparent <= actual
                if state.essence.apparent > state.essence.actual:
                    state.essence.apparent = state.essence.actual

            elif m.mutation_type == MutationType.CONCEALMENT_CHANGE:
                current = getattr(state.essence, m.field, 0.0)
                setattr(state.essence, m.field, max(0.0, min(1.0, current + (m.delta or 0))))

            elif m.mutation_type == MutationType.MORTAL_ALIGNMENT:
                if tid in state.mortals:
                    mortal_ref = state.mortals[tid]
                    current = mortal_ref.alignment
                    _align_cap = 1.0 if mortal_ref.role == MortalRole.PROXIUS else 0.9
                    mortal_ref.alignment = max(
                        0.01, min(_align_cap, current + (m.delta or 0))
                    )

            elif m.mutation_type == MutationType.CIVILIZATION_STAT:
                if tid in state.civilizations:
                    parts = m.field.split(".")
                    if len(parts) == 2:
                        obj = getattr(state.civilizations[tid], parts[0])
                        current = getattr(obj, parts[1], 0.0)
                        setattr(obj, parts[1], max(0.0, min(1.0, current + (m.delta or 0))))
                    elif len(parts) == 1:
                        current = getattr(state.civilizations[tid], parts[0], 0.0)
                        setattr(
                            state.civilizations[tid], parts[0],
                            max(0.0, min(1.0, current + (m.delta or 0)))
                        )

            elif m.mutation_type in (
                MutationType.BELIEF_SHIFT,
                MutationType.DOMAIN_EXPRESSION,
            ):
                tag = str(m.new_value) if m.new_value else None
                if not tag:
                    pass
                elif tid in state.civilizations:
                    beliefs = state.civilizations[tid].dominant_beliefs
                    current = beliefs.get(tag, 0.0)
                    delta = (m.delta or 0.0) * self._belief_inertia(current, m.delta or 0.0)
                    cap = BELIEF_CAP if delta > 0 else 1.0
                    new_strength = max(0.0, min(cap, current + delta))
                    if new_strength > 0.0:
                        beliefs[tag] = new_strength
                    elif tag in beliefs:
                        del beliefs[tag]
                elif tid in state.locations:
                    loc = state.locations[tid]
                    if isinstance(loc, SignificantLocation):
                        domain = loc.domain_expression
                        current = domain.get(tag, 0.0)
                        new_strength = max(0.0, min(1.0, current + (m.delta or 0.0)))
                        if new_strength > 0.0:
                            domain[tag] = new_strength
                        elif tag in domain:
                            del domain[tag]

            elif m.mutation_type == MutationType.PROXIUS_APPOINTED:
                if tid in state.mortals:
                    mortal = state.mortals[tid]
                    mortal.role = MortalRole.PROXIUS
                    mortal.visibility = 1.0
                    mortal.pinned = True
                    if mortal.proxius_appointed_tick is None:
                        mortal.proxius_appointed_tick = state.tick_number
                    if mortal.id not in state.demiurge.proxius_ids:
                        state.demiurge.proxius_ids.append(mortal.id)
                    world = _resolve_world_for(state, mortal.current_location)
                    if world and mortal.id not in world.proxius_ids:
                        world.proxius_ids.append(mortal.id)

            elif m.mutation_type == MutationType.PROXIUS_DISMISSED:
                if tid in state.mortals:
                    mortal = state.mortals[tid]
                    mortal.role = MortalRole.OTHER
                    mortal.pinned = False
                    if mortal.id in state.demiurge.proxius_ids:
                        state.demiurge.proxius_ids.remove(mortal.id)
                    world = _resolve_world_for(state, mortal.current_location)
                    if world and mortal.id in world.proxius_ids:
                        world.proxius_ids.remove(mortal.id)

            elif m.mutation_type == MutationType.MORTAL_POP_AGED_OUT:
                if tid in state.mortals:
                    state.mortals[tid].pop_id = None

            elif m.mutation_type == MutationType.MORTAL_STATUS:
                if tid in state.mortals and m.new_value:
                    state.mortals[tid].status = MortalStatus(m.new_value)

            elif m.mutation_type == MutationType.MORTAL_AGE:
                if tid in state.mortals and m.field in ("chrono_age", "bio_age"):
                    current = getattr(state.mortals[tid], m.field, 0.0)
                    setattr(state.mortals[tid], m.field, current + (m.delta or 0))

            elif m.mutation_type == MutationType.MORTAL_VISIBILITY:
                if tid in state.mortals:
                    if m.new_value is not None:
                        state.mortals[tid].visibility = max(0.0, min(1.0, float(m.new_value)))
                    elif m.delta is not None:
                        current = state.mortals[tid].visibility
                        state.mortals[tid].visibility = max(0.0, min(1.0, current + m.delta))

            elif m.mutation_type == MutationType.ENTITY_VISIBILITY:
                entity = (
                    state.locations.get(tid)
                    or state.civilizations.get(tid)
                    or state.species.get(tid)
                )
                if entity is not None:
                    if m.new_value is not None:
                        entity.visibility = max(0.0, min(1.0, float(m.new_value)))
                    elif m.delta is not None:
                        entity.visibility = max(0.0, min(1.0, entity.visibility + m.delta))

            elif m.mutation_type == MutationType.WORLD_CONDITION:
                if tid in state.locations and m.new_value:
                    loc = state.locations[tid]
                    if isinstance(loc, SignificantLocation):
                        loc.condition = LocCondition(m.new_value)

            elif m.mutation_type == MutationType.ENTITY_DESTROYED:
                if tid in state.civilizations:
                    civ = state.civilizations.pop(tid)
                    loc_id = str(civ.origin_location_id) if civ.origin_location_id else None
                    world = state.worlds.get(loc_id) if loc_id else None
                    if world and civ.id in world.civilization_ids:
                        world.civilization_ids.remove(civ.id)
                elif tid in state.mortals:
                    state.mortals[tid].status = MortalStatus.DECEASED

            elif m.mutation_type == MutationType.EXILED_TO_UNDERREAL:
                if tid in state.civilizations:
                    civ = state.civilizations.pop(tid)
                    loc_id = str(civ.origin_location_id) if civ.origin_location_id else None
                    world = state.worlds.get(loc_id) if loc_id else None
                    if world:
                        if civ.id in world.civilization_ids:
                            world.civilization_ids.remove(civ.id)
                        world.domain_expression["domain:underreal_trace"] = min(
                            1.0,
                            world.domain_expression.get("domain:underreal_trace", 0.0) + 0.4,
                        )
                elif tid in state.mortals:
                    mortal = state.mortals[tid]
                    mortal.status = MortalStatus.DECEASED
                    world = _resolve_world_for(state, mortal.current_location)
                    if world:
                        world.domain_expression["domain:underreal_trace"] = min(
                            1.0,
                            world.domain_expression.get("domain:underreal_trace", 0.0) + 0.2,
                        )
                elif tid in state.locations:
                    loc = state.locations[tid]
                    if isinstance(loc, SignificantLocation):
                        loc.condition = LocCondition.BARREN
                        loc.domain_expression = {"domain:underreal_trace": 1.0}

            elif m.mutation_type == MutationType.DISPOSITION_CHANGE:
                if tid in state.luminaries:
                    lum = state.luminaries[tid]
                    if m.field == "results":
                        lum.disposition.results = max(
                            -1.0, min(1.0, lum.disposition.results + (m.delta or 0))
                        )
                    elif m.field == "methods":
                        lum.disposition.methods = max(
                            -1.0, min(1.0, lum.disposition.methods + (m.delta or 0))
                        )

            elif m.mutation_type == MutationType.SPECIES_CREATED:
                if isinstance(m.new_value, Species):
                    sp = m.new_value
                    state.species[str(sp.id)] = sp
                    if tid and tid in state.locations:
                        loc = state.locations[tid]
                        if isinstance(loc, SignificantLocation) and sp.id not in loc.species_ids:
                            loc.species_ids.append(sp.id)

            elif m.mutation_type == MutationType.SPECIES_UPLIFTED:
                if tid in state.species:
                    state.species[tid].sapient = True
                    state.species[tid].condition = SpeciesCondition.THRIVING

            elif m.mutation_type == MutationType.SPECIES_CONDITION:
                if tid in state.species and m.new_value:
                    state.species[tid].condition = SpeciesCondition(m.new_value)

            elif m.mutation_type == MutationType.DEMIURGE_UNLOCK:
                tag = str(m.new_value) if m.new_value else None
                if tag and tag not in state.demiurge.unlocked_domain_tags:
                    state.demiurge.unlocked_domain_tags.append(tag)

            elif m.mutation_type == MutationType.AFFILIATED_DOMAIN_CHANGE:
                val = str(m.new_value) if m.new_value else ""
                if "→" in val:
                    old_tag, new_tag = val.split("→", 1)
                    if old_tag in state.demiurge.affiliated_domains:
                        state.demiurge.affiliated_domains.remove(old_tag)
                    if new_tag not in state.demiurge.affiliated_domains:
                        state.demiurge.affiliated_domains.append(new_tag)

            elif m.mutation_type == MutationType.EVENT_EMITTED:
                if isinstance(m.new_value, Event):
                    eid = str(m.new_value.id)
                    if eid not in state.active_events:
                        state.active_events[eid] = m.new_value

            elif m.mutation_type == MutationType.PROXIUS_AUDITED:
                if tid:
                    state.proxii_audited_this_tick.add(tid)

            elif m.mutation_type == MutationType.PROXIUS_AUDIT_RECORDED:
                if tid and tid in state.mortals and m.new_value is not None:
                    mortal = state.mortals[tid]
                    mortal.last_audit_text = str(m.new_value)
                    try:
                        mortal.last_audit_tick = int(m.field) if m.field else state.tick_number
                    except (TypeError, ValueError):
                        mortal.last_audit_tick = state.tick_number

            elif m.mutation_type == MutationType.LUMINARY_ORDERS_RESPONSE:
                if tid and tid in state.luminaries and m.new_value is not None:
                    lum = state.luminaries[tid]
                    lum.last_orders_response = str(m.new_value)
                    try:
                        lum.last_orders_response_tick = int(m.field) if m.field else state.tick_number
                    except (TypeError, ValueError):
                        lum.last_orders_response_tick = state.tick_number

            elif m.mutation_type == MutationType.PROXIUS_GOAL_SET:
                if tid in state.mortals and isinstance(m.new_value, ProxiusGoal):
                    state.mortals[tid].active_goal = m.new_value

            elif m.mutation_type == MutationType.PROXIUS_GOAL_CLEARED:
                if tid in state.mortals:
                    old_goal = state.mortals[tid].active_goal
                    state.mortals[tid].active_goal = None
                    # If the cleared goal had a goal Pop (Pop B), unpin it and set cooldown
                    if old_goal and old_goal.goal_pop_id:
                        gpid = str(old_goal.goal_pop_id)
                        goal_pop = state.pops.get(gpid)
                        if goal_pop:
                            goal_pop.preaching_imago_id = None
                            goal_pop.pinned = False
                            goal_pop.preaching_goal_cooldown_until = state.tick_number + 10

            elif m.mutation_type == MutationType.REVELATION_GAINED:
                tag = m.field
                if tag and m.delta is not None:
                    current = state.demiurge.revelation_pools.get(tag, 0.0)
                    state.demiurge.revelation_pools[tag] = round(max(0.0, current + m.delta), 2)
                    if m.delta > 0:
                        state.demiurge.lifetime_revelation = round(
                            state.demiurge.lifetime_revelation + m.delta, 2
                        )

            elif m.mutation_type == MutationType.IMAGO_REVEALED:
                node_id = str(m.new_value) if m.new_value else None
                if node_id and node_id not in state.demiurge.unlocked_imagines:
                    state.demiurge.unlocked_imagines.append(node_id)
                    state.demiurge.revealed_imagines += 1

            elif m.mutation_type == MutationType.POP_BELIEF_SHIFT:
                tag = str(m.new_value) if m.new_value else m.field
                if tid and tid in state.pops and tag:
                    beliefs = state.pops[tid].dominant_beliefs
                    current = beliefs.get(tag, 0.0)
                    delta = (m.delta or 0.0) * self._belief_inertia(current, m.delta or 0.0)
                    cap = BELIEF_CAP if delta > 0 else 1.0
                    new_strength = max(0.0, min(cap, current + delta))
                    # Sub-floor entries are permitted to persist within a tick so
                    # that small multi-source contributions (e.g. a 4-tick whisper
                    # echo's per-tick splashes) can accumulate and cross BELIEF_FLOOR
                    # together. `_prune_weak_beliefs` clears any entry that still
                    # sits below floor at the end of the next passive phase, so
                    # one-off below-floor shifts do not leave ghost residue.
                    if new_strength > 1e-5:
                        beliefs[tag] = new_strength
                    elif tag in beliefs:
                        del beliefs[tag]

            elif m.mutation_type == MutationType.MORTAL_BELIEF_SHIFT:
                tag = str(m.new_value) if m.new_value else m.field
                if tid and tid in state.mortals and tag:
                    beliefs = state.mortals[tid].belief_tags
                    current = beliefs.get(tag, 0.0)
                    delta = (m.delta or 0.0) * self._belief_inertia(current, m.delta or 0.0)
                    cap = BELIEF_CAP if delta > 0 else 1.0
                    new_strength = max(0.0, min(cap, current + delta))
                    # Sub-floor entries persist within a tick so multi-source
                    # contributions (e.g. a 4-tick whisper echo's per-tick shifts
                    # when each is below floor) can accumulate across floor.
                    # `_prune_weak_beliefs` clears entries still sub-floor at the
                    # end of the next passive phase.
                    if new_strength > 1e-5:
                        beliefs[tag] = new_strength
                    elif tag in beliefs:
                        del beliefs[tag]

            elif m.mutation_type == MutationType.MORTAL_CULTURE_SHIFT:
                tag = str(m.new_value) if m.new_value else m.field
                if tid and tid in state.mortals and tag:
                    culture = state.mortals[tid].culture_tags
                    current = culture.get(tag, 0.0)
                    delta = (m.delta or 0.0) * self._belief_inertia(current, m.delta or 0.0)
                    # values:* tags are stubborn — extra dampening on either direction.
                    if tag.startswith("values:"):
                        delta *= max(0.05, 1.0 - state.config.values_stubbornness_factor)
                    cap = BELIEF_CAP if delta > 0 else 1.0
                    new_strength = max(0.0, min(cap, current + delta))
                    # Sub-floor accumulation — see MORTAL_BELIEF_SHIFT above.
                    if new_strength > 1e-5:
                        culture[tag] = new_strength
                    elif tag in culture:
                        del culture[tag]

            elif m.mutation_type == MutationType.POP_VISIBILITY:
                if tid and tid in state.pops:
                    pop = state.pops[tid]
                    if m.new_value is not None:
                        pop.visibility = max(0.0, min(1.0, float(m.new_value)))
                    elif m.delta is not None:
                        pop.visibility = max(0.0, min(1.0, pop.visibility + m.delta))

            elif m.mutation_type == MutationType.CIV_ESTABLISHED_SHIFT:
                tag = str(m.new_value) if m.new_value else m.field
                if tid and tid in state.civilizations and tag:
                    established = state.civilizations[tid].established_beliefs
                    current = established.get(tag, 0.0)
                    delta = (m.delta or 0.0) * self._belief_inertia(current, m.delta or 0.0)
                    cap = BELIEF_CAP if delta > 0 else 1.0
                    new_strength = max(0.0, min(cap, current + delta))
                    if new_strength > BELIEF_FLOOR:
                        established[tag] = new_strength
                    elif tag in established:
                        del established[tag]

            elif m.mutation_type == MutationType.CIV_ESTABLISHED_CULTURE_SHIFT:
                tag = str(m.new_value) if m.new_value else m.field
                if tid and tid in state.civilizations and tag:
                    est_cult = state.civilizations[tid].established_culture_tags
                    current = est_cult.get(tag, 0.0)
                    delta = (m.delta or 0.0) * self._belief_inertia(current, m.delta or 0.0)
                    # values:* tags are stubborn — extra dampening on either direction.
                    if tag.startswith("values:"):
                        delta *= max(0.05, 1.0 - state.config.values_stubbornness_factor)
                    cap = BELIEF_CAP if delta > 0 else 1.0
                    new_strength = max(0.0, min(cap, current + delta))
                    if new_strength > CULTURE_FLOOR:
                        est_cult[tag] = new_strength
                    elif tag in est_cult:
                        del est_cult[tag]

            elif m.mutation_type == MutationType.POP_SPLINTER:
                # m.target_id = parent Pop UUID; m.new_value = splinter Pop object
                parent_pop = state.pops.get(tid) if tid else None
                splinter: "Pop" = m.new_value  # type: ignore[assignment]
                if parent_pop is not None and splinter is not None:
                    splinter_sz = splinter.size_fractional
                    # Reduce parent size
                    parent_pop.size_fractional = max(
                        0.0, parent_pop.size_fractional - splinter_sz
                    )
                    # Wire lineage
                    splinter_id_str = str(splinter.id)
                    parent_pop.child_pop_ids.append(splinter.id)
                    # Register splinter in state
                    state.pops[splinter_id_str] = splinter
                    # Wire splinter into civ and PopLocation
                    if splinter.civilization_id:
                        civ = state.civilizations.get(str(splinter.civilization_id))
                        if civ and splinter.id not in civ.pop_ids:
                            civ.pop_ids.append(splinter.id)
                    if splinter.current_location:
                        pop_loc = state.locations.get(str(splinter.current_location))
                        if pop_loc and hasattr(pop_loc, "pop_ids") and splinter.id not in pop_loc.pop_ids:
                            pop_loc.pop_ids.append(splinter.id)

            elif m.mutation_type == MutationType.POP_SIZE_CHANGE:
                if tid and tid in state.pops and m.delta is not None:
                    state.pops[tid].size_fractional = max(
                        0.0, state.pops[tid].size_fractional + m.delta
                    )

            elif m.mutation_type == MutationType.POP_RIDER_TRAIT:
                tag = m.field
                if tid and tid in state.pops and tag and m.delta is not None:
                    pop = state.pops[tid]
                    pop.rider_traits[tag] = max(
                        0.0, min(1.0, pop.rider_traits.get(tag, 0.0) + m.delta)
                    )

            elif m.mutation_type == MutationType.POP_CULTURE_SHIFT:
                tag = m.field
                if tid and tid in state.pops and tag and m.delta is not None:
                    pop = state.pops[tid]
                    current = pop.culture_tags.get(tag, 0.0)
                    delta = m.delta * self._belief_inertia(current, m.delta)
                    # values:* tags are stubborn — extra dampening on either direction.
                    if tag.startswith("values:"):
                        delta *= max(0.05, 1.0 - state.config.values_stubbornness_factor)
                    cap = BELIEF_CAP if delta > 0 else 1.0
                    new_val = max(0.0, min(cap, current + delta))
                    # Sub-floor accumulation (lever C, culture variant): allow
                    # entries to persist below CULTURE_FLOOR within a tick so
                    # repeated splashes can compound. `_prune_weak_beliefs`
                    # clears entries still under floor at the next passive phase.
                    if new_val > 1e-5:
                        pop.culture_tags[tag] = new_val
                    elif tag in pop.culture_tags:
                        del pop.culture_tags[tag]

            elif m.mutation_type == MutationType.POP_ABSORBED:
                # target_id = Pop A UUID, new_value = Pop B UUID string
                pop_a = state.pops.pop(tid, None) if tid else None
                goal_pid = str(m.new_value) if m.new_value else None
                pop_b = state.pops.get(goal_pid) if goal_pid else None
                if pop_a and pop_b:
                    # Transfer notable mortals; flag them as origin-subsumed
                    for mid in pop_a.notable_mortal_ids:
                        mortal_m = state.mortals.get(str(mid))
                        if mortal_m:
                            mortal_m.origin_pop_subsumed = True
                            if mid not in pop_b.notable_mortal_ids:
                                pop_b.notable_mortal_ids.append(mid)
                    # Remove Pop A from civilization pop_ids
                    if pop_a.civilization_id:
                        civ = state.civilizations.get(str(pop_a.civilization_id))
                        if civ and pop_a.id in civ.pop_ids:
                            civ.pop_ids.remove(pop_a.id)
                    # Remove Pop A from its PopLocation
                    pop_loc = state.locations.get(str(pop_a.current_location))
                    if pop_loc and hasattr(pop_loc, "pop_ids") and pop_a.id in pop_loc.pop_ids:
                        pop_loc.pop_ids.remove(pop_a.id)
                    # End goal target status on Pop B; unpin; start cooldown
                    pop_b.preaching_imago_id = None
                    pop_b.pinned = False
                    pop_b.preaching_goal_cooldown_until = state.tick_number + 10

        return state
