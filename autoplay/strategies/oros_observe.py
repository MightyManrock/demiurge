"""
autoplay/strategies/oros_observe.py — passive observer for the Oros test sandbox.

No Demiurge actions are queued. Intended for use with tools/oros_observe.py
which loads oros_test_sandbox.db and runs 100 ticks.
"""
from __future__ import annotations
from logic.tick_logic import TickLoop, SimulationState


def decide(loop: TickLoop, state: SimulationState, tick: int) -> str:
    return "(observe) — Demiurge is absent"
