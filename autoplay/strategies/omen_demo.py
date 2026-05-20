"""
autoplay/strategies/omen_demo.py

Diagnostic strategy for the "shotgun" Manifest Omen:
  - Tick 1: manifest an Imago-framed omen on Neran (domain + culture riders),
    target_loc_id left None (manifests at the world surface, distance 0).
  - Otherwise idle-harvest.

Each tick prints, per Neran Pop (grouped by PopLocation distance_from_core),
the FULL belief + culture spread — so the intended signal vs. scrambled
misinterpretation noise is visible — plus every notable mortal on Neran
(each resolved as a size-1 Pop: clean or fully-scrambled, binary).
"""
from __future__ import annotations
from uuid import UUID

from core.action_core import (
    TargetType,
    OmenIntent, EssenceHarvestIntent,
    DomainVector, CultureVector, Framing,
)
from core.universe_core import PopLocation, MortalStatus
from logic.tick_logic import TickLoop, SimulationState, _resolve_world_id_for
from utilities.imago_registry import get_registry as get_imago_registry

from autoplay.strategies._helpers import queue, world_id


OMEN_WORLD = "Neran"
OMEN_IMAGO = "change:t1:wheel"   # domain:change/sacrifice/mastery + culture riders


def _fmt(d: dict) -> str:
    items = sorted(d.items(), key=lambda kv: -abs(kv[1]))
    return " ".join(f"{t.split(':',1)[1][:6]}:{v:+.3f}" for t, v in items if abs(v) > 1e-4) or "—"


def _print_snapshot(state: SimulationState, tick: int) -> None:
    wid = str(world_id(state, OMEN_WORLD))
    print(f"  ── tick {tick} ──")
    rows = []
    for pop in state.pops.values():
        ploc = state.locations.get(str(pop.current_location)) if pop.current_location else None
        if isinstance(ploc, PopLocation) and str(ploc.parent_id) == wid:
            dist = getattr(ploc, "distance_from_core", 0) or 0
            rows.append((dist, pop))
    rows.sort(key=lambda r: (r[0], r[1].stratum))
    for dist, pop in rows:
        print(f"    d{dist} {pop.stratum[:8]:8s} sz{pop.size_magnitude}"
              f"  bel[{_fmt(pop.dominant_beliefs)}]  cul[{_fmt(pop.culture_tags)}]")
    for m in state.mortals.values():
        if m.status != MortalStatus.ACTIVE:
            continue
        if _resolve_world_id_for(state, m.current_location) != wid:
            continue
        print(f"    M  {m.name[:18]:18s}     "
              f"bel[{_fmt(m.belief_tags)}]  cul[{_fmt(m.culture_tags)}]")


def decide(loop: TickLoop, state: SimulationState, tick: int) -> str:
    def q(key, ttype, tid, intent=None, prox=None):
        queue(loop, state, key, ttype, tid, intent, prox)

    if tick <= 4:
        _print_snapshot(state, tick)

    if tick == 1:
        node = get_imago_registry().get_node(OMEN_IMAGO)
        dvs = [DomainVector(domain_tag=t, direction=v)
               for t, v in node.mechanics.items() if t.startswith("domain:")]
        cvs = [CultureVector(culture_tag=t, direction=v)
               for t, v in node.mechanics.items() if not t.startswith("domain:")]
        q("manifest_omen", TargetType.WORLD, world_id(state, OMEN_WORLD),
          OmenIntent(
              sign_description="The skies of Neran churn and reverse",
              intended_interpretation="The age of stillness is ending",
              domain_vectors=dvs,
              culture_vectors=cvs,
              framing=Framing.PROPHETIC,
              target_loc_id=None,
              imago_node_id=OMEN_IMAGO,
          ))
        return f"Manifest Omen ({OMEN_IMAGO}) on {OMEN_WORLD}."

    q("harvest_essence", TargetType.UNDERREAL, None,
      EssenceHarvestIntent(concealment_priority=0.9))
    return "Harvest Essence (idle)."
