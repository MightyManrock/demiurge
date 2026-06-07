from __future__ import annotations
import math
import random
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.universe_core import NotableMortal
    from core.agent_core import MortalAgentState, KnowledgeBase
    from logic.tick_logic import SimulationState

from logic.needs_config import DESIRE_ACCUMULATION, DESIRE_EXPLORATION, DESIRE_EXPRESSION

FATIGUE_BLOCK_THRESHOLD = 0.85

LEISURE_BASE_GAIN             = 0.35
SOCIALIZE_BASE_GAIN           = 0.30
LEISURE_SATIATION_HOLD_BASE   = 6
SOCIALIZE_SATIATION_HOLD_BASE = 5

# Ambient gain applied to leisure/socialize when not pressing but mortal is in transit with crew.
# Lower than base so ambient social play only wins over idle, never over commerce.
LEISURE_AMBIENT_GAIN   = 0.20
SOCIALIZE_AMBIENT_GAIN = 0.15

# Score multiplier applied to sell/collect when a commerce directive is active
DIRECTIVE_MULTIPLIER = 2.0

# Needs whose urgency can block travel (physical survival only).
# Social/purpose needs being low should not ground a mortal mid-route.
_TRAVEL_BLOCKING_NEEDS: frozenset[str] = frozenset({"nourishment", "hydration", "safety"})

# Score and gain multiplier for leisure while in transit with a crew pop.
# Leisure (culture, entertainment) is diminished on a working ship; socializing is not.
CREW_LEISURE_MULTIPLIER = 0.10

# Exponent applied to ticks_cost in travel scoring: 1.0 = linear (harsh); 0.5 = square root
# (gentler — a 12-tick trip divides benefit by ~3.5 instead of 12).
TRAVEL_DIST_EXPONENT = 0.5

# Desire score weights (desire urgency multipliers for action scoring)
ACCUMULATION_SELL_WEIGHT    = 0.6   # desire boost on sell score
ACCUMULATION_COLLECT_WEIGHT = 0.4   # desire boost on collect score (scaled by empty hold)
EXPRESSION_LEISURE_WEIGHT   = 0.35  # desire boost on leisure when practice quality > 0.5

# Social novelty constants (tunable)
SOCIAL_NOVELTY_FLOOR         = 0.40   # min fraction of belonging gain from a fully familiar Pop
NOVELTY_HALFLIFE             = 20     # interactions until novelty reaches ~50%
RECENCY_RECOVERY_TICKS       = 50     # ticks of absence to recover 50% novelty
EXPLORATION_NOVELTY_THRESHOLD = 0.50  # novelty above this grants Exploration satisfaction

# "Might as well" factor: per-tick probability that a mortal with an active directive
# and no pressing needs decides to run their route anyway.
# Culture tags modulate this probability additively (tag_weight * modifier).
MIGHT_AS_WELL_BASE_PROB   = 0.15
MIGHT_AS_WELL_COLLECT_BASE = 0.15   # collect-score baseline injected on a successful roll

_MIGHT_AS_WELL_CULTURE_MODS: dict[str, float] = {
    "values:tenacity":   +0.15,
    "values:prowess":    +0.15,
    "values:prosperity": +0.10,
    "values:pragmatism": +0.10,
    "values:indulgence": -0.10,
    "values:moderation": -0.05,
}


def _might_as_well_prob(culture_tags: dict[str, float]) -> float:
    mod = sum(culture_tags.get(t, 0.0) * w for t, w in _MIGHT_AS_WELL_CULTURE_MODS.items())
    return max(0.05, min(0.60, MIGHT_AS_WELL_BASE_PROB + mod))


def _need_urgency(need) -> float:
    """Continuous urgency in [0, ~1.5]. Zero when not pressing or held satisfied."""
    if need.satiation_hold > 0 or need.satisfaction >= need.pressing_threshold:
        return 0.0
    base = 1.0 - need.satisfaction / need.pressing_threshold
    if need.is_urgent:
        base = min(1.5, base * 1.5)
    return base



def _cosine_sim(a: dict[str, float], b: dict[str, float]) -> float:
    """Cosine similarity between two float-valued tag vectors, normalized to [0, 1].

    Returns 0.5 (neutral) if either vector is empty or zero-magnitude.
    Maps raw cosine [-1, 1] to [0, 1] via (raw + 1) / 2.
    """
    if not a or not b:
        return 0.5
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0.0) * b.get(k, 0.0) for k in keys)
    mag_a = sum(v * v for v in a.values()) ** 0.5
    mag_b = sum(v * v for v in b.values()) ** 0.5
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.5
    raw = dot / (mag_a * mag_b)
    return max(0.0, min(1.0, (raw + 1.0) / 2.0))

