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
    ChangeAffiliatedDomainsIntent, ScryIntent, ScryScope, RescindDirectiveIntent,
    TargetType, CategoryCooldowns, CATEGORY_BASE_COOLDOWNS, compute_cooldown,
)
from core.eval_core import (
    UniverseDomainProfile,
    LuminaryEvaluation,
    DialogueTrigger, DialogueTriggerType,
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
    Universe, Location, System, SignificantLocation, PopLocation, TravelNetwork,
    Civilization, NotableMortal, EntityAge,
    MortalRole, MortalStatus, MortalProminence, LocCondition,
    Species, SpeciesCondition,
    Pop, SocialClass, is_wild_civ, pop_label, Faction,
)
from utilities.domain_registry import DomainRegistry, LuminaryPersonality, get_registry as get_domain_registry
from utilities.culture_registry import (
    CultureRegistry, get_registry as get_culture_registry, peer_culture_tags,
)
from utilities.imago_registry import get_registry as get_imago_registry
from core.event_core import Event, EventType, StrengthCurve
from core.agent_core import ProxiusGoal, AgentActionChoice, TravelIntent, DirectiveFact, KnowledgeBase
from logic.mortal_agent_logic import (
    evaluate_mortal_action,
    _select_local_pop,
    _pop_practice_quality,
    _pop_social_quality,
    _effective_commerce_quality,
    _pop_novelty,
    LEISURE_BASE_GAIN,
    SOCIALIZE_BASE_GAIN,
    LEISURE_SATIATION_HOLD_BASE,
    SOCIALIZE_SATIATION_HOLD_BASE,
    CREW_LEISURE_MULTIPLIER,
    EXPLORATION_NOVELTY_THRESHOLD,
    SOCIAL_NOVELTY_FLOOR,
)
from logic.needs_config import (
    NEED_SUSTENANCE, NEED_SAFETY, NEED_LEISURE, NEED_BELONGING, NEED_PURPOSE, NEED_STATUS,
    DESIRE_ACCUMULATION, DESIRE_EXPLORATION, DESIRE_EXPRESSION,
    compute_desire_profile,
)
from logic.sim_utils import (
    resolve_world_id_for as _resolve_world_id_for,
    resolve_world_for as _resolve_world_for,
    cosine_similarity,
    pop_domain_receptivity as _pop_domain_receptivity,
    compute_link_factor,
    LINK_DRIFT_RATE, LINK_BREAK_THRESHOLD, LINK_DRIFT_STRIDE,
    LINK_SPLASH_OWN_POP_SCALE, LINK_SPLASH_WORLD_POP_SCALE, LINK_VISIBILITY_CASCADE_SCALE,
)
from logic.essence_generation import process_essence_generation
from logic.proxius_logic import resolve_proxius_agents
from logic.visibility_logic import (
    ENTITY_VISIBILITY_FLOOR, VISIBILITY_STALL_ON_CAP, VISIBILITY_STALL_SCENARIO_START,
    PROXIUS_COMPLIANCE_FACTOR,
    process_visibility_decay,
    emit_upward_visibility_splash, emit_omen_visibility_splash, emit_influence_visibility_splash,
)
from logic.belief_propagation import (
    BELIEF_FLOOR, CULTURE_FLOOR, BELIEF_CAP, LINEAGE_BLEED_FRACTION,
    belief_inertia,
    location_distance_from_core, pop_distance_factor,
    pops_on_world,
    pop_contact_resistance, process_pop_contact,
    recompute_civ_dominant_beliefs, recompute_civ_culture_tags,
    anchor_identity_pull,
    civ_conformity_pressure,
    process_location_ambient_influence,
    process_pop_cultural_noise,
    emit_lineage_bleed,
)


# ─────────────────────────────────────────
# POP SPLINTER CONSTANTS
# ─────────────────────────────────────────

SPLINTER_DIVERGENCE_THRESHOLD = 0.50
# Cosine distance (1 − similarity) at which a Pop's beliefs are divergent
# enough from civ.established_beliefs to trigger a population split.

SPLINTER_MIN_SIZE = 4.0
# Pop must be at least this large (size_fractional) to split.
# Prevents micro-Pops from fragmenting further.

SPLINTER_COOLDOWN_TICKS = 30
# After splitting, a Pop cannot split again for this many ticks.

# Stratum order lowest→highest. Used by the arrival milieu algorithm.
_STRATUM_ORDER: list[SocialClass] = [
    SocialClass.WILD,
    SocialClass.FERAL,
    SocialClass.UNDERCLASS,
    SocialClass.COMMON,
    SocialClass.ARTISAN,
    SocialClass.TRADER,
    SocialClass.WARRIOR,
    SocialClass.SCHOLAR,
    SocialClass.ELITE,
]

SPLINTER_CHECK_STRIDE        = 10     # ticks between splinter/reabsorption checks
SPLINTER_MIN_FRACTION        = 0.10   # smallest possible splinter (at threshold divergence)
SPLINTER_MAX_FRACTION        = 0.45   # largest possible splinter (at max divergence)
SPLINTER_BELIEF_NUDGE_FACTOR = 0.50   # how far parent nudges toward civ per split
SPLINTER_PROB_MIDPOINT       = 0.70   # divergence at which P(split) = 50%
SPLINTER_PROB_STEEPNESS      = 15.0   # sigmoid steepness

REABSORPTION_CONVERGENCE_THRESHOLD = 0.85   # cosine similarity floor to begin drain
REABSORPTION_DRAIN_FRACTION        = 0.20   # fraction of source drained per check

_CIV_SCALE_SPLINTER_OFFSET: dict[str, float] = {
    "nascent":         +0.20,
    "tribal":          +0.15,
    "city_state":      +0.08,
    "regional":        +0.03,
    "continental":      0.00,
    "planetary":       -0.03,
    "interplanetary":  -0.06,
    "interstellar":    -0.10,
    "intergalactic":   -0.15,
}


_CULTURE_DIVERGENCE_WEIGHTS: dict[str, float] = {
    "values":   1.0,
    "religion": 1.1,
}
# practice: and other prefixes are intentionally absent — excluded from divergence.


def _culture_divergence(pop_tags: dict[str, float], civ_tags: dict[str, float]) -> float:
    """Cosine distance on culture tags, restricted to values: and religion: prefixes.

    religion: entries are weighted 1.1× relative to values: (1.0×) before the
    cosine computation, making religious disagreement slightly more destabilising.
    Returns 0.0 if either side has no relevant tags after filtering.
    """
    def _weighted(tags: dict[str, float]) -> dict[str, float]:
        out: dict[str, float] = {}
        for k, v in tags.items():
            w = _CULTURE_DIVERGENCE_WEIGHTS.get(k.split(":", 1)[0])
            if w is not None:
                out[k] = v * w
        return out

    pop_w = _weighted(pop_tags)
    civ_w = _weighted(civ_tags)
    if not pop_w or not civ_w:
        return 0.0
    return 1.0 - cosine_similarity(pop_w, civ_w)


def _splinter_probability(divergence: float, effective_midpoint: float) -> float:
    """Sigmoid P(split) given divergence and the civ-scale-adjusted midpoint."""
    x = SPLINTER_PROB_STEEPNESS * (divergence - effective_midpoint)
    return 1.0 / (1.0 + math.exp(-x))


def _splinter_fraction(divergence: float) -> float:
    """Fraction of parent that breaks away, scaled linearly with divergence magnitude."""
    span  = divergence - SPLINTER_DIVERGENCE_THRESHOLD
    scale = span / (1.0 - SPLINTER_DIVERGENCE_THRESHOLD)
    return SPLINTER_MIN_FRACTION + scale * (SPLINTER_MAX_FRACTION - SPLINTER_MIN_FRACTION)


def _redistribute_mortals_on_splinter(
    parent: "Pop",
    splinter: "Pop",
    mortals: "dict[str, NotableMortal]",
) -> list["UUID"]:
    """Re-assign notable mortals between parent and splinter based on belief similarity.

    Called after the parent's belief nudge so the two pops have meaningfully
    different beliefs. Returns UUIDs of mortals that moved to the splinter.
    """
    moved: list["UUID"] = []
    for mid in list(parent.notable_mortal_ids):
        mortal = mortals.get(str(mid))
        if mortal is None:
            continue
        sim_parent   = cosine_similarity(mortal.belief_tags, parent.dominant_beliefs)
        sim_splinter = cosine_similarity(mortal.belief_tags, splinter.dominant_beliefs)
        if sim_splinter > sim_parent:
            parent.notable_mortal_ids.remove(mid)
            splinter.notable_mortal_ids.append(mid)
            mortal.pop_id = splinter.id
            moved.append(mid)
    return moved


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

RIDER_ATTRITION_BASE = 0.00002
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

# Per-scale weights for civ belief contribution to universal domain expression.
# Ordered so inherent location weight (3.0) always exceeds even max-scale civ (1.60).
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

# ─────────────────────────────────────────
# PUISSANCE CONSTANTS
# ─────────────────────────────────────────

REV_SCALE    = 500.0   # lifetime_revelation saturation point (revelation component)
IMAGO_SCALE  = 40.0    # tier-weighted imago score saturation point
TICK_SCALE   = 3650.0  # tick number saturation point (minor long-run contribution; ~10yr at 1 day/tick)
_IMAGO_TIER_WEIGHTS: dict[int, int] = {1: 1, 2: 2, 3: 4, 4: 8}

BASE_INFLUENCE       = 0.75   # floor success chance for Whisper / Shape Dream
PUISSANCE_WEIGHT     = 0.15   # max bonus from a fully mature Demiurge
VISIBILITY_WEIGHT    = 0.05   # max bonus from target visibility at 1.0
FRAMING_WEIGHT       = 0.04   # max bonus from perfect framing resonance
PUISSANCE_TIER_BONUS = 0.08   # max success-threshold shift for reliability-tier actions

# Scry footprint and essence costs — also consumed by the UI for display.
# World footprint rises with momentum: SCRY_FP_BASE[WORLD] + momentum * SCRY_FP_WORLD_MOM.
SCRY_FP_WORLD_MOM: float = 0.09   # at momentum=1.0, world total = 0.01 + 0.09 = 0.10
SCRY_FP_BASE: "dict[ScryScope, float]" = {
    ScryScope.WORLD:    0.01,
    ScryScope.SYSTEM:   0.10,
    ScryScope.GALAXY:   0.20,
    ScryScope.UNIVERSE: 0.35,
}
SCRY_ESSENCE: "dict[ScryScope, float]" = {
    ScryScope.WORLD:    0.0,
    ScryScope.SYSTEM:   0.0,
    ScryScope.GALAXY:   3.0,
    ScryScope.UNIVERSE: 5.0,
}


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
    """Sum of adjusted costs for all unrevealed Imāginēs in the Domain's tree."""
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
        if isinstance(loc, PopLocation):
            total += loc.domain_expression.get(domain_tag, 0.0) * 0.5
            continue
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
    Normalized domain expression at a location: 0.0–1.0.
    For a PopLocation, combines the parent world's ambient expression with the
    PopLocation's own domain_expression. Used for Proxius Commission Inquiry bonus.
    """
    world = _resolve_world_for(state, loc_id)
    world_expr = world.domain_expression.get(domain_tag, 0.0) if world is not None else 0.0
    loc = state.locations.get(str(loc_id))
    pop_loc_expr = loc.domain_expression.get(domain_tag, 0.0) if isinstance(loc, PopLocation) else 0.0
    return max(0.0, min(1.0, world_expr + pop_loc_expr))


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
    footprint_decay_rate: float = 0.0005
    # Subtracted from each footprint category per tick,
    # floor 0.0. Subtle influence fades faster than
    # direct creation — handled by per-category multipliers.
    footprint_decay_multipliers: dict[str, float] = Field(
        default_factory=lambda: {
            "overt_miracles":  1.0,
            "subtle_influence": 0.8,
            "proxius_activity": 0.8,
            "direct_creation":  0.4,  # Reshaping a world doesn't unhappen quickly
        }
    )

    # Concealment degradation
    concealment_decay_rate: float = 0.001
    # concealment_integrity drops this much per tick passively.
    # Spending Essence adds on top of this.

    # Civilization momentum
    # How much a civilization's stats move on their own per tick.
    civ_momentum_rate: float = 0.003
    civ_noise_factor: float = 0.004
    # Small random perturbation each tick — civilizations
    # are not perfectly predictable.

    # Mortal alignment drift
    # Proxii and Heralds slowly drift toward their personal tags
    # and away from their patron's agenda unless directed.
    alignment_drift_rate: float = 0.001

    # Mortal visibility decay
    # Base rate; modulated by prominence: effective_decay = rate * (1.0 - prominence).
    mortal_visibility_decay_rate: float = 0.001

    # Window visibility decay for non-mortal entities
    location_visibility_decay_rate: float = 0.0003
    civ_visibility_decay_rate: float = 0.0003
    species_visibility_decay_rate: float = 0.0003

    # Luminary attention decay
    # Attention naturally falls when nothing interesting happens.
    attention_decay_rate: float = 0.002

    # Passive Proxius footprint
    # Each active Proxius generates this much proxius_activity per tick.
    # Policy-compliant worlds (≤ max_per_world Proxii) contribute at
    # PROXIUS_COMPLIANCE_FACTOR of this rate; excess Proxii contribute at full rate.
    proxius_passive_footprint_rate: float = 0.0002

    # Evaluation frequency
    # Not every tick triggers a full Luminary evaluation.
    # Evaluation happens when: attention crosses a threshold,
    # a constraint is breached, or this many ticks have elapsed.
    evaluation_interval: float = 360.0

    # Essence generation weights (tuning targets; adjust after playtesting)
    essence_location_weight: float = 3.0
    # Multiplier for SignificantLocation.domain_expression contributions.

    essence_pop_location_weight: float = 1.5
    # Multiplier for PopLocation.domain_expression contributions (half world weight).
    # Sapient Pops (via essence_pop_weight) collectively outweigh any single
    # location; locations outweigh pre-sapient Pops; mortals are the floor.

    essence_pop_weight: float = 1.0
    # Baseline multiplier applied to all Pop dominant_beliefs contributions
    # (before scale_mult and belief-match bonuses are applied).
    # At 1×, Pop dominance reflects sheer numbers/size rather than artificial amplification.

    essence_mortal_weight: float = 0.5
    # Multiplier for NotableMortal.belief_tags contributions.

    essence_claiming_exponent: float = 0.40
    # Exponent applied to total pantheon affinity to derive the Luminary group's
    # claim fraction: lum_fraction = lum_total_aff ** essence_claiming_exponent.
    # At 0.40: aff=0.2→52.5%, aff=0.5→75.8%, aff=0.8→91.5%, aff=0.9→95.9%.
    # Demiurge gets 1 − lum_fraction of any affiliated domain pool.

    luminary_essence_baseline_rate: float = 0.05
    # Expected weighted domain production per effective-affinity-point per tick.
    # Threshold = effective_affinity × baseline_rate × ticks_since_last_eval,
    # where effective_affinity uses diminishing returns (see luminary_essence_decay).
    # At 1-day ticks with monthly essence fires and annual evaluation (360 ticks),
    # threshold ≈ effective_affinity × 18 per year.

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

    luminary_essence_passive_rise: float = 0.1
    # Per-tick expectation creep added each evaluation period, diminishing with age.
    # Actual increment = passive_rise × ticks_since / max(tick_number, 1).
    # At tick 1 with ticks_since=6: full 0.50×6=3.0 added. At tick 50: 0.50×6/50=0.06.
    # Ensures idle play eventually falls short even if starting conditions are generous.

    # Pop dynamics
    pop_conformity_base: float = 0.0003
    # Base rate at which Pops are nudged toward civ.established_beliefs per tick.
    # Scaled by scale_conformity_mult * civ.health.cohesion at runtime.

    civ_conformity_stride: int = 10
    # Conformity pressure fires every N ticks (not every tick) to reduce churn.

    anchor_pull_rate: float = 0.0002
    # Base rate at which splinter Pops are pulled back toward their identity_anchor per stride.
    anchor_fade_strides: int = 3
    # Strides before cooldown expiry at which anchor pull strength begins scaling down to zero.

    pop_visibility_drift_rate: float = 0.002
    # Rate at which Pop.visibility rises toward min(civ.visibility, world.visibility).

    pop_visibility_decay_rate: float = 0.0003
    # Base per-tick decay for Pop visibility; modulated by size and parent visibility.

    established_drift_base: float = 0.0005
    # Base rate at which civ.established_beliefs drifts toward civ.dominant_beliefs per tick.
    # Scaled by civ.health.cohesion at runtime.

    # Cross-Pop contact (passive belief drift between co-located Pops of different civs)
    pop_contact_base_rate: float = 0.00003
    pop_contact_stride: int = 7
    # Pop contact fires every N ticks. Co-prime with civ_conformity_stride (10)
    # so the two rarely fire on the same tick.
    cross_civ_contact_factor: float = 0.15
    cross_civ_scale_penalty: float = 0.08
    cross_species_contact_factor: float = 0.50
    cross_stratum_contact_factor: float = 0.70

    # Ambient location belief influence
    location_ambient_stride: int = 61
    location_ambient_base_scale: float = 0.2
    location_ambient_distance_falloff: float = 0.9

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

    # Per-pop periodic cultural noise (organic drift not captured at macro level)
    pop_noise_sigma: float = 0.03   # gauss std dev; most samples near 0, rare events up to cap
    pop_noise_cap: float = 0.25     # hard clamp on individual noise delta magnitude


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
    wealth_delta: float = 0.0
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
# PAUSE EVENTS
# Signals to the RTwP loop that auto-advance should stop.
# ─────────────────────────────────────────

class PauseEventType(str, Enum):
    # Hard-pause (not configurable — Phase 3a)
    LUMINARY_CONTACT   = "luminary_contact"    # any Luminary dialogue trigger fires
    LUMINARY_ULTIMATUM = "luminary_ultimatum"  # CONSTRAINT_ULTIMATUM or THREAT trigger
    HERALD_CONTACT     = "herald_contact"      # stub — Heralds not yet implemented
    PROXIUS_CONTACT    = "proxius_contact"     # stub — urgent Proxius signal (TBD)
    # Default-pause (configurable off — Phase 3b)
    EVALUATION_COMPLETE    = "evaluation_complete"     # a Luminary evaluated this tick
    REVELATION_THRESHOLD   = "revelation_threshold"    # an Imago node was revealed
    QUEUED_ACTION_COMPLETE = "queued_action_complete"  # a manually-queued action resolved
    PINNED_MORTAL_DIED     = "pinned_mortal_died"      # a pinned mortal died this tick
    # Default-silent (configurable on — Phase 3c)
    POP_SPLINT          = "pop_splint"           # a Pop splinted this tick
    DOMAIN_THRESHOLD    = "domain_threshold"     # a domain expression shifted significantly
    TRAVEL_COMPLETE     = "travel_complete"      # a mortal arrived at their destination
    MINOR_AGENT_UPDATE  = "minor_agent_update"   # Proxius report surfaced this tick

# Trigger types that map to LUMINARY_ULTIMATUM (everything else is LUMINARY_CONTACT).
_ULTIMATUM_DIALOGUE_TYPES: frozenset[DialogueTriggerType] = frozenset({
    DialogueTriggerType.CONSTRAINT_ULTIMATUM,
    DialogueTriggerType.THREAT,
})


class PauseEvent(BaseModel):
    event_type:       PauseEventType
    description:      str = ""
    is_hard_pause:    bool = True   # True → always pauses; False → configurable
    pauses_by_default: bool = False  # for soft events: True = default-on, False = default-off


class PauseConfig(BaseModel):
    """Per-trigger pause overrides persisted in save state."""
    overrides: dict[PauseEventType, bool] = Field(default_factory=dict)

    def should_pause(self, event: "PauseEvent") -> bool:
        if event.is_hard_pause:
            return True
        return self.overrides.get(event.event_type, event.pauses_by_default)


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
    universe_age_before: EntityAge
    universe_age_after:  EntityAge

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

    mortal_narratives:  list[str] = Field(default_factory=list)
    # Travel/activity reports for pinned notable mortals

    dialogue_triggers:  list["DialogueTrigger"] = Field(default_factory=list)
    # Unsuppressed triggers only — these go to the player

    terminal: TerminalCheck = Field(default_factory=TerminalCheck)

    pause_events: list[PauseEvent] = Field(default_factory=list)
    # Hard-pause events stop auto-advance; soft-pause events (3b/3c) are configurable.

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
    species:          dict[str, "Species"] = Field(default_factory=dict)
    travel_networks:  dict[str, "TravelNetwork"] = Field(default_factory=dict)
    factions:         dict[str, "Faction"] = Field(default_factory=dict)

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

    # Per-category cooldown counters; decremented each tick in Phase 2b
    category_cooldowns: CategoryCooldowns = Field(
        default_factory=CategoryCooldowns
    )

    # User-configurable pause trigger overrides (RTwP)
    pause_config: PauseConfig = Field(default_factory=PauseConfig)

    # Base filename (no path/ext) of the JSONL rich-log file; empty string = none assigned yet
    rich_log_name: str = ""

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

    # One pending slot per ActionCategory.
    # repeating=False: fire once, then clear. repeating=True: keep after firing.
    # Keyed by ActionCategory.value.
    pending_actions: dict[str, OngoingAction] = Field(default_factory=dict)

    # When a one-shot override is queued over a repeating action, the repeating
    # action is stored here. After the one-shot fires, it is restored.
    pending_resume: dict[str, OngoingAction] = Field(default_factory=dict)

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

    # Persistent snapshot of the most recent non-empty essence capture event.
    # Unlike last_tick_essence_by_domain (cleared each non-capture tick), these
    # fields survive save/load and are always available for display.
    last_essence_capture_by_domain: dict[str, float] = Field(default_factory=dict)
    last_essence_capture_tick: int = 0

    # Last successful Harvest Essence from Underreal result.
    # last_harvest_tick == 0 means never harvested.
    last_harvest_amount: float = 0.0
    last_harvest_tick: int = 0



def _assign_category_cooldown(state: SimulationState, category: "ActionCategory") -> None:
    state.category_cooldowns.counters[category] = compute_cooldown(
        category, state.demiurge.puissance
    )


from core.action_core import ActionCategory as _AC
_CATEGORY_PRIORITY: list = [
    _AC.DIRECT_CREATION,
    _AC.OVERT_MIRACLE,
    _AC.SUBTLE_INFLUENCE,
    _AC.PROXIUS_DIRECTION,
    _AC.OBSERVATION,
    _AC.HERALD_INTERACTION,
    _AC.LUMINARY_RELATIONS,
    _AC.UNDERREAL,
    _AC.SELF_REFINEMENT,
]


def _is_pending_target_valid(state: SimulationState, pending: "OngoingAction") -> bool:
    """Return False if the pending action's target no longer exists or is deceased."""
    if pending.target_id is None:
        return True
    tid = str(pending.target_id)
    tt = pending.target_type
    if tt == TargetType.MORTAL:
        m = state.mortals.get(tid)
        return m is not None and m.status != MortalStatus.DECEASED
    if tt in (TargetType.WORLD, TargetType.SYSTEM, TargetType.GALAXY):
        return tid in state.locations
    if tt == TargetType.CIVILIZATION:
        return tid in state.civilizations
    if tt == TargetType.LUMINARY:
        return tid in state.luminaries
    if tt == TargetType.SPECIES:
        return tid in state.species
    return True


