"""
autoplay/strategies/results_builder.py

Stress test: actively improve the universe. Accelerate civ development,
whisper to raise domain alignment, keep footprint clean.

Used to verify that:
  - Vrath's methods disposition holds steady or improves (COMPLIANT/EXEMPLARY
    on Results Demand as results score stays well above -0.5 floor).
  - Vrath results axis climbs as universe improves.
  - Cassiel is unaffected by Results Demand (Vrath-owned only).

Run with:  python main.py --autoplay results_builder
Watch:     Vrath methods should hold steady or tick upward.
           Vrath results should climb. No violations on Results Demand.
"""
from __future__ import annotations
from uuid import UUID

from core.action_core import (
    TargetType, WhisperIntent, DomainVector, Framing,
    EssenceHarvestIntent, ScryIntent, ScryScope, DevelopmentIntent,
)
from logic.tick_logic import TickLoop, SimulationState

from autoplay.strategies._helpers import (
    queue, visible_named, world_id, civ_id,
)


def decide(loop: TickLoop, state: SimulationState, tick: int) -> str:

    def q(key, ttype, tid, intent=None):
        queue(loop, state, key, ttype, tid, intent)

    neran = world_id(state, "Neran")
    oros  = world_id(state, "Oros")

    if tick == 1:
        q("scry", TargetType.WORLD, neran, ScryIntent(scope=ScryScope.WORLD))
        return "Scry Neran — discover mortals."

    if tick == 2:
        q("scry", TargetType.WORLD, oros, ScryIntent(scope=ScryScope.WORLD))
        return "Scry Oros."

    if tick % 8 == 0:
        q("harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(concealment_priority=1.0))
        return f"Tick {tick}: Harvest Essence (max concealment)."

    # Accelerate Neran development every 5 ticks
    if tick % 5 == 0:
        q("accelerate_development", TargetType.CIVILIZATION,
          civ_id(state, "The Neran Confederacy"),
          DevelopmentIntent(
              domain_vectors=[DomainVector(domain_tag="domain:order", direction=0.5)],
              target_aspect="legal and civic expansion",
          ))
        return f"Tick {tick}: Accelerate Neran development — boosting results."

    # Whisper to Senna every 3 ticks
    mid_senna, _ = visible_named(state, "Senna Vaur")
    if mid_senna and tick % 3 == 1:
        q("whisper", TargetType.MORTAL, UUID(mid_senna),
          WhisperIntent(
              concept="Order and mastery together build lasting civilizations.",
              domain_vectors=[
                  DomainVector(domain_tag="domain:order", direction=0.5),
                  DomainVector(domain_tag="domain:mastery", direction=0.4),
              ],
              framing=Framing.INSPIRATIONAL,
          ))
        return f"Tick {tick}: Whisper to Senna — nudging domain alignment upward."

    # Fallback: passive scry
    target = neran if tick % 2 == 0 else oros
    name   = "Neran" if tick % 2 == 0 else "Oros"
    q("scry", TargetType.WORLD, target, ScryIntent(scope=ScryScope.WORLD))
    return f"Tick {tick}: Scry {name} — passive observation."
