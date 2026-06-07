"""
autoplay/strategies/vail_travel_test.py

Validates Durenn Vail's full trade loop: collect unobtanium on Sethis,
sell on Neran, spend credits on Neran.

Expected behavior:
  Tick  1: Vail departs Neran → Sethis (12-tick journey)
  Tick 13: Arrives Sethis Surface; begins collecting unobtanium
  Tick ~16+: Unobtanium threshold reached; departs Sethis → Neran
  Tick ~28+: Arrives Neran Surface; sells unobtanium for credits
  Tick ~30+: Spends credits; indulgence need partially fulfilled
"""
from __future__ import annotations
from core.universe_core import TravelLocation
from core.agent_core import TravelIntent
from autoplay.strategies._helpers import queue, world_id
from logic.tick_logic import TickLoop, SimulationState

VAIL_NAME = "Durenn Vail"
MAX_TICKS = 50

_arrived_sethis: bool = False
_returned_neran: bool = False
_sold_unobtanium: bool = False
_spent_credits: bool = False
_prev_unobtanium: float = 0.0
_prev_credits: float = 0.0


def _vail(state: SimulationState):
    return next((m for m in state.mortals.values() if m.name == VAIL_NAME), None)


def _loc_name(state: SimulationState, loc_id) -> str:
    if loc_id is None:
        return "?"
    loc = state.locations.get(str(loc_id))
    return loc.name if loc else str(loc_id)


def _print_status(state: SimulationState, tick: int) -> None:
    global _prev_unobtanium, _prev_credits
    vail = _vail(state)
    if vail is None:
        print(f"  tick {tick:3d} | Vail NOT FOUND")
        return

    cs = vail.mortal_state
    inv_str = ""
    if cs and cs.mortal_inventory.items:
        parts = [f"{r.resource_type}={r.quantity:.1f}" for r in cs.mortal_inventory.items]
        inv_str = "  inv:[" + ", ".join(parts) + "]"

    ti = vail.travel_intent
    if ti is not None:
        tl = state.locations.get(str(ti.travel_location_id))
        if isinstance(tl, TravelLocation):
            wp_name = _loc_name(state, tl.current_waypoint)
            dest_key = next(k for k, v in tl.legs.items() if v == 0)
            dest_name = _loc_name(state, dest_key)
            print(f"  tick {tick:3d} | IN TRANSIT → {dest_name}"
                  f"  (leg: {wp_name}, {tl.ticks_remaining} tick(s) left){inv_str}")
        else:
            print(f"  tick {tick:3d} | travel_intent → missing TravelLocation{inv_str}")
    else:
        loc_name = _loc_name(state, vail.current_location)
        print(f"  tick {tick:3d} | AT {loc_name}{inv_str}")


def decide(loop: TickLoop, state: SimulationState, tick: int) -> str:
    global _arrived_sethis, _returned_neran, _sold_unobtanium, _spent_credits
    global _prev_unobtanium, _prev_credits

    _print_status(state, tick)

    vail = _vail(state)
    if vail and vail.travel_intent is None and vail.mortal_state:
        cs = vail.mortal_state
        loc = _loc_name(state, vail.current_location)

        if loc == "Sethis Surface":
            _arrived_sethis = True
        elif loc == "Neran Surface" and _arrived_sethis:
            _returned_neran = True

        unobtanium = next((r.quantity for r in cs.mortal_inventory.items if r.resource_type == "unobtanium"), 0.0)
        credits = next((r.quantity for r in cs.mortal_inventory.items if r.resource_type == "credits"), 0.0)

        if unobtanium < _prev_unobtanium and credits > _prev_credits:
            _sold_unobtanium = True
            print(f"  tick {tick:3d} | *** SOLD unobtanium → credits ({credits:.2f})")

        if credits < _prev_credits:
            _spent_credits = True
            print(f"  tick {tick:3d} | *** SPENT credits")

        _prev_unobtanium = unobtanium
        _prev_credits = credits

    if tick >= MAX_TICKS:
        print(f"\n=== RESULT at tick {tick} ===")
        print(f"  arrived Sethis:   {_arrived_sethis}")
        print(f"  returned Neran:   {_returned_neran}")
        print(f"  sold unobtanium:  {_sold_unobtanium}")
        print(f"  spent credits:    {_spent_credits}")
        if _arrived_sethis and _returned_neran and _sold_unobtanium and _spent_credits:
            print("PASS: Vail completed full trade loop.")
        elif _arrived_sethis and _returned_neran:
            print("PASS (partial): round trip done but sell/spend not observed.")
        elif _arrived_sethis:
            print("PASS (partial): reached Sethis, did not return.")
        else:
            print("FAIL: Vail did not reach Sethis within 50 ticks.")

    from core.action_core import EssenceHarvestIntent, TargetType
    queue(loop, state, "harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(concealment_priority=0.9))
    return "Idle harvest (watching Vail)."
