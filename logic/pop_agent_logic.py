from __future__ import annotations
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.universe_core import Pop, PopLocation, Faction

from core.agent_core import PopAgentState, PopNeed

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

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_matching_resources(collectible_resources: list, action: str) -> list:
    """Return CollectibleResources usable by this action (action_types=[] means any)."""
    return [
        cr for cr in collectible_resources
        if (not cr.action_types or action in cr.action_types)
        and cr.current_yield > 0
    ]

def _pop_need_urgency(need: PopNeed) -> float:
    """Continuous urgency in [0, ~1.5]. 0 when satisfied or held; >1 when urgent."""
    if need.satiation_hold > 0 or need.satisfaction >= need.pressing_threshold:
        return 0.0
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
            if matching:
                per_resource_output = output / len(matching)
                for cr in matching:
                    actual = min(per_resource_output, cr.current_yield)
                    cr.current_yield = max(0.0, cr.current_yield - actual)
                    pop_loc.resource_stockpile[cr.resource_type] = (
                        pop_loc.resource_stockpile.get(cr.resource_type, 0.0) + actual
                    )
            else:
                # Environment fallback
                if action == "forage":
                    pop_loc.resource_stockpile["food_flora"] = (
                        pop_loc.resource_stockpile.get("food_flora", 0.0) + output * BASE_FORAGE_YIELD
                    )
                elif action == "hunt":
                    pop_loc.resource_stockpile["food_fauna"] = (
                        pop_loc.resource_stockpile.get("food_fauna", 0.0) + output * BASE_FORAGE_YIELD
                    )
                # collect with no matching resource → no output

        elif action == "commune":
            need = needs_by_name.get("cohesion")
            if need:
                need.satisfaction = min(1.0, need.satisfaction + output * 0.10)

        elif action == "revel":
            need = needs_by_name.get("cohesion")
            if need:
                need.satisfaction = min(1.0, need.satisfaction + output * 0.15)

        elif action == "enact_rituals":
            need = needs_by_name.get("purpose")
            if need:
                need.satisfaction = min(1.0, need.satisfaction + output * NEED_FILL_RATE)

        elif action == "build":
            need = needs_by_name.get("shelter")
            if need:
                need.satisfaction = min(1.0, need.satisfaction + output * NEED_FILL_RATE)

        elif action == "fortify":
            need = needs_by_name.get("safety")
            if need:
                need.satisfaction = min(1.0, need.satisfaction + output * NEED_FILL_RATE)
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

    for resource_type, quantity in list(pop_loc.resource_stockpile.items()):
        if quantity <= 0:
            continue
        category = _biochem_map.get(resource_type)
        if category == "basis" and nourishment and nourishment.satisfaction < 1.0:
            consumed = min(quantity, NOURISHMENT_CONSUME_RATE)
            pop_loc.resource_stockpile[resource_type] -= consumed
            nourishment.satisfaction = min(1.0, nourishment.satisfaction + NOURISHMENT_FILL_RATE)
        elif category == "solvent" and hydration and hydration.satisfaction < 1.0:
            consumed = min(quantity, HYDRATION_CONSUME_RATE)
            pop_loc.resource_stockpile[resource_type] -= consumed
            hydration.satisfaction = min(1.0, hydration.satisfaction + HYDRATION_FILL_RATE)

    # Narrative: unmet nourishment or hydration
    if nourishment and nourishment.is_pressing and not any(
        _biochem_map.get(rt) == "basis" and q > 0
        for rt, q in pop_loc.resource_stockpile.items()
    ):
        from core.universe_core import pop_label as _pop_label
        narratives.append(
            f"§pop§{pop.id}§{_pop_label(pop)}§ has no food — nourishment unmet."
        )
    if hydration and hydration.is_pressing and not any(
        _biochem_map.get(rt) == "solvent" and q > 0
        for rt, q in pop_loc.resource_stockpile.items()
    ):
        from core.universe_core import pop_label as _pop_label
        narratives.append(
            f"§pop§{pop.id}§{_pop_label(pop)}§ has no water — hydration unmet."
        )

    return narratives
