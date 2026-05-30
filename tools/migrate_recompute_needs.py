"""
Recompute MortalNeed parameters for all mortals from their current culture_tags.

Needs are initialized once and stored in the DB. When default parameters or
trait modifiers change in needs_config.py, existing mortals keep stale values.
This migration calls compute_need_profile() for every mortal and replaces their
need parameters (decay_rate, pressing_threshold, urgent_threshold) while
preserving current satisfaction levels and satiation_hold.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utilities.scenario_loader import load_scenario
from utilities.scenario_exporter import export_scenario
from logic.needs_config import compute_need_profile

DB = "scenarios/wardens_compact.db"


def main() -> None:
    state = load_scenario(DB)

    for mortal in state.mortals.values():
        if mortal.civilian_state is None:
            continue
        new_needs = compute_need_profile(mortal.culture_tags)
        new_by_name = {n.name: n for n in new_needs}

        for need in mortal.civilian_state.needs:
            fresh = new_by_name.get(need.name)
            if fresh is None:
                continue
            old = (need.decay_rate, need.pressing_threshold, need.urgent_threshold)
            need.decay_rate          = fresh.decay_rate
            need.pressing_threshold  = fresh.pressing_threshold
            need.urgent_threshold    = fresh.urgent_threshold
            new = (need.decay_rate, need.pressing_threshold, need.urgent_threshold)
            if old != new:
                print(f"  {mortal.name} / {need.name}: {old} -> {new}")

    export_scenario(state, DB)
    print("Done.")


if __name__ == "__main__":
    main()
