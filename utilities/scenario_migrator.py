"""
scenario_migrator.py — bring scenario .db files up to the current schema.

The scenario .db is the source of truth for any given scenario. Over time,
new tables / columns / JSON keys may be added to `core/scenario_schema.sql`
and the Pydantic models in `core/`. Existing .db files written under older
schemas keep working at *load* time because the loader uses `.get()` /
`row.get()` fallbacks everywhere — but their on-disk schema doesn't grow
new columns on its own, which makes downstream operations brittle.

Migration here is a deliberate load → re-export round-trip:

  1. Open the existing .db.
  2. Run `scenario_loader.load_scenario()` — tolerates missing columns and
     missing optional fields by falling back to Pydantic defaults.
  3. Run `scenario_exporter.export_scenario()` — drops and re-creates every
     table fresh from the current `scenario_schema.sql`, then writes the
     loaded state. Missing fields gain their defaults; obsolete columns get
     dropped silently. Any data the loader doesn't know about is lost
     (rare; this is intentional for schema cleanups like
     `Constraint.domain_source` → `domain_tag`).

This module is called by:
  - `python main.py --rebuild --scenario` — sweeps every `scenarios/*.db`.
  - `BuilderApp.choose_scenario` — migrates a file just before opening it,
    so the builder always sees a current-schema state.
"""
from __future__ import annotations
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class MigrationResult:
    path: Path
    migrated: bool
    note: str  # human-readable; "ok", "no changes needed", or an error message
    error: Optional[Exception] = None


def _peek_scenario_meta(path: Path) -> tuple[str, str]:
    """Return (scenario_name, description) from scenario_meta, with empty
    fallbacks. Used to preserve those fields across the round-trip."""
    try:
        with sqlite3.connect(path) as c:
            row = c.execute(
                "SELECT name, description FROM scenario_meta LIMIT 1"
            ).fetchone()
        if row:
            return row[0] or path.stem, row[1] or ""
    except Exception:
        pass
    return path.stem, ""


def migrate_scenario(path: Path) -> MigrationResult:
    """Migrate a single scenario .db via load → export round-trip.

    Returns a `MigrationResult`. On error, the original file is left
    untouched (the loader fails before the exporter is invoked, and the
    exporter only deletes/recreates the file at its own success path).
    """
    path = Path(path)
    if not path.exists():
        return MigrationResult(path, False, "file does not exist")
    name, description = _peek_scenario_meta(path)
    # Import lazily so the migrator can be imported without pulling in the
    # entire model chain when callers only need its types.
    from utilities.scenario_loader import load_scenario
    from utilities.scenario_exporter import export_scenario
    try:
        state = load_scenario(path)
    except Exception as exc:
        return MigrationResult(path, False, f"load failed: {exc}", error=exc)
    try:
        export_scenario(state, path, scenario_name=name, description=description)
    except Exception as exc:
        return MigrationResult(path, False, f"export failed: {exc}", error=exc)
    return MigrationResult(path, True, "migrated")


def migrate_all(scenarios_dir: Path) -> list[MigrationResult]:
    """Migrate every `*.db` in `scenarios_dir`. Returns one result per file
    in alphabetical order."""
    scenarios_dir = Path(scenarios_dir)
    if not scenarios_dir.exists():
        return []
    results: list[MigrationResult] = []
    for path in sorted(scenarios_dir.glob("*.db")):
        results.append(migrate_scenario(path))
    return results
