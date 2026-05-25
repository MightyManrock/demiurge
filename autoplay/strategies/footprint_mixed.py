"""
autoplay/strategies/footprint_mixed.py

Stress test: spam Proxii appointments to push proxius_activity above
Cassiel's Proxius Restraint tolerance (0.25), while keeping overt_miracles
at zero.  Used to verify that:
  - Cassiel's methods disposition drops (Proxius Restraint fires).
  - Vrath's methods disposition is unaffected (Vrath has only a
    NarrativeConstraint — Results Demand — which is never evaluated).
  - The Pantheon's Collective Subtlety Expectation stays EXEMPLARY
    (overt_miracles=0), producing a small positive fan-out to both
    Luminaries that partially offsets Cassiel's proxius hit.

Run with:  python main.py --autoplay footprint_mixed
Watch:     Cassiel methods disposition should fall steadily.
           Vrath methods should hold steady or tick slightly upward.
           Evaluations should show STRAINING/BREACHING on
           "Proxius Restraint [proxius_activity]" for Cassiel only.
"""
from __future__ import annotations
from uuid import UUID

from core.action_core import (
    TargetType, WhisperIntent, DomainVector,
    EssenceHarvestIntent, ScryIntent, ScryScope,
)
from core.universe_core import MortalRole, MortalStatus
from logic.tick_logic import TickLoop, SimulationState

from autoplay.strategies._helpers import (
    queue, visible_named, world_id,
)


def decide(loop: TickLoop, state: SimulationState, tick: int) -> str:

    def q(key, ttype, tid, intent=None, prox=None):
        queue(loop, state, key, ttype, tid, intent, prox)

    neran = world_id(state, "Neran")
    oros  = world_id(state, "Oros")

    # Scry early to discover mortals
    if tick == 1:
        q("scry", TargetType.WORLD, neran, ScryIntent(scope=ScryScope.WORLD))
        return "Scry Neran — discover mortals."

    if tick == 2:
        q("scry", TargetType.WORLD, oros, ScryIntent(scope=ScryScope.WORLD))
        return "Scry Oros."

    # Harvest with high concealment to avoid overt footprint
    if tick % 6 == 0:
        q("harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(concealment_priority=1.0))
        return f"Tick {tick}: Harvest Essence (max concealment — no trace)."

    # Appoint every eligible non-Proxius mortal as Proxius each tick to
    # aggressively spike proxius_activity above Cassiel's tolerance of 0.25.
    non_proxii = [
        (mid, m) for mid, m in state.mortals.items()
        if m.role != MortalRole.PROXIUS and m.status == MortalStatus.ACTIVE
    ]
    if non_proxii:
        mid, mortal = non_proxii[0]
        q("appoint_proxius", TargetType.MORTAL, UUID(mid))
        return (
            f"Tick {tick}: Appoint {mortal.name} as Proxius — "
            f"spiking proxius_activity above Cassiel's 0.25 tolerance."
        )

    # Fallback when all mortals are already Proxii: whisper subtly (zero overt cost)
    mid_senna, _ = visible_named(state, "Senna Vaur")
    if mid_senna:
        q("whisper", TargetType.MORTAL, UUID(mid_senna),
          WhisperIntent(
              domain_vectors=[DomainVector(domain_tag="domain:order", direction=0.3)],
          ))
        return f"Tick {tick}: Whisper to Senna — all Proxii appointed, maintaining low overt footprint."

    # Final fallback: passive scry
    target = neran if tick % 2 == 0 else oros
    name = "Neran" if tick % 2 == 0 else "Oros"
    q("scry", TargetType.WORLD, target, ScryIntent(scope=ScryScope.WORLD))
    return f"Tick {tick}: Scry {name} — passive observation."