# ─────────────────────────────────────────
# TICK LOOP
# ─────────────────────────────────────────

def _birthday_fires(old: EntityAge, new: EntityAge, month: int, day: int) -> bool:
    """True if (month, day) anniversary falls in the half-open interval (old, new]."""
    old_fy = old.full_year()
    new_fy = new.full_year()
    old_t  = (old_fy, old.month, old.day)
    new_t  = (new_fy, new.month, new.day)
    for y in range(old_fy, new_fy + 1):
        if old_t < (y, month, day) <= new_t:
            return True
    return False


def _status_recognition_from_pop(
    mortal: "NotableMortal",
    local_pop: "Pop",
    state: "SimulationState",
    *,
    strong: bool,
) -> tuple[float, int]:
    """
    Return (status_gain, satiation_hold) granted to a mortal by a pop noticing their contribution.
    strong=True for sell (commerce); strong=False for socialize (presence).
    Relationship tiers: own pop > linked pop (link-factor scaled) > stranger.
    """
    own_gain,    own_hold    = (0.60, 14) if strong else (0.10, 3)
    link_scale               = 0.50       if strong else 0.10
    link_hold                = 10         if strong else 2
    stranger_gain, str_hold  = (0.12, 6)  if strong else (0.02, 0)

    if str(mortal.pop_id) == str(local_pop.id):
        return own_gain, own_hold

    origin_pop = state.pops.get(str(mortal.pop_id)) if mortal.pop_id else None
    if origin_pop and str(origin_pop.id) in local_pop.linked_pop_ids:
        base = local_pop.linked_pop_ids[str(origin_pop.id)]
        lf = compute_link_factor(origin_pop, local_pop, base)
        return link_scale * lf, link_hold

    return stranger_gain, str_hold


_DIRECTIVE_ACTION_MAP: dict[str, str] = {
    "commerce": "sell",
}


