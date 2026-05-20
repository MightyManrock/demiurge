"""
autoplay/strategies/omen_demo.py

Diagnostic strategy for Manifest Omen sub-location shielding:
  - Tick 1: manifest an omen on Neran pushing domain:change, target_loc_id
    left None (manifests at the world surface, distance 0).
  - Otherwise idle-harvest.

Each tick prints every Pop on Neran grouped with its PopLocation's
distance_from_core, so we can watch the omen + its 5-tick SPIKE_FADE echo
land harder on surface Pops than on orbital / bathypelagic ones.
"""
from __future__ import annotations
from uuid import UUID

from core.action_core import (
    TargetType,
    OmenIntent, EssenceHarvestIntent,
    DomainVector, Framing,
)
from core.universe_core import PopLocation
from logic.tick_logic import TickLoop, SimulationState

from autoplay.strategies._helpers import queue, world_id


OMEN_WORLD = "Neran"
OMEN_TAG = "domain:change"


def _print_snapshot(state: SimulationState, tick: int) -> None:
    wid = str(world_id(state, OMEN_WORLD))
    rows = []
    for pop in state.pops.values():
        ploc = state.locations.get(str(pop.current_location)) if pop.current_location else None
        if isinstance(ploc, PopLocation) and str(ploc.parent_id) == wid:
            dist = getattr(ploc, "distance_from_core", 0) or 0
            rows.append((dist, ploc.name, pop))
    rows.sort(key=lambda r: (r[0], r[1]))
    line = f"    [t{tick:>2}]"
    for dist, locname, pop in rows:
        v = pop.dominant_beliefs.get(OMEN_TAG, 0.0)
        line += f"  d{dist}:{pop.stratum[:5]}={v:.4f}"
    print(line)


def decide(loop: TickLoop, state: SimulationState, tick: int) -> str:
    def q(key, ttype, tid, intent=None, prox=None):
        queue(loop, state, key, ttype, tid, intent, prox)

    _print_snapshot(state, tick)

    if tick == 1:
        q("manifest_omen", TargetType.WORLD, world_id(state, OMEN_WORLD),
          OmenIntent(
              sign_description="The skies of Neran churn and reverse",
              intended_interpretation="The age of stillness is ending",
              domain_vectors=[DomainVector(domain_tag=OMEN_TAG, direction=1.0)],
              framing=Framing.PROPHETIC,
              target_loc_id=None,   # manifests at the surface (distance 0)
          ))
        return f"Manifest Omen on {OMEN_WORLD} ({OMEN_TAG})."

    q("harvest_essence", TargetType.UNDERREAL, None,
      EssenceHarvestIntent(concealment_priority=0.9))
    return "Harvest Essence (idle)."
