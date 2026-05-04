#!/usr/bin/env python3
"""
Rebuild all databases from source data.

  python rebuild_databases.py

Deletes core/core.db and rebuilds it by instantiating each registry
(domain, culture, imago) — each calls _ensure_db() on init and writes
its tables from hardcoded source data.  Then rebuilds the default scenario.
"""

from pathlib import Path

CORE_DB = Path(__file__).parent / "core" / "core.db"


def rebuild_core_db() -> None:
    print("Rebuilding core/core.db ...")
    if CORE_DB.exists():
        CORE_DB.unlink()
        print("  Deleted existing core.db")

    from utilities.domain_registry import get_registry as get_domain_registry
    from utilities.culture_registry import get_registry as get_culture_registry
    from utilities.imago_registry   import get_registry as get_imago_registry

    get_domain_registry()
    print("  Domain registry written")
    get_culture_registry()
    print("  Culture registry written")
    get_imago_registry()
    print("  Imago registry written")


def rebuild_scenario_db() -> None:
    print("Rebuilding scenarios/wardens_compact.db ...")
    from utilities.scenario_exporter import main
    main()


if __name__ == "__main__":
    rebuild_core_db()
    rebuild_scenario_db()
    print("Done.")
