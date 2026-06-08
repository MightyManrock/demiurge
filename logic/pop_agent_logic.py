from __future__ import annotations
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.universe_core import Pop, PopLocation, Faction

from core.agent_core import PopAgentState, PopNeed, ResourceStockpile, can_access_stockpile

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

POP_FOOD_RESOURCE_TYPES = ("food_flora", "food_fauna")
NEED_FILL_RATE = 0.08
SUSTENANCE_CONSUME_RATE = 0.05  # kept for back-compat; superseded by split rates below

NOURISHMENT_CONSUME_RATE = 0.05
HYDRATION_CONSUME_RATE   = 0.05
NOURISHMENT_FILL_RATE    = 0.08
HYDRATION_FILL_RATE      = 0.08
BASE_FORAGE_YIELD        = 0.1   # fallback when no matching collectible_resource

# Resource types → biochem categories for consumption pass
_RESOURCE_BIOCHEM: dict[str, str] = {
    "food_flora":            "basis",
    "food_fauna":            "basis",
    "silicate_flora":        "basis",
    "silicate_fauna":        "basis",
    "methane_flora":         "basis",
    "methane_fauna":         "basis",
    "potable_water":         "solvent",
    "potable_sulfuric_acid": "solvent",
    "potable_ammonia":       "solvent",
    "potable_methane_liq":   "solvent",
}

ACTION_NEED_MAP: dict[str, str] = {
    "forage":        "nourishment",
    "hunt":          "nourishment",
    "collect":       "nourishment",
    "commune":       "cohesion",
    "revel":         "cohesion",
    "enact_rituals": "purpose",
    "build":         "shelter",
    "fortify":       "safety",
    "migrate":       "wanderlust",
    "raid":          "safety",
    "fight":         "safety",
    "rout":          "safety",
}

ALL_ACTIONS: list[str] = list(ACTION_NEED_MAP.keys())
STUB_ACTIONS: frozenset[str] = frozenset({"raid", "fight", "rout"})

_COMPETENCY: dict[str, dict[str, float]] = {
    "wild":       {"forage": 1.5, "hunt": 1.5, "collect": 1.2, "migrate": 1.3},
    "feral":      {"forage": 1.4, "hunt": 1.4, "migrate": 1.2},
    "underclass": {"forage": 1.2},
    "common":     {"forage": 1.3, "hunt": 1.2, "collect": 1.2},
    "artisan":    {"build": 1.5, "fortify": 1.2},
    "trader":     {"collect": 1.3},
    "warrior":    {"fortify": 1.5},
    "scholar":    {"enact_rituals": 1.5, "commune": 1.2},
    "elite":      {"commune": 1.1, "enact_rituals": 1.1},
}

OCCUPATION_BASELINE_WEIGHTS: dict[str, dict[str, float]] = {
    "forager":      {"forage": 0.25, "hunt": 0.20, "migrate": 0.15},
    "raider":       {"hunt": 0.25,   "migrate": 0.20, "forage": 0.10},
    "outcast":      {"forage": 0.20, "migrate": 0.25, "hunt": 0.15},
    "criminal":     {"forage": 0.15, "migrate": 0.20, "hunt": 0.15},
    "bonded":       {"build": 0.20,  "forage": 0.15},
    "dispossessed": {"forage": 0.20, "migrate": 0.15},
    "producer":     {"forage": 0.20, "hunt": 0.15, "collect": 0.10},
    "laborer":      {"build": 0.20,  "forage": 0.10, "collect": 0.15},
    "service":      {"commune": 0.15, "collect": 0.10},
    "transport":    {"migrate": 0.20, "collect": 0.15},
    "professional": {"collect": 0.20, "commune": 0.10},
    "crafter":      {"build": 0.25,  "collect": 0.15},
    "builder":      {"build": 0.30,  "fortify": 0.15},
    "engineer":     {"build": 0.25,  "fortify": 0.20},
    "technician":   {"build": 0.20,  "fortify": 0.15},
    "healer":       {"commune": 0.20, "enact_rituals": 0.10},
    "artist":       {"revel": 0.20,  "commune": 0.15},
    "merchant":     {"collect": 0.30, "migrate": 0.15},
    "financier":    {"collect": 0.25, "commune": 0.10},
    "executive":    {"collect": 0.20, "commune": 0.15},
    "soldier":      {"fortify": 0.25, "hunt": 0.15},
    "officer":      {"fortify": 0.20, "commune": 0.10},
    "guard":        {"fortify": 0.25, "build": 0.10},
    "mercenary":    {"fortify": 0.20, "hunt": 0.20},
    "militia":      {"fortify": 0.20, "hunt": 0.10},
    "clergy":       {"enact_rituals": 0.30, "commune": 0.20},
    "scientist":    {"collect": 0.20, "commune": 0.15},
    "academic":     {"commune": 0.20, "enact_rituals": 0.15},
    "poli_admin":   {"commune": 0.20, "revel": 0.15},
    "noble":        {"revel": 0.25,  "commune": 0.15},
}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _public_stockpile(pop_loc) -> ResourceStockpile:
    """Return the public ResourceStockpile at this location, creating one if absent."""
    for s in pop_loc.stockpiles:
        if s.owner_faction_id is None and s.owner_band_id is None:
            return s
    s = ResourceStockpile()
    pop_loc.stockpiles.append(s)
    return s


