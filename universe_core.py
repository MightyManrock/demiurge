#!/usr/bin/env python3
"""
universe_core.py
Classes connected to the universe simulation.
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from uuid import UUID, uuid4


# ─────────────────────────────────────────
# UNIVERSE RULES
# Scenario-level mechanical contract.
# These are the thresholds and flags the evaluation
# layer actually checks — distinct from Luminary
# Constraints (which are the *source* of these rules).
# ─────────────────────────────────────────

class FootprintTolerances(BaseModel):
    """
    Per-category thresholds before Luminary disposition
    starts degrading. Set at scenario creation from
    Pantheon/Luminary constraints.
    Values are 0.0–1.0 matching FootprintProfile.
    """
    overt_miracles: float  = Field(ge=0.0, le=1.0, default=0.3)
    subtle_influence: float = Field(ge=0.0, le=1.0, default=0.8)
    proxius_activity: float  = Field(ge=0.0, le=1.0, default=0.6)
    direct_creation: float  = Field(ge=0.0, le=1.0, default=0.2)


class ProxiiPolicy(BaseModel):
    """
    How the Pantheon feels about Proxius usage.
    The 'one per world' norm is the default —
    scenarios can loosen or tighten this.
    """
    max_per_world: Optional[int] = 1        # None = no enforced limit
    total_cap: Optional[int] = None         # Pantheon-wide cap across all worlds
    tolerance_for_excess: float = Field(
        ge=0.0, le=1.0, default=0.3
    )
    # How much they'll let it slide before disposition degrades


class UniverseRules(BaseModel):
    """
    The mechanical contract for a given scenario.
    Derived from Pantheon/Luminary constraints at
    scenario setup; queried directly by the evaluation layer.
    """
    footprint_tolerances: FootprintTolerances = Field(
        default_factory=FootprintTolerances
    )
    proxii_policy: ProxiiPolicy = Field(
        default_factory=ProxiiPolicy
    )

    # Mortal awareness — whether civilizations can
    # meaningfully perceive and record divine intervention.
    # Affects footprint accumulation rate and certain
    # Luminary evaluations.
    mortals_can_perceive_divinity: bool = True

    # Whether the Demiurge is expected to actively
    # direct civilizational development toward Domain outcomes,
    # or merely maintain conditions.
    active_shaping_expected: bool = True

    # Scenario-specific flags for the evaluation layer.
    # e.g. ["torture_nexus", "isolationist_pantheon", "no_direct_creation"]
    special_flags: list[str] = Field(default_factory=list)

    # Freeform notes on unusual constraints not captured
    # structurally — to be formalized later as needed.
    notes: str = ""


# ─────────────────────────────────────────
# SPATIAL HIERARCHY
# ─────────────────────────────────────────

class CosmicCoordinates(BaseModel):
    """
    Relative position within the universe.
    Not a hard physics simulation — used for
    determining isolation, travel time between
    civilizations, and regional Luminary influence gradients.
    """
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


class Galaxy(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    coordinates: CosmicCoordinates = Field(default_factory=CosmicCoordinates)
    system_ids: list[UUID] = Field(default_factory=list)

    # Dominant domain influence in this region.
    # Could emerge from civilization beliefs or be
    # set by scenario — used for regional evaluation weighting.
    dominant_domain_tags: list[str] = Field(default_factory=list)


class StarType(str, Enum):
    MAIN_SEQUENCE = "main_sequence"
    GIANT         = "giant"
    DWARF         = "dwarf"
    NEUTRON       = "neutron"
    OTHER         = "other"


class System(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    galaxy_id: UUID
    coordinates: CosmicCoordinates = Field(default_factory=CosmicCoordinates)
    star_type: StarType = StarType.MAIN_SEQUENCE
    world_ids: list[UUID] = Field(default_factory=list)


# ─────────────────────────────────────────
# WORLD
# The primary locus of gameplay.
# ─────────────────────────────────────────

class WorldCondition(str, Enum):
    """Broad physical/ecological state."""
    THRIVING   = "thriving"
    STABLE     = "stable"
    STRESSED   = "stressed"
    DYING      = "dying"
    BARREN     = "barren"


class WorldFootprint(BaseModel):
    """
    Local divine footprint accumulation on this specific world.
    Separate from the Demiurge's universe-wide FootprintProfile —
    a world can be heavily touched without that being
    universally visible, depending on scenario rules.
    """
    overt_miracles: float  = Field(ge=0.0, le=1.0, default=0.0)
    subtle_influence: float = Field(ge=0.0, le=1.0, default=0.0)
    proxius_activity: float  = Field(ge=0.0, le=1.0, default=0.0)
    direct_creation: float  = Field(ge=0.0, le=1.0, default=0.0)

    def aggregate(self) -> float:
        return (
            self.overt_miracles +
            self.subtle_influence +
            self.proxius_activity +
            self.direct_creation
        ) / 4.0


class World(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    system_id: UUID
    condition: WorldCondition = WorldCondition.STABLE

    civilization_ids: list[UUID] = Field(default_factory=list)
    proxius_ids: list[UUID] = Field(default_factory=list)
    herald_ids: list[UUID] = Field(default_factory=list)

    local_footprint: WorldFootprint = Field(default_factory=WorldFootprint)

    # Domain tags that characterize this world's
    # current "spiritual flavor" — aggregate of its
    # civilizations' dominant beliefs and recent history.
    # Used for Luminary satisfaction evaluation.
    domain_expression: list[str] = Field(default_factory=list)

    age: float = 0.0        # In-universe time units; scenario defines the scale


# ─────────────────────────────────────────
# CIVILIZATION
# ─────────────────────────────────────────

class CivilizationScale(str, Enum):
    NASCENT       = "nascent"       # Pre-organized society
    TRIBAL        = "tribal"
    CITY_STATE    = "city_state"
    REGIONAL      = "regional"
    CONTINENTAL   = "continental"
    PLANETARY     = "planetary"
    INTERPLANETARY = "interplanetary"
    INTERSTELLAR  = "interstellar"


class CivilizationHealth(BaseModel):
    """
    Aggregate vitals. These are what most divine
    interventions actually move — either directly
    or through Proxii action.
    """
    stability: float  = Field(ge=0.0, le=1.0, default=0.5)
    prosperity: float = Field(ge=0.0, le=1.0, default=0.5)
    cohesion: float   = Field(ge=0.0, le=1.0, default=0.5)
    # cohesion: how unified vs. fractured internally

    def overall(self) -> float:
        return (self.stability + self.prosperity + self.cohesion) / 3.0


class Civilization(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    world_id: UUID
    scale: CivilizationScale = CivilizationScale.TRIBAL
    health: CivilizationHealth = Field(default_factory=CivilizationHealth)

    # Which Domain tags this civilization currently
    # expresses through its beliefs, practices, conflicts.
    # This is the primary signal Luminaries read to judge
    # whether your universe is reflecting their Domains.
    dominant_beliefs: list[str] = Field(default_factory=list)
    # e.g. ["domain:war", "domain:trade", "domain:ancestor_worship"]

    # Whether this civilization is aware of and actively
    # engaging with the divine — affects footprint
    # accumulation and certain Proxius action types.
    theistic: bool = True
    divine_awareness: float = Field(ge=0.0, le=1.0, default=0.3)
    # 0.0 = no concept of gods; 1.0 = constant direct interaction

    notable_mortal_ids: list[UUID] = Field(default_factory=list)
    age: float = 0.0


# ─────────────────────────────────────────
# NOTABLE MORTALS — Proxii and Heralds
# ─────────────────────────────────────────

class MortalRole(str, Enum):
    PROXIUS   = "proxius"
    HERALD  = "herald"
    OTHER   = "other"   # Person of interest with no divine appointment


class MortalStatus(str, Enum):
    ACTIVE   = "active"
    DORMANT  = "dormant"     # Appointed but currently inactive
    DECEASED = "deceased"
    ASCENDED = "ascended"    # Rare — mortal elevated to something greater


class NotableMortal(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    world_id: UUID
    civilization_id: Optional[UUID] = None
    role: MortalRole = MortalRole.OTHER
    status: MortalStatus = MortalStatus.ACTIVE

    # For Proxii — which Demiurge appointed them
    appointed_by_demiurge: Optional[UUID] = None

    # For Heralds — which Luminary appointed them
    appointed_by_luminary: Optional[UUID] = None

    # Personal domain/value tags — what this mortal
    # actually cares about, which may or may not align
    # with their patron's Domains.
    personal_tags: list[str] = Field(default_factory=list)

    # How faithfully they're currently pursuing their
    # patron's agenda vs. their own. 1.0 = fully aligned.
    alignment: float = Field(ge=0.0, le=1.0, default=0.8)

    age: float = 0.0


# ─────────────────────────────────────────
# UNIVERSE — top-level container
# ─────────────────────────────────────────

class Universe(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    demiurge_id: UUID
    pantheon_id: UUID
    rules: UniverseRules = Field(default_factory=UniverseRules)

    galaxy_ids: list[UUID] = Field(default_factory=list)

    # Running clock. Scenario defines what one unit means —
    # could be years, centuries, or abstract "eras."
    current_age: float = 0.0

    # Aggregate event log — references to Event objects
    # (defined when we build the action layer).
    event_log_ids: list[UUID] = Field(default_factory=list)
