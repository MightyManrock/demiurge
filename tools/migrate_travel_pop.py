"""
Create Vail's Crew — a vessel crew Pop for Durenn's merchant_vessel.

Changes:
- Creates a new Pop (social_class=common, occupation=transport, asset_crew_for="merchant_vessel")
  at Neran Surface, seeded with culture_tags and beliefs from the Neran Orbital Ring transport pop.
- Bidirectional links (base=0.6): crew <-> Neran Surface transport pop, crew <-> Neran Orbital Ring transport pop.
- size_fractional = 1.72 (~52 people).
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from uuid import uuid4
from utilities.scenario_loader import load_scenario
from utilities.scenario_exporter import export_scenario
from core.universe_core import Pop, SocialClass

DB = "scenarios/wardens_compact.db"

NERAN_SURFACE_ID  = "2ac3f5fc-d4fd-4d72-be5b-eada9fb43e6d"
NERAN_ORBITAL_ID  = "b6e77481-97bd-4d4f-a948-4216d22522c3"


def main() -> None:
    state = load_scenario(DB)

    # ── Find transport pops ─────────────────────────────────────────────────
    neran_surface_transport = next(
        (p for p in state.pops.values()
         if p.occupation == "transport"
         and str(p.current_location) == NERAN_SURFACE_ID),
        None,
    )
    neran_orbital_transport = next(
        (p for p in state.pops.values()
         if p.occupation == "transport"
         and str(p.current_location) == NERAN_ORBITAL_ID),
        None,
    )

    if neran_surface_transport is None:
        print("ERROR: Neran Surface transport pop not found.")
        sys.exit(1)
    if neran_orbital_transport is None:
        print("ERROR: Neran Orbital Ring transport pop not found.")
        sys.exit(1)

    print(f"Neran Surface transport: {neran_surface_transport.id}")
    print(f"Neran Orbital transport: {neran_orbital_transport.id}")

    # ── Check crew doesn't already exist ────────────────────────────────────
    existing_crew = next(
        (p for p in state.pops.values() if p.asset_crew_for == "merchant_vessel"),
        None,
    )
    if existing_crew is not None:
        print(f"Crew pop already exists: {existing_crew.id} ({existing_crew.name!r}). Aborting.")
        sys.exit(0)

    # ── Create crew Pop ──────────────────────────────────────────────────────
    from uuid import UUID
    crew = Pop(
        id=uuid4(),
        name="Vail's Crew",
        demiurge_authored=False,
        social_class=SocialClass.COMMON,
        occupation="transport",
        asset_crew_for="merchant_vessel",
        current_location=UUID(NERAN_SURFACE_ID),
        size_fractional=1.72,
        culture_tags=dict(neran_orbital_transport.culture_tags),
        dominant_beliefs=dict(neran_orbital_transport.dominant_beliefs),
    )
    print(f"Created crew pop: {crew.id} (size_fractional=1.72)")
    print(f"  culture_tags: {crew.culture_tags}")

    # ── Bidirectional links ──────────────────────────────────────────────────
    crew_id_str = str(crew.id)

    crew.linked_pop_ids[str(neran_surface_transport.id)] = 0.6
    neran_surface_transport.linked_pop_ids[crew_id_str] = 0.6
    print(f"Linked crew <-> Neran Surface transport (base=0.6)")

    crew.linked_pop_ids[str(neran_orbital_transport.id)] = 0.6
    neran_orbital_transport.linked_pop_ids[crew_id_str] = 0.6
    print(f"Linked crew <-> Neran Orbital transport (base=0.6)")

    # ── Register in state ────────────────────────────────────────────────────
    state.pops[crew_id_str] = crew

    export_scenario(state, DB)
    print("Done.")


if __name__ == "__main__":
    main()
