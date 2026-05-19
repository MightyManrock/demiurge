"""
autoplay/strategies/passive.py — do-nothing baseline.

No Demiurge actions are queued. The simulation runs entirely on its own
passive mechanics: belief and culture drift, Pop-to-Pop contact, established
anchoring, footprint and visibility decay. Useful for observing baseline
universe behaviour without any divine intervention.
"""
from __future__ import annotations
from logic.tick_logic import TickLoop, SimulationState


def decide(loop: TickLoop, state: SimulationState, tick: int) -> str:
    return f"(passive) — no Demiurge action this tick."