def _pop_practice_quality(mortal_tags: dict[str, float], pop_tags: dict[str, float]) -> float:
    """Weighted leisure quality: mortal preference × pop practice level, normalized to [0, 1]."""
    EXCLUDED = {"practice:ritual", "practice:revelry"}
    total_weight = total = 0.0
    for tag, pop_val in pop_tags.items():
        if not tag.startswith("practice:") or tag in EXCLUDED:
            continue
        mortal_pref = max(0.0, mortal_tags.get(tag, 0.2))
        total_weight += mortal_pref
        total += mortal_pref * pop_val
    if total_weight == 0:
        return 0.3
    return min(1.0, total / total_weight)


# ── Social quality constants (tunable) ───────────────────────────────────────
_CROSS_SPECIES_BASE = 0.80
_CROSS_CIV_BASE = 0.70
_CROSS_SPECIES_XENO_NEUTRAL = 0.30
_CROSS_CIV_XENO_NEUTRAL = 0.40
_CROSS_MAX_BONUS = 0.20
_NEG_XENO_MIN = 0.30
_SOLIDARITY_BONUS_WEIGHT = 0.15
_REVELRY_BONUS_WEIGHT = 0.15


def _cross_factor(base: float, xeno_neutral: float, xeno: float) -> float:
    """Compatibility multiplier for a cross-group barrier (species or civ).

    base: factor at xeno=0 (e.g. 0.80 → 20% penalty)
    xeno_neutral: xenophilia value where factor reaches 1.0 (no penalty)
    xeno: mortal's values:xenophilia in [-1, 1]
    """
    if xeno < 0.0:
        return max(_NEG_XENO_MIN, base + xeno * (1.0 - base))
    elif xeno <= xeno_neutral:
        return base + (1.0 - base) * (xeno / xeno_neutral)
    else:
        excess = (xeno - xeno_neutral) / max(0.001, 1.0 - xeno_neutral)
        return min(1.0 + _CROSS_MAX_BONUS, 1.0 + _CROSS_MAX_BONUS * excess)


def _pop_social_quality(
    mortal_beliefs: dict[str, float],
    mortal_culture: dict[str, float],
    pop_beliefs: dict[str, float],
    pop_culture: dict[str, float],
    same_species: bool = True,
    same_civ: bool = True,
) -> float:
    """Belonging quality score [0, 1] for a mortal socialising with a pop.

    Drives the 'belonging' need. Components:
    - Cosine similarity of beliefs + non-practice culture (xenophilia-modulated)
    - Cross-species and cross-civ penalties (weighted more heavily by xenophilia)
    - Small additive bonus from pop solidarity and revelry
    """
    xeno = mortal_culture.get("values:xenophilia", 0.0)

    def _profile(beliefs: dict, culture: dict) -> dict:
        v = dict(beliefs)
        v.update({t: val for t, val in culture.items() if not t.startswith("practice:")})
        return v

    sim = _cosine_sim(_profile(mortal_beliefs, mortal_culture), _profile(pop_beliefs, pop_culture))

    if 0.0 < xeno <= 0.5:
        adj_sim = sim + (0.5 - sim) * (xeno / 0.5)
    elif xeno > 0.5:
        adj_sim = 0.5 + (0.5 - sim) * ((xeno - 0.5) / 0.5)
    else:
        adj_sim = sim

    species_f = _cross_factor(_CROSS_SPECIES_BASE, _CROSS_SPECIES_XENO_NEUTRAL, xeno) if not same_species else 1.0
    civ_f = _cross_factor(_CROSS_CIV_BASE, _CROSS_CIV_XENO_NEUTRAL, xeno) if not same_civ else 1.0
    neg_f = max(_NEG_XENO_MIN, 1.0 + xeno * (1.0 - _NEG_XENO_MIN)) if xeno < 0.0 else 1.0

    base = adj_sim * species_f * civ_f * neg_f
    solidarity = pop_culture.get("values:solidarity", 0.3) * _SOLIDARITY_BONUS_WEIGHT
    revelry = pop_culture.get("practice:revelry", 0.3) * _REVELRY_BONUS_WEIGHT
    return min(1.0, max(0.0, base + solidarity + revelry))