def _find_matching_resources(collectible_resources: list, action: str) -> list:
    """Return CollectibleResources usable by this action (action_types=[] means any)."""
    return [
        cr for cr in collectible_resources
        if (not cr.action_types or action in cr.action_types)
        and cr.current_yield > 0
    ]

def _pop_need_urgency(need: PopNeed) -> float:
    """Continuous urgency in [0, ~1.5]. 0 when held; small background when satisfied; >1 when urgent."""
    if need.satiation_hold > 0:
        return 0.0
    if need.satisfaction >= need.pressing_threshold:
        span = max(1.0 - need.pressing_threshold, 0.01)
        return need.decay_rate * (1.0 - need.satisfaction) / span
    if need.satisfaction <= need.urgent_threshold:
        return 1.0 + (need.urgent_threshold - need.satisfaction) / max(need.urgent_threshold, 0.01) * 0.5
    span = need.pressing_threshold - need.urgent_threshold
    return (need.pressing_threshold - need.satisfaction) / max(span, 0.01)


def _pop_competency_modifier(pop, action: str) -> float:
    stratum = pop.stratum if pop.stratum else "common"
    mod = _COMPETENCY.get(stratum, {}).get(action)
    if mod is None:
        # For wild pops with a wild_stratum set, stratum returns the wild stratum value
        # (e.g., "apex", "herd", "carrion") which isn't in _COMPETENCY.
        # Fall back to the "wild" entry for wild competency bonuses.
        from core.universe_core import SocialStratum
        if getattr(pop, "social_class", None) == SocialStratum.WILD:
            mod = _COMPETENCY.get("wild", {}).get(action)
    return mod if mod is not None else 1.0


def _pop_spillover_factor(actor, neighbor, factions: dict) -> float:
    """Return the need-satisfaction spillover multiplier from actor to neighbor.

    Tiers:
      cross-factional (both in factions, no overlap) → 0.0
      co-factional (share ≥1 faction)               → max(link_factor, 0.75)
      linked only                                    → link_factor
      neither / one unfactioned                      → 0.5
    """
    from logic.sim_utils import compute_link_factor
    actor_fids    = {str(fid) for fid in actor.faction_ids}
    neighbor_fids = {str(fid) for fid in neighbor.faction_ids}
    shared_fids   = actor_fids & neighbor_fids

    if actor_fids and neighbor_fids and not shared_fids:
        return 0.0  # cross-factional rivals

    base = actor.linked_pop_ids.get(str(neighbor.id))
    lf   = compute_link_factor(actor, neighbor, base) if base is not None else None

    if shared_fids:
        return max(lf if lf is not None else 0.0, 0.75)

    if lf is not None:
        return lf

    return 0.5


# Civic actions whose effects spill over to co-located pops.
_CIVIC_ACTIONS: frozenset[str] = frozenset({"fortify", "build", "commune", "revel", "enact_rituals"})


def _apply_spillover(actor, colocated_pops: list, need_name: str, gain: float, factions: dict) -> None:
    """Apply a fraction of `gain` to `need_name` on each co-located pop."""
    for neighbor in colocated_pops:
        if neighbor.pop_state is None:
            continue
        factor = _pop_spillover_factor(actor, neighbor, factions)
        if factor <= 0.0:
            continue
        nb_need = next((n for n in neighbor.pop_state.needs if n.name == need_name), None)
        if nb_need is not None:
            nb_need.satisfaction = min(1.0, nb_need.satisfaction + gain * factor)


def _collect_directive_modifiers(pop, factions: dict) -> dict[str, float]:
    mods: dict[str, float] = {}
    directives = list(pop.active_directives)
    for fid in pop.faction_ids:
        faction = factions.get(str(fid))
        if faction:
            directives.extend(faction.active_directives)
    for d in directives:
        for action, delta in d.action_weight_modifiers.items():
            mods[action] = mods.get(action, 0.0) + delta
    return mods


