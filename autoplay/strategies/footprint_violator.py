"""
autoplay/strategies/footprint_violator.py

Stress test: aggressively push overt_miracles and proxius_activity into
BREACHING/FLAGRANT territory. Used to verify that:
  - Cassiel's disposition (methods axis) drops as FootprintConstraints fire.
  - Pantheon's Collective Subtlety Expectation fans out to both Luminaries.
  - Vrath (NarrativeConstraint only) is NOT affected by the same violation.

Run with:  python main.py --autoplay footprint_violator
Watch:     Cassiel methods disposition should fall sharply.
           Vrath methods should also drop (Pantheon fan-out).
"""
from __future__ import annotations
from uuid import UUID

from core.action_core import (
    TargetType, OmenIntent, DomainVector, CultureVector, Framing,
    EssenceHarvestIntent, ScryIntent, ScryScope,
)
from logic.tick_logic import TickLoop, SimulationState
from utilities.imago_registry import get_registry as get_imago_registry

from autoplay.strategies._helpers import (
    queue, mortal_named, world_id,
)


def decide(loop: TickLoop, state: SimulationState, tick: int) -> str:

    def q(key, ttype, tid, intent=None, prox=None):
        queue(loop, state, key, ttype, tid, intent, prox)

    neran = world_id(state, "Neran")
    oros  = world_id(state, "Oros")

    # Tick 1: scry to populate visible mortals
    if tick == 1:
        q("scry", TargetType.WORLD, neran, ScryIntent(scope=ScryScope.WORLD))
        return "Scry Neran — populate visible mortals."

    # Tick 2: scry Oros
    if tick == 2:
        q("scry", TargetType.WORLD, oros, ScryIntent(scope=ScryScope.WORLD))
        return "Scry Oros."

    # Ticks 3+: appoint every visible mortal as Proxius to spike proxius_activity,
    # and alternate Manifest Omen on each world to spike overt_miracles.
    # Harvest occasionally so we don't run dry.
    if tick % 8 == 0:
        q("harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(concealment_priority=0.0))
        return f"Tick {tick}: Harvest Essence (no concealment — leaving trace)."

    # Appoint the first non-Proxius visible mortal each tick if any exist
    from core.universe_core import MortalRole, MortalStatus
    non_proxii = [
        (mid, m) for mid, m in state.mortals.items()
        if m.role != MortalRole.PROXIUS and m.status == MortalStatus.ACTIVE
    ]
    if non_proxii and tick % 4 == 3:
        mid, mortal = non_proxii[0]
        q("appoint_proxius", TargetType.MORTAL, UUID(mid))
        return f"Tick {tick}: Appoint {mortal.name} as Proxius — spiking proxius_activity."

    # Alternate worlds for Manifest Omen — high overt_miracles cost (0.5/tick)
    target_world = neran if tick % 2 == 1 else oros
    world_name = "Neran" if tick % 2 == 1 else "Oros"

    reg = get_imago_registry()
    node = reg.get_node("conflict:t1:spark")
    if node is None:
        # Fallback to any available node
        node = next(iter(reg._nodes.values()))

    dvs = [DomainVector(domain_tag=t, direction=v)
           for t, v in node.mechanics.items() if t.startswith("domain:")]
    cvs = [CultureVector(culture_tag=t, direction=v)
           for t, v in node.mechanics.items() if not t.startswith("domain:")]

    q("manifest_omen", TargetType.WORLD, target_world,
      OmenIntent(
          sign_description=f"A blinding pillar of divine fire descends over {world_name}.",
          intended_interpretation="This is not subtle. The gods are HERE.",
          domain_vectors=dvs,
          culture_vectors=cvs,
          framing=Framing.PROPHETIC,
          target_loc_id=None,
          imago_node_id=node.id,
      ))
    return (
        f"Tick {tick}: Manifest Omen on {world_name} — "
        f"overt_miracles spike, Cassiel's constraint violated."
    )
