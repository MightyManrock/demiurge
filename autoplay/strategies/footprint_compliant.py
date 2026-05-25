"""
autoplay/strategies/footprint_compliant.py

Stress test: play cautiously and stay well under all FootprintConstraint
tolerances. Used to verify that:
  - EXEMPLARY/COMPLIANT compliance bands produce neutral-to-positive
    methods disposition deltas.
  - No spurious violations fire when footprint is genuinely low.
  - Cassiel and Vrath methods dispositions remain stable or improve.

Run with:  python main.py --autoplay footprint_compliant
Watch:     Both Luminary methods dispositions should hold steady or tick
           upward. No STRAINING/BREACHING/FLAGRANT entries in evaluations.
"""
from __future__ import annotations
from uuid import UUID

from core.action_core import (
    TargetType, WhisperIntent, DomainVector,
    EssenceHarvestIntent, ScryIntent, ScryScope, DevelopmentIntent,
)
from logic.tick_logic import TickLoop, SimulationState

from autoplay.strategies._helpers import (
    queue, visible_named, world_id, civ_id,
)


def decide(loop: TickLoop, state: SimulationState, tick: int) -> str:

    def q(key, ttype, tid, intent=None, prox=None):
        queue(loop, state, key, ttype, tid, intent, prox)

    neran = world_id(state, "Neran")
    oros  = world_id(state, "Oros")

    # Scry early to open the board
    if tick == 1:
        q("scry", TargetType.WORLD, neran, ScryIntent(scope=ScryScope.WORLD))
        return "Scry Neran — low-footprint information gathering."

    if tick == 2:
        q("scry", TargetType.WORLD, oros, ScryIntent(scope=ScryScope.WORLD))
        return "Scry Oros."

    # Harvest with high concealment priority every 5 ticks
    if tick % 5 == 0:
        q("harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(concealment_priority=1.0))
        return f"Tick {tick}: Harvest Essence (max concealment — minimal trace)."

    # Whisper to visible mortals — subtle_influence 0.1, well within any tolerance
    mid_senna, senna = visible_named(state, "Senna Vaur")
    if mid_senna and tick % 3 == 1:
        q("whisper", TargetType.MORTAL, UUID(mid_senna),
          WhisperIntent(
              domain_vectors=[DomainVector(domain_tag="domain:order", direction=0.5)],
          ))
        return f"Tick {tick}: Whisper to Senna (subtle_influence=0.1) — well inside tolerance."

    mid_kael, _ = visible_named(state, "Kael Ash")
    if mid_kael and tick % 3 == 2:
        q("whisper", TargetType.MORTAL, UUID(mid_kael),
          WhisperIntent(
              domain_vectors=[DomainVector(domain_tag="domain:conflict", direction=0.4)],
          ))
        return f"Tick {tick}: Whisper to Kael (subtle_influence=0.1) — well inside tolerance."

    # Accelerate development through natural means — low footprint
    if tick % 7 == 4:
        q("accelerate_development", TargetType.CIVILIZATION,
          civ_id(state, "The Neran Confederacy"),
          DevelopmentIntent(
              domain_vectors=[DomainVector(domain_tag="domain:order", direction=0.4)],
              target_aspect="incremental legal reform",
          ))
        return f"Tick {tick}: Accelerate Neran (low footprint dev push)."

    # Fallback: scry for information — zero footprint
    target = neran if tick % 2 == 0 else oros
    name = "Neran" if tick % 2 == 0 else "Oros"
    q("scry", TargetType.WORLD, target, ScryIntent(scope=ScryScope.WORLD))
    return f"Tick {tick}: Scry {name} — passive observation, zero footprint."