_TRADE_QUALITY_WEIGHT = 0.30  # max bonus contribution from practice:trade pops


def _pop_novelty(pop_fact, current_tick: int) -> float:
    """Novelty in [0, 1]: 1.0 for an unknown Pop, decays with interaction_count,
    partially recovers with time since last interaction."""
    if pop_fact is None:
        return 1.0
    familiarity = pop_fact.interaction_count / (pop_fact.interaction_count + NOVELTY_HALFLIFE)
    base = 1.0 - familiarity
    if pop_fact.last_interaction_tick > 0:
        ticks_since = max(0, current_tick - pop_fact.last_interaction_tick)
        recency = min(1.0, ticks_since / RECENCY_RECOVERY_TICKS)
        return max(base, recency)
    return base


def _effective_commerce_quality(loc, state) -> float:
    """Authored commerce_quality + size-weighted pop practice:trade contribution."""
    base = getattr(loc, "commerce_quality", 0.5)
    pop_ids = getattr(loc, "pop_ids", [])
    if not pop_ids:
        return base
    pops = [state.pops[str(pid)] for pid in pop_ids if str(pid) in state.pops]
    if not pops:
        return base
    total_size = sum(p.size_fractional for p in pops)
    if total_size == 0.0:
        return base
    trade_activity = sum(
        p.culture_tags.get("practice:trade", 0.0) * p.size_fractional for p in pops
    ) / total_size
    return min(1.0, base + trade_activity * _TRADE_QUALITY_WEIGHT)


def _select_local_pop(mortal, state) -> Optional[str]:
    """Return pop_id of the best pop at mortal's location for pressing social needs,
    or None if no social needs are pressing or no pops are co-located.
    Used by tick_logic for zero-cost milieu switching."""
    cs = mortal.mortal_state
    if cs is None:
        return None
    leisure_pressing  = (n := cs.get_need("leisure"))  is not None and n.is_pressing
    belonging_pressing = (n := cs.get_need("belonging")) is not None and n.is_pressing
    if not leisure_pressing and not belonging_pressing:
        return None
    cur_loc_str = str(mortal.current_location)
    local_pops = [(pid, p) for pid, p in state.pops.items()
                  if str(p.current_location) == cur_loc_str]
    if not local_pops:
        return None
    _mortal_home_pop = state.pops.get(str(mortal.pop_milieu or mortal.pop_id or ""))
    _mortal_civ = str(_mortal_home_pop.civilization_id) if _mortal_home_pop and _mortal_home_pop.civilization_id else None

    def _score(item: tuple) -> float:
        _, pop = item
        s = 0.0
        if leisure_pressing:
            s += _pop_practice_quality(mortal.culture_tags, pop.culture_tags)
        if belonging_pressing:
            _same_species = (str(mortal.species_id) == str(pop.species_id)) if (mortal.species_id and pop.species_id) else True
            _same_civ = (_mortal_civ == str(pop.civilization_id)) if (_mortal_civ and pop.civilization_id) else True
            s += _pop_social_quality(
                mortal.belief_tags, mortal.culture_tags,
                pop.dominant_beliefs, pop.culture_tags,
                same_species=_same_species,
                same_civ=_same_civ,
            )
        return s
    best_pid, _ = max(local_pops, key=_score)
    return best_pid


def _mortal_is_travelling(mortal, state) -> bool:
    if mortal.travel_intent is not None:
        return True
    loc = state.locations.get(str(mortal.current_location))
    return loc is not None and getattr(loc, "location_type", None) == "travel_location"


def _select_best_route(routes, mortal_state):
    """Select the best TravelRoute for this mortal from a list of candidates.
    Filters routes whose resource costs the mortal can't afford or that would
    drain a survival need to zero. Returns the highest-scoring route or None.
    """
    best = None
    best_score = 0.0
    for route in routes:
        if not route.resource_costs:
            score = 1.0 / max(1, route.total_ticks)
        else:
            # Check affordability: mortal must have enough of each consumed resource
            can_afford = True
            if mortal_state is not None:
                inventory = {r.resource_type: r.quantity for r in mortal_state.inventory}
                for rc in route.resource_costs:
                    if rc.consumed and inventory.get(rc.resource_type, 0.0) < rc.amount:
                        can_afford = False
                        break
                    # Check survival needs won't be drained to zero
                    need_obj = next(
                        (n for n in mortal_state.needs if n.fills_need == rc.resource_type),
                        None,
                    )
                    if need_obj and rc.consumed:
                        remaining = inventory.get(rc.resource_type, 0.0) - rc.amount
                        if remaining <= 0 and need_obj.name in _TRAVEL_BLOCKING_NEEDS:
                            can_afford = False
                            break
            if not can_afford:
                continue
            score = 1.0 / max(1, route.total_ticks)
        if score > best_score:
            best_score = score
            best = route
    return best


