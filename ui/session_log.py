"""
Plain-text session log: a write-only sink that mirrors what the player sees
in the RichLog feed to a file under `logs/`. Strips Rich markup so the file
is readable in any text editor.
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from rich.text import Text as _RText

import display

if TYPE_CHECKING:
    from logic.tick_logic import SimulationState, TickResult


class SessionLog:
    def __init__(self, path: Path):
        self.path = path
        self.path.write_text(
            f"DEMIURGE SESSION LOG\nStarted: {datetime.now().isoformat()}\n{'='*60}\n\n",
            encoding="utf-8",
        )

    def write(self, text: str) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(text + "\n")

    def write_tick(self, result: "TickResult") -> None:
        # Strip Rich markup for the plain-text session log.
        self.write(
            _RText.from_markup(
                display.display_tick_result(result, dev_mode=display.DEV_MODE)
            ).plain
        )

    def write_action(self, summary: str) -> None:
        self.write(f"  > QUEUED: {summary}")

    def finalize(self, state: "SimulationState", result: "TickResult | None") -> None:
        self.write("\n" + "=" * 60)
        self.write("SESSION END")
        self.write(f"Final age: {state.universe.current_age:.1f}")
        self.write(f"Final tick: {state.tick_number}")
        if result and result.terminal.triggered:
            self.write(f"Outcome: {result.terminal.condition.value}")
        self.write(f"Ended: {datetime.now().isoformat()}")