def _sync_faction_directives(
    mortal: "NotableMortal",
    state: "SimulationState",
    tick: int,
) -> None:
    """Rebuild Faction-sourced DirectiveFacts in the mortal's KnowledgeBase each tick."""
    if not mortal.knowledge_base:
        return
    kb = mortal.knowledge_base
    kb.facts = [
        f for f in kb.facts
        if not (f.fact_type == "directive" and getattr(f, "source_faction_id", None))
    ]
    mortal_skills = getattr(mortal, "skill_tags", {}) or {}
    for faction in state.factions.values():
        if faction.id not in mortal.faction_ids:
            continue
        for directive in faction.active_directives:
            if directive.required_skill and directive.required_skill not in mortal_skills:
                continue
            satisfying_action = _DIRECTIVE_ACTION_MAP.get(directive.directive_type, directive.directive_type)
            target = str(directive.target_location_id) if directive.target_location_id else ""
            df = DirectiveFact(
                directive_id=str(directive.id),
                directive_type=directive.directive_type,
                satisfying_action=satisfying_action,
                target_pop_location_id=target,
                source_faction_id=str(faction.id),
                learned_at_tick=tick,
            )
            kb.facts.append(df)


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

        _days_this_tick = max(1, round(cfg.tick_duration * 360))
        _new_age = state.universe.age.advance_days(_days_this_tick)
        result = TickResult(
            tick_number=state.tick_number,
            universe_age_before=state.universe.age,
            universe_age_after=_new_age,
            passive_result=PassiveWorldResult(),
            action_result=ActionProcessingResult(),
            domain_profile=UniverseDomainProfile(
                timestamp=state.universe.age.to_float_years()
            ),
            seed=seed,
        )

        # ── Puissance recomputation ────────────────────
        state.demiurge.puissance = _compute_puissance(state)

        # ── Phase 1: Passive World ─────────────────────
        passive = self._run_passive_phase(
            state, cfg, phase_rng,
            result.universe_age_before, _new_age,
        )
        result.passive_result = passive

        # ── Active event continuation (Phase 1 extension) ─
        # Runs at offset ≥ 1; tick-0 effects are applied by the action handler directly.
        event_mutations = self._process_active_events(state)
        state = self._apply_mutations(state, event_mutations)

        state = self._apply_passive_mutations(state, passive)
        state = self._prune_weak_beliefs(state)

        # ── Essence generation (Phase 1 tail) — fires monthly (day 1 of each month) ─
        if _new_age.day == 1:
            essence_gen_mutations, essence_by_domain = process_essence_generation(state, cfg)
            state = self._apply_mutations(state, essence_gen_mutations)
        else:
            essence_by_domain = {}
        result.essence_claimed_by_domain = essence_by_domain
        state.last_tick_essence_by_domain = dict(essence_by_domain)
        if essence_by_domain:
            state.last_essence_capture_by_domain = dict(essence_by_domain)
            state.last_essence_capture_tick = state.tick_number

        # ── Phase 2: Pending action fire (priority order) ─────────────────
        # Validate pending targets; cancel stale slots before attempting to fire.
        stale_cats = [
            cat_val for cat_val, pa in state.pending_actions.items()
            if not _is_pending_target_valid(state, pa)
        ]
        for cat_val in stale_cats:
            pa = state.pending_actions.pop(cat_val)
            result.passive_result.narrative_events.append(NarrativeEvent(
                text=f"[Queue] Pending {pa.action_key.replace('_', ' ')} cancelled: target no longer valid.",
                in_window=True,
            ))

        # Build fire_queue from pending_actions in category priority order.
        # Cooldown and Essence checks happen here; only actions that can run
        # this tick are included.
        committed_essence = 0.0
        fire_queue: list[ActionInstance] = []
        fired_cat_vals: list[str] = []
        fired_repeating_ids: set[str] = set()   # instance IDs from repeating slots
        fired_oneshot_count: int = 0             # count of non-repeating slots that fired

        for category in _CATEGORY_PRIORITY:
            cat_val = category.value
            pending = state.pending_actions.get(cat_val)
            if pending is None:
                continue
            pending.ticks_active += 1

            defn = self._action_library.get(pending.action_key)
            if defn is None:
                continue

            if state.category_cooldowns.counters.get(category, 0) > 0:
                continue

            if defn.essence_cost > 0:
                available = state.essence.actual - committed_essence
                if defn.essence_cost > available:
                    continue
                committed_essence += defn.essence_cost

            instance = ActionInstance(
                action_definition_id=defn.id,
                target_type=pending.target_type,
                target_id=pending.target_id,
                timestamp=state.universe.age.to_float_years(),
                demiurge_id=state.demiurge.id,
                proxius_id=pending.proxius_id,
                intent=pending.intent,
            )
            fire_queue.append(instance)
            fired_cat_vals.append(cat_val)
            if pending.repeating:
                fired_repeating_ids.add(str(instance.id))
            else:
                fired_oneshot_count += 1

        _essence_before = state.essence.actual
        action_result = self._process_action_queue_list(state, cfg, phase_rng, fire_queue)
        result.action_result = action_result
        state = self._apply_action_mutations(state, action_result)
        state.action_queue = []

        # Credit stats, assign cooldowns, clear non-repeating slots.
        executed_ids = {str(e.action_instance_id) for e in action_result.entries}
        outcome_by_id = {str(e.action_instance_id): e.outcome for e in action_result.entries}
        for instance, cat_val in zip(fire_queue, fired_cat_vals):
            if str(instance.id) not in executed_ids:
                continue
            pending = state.pending_actions.get(cat_val)
            if pending is None:
                continue
            pending.executed_ticks += 1
            if outcome_by_id.get(str(instance.id)) != ActionOutcome.FAILURE:
                pending.successful_ticks += 1
            defn = self._action_library.get(pending.action_key)
            if defn:
                _assign_category_cooldown(state, defn.category)
            if not pending.repeating:
                if outcome_by_id.get(str(instance.id)) != ActionOutcome.FAILURE:
                    del state.pending_actions[cat_val]
                    resume = state.pending_resume.pop(cat_val, None)
                    if resume is not None:
                        state.pending_actions[cat_val] = resume

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
        # Fires after Phase 2 revelation gain. Cap check first; then per-tier
        # one/both checks if any tier stop flags are set on the intent.
        from core.action_core import ActionCategory as _AC
        _sr_key = _AC.SELF_REFINEMENT.value
        if _sr_key in state.pending_actions:
            _oa = state.pending_actions[_sr_key]
            if _oa.action_key == "explore_beliefs" and isinstance(_oa.intent, ExploreBeliefIntent):
                _tag   = _oa.intent.domain_tag
                _cap   = _compute_revelation_cap(state, _tag)
                _pool  = state.demiurge.revelation_pools.get(_tag, 0.0)
                _short = _tag.split(":", 1)[1].title() if ":" in _tag else _tag.title()
                _domain_link = f"§domain§{_tag}§{_short}§"

                if _cap == 0.0 or _pool >= _cap:
                    del state.pending_actions[_sr_key]
                    _assign_category_cooldown(state, _AC.SELF_REFINEMENT)
                    result.passive_result.narrative_events.append(NarrativeEvent(
                        text=(
                            f"[Revelation] Explore Beliefs on {_domain_link} stopped: pool full "
                            f"({_pool:.2f} / {_cap:.2f}). Use Reveal Imāgō to internalize Imāginēs."
                        )
                    ))
                    result.pause_events.append(PauseEvent(
                        event_type=PauseEventType.REVELATION_THRESHOLD,
                        description=f"Revelation pool full for {_short}",
                        is_hard_pause=False,
                        pauses_by_default=True,
                    ))
                else:
                    _intent = _oa.intent
                    _tier_flags = [
                        (1, _intent.stop_on_t1_one, _intent.stop_on_t1_both),
                        (2, _intent.stop_on_t2_one, _intent.stop_on_t2_both),
                        (3, _intent.stop_on_t3_one, _intent.stop_on_t3_both),
                    ]
                    if any(f for _, one, both in _tier_flags for f in (one, both)):
                        _revealed  = state.demiurge.revealed_imagines
                        for _tier, _flag_one, _flag_both in _tier_flags:
                            if not (_flag_one or _flag_both):
                                continue
                            _cost_one  = _revelation_adjusted_cost(_tier, _revealed)
                            _cost_both = _cost_one + _revelation_adjusted_cost(_tier, _revealed + 1)
                            _threshold = _cost_both if _flag_both else _cost_one
                            _label     = f"both Tier {_tier}s" if _flag_both else f"one Tier {_tier}"
                            if _pool >= _threshold:
                                del state.pending_actions[_sr_key]
                                _assign_category_cooldown(state, _AC.SELF_REFINEMENT)
                                result.passive_result.narrative_events.append(NarrativeEvent(
                                    text=(
                                        f"[Revelation] Explore Beliefs on {_domain_link} paused: "
                                        f"enough Revelation to reveal {_label} Imāgō "
                                        f"({_pool:.2f} ≥ {_threshold})."
                                    )
                                ))
                                result.pause_events.append(PauseEvent(
                                    event_type=PauseEventType.REVELATION_THRESHOLD,
                                    description=f"Revelation threshold met for {_short} ({_label})",
                                    is_hard_pause=False,
                                    pauses_by_default=True,
                                ))
                                break

        # ── Phase 2.5: Proxius Agent Actions ───────────
        agent_mutations, agent_narratives = resolve_proxius_agents(state, phase_rng, cfg)
        state = self._apply_mutations(state, agent_mutations)
        result.agent_narratives.extend(agent_narratives)

        # ── Phase 2.55: Civilian Agent Actions ─────────
        mortal_agent_narratives = self._tick_mortal_agents(state, state.tick_number)
        result.mortal_narratives.extend(mortal_agent_narratives)

        # ── Phase 2.57: Pop Agent Actions ───────────────
        pop_agent_narratives = self._tick_pop_agents(state, state.tick_number)
        result.mortal_narratives.extend(pop_agent_narratives)

        # ── Phase 2.6: Mortal Travel ────────────────────
        travel_decisions = self._resolve_mortal_travel_decisions(state)
        travel_arrivals  = self._process_mortal_travel(state)
        result.mortal_narratives.extend(travel_decisions + travel_arrivals)

        # ── Pop aggregate recomputation ────────────────
        # Recompute Civilization.dominant_beliefs and culture_tags as size-weighted
        # averages of constituent Pop beliefs/tags. Peripheral (non-core) Pops are
        # weighted down so colony Pops don't over-influence the civ aggregate.
        recompute_civ_dominant_beliefs(state, cfg)
        recompute_civ_culture_tags(state, cfg)

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

        # ── Pause event generation ─────────────────────
        # Hard-pause: any Luminary dialogue trigger (ultimatum gets its own type).
        for trigger in result.dialogue_triggers:
            if trigger.trigger_type in _ULTIMATUM_DIALOGUE_TYPES:
                result.pause_events.append(PauseEvent(
                    event_type=PauseEventType.LUMINARY_ULTIMATUM,
                    description=trigger.subject_ref or trigger.trigger_type.value,
                ))
            else:
                result.pause_events.append(PauseEvent(
                    event_type=PauseEventType.LUMINARY_CONTACT,
                    description=trigger.subject_ref or trigger.trigger_type.value,
                ))

        # Default-pause: evaluation completed.
        if result.evaluations:
            result.pause_events.append(PauseEvent(
                event_type=PauseEventType.EVALUATION_COMPLETE,
                description=f"{len(result.evaluations)} luminary evaluation(s)",
                is_hard_pause=False,
                pauses_by_default=True,
            ))

        # Default-pause: an Imago node was revealed this tick.
        for entry in result.action_result.entries:
            if any(m.mutation_type == MutationType.IMAGO_REVEALED for m in entry.mutations):
                result.pause_events.append(PauseEvent(
                    event_type=PauseEventType.REVELATION_THRESHOLD,
                    description="Imago revealed",
                    is_hard_pause=False,
                    pauses_by_default=True,
                ))
                break  # one event per tick is enough

        # Default-pause: a one-shot (non-repeating) pending action resolved this tick.
        if fired_oneshot_count > 0:
            non_repeating_entries = [
                e for e in result.action_result.entries
                if str(e.action_instance_id) not in fired_repeating_ids
            ]
            if non_repeating_entries:
                result.pause_events.append(PauseEvent(
                    event_type=PauseEventType.QUEUED_ACTION_COMPLETE,
                    description=f"{len(non_repeating_entries)} action(s) resolved",
                    is_hard_pause=False,
                    pauses_by_default=True,
                ))

        # Default-pause: a pinned mortal died this tick.
        for mut in passive.pending_death_mutations:
            mortal = state.mortals.get(str(mut.target_id))
            if mortal and mortal.pinned:
                result.pause_events.append(PauseEvent(
                    event_type=PauseEventType.PINNED_MORTAL_DIED,
                    description=mortal.name,
                    is_hard_pause=False,
                    pauses_by_default=True,
                ))

        # Default-silent: a Pop splinted this tick.
        for m in result.passive_result.civilization_mutations:
            if m.mutation_type == MutationType.POP_SPLINTER:
                result.pause_events.append(PauseEvent(
                    event_type=PauseEventType.POP_SPLINT,
                    description=m.note or "Pop splinted",
                    is_hard_pause=False,
                    pauses_by_default=False,
                ))
                break

        # Default-silent: a domain expression shifted significantly.
        for m in result.passive_result.entity_mutations:
            if m.mutation_type == MutationType.DOMAIN_EXPRESSION and abs(m.delta or 0.0) >= 0.05:
                result.pause_events.append(PauseEvent(
                    event_type=PauseEventType.DOMAIN_THRESHOLD,
                    description=m.field or "domain expression",
                    is_hard_pause=False,
                    pauses_by_default=False,
                ))
                break

        # Default-silent: a mortal arrived at their destination.
        for ev in result.passive_result.narrative_events:
            if "arrives at" in ev.text:
                result.pause_events.append(PauseEvent(
                    event_type=PauseEventType.TRAVEL_COMPLETE,
                    description=ev.text,
                    is_hard_pause=False,
                    pauses_by_default=False,
                ))
                break

        # Default-silent: a Proxius report surfaced this tick.
        if result.agent_narratives:
            result.pause_events.append(PauseEvent(
                event_type=PauseEventType.MINOR_AGENT_UPDATE,
                description=f"{len(result.agent_narratives)} agent update(s)",
                is_hard_pause=False,
                pauses_by_default=False,
            ))

        # ── Bookkeeping ────────────────────────────────
        state.universe.age = _new_age
        # Advance EntityAge for all locations and civilizations in lockstep
        for loc in state.locations.values():
            loc.age = loc.age.advance_days(_days_this_tick)
        for civ in state.civilizations.values():
            civ.age = civ.age.advance_days(_days_this_tick)
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
        old_age: EntityAge = None,
        new_age: EntityAge = None,
    ) -> PassiveWorldResult:

        result = PassiveWorldResult()

        _old_age = old_age or state.universe.age
        _new_age_obj = new_age or state.universe.age.advance_days(
            max(1, round(cfg.tick_duration * 360))
        )

        # ── Category cooldown decrement ────────────────
        counters = state.category_cooldowns.counters
        for cat in list(counters):
            counters[cat] -= 1
            if counters[cat] <= 0:
                del counters[cat]

        # ── Civilization momentum ──────────────────────
        for cid, civ in state.civilizations.items():
            momentum = state.civ_momentum.get(
                cid,
                CivilizationMomentum(civilization_id=UUID(cid))
            )

            stability_delta = 0.0
            # wealth, cohesion, and stability momentum fires monthly (day 1 of each month)
            if _new_age_obj.day == 1:
                for stat, delta in [
                    ("wealth",   momentum.wealth_delta),
                    ("cohesion", momentum.cohesion_delta),
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

                if civ.dominant_beliefs and civ.established_beliefs:
                    stability_target = cosine_similarity(
                        civ.dominant_beliefs, civ.established_beliefs
                    )
                else:
                    stability_target = civ.health.stability
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

            # Civilization founding anniversary — detected via elapsed_years crossing
            *_, fm, fd = civ.age.formation_date
            if _birthday_fires(_old_age, _new_age_obj, fm, fd):
                result.narrative_events.append(NarrativeEvent(
                    text=f"{civ.name} founding anniversary (year {civ.age.elapsed_years() + 1:,}).",
                    in_window=is_in_window(civ),
                ))

        # ── Civ → Pop conformity pressure ──────────────
        # Staggered per civ; stride gate is inside the function.
        for m in civ_conformity_pressure(state, cfg, tick_number=state.tick_number):
            result.civilization_mutations.append(m)
        for m in anchor_identity_pull(state, cfg, tick_number=state.tick_number):
            result.civilization_mutations.append(m)

        # ── Per-pop periodic cultural noise ────────────
        # Staggered per pop (POP_NOISE_STRIDE=89 ticks); gate inside the function.
        for m in process_pop_cultural_noise(state, cfg, self._rng, state.tick_number):
            result.civilization_mutations.append(m)

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

            *_, bm, bd = mortal.birthday
            on_birthday = _birthday_fires(_old_age, _new_age_obj, bm, bd)

            if on_birthday:
                result.mortal_mutations.append(StateMutation(
                    mutation_type=MutationType.MORTAL_AGE,
                    target_id=UUID(mid),
                    field="chrono_age",
                    delta=1.0,
                    note=f"{mortal.name} chrono_age +1 (birthday {bm}/{bd})",
                ))

            # bio_age frozen for active Proxii/Heralds; dormant Proxii age slowly (0.2/yr)
            if (mortal.status == MortalStatus.ACTIVE
                    and mortal.role in (MortalRole.PROXIUS, MortalRole.HERALD)):
                bio_delta = 0.0
            elif (mortal.status == MortalStatus.DORMANT
                    and mortal.role == MortalRole.PROXIUS):
                bio_delta = 0.2 if on_birthday else 0.0
            else:
                bio_delta = 1.0 if on_birthday else 0.0

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

        # ── Visibility decay, footprint decay, concealment, attention ──
        result.entity_mutations.extend(process_visibility_decay(state, cfg))

        # ── Cross-Pop contact (passive cross-civ belief drift) ─────
        # Co-located Pops of different civs slowly drift toward each other's beliefs.
        # Staggered per world; stride gate is inside the function.
        for m in process_pop_contact(state, cfg, tick_number=state.tick_number):
            result.civilization_mutations.append(m)

        # ── Ambient location belief influence ──────────────────────
        # Staggered per world; stride gate is inside the function.
        process_location_ambient_influence(state, cfg, tick_number=state.tick_number)

        # ── Pop splinter and reabsorption checks ────────
        # Both stride-gated on SPLINTER_CHECK_STRIDE; run after conformity pressure
        # so we react to this tick's final belief state.
        splinter_mutations, splinter_events = self._check_pop_splinters(state)
        result.entity_mutations.extend(splinter_mutations)
        result.narrative_events.extend(splinter_events)
        reabsorb_mutations, reabsorb_events = self._check_pop_reabsorption(state)
        result.entity_mutations.extend(reabsorb_mutations)
        result.narrative_events.extend(reabsorb_events)

        # ── Linked-pop base factor drift ────────────────
        # Staggered per pop; stride gate is inside _process_link_drift.
        link_events = self._process_link_drift(state)
        result.narrative_events.extend(link_events)

        return result

    def _check_pop_splinters(
        self,
        state: SimulationState,
    ) -> tuple[list[StateMutation], list[NarrativeEvent]]:
        """Check every eligible Pop for belief divergence and emit splinter mutations.
        Stride-gated (SPLINTER_CHECK_STRIDE); probabilistic gate per pop."""
        mutations: list[StateMutation] = []
        events: list[NarrativeEvent] = []
        if state.tick_number % SPLINTER_CHECK_STRIDE != 0:
            return mutations, events
        for pid, pop in list(state.pops.items()):
            if pop.asset_crew_for is not None:
                continue
            if pop.splinter_cooldown > 0:
                pop.splinter_cooldown -= 1
                if pop.splinter_cooldown == 0 and pop.identity_anchor is not None:
                    pop.identity_anchor = None
                continue
            if pop.size_fractional < SPLINTER_MIN_SIZE:
                continue
            if not pop.civilization_id:
                continue
            civ = state.civilizations.get(str(pop.civilization_id))
            if civ is None or not civ.established_beliefs:
                continue
            belief_div   = 1.0 - cosine_similarity(pop.dominant_beliefs, civ.established_beliefs)
            culture_div  = _culture_divergence(pop.culture_tags, civ.established_culture_tags)
            divergence   = 0.9 * belief_div + 0.1 * culture_div
            if divergence < SPLINTER_DIVERGENCE_THRESHOLD:
                continue

            scale_offset = _CIV_SCALE_SPLINTER_OFFSET.get(civ.scale.value, 0.0)
            effective_midpoint = SPLINTER_PROB_MIDPOINT + scale_offset
            if self._rng.random() >= _splinter_probability(divergence, effective_midpoint):
                continue

            top_div_tag = max(
                (t for t in pop.dominant_beliefs),
                key=lambda t: abs(
                    pop.dominant_beliefs.get(t, 0.0)
                    - civ.established_beliefs.get(t, 0.0)
                ),
                default=None,
            )
            short_label = top_div_tag.split(":", 1)[-1].title() if top_div_tag else "Unknown"
            domain_sentinel = f"§domain§{top_div_tag}§{short_label}§" if top_div_tag else short_label
            label = pop_label(pop)

            fraction = _splinter_fraction(divergence)
            original_size = pop.size_fractional

            # Capture deviant beliefs and culture before nudging parent
            original_beliefs = dict(pop.dominant_beliefs)
            original_culture = dict(pop.culture_tags)

            # Shrink parent and nudge beliefs toward civ
            pop.size_fractional = max(0.0, original_size + math.log10(1.0 - fraction))
            nudge = fraction * SPLINTER_BELIEF_NUDGE_FACTOR
            for tag, val in list(pop.dominant_beliefs.items()):
                civ_val = civ.established_beliefs.get(tag, 0.0)
                pop.dominant_beliefs[tag] = val + (civ_val - val) * nudge

            # Nudge parent culture (values:/religion: only) toward established_culture_tags
            for tag, val in list(pop.culture_tags.items()):
                prefix = tag.split(":", 1)[0]
                w = _CULTURE_DIVERGENCE_WEIGHTS.get(prefix)
                if w is None:
                    continue
                civ_val = civ.established_culture_tags.get(tag, 0.0)
                pop.culture_tags[tag] = val + (civ_val - val) * nudge * w

            anchor = {
                **original_beliefs,
                **{k: v for k, v in original_culture.items() if not k.startswith("practice:")},
            }
            splinter = Pop(
                id=uuid4(),
                name=f"{pop_label(pop)} Splinter",
                civilization_id=pop.civilization_id,
                species_id=pop.species_id,
                social_class=pop.social_class,
                wild_stratum=pop.wild_stratum,
                occupation=pop.occupation,
                current_location=pop.current_location,
                size_fractional=max(0.0, original_size + math.log10(fraction)),
                dominant_beliefs=original_beliefs,
                culture_tags=original_culture,
                rider_traits=dict(pop.rider_traits),
                parent_pop_id=pop.id,
                visibility=max(0.0, pop.visibility * 0.75),
                pinned=False,
                splinter_cooldown=SPLINTER_COOLDOWN_TICKS,
                identity_anchor=anchor if anchor else None,
            )

            # Redistribute mortals: those more similar to splinter beliefs move over
            moved_mortal_ids = _redistribute_mortals_on_splinter(
                pop, splinter, state.mortals
            )
            for mid in moved_mortal_ids:
                mortal = state.mortals.get(str(mid))
                if mortal and is_in_window(mortal) and is_in_window(pop):
                    _m_sentinel = f"§mortal§{mortal.id}§{mortal.name}§"
                    events.append(NarrativeEvent(
                        text=f"[Pop splinter] {_m_sentinel} sided with the splinter faction.",
                        in_window=True,
                    ))

            _parent_sentinel  = f"§pop§{pop.id}§{label}§"
            _splinter_sentinel = f"§pop§{splinter.id}§{label}§"
            note = (
                f"[Pop splinter] Part of {_parent_sentinel} ({civ.name}) "
                f"broke away as {_splinter_sentinel} over {domain_sentinel} "
                f"(divergence {divergence:.2f})."
            )
            pop.splinter_cooldown = SPLINTER_COOLDOWN_TICKS
            mutations.append(StateMutation(
                mutation_type=MutationType.POP_SPLINTER,
                target_id=pop.id,
                field="pops",
                new_value=splinter,
                note=note,
            ))
            events.append(NarrativeEvent(
                text=note,
                in_window=is_in_window(pop),
            ))
        return mutations, events

    def _check_pop_reabsorption(
        self,
        state: SimulationState,
    ) -> tuple[list[StateMutation], list[NarrativeEvent]]:
        """Gradually drain small converged splinter pops back into a larger compatible pop.
        Stride-gated to run on the same ticks as _check_pop_splinters."""
        mutations: list[StateMutation] = []
        events: list[NarrativeEvent] = []
        if state.tick_number % SPLINTER_CHECK_STRIDE != 0:
            return mutations, events

        for pid, pop in list(state.pops.items()):
            if pop.asset_crew_for is not None:
                continue
            if pop.preaching_imago_id is not None:
                continue
            if pop.splinter_cooldown > 0:
                continue
            # Only drain pops that are small (at or near minimum size)
            if pop.size_fractional >= SPLINTER_MIN_SIZE + 1.0:
                continue

            target = self._find_reabsorption_target(pop, state)
            if target is None:
                continue

            sim = cosine_similarity(pop.dominant_beliefs, target.dominant_beliefs)
            if sim < REABSORPTION_CONVERGENCE_THRESHOLD:
                continue

            # Drain fraction of source into target (log-space, population-conserving)
            transferred = (10 ** pop.size_fractional) * REABSORPTION_DRAIN_FRACTION
            new_target_size = math.log10(10 ** target.size_fractional + transferred)
            new_source_size = pop.size_fractional + math.log10(1.0 - REABSORPTION_DRAIN_FRACTION)

            delta_source = new_source_size - pop.size_fractional   # negative
            delta_target = new_target_size - target.size_fractional  # positive

            in_win = is_in_window(pop) or is_in_window(target)
            if new_source_size < SPLINTER_MIN_SIZE:
                # Final absorption: transfer ALL remaining population to target, then clean up
                full_transferred = 10 ** pop.size_fractional
                delta_target_final = math.log10(10 ** target.size_fractional + full_transferred) - target.size_fractional
                mutations.append(StateMutation(
                    mutation_type=MutationType.POP_SIZE_CHANGE,
                    target_id=target.id,
                    field="size_fractional",
                    delta=delta_target_final,
                ))
                mutations.append(StateMutation(
                    mutation_type=MutationType.POP_ABSORBED,
                    target_id=pop.id,
                    field="pops",
                    new_value=str(target.id),
                    note=f"[Pop reabsorption] {pop_label(pop)} fully reintegrated into {pop_label(target)}.",
                ))
                if in_win:
                    events.append(NarrativeEvent(
                        text=(
                            f"[Pop reabsorption] §pop§{pop.id}§{pop_label(pop)}§ "
                            f"fully reintegrated into §pop§{target.id}§{pop_label(target)}§."
                        ),
                        in_window=in_win,
                    ))
            else:
                # Partial drain: transfer only the drain fraction
                mutations.append(StateMutation(
                    mutation_type=MutationType.POP_SIZE_CHANGE,
                    target_id=pop.id,
                    field="size_fractional",
                    delta=delta_source,
                ))
                mutations.append(StateMutation(
                    mutation_type=MutationType.POP_SIZE_CHANGE,
                    target_id=target.id,
                    field="size_fractional",
                    delta=delta_target,
                ))
                if in_win:
                    events.append(NarrativeEvent(
                        text=(
                            f"[Pop reabsorption] §pop§{pop.id}§{pop_label(pop)}§ "
                            f"is drifting back into §pop§{target.id}§{pop_label(target)}§."
                        ),
                        in_window=in_win,
                    ))

        return mutations, events

    def _find_reabsorption_target(
        self,
        pop: "Pop",
        state: SimulationState,
    ) -> "Optional[Pop]":
        """Return the best reabsorption target: parent first, then best local match.

        Target must share stratum, occupation, and location; be larger than source;
        and not be a vessel crew or Preach Imago goal.
        """
        def _eligible(p: "Pop") -> bool:
            return (
                p.id != pop.id
                and p.asset_crew_for is None
                and p.preaching_imago_id is None
                and p.stratum == pop.stratum
                and p.occupation == pop.occupation
                and p.current_location == pop.current_location
                and p.size_fractional >= pop.size_fractional
            )

        if pop.parent_pop_id is not None:
            parent = state.pops.get(str(pop.parent_pop_id))
            if parent is not None and _eligible(parent):
                return parent

        best: "Optional[Pop]" = None
        best_sim: float = -1.0
        for other in state.pops.values():
            if not _eligible(other):
                continue
            sim = cosine_similarity(pop.dominant_beliefs, other.dominant_beliefs)
            if sim > best_sim:
                best_sim = sim
                best = other
        return best

    def _process_link_drift(self, state: SimulationState) -> list[NarrativeEvent]:
        """Drift each Pop's base link factors toward cosine similarity and break dissolved links.
        Staggered per pop: each pop's links drift on their own offset within LINK_DRIFT_STRIDE."""
        events: list[NarrativeEvent] = []
        for pop in state.pops.values():
            if not pop.linked_pop_ids:
                continue
            pop_offset = int(pop.id.int) % LINK_DRIFT_STRIDE
            if (state.tick_number - pop_offset) % LINK_DRIFT_STRIDE != 0:
                continue
            to_remove: list[str] = []
            for other_id_str, base_factor in list(pop.linked_pop_ids.items()):
                other_pop = state.pops.get(other_id_str)
                if other_pop is None:
                    to_remove.append(other_id_str)
                    continue
                a_vec = {**pop.dominant_beliefs, **pop.culture_tags}
                b_vec = {**other_pop.dominant_beliefs, **other_pop.culture_tags}
                cosine = cosine_similarity(a_vec, b_vec)
                new_base = base_factor + (cosine - base_factor) * LINK_DRIFT_RATE
                computed = compute_link_factor(pop, other_pop, new_base)
                if computed < LINK_BREAK_THRESHOLD:
                    to_remove.append(other_id_str)
                    if pop.pinned or other_pop.pinned:
                        events.append(NarrativeEvent(
                            text=(
                                f"[Link dissolved] {pop.name or pop.stratum} and "
                                f"{other_pop.name or other_pop.stratum} no longer identify with each other "
                                f"(link factor {computed:.2f})."
                            ),
                            in_window=pop.pinned or other_pop.pinned,
                        ))
                else:
                    pop.linked_pop_ids[other_id_str] = new_base
            for k in to_remove:
                del pop.linked_pop_ids[k]
        return events

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
        cooldowns: "CategoryCooldowns",
    ) -> tuple[list["ActionInstance"], list[str]]:
        """
        Enforce per-tick uniqueness: at most one action per ActionCategory.
        Cooldown gating is handled upstream (Phase 2 fire loop).
        Returns (accepted, rejection_messages).
        """
        accepted: list[ActionInstance] = []
        rejected: list[str] = []
        seen_categories: dict[str, str] = {}

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

    def _process_action_queue_list(
        self,
        state: SimulationState,
        cfg: TickConfig,
        rng: random.Random,
        queue: list["ActionInstance"],
    ) -> ActionProcessingResult:

        result = ActionProcessingResult()

        validated_queue, rejections = self._validate_and_filter_queue(
            queue, state.category_cooldowns
        )
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
            narrative = "" if isinstance(instance.intent, ScryIntent) else f"{defn.name} failed to produce any effect."
            return outcome, [], narrative

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
                    field="suspicious",
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

        # ── Visibility refresh for mortal- and world-targeted actions ─
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
        elif instance.target_type == TargetType.WORLD and instance.target_id:
            loc = state.locations.get(str(instance.target_id))
            if loc and not getattr(loc, "pinned", False):
                mutations.append(StateMutation(
                    mutation_type=MutationType.ENTITY_VISIBILITY,
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
                    if g.imago_node_id:
                        _a_node = get_imago_registry().get_node(g.imago_node_id)
                        _a_name = _a_node.name if _a_node else g.imago_node_id
                        directive_desc = g.label if g.label else f"§imago§{g.imago_node_id}§{_a_name}§"
                    else:
                        directive_desc = g.label if g.label else "directive"
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
                surplus_ratio = (domain_production - threshold_so_far) / max(threshold_so_far, 0.001)

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
                    f"(surplus ratio: {surplus_ratio:+.0%})"
                )

                # Previous period trend
                if len(luminary.essence_received_log) >= 2:
                    slope = (luminary.essence_received_log[-1] - luminary.essence_received_log[0]) / len(luminary.essence_received_log)
                    normalized_slope = slope / max(threshold_so_far, 0.001)
                    traj = max(-0.02, min(0.02, normalized_slope * 0.5))
                    report.append(
                        f"  Trajectory: {slope:+.3f} / period  (modifier: {traj:+.3f})"
                    )
                elif luminary.essence_received_log:
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

        # ── Scry ─────────────────────────────────────────────────────────
        if isinstance(intent, ScryIntent):
            scope = intent.scope
            target_id_str = str(instance.target_id) if instance.target_id else None

            # Momentum: read and update directly on the OngoingAction instance.
            _own_oa: Optional[OngoingAction] = next(
                (oa for oa in state.pending_actions.values()
                 if isinstance(oa.intent, ScryIntent)
                 and oa.intent.scope == scope
                 and oa.target_id == instance.target_id),
                None,
            )
            _old_momentum = _own_oa.momentum if _own_oa is not None else 0.0
            _new_momentum = _old_momentum + (1.0 - _old_momentum) * 0.15
            if _own_oa is not None:
                _own_oa.momentum = _new_momentum

            # Footprint cost
            _fp = SCRY_FP_BASE[scope] + (_new_momentum * SCRY_FP_WORLD_MOM if scope == ScryScope.WORLD else 0.0)
            mutations.append(StateMutation(
                mutation_type=MutationType.FOOTPRINT_CHANGE,
                target_id=state.demiurge.id,
                field="subtle_influence",
                delta=_fp,
                note=f"Scry ({scope.value}) footprint",
            ))

            # Essence cost (galaxy/universe only)
            scope_essence = SCRY_ESSENCE
            if scope_essence[scope] > 0.0:
                mutations.append(StateMutation(
                    mutation_type=MutationType.ESSENCE_CHANGE,
                    target_id=state.demiurge.id,
                    field="actual",
                    delta=-scope_essence[scope],
                    note=f"Scry ({scope.value}) essence cost",
                ))

            # Spatial infrastructure (for incidental pass in Task 7)
            _GALAXY_SCALE = 1000.0
            _SPATIAL_SCALE = 8.0

            def _effective_pos(loc_id: str) -> tuple[float, float, float]:
                loc = state.locations.get(loc_id)
                if loc is None:
                    return (0.0, 0.0, 0.0)
                cx, cy, cz = loc.coordinates.x, loc.coordinates.y, loc.coordinates.z
                if loc.parent_id is not None:
                    px, py, pz = _effective_pos(str(loc.parent_id))
                    return (px * _GALAXY_SCALE + cx, py * _GALAXY_SCALE + cy, pz * _GALAXY_SCALE + cz)
                return (cx, cy, cz)

            _focus_pos: Optional[tuple[float, float, float]] = None
            if scope in (ScryScope.WORLD, ScryScope.SYSTEM, ScryScope.GALAXY) and instance.target_id:
                target_loc = state.locations.get(str(instance.target_id))
                if target_loc is not None:
                    if scope == ScryScope.WORLD and target_loc.parent_id is not None:
                        _focus_pos = _effective_pos(str(target_loc.parent_id))
                    else:
                        _focus_pos = _effective_pos(str(instance.target_id))

            def _spatial_factor(candidate_loc_id: str) -> float:
                if _focus_pos is None:
                    return 1.0
                loc = state.locations.get(candidate_loc_id)
                if loc is None:
                    return 1.0
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

            # Primary sweep helpers
            _BASE = 0.45
            _MOM  = 0.35

            def _scry_p(tags: list[str]) -> float:
                return min(0.95, _BASE + _new_momentum * _MOM + _domain_bonus(tags, _BASE))

            def _scry_new_vis(cur_vis: float) -> float:
                return max(cur_vis, _BASE + _new_momentum * _MOM)

            # Narrative accumulators
            discovered_locs: list[str] = []
            discovered_civs: list[str] = []
            discovered_sp:   list[str] = []
            discovered_mort: list[str] = []
            discovered_pops: list[tuple] = []
            parts: list[str] = []

            # ── Build primary location set ────────────────────────────────
            if scope == ScryScope.UNIVERSE:
                primary_locs = [
                    (lid, loc) for lid, loc in state.locations.items()
                    if loc.location_type == "galaxy" and not getattr(loc, "pinned", False)
                ]
            elif scope == ScryScope.GALAXY and target_id_str:
                primary_locs = [
                    (lid, loc) for lid, loc in state.locations.items()
                    if loc.location_type == "system"
                    and str(loc.parent_id) == target_id_str
                    and not getattr(loc, "pinned", False)
                ]
            elif scope == ScryScope.SYSTEM and target_id_str:
                primary_locs = [
                    (lid, loc) for lid, loc in state.locations.items()
                    if loc.location_type not in ("galaxy", "system")
                    and str(loc.parent_id) == target_id_str
                    and not getattr(loc, "pinned", False)
                ]
            else:
                primary_locs = []

            _primary_loc_ids: set[str] = {lid for lid, _ in primary_locs}

            # ── Primary location sweep (UNIVERSE / GALAXY / SYSTEM) ───────
            for lid, loc in primary_locs:
                tags = (
                    list(getattr(loc, "domain_expression", {}).keys())
                    + list(getattr(loc, "traits", []))
                )
                p = _scry_p(tags)
                if is_in_window(loc):
                    mutations.append(StateMutation(
                        mutation_type=MutationType.ENTITY_VISIBILITY,
                        target_id=UUID(lid), field="visibility",
                        new_value=min(1.0, loc.visibility + p * 0.3),
                        note=f"Scry ({scope.value}): {loc.name} refreshed",
                    ))
                elif rng.random() < p:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.ENTITY_VISIBILITY,
                        target_id=UUID(lid), field="visibility",
                        new_value=_scry_new_vis(loc.visibility),
                        note=f"Scry ({scope.value}): {loc.name} sighted",
                    ))
                    discovered_locs.append(loc.name)

            # ── WORLD scope: sweep pops, mortals, civs, species ───────────
            _world_pop_loc_ids: set[str] = set()
            _civs_at_world: set[str] = set()
            if scope == ScryScope.WORLD and target_id_str:
                _world_pop_loc_ids = {
                    lid for lid, loc in state.locations.items()
                    if isinstance(loc, PopLocation)
                    and str(loc.parent_id) == target_id_str
                    and not getattr(loc, "pinned", False)
                }
                _primary_loc_ids |= _world_pop_loc_ids

                # PopLocations
                for lid in _world_pop_loc_ids:
                    loc = state.locations[lid]
                    p = _scry_p([])
                    if is_in_window(loc):
                        mutations.append(StateMutation(
                            mutation_type=MutationType.ENTITY_VISIBILITY,
                            target_id=UUID(lid), field="visibility",
                            new_value=min(1.0, loc.visibility + p * 0.3),
                            note="Scry (world): PopLocation refreshed",
                        ))
                    elif rng.random() < p:
                        mutations.append(StateMutation(
                            mutation_type=MutationType.ENTITY_VISIBILITY,
                            target_id=UUID(lid), field="visibility",
                            new_value=_scry_new_vis(loc.visibility),
                            note="Scry (world): PopLocation sighted",
                        ))

                # Pops
                _PROMINENT = {"elite", "scholar", "warrior"}
                for pid, pop in state.pops.items():
                    if pop.pinned or str(pop.current_location) not in _world_pop_loc_ids:
                        continue
                    tags = list(pop.dominant_beliefs.keys()) if hasattr(pop, "dominant_beliefs") else []
                    p = _scry_p(tags)
                    if pop.social_class and pop.social_class.value in _PROMINENT:
                        p = min(0.95, p * 1.3)
                    if is_in_window(pop):
                        mutations.append(StateMutation(
                            mutation_type=MutationType.POP_VISIBILITY,
                            target_id=UUID(pid), field="visibility",
                            new_value=min(1.0, pop.visibility + p * 0.3),
                            note="Scry (world): Pop refreshed",
                        ))
                    elif rng.random() < p:
                        mutations.append(StateMutation(
                            mutation_type=MutationType.POP_VISIBILITY,
                            target_id=UUID(pid), field="visibility",
                            new_value=_scry_new_vis(pop.visibility),
                            note="Scry (world): Pop sighted",
                        ))
                        civ = state.civilizations.get(str(pop.civilization_id)) if pop.civilization_id else None
                        discovered_pops.append((pid, pop, civ))

                # Mortals
                for mid, mortal in state.mortals.items():
                    if mortal.status == MortalStatus.DECEASED or mortal.pinned:
                        continue
                    if str(mortal.current_location) not in _world_pop_loc_ids:
                        continue
                    tags = list(mortal.belief_tags.keys()) + mortal.personal_tags
                    p = _scry_p(tags)
                    if is_in_window(mortal):
                        mutations.append(StateMutation(
                            mutation_type=MutationType.MORTAL_VISIBILITY,
                            target_id=UUID(mid), field="visibility",
                            new_value=min(1.0, mortal.visibility + p * 0.3),
                            note=f"Scry (world): {mortal.name} refreshed",
                        ))
                    elif rng.random() < p:
                        mutations.append(StateMutation(
                            mutation_type=MutationType.MORTAL_VISIBILITY,
                            target_id=UUID(mid), field="visibility",
                            new_value=_scry_new_vis(mortal.visibility),
                            note=f"Scry (world): {mortal.name} sighted",
                        ))
                        discovered_mort.append(mortal.name)

                # Civs with pops at this world
                _civs_at_world = {
                    str(pop.civilization_id) for pop in state.pops.values()
                    if pop.civilization_id
                    and str(pop.current_location) in _world_pop_loc_ids
                }
                for cid in _civs_at_world:
                    civ = state.civilizations.get(cid)
                    if civ is None or civ.pinned:
                        continue
                    if is_wild_civ(civ):
                        continue
                    tags = list(civ.dominant_beliefs.keys()) if hasattr(civ, "dominant_beliefs") else []
                    p = _scry_p(tags)
                    if is_in_window(civ):
                        mutations.append(StateMutation(
                            mutation_type=MutationType.ENTITY_VISIBILITY,
                            target_id=UUID(cid), field="visibility",
                            new_value=min(1.0, civ.visibility + p * 0.3),
                            note=f"Scry (world): {civ.name} refreshed",
                        ))
                    elif rng.random() < p:
                        mutations.append(StateMutation(
                            mutation_type=MutationType.ENTITY_VISIBILITY,
                            target_id=UUID(cid), field="visibility",
                            new_value=_scry_new_vis(civ.visibility),
                            note=f"Scry (world): {civ.name} sighted",
                        ))
                        discovered_civs.append(civ.name)

                # Species originating at this world
                for sid, sp in state.species.items():
                    if sp.pinned or str(getattr(sp, "origin_world_id", None)) != target_id_str:
                        continue
                    tags = list(getattr(sp, "domain_tags", []))
                    p = _scry_p(tags)
                    if is_in_window(sp):
                        mutations.append(StateMutation(
                            mutation_type=MutationType.ENTITY_VISIBILITY,
                            target_id=UUID(sid), field="visibility",
                            new_value=min(1.0, sp.visibility + p * 0.3),
                            note=f"Scry (world): {sp.name} refreshed",
                        ))
                    elif rng.random() < p:
                        mutations.append(StateMutation(
                            mutation_type=MutationType.ENTITY_VISIBILITY,
                            target_id=UUID(sid), field="visibility",
                            new_value=_scry_new_vis(sp.visibility),
                            note=f"Scry (world): {sp.name} sighted",
                        ))
                        discovered_sp.append(sp.name)

            # ── Termination check ─────────────────────────────────────────
            _vis_muts: dict[str, float] = {
                str(m.target_id): float(m.new_value)
                for m in mutations
                if m.mutation_type in (
                    MutationType.ENTITY_VISIBILITY,
                    MutationType.POP_VISIBILITY,
                    MutationType.MORTAL_VISIBILITY,
                )
                and m.new_value is not None
            }

            _stop_full = getattr(intent, "stop_when", "visible") == "full"

            def _will_be_visible(eid: str, cur_vis: float) -> bool:
                if _stop_full:
                    return cur_vis >= 1.0
                return (
                    cur_vis > ENTITY_VISIBILITY_FLOOR
                    or _vis_muts.get(eid, 0.0) > ENTITY_VISIBILITY_FLOOR
                )

            _has_primary = bool(primary_locs) or bool(_world_pop_loc_ids)
            _all_visible = _has_primary and all(
                _will_be_visible(lid, loc.visibility) for lid, loc in primary_locs
            )

            if _all_visible and scope == ScryScope.WORLD and target_id_str:
                _all_visible = (
                    all(
                        _will_be_visible(lid, state.locations[lid].visibility)
                        for lid in _world_pop_loc_ids
                    )
                    and all(
                        _will_be_visible(pid, pop.visibility)
                        for pid, pop in state.pops.items()
                        if not pop.pinned
                        and str(pop.current_location) in _world_pop_loc_ids
                    )
                    and all(
                        _will_be_visible(mid, mortal.visibility)
                        for mid, mortal in state.mortals.items()
                        if mortal.status != MortalStatus.DECEASED
                        and not mortal.pinned
                        and str(mortal.current_location) in _world_pop_loc_ids
                    )
                    and all(
                        _will_be_visible(cid, state.civilizations[cid].visibility)
                        for cid in _civs_at_world
                        if cid in state.civilizations
                        and not state.civilizations[cid].pinned
                        and not is_wild_civ(state.civilizations[cid])
                    )
                    and all(
                        _will_be_visible(sid, sp.visibility)
                        for sid, sp in state.species.items()
                        if not sp.pinned
                        and str(getattr(sp, "origin_world_id", None)) == target_id_str
                    )
                )

            if _all_visible and _own_oa is not None:
                _own_cat = next(
                    (k for k, oa in state.pending_actions.items() if oa is _own_oa),
                    None,
                )
                if _own_cat is not None:
                    _tgt_loc = state.locations.get(target_id_str or "")
                    tgt_name = _tgt_loc.name if _tgt_loc is not None else scope.value
                    mutations.append(StateMutation(
                        mutation_type=MutationType.CLEAR_PENDING_SLOT,
                        target_id=state.demiurge.id,
                        field=_own_cat,
                        note=f"Scry of {tgt_name} complete",
                    ))
                    parts.append(
                        f"Scry of {tgt_name} complete — all entities within scope have been revealed."
                    )

            # ── Incidental discovery pass ─────────────────────────────────
            _eligible_locs: set[str] = {
                lid for lid, loc in state.locations.items() if is_in_window(loc)
            }
            for _m in mutations:
                if (
                    _m.mutation_type == MutationType.ENTITY_VISIBILITY
                    and _m.new_value is not None
                    and float(_m.new_value) > ENTITY_VISIBILITY_FLOOR
                ):
                    _eligible_locs.add(str(_m.target_id))

            scope_anchor: dict[ScryScope, int] = {
                ScryScope.WORLD: 3, ScryScope.SYSTEM: 2,
                ScryScope.GALAXY: 1, ScryScope.UNIVERSE: 0,
            }
            _anchor = scope_anchor[scope]

            def _depth_chance(delta: int) -> float:
                if delta == 0: return 0.85
                if delta == 1: return 0.55
                if delta == 2: return 0.30
                if delta == 3: return 0.06
                if delta == 4: return 0.02
                return 0.005

            for lid, loc in state.locations.items():
                if lid in _primary_loc_ids or getattr(loc, "pinned", False) or is_in_window(loc):
                    continue
                depth = (
                    1 if loc.location_type == "galaxy"
                    else 2 if loc.location_type == "system"
                    else 3
                )
                if depth > 1 and (loc.parent_id is None or str(loc.parent_id) not in _eligible_locs):
                    continue
                delta = abs(depth - _anchor)
                base = _depth_chance(delta)
                sf = _spatial_factor(lid)
                expr_tags = (
                    list(getattr(loc, "domain_expression", {}).keys())
                    + list(getattr(loc, "traits", []))
                )
                p = max(0.0, min(1.0, (base + _domain_bonus(expr_tags, base)) * sf))
                if rng.random() < p:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.ENTITY_VISIBILITY,
                        target_id=UUID(lid), field="visibility",
                        new_value=max(loc.visibility, base),
                        note=f"Scry ({scope.value}) incidental: {loc.name} sighted",
                    ))
                    discovered_locs.append(f"{loc.name} [incidental]")

            for mid, mortal in state.mortals.items():
                if mortal.status == MortalStatus.DECEASED or mortal.pinned:
                    continue
                if str(mortal.current_location) in _world_pop_loc_ids:
                    continue
                if is_in_window(mortal):
                    continue
                _milieu_pop = (
                    state.pops.get(str(mortal.pop_milieu)) if mortal.pop_milieu else None
                )
                if _milieu_pop is None or not is_in_window(_milieu_pop):
                    continue
                if _milieu_pop.visibility > 0.5:
                    _m_delta = 1
                else:
                    _m_loc = state.locations.get(str(mortal.current_location))
                    _m_dist = _m_loc.distance_from_core if isinstance(_m_loc, PopLocation) else 0
                    _m_delta = abs(5 - _anchor) + min(_m_dist, 2)
                base = _depth_chance(_m_delta)
                tags = list(mortal.belief_tags.keys()) + mortal.personal_tags
                p = max(0.0, min(1.0, base + _domain_bonus(tags, base)))
                if rng.random() < p:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.MORTAL_VISIBILITY,
                        target_id=UUID(mid), field="visibility",
                        new_value=max(mortal.visibility, base),
                        note=f"Scry ({scope.value}) incidental: {mortal.name} sighted via milieu",
                    ))
                    discovered_mort.append(f"{mortal.name} [incidental]")

            # ── Narrative ─────────────────────────────────────────────────
            if discovered_locs:
                parts.append(f"Locations sighted: {', '.join(discovered_locs)}.")
            if discovered_civs:
                parts.append(f"Civilizations sighted: {', '.join(discovered_civs)}.")
            if discovered_sp:
                parts.append(f"Species sighted: {', '.join(discovered_sp)}.")
            if discovered_mort:
                parts.append(f"Mortals sighted: {', '.join(discovered_mort)}.")
            if discovered_pops:
                formatted = self._format_pop_entries_with_links(discovered_pops, state)
                parts.append(f"Pops sighted: {', '.join(formatted)}.")

            if not (discovered_locs or discovered_civs or discovered_sp or discovered_mort or discovered_pops):
                _tgt_loc2 = state.locations.get(target_id_str or "")
                _tgt_name2 = _tgt_loc2.name if _tgt_loc2 is not None else scope.value
                parts.append(f"Scry of {_tgt_name2} refreshed visibility but revealed nothing new.")

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
            old_short = old_tag.split(":", 1)[1].title() if ":" in old_tag else old_tag.title()
            new_short = new_tag.split(":", 1)[1].title() if ":" in new_tag else new_tag.title()
            old_link = f"§domain§{old_tag}§{old_short}§"
            new_link = f"§domain§{new_tag}§{new_short}§"
            return mutations, (
                f"You release your conceptual hold on {old_link} and turn your focus "
                f"toward {new_link}. The reorientation settles into your nature."
            )

        # ── Explore Beliefs ───────────────────────────
        if isinstance(intent, ExploreBeliefIntent):
            tag = intent.domain_tag
            short = tag.split(":", 1)[1].title() if ":" in tag else tag.title()
            domain_link = f"§domain§{tag}§{short}§"
            cap = _compute_revelation_cap(state, tag)
            if cap == 0.0:
                return mutations, f"All Imāginēs in {short} are already revealed — there is nothing left to research here."
            pool = state.demiurge.revelation_pools.get(tag, 0.0)
            if pool >= cap:
                return mutations, (
                    f"You have accumulated maximum Revelation for {domain_link} ({pool:.2f} / {cap:.2f}). "
                    f"Use Reveal Imāgō to unlock Imāginēs before continuing."
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
            newly_affordable_links: list[str] = []
            for node in ireg.nodes_for_tree(tree):
                if node.node_id in unlocked_set:
                    continue
                if not ireg.is_unlockable(node.node_id, unlocked_set):
                    continue
                cost = _revelation_adjusted_cost(node.tier, state.demiurge.revealed_imagines)
                if pool < cost <= new_pool:
                    newly_affordable_links.append(f"§imago§{node.node_id}§{node.name}§")
            narrative = f"+{actual_gain} Revelation for {domain_link} ({new_pool:.2f} / {cap:.2f})."
            if newly_affordable_links:
                narrative += f" You have enough Revelation in {domain_link} to reveal: {', '.join(newly_affordable_links)}."
            return mutations, narrative

        # ── Reveal Imago ──────────────────────────────
        if isinstance(intent, RevealImagoIntent):
            tag = intent.domain_tag
            node_id = intent.node_id
            short = tag.split(":", 1)[1].title() if ":" in tag else tag.title()
            domain_link = f"§domain§{tag}§{short}§"
            ireg = get_imago_registry()
            node = ireg.get_node(node_id)
            if node is None or node.tree != (tag.split(":", 1)[1] if ":" in tag else tag):
                return mutations, f"Invalid Imāgō node '{node_id}' for domain {tag}."
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
            imago_link = f"§imago§{node_id}§{node.name}§"
            return mutations, (
                f"You have internalized {imago_link}, a {tier_names.get(node.tier, 'Tier')} Imāgō "
                f"of {domain_link}. {cost} Revelation spent."
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
                return mutations, f"All Imāginēs in {short} are already revealed — no research needed."
            pool = state.demiurge.revelation_pools.get(tag, 0.0)
            if pool >= cap:
                return mutations, f"Revelation for {short} is already at its cap. Reveal Imāginēs before commissioning further research."
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

            _w_ireg  = get_imago_registry()
            _w_node  = _w_ireg.get_node(intent.imago_node_id) if intent.imago_node_id else None
            _w_name  = _w_node.name if _w_node else (intent.imago_node_id or "")
            _w_label = (
                f"§imago§{intent.imago_node_id}§{_w_name}§"
                if intent.imago_node_id else f"'{_w_name}'"
            )

            for dv in intent.domain_vectors:
                mutations.append(StateMutation(
                    mutation_type=MutationType.MORTAL_BELIEF_SHIFT,
                    target_id=mortal.id,
                    field=dv.domain_tag,
                    delta=dv.direction * effectiveness * 0.1,
                    new_value=dv.domain_tag,
                    note=f"Whisper to {mortal.name}: {_w_name}",
                ))
            for cv in intent.culture_vectors:
                mutations.append(StateMutation(
                    mutation_type=MutationType.MORTAL_CULTURE_SHIFT,
                    target_id=mortal.id,
                    field=cv.culture_tag,
                    delta=cv.direction * effectiveness * 0.1,
                    new_value=cv.culture_tag,
                    note=f"Whisper culture rider to {mortal.name}: {_w_name}",
                ))

            narrative = (
                f"You whispered to {mortal.name}, implying the concept of {_w_label}, "
                f"with {effectiveness:.0%} effectiveness."
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
                    imago_node_id=intent.imago_node_id,
                    concept=_w_name,
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
            _, _, discovered_pop_ids, _vis_boosts = emit_influence_visibility_splash(mutations, state, mortal)
            for _bpid, _boost in _vis_boosts.items():
                _bp = state.pops.get(_bpid)
                if _bp is None or not _bp.linked_pop_ids:
                    continue
                for _lid, _lbase in _bp.linked_pop_ids.items():
                    _lp = state.pops.get(_lid)
                    if _lp is None or _lp.id == _bp.id:
                        continue
                    _lf = compute_link_factor(_bp, _lp, _lbase)
                    _vis_delta = _boost * _lf * LINK_VISIBILITY_CASCADE_SCALE
                    if _vis_delta > 1e-5:
                        mutations.append(StateMutation(
                            mutation_type=MutationType.POP_VISIBILITY,
                            target_id=_lp.id,
                            field="visibility",
                            new_value=min(1.0, _lp.visibility + _vis_delta),
                            note="Linked pop visibility cascade",
                        ))
            narrative += self._format_pop_discovery_line(mortal.name, discovered_pop_ids, state)

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
                    concept="",
                ),
            ))

            self._emit_whisper_splash(
                mutations, state, mortal,
                domain_vectors=combined_dvs,
                culture_vectors=combined_cvs,
                per_unit_delta=effectiveness * 0.1,
                note_prefix="Shape Dream",
            )
            _, _, discovered_pop_ids, _vis_boosts = emit_influence_visibility_splash(mutations, state, mortal)
            for _bpid, _boost in _vis_boosts.items():
                _bp = state.pops.get(_bpid)
                if _bp is None or not _bp.linked_pop_ids:
                    continue
                for _lid, _lbase in _bp.linked_pop_ids.items():
                    _lp = state.pops.get(_lid)
                    if _lp is None or _lp.id == _bp.id:
                        continue
                    _lf = compute_link_factor(_bp, _lp, _lbase)
                    _vis_delta = _boost * _lf * LINK_VISIBILITY_CASCADE_SCALE
                    if _vis_delta > 1e-5:
                        mutations.append(StateMutation(
                            mutation_type=MutationType.POP_VISIBILITY,
                            target_id=_lp.id,
                            field="visibility",
                            new_value=min(1.0, _lp.visibility + _vis_delta),
                            note="Linked pop visibility cascade",
                        ))

            ireg = get_imago_registry()
            dom_node = ireg.get_node(dominant_id)
            sup_node = ireg.get_node(suppressed_id)
            dom_name = dom_node.name if dom_node else dominant_id
            sup_name = sup_node.name if sup_node else suppressed_id
            dom_sent = f"§imago§{dominant_id}§{dom_name}§"
            sup_sent = f"§imago§{suppressed_id}§{sup_name}§"
            narrative = (
                f"You shaped {mortal.name}'s dreams around {dom_sent} and {sup_sent}. "
                f"In sleep, {dom_sent} took stronger root than {sup_sent}. "
                f"Overall, this was {effectiveness:.0%} effective."
            )
            narrative += self._format_pop_discovery_line(mortal.name, discovered_pop_ids, state)

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
                    node_label = node.name if node else intent.imago_node_id
                    imago_label = f" to preach §imago§{intent.imago_node_id}§{node_label}§"
                else:
                    imago_label = ""
                narrative = (
                    f"Proxius {proxius.name} has been sent{imago_label}. "
                    f"They will pursue it {dedication_note}."
                )

        # ── Essence Harvest ───────────────────────────
        elif isinstance(intent, EssenceHarvestIntent):
            # ── Auto-stop checks ──────────────────────────────────────────
            stop_reason = None
            if (intent.stop_at_suspicious is not None
                    and state.essence.suspicious >= intent.stop_at_suspicious):
                stop_reason = f"suspicious Essence reached {state.essence.suspicious:.2f}"
            elif (intent.stop_at_integrity_below is not None
                    and state.essence.concealment_integrity < intent.stop_at_integrity_below):
                stop_reason = (
                    f"concealment integrity at "
                    f"{state.essence.concealment_integrity:.0%}"
                )
            elif (intent.stop_at_stockpile is not None
                    and state.essence.actual >= intent.stop_at_stockpile):
                stop_reason = f"Essence stockpile reached {state.essence.actual:.2f}"

            if stop_reason:
                cat_key = defn.category.value
                pending = state.pending_actions.get(cat_key)
                if pending:
                    pending.repeating = False
                return [], f"Harvest paused: {stop_reason}."

            if outcome == ActionOutcome.FAILURE:
                return mutations, "The Underreal offered nothing this time."

            # Yield modulated by concealment priority
            # High concealment = slower, but less apparent leak
            base_yield = 3.0
            if outcome == ActionOutcome.PARTIAL:
                base_yield *= 0.5
            concealment_factor = intent.concealment_priority
            actual_yield = base_yield * (1.0 - concealment_factor * 0.5)
            suspicious_leak = base_yield * (1.0 - concealment_factor) * 0.5

            mutations.append(StateMutation(
                mutation_type=MutationType.ESSENCE_CHANGE,
                target_id=state.demiurge.id,
                field="actual",
                delta=actual_yield,
                note="Essence harvested from Underreal",
            ))
            if suspicious_leak > 0.0:
                mutations.append(StateMutation(
                    mutation_type=MutationType.ESSENCE_CHANGE,
                    target_id=state.demiurge.id,
                    field="suspicious",
                    delta=suspicious_leak,
                    note="Essence concealment leak during harvest",
                ))

            state.last_harvest_amount = actual_yield
            state.last_harvest_tick   = state.tick_number

            narrative = (
                f"Harvested {actual_yield:.2f} Essence from the Underreal. "
                f"Suspicious Essence added: {suspicious_leak:.2f}. "
                f"Concealment integrity held at {intent.concealment_priority:.0%} priority."
            )

        # ── Omen / Manifestation ──────────────────────
        elif isinstance(intent, OmenIntent):
            base_pass = (
                OMEN_PASS_BASE_SUCCESS if outcome == ActionOutcome.SUCCESS
                else OMEN_PASS_BASE_PARTIAL
            )
            aware_eff = 1.0 if outcome == ActionOutcome.SUCCESS else rng.uniform(0.5, 1.5)

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
                world_pops = pops_on_world(str(omen_world_id), state)
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

            if omen_world_id:
                emit_omen_visibility_splash(mutations, state, str(omen_world_id))

            scope_desc = (
                state.civilizations[scope_civ_id].name
                if scope_civ_id and scope_civ_id in state.civilizations
                else "all populations"
            )
            narrative = (
                f"An omen manifested across {scope_desc}. "
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
                            emit_lineage_bleed(
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

        elif isinstance(intent, RescindDirectiveIntent):
            mortal = state.mortals.get(str(intent.proxius_id))
            if not mortal or mortal.role != MortalRole.PROXIUS:
                return mutations, "No Proxius found to rescind."
            if not mortal.active_goal:
                return mutations, f"{mortal.name} has no active directive to rescind."
            mutations.append(StateMutation(
                mutation_type=MutationType.PROXIUS_GOAL_CLEARED,
                target_id=mortal.id,
                field="active_goal",
                note=f"{mortal.name}'s directive has been rescinded",
            ))
            mutations.append(StateMutation(
                mutation_type=MutationType.MORTAL_ALIGNMENT,
                target_id=mortal.id,
                field="alignment",
                delta=0.02,
                note=f"{mortal.name} takes stock",
            ))
            narrative = (
                f"{mortal.name}'s active directive has been rescinded. "
                f"They stand idle, awaiting your next instruction."
            )

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
                timestamp=state.universe.age.to_float_years()
            )

        normalized = {
            tag: min(1.0, score / total_weight)
            for tag, score in raw_scores.items()
        }

        return UniverseDomainProfile(
            timestamp=state.universe.age.to_float_years(),
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
                suspicious_stockpile=state.essence.suspicious,
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

            # Passive expectation creep: rises each period, magnitude shrinks with age
            passive_rise = cfg.luminary_essence_passive_rise * ticks_since / max(state.tick_number, 1)
            luminary.essence_expectation_raised += passive_rise

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
            if essence_satisfaction.surplus_ratio >= 0.0:
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
            # Results axis is driven exclusively by Essence satisfaction —
            # Luminaries have no direct view of domain expression, only their income.
            delta = DispositionDelta()

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
                        f"(surplus ratio: {essence_satisfaction.surplus_ratio:+.0%}, "
                        f"trajectory: {essence_satisfaction.trajectory_modifier:+.3f})"
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
                timestamp=state.universe.age.to_float_years(),
            )

            ev = LuminaryEvaluation(
                luminary_id=luminary.id,
                timestamp=state.universe.age.to_float_years(),
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
                tag: s for tag, s in pop.culture_tags.items() if abs(s) > CULTURE_FLOOR
            }
        for mortal in state.mortals.values():
            mortal.belief_tags = {
                tag: s for tag, s in mortal.belief_tags.items() if s > BELIEF_FLOOR
            }
            mortal.culture_tags = {
                tag: s for tag, s in mortal.culture_tags.items() if abs(s) > CULTURE_FLOOR
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

    _KARATH_OMN_NAME      = "Karath Omn"
    _KARATH_OMN_SHUTTLE_A = "Neran Surface"
    _KARATH_OMN_SHUTTLE_B = "Neran Orbital Ring"
    _DURENN_VAIL_NAME = "Durenn Vail"
    _VAIL_DEST_A      = "Neran Surface"
    _VAIL_DEST_B      = "Sethis Surface"

    @staticmethod
    def _default_arrival_milieu(
        state: "SimulationState",
        mortal: "NotableMortal",
        dest_loc_id: "UUID",
    ) -> "Optional[UUID]":
        """Determine pop_milieu when a mortal arrives with no target_pop_id.

        Priority:
        1. Mortal's own Pop is at the destination → use it.
        2. No origin Pop → None.
        3. Build candidate list from destination PopLocation's Pops, filtered
           and priority-sorted, then scan for:
           a. Same occupation (origin Pop's stratum occupation labels)
           b. Same stratum
           c. Closest stratum beneath origin Pop's, within 2 steps
           d. None
        COMMON-and-above mortals exclude FERAL/WILD Pops from consideration.
        """
        dest_loc = state.locations.get(str(dest_loc_id))
        if not isinstance(dest_loc, PopLocation):
            return None

        origin_pop = state.pops.get(str(mortal.pop_id)) if mortal.pop_id else None

        pop_ids = getattr(dest_loc, "pop_ids", [])
        candidates = [state.pops[str(pid)] for pid in pop_ids if str(pid) in state.pops]
        if not candidates:
            return None

        # Step 1: mortal's own Pop is present at the destination
        if origin_pop is not None:
            for pop in candidates:
                if pop.id == origin_pop.id:
                    return pop.id

        # Step 1b: linked Pop at destination — pick highest computed link factor.
        # Runs on unfiltered candidates (FERAL/WILD filter not yet applied);
        # an explicit link relationship overrides social-class aversions.
        if origin_pop is not None and origin_pop.linked_pop_ids:
            best_id: Optional[UUID] = None
            best_lf = -1.0
            for pop in candidates:
                cand_str = str(pop.id)
                if cand_str in origin_pop.linked_pop_ids:
                    lf = compute_link_factor(origin_pop, pop, origin_pop.linked_pop_ids[cand_str])
                    if lf > best_lf:
                        best_lf = lf
                        best_id = pop.id
            if best_id is not None:
                return best_id

        if origin_pop is None:
            return None

        origin_cls = origin_pop.social_class
        try:
            origin_idx = _STRATUM_ORDER.index(origin_cls) if origin_cls else -1
        except ValueError:
            origin_idx = -1

        # Filter: COMMON and above exclude FERAL and WILD Pops
        _common_idx = _STRATUM_ORDER.index(SocialClass.COMMON)
        if origin_idx >= _common_idx:
            candidates = [
                p for p in candidates
                if p.social_class not in (SocialClass.FERAL, SocialClass.WILD)
            ]
        if not candidates:
            return None

        # Sort: same civ first, then same species, then descending size
        origin_civ = str(origin_pop.civilization_id) if origin_pop.civilization_id else None
        origin_spc = str(origin_pop.species_id) if origin_pop.species_id else None

        candidates.sort(key=lambda p: (
            0 if str(p.civilization_id) == origin_civ else 1,
            0 if str(p.species_id) == origin_spc else 1,
            -p.size_fractional,
        ))

        # Step a: same occupation (direct match on Pop.occupation string)
        origin_occ = origin_pop.occupation
        if origin_occ:
            for pop in candidates:
                if pop.occupation == origin_occ:
                    return pop.id

        # Step b: same stratum
        if origin_cls:
            for pop in candidates:
                if pop.social_class == origin_cls:
                    return pop.id

        # Step c: closest stratum beneath (WARRIOR special case: COMMON > TRADER > ARTISAN)
        if origin_idx >= 0:
            if origin_cls == SocialClass.WARRIOR:
                for target_cls in (SocialClass.COMMON, SocialClass.TRADER, SocialClass.ARTISAN):
                    for pop in candidates:
                        if pop.social_class == target_cls:
                            return pop.id
            else:
                for steps in (1, 2):
                    target_idx = origin_idx - steps
                    if target_idx < 0:
                        break
                    target_cls = _STRATUM_ORDER[target_idx]
                    for pop in candidates:
                        if pop.social_class == target_cls:
                            return pop.id

        return None

    @staticmethod
    def _try_same_location_milieu_swap(
        state: SimulationState,
        mortal: "NotableMortal",
        target_pop_id: "UUID",
    ) -> bool:
        """If target Pop is in the mortal's current PopLocation, update pop_milieu
        immediately and return True. Returns False when routing is needed instead.

        Call this before creating a TravelIntent when the destination is a specific
        Pop rather than a named PopLocation. If it returns True, no TravelIntent
        should be created — the milieu change resolves in the current tick.
        """
        from core.universe_core import PopLocation
        target_pop = state.pops.get(str(target_pop_id))
        if target_pop is None:
            return False
        if str(target_pop.current_location) == str(mortal.current_location):
            mortal.pop_milieu = target_pop_id
            return True
        return False

    def _resolve_mortal_travel_decisions(self, state: SimulationState) -> list[str]:
        """Phase 2.6a — assign new TravelIntents via TravelLocation routing."""
        from core.universe_core import PopLocation, TravelLocation
        from core.agent_core import TravelIntent
        from utilities.travel_routing import find_route, build_legs, get_or_create_travel_location

        narratives: list[str] = []
        pop_locs_by_name: dict[str, str] = {
            loc.name: lid
            for lid, loc in state.locations.items()
            if isinstance(loc, PopLocation)
        }

        for mortal in state.mortals.values():
            if mortal.travel_intent is not None:
                continue

            current_loc = state.locations.get(str(mortal.current_location))
            current_name = current_loc.name if current_loc else ""

            dest_name: str | None = None
            if mortal.name == self._KARATH_OMN_NAME:
                dest_name = (
                    self._KARATH_OMN_SHUTTLE_B
                    if current_name == self._KARATH_OMN_SHUTTLE_A
                    else self._KARATH_OMN_SHUTTLE_A
                )
            elif mortal.name == self._DURENN_VAIL_NAME and mortal.mortal_state is None:
                dest_name = (
                    self._VAIL_DEST_B
                    if current_name == self._VAIL_DEST_A
                    else self._VAIL_DEST_A
                )

            if dest_name is None or dest_name not in pop_locs_by_name:
                continue

            dest_id_str = pop_locs_by_name[dest_name]
            route = find_route(state, mortal.current_location, UUID(dest_id_str))
            if route is None or len(route) < 2:
                continue

            legs  = build_legs(state, route)
            tl    = get_or_create_travel_location(state, legs)
            tl.occupants.append(mortal.id)
            mortal.travel_intent = TravelIntent(travel_location_id=tl.id)

            total_ticks = sum(v for v in legs.values())
            if mortal.pinned:
                narratives.append(
                    f"{mortal.name} begins traveling to {dest_name} "
                    f"({total_ticks} tick{'s' if total_ticks != 1 else ''})."
                )
        return narratives

    def _process_mortal_travel(self, state: SimulationState) -> list[str]:
        """Phase 2.6b — advance TravelLocation countdowns; teleport on arrival."""
        from core.universe_core import TravelLocation
        from uuid import UUID

        narratives: list[str] = []
        to_remove: list[str] = []

        for lid, loc in list(state.locations.items()):
            if not isinstance(loc, TravelLocation):
                continue

            loc.ticks_remaining -= 1
            if loc.ticks_remaining > 0:
                # Still crossing this leg — move occupants into the TravelLocation
                # and update its name to reflect the current leg.
                leg_keys = list(loc.legs.keys())
                try:
                    cw_idx = leg_keys.index(loc.current_waypoint)
                    next_wp_id = leg_keys[cw_idx + 1] if cw_idx + 1 < len(leg_keys) else None
                except ValueError:
                    next_wp_id = None
                if next_wp_id:
                    cw_obj = state.locations.get(loc.current_waypoint)
                    nw_obj = state.locations.get(next_wp_id)
                    loc.name = f"{cw_obj.name if cw_obj else loc.current_waypoint} → {nw_obj.name if nw_obj else next_wp_id}"
                loc_uuid = loc.id
                for occ_id in loc.occupants:
                    mortal = state.mortals.get(str(occ_id))
                    if mortal:
                        mortal.current_location = loc_uuid
                continue

            leg_keys = list(loc.legs.keys())
            try:
                current_idx = leg_keys.index(loc.current_waypoint)
            except ValueError:
                fallback_loc = UUID(leg_keys[0]) if leg_keys else loc.id
                for occ_id in loc.occupants:
                    mortal = state.mortals.get(str(occ_id))
                    if mortal:
                        target_pop_id = mortal.travel_intent.target_pop_id if mortal.travel_intent else None
                        mortal.current_location = fallback_loc
                        mortal.travel_intent = None
                        if target_pop_id is not None:
                            mortal.pop_milieu = target_pop_id
                to_remove.append(lid)
                continue

            next_idx = current_idx + 1
            if next_idx >= len(leg_keys):
                # current_waypoint is already the destination key (cost 0)
                dest_uuid = UUID(loc.current_waypoint)
                for occ_id in loc.occupants:
                    mortal = state.mortals.get(str(occ_id))
                    if mortal:
                        target_pop_id = mortal.travel_intent.target_pop_id if mortal.travel_intent else None
                        mortal.current_location = dest_uuid
                        mortal.travel_intent = None
                        if target_pop_id is not None:
                            mortal.pop_milieu = target_pop_id
                        else:
                            mortal.pop_milieu = self._default_arrival_milieu(state, mortal, dest_uuid)
                to_remove.append(lid)
                continue

            next_wp   = leg_keys[next_idx]
            next_cost = loc.legs[next_wp]

            if next_cost == 0:
                # Arrival
                dest_loc  = state.locations.get(next_wp)
                dest_name = dest_loc.name if dest_loc else next_wp
                dest_uuid_arr = UUID(next_wp)
                for occ_id in loc.occupants:
                    mortal = state.mortals.get(str(occ_id))
                    if mortal:
                        target_pop_id = mortal.travel_intent.target_pop_id if mortal.travel_intent else None
                        mortal.current_location = dest_uuid_arr
                        mortal.travel_intent    = None
                        if target_pop_id is not None:
                            mortal.pop_milieu = target_pop_id
                        else:
                            mortal.pop_milieu = self._default_arrival_milieu(state, mortal, dest_uuid_arr)
                        if mortal.pinned:
                            narratives.append(f"{mortal.name} arrives at {dest_name}.")
                to_remove.append(lid)
            else:
                loc.current_waypoint  = next_wp
                loc.ticks_remaining   = next_cost
                # Mortal arrives at the start of the next leg's PopLocation.
                next_wp_uuid = UUID(next_wp)
                for occ_id in loc.occupants:
                    mortal = state.mortals.get(str(occ_id))
                    if mortal:
                        mortal.current_location = next_wp_uuid
                        if mortal.mortal_state is not None:
                            mortal.mortal_state.pending_transfer = True

        for lid in to_remove:
            tl = state.locations.get(lid)
            if tl is not None and hasattr(tl, "pop_ids"):
                # Determine destination: last leg key (cost 0) or first leg key as fallback
                leg_keys = list(tl.legs.keys()) if tl.legs else []
                dest_loc_id_str = leg_keys[-1] if leg_keys else None
                dest_loc_uuid = None
                if dest_loc_id_str:
                    try:
                        dest_loc_uuid = UUID(dest_loc_id_str)
                    except ValueError:
                        pass
                if dest_loc_uuid is None:
                    dest_loc_uuid = tl.id
                dest_pop_loc = state.locations.get(str(dest_loc_uuid))
                for pop_id in list(tl.pop_ids):
                    crew = state.pops.get(str(pop_id))
                    if crew is None:
                        continue
                    crew.current_location = dest_loc_uuid
                    if dest_pop_loc is not None and hasattr(dest_pop_loc, "pop_ids"):
                        if pop_id not in dest_pop_loc.pop_ids:
                            dest_pop_loc.pop_ids.append(pop_id)
            state.locations.pop(lid, None)

        return narratives

    def _tick_pop_agents(self, state: "SimulationState", current_tick: int) -> list[str]:
        """Phase 2.57 — run PopAgent logic for each Pop with pop_state."""
        from logic.pop_agent_logic import compute_pop_priorities, compute_active_slots, resolve_pop_actions
        from core.universe_core import PopLocation

        narratives: list[str] = []
        factions = getattr(state, "factions", {})

        for pop in state.pops.values():
            ps = pop.pop_state
            if ps is None:
                continue

            pop_loc = state.locations.get(str(pop.current_location))
            if not isinstance(pop_loc, PopLocation):
                continue

            # 1. Decay PopNeeds
            for need in ps.needs:
                if need.satiation_hold > 0:
                    need.satiation_hold -= 1
                else:
                    need.satisfaction = max(0.0, need.satisfaction - need.decay_rate)

            # 2. Fatigue update
            all_directives = list(pop.active_directives)
            for fid in pop.faction_ids:
                faction = factions.get(str(fid))
                if faction:
                    all_directives.extend(faction.active_directives)
            has_slot_modifier = any(d.slot_modifier != 0 for d in all_directives)
            if has_slot_modifier:
                ps.fatigue = min(1.0, ps.fatigue + 0.05)
            else:
                ps.fatigue = max(0.0, ps.fatigue - 0.05)

            # 3–4. Priority vector + active slots
            priorities = compute_pop_priorities(pop, factions)
            ps.action_priorities = priorities
            n_slots = compute_active_slots(pop, factions)

            # 5–6. Resolve actions + consumption
            events = resolve_pop_actions(pop, pop_loc, priorities, n_slots, factions, current_tick)
            narratives.extend(events)

        return narratives

    def _tick_mortal_agents(self, state: SimulationState, current_tick: int) -> list[str]:
        """Phase 2.55 — run autonomous civilian agent logic for each mortal with mortal_state."""
        import uuid as _uuid_mod
        narratives: list[str] = []
        for mortal in state.mortals.values():
            cs = mortal.mortal_state
            if cs is None:
                continue

            # Lazy desire init: existing saves pre-date desires; populate on first tick
            if not cs.desires and mortal.culture_tags:
                cs.desires = compute_desire_profile(mortal.culture_tags)
                # Pre-existing LocationFacts are already-known places — mark as visited
                # so they don't trigger Exploration first-visit satisfaction spuriously
                if mortal.knowledge_base:
                    for _f in mortal.knowledge_base.facts:
                        if getattr(_f, "fact_type", None) == "location" and _f.visit_count == 0:
                            _f.visit_count = 1

            # Lazy PopFact seeding: populate KB with same-civ Pops under home SignificantLocation
            if (
                mortal.knowledge_base is not None
                and not mortal.knowledge_base.pop_facts()
                and mortal.civilization_id is not None
                and mortal.home_location is not None
            ):
                from core.agent_core import PopFact as _PopFact
                _home_loc = state.locations.get(str(mortal.home_location))
                _home_parent_id = str(getattr(_home_loc, "parent_id", None) or "")
                if _home_parent_id:
                    for _sib_loc in state.locations.values():
                        if not isinstance(_sib_loc, PopLocation):
                            continue
                        if str(getattr(_sib_loc, "parent_id", None) or "") != _home_parent_id:
                            continue
                        for _seed_pid in _sib_loc.pop_ids:
                            _seed_pop = state.pops.get(str(_seed_pid))
                            if _seed_pop is None or _seed_pop.civilization_id != mortal.civilization_id:
                                continue
                            if mortal.knowledge_base.get_pop_fact(str(_seed_pid)) is None:
                                mortal.knowledge_base.facts.append(
                                    _PopFact(pop_id=str(_seed_pid), label=pop_label(_seed_pop))
                                )

            # Passive restoration for needs that are auto-satisfied by stable conditions
            loc = state.locations.get(str(mortal.current_location))
            if loc and _effective_commerce_quality(loc, state) > 0:
                sust = cs.get_need(NEED_SUSTENANCE)
                if sust and sust.satisfaction < 1.0:
                    sust.satisfaction = min(1.0, sust.satisfaction + 0.03)
            safe = cs.get_need(NEED_SAFETY)
            if safe and safe.satisfaction < 1.0:
                safe.satisfaction = min(1.0, safe.satisfaction + 0.02)

            # Wealth decay on the mortal's home PopLocation
            local_pop_id = str(mortal.pop_milieu or mortal.pop_id or "")
            local_pop = state.pops.get(local_pop_id)
            if local_pop:
                pop_loc = state.locations.get(str(local_pop.current_location))
                if pop_loc and hasattr(pop_loc, "wealth") and pop_loc.wealth > 0.0:
                    pop_loc.wealth = max(0.0, pop_loc.wealth - 0.005)

            _was_idle = cs.last_action == "idle"
            for need in cs.needs:
                if need.satiation_hold > 0:
                    # Leisure hold is preserved while the mortal is idle — restful downtime.
                    if need.name == NEED_LEISURE and _was_idle:
                        pass
                    else:
                        need.satiation_hold -= 1
                elif need.name == NEED_LEISURE and _was_idle:
                    pass  # satisfaction also frozen — idle keeps leisure from falling
                else:
                    need.satisfaction = max(0.0, need.satisfaction - need.decay_rate)

            for desire in cs.desires:
                if desire.satiation_hold > 0:
                    desire.satiation_hold -= 1
                else:
                    desire.satisfaction = max(0.0, desire.satisfaction - desire.decay_rate)

            if mortal.fatigue > 0.0:
                mortal.fatigue = max(0.0, mortal.fatigue - 0.1)

            # Zero-cost milieu switch: move among best local pop for pressing social needs
            _milieu_pop_id = _select_local_pop(mortal, state)
            if _milieu_pop_id:
                mortal.pop_milieu = UUID(_milieu_pop_id)

            # Milieu → PopFact: being among a Pop creates a KB record even before interacting
            if mortal.pop_milieu and (kb := mortal.knowledge_base):
                _milieu_id_str = str(mortal.pop_milieu)
                if kb.get_pop_fact(_milieu_id_str) is None:
                    from core.agent_core import PopFact as _PopFact
                    _milieu_pop = state.pops.get(_milieu_id_str)
                    if _milieu_pop:
                        kb.facts.append(_PopFact(pop_id=_milieu_id_str, label=pop_label(_milieu_pop)))

            # Observe local pop_location wealth → keep sell quality fact current
            if (kb := mortal.knowledge_base):
                _obs_loc = state.locations.get(str(mortal.current_location))
                if _obs_loc and hasattr(_obs_loc, "wealth"):
                    _cur_loc_str = str(mortal.current_location)
                    for _qf in kb.facts:
                        if (getattr(_qf, "fact_type", None) == "location_quality"
                                and getattr(_qf, "location_id", None) == _cur_loc_str
                                and getattr(_qf, "quality_type", None) == "sell"):
                            _qf.quality = _obs_loc.wealth
                            break

            # Background loading: auto-collect each tick while a loading session is active.
            # The freighter is docked; evaluate_mortal_action will return personal time
            # (leisure / socialize / idle) rather than collect or travel.
            if cs.collecting_ticks_remaining > 0:
                _bg_loc = state.locations.get(str(mortal.current_location))
                _bg_cr  = getattr(_bg_loc, "collectible_resource", None)
                _bg_cap = next(
                    (a.cargo_capacity for a in mortal.assets if a.cargo_capacity is not None),
                    None,
                )
                _bg_load = sum(r.quantity for r in cs.inventory if "sell" in r.usable_for)
                if _bg_cap is not None and _bg_load >= _bg_cap:
                    cs.collecting_ticks_remaining = 0          # hold full — stop loading
                elif _bg_cr:
                    _bg_res = cs.get_resource(_bg_cr.resource_type)
                    if _bg_res is None:
                        from core.agent_core import Resource as _Resource
                        _bg_res = _Resource(resource_type=_bg_cr.resource_type)
                        cs.inventory.append(_bg_res)
                    _bg_res.quantity += _bg_cr.resource_yield
                    mortal.fatigue = min(1.0, mortal.fatigue + 0.15)
                    if mortal.pinned:
                        narratives.append(
                            f"{mortal.name} loads {_bg_cr.resource_yield} {_bg_cr.resource_type} "
                            f"(hold: {_bg_res.quantity:.0f}/{_bg_cap:.0f})."
                        )
                    cs.collecting_ticks_remaining = max(0, cs.collecting_ticks_remaining - 1)

            if cs.pending_transfer:
                cs.pending_transfer = False
                cs.last_action = "transfer"
                continue  # busy setting up next leg — no need satisfaction this tick

            # Presence tracking: increment visit_count on current LocationFact; grant Exploration on first visit
            _travelling = mortal.travel_intent is not None or (
                (lambda _l: _l is not None and getattr(_l, "location_type", None) == "travel_location")(
                    state.locations.get(str(mortal.current_location))
                )
            )
            if not _travelling and (kb := mortal.knowledge_base):
                _cur_loc_str = str(mortal.current_location)
                _loc_fact = next(
                    (f for f in kb.facts if getattr(f, "fact_type", None) == "location" and f.location_id == _cur_loc_str),
                    None,
                )
                if _loc_fact is not None:
                    if _loc_fact.visit_count == 0:
                        # First visit — satisfy Exploration desire
                        _exp_desire = next((d for d in cs.desires if d.name == DESIRE_EXPLORATION), None)
                        if _exp_desire is not None:
                            _exp_desire.satisfaction = min(1.0, _exp_desire.satisfaction + 0.40)
                            _exp_desire.satiation_hold = 5
                    _loc_fact.visit_count = min(99, _loc_fact.visit_count + 1)

                # Passive Pop discovery: 20% chance per unknown Pop physically at this PopLocation
                _cur_pop_loc = state.locations.get(_cur_loc_str)
                if isinstance(_cur_pop_loc, PopLocation):
                    from core.agent_core import PopFact as _PopFact
                    for _disc_pid in _cur_pop_loc.pop_ids:
                        _disc_pid_str = str(_disc_pid)
                        if kb.get_pop_fact(_disc_pid_str) is not None:
                            continue
                        _disc_pop = state.pops.get(_disc_pid_str)
                        if _disc_pop is None or str(_disc_pop.current_location) != _cur_loc_str:
                            continue
                        if random.random() < 0.20:
                            kb.facts.append(_PopFact(pop_id=_disc_pid_str, label=pop_label(_disc_pop)))

            _sync_faction_directives(mortal, state, current_tick)
            action = evaluate_mortal_action(mortal, state, current_tick)
            cs.last_action = action

            if action == "collect":
                loc = state.locations.get(str(mortal.current_location))
                cr = getattr(loc, "collectible_resource", None)
                if cr:
                    res = cs.get_resource(cr.resource_type)
                    if res is None:
                        from core.agent_core import Resource as _Resource
                        res = _Resource(resource_type=cr.resource_type)
                        cs.inventory.append(res)
                    res.quantity += cr.resource_yield
                    mortal.fatigue = min(1.0, mortal.fatigue + 0.15)
                    if mortal.pinned:
                        narratives.append(
                            f"{mortal.name} collects {cr.resource_yield} {cr.resource_type} "
                            f"(total: {res.quantity:.0f})."
                        )

            elif action == "sell":
                loc = state.locations.get(str(mortal.current_location))
                quality = _effective_commerce_quality(loc, state) if loc else 0.5
                for res in cs.inventory:
                    if "sell" not in res.usable_for or res.quantity < res.threshold:
                        continue
                    if res.converts_to is None:
                        continue
                    units = int(res.quantity)
                    if units == 0:
                        continue
                    credits_gained = units * res.base_value * quality
                    res.quantity -= units
                    target = cs.get_resource(res.converts_to)
                    if target is None:
                        from core.agent_core import Resource as _Resource
                        target = _Resource(resource_type=res.converts_to)
                        cs.inventory.append(target)
                    target.quantity += credits_gained
                    if res.fills_need:
                        need = next((n for n in cs.needs if n.name == res.fills_need), None)
                        if need:
                            need.satisfaction = 1.0
                            need.satiation_hold = round(8 * quality)
                    # Find sell pop by location: prefer own pop if present, else any local pop.
                    # Do NOT use pop_milieu here — milieu selection optimises for social needs
                    # and may point to a non-merchant pop even while Durenn is at his trade hub.
                    _sell_cur_loc = str(mortal.current_location)
                    _sell_pop = state.pops.get(str(mortal.pop_id)) if mortal.pop_id else None
                    if _sell_pop is None or str(_sell_pop.current_location) != _sell_cur_loc:
                        _sell_pop = next(
                            (p for p in state.pops.values()
                             if str(p.current_location) == _sell_cur_loc),
                            None,
                        )
                    if _sell_pop:
                        _pop_loc = state.locations.get(str(_sell_pop.current_location))
                        if _pop_loc and hasattr(_pop_loc, "wealth"):
                            wealth_gain = min(0.05, credits_gained * 0.005)
                            _pop_loc.wealth = min(1.0, _pop_loc.wealth + wealth_gain)
                        # Pop recognition → Status satisfaction
                        _s_gain, _s_hold = _status_recognition_from_pop(
                            mortal, _sell_pop, state, strong=True
                        )
                        _status_need = cs.get_need(NEED_STATUS)
                        if _status_need:
                            _status_need.satisfaction = min(1.0, _status_need.satisfaction + _s_gain)
                            if _s_hold:
                                _status_need.satiation_hold = _s_hold
                        if kb := mortal.knowledge_base:
                            for _df in kb.directive_facts():
                                if _df.directive_type == "commerce" and _df.satisfying_action == "sell":
                                    purpose_need = cs.get_need(NEED_PURPOSE)
                                    if purpose_need:
                                        _origin_pop = state.pops.get(str(mortal.pop_id)) if mortal.pop_id else None
                                        _is_own = _origin_pop and str(_sell_pop.id) == str(_origin_pop.id)
                                        if _is_own:
                                            purpose_need.satisfaction = 1.0
                                            purpose_need.satiation_hold = 10
                                        elif _origin_pop and str(_sell_pop.id) in _origin_pop.linked_pop_ids:
                                            _p_base = _origin_pop.linked_pop_ids[str(_sell_pop.id)]
                                            _p_lf = compute_link_factor(_origin_pop, _sell_pop, _p_base)
                                            purpose_need.satisfaction = min(1.0, purpose_need.satisfaction + _p_lf)
                                            purpose_need.satiation_hold = round(10 * _p_lf)
                                    break
                    # Accumulation desire satisfaction from completing a trade
                    _acc_desire = next((d for d in cs.desires if d.name == DESIRE_ACCUMULATION), None)
                    if _acc_desire is not None:
                        _acc_desire.satisfaction = min(1.0, _acc_desire.satisfaction + 0.25)
                        _acc_desire.satiation_hold = 3
                    mortal.fatigue = min(1.0, mortal.fatigue + 0.1)
                    if mortal.pinned:
                        _sell_loc = state.locations.get(str(mortal.current_location))
                        _sell_loc_str = f" at {_sell_loc.name}" if _sell_loc else ""
                        narratives.append(
                            f"{mortal.name} sells {units} {res.resource_type} "
                            f"for {credits_gained:.0f} credits{_sell_loc_str}."
                        )
                    break

            elif action == "spend":
                loc = state.locations.get(str(mortal.current_location))
                quality = _effective_commerce_quality(loc, state) if loc else 0.5
                for res in cs.inventory:
                    if "spend" not in res.usable_for or res.quantity < res.threshold:
                        continue
                    base_per_unit = 0.12
                    bulk_bonus = 0.04
                    target_need = (
                        next((n for n in cs.needs if n.name == res.fills_need), None)
                        if res.fills_need else None
                    )
                    needs_to_fill = [target_need] if target_need else cs.needs
                    max_deficit = max((1.0 - n.satisfaction for n in needs_to_fill), default=0.0)
                    available = int(res.quantity)
                    if max_deficit > 0 and base_per_unit * quality > 0:
                        n_units = max(1, min(
                            int(max_deficit / (base_per_unit * quality) + 0.5),
                            available,
                        ))
                    else:
                        n_units = min(1, available)
                    gain_per_need = n_units * base_per_unit * quality * (1 + bulk_bonus * (n_units - 1))
                    res.quantity -= n_units
                    hold_ticks = round(8 * quality)
                    for need in needs_to_fill:
                        need.satisfaction = min(1.0, need.satisfaction + gain_per_need)
                        if need.satisfaction >= 1.0:
                            need.satiation_hold = hold_ticks
                    need_names = ", ".join(n.name for n in needs_to_fill)
                    if mortal.pinned:
                        narratives.append(
                            f"{mortal.name} spends {n_units} credits on {need_names} "
                            f"(+{gain_per_need:.2f} satisfaction)."
                        )
                    break

            elif action == "leisure":
                local_pop_id = str(mortal.pop_milieu or mortal.pop_id or "")
                pop = state.pops.get(local_pop_id)
                gain = 0.0  # default so narrative reference is always bound
                if pop:
                    quality = _pop_practice_quality(mortal.culture_tags, pop.culture_tags)
                    _crew_mult = CREW_LEISURE_MULTIPLIER if getattr(pop, "asset_crew_for", None) else 1.0
                    leisure_need = cs.get_need(NEED_LEISURE)
                    if leisure_need:
                        gain = LEISURE_BASE_GAIN * quality * _crew_mult
                        leisure_need.satisfaction = min(1.0, leisure_need.satisfaction + gain)
                        leisure_need.satiation_hold = round(LEISURE_SATIATION_HOLD_BASE * quality * _crew_mult)
                    mortal.fatigue = min(1.0, mortal.fatigue + 0.03)
                    # Expression desire satisfaction when practice quality is high
                    if quality > 0.5:
                        _expr_desire = next((d for d in cs.desires if d.name == DESIRE_EXPRESSION), None)
                        if _expr_desire is not None:
                            _expr_desire.satisfaction = min(1.0, _expr_desire.satisfaction + 0.20)
                            _expr_desire.satiation_hold = 2
                    # Upsert PopFact for time spent with this Pop during leisure
                    if (kb := mortal.knowledge_base) and pop:
                        _pf = kb.get_pop_fact(local_pop_id)
                        _novelty = _pop_novelty(_pf, current_tick)
                        if _pf is None:
                            from core.agent_core import PopFact as _PopFact
                            _pf = _PopFact(pop_id=local_pop_id, label=pop_label(pop))
                            kb.facts.append(_pf)
                        _pf.interaction_count += 1
                        _pf.last_interaction_tick = current_tick
                        # Leisure novelty boost: smaller than socialize (0.12 vs 0.25); leisure enjoyment
                        # is intrinsic to the activity, not relational — no novelty discount on gain.
                        _exp_desire = next((d for d in cs.desires if d.name == DESIRE_EXPLORATION), None)
                        if _exp_desire is not None and _novelty >= EXPLORATION_NOVELTY_THRESHOLD:
                            _exp_desire.satisfaction = min(1.0, _exp_desire.satisfaction + _novelty * 0.12)
                            _exp_desire.satiation_hold = round(_novelty * 2)
                    if mortal.pinned:
                        narratives.append(
                            f"{mortal.name} spends time enjoying local culture "
                            f"(quality {quality:.2f}, +{gain:.2f} leisure)."
                        )

            elif action == "socialize":
                local_pop_id = str(mortal.pop_milieu or mortal.pop_id or "")
                pop = state.pops.get(local_pop_id)
                if pop:
                    quality = _pop_social_quality(
                        mortal.belief_tags, mortal.culture_tags,
                        pop.dominant_beliefs, pop.culture_tags,
                        same_species=(str(mortal.species_id) == str(pop.species_id)) if (mortal.species_id and pop.species_id) else True,
                        same_civ=True,
                    )
                    # compute novelty BEFORE updating PopFact
                    _kb = mortal.knowledge_base
                    _pf = _kb.get_pop_fact(local_pop_id) if _kb else None
                    _novelty = _pop_novelty(_pf, current_tick)
                    _novelty_factor = SOCIAL_NOVELTY_FLOOR + _novelty * (1.0 - SOCIAL_NOVELTY_FLOOR)
                    belonging_need = cs.get_need(NEED_BELONGING)
                    if belonging_need:
                        gain = SOCIALIZE_BASE_GAIN * quality * _novelty_factor
                        belonging_need.satisfaction = min(1.0, belonging_need.satisfaction + gain)
                        belonging_need.satiation_hold = round(SOCIALIZE_SATIATION_HOLD_BASE * quality * _novelty_factor)
                    # Minor Status recognition from being seen by the community
                    _s_gain, _s_hold = _status_recognition_from_pop(
                        mortal, pop, state, strong=False
                    )
                    _soc_status = cs.get_need(NEED_STATUS)
                    if _soc_status:
                        _soc_status.satisfaction = min(1.0, _soc_status.satisfaction + _s_gain)
                        if _s_hold:
                            _soc_status.satiation_hold = _s_hold
                    mortal.fatigue = min(1.0, mortal.fatigue + 0.03)
                    # Upsert PopFact
                    if _kb is not None:
                        if _pf is None:
                            from core.agent_core import PopFact as _PopFact
                            _pf = _PopFact(pop_id=local_pop_id, label=pop_label(pop))
                            _kb.facts.append(_pf)
                        _pf.interaction_count += 1
                        _pf.last_interaction_tick = current_tick
                    # Exploration satisfaction from novel social interaction
                    _exp_desire = next((d for d in cs.desires if d.name == DESIRE_EXPLORATION), None)
                    if _exp_desire is not None and _novelty >= EXPLORATION_NOVELTY_THRESHOLD:
                        _exp_desire.satisfaction = min(1.0, _exp_desire.satisfaction + _novelty * 0.25)
                        _exp_desire.satiation_hold = round(_novelty * 4)
                    if mortal.pinned:
                        from utilities.occupation_registry import pop_display_name as _pdname
                        _civ_for_pop = state.civilizations.get(str(pop.civilization_id)) if pop.civilization_id else None
                        if pop.visibility > ENTITY_VISIBILITY_FLOOR:
                            _pop_label = _pdname(pop, _civ_for_pop)
                            _soc_target = f"§pop§{local_pop_id}§{_pop_label}§"
                        else:
                            _soc_target = "the local community"
                        narratives.append(
                            f"{mortal.name} socializes with {_soc_target} "
                            f"(quality {quality:.2f}, +{gain:.2f} belonging)."
                        )

            elif action and action.startswith("travel:"):
                dest_id = action.split(":", 1)[1]
                try:
                    from utilities.travel_routing import (
                        find_qualified_routes, get_or_create_travel_location,
                    )
                    from logic.mortal_agent_logic import _select_best_route
                    dest_uuid = _uuid_mod.UUID(dest_id)
                    _cs = mortal.mortal_state
                    routes = find_qualified_routes(state, mortal, _cs, mortal.current_location, dest_uuid)
                    chosen = _select_best_route(routes, _cs)
                    if chosen:
                        tl = get_or_create_travel_location(state, chosen.legs)
                        tl.occupants.append(mortal.id)
                        mortal.travel_intent = TravelIntent(
                            travel_location_id=tl.id
                        )
                        # Move crew pop into TravelLocation and set as milieu
                        _crew_pop = next(
                            (p for p in state.pops.values()
                             if getattr(p, "asset_crew_for", None) is not None
                             and any(a.asset_type == p.asset_crew_for for a in mortal.assets)),
                            None,
                        )
                        if _crew_pop:
                            # Remove from previous PopLocation's pop_ids
                            _old_crew_loc = state.locations.get(str(_crew_pop.current_location))
                            if _old_crew_loc is not None and hasattr(_old_crew_loc, "pop_ids"):
                                try:
                                    _old_crew_loc.pop_ids.remove(_crew_pop.id)
                                except ValueError:
                                    pass
                            tl.pop_ids.append(_crew_pop.id)
                            _crew_pop.current_location = tl.id
                            mortal.pop_milieu = _crew_pop.id
                        mortal.fatigue = min(1.0, mortal.fatigue + 0.2)
                        dest_loc = state.locations.get(dest_id)
                        dest_name = dest_loc.name if dest_loc else dest_id
                        if mortal.pinned:
                            narratives.append(f"{mortal.name} departs for {dest_name}.")
                except (ValueError, Exception):
                    pass

            elif action and action.startswith("wander:"):
                # Wander: same as travel but desire-driven. Exploration satisfaction granted on arrival
                # (handled by visit_count first-visit detection above). Reuse travel logic exactly.
                wander_dest_id = action.split(":", 1)[1]
                try:
                    from utilities.travel_routing import (
                        find_qualified_routes, get_or_create_travel_location,
                    )
                    from logic.mortal_agent_logic import _select_best_route
                    dest_uuid = _uuid_mod.UUID(wander_dest_id)
                    _cs = mortal.mortal_state
                    routes = find_qualified_routes(state, mortal, _cs, mortal.current_location, dest_uuid)
                    chosen = _select_best_route(routes, _cs)
                    if chosen:
                        tl = get_or_create_travel_location(state, chosen.legs)
                        tl.occupants.append(mortal.id)
                        mortal.travel_intent = TravelIntent(travel_location_id=tl.id)
                        _crew_pop = next(
                            (p for p in state.pops.values()
                             if getattr(p, "asset_crew_for", None) is not None
                             and any(a.asset_type == p.asset_crew_for for a in mortal.assets)),
                            None,
                        )
                        if _crew_pop:
                            _old_crew_loc = state.locations.get(str(_crew_pop.current_location))
                            if _old_crew_loc is not None and hasattr(_old_crew_loc, "pop_ids"):
                                try:
                                    _old_crew_loc.pop_ids.remove(_crew_pop.id)
                                except ValueError:
                                    pass
                            tl.pop_ids.append(_crew_pop.id)
                            _crew_pop.current_location = tl.id
                            mortal.pop_milieu = _crew_pop.id
                        mortal.fatigue = min(1.0, mortal.fatigue + 0.2)
                        dest_loc = state.locations.get(wander_dest_id)
                        dest_name = dest_loc.name if dest_loc else wander_dest_id
                        if mortal.pinned:
                            narratives.append(f"{mortal.name} wanders toward {dest_name}.")
                except (ValueError, Exception):
                    pass

        return narratives

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

    @staticmethod
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
                _pop_domain_receptivity(target, tag)
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
        dist_factor = pop_distance_factor(state, omen_loc_id, target.current_location)
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

    @staticmethod
    def _format_pop_entries_with_links(
        pop_items: "list[tuple[str, Pop, Civilization | None]]",
        state: "SimulationState | None" = None,
    ) -> "list[str]":
        """Return sentinel-embedded formatted strings for a list of (pid, pop, civ) tuples.

        Groups by civ_id; §civ§ link appears only on the first Pop per civ group.
        For wild-civ pops, a §species§ link prefixes the entry instead.
        Pop label is emitted as §pop§pid§label§ so display.py can resolve it to a clickable link.
        """
        civ_groups: dict[str, list] = {}
        civ_order: list[str] = []
        for pid, pop, civ in pop_items:
            civ_key = str(civ.id) if civ else ""
            if civ_key not in civ_groups:
                civ_groups[civ_key] = []
                civ_order.append(civ_key)
            civ_groups[civ_key].append((pid, pop, civ))

        from utilities.occupation_registry import pop_display_name as _pop_display_name

        entries: list[str] = []
        for civ_key in civ_order:
            for i, (pid, pop, civ) in enumerate(civ_groups[civ_key]):
                label = _pop_display_name(pop, civ)
                pop_sentinel = f"§pop§{pid}§{label}§"
                entry = f"{pop_sentinel} (sz {pop.size_magnitude})"
                if i == 0 and civ:
                    if not is_wild_civ(civ):
                        civ_label = civ.name.removeprefix("The ")
                        entry = f"§civ§{civ.id}§{civ_label}§ {entry}"
                    elif state is not None and pop.species_id:
                        sp = state.species.get(str(pop.species_id))
                        if sp:
                            entry = f"§species§{sp.id}§{sp.name}§ {entry}"
                entries.append(entry)
        return entries

    @staticmethod
    def _format_pop_discovery_line(mortal_name: str, discovered_pop_ids: set, state: "SimulationState") -> str:
        """Build a single discovery sentence, grouping Pops by civilization with clickable links."""
        if not discovered_pop_ids:
            return ""
        pop_items = []
        for pid in sorted(discovered_pop_ids):
            pop = state.pops.get(pid)
            if not pop:
                continue
            civ = state.civilizations.get(str(pop.civilization_id)) if pop.civilization_id else None
            pop_items.append((pid, pop, civ))
        if not pop_items:
            return ""
        entries = TickLoop._format_pop_entries_with_links(pop_items, state)
        if not entries:
            return ""
        return f" Through {mortal_name}, you have discovered: {', '.join(entries)}."

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
        if world_id:
            splash_pops = pops_on_world(world_id, state)
        else:
            from core.universe_core import TravelLocation as _TL
            _tloc = state.locations.get(str(mortal.current_location))
            if not isinstance(_tloc, _TL) or not _tloc.pop_ids:
                return
            splash_pops = [
                p for uid in _tloc.pop_ids
                if (p := state.pops.get(str(uid))) is not None
            ]
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

            # Co-located linked Pops bypass resistance/distance/receptivity —
            # the link relationship overrides social-boundary factors.
            sp_str = str(sp.id)
            co_linked_lf: float | None = None
            if src_pop is not None and sp_str in src_pop.linked_pop_ids and sp_str != str(src_pop.id):
                co_linked_lf = compute_link_factor(src_pop, sp, src_pop.linked_pop_ids[sp_str])

            if co_linked_lf is not None:
                for dv in domain_vectors:
                    splash_delta = dv.direction * per_unit_delta * WHISPER_POP_SPLASH * co_linked_lf * influence
                    if abs(splash_delta) > 1e-5:
                        mutations.append(StateMutation(
                            mutation_type=MutationType.POP_BELIEF_SHIFT,
                            target_id=sp.id,
                            field=dv.domain_tag,
                            delta=splash_delta,
                            note=(
                                f"{note_prefix} linked splash to {sp.stratum} Pop"
                                + (" (own pop)" if is_own else "")
                            ),
                        ))
                        emit_lineage_bleed(mutations, state, sp, dv.domain_tag, splash_delta, "whisper")
                for cv in culture_vectors:
                    splash_delta = cv.direction * per_unit_delta * WHISPER_POP_SPLASH * co_linked_lf * influence
                    if abs(splash_delta) > 1e-5:
                        mutations.append(StateMutation(
                            mutation_type=MutationType.POP_CULTURE_SHIFT,
                            target_id=sp.id,
                            field=cv.culture_tag,
                            delta=splash_delta,
                            note=(
                                f"{note_prefix} linked culture splash to {sp.stratum} Pop"
                                + (" (own pop)" if is_own else "")
                            ),
                        ))
            else:
                resistance = pop_contact_resistance(
                    sp, src_civ_id, src_species_id, src_class, state, cfg,
                    src_size=src_size,
                )
                dist_factor = pop_distance_factor(state, src_loc_id, sp.current_location)
                for dv in domain_vectors:
                    receptivity = _pop_domain_receptivity(sp, dv.domain_tag)
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
                        emit_lineage_bleed(
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

            # Linked-pop belief cascade (cross-world only — co-located linked Pops
            # are already handled above via link-override world splash).
            cascade_scale = LINK_SPLASH_OWN_POP_SCALE if is_own else LINK_SPLASH_WORLD_POP_SCALE
            self._emit_linked_pop_belief_cascade(
                mutations, state, sp,
                domain_vectors=domain_vectors,
                culture_vectors=culture_vectors,
                per_unit_delta=per_unit_delta,
                cascade_scale=cascade_scale,
                note_prefix=note_prefix,
                skip_world_id=world_id,
            )

    def _emit_linked_pop_belief_cascade(
        self,
        mutations: list,
        state: "SimulationState",
        source_pop: "Pop",
        domain_vectors,
        culture_vectors,
        per_unit_delta: float,
        cascade_scale: float,
        note_prefix: str,
        skip_world_id: "str | None" = None,
    ) -> None:
        """Cascade belief/culture from a world-splash Pop to its linked Pops.

        Bypasses contact resistance, distance factor, and domain receptivity —
        the link factor IS the relationship-quality proxy, and cross-world reach
        is the intended benefit. Depth is structurally bounded to 1: this method
        only emits StateMutation objects; it never calls _emit_whisper_splash.

        skip_world_id: when set, linked Pops on that world are skipped because
        they were already handled via link-override world splash in
        _emit_whisper_splash. Pass world_id from the caller to avoid
        double-counting co-located linked Pops.

        emit_lineage_bleed is deliberately omitted: lineage bleed models
        within-world heritage; applying it through cross-world links would
        create spurious cross-world heritage effects.
        """
        if not source_pop.linked_pop_ids:
            return
        for other_id_str, base_factor in source_pop.linked_pop_ids.items():
            other_pop = state.pops.get(other_id_str)
            if other_pop is None or other_pop.id == source_pop.id:
                continue
            if skip_world_id and _resolve_world_id_for(state, other_pop.current_location) == skip_world_id:
                continue
            lf = compute_link_factor(source_pop, other_pop, base_factor)
            for dv in domain_vectors:
                delta = dv.direction * per_unit_delta * WHISPER_POP_SPLASH * lf * cascade_scale
                if abs(delta) > 1e-5:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.POP_BELIEF_SHIFT,
                        target_id=other_pop.id,
                        field=dv.domain_tag,
                        delta=delta,
                        note=f"{note_prefix} linked cascade to {other_pop.stratum} Pop",
                    ))
            for cv in culture_vectors:
                delta = cv.direction * per_unit_delta * WHISPER_POP_SPLASH * lf * cascade_scale
                if abs(delta) > 1e-5:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.POP_CULTURE_SHIFT,
                        target_id=other_pop.id,
                        field=cv.culture_tag,
                        delta=delta,
                        note=f"{note_prefix} linked culture cascade to {other_pop.stratum} Pop",
                    ))

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
                # Enforce suspicious <= actual
                if state.essence.suspicious > state.essence.actual:
                    state.essence.suspicious = state.essence.actual
                # Laundering: spending actual Essence passively drains suspicious.
                # Fraction drained ≈ (suspicious / pre-spend actual) with mild noise.
                if (
                    m.field == "actual"
                    and (m.delta or 0) < 0
                    and state.essence.actual > 0.0
                    and state.essence.suspicious > 0.0
                ):
                    spend = abs(m.delta)
                    pre_spend_actual = state.essence.actual + spend  # actual before the deduction
                    ratio = state.essence.suspicious / pre_spend_actual
                    noise = self._rng.uniform(-0.15, 0.15)
                    drain = spend * ratio * (1.0 + noise)
                    drain = max(0.0, min(drain, state.essence.suspicious))
                    state.essence.suspicious = max(0.0, state.essence.suspicious - drain)

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
                        new_val = max(0.0, min(1.0, current + (m.delta or 0)))
                        setattr(state.civilizations[tid], parts[0], new_val)

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
                    delta = (m.delta or 0.0) * belief_inertia(current, m.delta or 0.0)
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
                    if mortal.visibility_stall_remaining < VISIBILITY_STALL_ON_CAP:
                        mortal.visibility_stall_remaining = VISIBILITY_STALL_ON_CAP
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
                    mortal_ref = state.mortals[tid]
                    if m.new_value is not None:
                        mortal_ref.visibility = max(0.0, min(1.0, float(m.new_value)))
                    elif m.delta is not None:
                        mortal_ref.visibility = max(0.0, min(1.0, mortal_ref.visibility + m.delta))
                    if mortal_ref.visibility >= 1.0:
                        mortal_ref.visibility_stall_remaining = max(
                            mortal_ref.visibility_stall_remaining, VISIBILITY_STALL_ON_CAP
                        )

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
                    if entity.visibility >= 1.0 and hasattr(entity, "visibility_stall_remaining"):
                        entity.visibility_stall_remaining = max(
                            entity.visibility_stall_remaining, VISIBILITY_STALL_ON_CAP
                        )

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

            elif m.mutation_type == MutationType.CLEAR_PENDING_SLOT:
                state.pending_actions.pop(m.field, None)

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
                    delta = (m.delta or 0.0) * belief_inertia(current, m.delta or 0.0)
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
                    delta = (m.delta or 0.0) * belief_inertia(current, m.delta or 0.0)
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
                if tid and tid in state.mortals and tag and m.delta is not None:
                    culture = state.mortals[tid].culture_tags
                    current = culture.get(tag, 0.0)
                    _s = tag.startswith(("values:", "practice:"))
                    delta = m.delta * belief_inertia(abs(current) if _s else current, m.delta)
                    if tag.startswith("values:"):
                        delta *= max(0.05, 1.0 - state.config.values_stubbornness_factor)
                    if _s:
                        new_strength = max(-1.0, min(1.0, current + delta))
                    else:
                        cap = BELIEF_CAP if delta > 0 else 1.0
                        new_strength = max(0.0, min(cap, current + delta))
                    if abs(new_strength) > 1e-5:
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
                    if pop.visibility >= 1.0:
                        pop.visibility_stall_remaining = max(
                            pop.visibility_stall_remaining, VISIBILITY_STALL_ON_CAP
                        )

            elif m.mutation_type == MutationType.CIV_ESTABLISHED_SHIFT:
                tag = str(m.new_value) if m.new_value else m.field
                if tid and tid in state.civilizations and tag:
                    established = state.civilizations[tid].established_beliefs
                    current = established.get(tag, 0.0)
                    delta = (m.delta or 0.0) * belief_inertia(current, m.delta or 0.0)
                    cap = BELIEF_CAP if delta > 0 else 1.0
                    new_strength = max(0.0, min(cap, current + delta))
                    if new_strength > BELIEF_FLOOR:
                        established[tag] = new_strength
                    elif tag in established:
                        del established[tag]

            elif m.mutation_type == MutationType.CIV_ESTABLISHED_CULTURE_SHIFT:
                tag = str(m.new_value) if m.new_value else m.field
                if tid and tid in state.civilizations and tag and m.delta is not None:
                    est_cult = state.civilizations[tid].established_culture_tags
                    current = est_cult.get(tag, 0.0)
                    _s = tag.startswith(("values:", "practice:"))
                    delta = m.delta * belief_inertia(abs(current) if _s else current, m.delta)
                    if tag.startswith("values:"):
                        delta *= max(0.05, 1.0 - state.config.values_stubbornness_factor)
                    if _s:
                        new_strength = max(-1.0, min(1.0, current + delta))
                    else:
                        cap = BELIEF_CAP if delta > 0 else 1.0
                        new_strength = max(0.0, min(cap, current + delta))
                    if abs(new_strength) > CULTURE_FLOOR:
                        est_cult[tag] = new_strength
                    elif tag in est_cult:
                        del est_cult[tag]

            elif m.mutation_type == MutationType.POP_SPLINTER:
                # m.target_id = parent Pop UUID; m.new_value = splinter Pop object
                parent_pop = state.pops.get(tid) if tid else None
                splinter: "Pop" = m.new_value  # type: ignore[assignment]
                if parent_pop is not None and splinter is not None:
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
                    _s = tag.startswith(("values:", "practice:"))
                    delta = m.delta * belief_inertia(abs(current) if _s else current, m.delta)
                    if tag.startswith("values:"):
                        delta *= max(0.05, 1.0 - state.config.values_stubbornness_factor)
                    if _s:
                        new_val = max(-1.0, min(1.0, current + delta))
                    else:
                        cap = BELIEF_CAP if delta > 0 else 1.0
                        new_val = max(0.0, min(cap, current + delta))
                    # Sub-floor accumulation (lever C, culture variant): allow
                    # entries to persist below CULTURE_FLOOR within a tick so
                    # repeated splashes can compound. `_prune_weak_beliefs`
                    # clears entries still under floor at the next passive phase.
                    if abs(new_val) > 1e-5:
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
                    # End goal target status on Pop B; unpin; start cooldown (only if preaching was active)
                    if pop_b.preaching_imago_id is not None:
                        pop_b.preaching_imago_id = None
                        pop_b.pinned = False
                        pop_b.preaching_goal_cooldown_until = state.tick_number + 10

        return state
