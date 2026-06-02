"""
Build a minimal skeleton SimulationState for a fresh scenario.

One of each entity, default Pydantic values, dummy names. Everything is
pinned (visibility=1.0, pinned=True) so the player can see the placeholder
entities immediately in the builder UI.
"""
from __future__ import annotations

from core.onto_core import Demiurge, FootprintProfile, Luminary, Pantheon
from core.action_core import EssenceStockpile
from core.universe_core import (
    Civilization, Location, NotableMortal, Pop, PopLocation,
    SignificantLocation, SocialClass, Species, System, Universe, EntityAge, UniverseRules,
)
from logic.tick_logic import SimulationState


def build_skeleton_state(scenario_name: str, initialism: str) -> SimulationState:
    """Return a SimulationState containing one of each entity type with
    placeholder names. The Universe is named after `scenario_name`; its
    `save_name` carries `initialism` (used by the core game for save-file
    naming)."""

    # Overreal: Luminary, Pantheon, Demiurge
    luminary = Luminary(name="Luminary", domains={})
    pantheon = Pantheon(name="Pantheon", luminary_ids=[luminary.id])
    luminary.pantheon_id = pantheon.id

    demiurge = Demiurge(
        name="Demiurge",
        liege_luminary_ids=[luminary.id],
        footprint=FootprintProfile(),
    )

    # Spatial hierarchy: Galaxy → System → Planet → Settlement
    galaxy = Location(
        name="Galaxy", location_type="galaxy",
        visibility=1.0, pinned=True,
    )
    system = System(
        name="System", parent_id=galaxy.id,
        visibility=1.0, pinned=True,
    )
    planet = SignificantLocation(
        name="Planet", location_type="planet", parent_id=system.id,
        geo_tags=["geo:terrestrial"], atmo_tags=["atmo:nitrogen_oxygen"],
        visibility=1.0, pinned=True,
    )
    settlement = PopLocation(
        name="Settlement", location_type="pop_location", parent_id=planet.id,
        visibility=1.0, pinned=True,
    )
    galaxy.child_ids.append(system.id)
    system.child_ids.append(planet.id)
    planet.child_ids.append(settlement.id)

    # Species → Civilization → Pop → Notable Mortal
    species = Species(
        name="Species",
        lifespan_min=40.0, lifespan_max=80.0,
        origin_world_id=planet.id,
        visibility=1.0, pinned=True,
    )
    planet.species_ids.append(species.id)

    civ = Civilization(
        name="Civilization",
        origin_location_id=planet.id,
        primary_species_id=species.id,
        core_locs=[planet.id],
        visibility=1.0, pinned=True,
    )
    planet.civilization_ids.append(civ.id)

    pop = Pop(
        civilization_id=civ.id,
        species_id=species.id,
        social_class=SocialClass.COMMON,
        current_location=settlement.id,
        visibility=1.0, pinned=True,
    )
    civ.pop_ids.append(pop.id)
    settlement.pop_ids.append(pop.id)

    mortal = NotableMortal(
        name="Mortal",
        civilization_id=civ.id,
        species_id=species.id,
        pop_id=pop.id,
        home_location=planet.id,
        current_location=planet.id,
        visibility=1.0, pinned=True,
    )
    civ.notable_mortal_ids.append(mortal.id)
    pop.notable_mortal_ids.append(mortal.id)

    # Universe wraps it all
    universe = Universe(
        name=scenario_name,
        save_name=initialism,
        demiurge_id=demiurge.id,
        pantheon_id=pantheon.id,
        rules=UniverseRules(),
        child_ids=[galaxy.id],
        age=EntityAge(),
    )

    locations: dict[str, Location] = {
        str(galaxy.id):     galaxy,
        str(system.id):     system,
        str(planet.id):     planet,
        str(settlement.id): settlement,
    }

    return SimulationState(
        universe=universe,
        demiurge=demiurge,
        essence=EssenceStockpile(actual=1.0, suspicious=0.0, concealment_integrity=1.0),
        pantheon=pantheon,
        luminaries={str(luminary.id): luminary},
        locations=locations,
        civilizations={str(civ.id): civ},
        pops={str(pop.id): pop},
        mortals={str(mortal.id): mortal},
        species={str(species.id): species},
    )