def _max_slot_modifier(pop, factions: dict) -> int:
    directives = list(pop.active_directives)
    for fid in pop.faction_ids:
        faction = factions.get(str(fid))
        if faction:
            directives.extend(faction.active_directives)
    for d in directives:
        if d.slot_modifier != 0:
            return d.slot_modifier
    return 0

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_pop_priorities(pop, factions: dict) -> dict[str, float]:
    """4-pass priority computation. Returns dict over ALL_ACTIONS summing to 1.0."""
    ps = pop.pop_state
    if ps is None:
        return {a: 0.0 for a in ALL_ACTIONS}

    needs_by_name = {n.name: n for n in ps.needs}

    # Pass 1: need urgency (stubs always 0; sharing actions split urgency)
    raw: dict[str, float] = {}
    for action in ALL_ACTIONS:
        if action in STUB_ACTIONS:
            raw[action] = 0.0
            continue
        need_name = ACTION_NEED_MAP[action]
        need = needs_by_name.get(need_name)
        urgency = _pop_need_urgency(need) if need else 0.0
        sharing_count = sum(
            1 for a in ALL_ACTIONS
            if a not in STUB_ACTIONS and ACTION_NEED_MAP.get(a) == need_name
        )
        raw[action] = urgency / max(sharing_count, 1)

    # Occupation baseline: additive offset before competency scaling.
    occ_key = pop.occupation.value if hasattr(pop.occupation, "value") else str(pop.occupation)
    for action, baseline in OCCUPATION_BASELINE_WEIGHTS.get(occ_key, {}).items():
        if action in raw and action not in STUB_ACTIONS:
            raw[action] += baseline

    # Pass 2: competency scaling
    weighted = {action: raw[action] * _pop_competency_modifier(pop, action) for action in ALL_ACTIONS}

    # Pass 3: directive weight modifiers (additive; floor at 0)
    mods = _collect_directive_modifiers(pop, factions)
    for action, delta in mods.items():
        if action in weighted:
            weighted[action] = max(0.0, weighted[action] + delta)

    # Pass 4: normalize
    total = sum(weighted.values())
    if total <= 0.0:
        non_stub = [a for a in ALL_ACTIONS if a not in STUB_ACTIONS]
        return {a: (1.0 / len(non_stub) if a not in STUB_ACTIONS else 0.0) for a in ALL_ACTIONS}

    return {action: weighted[action] / total for action in ALL_ACTIONS}


def compute_active_slots(pop, factions: dict) -> int:
    """Compute how many priority slots are active this tick."""
    base = max(2, int(math.floor(pop.size_fractional)))
    ps = pop.pop_state
    if ps is not None and ps.fatigue < 1.0:
        modifier = _max_slot_modifier(pop, factions)
        base = max(1, base + modifier)
    return base


