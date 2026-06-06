#!/usr/bin/env python3
"""
Migrate Durenn Vail's mortal_state and knowledge_base in wardens_compact.db
to the typed Resource model.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utilities.scenario_loader import load_scenario
from utilities.scenario_exporter import export_scenario
from core.agent_core import (
    MortalAgentState, Resource, MortalNeed,
    KnowledgeBase, LocationFact, LocationQualityFact, RouteFact, ResourceFact,
)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "scenarios", "wardens_compact.db")
VAIL_NAME = "Durenn Vail"

NERAN_SURFACE_ID    = "2ac3f5fc-d4fd-4d72-be5b-eada9fb43e6d"
NERAN_ORBITAL_ID    = "b6e77481-97bd-4d4f-a948-4216d22522c3"
SETHIS_ORBITAL_ID   = "38474e57-8d40-4397-ade8-b9751cfa7d3c"
SETHIS_SURFACE_ID   = "ef5b9dc6-de3d-46a4-a9e4-6f8e1a6b76bc"


def migrate():
    state = load_scenario(DB_PATH)
    vail = next((m for m in state.mortals.values() if m.name == VAIL_NAME), None)
    if vail is None:
        print(f"ERROR: {VAIL_NAME} not found in {DB_PATH}")
        sys.exit(1)

    # ── mortal_state ──────────────────────────────────────────────────────
    vail.mortal_state = MortalAgentState(
        needs=[
            MortalNeed(
                name="indulgence",
                satisfaction=0.1,
                decay_rate=0.02,
                pressing_threshold=0.65,
                urgent_threshold=0.35,
            ),
            MortalNeed(
                name="trader",
                satisfaction=0.1,
                decay_rate=0.015,
                pressing_threshold=0.65,
                urgent_threshold=0.35,
            ),
        ],
        inventory=[
            Resource(
                resource_type="unobtanium",
                quantity=0.0,
                base_value=1.0,
                converts_to="credits",
                threshold=2.0,
                usable_for=["sell"],
                fills_need="trader",
            ),
            Resource(
                resource_type="credits",
                quantity=0.0,
                base_value=1.0,
                converts_to=None,
                threshold=1.0,
                usable_for=["spend"],
                fills_need="indulgence",
            ),
        ],
        action_cooldowns={},
    )

    # ── knowledge_base ──────────────────────────────────────────────────────
    vail.knowledge_base = KnowledgeBase(facts=[
        # Location pointers
        LocationFact(location_id=NERAN_SURFACE_ID,  label="Neran Surface"),
        LocationFact(location_id=NERAN_ORBITAL_ID,  label="Neran Orbital Ring"),
        LocationFact(location_id=SETHIS_ORBITAL_ID, label="Sethis Orbital Station"),
        LocationFact(location_id=SETHIS_SURFACE_ID, label="Sethis Surface"),

        # Resource fact
        ResourceFact(
            location_id=SETHIS_SURFACE_ID,
            resource_type="unobtanium",
            resource_yield=10.0,
        ),

        # Spend quality facts
        LocationQualityFact(location_id=NERAN_SURFACE_ID, quality=0.9, quality_type="spend"),
        LocationQualityFact(location_id=NERAN_ORBITAL_ID, quality=0.5, quality_type="spend"),

        # Sell quality facts (Neran is best for selling)
        LocationQualityFact(location_id=NERAN_SURFACE_ID, quality=0.9, quality_type="sell"),
        LocationQualityFact(location_id=SETHIS_SURFACE_ID, quality=0.2, quality_type="sell"),

        # Routes with ticks_cost
        RouteFact(
            from_id=NERAN_SURFACE_ID,
            to_id=SETHIS_SURFACE_ID,
            vehicle_type="merchant_vessel",
            ticks_cost=12,
        ),
        RouteFact(
            from_id=SETHIS_SURFACE_ID,
            to_id=NERAN_SURFACE_ID,
            vehicle_type="merchant_vessel",
            ticks_cost=12,
        ),
    ])

    from pathlib import Path
    from utilities.scenario_migrator import _peek_scenario_meta
    name, description = _peek_scenario_meta(Path(DB_PATH))
    export_scenario(state, DB_PATH, scenario_name=name, description=description)
    print(f"Migration complete. Patched {VAIL_NAME} in {DB_PATH}.")


if __name__ == "__main__":
    migrate()
