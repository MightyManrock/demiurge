"""
autoplay/strategies/essence_claim_test.py

Watches Essence income vs puissance over 100 ticks to validate the
uncontested-domain claim formula: min(0.50, max(0.25, puissance)).

Prints a summary row every 10 ticks.
"""
from __future__ import annotations
from core.action_core import EssenceHarvestIntent, TargetType
from autoplay.strategies._helpers import queue
from logic.tick_logic import TickLoop, SimulationState

MAX_TICKS = 100
_header_printed = False
_prev_essence = None


def decide(loop: TickLoop, state: SimulationState, tick: int) -> str:
    global _header_printed, _prev_essence

    if not _header_printed:
        print(f"\n{'tick':>4}  {'puissance':>9}  {'essence':>8}  {'Δessence':>8}  {'cap':>5}")
        print("-" * 44)
        _header_printed = True

    if tick % 10 == 0:
        d = state.demiurge
        cap = min(0.50, max(0.25, d.puissance))
        actual = state.essence.actual
        delta = actual - _prev_essence if _prev_essence is not None else 0.0
        print(f"{tick:>4}  {d.puissance:>9.4f}  {actual:>8.2f}  {delta:>+8.3f}  {cap:>5.2f}")

    _prev_essence = state.essence.actual

    if tick >= MAX_TICKS:
        print("\nDone.")

    queue(loop, state, "harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(concealment_priority=0.9))
    return "Watching Essence income vs puissance."