def resolve_pop_actions(
    pop,
    pop_loc,
    priorities: dict[str, float],
    n_slots: int,
    factions: dict,
    current_tick: int = 0,
    colocated_pops: list | None = None,
) -> list[str]:
    """Execute top-N priority actions; return narrative strings for notable events.

    If ``priorities`` is empty (``{}`` or ``[]``), priorities are computed from
    the pop's current needs via ``compute_pop_priorities``.
    """
    narratives: list[str] = []
    ps = pop.pop_state
    if ps is None:
        return narratives

    needs_by_name = {n.name: n for n in ps.needs}

    # Compute priorities on demand when caller passes none
    if not priorities:
        factions_dict = factions if isinstance(factions, dict) else {}
        priorities = compute_pop_priorities(pop, factions_dict)

    # Select top-N active (non-stub, non-zero) actions by weight
    ranked = sorted(
        [(a, w) for a, w in priorities.items() if a not in STUB_ACTIONS and w > 0],
        key=lambda x: x[1],
        reverse=True,
    )
    active = [action for action, _ in ranked[:n_slots]]

    for action in active:
        weight = priorities[action]
        competency = _pop_competency_modifier(pop, action)
        output = weight * pop.size_fractional * competency

        if action in ("forage", "hunt", "collect"):
            matching = _find_matching_resources(pop_loc.collectible_resources, action)
            _pub = _public_stockpile(pop_loc)
            if matching:
                per_resource_output = output / len(matching)
                for cr in matching:
                    actual = min(per_resource_output, cr.current_yield)
                    cr.current_yield = max(0.0, cr.current_yield - actual)
                    _pub.quantities[cr.resource_type] = _pub.quantities.get(cr.resource_type, 0.0) + actual
            else:
                # Environment fallback
                if action == "forage":
                    _pub.quantities["food_flora"] = _pub.quantities.get("food_flora", 0.0) + output * BASE_FORAGE_YIELD
                elif action == "hunt":
                    _pub.quantities["food_fauna"] = _pub.quantities.get("food_fauna", 0.0) + output * BASE_FORAGE_YIELD
                # collect with no matching resource → no output

        elif action == "commune":
            gain = output * 0.10
            need = needs_by_name.get("cohesion")
            if need:
                need.satisfaction = min(1.0, need.satisfaction + gain)
            _apply_spillover(pop, colocated_pops or [], "cohesion", gain, factions)

        elif action == "revel":
            gain = output * 0.15
            need = needs_by_name.get("cohesion")
            if need:
                need.satisfaction = min(1.0, need.satisfaction + gain)
            _apply_spillover(pop, colocated_pops or [], "cohesion", gain, factions)

        elif action == "enact_rituals":
            gain = output * NEED_FILL_RATE
            need = needs_by_name.get("purpose")
            if need:
                need.satisfaction = min(1.0, need.satisfaction + gain)
            _apply_spillover(pop, colocated_pops or [], "purpose", gain, factions)

        elif action == "build":
            gain = output * NEED_FILL_RATE
            need = needs_by_name.get("shelter")
            if need:
                need.satisfaction = min(1.0, need.satisfaction + gain)
            _apply_spillover(pop, colocated_pops or [], "shelter", gain, factions)

        elif action == "fortify":
            gain = output * NEED_FILL_RATE
            need = needs_by_name.get("safety")
            if need:
                need.satisfaction = min(1.0, need.satisfaction + gain)
            _apply_spillover(pop, colocated_pops or [], "safety", gain, factions)
            pop_loc.danger = max(0.0, pop_loc.danger - output * 0.005)

        elif action == "migrate":
            # Actual leg-by-leg routing is future work; provide placeholder satisfaction
            # so wanderlust doesn't drain to zero before movement is implemented
            need = needs_by_name.get("wanderlust")
            if need:
                need.satisfaction = min(1.0, need.satisfaction + output * NEED_FILL_RATE * 0.5)

    # Consumption pass: draw basis/solvent resources from stockpile → fill nourishment/hydration
    # Build resource_type → "basis" | "solvent" map (collectible_resource biochem_tags take priority)
    _biochem_map: dict[str, str] = dict(_RESOURCE_BIOCHEM)
    for _cr in pop_loc.collectible_resources:
        if _cr.biochem_tags:
            if any(t.startswith("basis:") for t in _cr.biochem_tags):
                _biochem_map[_cr.resource_type] = "basis"
            elif any(t.startswith("solvent:") for t in _cr.biochem_tags):
                _biochem_map[_cr.resource_type] = "solvent"

    nourishment = needs_by_name.get("nourishment")
    hydration    = needs_by_name.get("hydration")

    _accessible = [s for s in pop_loc.stockpiles if can_access_stockpile(pop, s)]
    for _s in _accessible:
        for resource_type, quantity in list(_s.quantities.items()):
            if quantity <= 0:
                continue
            category = _biochem_map.get(resource_type)
            if category == "basis" and nourishment and nourishment.satisfaction < 1.0:
                consumed = min(quantity, NOURISHMENT_CONSUME_RATE)
                _s.quantities[resource_type] -= consumed
                nourishment.satisfaction = min(1.0, nourishment.satisfaction + NOURISHMENT_FILL_RATE)
            elif category == "solvent" and hydration and hydration.satisfaction < 1.0:
                consumed = min(quantity, HYDRATION_CONSUME_RATE)
                _s.quantities[resource_type] -= consumed
                hydration.satisfaction = min(1.0, hydration.satisfaction + HYDRATION_FILL_RATE)

    # Narrative: unmet nourishment or hydration
    if nourishment and nourishment.is_pressing and not any(
        _biochem_map.get(rt) == "basis" and q > 0
        for _s in _accessible
        for rt, q in _s.quantities.items()
    ):
        from core.universe_core import pop_label as _pop_label
        narratives.append(
            f"§pop§{pop.id}§{_pop_label(pop)}§ has no food — nourishment unmet."
        )
    if hydration and hydration.is_pressing and not any(
        _biochem_map.get(rt) == "solvent" and q > 0
        for _s in _accessible
        for rt, q in _s.quantities.items()
    ):
        from core.universe_core import pop_label as _pop_label
        narratives.append(
            f"§pop§{pop.id}§{_pop_label(pop)}§ has no water — hydration unmet."
        )

    return narratives
