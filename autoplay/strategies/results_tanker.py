"""
autoplay/strategies/results_tanker.py

Stress test: do as little as possible. Scry passively, harvest occasionally.
No civilization-building, no whispers, no development. Let Vrath's results
score drift negative until it crosses the min_results=-0.5 floor.

Used to verify that:
  - Vrath's methods disposition drops as Results Demand fires STRAINING/BREACHING.
  - Cassiel is unaffected (Results Demand is Vrath-owned, not Pantheon).
  - Attention rises on Vrath only.

Run with:  python main.py --autoplay results_tanker
Watch:     Vrath methods should fall. Cassiel methods should hold steady.
           Vrath attention should tick upward as violations compound.
"""
from __future__ import annotations

from core.action_core import TargetType, EssenceHarvestIntent, ScryIntent, ScryScope
from logic.tick_logic import TickLoop, SimulationState

from autoplay.strategies._helpers import queue, world_id


def decide(loop: TickLoop, state: SimulationState, tick: int) -> str:

    def q(key, ttype, tid, intent=None):
        queue(loop, state, key, ttype, tid, intent)

    neran = world_id(state, "Neran")
    oros  = world_id(state, "Oros")

    # Harvest occasionally so we don't run dry — but nothing constructive
    if tick % 8 == 0:
        q("harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(concealment_priority=1.0))
        return f"Tick {tick}: Harvest Essence — minimal activity, letting results decay."

    # Alternate passive scry — zero footprint, zero universe improvement
    target = neran if tick % 2 == 1 else oros
    name   = "Neran" if tick % 2 == 1 else "Oros"
    q("scry", TargetType.WORLD, target, ScryIntent(scope=ScryScope.WORLD))
    return f"Tick {tick}: Scry {name} — passive only, results tanking."
