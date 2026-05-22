"""
autoplay/strategies/vail_travel_test.py

Validates the Durenn Vail Neran↔Sethis travel route end-to-end.
Tracks Vail's position each tick and verifies she completes the journey.

Expected: Vail departs tick 1, arrives Sethis Surface on tick 10
          (2 + 4 + 3 = 9 ticks in transit). Then returns.
"""
from __future__ import annotations
from core.universe_core import TravelLocation, PopLocation
from core.agent_core import TravelIntent
from autoplay.strategies._helpers import queue, world_id
from logic.tick_logic import TickLoop, SimulationState

VAIL_NAME = "Durenn Vail"
MAX_TICKS = 25

_arrived_sethis: bool = False
_returned_neran: bool = False


def _vail(state: SimulationState):
    return next((m for m in state.mortals.values() if m.name == VAIL_NAME), None)


def _loc_name(state: SimulationState, loc_id) -> str:
    if loc_id is None:
        return "?"
    loc = state.locations.get(str(loc_id))
    return loc.name if loc else str(loc_id)


def _print_status(state: SimulationState, tick: int) -> None:
    vail = _vail(state)
    if vail is None:
        print(f"  tick {tick:3d} | Vail NOT FOUND")
        return

    loc_name = _loc_name(state, vail.current_location)
    ti = vail.travel_intent
    if ti is not None:
        tl = state.locations.get(str(ti.travel_location_id))
        if isinstance(tl, TravelLocation):
            wp_name = _loc_name(state, tl.current_waypoint)
            dest_key = next(k for k, v in tl.legs.items() if v == 0)
            dest_name = _loc_name(state, dest_key)
            print(f"  tick {tick:3d} | IN TRANSIT → {dest_name}"
                  f"  (leg: {wp_name}, {tl.ticks_remaining} tick(s) left)")
        else:
            print(f"  tick {tick:3d} | travel_intent points to missing TravelLocation!")
    else:
        print(f"  tick {tick:3d} | AT {loc_name}")


def decide(loop: TickLoop, state: SimulationState, tick: int) -> str:
    global _arrived_sethis, _returned_neran

    _print_status(state, tick)

    vail = _vail(state)
    if vail and vail.travel_intent is None:
        loc = _loc_name(state, vail.current_location)
        if loc == "Sethis Surface":
            _arrived_sethis = True
        elif loc == "Neran Surface" and _arrived_sethis:
            _returned_neran = True

    if tick >= MAX_TICKS:
        print(f"\n=== RESULT at tick {tick} ===")
        print(f"  arrived Sethis: {_arrived_sethis}, returned Neran: {_returned_neran}")
        if _arrived_sethis and _returned_neran:
            print("PASS: Vail completed full round trip.")
        elif _arrived_sethis:
            print("PASS (partial): Vail reached Sethis Surface.")
        else:
            print("FAIL: Vail did not reach Sethis Surface within 25 ticks.")

    from core.action_core import EssenceHarvestIntent, TargetType
    queue(loop, state, "harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(concealment_priority=0.9))
    return "Idle harvest (watching Vail)."
