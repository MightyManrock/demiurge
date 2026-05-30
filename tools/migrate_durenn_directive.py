"""
Add a commerce Directive to Durenn Vail's merchant Pop and a matching DirectiveFact
to his KnowledgeBase. Also sets the Pop's home PopLocation.wealth to 0.6.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utilities.scenario_loader import load_scenario
from utilities.scenario_exporter import export_scenario
from core.universe_core import Directive
from core.agent_core import DirectiveFact


DB = "scenarios/wardens_compact.db"


def main() -> None:
    state = load_scenario(DB)

    # Find Durenn Vail
    vail = next(
        (m for m in state.mortals.values() if m.name == "Durenn Vail"),
        None,
    )
    if vail is None:
        print("ERROR: Durenn Vail not found in scenario.")
        sys.exit(1)

    # Resolve local pop — pop_milieu takes precedence when present in state.pops
    local_pop_id = str(vail.pop_milieu or vail.pop_id or "")
    pop = state.pops.get(local_pop_id)
    if pop is None and vail.pop_id:
        local_pop_id = str(vail.pop_id)
        pop = state.pops.get(local_pop_id)
    if pop is None:
        print(f"ERROR: No pop found for Durenn (pop_id={vail.pop_id}, pop_milieu={vail.pop_milieu}).")
        sys.exit(1)

    # Resolve the pop's home PopLocation
    pop_loc = state.locations.get(str(pop.current_location))
    if pop_loc is None or not hasattr(pop_loc, "wealth"):
        print(f"ERROR: PopLocation {pop.current_location} missing or has no wealth field.")
        sys.exit(1)

    # Create and attach Directive to the pop
    directive = Directive(
        directive_type="commerce",
        label="Maintain trade flow for the Merchant bloc",
        target_location_id=None,
        issued_at_tick=0,
    )
    pop.active_directives.append(directive)

    # Set initial wealth
    pop_loc.wealth = 0.6

    # Add DirectiveFact to Durenn's KnowledgeBase
    if vail.knowledge_base is None:
        from core.agent_core import KnowledgeBase
        vail.knowledge_base = KnowledgeBase()

    df = DirectiveFact(
        directive_id=str(directive.id),
        directive_type="commerce",
        satisfying_action="sell",
        target_pop_location_id=str(pop.current_location),
    )
    vail.knowledge_base.facts.append(df)

    export_scenario(state, DB)

    print(f"Pop          : {local_pop_id}")
    print(f"Directive    : {directive.id} ({directive.label})")
    print(f"DirectiveFact: directive_id={df.directive_id}, action={df.satisfying_action}")
    print(f"PopLocation  : {pop.current_location} → wealth={pop_loc.wealth:.2f}")
    print("Done.")


if __name__ == "__main__":
    main()
