"""
Plain-text session log: a write-only sink that mirrors what the player sees
in the RichLog feed to a file under `logs/`. Strips Rich markup so the file
is readable in any text editor.

RichLogBuffer: keeps the last 100 ticks of (tick, category, markup) tuples
in memory and can persist/restore them as JSONL for save-load continuity.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from rich.text import Text as _RText

from ui import display

if TYPE_CHECKING:
    from logic.tick_logic import SimulationState, TickResult

_RICH_LOG_MAX_TICKS = 100


class RichLogBuffer:
    """In-memory ring of the last _RICH_LOG_MAX_TICKS ticks' log entries.

    Each entry is (tick_number, category, markup_line). On append, ticks
    older than (newest - _RICH_LOG_MAX_TICKS) are dropped. The buffer can
    be saved to / loaded from a JSONL file for save-game continuity.
    """

    def __init__(self) -> None:
        self._entries: list[tuple[int, str, str]] = []

    def append_tick(self, tick_number: int, entries: list[tuple[str, str]]) -> None:
        for cat, markup in entries:
            self._entries.append((tick_number, cat, markup))
        cutoff = tick_number - _RICH_LOG_MAX_TICKS
        if cutoff > 0:
            self._entries = [e for e in self._entries if e[0] > cutoff]

    def entries(self) -> list[tuple[int, str, str]]:
        return list(self._entries)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for tick, cat, markup in self._entries:
                f.write(json.dumps([tick, cat, markup]) + "\n")

    def load(self, path: Path) -> None:
        self._entries = []
        if not path.exists():
            return
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        tick, cat, markup = json.loads(line)
                        self._entries.append((int(tick), str(cat), str(markup)))
                    except Exception:
                        pass


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
