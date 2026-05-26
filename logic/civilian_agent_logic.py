from __future__ import annotations
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.universe_core import NotableMortal
    from logic.tick_logic import SimulationState

FATIGUE_BLOCK_THRESHOLD = 0.85
COLLECT_COOLDOWN = "collect"
SPEND_COOLDOWN = "spend"
TRAVEL_COOLDOWN = "travel"


def _mortal_is_travelling(mortal: NotableMortal, state: SimulationState) -> bool:
    loc = state.locations.get(str(mortal.current_location))
    return loc is not None and getattr(loc, "location_type", None) == "travel_location"


def evaluate_civilian_action(
    mortal: NotableMortal,
    state: SimulationState,
    current_tick: int,
) -> Optional[str]:
    """
    Returns one of: "collect", "spend", "travel:<location_id>", "idle", None.
    None means the mortal has no civilian_state and should be skipped.
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

    if cs.resources >= cs.spend_threshold:
        best_spend_loc = kb.best_known_spend_location()
        if not best_spend_loc:
            return "idle"
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
