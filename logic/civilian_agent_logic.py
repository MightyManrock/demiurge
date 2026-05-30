from __future__ import annotations
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.universe_core import NotableMortal
    from core.agent_core import CivilianAgentState, KnowledgeBase
    from logic.tick_logic import SimulationState

FATIGUE_BLOCK_THRESHOLD = 0.85
COLLECT_COOLDOWN  = "collect"
SELL_COOLDOWN     = "sell"
SPEND_COOLDOWN    = "spend"
TRAVEL_COOLDOWN   = "travel"
LEISURE_COOLDOWN  = "leisure"
SOCIALIZE_COOLDOWN = "socialize"

LEISURE_BASE_GAIN          = 0.35
SOCIALIZE_BASE_GAIN        = 0.30
LEISURE_SATIATION_HOLD_BASE  = 6
SOCIALIZE_SATIATION_HOLD_BASE = 5


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


def _pop_social_quality(pop_tags: dict[str, float]) -> float:
    """Belonging quality from socializing: driven by pop solidarity + revelry."""
    base = (
        pop_tags.get("values:solidarity", 0.3) * 0.5
        + pop_tags.get("practice:revelry", 0.3) * 0.5
    )
    return min(1.0, max(0.0, base))


def _mortal_is_travelling(mortal: NotableMortal, state: SimulationState) -> bool:
    if mortal.travel_intent is not None:
        return True
    loc = state.locations.get(str(mortal.current_location))
    return loc is not None and getattr(loc, "location_type", None) == "travel_location"


def _trip_too_long_for_urgent_need(
    cs: CivilianAgentState,
    kb: KnowledgeBase,
    dest_id: str,
) -> bool:
    """Return True if any urgent need will reach 0 before the trip completes."""
    ticks_cost = kb.route_ticks_to(dest_id)
    if ticks_cost == 0:
        return False
    for need in cs.needs:
        if need.is_urgent and need.decay_rate > 0:
            ticks_until_desperate = need.satisfaction / need.decay_rate
            if ticks_cost > ticks_until_desperate:
                return True
    return False


def evaluate_civilian_action(
    mortal: NotableMortal,
    state: SimulationState,
    current_tick: int,
) -> Optional[str]:
    """
    Returns one of: "collect", "sell", "spend", "travel:<location_id>", "idle", None.
    None means the mortal has no civilian_state and should be skipped.

    Priority: sell sellable resources → spend credits → collect raw resources.
    Long-trip guard: if any urgent need would hit 0 before arrival, skip that travel.
    """
    cs = mortal.civilian_state
    kb = mortal.knowledge_base
    if cs is None or kb is None:
        return None

    if _mortal_is_travelling(mortal, state):
        return "idle"

    if mortal.fatigue >= FATIGUE_BLOCK_THRESHOLD:
        return "idle"

    if not cs.pressing_needs():
        return "idle"

    current_loc_id = str(mortal.current_location)

    # ── Priority 1: sell ─────────────────────────────────────────────────────
    sellable = next(
        (r for r in cs.inventory if "sell" in r.usable_for and r.quantity >= r.threshold),
        None,
    )
    if sellable:
        best_sell_loc = kb.best_known_sell_location()
        if best_sell_loc:
            if current_loc_id == best_sell_loc:
                if cs.cooldown_expired(SELL_COOLDOWN, current_tick):
                    return "sell"
                return "idle"
            if cs.cooldown_expired(TRAVEL_COOLDOWN, current_tick):
                route = kb.route_to(best_sell_loc)
                if route and route.vehicle_type:
                    if not any(a.asset_type == route.vehicle_type for a in mortal.assets):
                        return "idle"
                return f"travel:{best_sell_loc}"
            return "idle"

    # ── Priority 2: spend ────────────────────────────────────────────────────
    spendable = next(
        (
            r for r in cs.inventory
            if "spend" in r.usable_for
            and r.quantity >= r.threshold
            and (
                r.fills_need is None
                or any(n.name == r.fills_need and n.is_pressing for n in cs.needs)
            )
        ),
        None,
    )
    if spendable:
        best_spend_loc = kb.best_known_spend_location()
        if best_spend_loc:
            if current_loc_id == best_spend_loc:
                if cs.cooldown_expired(SPEND_COOLDOWN, current_tick):
                    return "spend"
                return "idle"
            if cs.cooldown_expired(TRAVEL_COOLDOWN, current_tick):
                route = kb.route_to(best_spend_loc)
                if route and route.vehicle_type:
                    if not any(a.asset_type == route.vehicle_type for a in mortal.assets):
                        return "idle"
                return f"travel:{best_spend_loc}"
            return "idle"

    # ── Priority 2.5: directive override ────────────────────────────────────
    # When Purpose is pressing and the mortal has a commerce directive, skip
    # leisure/socialize — community obligation takes precedence over personal time.
    _purpose = cs.get_need("purpose")
    _directive_active = bool(_purpose and _purpose.is_pressing and kb.directive_facts())

    if not _directive_active:
        # ── Priority 3: leisure ──────────────────────────────────────────────
        leisure_need = cs.get_need("leisure")
        if leisure_need and leisure_need.is_pressing:
            local_pop_id = str(mortal.pop_milieu or mortal.pop_id or "")
            if local_pop_id and local_pop_id in state.pops:
                if cs.cooldown_expired(LEISURE_COOLDOWN, current_tick):
                    return "leisure"

        # ── Priority 4: socialize ────────────────────────────────────────────
        belonging_need = cs.get_need("belonging")
        if belonging_need and belonging_need.is_pressing:
            local_pop_id = str(mortal.pop_milieu or mortal.pop_id or "")
            if local_pop_id and local_pop_id in state.pops:
                if cs.cooldown_expired(SOCIALIZE_COOLDOWN, current_tick):
                    return "socialize"

    # ── Priority 5: collect ──────────────────────────────────────────────────
    resource_locs = kb.known_resource_locations()
    if not resource_locs:
        return "idle"

    loc = state.locations.get(current_loc_id)
    at_resource = (
        loc is not None
        and getattr(loc, "collectible_resource", None) is not None
        and current_loc_id in resource_locs
    )

    if at_resource:
        if cs.cooldown_expired(COLLECT_COOLDOWN, current_tick):
            return "collect"
        return "idle"

    if cs.cooldown_expired(TRAVEL_COOLDOWN, current_tick):
        dest = resource_locs[0]
        route = kb.route_to(dest)
        if route and route.vehicle_type:
            if not any(a.asset_type == route.vehicle_type for a in mortal.assets):
                return "idle"
        return f"travel:{dest}"

    return "idle"
