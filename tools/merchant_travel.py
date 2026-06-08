#!/usr/bin/env python3
"""
tools/merchant_travel.py — Track travel behavior of the two merchant Pops
over 100 ticks:
  - Qaebdol Cave Village merchant (b80de66d) → The Ancestor Stones
  - Hiparun's Rift merchant       (e2007ab7) → Ulum Highlands
"""
from __future__ import annotations
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utilities.scenario_loader import load_scenario
from logic.tick_logic import TickLoop, SimulationState
from autoplay.strategies.oros_observe import decide

SCENARIO = _ROOT / "scenarios" / "oros_test_sandbox.db"
N_TICKS  = 100
SEED     = 42

QAEBDOL_MERCHANT  = "b80de66d-8ed8-4ee8-9dda-a8b7d7c41d60"
HIPARUN_MERCHANT  = "e2007ab7-d5c6-4e49-a24e-fec2ff2d1f9e"
ANCESTOR_STONES   = "60cca63f-b99c-4e52-9dd9-87ab3b1e8c78"
ULUM_HIGHLANDS    = "59e2edc9-58b1-41b1-a4c5-bf8d36f9a1e3"


def _loc_label(loc_id: str, state: SimulationState) -> str:
    loc = state.locations.get(loc_id)
    if loc is None:
        return f"?{loc_id[:8]}"
    name = getattr(loc, "name", None) or loc_id[:8]
    if getattr(loc, "location_type", "") == "travel_location":
        dest_id = list(loc.legs.keys())[-1] if loc.legs else ""
        dest = state.locations.get(dest_id)
        dest_name = (getattr(dest, "name", None) or dest_id[:8]) if dest else dest_id[:8]
        return f"→{dest_name}({loc.ticks_remaining}t)"
    return name


def run() -> None:
    state = load_scenario(SCENARIO)
    loop  = TickLoop(rng_seed=SEED)

    # Resolve full pop IDs from prefix
    pop_ids = list(state.pops.keys())
    qaebdol_id = next((p for p in pop_ids if p.startswith(QAEBDOL_MERCHANT[:8])), None)
    hiparun_id = next((p for p in pop_ids if p.startswith(HIPARUN_MERCHANT[:8])), None)

    if not qaebdol_id or not hiparun_id:
        print("ERROR: could not find merchant pops")
        print("  Pops with 'merchant' occupation:")
        for pid, pop in state.pops.items():
            if pop.occupation == "merchant":
                loc = state.locations.get(str(pop.current_location))
                print(f"    {pid}  @ {getattr(loc, 'name', '?')}")
        return

    loc_ids = list(state.locations.keys())
    ancestor_id = next((l for l in loc_ids if l.startswith(ANCESTOR_STONES[:8])), None)
    ulum_id     = next((l for l in loc_ids if l.startswith(ULUM_HIGHLANDS[:8])), None)

    print("=" * 70)
    print("  MERCHANT TRAVEL TRACKER — 100 ticks")
    print("=" * 70)
    print(f"  Qaebdol merchant  ({qaebdol_id[:8]}) → The Ancestor Stones")
    print(f"  Hiparun merchant  ({hiparun_id[:8]}) → Ulum Highlands")
    print()

    q_visits   = 0   # ticks spent at Ancestor Stones
    h_visits   = 0   # ticks spent at Ulum Highlands
    q_transits = 0   # ticks in transit toward Ancestor Stones
    h_transits = 0   # ticks in transit toward Ulum Highlands

    prev_q_loc = str(state.pops[qaebdol_id].current_location)
    prev_h_loc = str(state.pops[hiparun_id].current_location)

    print(f"  {'Tick':>4}  {'Qaebdol merchant':30s}  {'Hiparun merchant':30s}")
    print(f"  {'─'*4}  {'─'*30}  {'─'*30}")

    for tick in range(1, N_TICKS + 1):
        _ = decide(loop, state, tick)
        state, _ = loop.advance(state)

        q_pop = state.pops[qaebdol_id]
        h_pop = state.pops[hiparun_id]

        q_loc_id = str(q_pop.current_location)
        h_loc_id = str(h_pop.current_location)

        q_label = _loc_label(q_loc_id, state)
        h_label = _loc_label(h_loc_id, state)

        # Count visits (at destination)
        if q_loc_id == ancestor_id:
            q_visits += 1
        if h_loc_id == ulum_id:
            h_visits += 1

        # Count transit ticks toward destination
        q_loc_obj = state.locations.get(q_loc_id)
        h_loc_obj = state.locations.get(h_loc_id)
        if getattr(q_loc_obj, "location_type", "") == "travel_location":
            dest = list(q_loc_obj.legs.keys())[-1] if q_loc_obj.legs else ""
            if dest == ancestor_id:
                q_transits += 1
        if getattr(h_loc_obj, "location_type", "") == "travel_location":
            dest = list(h_loc_obj.legs.keys())[-1] if h_loc_obj.legs else ""
            if dest == ulum_id:
                h_transits += 1

        # Print every tick if either pop is away from home or changed location
        q_moved = q_loc_id != prev_q_loc
        h_moved = h_loc_id != prev_h_loc
        at_ancestor = q_loc_id == ancestor_id
        at_ulum     = h_loc_id == ulum_id
        in_transit  = (
            getattr(q_loc_obj, "location_type", "") == "travel_location" or
            getattr(h_loc_obj, "location_type", "") == "travel_location"
        )
        if q_moved or h_moved or at_ancestor or at_ulum or in_transit:
            marker_q = " ★" if at_ancestor else ("  " if not q_moved else " →")
            marker_h = " ★" if at_ulum     else ("  " if not h_moved else " →")
            print(f"  {tick:>4}  {q_label + marker_q:32s}  {h_label + marker_h:32s}")

        prev_q_loc = q_loc_id
        prev_h_loc = h_loc_id

    print()
    print("=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print(f"  Qaebdol merchant @ Ancestor Stones : {q_visits:3d} ticks resident")
    print(f"                     in transit there: {q_transits:3d} ticks")
    print(f"  Hiparun merchant @ Ulum Highlands  : {h_visits:3d} ticks resident")
    print(f"                     in transit there: {h_transits:3d} ticks")


if __name__ == "__main__":
    run()