def _trip_too_long_for_urgent_need(cs, kb, dest_id: str) -> bool:
    """Return True if any survival need will reach 0 before the trip completes.
    Only nourishment, hydration, and safety can ground a mortal — social/purpose urgency does not."""
    ticks_cost = kb.route_ticks_to(dest_id)
    if ticks_cost == 0:
        return False
    for need in cs.needs:
        if need.name not in _TRAVEL_BLOCKING_NEEDS:
            continue
        if need.is_urgent and need.decay_rate > 0:
            ticks_until_desperate = need.satisfaction / need.decay_rate
            if ticks_cost > ticks_until_desperate:
                return True
    return False


def _begin_loading(cs, cur_loc, cargo_cap: Optional[float], cargo_load: float) -> None:
    """Set collecting_ticks_remaining for a multi-tick load session.
    Duration = ceil(remaining_capacity / resource_yield) - 1 (this tick is tick 0).
    Only applied when cargo capacity is known and resource yield is a real number."""
    if cargo_cap is None or cur_loc is None:
        return
    crs = getattr(cur_loc, "collectible_resources", [])
    cr = next(
        (c for c in crs
         if (not c.action_types or "collect" in c.action_types) and c.current_yield > 0),
        None,
    )
    if cr is None:
        return
    yield_per_tick = cr.max_yield * 0.15
    if yield_per_tick <= 0:
        return
    remaining = max(0.0, cargo_cap - cargo_load)
    additional_ticks = max(0, math.ceil(remaining / yield_per_tick) - 1)
    cs.collecting_ticks_remaining = additional_ticks


def _has_skill(mortal: Any, skill_name: str) -> bool:
    """True if mortal can attempt skill-gated actions for `skill_name`.

    Empty skill_tags means the skill system isn't engaged for this mortal
    (legacy / pre-skill entities). Non-empty skill_tags means the mortal is
    in the skill system and must hold the skill explicitly.
    """
    tags = getattr(mortal, "skill_tags", {}) or {}
    if not tags:
        return True  # legacy: ungated
    return skill_name in tags


def _skill_rating(mortal: Any, skill_name: str) -> float:
    """Skill rating in [0, 1]. Returns 1.0 for legacy (empty skill_tags) mortals.
    Returns 0.0 if skill system is engaged but the skill is absent.
    """
    tags = getattr(mortal, "skill_tags", {}) or {}
    if not tags:
        return 1.0  # legacy: full effectiveness
    return tags.get(skill_name, 0.0)


