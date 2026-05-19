"""
Small helpers for peeking at scenario_meta without loading the full scenario.
Used by the chooser (list display) and by BuilderScreen (to recover the
scenario_meta.description field, which scenario_loader drops on load).
"""
from __future__ import annotations
import sqlite3
from pathlib import Path


def peek_meta(path: Path) -> dict:
    """Return {'name': str, 'description': str} for a scenario .db. Falls back
    to defaults derived from the path when the DB can't be read."""
    try:
        with sqlite3.connect(path) as c:
            row = c.execute(
                "SELECT name, description FROM scenario_meta LIMIT 1"
            ).fetchone()
        if row:
            return {"name": row[0] or path.stem, "description": row[1] or ""}
    except Exception:
        pass
    return {"name": path.stem, "description": ""}
