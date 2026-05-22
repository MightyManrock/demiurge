#!/usr/bin/env python3
"""
universe_core.py
Classes connected to the universe simulation.
"""

from __future__ import annotations
from pydantic import BaseModel, Field, model_validator
from typing import Optional
from enum import Enum
from uuid import UUID, uuid4

from core.agent_core import ProxiusGoal, TravelIntent

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
    # DEPRECATED: superseded by FootprintConstraint objects on Luminary/Pantheon.
    # Retained for backwards compatibility with old saves; will be removed in a future cleanup.
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
# LOCATION HIERARCHY
# Generic spatial containers for the universe.
# ─────────────────────────────────────────

class LocCondition(str, Enum):
    """Broad physical/ecological state."""
    THRIVING   = "thriving"
    STABLE     = "stable"
    STRESSED   = "stressed"
    DYING      = "dying"
    BARREN     = "barren"


class LocFootprint(BaseModel):
    """
    Local divine footprint accumulation on this specific location.
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


class CosmicCoordinates(BaseModel):
    """
    Relative position within the universe.
    Not a hard physics simulation — used for
    determining isolation, travel time between
    civilizations, and regional Luminary influence gradients.
    Galaxy-level coordinates use a much larger effective scale
    than system-level coordinates (see _GALAXY_SCALE in tick_logic).
    """
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


class Location(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str = ""
    location_type: str          # "galaxy", "system", "planet", "plane", "city" — free-form
    parent_id: Optional[UUID] = None
    child_ids: list[UUID] = Field(default_factory=list)
    traits: list[str] = Field(default_factory=list)
    condition: LocCondition = LocCondition.STABLE
    coordinates: CosmicCoordinates = Field(default_factory=CosmicCoordinates)
    visibility: float = 0.0   # 0.0 = unknown; 1.0 = fully in-window
    pinned: bool = False       # True = never decays (all starting-scenario locations)


class StarType(str, Enum):
    MAIN_SEQUENCE = "main_sequence"
    GIANT         = "giant"
    DWARF         = "dwarf"
    NEUTRON       = "neutron"
    OTHER         = "other"


class System(Location):
    location_type: str = "system"
    star_type: StarType = StarType.MAIN_SEQUENCE


class SignificantLocation(Location):
    """
    Planets, planes, and other mid-level locations that accumulate
    domain expression, local footprint, and host civilizations.
    """
    domain_expression: dict[str, float] = Field(default_factory=dict)
    local_footprint: LocFootprint = Field(default_factory=LocFootprint)

    # IDs of entities anchored to this location
    civilization_ids: list[UUID] = Field(default_factory=list)
    species_ids: list[UUID] = Field(default_factory=list)
    proxius_ids: list[UUID] = Field(default_factory=list)
    herald_ids: list[UUID] = Field(default_factory=list)

    # Physical character tags
    geo_tags: list[str] = Field(default_factory=list)
    # e.g. ["geo:terrestrial", "geo:arid"]
    atmo_tags: list[str] = Field(default_factory=list)
    # e.g. ["atmo:nitrogen_oxygen"]

    age: float = 0.0    # In-universe time units; scenario defines the scale


class PopLocation(Location):
    """Low-tier locations that house Pops (cities, towns, space stations, etc.)"""
    pop_ids: list[UUID] = Field(default_factory=list)
    # Travel/perception distance from the parent SignificantLocation's "core"
    # (surface settlement). 0 = the core itself. Higher values add to the
    # effective depth used by Scry and (future) travel mechanics.
    distance_from_core: int = 0
    travel_features: set[str] = Field(default_factory=set)


class TravelLocation(Location):
    """Ephemeral in-transit location. Lives in state.locations while occupied."""
    location_type: str = "travel_location"
    legs: dict[str, int] = Field(default_factory=dict)
    # Ordered dict: PopLocation UUID str → tick cost for leg starting at that waypoint.
    # Last entry always has value 0 — that key IS the destination.
    current_waypoint: str = ""   # UUID str of the leg currently in progress
    ticks_remaining: int = 0
    occupants: list[UUID] = Field(default_factory=list)


# ─────────────────────────────────────────
# SPECIES
# A named, categorized form of life.
# ─────────────────────────────────────────

class SpeciesCondition(str, Enum):
    THRIVING   = "thriving"
    STABLE     = "stable"
    ENDANGERED = "endangered"
    EXTINCT    = "extinct"


class Species(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str = ""
    origin_world_id: Optional[UUID] = None

    sapient: bool = True
    transplanted: bool = False  # True if the species exists away from its origin world

    lifespan_min: float  # In universe time units — death checks begin here
    lifespan_max: float  # Full probability reached at this age

    domain_tags: list[str] = Field(default_factory=list)
    # Innate divine domain affinity, e.g. ["domain:fire", "domain:growth"]

    bio_tags: list[str] = Field(default_factory=list)
    # e.g. ["bio:bipedal", "bio:warm_blooded", "bio:carbon_based"]

    condition: SpeciesCondition = SpeciesCondition.STABLE
    visibility: float = 0.0
    pinned: bool = False


# ─────────────────────────────────────────
# POPS
# Sub-civilizational population groups.
# ─────────────────────────────────────────

class SocialClass(str, Enum):
    WILD       = "wild"         # No social structure at all (pre-sapient pods, true wilderness).
    FERAL      = "feral"        # Partially or recently de-civilized — outside class but not pre-social.
    UNDERCLASS = "underclass"   # Slaves, serfs, the dispossessed
    COMMON     = "common"       # Peasants, laborers, the broad base
    ARTISAN    = "artisan"      # Skilled specialists and craftspeople
    MERCHANT   = "merchant"     # Traders and economic actors
    WARRIOR    = "warrior"      # Martial class
    PRIEST     = "priest"       # Religious and scholarly class
    ELITE      = "elite"        # Ruling class and aristocracy


class WildStratum(str, Enum):
    APEX     = "apex"      # Top predator / dominant organism
    HERD     = "herd"      # Prey species / herd animals
    CARRION  = "carrion"   # Scavengers
    SYMBIONT = "symbiont"  # Mutualistic partners
    PARASITE = "parasite"  # Parasitic/exploitative role


class Pop(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: Optional[str] = None
    # Optional authored identity. When set, the UI prefers it over the
    # computed stratum label everywhere ("The Bathy Cult" rather than
    # "Common"). When unset, displays fall back to the stratum.
    demiurge_authored: bool = False
    # True if the Demiurge was directly involved in this Pop's creation
    # (currently: splinter Pops formed by a Proxius preach_imago directive).
    # Grants the Demiurge naming rights — the pop's detail tab in the core
    # game shows a [ Rename ] button on demiurge-authored pops only.
    # Scenario-authored pops keep this False even when they have a `name`,
    # because their identity belongs to the scenario author, not the player.
    civilization_id: Optional[UUID] = None
    species_id: Optional[UUID] = None

    # Exactly one of these should be set depending on whether the species is sapient.
    social_class: Optional[SocialClass] = None
    wild_stratum: Optional[WildStratum] = None

    @property
    def stratum(self) -> str:
        # SocialClass.WILD is a sapience designation, not a meaningful
        # stratum; fall through to wild_stratum (APEX/HERD/etc.) when set.
        if self.social_class is not None and self.social_class != SocialClass.WILD:
            return self.social_class.value
        if self.wild_stratum is not None:
            return self.wild_stratum.value
        if self.social_class == SocialClass.WILD:
            return "wild"
        return "unknown"

    @property
    def is_wild(self) -> bool:
        """True if this Pop represents wild (non-sapient) creatures.
        Use this instead of `stratum == 'wild'` — the property's value
        depends on whether `wild_stratum` is also populated."""
        return (
            self.social_class == SocialClass.WILD
            or self.wild_stratum is not None
        )

    current_location: UUID       # PopLocation UUID; sub-world location

    # Fractional logarithmic size tracked internally; displayed as int.
    # Actual population ≈ 10 ** size_magnitude
    # e.g. 3.0 → ~1,000 | 6.0 → ~1,000,000 | 9.0 → ~1,000,000,000
    size_fractional: float = 6.0

    @property
    def size_magnitude(self) -> int:
        return int(self.size_fractional)

    # Authoritative source of belief/culture data for this group.
    # Civilization.dominant_beliefs and culture_tags are aggregates derived from Pops (and Govs).
    dominant_beliefs: dict[str, float] = Field(default_factory=dict)
    culture_tags: dict[str, float] = Field(default_factory=dict)

    # Traits introduced via Imago preaching — tracked separately from inherited culture_tags.
    rider_traits: dict[str, float] = Field(default_factory=dict)

    # Set while this Pop is the "goal target" of an active Preach Imāgō directive.
    # Auto-selected as goal_pop when its source Pop is re-targeted with the same Imāgō.
    preaching_imago_id: Optional[str] = None

    # Tick before which this Pop cannot be selected as a source target for Preach Imāgō.
    # Set to (current_tick + 10) when goal target status ends for any reason.
    preaching_goal_cooldown_until: int = 0

    notable_mortal_ids: list[UUID] = Field(default_factory=list)

    # Splinter lineage: parent_pop_id set if this Pop was split from another.
    parent_pop_id: Optional[UUID] = None
    child_pop_ids: list[UUID] = Field(default_factory=list)

    visibility: float = 0.0
    pinned: bool = False


# ─────────────────────────────────────────
# CIVILIZATION
# ─────────────────────────────────────────

class CivilizationScale(str, Enum):
    NON_SENTIENT  = "non_sentient"  # No mind in any meaningful sense (future-reserved).
    PRE_SAPIENT   = "pre_sapient"   # Aware but not yet civilized (wild populations).
    NASCENT       = "nascent"       # Pre-organized society
    TRIBAL        = "tribal"
    CITY_STATE    = "city_state"
    REGIONAL      = "regional"
    CONTINENTAL   = "continental"
    PLANETARY     = "planetary"
    INTERPLANETARY = "interplanetary"
    INTERSTELLAR  = "interstellar"
    INTERGALACTIC  = "intergalactic"


# Civilization scales considered "wild" — i.e., not real civilizations in the
# player-facing sense. Used by `is_wild_civ` to drive UI hiding and to gate
# discovery/scry from treating these as discoverable entities.
WILD_CIV_SCALES: frozenset = frozenset({
    CivilizationScale.PRE_SAPIENT,
    CivilizationScale.NON_SENTIENT,
})


def is_wild_civ(civ) -> bool:
    """True if `civ` is a 'wild' civilization (pre-sapient or non-sentient).

    Wild civs exist as bookkeeping for cross-pop contact math but are hidden
    from the player UI: no info page, not listed under their parent world,
    not discoverable via scry, and Pops attached to them render as 'wild'
    rather than as members of the civilization.

    Accepts a Civilization, an id+state pair via the helpers, or None."""
    if civ is None:
        return False
    return getattr(civ, "scale", None) in WILD_CIV_SCALES


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
    description: str = ""
    origin_location_id: Optional[UUID] = None
    scale: CivilizationScale = CivilizationScale.TRIBAL
    health: CivilizationHealth = Field(default_factory=CivilizationHealth)

    # Tick-computed weighted aggregate of Pop dominant_beliefs.
    # Written at end of Phase 2 each tick; do not set independently.
    # Float strength is 0.0–1.0; entries below BELIEF_FLOOR are pruned each tick.
    dominant_beliefs: dict[str, float] = Field(default_factory=dict)
    # e.g. {"domain:conflict": 0.8, "domain:memory": 0.3}

    # The institutional/official belief profile — what the educational system,
    # laws, and clergy actively reinforce. Seeded from dominant_beliefs at scenario
    # creation; drifts toward dominant_beliefs slowly each tick (rate ∝ cohesion).
    # Divergence from dominant_beliefs drives stability loss.
    established_beliefs: dict[str, float] = Field(default_factory=dict)

    # Tick-computed weighted aggregate of Pop culture_tags.
    # Written each tick; do not set independently.
    culture_tags: dict[str, float] = Field(default_factory=dict)

    # The institutional/official cultural profile — what customs, norms, and
    # institutions actively reinforce. Seeded from culture_tags at scenario
    # creation; drifts toward culture_tags slowly each tick (rate ∝ cohesion).
    # Pops receive a conformity nudge toward established_culture_tags each tick.
    established_culture_tags: dict[str, float] = Field(default_factory=dict)

    # Whether this civilization is aware of and actively
    # engaging with the divine — affects footprint
    # accumulation and certain Proxius action types.
    theistic: bool = True
    divine_awareness: float = Field(ge=0.0, le=1.0, default=0.3)
    # 0.0 = no concept of gods; 1.0 = constant direct interaction

    primary_species_id: Optional[UUID] = None
    pop_ids: list[UUID] = Field(default_factory=list)
    notable_mortal_ids: list[UUID] = Field(default_factory=list)

    # Locations considered "home territory" for this civilization.
    # Pops at locations NOT in this list are weighted down when computing
    # the civilization's aggregate dominant_beliefs and culture_tags.
    core_locs: list[UUID] = Field(default_factory=list)

    age: float = 0.0
    visibility: float = 0.0
    pinned: bool = False


# ─────────────────────────────────────────
# NOTABLE MORTALS — Proxii and Heralds
# ─────────────────────────────────────────

class MortalRole(str, Enum):
    PROXIUS = "proxius"
    HERALD  = "herald"
    OTHER   = "other"   # Person of interest with no divine appointment


class MortalProminence(str, Enum):
    """
    Discrete social role(s) that make a mortal notable.
    A mortal can hold several simultaneously.
    Used by the UI to explain why a mortal is visible.
    """
    LEADER   = "leader"    # Political or civic authority
    MILITARY = "military"  # Military commander
    PRIEST   = "priest"    # Religious figure
    MERCHANT = "merchant"  # Economic power
    REBEL    = "rebel"     # Opposed to the current order
    SCHOLAR  = "scholar"   # Keeper of knowledge or arcane lore
    APEX     = "apex"      # Notable member of non-sapient species
    NONE     = "none"      # No notable role


class MortalStatus(str, Enum):
    ACTIVE   = "active"
    DORMANT  = "dormant"     # Appointed but currently inactive
    DECEASED = "deceased"
    ASCENDED = "ascended"    # Rare — mortal elevated to something greater


class NotableMortal(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str = ""
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
    belief_tags: dict[str, float] = Field(default_factory=dict)     # Domain beliefs
    personal_tags: list[str] = Field(default_factory=list)
    # Status-y markers: exiled, imprisoned, fugitive, war_veteran, etc. Rendered
    # separately from `personal_tags` so descriptive traits (`stoic`, `scarred`)
    # don't get mixed with situational state.
    status_tags: list[str] = Field(default_factory=list)
    culture_tags: dict[str, float] = Field(default_factory=dict)
    # Cultural traits inherited from their civilization, e.g. {"culture:hierarchy": 0.8}

    species_id: Optional[UUID] = None
    pop_id: Optional[UUID] = None   # Pop this mortal belongs to; cleared when they age out

    # Tick at which the mortal was first elevated to each divine-appointment role.
    # Set once at appointment; never reset on dormancy/reactivation.
    # Used to compute wall-clock tenure and determine when they age out of pop_id.
    proxius_appointed_tick: Optional[int] = None
    herald_appointed_tick:  Optional[int] = None

    # Discrete social roles — explains in the UI why this mortal is notable.
    # An empty list (or [NONE]) means the mortal has no recognised public role.
    prominence_roles: list[MortalProminence] = Field(default_factory=list)

    # Numeric prominence 0.0–1.0. Drives discovery probability and the
    # always-visible threshold check. Set independently of prominence_roles
    # so role and mechanical weight can be tuned separately.
    prominence: float = Field(ge=0.0, le=1.0, default=0.5)

    # How clearly the Demiurge currently perceives this mortal.
    # Decays passively at mortal_visibility_decay_rate × (1 − prominence); refreshed by
    # scrying their world or taking direct action on them.
    visibility: float = Field(ge=0.0, le=1.0, default=0.0)
    # True while the Demiurge has this mortal actively in focus (prevents decay).
    # Starting-scenario mortals are pinned for the first 10 ticks, then released.
    pinned: bool = False

    # How faithfully they're currently pursuing their
    # patron's agenda vs. their own. 1.0 = fully aligned.
    alignment: float = Field(ge=0.0, le=1.0, default=0.8)

    chrono_age: float = 0.0  # Always increments each tick
    bio_age: float = 0.0     # Frozen while mortal is an active Proxius or Herald

    # Where this mortal was born / first recorded (fixed).
    # Where they are now (changes when moved to a new world or sub-world location).
    # Both hold a SignificantLocation UUID for now; will accommodate finer locations later.
    home_location: UUID
    current_location: UUID

    # True when the Pop this mortal originated from was fully absorbed into the goal Pop.
    # They may poorly represent the new Pop's cultural/belief profile.
    origin_pop_subsumed: bool = False

    active_goal: Optional["ProxiusGoal"] = None
    travel_intent: Optional[TravelIntent] = None

    # Captured narrative + tick from the most recent Audit Proxius action.
    # Surfaced in the mortal detail tab as part of the Proxius fog-of-war view.
    last_audit_text: Optional[str] = None
    last_audit_tick: Optional[int] = None

    @model_validator(mode="after")
    def _split_legacy_tags(self) -> "NotableMortal":
        """
        Migrate legacy prefixed strings in `personal_tags` into the right
        bucket. Historical scenarios mixed `status:senator` and
        `personal:ambitious` entries into a single list; this validator
        peels them apart so callers always see clean per-bucket lists.
        Bare strings (no prefix) stay in `personal_tags`.
        """
        if not self.personal_tags:
            return self
        new_personal: list[str] = []
        new_status: list[str] = list(self.status_tags)
        for tag in self.personal_tags:
            if tag.startswith("status:"):
                stripped = tag.split(":", 1)[1]
                if stripped not in new_status:
                    new_status.append(stripped)
            elif tag.startswith("personal:"):
                new_personal.append(tag.split(":", 1)[1])
            else:
                new_personal.append(tag)
        self.personal_tags = new_personal
        self.status_tags = new_status
        return self


# ─────────────────────────────────────────
# UNIVERSE — top-level container
# ─────────────────────────────────────────

class Universe(Location):
    location_type: str = "universe"
    name: str = "universe"
    save_name: str = "U"
    demiurge_id: UUID
    pantheon_id: UUID
    rules: UniverseRules = Field(default_factory=UniverseRules)

    # Running clock. Scenario defines what one unit means —
    # could be years, centuries, or abstract "eras."
    current_age: float = 0.0

    # Per-domain expression baseline. Keys are domain:xxx tags.
    # Missing keys default to 0.1 in _compute_universal_expression.
    universe_domain_expression: dict[str, float] = Field(default_factory=dict)

    # Aggregate event log — references to Event objects
    # (defined when we build the action layer).
    event_log_ids: list[UUID] = Field(default_factory=list)
