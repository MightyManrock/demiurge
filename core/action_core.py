#!/usr/bin/env python3
"""
action_core.py
Classes and code handling actions performed by the
Demiurge.
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, Union
from enum import Enum
from uuid import UUID, uuid4
from dataclasses import dataclass


# ─────────────────────────────────────────
# DIVINE ESSENCE
# ─────────────────────────────────────────

class EssenceStockpile(BaseModel):
    """
    Divine Essence — raw conceptual power drawn primarily
    from the Underreal. Split into actual vs. apparent
    because concealment is an active, maintained gap
    between the two.

    Luminaries evaluate apparent, not actual.
    The player manages both.
    """
    actual: float = Field(ge=0.0, default=0.0)
    apparent: float = Field(ge=0.0, default=0.0)
    # apparent <= actual always; enforced on mutation

    concealment_integrity: float = Field(ge=0.0, le=1.0, default=1.0)
    # 1.0 = perfectly hidden; 0.0 = fully exposed
    # Degrades on: essence spending, Luminary scrutiny,
    # Herald investigation, passage of time without maintenance

    def hidden_amount(self) -> float:
        """How much is successfully concealed."""
        return self.actual - self.apparent

    def exposure_risk(self) -> float:
        """
        Rough probability a Luminary audit reveals
        more than apparent. Rises as concealment degrades
        and hidden amount grows.
        """
        if self.actual == 0.0:
            return 0.0
        hidden_ratio = self.hidden_amount() / self.actual
        return hidden_ratio * (1.0 - self.concealment_integrity)


# ─────────────────────────────────────────
# ACTION TAXONOMY
# ─────────────────────────────────────────

class ActionCategory(str, Enum):
    DIRECT_CREATION   = "direct_creation"
    OVERT_MIRACLE     = "overt_miracle"
    SUBTLE_INFLUENCE  = "subtle_influence"
    PROXIUS_DIRECTION  = "proxius_direction"
    OBSERVATION       = "observation"
    HERALD_INTERACTION = "herald_interaction"
    LUMINARY_RELATIONS = "luminary_relations"
    UNDERREAL         = "underreal"
    SELF_REFINEMENT   = "self_refinement"


class TargetType(str, Enum):
    UNIVERSE      = "universe"
    GALAXY        = "galaxy"
    SYSTEM        = "system"
    WORLD         = "world"
    CIVILIZATION  = "civilization"
    MORTAL        = "mortal"
    SPECIES       = "species"
    LUMINARY      = "luminary"
    UNDERREAL     = "underreal"


class ActionReliability(str, Enum):
    """
    How predictable the outcome is.
    Subtle and Underreal actions are inherently less certain.
    Direct creation is essentially guaranteed.
    """
    CERTAIN     = "certain"     # Outcome is what you intended
    PROBABLE    = "probable"    # Usually works; small chance of partial effect
    UNCERTAIN   = "uncertain"   # Meaningful chance of unintended outcome
    CHAOTIC     = "chaotic"     # Underreal salvage — outcome is genuinely unpredictable


# ─────────────────────────────────────────
# FOOTPRINT COST
# Maps to FootprintProfile categories.
# ─────────────────────────────────────────

class FootprintCost(BaseModel):
    """
    How much divine footprint an action generates,
    per category. Most actions only touch one or two.
    Additive with existing footprint on target world/universe.
    """
    overt_miracles:  float = Field(ge=0.0, default=0.0)
    subtle_influence: float = Field(ge=0.0, default=0.0)
    proxius_activity:  float = Field(ge=0.0, default=0.0)
    direct_creation:  float = Field(ge=0.0, default=0.0)

    def total(self) -> float:
        return (
            self.overt_miracles +
            self.subtle_influence +
            self.proxius_activity +
            self.direct_creation
        )

# ─────────────────────────────────────────
# SHARED PRIMITIVES
# ─────────────────────────────────────────

class DomainVector(BaseModel):
    """
    A directional push toward or away from a Domain tag.
    The basic unit of 'what you're trying to change.'
    Most intents contain one or more of these.
    """
    domain_tag: str
    # e.g. "domain:war", "domain:trade", "domain:ancestor_worship"

    direction: float = Field(ge=-1.0, le=1.0)
    # +1.0 = strongly toward this domain
    # -1.0 = strongly away from it
    # 0.5  = gentle nudge toward

    notes: str = ""
    # Human-readable rationale — also seeds narrative generation


class Framing(str, Enum):
    """
    How the intent is meant to appear to mortals.
    Affects divine_awareness accumulation and
    how mortals interpret and retell what happened.
    """
    NATURAL       = "natural"       # Should seem like it arose organically
    PROPHETIC     = "prophetic"     # Framed as divine will or destiny
    INSPIRATIONAL = "inspirational" # A good idea that occurred to someone
    THREATENING   = "threatening"   # A warning with teeth
    AMBIGUOUS     = "ambiguous"     # Deliberately unclear — let them wonder


# ─────────────────────────────────────────
# INTENT TYPES BY ACTION CATEGORY
# ─────────────────────────────────────────

class WhisperIntent(BaseModel):
    """
    For: whisper, shape_dream
    The core of a subtle influence on a specific mortal.
    """
    concept: str
    # Plain statement of what you're planting.
    # e.g. "The eastern tribes could be united under a single leader"
    #      "Your gods have abandoned you — seek new ones"
    #      "The merchant guild is planning to betray the king"

    domain_vectors: list[DomainVector] = Field(default_factory=list)
    # What Domain shifts this is meant to eventually produce
    # in the wider civilization, through this mortal

    framing: Framing = Framing.INSPIRATIONAL

    urgency: float = Field(ge=0.0, le=1.0, default=0.3)
    # How pressing the message feels to the recipient.
    # High urgency is more memorable but more obviously supernatural.

    target_audience: Optional[str] = None
    # Who the mortal is meant to carry this to, if anyone.
    # e.g. "their ruler", "their congregation", "their children"

    imago_node_id: Optional[str] = None
    # The Imago node (e.g. "change:t1:wheel") that framed this action, if any.


class OmenIntent(BaseModel):
    """
    For: manifest_omen, divine_manifestation
    Omens are deliberately interpretable — you set
    the signal, mortals supply the meaning.
    """
    sign_description: str
    # What physically/supernaturally occurs.
    # e.g. "A red star appears and burns for seven nights"
    #      "All rivers in the region run backward for one day"

    intended_interpretation: str
    # What you *want* them to conclude — may differ from actual outcome
    # depending on reliability roll and civilization's existing beliefs

    domain_vectors: list[DomainVector] = Field(default_factory=list)
    framing: Framing = Framing.PROPHETIC

    civilization_scope: Optional[UUID] = None
    # Which civilization this is aimed at.
    # None = world-wide, multiple civilizations see it
    # and may interpret it very differently

    imago_node_id: Optional[str] = None


class ProbabilityNudgeIntent(BaseModel):
    """
    For: nudge_probability
    You're tilting odds around a specific coming event,
    not dictating the outcome.
    """
    event_description: str
    # What event you're influencing.
    # e.g. "The succession conflict following King Aldric's death"
    #      "The harvest season in the Keth valley"
    #      "The military campaign the Suric Confederation is planning"

    desired_outcome: str
    # What you want to be more likely.
    # e.g. "The reformist faction takes power"
    #      "The harvest fails, creating desperation and religious fervor"

    domain_vectors: list[DomainVector] = Field(default_factory=list)

    nudge_strength: float = Field(ge=0.0, le=1.0, default=0.4)
    # How hard you're pushing. Higher = more footprint,
    # more likely to work, more obviously unnatural if noticed.

    imago_node_id: Optional[str] = None


class DevelopmentIntent(BaseModel):
    """
    For: accelerate_development, and by extension
    any long-duration civilization-shaping action.
    """
    domain_vectors: list[DomainVector]
    # What you want the civilization to develop toward/away from.
    # e.g. toward "domain:philosophy", away from "domain:conquest"

    target_aspect: str
    # Which part of the civilization is the lever.
    # e.g. "religious institutions", "merchant class",
    #      "military doctrine", "oral tradition"

    framing: Framing = Framing.NATURAL

    duration_estimate: Optional[float] = None
    # In universe time units — how long you expect this to take
    # before meaningful domain_expression shift is visible.
    # Informs the evaluation layer's patience modeling.

    imago_node_id: Optional[str] = None


class ProxiusDirectiveIntent(BaseModel):
    """
    For: issue_directive
    Deliberately loose — a Proxius interprets your goal
    through their own alignment and personal tags.
    The gap between your intent and their execution
    is where interesting things happen.
    """
    goal_statement: str = ""

    domain_vectors: list[DomainVector] = Field(default_factory=list)
    # The underlying Domain agenda this serves

    latitude: float = Field(ge=0.0, le=1.0, default=0.5)
    # How much interpretive freedom you're granting.
    # 0.0 = specific instruction (less alignment drift, more footprint if they comply)
    # 1.0 = vague mandate (high drift potential, very deniable)

    priority: float = Field(ge=0.0, le=1.0, default=0.5)
    # How urgently you need this done.
    # High priority pushes a Proxius to act faster and more
    # overtly — potentially generating unwanted footprint.

    target_civilization_id: Optional[UUID] = None
    # The civilization the Proxius should promote domain beliefs within.
    # Required when domain_vectors is non-empty; ignored otherwise.

    target_pop_id: Optional[UUID] = None
    # The source Pop (Pop A) the Proxius will preach to directly.
    # When set, PROMOTE_DOMAIN targets this Pop rather than the whole civilization.

    constraints: list[str] = Field(default_factory=list)
    # Explicit limits on method.
    # e.g. ["do not kill the king directly", "do not reveal your divine appointment"]
    # A drifting Proxius may ignore these.

    imago_node_id: Optional[str] = None


class LuminaryPetitionIntent(BaseModel):
    """
    For: report_to_luminary, petition_constraint_relaxation,
    dispute_demand, petition_luminary_herald
    The framing of what you say to your liege matters —
    this feeds directly into the dialogue system.
    """
    subject: str
    # What you're reporting on, petitioning about, or disputing.
    # e.g. "The current state of the Verath civilization"
    #      "The footprint tolerance on overt miracles"
    #      "Luminary Cassiel's Herald is actively destabilizing my work"

    your_position: str
    # What you want them to understand or agree to.

    tone: str
    # Feeds speech act queries.
    # e.g. "deferential", "confident", "urgent", "contrite", "firm"

    supporting_evidence: list[str] = Field(default_factory=list)
    # References to events or universe state you're citing.
    # e.g. ["the_verath_reformation", "herald_cassiel_interference_at_arnoth"]
    # These are event log keys — the dialogue system can
    # pull narrative notes from them for context.


class EssenceHarvestIntent(BaseModel):
    """
    For: harvest_essence, investigate_underreal
    The Underreal isn't a tap you just open —
    you're navigating something with its own character.
    """
    target_concept_type: Optional[str] = None
    # What kind of abandoned material you're looking for.
    # e.g. "failed civilizations", "unrealized species",
    #      "discarded divine experiments"
    # None = opportunistic — take what's available

    concealment_priority: float = Field(ge=0.0, le=1.0, default=0.7)
    # How carefully you're hiding this operation.
    # High = slower yield, lower concealment_impact
    # Low = faster yield, riskier apparent stockpile growth

    yield_target: Optional[float] = None
    # How much Essence you're trying to accumulate
    # before stopping. None = harvest until interrupted.


class SalvageIntent(BaseModel):
    """
    For: salvage_concept
    You have some influence over what you pull up,
    but the Underreal resists clean intention.
    """
    desired_concept: str
    # What you're hoping to find.
    # e.g. "a pre-Awakening civilization with no divine awareness"
    #      "a species adapted to extreme cold"
    #      "a philosophical tradition centered on self-determination"

    target_world_id: UUID
    # Where you intend to introduce what you salvage

    domain_vectors: list[DomainVector] = Field(default_factory=list)
    # What Domain expression you hope this produces

    acceptable_chaos_level: float = Field(ge=0.0, le=1.0, default=0.5)
    # How much unpredictability you're willing to absorb.
    # Affects the outcome roll — low tolerance means
    # you pull back if the salvage is too strange,
    # burning Essence without result.

    imago_node_id: Optional[str] = None


class SeedWorldIntent(BaseModel):
    """
    For: seed_world
    You name and define the life you're introducing.
    Non-sapient by default — sapience requires uplift later
    or can be seeded directly at higher footprint cost.
    """
    species_name: str
    lifespan_min: float
    lifespan_max: float
    sapient: bool = False
    bio_tags: list[str] = Field(default_factory=list)
    # e.g. ["bio:bipedal", "bio:warm_blooded", "bio:nocturnal"]


class UpliftSpeciesIntent(BaseModel):
    """
    For: uplift_species
    Catalyze a non-sapient species toward full sapience.
    The domain_vectors shape what kind of sapience emerges.
    """
    species_id: UUID
    domain_vectors: list[DomainVector] = Field(default_factory=list)
    framing: Framing = Framing.NATURAL
    imago_node_id: Optional[str] = None


class ExploreBeliefIntent(BaseModel):
    """
    For: explore_beliefs
    The Demiurge turns their awareness inward and meditates on a Domain,
    accumulating Revelation in that Domain's pool each tick.
    """
    domain_tag: str
    # The canonical domain:... tag being researched.


class RevealImagoIntent(BaseModel):
    """
    For: reveal_imago
    The Demiurge spends accumulated Revelation from a Domain pool to
    permanently internalize an Imago node from that Domain's tree.
    """
    domain_tag: str  # which domain's pool to draw from
    node_id: str     # the specific Imago node to unlock


class CommissionInquiryIntent(BaseModel):
    """
    For: commission_inquiry
    The Demiurge directs a Proxius to conduct ongoing research into a Domain,
    funneling a small stream of Revelation into the Demiurge's pool each tick.
    """
    proxius_id: UUID
    domain_tag: str  # domain:... tag to research


class ChangeAffiliatedDomainsIntent(BaseModel):
    """
    For: change_affiliated_domains
    The Demiurge swaps one affiliated domain for another.
    Any canonical domain may be chosen as the replacement.
    """
    old_domain: str
    # The domain:... tag being dropped from affiliated_domains.
    new_domain: str
    # The domain:... tag being added to affiliated_domains.


class ScryScope(str, Enum):
    WORLD    = "world"
    SYSTEM   = "system"
    GALAXY   = "galaxy"
    UNIVERSE = "universe"


class ScryIntent(BaseModel):
    """
    For: scry
    The scope at which the Demiurge surveys the cosmos.
    Broader scopes cost more footprint but can reveal more entity types.
    """
    scope: ScryScope = ScryScope.WORLD


class WeighCivilizationIntent(BaseModel):
    """
    For: weigh_civilization
    Snapshot of civilization state at queue time; used to compute per-field
    deltas in the tick-log report.
    """
    beliefs_snapshot: dict[str, float] = Field(default_factory=dict)
    culture_snapshot: dict[str, float] = Field(default_factory=dict)
    health_snapshot: dict[str, float] = Field(default_factory=dict)
    divine_awareness_snapshot: float = 0.0


# ─────────────────────────────────────────
# UNIFIED INTENT TYPE
# ActionInstance.intent replaces .parameters
# ─────────────────────────────────────────

ActionIntent = Union[
    WhisperIntent,
    OmenIntent,
    ProbabilityNudgeIntent,
    DevelopmentIntent,
    ProxiusDirectiveIntent,
    LuminaryPetitionIntent,
    EssenceHarvestIntent,
    SalvageIntent,
    SeedWorldIntent,
    UpliftSpeciesIntent,
    ExploreBeliefIntent,
    RevealImagoIntent,
    CommissionInquiryIntent,
    ChangeAffiliatedDomainsIntent,
    ScryIntent,
    WeighCivilizationIntent,
]


# ─────────────────────────────────────────
# ACTION DEFINITION
# Static — what an action *is*.
# Scenarios can override costs on specific actions.
# ─────────────────────────────────────────

class ActionDefinition(BaseModel):
    """
    A type of thing the Demiurge can do.
    Instantiated once per action type; referenced by
    ActionInstance when the player actually uses it.
    """
    id: UUID = Field(default_factory=uuid4)
    name: str
    category: ActionCategory
    description: str

    valid_targets: list[TargetType]
    reliability: ActionReliability = ActionReliability.CERTAIN

    # Costs
    footprint_cost: FootprintCost = Field(default_factory=FootprintCost)
    essence_cost: float = 0.0
    # Negative = this action *yields* Essence (Underreal harvesting)

    # Concealment impact — some actions are harder to hide
    # even if they don't generate standard footprint.
    # Particularly relevant for Essence accumulation.
    concealment_impact: float = Field(ge=0.0, default=0.0)
    # Added to apparent stockpile on execution if Essence is gained

    # Whether this action requires a Proxius to be appointed
    # on the target world first.
    requires_proxius: bool = False

    # Tags for evaluation layer and dialogue system queries.
    tags: list[str] = Field(default_factory=list)


# ─────────────────────────────────────────
# STANDARD ACTION LIBRARY
# ─────────────────────────────────────────

def build_action_library() -> dict[str, ActionDefinition]:
    from utilities.action_registry import get_registry as get_action_registry
    return get_action_registry().build_action_library()


# ─────────────────────────────────────────
# ACTION INSTANCE
# A specific use of an action by the player.
# ─────────────────────────────────────────

class ActionInstance(BaseModel):
    """
    A single use of an ActionDefinition against a specific target.
    Recorded in the event log; evaluated by the action layer.
    """
    id: UUID = Field(default_factory=uuid4)
    action_definition_id: UUID
    target_type: TargetType
    target_id: Optional[UUID]
    # None for UNDERREAL targets which have no UUID in the world model

    timestamp: float        # Universe age at time of action
    demiurge_id: UUID
    proxius_id: Optional[UUID] = None
    # If executed through a Proxius — changes footprint category routing

    intent: Optional[ActionIntent] = None
    # None for actions that don't require it (scry, audit_proxius, dismiss_proxius)


# ─────────────────────────────────────────
# ONGOING ACTION
# ─────────────────────────────────────────

class OngoingAction(BaseModel):
    """
    A persistent action that auto-executes each tick until explicitly stopped.
    Keyed by ActionCategory.value in SimulationState.ongoing_actions.
    """
    action_key: str
    action_definition_id: UUID
    target_type: TargetType
    target_id: Optional[UUID] = None
    proxius_id: Optional[UUID] = None
    intent: Optional[ActionIntent] = None
    ticks_active: int = 0
    executed_ticks: int = 0
    started_at_tick: int = 0


# ─────────────────────────────────────────
# ACTION RESULT
# What actually happened.
# ─────────────────────────────────────────

class MutationType(str, Enum):
    """What kind of state change this mutation represents."""
    FOOTPRINT_CHANGE       = "footprint_change"
    ESSENCE_CHANGE         = "essence_change"
    CONCEALMENT_CHANGE     = "concealment_change"
    DISPOSITION_CHANGE     = "disposition_change"
    CIVILIZATION_STAT      = "civilization_stat"
    WORLD_CONDITION        = "world_condition"
    MORTAL_ALIGNMENT       = "mortal_alignment"
    MORTAL_STATUS          = "mortal_status"
    MORTAL_AGE             = "mortal_age"
    MORTAL_VISIBILITY      = "mortal_visibility"
    BELIEF_SHIFT           = "belief_shift"
    DOMAIN_EXPRESSION      = "domain_expression"
    PROXIUS_APPOINTED        = "proxius_appointed"
    PROXIUS_DISMISSED        = "proxius_dismissed"
    ENTITY_CREATED         = "entity_created"
    ENTITY_DESTROYED       = "entity_destroyed"
    EXILED_TO_UNDERREAL    = "exiled_to_underreal"
    SALVAGED_FROM_UNDERREAL = "salvaged_from_underreal"
    SPECIES_CREATED        = "species_created"
    SPECIES_UPLIFTED       = "species_uplifted"
    SPECIES_CONDITION      = "species_condition"
    DEMIURGE_UNLOCK        = "demiurge_unlock"
    AFFILIATED_DOMAIN_CHANGE = "affiliated_domain_change"
    EVENT_EMITTED          = "event_emitted"
    ENTITY_VISIBILITY      = "entity_visibility"   # locations, civilizations, species
    PROXIUS_GOAL_SET       = "proxius_goal_set"    # new_value = ProxiusGoal instance
    PROXIUS_GOAL_CLEARED   = "proxius_goal_cleared"
    PROXIUS_AUDITED        = "proxius_audited"      # transient; marks mortal audited this tick
    REVELATION_GAINED      = "revelation_gained"   # field=domain_tag, delta=amount (negative to spend)
    IMAGO_REVEALED         = "imago_revealed"      # new_value=node_id; appends to unlocked_imagines, increments revealed_imagines
    POP_BELIEF_SHIFT       = "pop_belief_shift"    # field=domain_tag, delta on Pop.dominant_beliefs
    POP_VISIBILITY         = "pop_visibility"      # delta/new_value on Pop.visibility; clamp 0–1
    CIV_ESTABLISHED_SHIFT  = "civ_established_shift"  # field=domain_tag, delta on Civilization.established_beliefs
    POP_SPLINTER           = "pop_splinter"        # new_value=Pop object (splinter); target_id=parent Pop UUID
    POP_SIZE_CHANGE        = "pop_size_change"     # delta on Pop.size_fractional; floor 0.0
    POP_RIDER_TRAIT        = "pop_rider_trait"     # field=domain_tag, delta on Pop.rider_traits; clamp 0–1
    POP_ABSORBED           = "pop_absorbed"        # target_id=Pop A UUID, new_value=Pop B UUID; full cleanup
    POP_CULTURE_SHIFT      = "pop_culture_shift"   # field=culture_tag, delta on Pop.culture_tags; clamp 0–1, prune below BELIEF_FLOOR
    MORTAL_POP_AGED_OUT    = "mortal_pop_aged_out" # target_id=mortal UUID; clears pop_id


class StateMutation(BaseModel):
    """
    A discrete change to world state produced by an action.
    The execution layer returns a list of these rather than
    mutating state directly — keeps the simulation inspectable.
    """
    mutation_type: MutationType
    target_id: Optional[UUID]
    field: str
    delta: Optional[float] = None       # For numeric fields
    new_value: Optional[object] = None  # For enum/string/list fields
    note: str = ""                      # Human-readable explanation


class ActionOutcome(str, Enum):
    SUCCESS         = "success"
    PARTIAL         = "partial"     # PROBABLE action that half-worked
    FAILURE         = "failure"
    CHAOTIC_RESULT  = "chaotic"     # CHAOTIC action — something happened, unclear what


class ActionResult(BaseModel):
    """
    The full result of executing an ActionInstance.
    Stored in the event log; read by the evaluation layer.
    """
    id: UUID = Field(default_factory=uuid4)
    action_instance_id: UUID
    outcome: ActionOutcome
    mutations: list[StateMutation] = Field(default_factory=list)
    narrative_note: str = ""
    # Brief generated description of what happened
    # — feeds the dialogue system and UI event feed

    luminary_visibility: dict[str, float] = Field(default_factory=dict)
    # luminary_id -> how visible this action was to them
    # Populated by evaluation layer after the fact
