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
SUSTENANCE_CONSUME_RATE = 0.05

ACTION_NEED_MAP: dict[str, str] = {
    "forage":        "sustenance",
    "hunt":          "sustenance",
    "collect":       "sustenance",
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
        from core.universe_core import SocialClass
        if getattr(pop, "social_class", None) == SocialClass.WILD:
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
    current_tick: int,
) -> list[str]:
    """Execute top-N priority actions; return narrative strings for notable events."""
    narratives: list[str] = []
    ps = pop.pop_state
    if ps is None:
        return narratives

    needs_by_name = {n.name: n for n in ps.needs}

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

        if action == "forage":
            pop_loc.resource_stockpile["food_flora"] = (
                pop_loc.resource_stockpile.get("food_flora", 0.0) + output
            )

        elif action == "hunt":
            pop_loc.resource_stockpile["food_fauna"] = (
                pop_loc.resource_stockpile.get("food_fauna", 0.0) + output
            )

        elif action == "collect":
            cr = pop_loc.collectible_resource
            if cr:
                deposited = min(output, cr.resource_yield)
                pop_loc.resource_stockpile[cr.resource_type] = (
                    pop_loc.resource_stockpile.get(cr.resource_type, 0.0) + deposited
                )

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

    # Consumption pass: draw food from stockpile → fill sustenance need
    sustenance = needs_by_name.get("sustenance")
    if sustenance:
        food_available = sum(pop_loc.resource_stockpile.get(rt, 0.0) for rt in POP_FOOD_RESOURCE_TYPES)
        if food_available > 0.0:
            consume_amount = min(food_available, pop.size_fractional * 0.5)
            remaining = consume_amount
            for rt in POP_FOOD_RESOURCE_TYPES:
                if rt in pop_loc.resource_stockpile and pop_loc.resource_stockpile[rt] > 0.0:
                    take = min(pop_loc.resource_stockpile[rt], remaining)
                    pop_loc.resource_stockpile[rt] -= take
                    remaining -= take
                    if remaining <= 0.0:
                        break
            sustenance.satisfaction = min(1.0, sustenance.satisfaction + SUSTENANCE_CONSUME_RATE)
        elif sustenance.is_pressing:
            from core.universe_core import pop_label
            narratives.append(
                f"§pop§{pop.id}§{pop_label(pop)}§ has no food — sustenance need unmet."
            )

    return narratives
