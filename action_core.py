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


class ProxiusDirectiveIntent(BaseModel):
    """
    For: issue_directive
    Deliberately loose — a Proxius interprets your goal
    through their own alignment and personal tags.
    The gap between your intent and their execution
    is where interesting things happen.
    """
    goal_statement: str
    # Your intent in plain terms — what you want achieved.
    # e.g. "Ensure the reformist faction survives the purge"
    #      "Discredit the Church of the Threefold before it unifies the northern clans"
    #      "Find me a mortal worthy of elevation"

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

    constraints: list[str] = Field(default_factory=list)
    # Explicit limits on method.
    # e.g. ["do not kill the king directly", "do not reveal your divine appointment"]
    # A drifting Proxius may ignore these.


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
    trait_tags: list[str] = Field(default_factory=list)
    # e.g. ["trait:bipedal", "trait:warm_blooded", "trait:nocturnal"]


class UpliftSpeciesIntent(BaseModel):
    """
    For: uplift_species
    Catalyze a non-sapient species toward full sapience.
    The domain_vectors shape what kind of sapience emerges.
    """
    species_id: UUID
    domain_vectors: list[DomainVector] = Field(default_factory=list)
    framing: Framing = Framing.NATURAL


class ExploreBeliefIntent(BaseModel):
    """
    For: explore_beliefs
    The Demiurge contemplates a domain adjacent to their current understanding,
    expanding their conceptual frontier without promoting it in the universe.
    Adds the domain to the Demiurge's unlocked_domain_tags list.
    """
    domain_tag: str
    # The canonical domain:... tag being explored.
    # Must be within the Demiurge's current accessibility threshold.


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
    """
    Canonical action definitions.
    Scenarios can deepcopy and modify costs as needed.
    """
    return {

        # ── Direct Creation ──────────────────────────────

        "seed_world": ActionDefinition(
            name="Seed World with Life",
            category=ActionCategory.DIRECT_CREATION,
            description=(
                "Introduce a named species to a barren world. "
                "You define the species' basic biology and lifespan. "
                "Sapience requires a separate uplift action."
            ),
            valid_targets=[TargetType.WORLD],
            reliability=ActionReliability.CERTAIN,
            footprint_cost=FootprintCost(direct_creation=0.8),
            tags=["creation", "world_shaping", "high_footprint", "species"],
        ),

        "uplift_species": ActionDefinition(
            name="Uplift Species to Sapience",
            category=ActionCategory.DIRECT_CREATION,
            description=(
                "Catalyze a non-sapient species toward full sapience. "
                "A civilization will eventually emerge. High footprint."
            ),
            valid_targets=[TargetType.SPECIES],
            reliability=ActionReliability.PROBABLE,
            footprint_cost=FootprintCost(direct_creation=0.6, subtle_influence=0.2),
            essence_cost=0.2,
            tags=["creation", "species", "high_footprint", "civilization_seed"],
        ),

        "reshape_world": ActionDefinition(
            name="Reshape World Geography",
            category=ActionCategory.DIRECT_CREATION,
            description=(
                "Alter a world's physical features — continents, climate, "
                "atmosphere. Unmistakable as divine intervention."
            ),
            valid_targets=[TargetType.WORLD],
            reliability=ActionReliability.CERTAIN,
            footprint_cost=FootprintCost(direct_creation=0.9),
            tags=["world_shaping", "high_footprint", "irreversible"],
        ),

        "extinguish_civilization": ActionDefinition(
            name="Extinguish Civilization",
            category=ActionCategory.DIRECT_CREATION,
            description="Directly destroy a civilization. Maximum footprint.",
            valid_targets=[TargetType.CIVILIZATION],
            reliability=ActionReliability.CERTAIN,
            footprint_cost=FootprintCost(
                direct_creation=1.0,
                overt_miracles=0.8
            ),
            tags=["destruction", "high_footprint", "irreversible", "politically_sensitive"],
        ),

        # ── Overt Miracles ───────────────────────────────

        "manifest_omen": ActionDefinition(
            name="Manifest Omen",
            category=ActionCategory.OVERT_MIRACLE,
            description=(
                "Send a civilization-scale sign. Interpretable — mortals decide "
                "what it means, which affects belief drift unpredictably."
            ),
            valid_targets=[TargetType.CIVILIZATION],
            reliability=ActionReliability.PROBABLE,
            footprint_cost=FootprintCost(overt_miracles=0.5),
            tags=["belief_shift", "divine_awareness", "interpretable"],
        ),

        "direct_miracle": ActionDefinition(
            name="Perform Direct Miracle",
            category=ActionCategory.OVERT_MIRACLE,
            description="A visibly supernatural act for a specific mortal.",
            valid_targets=[TargetType.MORTAL],
            reliability=ActionReliability.CERTAIN,
            footprint_cost=FootprintCost(overt_miracles=0.6),
            tags=["mortal_directed", "divine_awareness", "high_footprint"],
        ),

        "divine_manifestation": ActionDefinition(
            name="Manifest in Divine Form",
            category=ActionCategory.OVERT_MIRACLE,
            description=(
                "Appear directly. Maximally high divine_awareness impact. "
                "Luminaries who care about subtlety will be displeased."
            ),
            valid_targets=[TargetType.CIVILIZATION, TargetType.MORTAL],
            reliability=ActionReliability.CERTAIN,
            footprint_cost=FootprintCost(overt_miracles=0.9),
            tags=["divine_awareness", "high_footprint", "belief_anchor"],
        ),

        # ── Subtle Influence ─────────────────────────────

        "whisper": ActionDefinition(
            name="Whisper to Mortal",
            category=ActionCategory.SUBTLE_INFLUENCE,
            description=(
                "Plant an inspiration, warning, or idea in a mortal's mind. "
                "Deniable. Effect depends on mortal's receptivity and alignment."
            ),
            valid_targets=[TargetType.MORTAL],
            reliability=ActionReliability.PROBABLE,
            footprint_cost=FootprintCost(subtle_influence=0.1),
            tags=["mortal_directed", "low_footprint", "deniable"],
        ),

        "shape_dream": ActionDefinition(
            name="Shape Dream",
            category=ActionCategory.SUBTLE_INFLUENCE,
            description=(
                "Deliver complex intent through a mortal's dreams. "
                "More information than a whisper; slightly more footprint."
            ),
            valid_targets=[TargetType.MORTAL],
            reliability=ActionReliability.PROBABLE,
            footprint_cost=FootprintCost(subtle_influence=0.15),
            tags=["mortal_directed", "low_footprint", "deniable", "complex_intent"],
        ),

        "nudge_probability": ActionDefinition(
            name="Nudge Probability",
            category=ActionCategory.SUBTLE_INFLUENCE,
            description=(
                "Weight the odds around a coming event — a battle, discovery, "
                "natural disaster. Not guaranteed; you tilt, not control."
            ),
            valid_targets=[TargetType.CIVILIZATION, TargetType.WORLD],
            reliability=ActionReliability.UNCERTAIN,
            footprint_cost=FootprintCost(subtle_influence=0.2),
            tags=["low_footprint", "deniable", "probabilistic"],
        ),

        "accelerate_development": ActionDefinition(
            name="Accelerate Civilizational Development",
            category=ActionCategory.SUBTLE_INFLUENCE,
            description=(
                "Nudge a civilization toward faster growth in a domain area. "
                "Slow. Plausibly natural. Compounds over time."
            ),
            valid_targets=[TargetType.CIVILIZATION],
            reliability=ActionReliability.PROBABLE,
            footprint_cost=FootprintCost(subtle_influence=0.25),
            tags=["long_term", "low_footprint", "domain_shaping"],
        ),

        # ── Proxius Direction ─────────────────────────────

        "appoint_proxius": ActionDefinition(
            name="Appoint Proxius",
            category=ActionCategory.PROXIUS_DIRECTION,
            description=(
                "Elevate a mortal to Proxius status. Generates proxius_activity "
                "footprint. Subject to Pantheon proxius_policy."
            ),
            valid_targets=[TargetType.MORTAL],
            reliability=ActionReliability.CERTAIN,
            footprint_cost=FootprintCost(subtle_influence=0.05,proxius_activity=0.3),
            tags=["proxii", "appointment", "politically_sensitive"],
        ),

        "issue_directive": ActionDefinition(
            name="Issue Directive to Proxius",
            category=ActionCategory.PROXIUS_DIRECTION,
            description=(
                "Communicate intent to a Proxius. They interpret and execute "
                "according to their alignment and personal tags. "
                "Issuing to a dormant Proxius reactivates them."
            ),
            valid_targets=[TargetType.MORTAL],
            requires_proxius=True,
            reliability=ActionReliability.UNCERTAIN,
            # Uncertainty here is alignment drift, not the channel
            footprint_cost=FootprintCost(proxius_activity=0.15),
            tags=["proxii", "indirect", "alignment_dependent",
                  "include_dormant_proxius"],
        ),

        "empower_proxius": ActionDefinition(
            name="Empower Proxius",
            category=ActionCategory.PROXIUS_DIRECTION,
            description="Grant a Proxius a temporary boost of divine capability.",
            valid_targets=[TargetType.MORTAL],
            requires_proxius=True,
            reliability=ActionReliability.CERTAIN,
            footprint_cost=FootprintCost(
                proxius_activity=0.4,
                overt_miracles=0.2
            ),
            essence_cost=0.1,
            tags=["proxii", "essence_consuming", "high_footprint"],
        ),

        "dismiss_proxius": ActionDefinition(
            name="Dismiss Proxius",
            category=ActionCategory.PROXIUS_DIRECTION,
            description="Revoke a mortal's Proxius status.",
            valid_targets=[TargetType.MORTAL],
            requires_proxius=True,
            reliability=ActionReliability.CERTAIN,
            footprint_cost=FootprintCost(proxius_activity=0.1),
            tags=["proxii", "appointment", "include_dormant_proxius"],
        ),

        "go_quiet_proxius": ActionDefinition(
            name="Go Quiet",
            category=ActionCategory.PROXIUS_DIRECTION,
            description=(
                "Signal a Proxius to suspend visible activity. "
                "They enter dormancy — appointed but generating no ongoing "
                "proxius_activity footprint. Bio-age resumes during dormancy. "
                "A future directive reactivates them."
            ),
            valid_targets=[TargetType.MORTAL],
            requires_proxius=True,
            reliability=ActionReliability.CERTAIN,
            footprint_cost=FootprintCost(proxius_activity=0.05),
            tags=["proxii", "appointment", "footprint_management"],
        ),

        # ── Observation ──────────────────────────────────

        "scry": ActionDefinition(
            name="Scry",
            category=ActionCategory.OBSERVATION,
            description=(
                "Survey a world to read its current state and bring "
                "low-prominence mortals into view. The only way to discover "
                "mortals who are not automatically perceived."
            ),
            valid_targets=[TargetType.WORLD],
            reliability=ActionReliability.CERTAIN,
            footprint_cost=FootprintCost(subtle_influence=0.05),
            tags=["observation", "low_footprint", "intelligence"],
        ),

        "read_divine_traces": ActionDefinition(
            name="Read Divine Traces",
            category=ActionCategory.OBSERVATION,
            description=(
                "Detect residual footprint and Herald activity on a world. "
                "Reveals what other divine actors have been doing."
            ),
            valid_targets=[TargetType.WORLD],
            reliability=ActionReliability.PROBABLE,
            footprint_cost=FootprintCost(),
            tags=["observation", "zero_footprint", "intelligence", "herald_detection"],
        ),

        "audit_proxius": ActionDefinition(
            name="Audit Proxius",
            category=ActionCategory.OBSERVATION,
            description=(
                "Read a Proxius's actual current alignment and recent behavior. "
                "Passive — they don't know you're checking."
            ),
            valid_targets=[TargetType.MORTAL],
            requires_proxius=True,
            reliability=ActionReliability.CERTAIN,
            footprint_cost=FootprintCost(),
            tags=["observation", "zero_footprint", "proxii", "alignment_check",
                  "include_dormant_proxius"],
        ),

        # ── Herald Interaction ───────────────────────────

        "negotiate_herald": ActionDefinition(
            name="Negotiate with Herald",
            category=ActionCategory.HERALD_INTERACTION,
            description=(
                "Attempt to find common ground with a Herald whose agenda "
                "partially overlaps yours. Outcome depends on their alignment "
                "with their patron and personal tags."
            ),
            valid_targets=[TargetType.MORTAL],
            reliability=ActionReliability.UNCERTAIN,
            footprint_cost=FootprintCost(subtle_influence=0.1),
            tags=["herald", "political", "alignment_dependent"],
        ),

        "obstruct_herald": ActionDefinition(
            name="Obstruct Herald",
            category=ActionCategory.HERALD_INTERACTION,
            description=(
                "Actively work against a Herald's activities. "
                "Their patron will likely notice. High political risk."
            ),
            valid_targets=[TargetType.MORTAL],
            reliability=ActionReliability.PROBABLE,
            footprint_cost=FootprintCost(
                subtle_influence=0.3,
                overt_miracles=0.2
            ),
            tags=["herald", "political", "politically_sensitive", "risky"],
        ),

        "petition_luminary_herald": ActionDefinition(
            name="Petition Luminary re: Herald",
            category=ActionCategory.HERALD_INTERACTION,
            description=(
                "Formally request a Luminary recall or redirect their Herald. "
                "Costs political capital but is legitimate."
            ),
            valid_targets=[TargetType.LUMINARY],
            reliability=ActionReliability.UNCERTAIN,
            footprint_cost=FootprintCost(),
            tags=["luminary_relations", "herald", "political", "disposition_dependent"],
        ),

        # ── Luminary Relations ───────────────────────────

        "report_to_luminary": ActionDefinition(
            name="Report to Luminary",
            category=ActionCategory.LUMINARY_RELATIONS,
            description=(
                "Proactively update a liege on your universe's state. "
                "Affects results disposition. Framing matters."
            ),
            valid_targets=[TargetType.LUMINARY],
            reliability=ActionReliability.CERTAIN,
            footprint_cost=FootprintCost(),
            tags=["luminary_relations", "disposition_shift", "narrative"],
        ),

        "petition_constraint_relaxation": ActionDefinition(
            name="Petition for Constraint Relaxation",
            category=ActionCategory.LUMINARY_RELATIONS,
            description=(
                "Ask a Luminary for more latitude on a specific constraint. "
                "Requires good standing. May reveal you've been straining against it."
            ),
            valid_targets=[TargetType.LUMINARY],
            reliability=ActionReliability.UNCERTAIN,
            footprint_cost=FootprintCost(),
            tags=["luminary_relations", "constraint", "politically_sensitive"],
        ),

        "dispute_demand": ActionDefinition(
            name="Dispute Demand",
            category=ActionCategory.LUMINARY_RELATIONS,
            description=(
                "Push back against a Luminary directive. "
                "Risky — degrades methods disposition, possibly results. "
                "Sometimes necessary when demands conflict."
            ),
            valid_targets=[TargetType.LUMINARY],
            reliability=ActionReliability.UNCERTAIN,
            footprint_cost=FootprintCost(),
            tags=["luminary_relations", "risky", "disposition_shift", "conflict"],
        ),

        # ── Underreal ────────────────────────────────────

        "harvest_essence": ActionDefinition(
            name="Harvest Essence from Underreal",
            category=ActionCategory.UNDERREAL,
            description=(
                "Draw Divine Essence from unrealized and abandoned concepts "
                "in the Underreal. Primary Essence source. "
                "Must be concealed — Luminaries are hostile to this."
            ),
            valid_targets=[TargetType.UNDERREAL],
            reliability=ActionReliability.PROBABLE,
            footprint_cost=FootprintCost(),
            essence_cost=-0.3,
            # Negative = yields 0.3 Essence per action
            concealment_impact=0.2,
            # 0.2 added to apparent stockpile unless actively hidden
            tags=["underreal", "essence_source", "high_risk", "conceal"],
        ),

        "salvage_concept": ActionDefinition(
            name="Salvage Concept from Underreal",
            category=ActionCategory.UNDERREAL,
            description=(
                "Pull a half-formed concept into your universe — "
                "a lost civilization, a forgotten technology, an unrealized species. "
                "Outcome is genuinely unpredictable."
            ),
            valid_targets=[TargetType.UNDERREAL],
            reliability=ActionReliability.CHAOTIC,
            footprint_cost=FootprintCost(direct_creation=0.4),
            essence_cost=0.2,
            concealment_impact=0.3,
            tags=["underreal", "essence_consuming", "chaotic", "creation", "conceal"],
        ),

        "exile_to_underreal": ActionDefinition(
            name="Exile to Underreal",
            category=ActionCategory.UNDERREAL,
            description=(
                "Suppress and exile something from your universe — "
                "a civilization, concept, or entity — into the conceptual graveyard. "
                "Permanent and leaves a distinctive trace."
            ),
            valid_targets=[
                TargetType.CIVILIZATION,
                TargetType.MORTAL,
                TargetType.WORLD
            ],
            reliability=ActionReliability.CERTAIN,
            footprint_cost=FootprintCost(
                direct_creation=0.7,
                overt_miracles=0.3
            ),
            essence_cost=0.3,
            tags=["underreal", "destruction", "essence_consuming",
                  "irreversible", "high_footprint"],
        ),

        "investigate_underreal": ActionDefinition(
            name="Investigate Underreal",
            category=ActionCategory.UNDERREAL,
            description=(
                "Survey what failed Demiurges and abandoned concepts left behind. "
                "Intelligence on available salvage and Underreal inhabitants."
            ),
            valid_targets=[TargetType.UNDERREAL],
            reliability=ActionReliability.PROBABLE,
            footprint_cost=FootprintCost(),
            essence_cost=0.05,
            concealment_impact=0.05,
            tags=["underreal", "observation", "intelligence"],
        ),

        "maintain_concealment": ActionDefinition(
            name="Maintain Concealment",
            category=ActionCategory.UNDERREAL,
            description=(
                "Actively reinforce the veil over your Essence stockpile. "
                "Spend a small amount of Essence to restore concealment integrity. "
                "Diminishing returns when integrity is already high. "
                "Cannot be combined with an Essence harvest in the same tick."
            ),
            valid_targets=[TargetType.UNDERREAL],
            reliability=ActionReliability.PROBABLE,
            footprint_cost=FootprintCost(),
            essence_cost=0.10,
            tags=["underreal", "concealment", "essence_consuming", "maintenance"],
        ),

        # ── Demiurge Self-Development ─────────────────────

        "explore_beliefs": ActionDefinition(
            name="Explore Beliefs",
            category=ActionCategory.SELF_REFINEMENT,
            description=(
                "Contemplate a domain adjacent to your current understanding. "
                "Expands your conceptual frontier without promoting the belief "
                "in the universe — but unlocks it for future directive use."
            ),
            valid_targets=[TargetType.UNDERREAL],
            reliability=ActionReliability.CERTAIN,
            footprint_cost=FootprintCost(),
            essence_cost=0.0,
            tags=["zero_footprint", "self_refinement"],
        ),

        "overthrow_luminary": ActionDefinition(
            name="Move Against Luminary",
            category=ActionCategory.UNDERREAL,
            description=(
                "Spend massive accumulated Essence to challenge or sever a "
                "Luminary's hold over your universe. "
                "The ultimate high-risk action — possible victory state, "
                "possible immediate demotion to the Underreal."
            ),
            valid_targets=[TargetType.LUMINARY],
            reliability=ActionReliability.UNCERTAIN,
            footprint_cost=FootprintCost(
                overt_miracles=1.0,
                direct_creation=0.8
            ),
            essence_cost=1.0,
            concealment_impact=1.0,
            tags=["underreal", "essence_consuming", "victory_condition",
                  "catastrophic_risk", "irreversible"],
        ),
    }


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