def evaluate_mortal_action(
    mortal,
    state,
    current_tick: int,
) -> Optional[str]:
    """
    Returns one of: "collect", "sell", "spend", "leisure", "socialize",
    "travel:<location_id>", "idle", None.
    None means the mortal has no mortal_state and should be skipped.

    Actions are scored by Σ(need_urgency × expected_gain). Sell and collect
    carry a "follow-through" component from cargo load fraction: a loaded hold
    creates sell pressure; an empty hold creates collect pressure. Directive-
    aligned actions receive DIRECTIVE_MULTIPLIER. Travel is scored as
    (best_score_at_dest − best_local_score) / ticks_cost, and only beats local
    options when the destination advantage outweighs the journey cost.
    """
    cs = mortal.mortal_state
    kb = mortal.knowledge_base
    if cs is None or kb is None:
        return None

    _travelling = _mortal_is_travelling(mortal, state)
    _in_transit_with_crew = False
    if _travelling:
        _milieu_id = str(mortal.pop_milieu) if mortal.pop_milieu is not None else ""
        _milieu_pop = state.pops.get(_milieu_id)
        _in_transit_with_crew = (
            _milieu_pop is not None
            and getattr(_milieu_pop, "asset_crew_for", None) is not None
        )
        if not _in_transit_with_crew:
            return "idle"

    if mortal.fatigue >= FATIGUE_BLOCK_THRESHOLD:
        return "idle"

    # While actively loading cargo the freighter is docked — handle personal time only.
    # pending_travel_dest waits until loading is done; it commits on the next free tick.
    _docked = cs.collecting_ticks_remaining > 0

    # Sticky collect-then-travel: commit unconditionally on the first free tick after loading
    if not _docked and cs.pending_travel_dest:
        dest = cs.pending_travel_dest
        cs.pending_travel_dest = None
        return f"travel:{dest}"

    current_loc_id = str(mortal.current_location)

    # ── Cargo state ──────────────────────────────────────────────────────────
    _cargo_cap = next(
        (a.cargo_capacity for a in mortal.assets if a.cargo_capacity is not None),
        None,
    )
    _cargo_load = sum(r.quantity for r in cs.inventory if "sell" in r.usable_for)
    _hold_full = _cargo_cap is not None and _cargo_load >= _cargo_cap

    _sell_threshold = _cargo_cap  # None → fall back to Resource.threshold
    _sellable = next(
        (r for r in cs.inventory
         if "sell" in r.usable_for
         and r.quantity >= (_sell_threshold if _sell_threshold is not None else r.threshold)),
        None,
    )

    _directive_active = bool(kb.directive_facts())
    _purpose_pressing = any(n.name == "purpose" and n.is_pressing for n in cs.needs)
    _might_as_well = (
        _directive_active and not _purpose_pressing
        and random.random() < _might_as_well_prob(getattr(mortal, "culture_tags", {}))
    )
    _directive_work_pending = (
        _directive_active and not _hold_full
        and (_purpose_pressing or _might_as_well)
    )

    # Gate: idle when nothing is pressing — UNLESS mortal has a full hold to sell
    # or a directive with pending work (purpose pressing, or "might as well" roll succeeded),
    # or any desire is pressing (so wander can be scored).
    _any_desire_pressing = any(d.is_pressing for d in cs.desires)
    if not cs.pressing_needs() and not _in_transit_with_crew and _sellable is None and not _directive_work_pending and not _any_desire_pressing:
        return "idle"
    # Load fraction: ratio when capacity is known; sigmoid (L/(L+1)) otherwise.
    # The sigmoid never reaches 1.0, so uncapped mortals always have some collect score
    # alongside sell pressure — they don't get stuck choosing only one direction.
    _load_fraction = (
        (_cargo_load / _cargo_cap) if _cargo_cap is not None
        else (_cargo_load / (_cargo_load + 1.0))
    )

    _spendable = next(
        (r for r in cs.inventory
         if "spend" in r.usable_for
         and r.quantity >= r.threshold
         and (r.fills_need is None
              or any(n.name == r.fills_need and n.is_pressing for n in cs.needs))),
        None,
    )

    _cur_loc = state.locations.get(current_loc_id)
    _at_resource = (
        _cur_loc is not None
        and any(
            (not c.action_types or "collect" in c.action_types) and c.current_yield > 0
            for c in getattr(_cur_loc, "collectible_resources", [])
        )
        and current_loc_id in kb.known_resource_locations()
    )

    _local_pop_id = str(mortal.pop_milieu or mortal.pop_id or "")
    _local_pop = state.pops.get(_local_pop_id) if _local_pop_id else None

    # Need urgency map
    urgency = {n.name: _need_urgency(n) for n in cs.needs}
    _desire_u = {d.name: d.urgency() for d in cs.desires}

    _best_sell_loc  = kb.best_known_sell_location()  if _sellable  else None
    _best_spend_loc = kb.best_known_spend_location() if _spendable else None

    # ── Action scores ─────────────────────────────────────────────────────────

    # Sell: follow-through from loaded hold + purpose + status urgency + accumulation desire
    _sell_score = (
        _load_fraction
        + urgency.get("purpose", 0.0) * 1.0
        + urgency.get("status",  0.0) * 0.5
        + _desire_u.get(DESIRE_ACCUMULATION, 0.0) * ACCUMULATION_SELL_WEIGHT
    ) if _sellable else 0.0
    if _directive_active and _sell_score > 0:
        _sell_score *= DIRECTIVE_MULTIPLIER
    if _sell_score > 0:
        _sell_score *= _skill_rating(mortal, "skill:trade") if _has_skill(mortal, "skill:trade") else 0.0

    # Collect: purpose urgency drives it; a small baseline fires on a "might as well" roll.
    # Accumulation desire also lifts the base score even without purpose pressure.
    _directive_base = MIGHT_AS_WELL_COLLECT_BASE if _might_as_well else 0.0
    _collect_base = max(urgency.get("purpose", 0.0), _directive_base, _desire_u.get(DESIRE_ACCUMULATION, 0.0) * ACCUMULATION_COLLECT_WEIGHT)
    _collect_score = (
        (1.0 - _load_fraction) * _collect_base
    ) if not _hold_full else 0.0
    if _directive_active and _collect_score > 0:
        _collect_score *= DIRECTIVE_MULTIPLIER
    if _collect_score > 0:
        _collect_score *= _skill_rating(mortal, "skill:trade") if _has_skill(mortal, "skill:trade") else 0.0

    # Spend: direct need fill (or generic QoL boost when fills_need is unset)
    if _spendable:
        _spend_score = (
            urgency.get(_spendable.fills_need, 0.0) if _spendable.fills_need
            else sum(urgency.values()) * 0.3
        )
    else:
        _spend_score = 0.0

    # Leisure: urgency-based score (pressing) or ambient score (in transit with crew, not full).
    # Zeroed out if the expected gain would be less than the per-tick decay — not worth doing.
    _leisure_u = urgency.get("leisure", 0.0)
    _expr_u = _desire_u.get(DESIRE_EXPRESSION, 0.0)
    if _local_pop is not None and (_leisure_u > 0 or _in_transit_with_crew):
        mortal_tags = getattr(mortal, "culture_tags", {}) or {}
        _pq = _pop_practice_quality(mortal_tags, _local_pop.culture_tags)
        _crew_mult_lei = CREW_LEISURE_MULTIPLIER if _in_transit_with_crew else 1.0
        _l_need = cs.get_need("leisure")
        _l_sat = _l_need.satisfaction if _l_need else 1.0
        if _leisure_u > 0:
            _lei_gain = LEISURE_BASE_GAIN * _pq * _crew_mult_lei
            _leisure_score = _leisure_u * _lei_gain
            if _expr_u > 0 and _pq > 0.5:
                _leisure_score += _expr_u * (_pq - 0.5) * EXPRESSION_LEISURE_WEIGHT
        else:
            _lei_gain = max(0.0, 1.0 - _l_sat) * LEISURE_AMBIENT_GAIN * _pq * _crew_mult_lei
            _leisure_score = _lei_gain
        if _l_need and _lei_gain < _l_need.decay_rate:
            _leisure_score = 0.0
    elif _local_pop is not None and _expr_u > 0:
        # Expression desire drives leisure independently of the leisure need
        mortal_tags = getattr(mortal, "culture_tags", {}) or {}
        _pq = _pop_practice_quality(mortal_tags, _local_pop.culture_tags)
        _leisure_score = _expr_u * (_pq - 0.5) * EXPRESSION_LEISURE_WEIGHT if _pq > 0.5 else 0.0
    else:
        _leisure_score = 0.0

    # Socialize: urgency-based score (pressing) or ambient score (in transit with crew, not full)
    # No multiplier for crew transit — socializing with your crew is genuinely fulfilling.
    _belonging_u = urgency.get("belonging", 0.0)
    if _local_pop is not None and (_belonging_u > 0 or _in_transit_with_crew):
        _sq = _pop_social_quality(
            mortal.belief_tags, mortal.culture_tags,
            _local_pop.dominant_beliefs, _local_pop.culture_tags,
            same_species=(str(mortal.species_id) == str(_local_pop.species_id)) if (mortal.species_id and _local_pop.species_id) else True,
            same_civ=True,  # mortal socialises with their milieu pop — treat as same-civ
        )
        if _belonging_u > 0:
            _socialize_score = _belonging_u * SOCIALIZE_BASE_GAIN * _sq
        else:
            _b_need = cs.get_need("belonging")
            _b_sat = _b_need.satisfaction if _b_need else 1.0
            _socialize_score = max(0.0, 1.0 - _b_sat) * SOCIALIZE_AMBIENT_GAIN * _sq
        # Apply novelty weighting: familiar Pops yield less belonging gain
        _pop_fact = kb.get_pop_fact(_local_pop_id) if kb else None
        _novelty = _pop_novelty(_pop_fact, current_tick)
        _novelty_factor = SOCIAL_NOVELTY_FLOOR + _novelty * (1.0 - SOCIAL_NOVELTY_FLOOR)
        _socialize_score *= _novelty_factor
    else:
        _socialize_score = 0.0

    # ── Local candidates ──────────────────────────────────────────────────────
    local_candidates: dict[str, float] = {}
    if _best_sell_loc  and current_loc_id == _best_sell_loc  and _sell_score    > 0:
        local_candidates["sell"]      = _sell_score
    # Collect and travel are unavailable while the freighter is docked for loading
    if not _docked and _at_resource and not _hold_full and _collect_score > 0:
        local_candidates["collect"]   = _collect_score
    if _best_spend_loc and current_loc_id == _best_spend_loc and _spend_score   > 0:
        local_candidates["spend"]     = _spend_score
    if _leisure_score  > 0:
        local_candidates["leisure"]   = _leisure_score
    if _socialize_score > 0:
        local_candidates["socialize"] = _socialize_score

    _best_local = max(local_candidates.values()) if local_candidates else 0.0

    # ── Travel candidates: score = (dest_score − best_local) / ticks_cost ────
    travel_candidates: dict[str, float] = {}

    if not _docked and not _travelling and mortal.travel_intent is None:
        def _try_travel(dest_id: str, dest_score: float) -> None:
            if dest_id == current_loc_id or dest_score <= _best_local:
                return
            route = kb.route_to(dest_id)
            can_travel = not (route and route.vehicle_type) or any(
                a.asset_type == route.vehicle_type for a in mortal.assets
            )
            if not can_travel or _trip_too_long_for_urgent_need(cs, kb, dest_id):
                return
            ticks = route.ticks_cost if route else 1
            _ctags = getattr(mortal, "culture_tags", None)
            sedentism = _ctags.get("values:sedentism", 0.0) if isinstance(_ctags, dict) else 0.0
            sedentism_bonus = max(1.0, 1.0 - sedentism * 0.5)
            score = (dest_score - _best_local) / max(1.0, ticks ** TRAVEL_DIST_EXPONENT) * sedentism_bonus
            if score > 0:
                travel_candidates[dest_id] = max(travel_candidates.get(dest_id, 0.0), score)

        if _best_sell_loc:
            _try_travel(_best_sell_loc, _sell_score)
        if not _hold_full:
            for res_loc in kb.known_resource_locations():
                _try_travel(res_loc, _collect_score)
        if _best_spend_loc:
            _try_travel(_best_spend_loc, _spend_score)

    # ── Pick best action ──────────────────────────────────────────────────────
    all_candidates: dict[str, float] = dict(local_candidates)
    for dest, score in travel_candidates.items():
        all_candidates[f"travel:{dest}"] = score

    # ── Wander: Exploration desire drives travel to unvisited locations ────────
    _exploration_u = _desire_u.get(DESIRE_EXPLORATION, 0.0)
    if _exploration_u > 0 and not _docked and not _travelling and mortal.travel_intent is None and not cs.pressing_needs():
        _kb_locations = [f for f in kb.facts if f.fact_type == "location"]
        for loc_fact in _kb_locations:
            dest_id = loc_fact.location_id
            if dest_id == current_loc_id:
                continue
            if loc_fact.visit_count > 0:
                continue
            # Only wander to reachable locations
            route = kb.route_to(dest_id)
            can_travel = not (route and route.vehicle_type) or any(
                a.asset_type == route.vehicle_type for a in mortal.assets
            )
            if not can_travel:
                continue
            if _trip_too_long_for_urgent_need(cs, kb, dest_id):
                continue
            ticks = route.ticks_cost if route else 1
            _wander_score = _exploration_u / max(1.0, ticks ** TRAVEL_DIST_EXPONENT)
            if _wander_score > 0:
                wander_key = f"wander:{dest_id}"
                all_candidates[wander_key] = max(all_candidates.get(wander_key, 0.0), _wander_score)

    if not all_candidates:
        return "idle"

    best_action = max(all_candidates, key=all_candidates.__getitem__)

    if all_candidates[best_action] <= 0:
        return "idle"

    # Sticky intercept: if travel wins but mortal is at a resource with cargo room,
    # start a loading session and lock in the destination.
    if best_action.startswith("travel:") and _at_resource and not _hold_full and _collect_score > 0:
        cs.pending_travel_dest = best_action[len("travel:"):]
        _begin_loading(cs, _cur_loc, _cargo_cap, _cargo_load)
        return "collect"

    if best_action == "collect":
        _begin_loading(cs, _cur_loc, _cargo_cap, _cargo_load)

    return best_action
