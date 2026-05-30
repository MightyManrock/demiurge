"""
Add 'values:' prefix to bare canonical value tags in all pops and mortals.

Bare tags like 'sedentism', 'solidarity', 'pragmatism' etc. are stored in the DB
without their canonical namespace prefix. This migration renames them to the proper
'values:sedentism', 'values:solidarity', etc. format so needs_config trait modifiers
and sedentism-aware scoring work correctly.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utilities.scenario_loader import load_scenario
from utilities.scenario_exporter import export_scenario

DB = "scenarios/wardens_compact.db"

# Canonical values: tags that may be stored without prefix in old data
VALUES_TAGS = {
    "honesty", "adaptability", "moderation", "indulgence", "charity",
    "prosperity", "ambition", "humility", "wit", "sincerity", "patience",
    "tenacity", "idealism", "pragmatism", "erudition", "folk_wisdom",
    "honor", "prowess", "hierarchy", "sedentism", "xenophilia",
    "meritocracy", "solidarity", "autonomy",
}


def _fix_tags(tags: dict[str, float]) -> tuple[dict[str, float], int]:
    """Return (fixed_dict, n_changed)."""
    fixed = {}
    changed = 0
    for k, v in tags.items():
        if k in VALUES_TAGS:
            fixed[f"values:{k}"] = v
            changed += 1
        else:
            fixed[k] = v
    return fixed, changed


def main() -> None:
    state = load_scenario(DB)
    total = 0

    for pop in state.pops.values():
        fixed, n = _fix_tags(pop.culture_tags)
        if n:
            pop.culture_tags = fixed
            total += n
            print(f"Pop {pop.name or str(pop.id)[:8]}: {n} tag(s) prefixed")

    for mortal in state.mortals.values():
        fixed, n = _fix_tags(mortal.culture_tags)
        if n:
            mortal.culture_tags = fixed
            total += n
            print(f"Mortal {mortal.name}: {n} tag(s) prefixed")

    if total == 0:
        print("No bare tags found — nothing to do.")
        return

    export_scenario(state, DB)
    print(f"Done. {total} tag(s) prefixed total.")


if __name__ == "__main__":
    main()
