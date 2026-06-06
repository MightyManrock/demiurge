from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, Literal, Annotated, TYPE_CHECKING
if TYPE_CHECKING:
    from core.universe_core import Species
from enum import Enum
from uuid import UUID

from core.action_core import DomainVector, CultureVector


# ---------------------------------------------------------------------------
# Knowledge Base
# ---------------------------------------------------------------------------

class LocationFact(BaseModel):
    fact_type: Literal["location"] = "location"
    location_id: str
    label: str = ""
    confidence: float = 1.0
    learned_at_tick: int = 0
    visit_count: int = 0


class ResourceFact(BaseModel):
    fact_type: Literal["resource"] = "resource"
    location_id: str
    resource_type: str = "unobtanium"
    resource_yield: float = 1.0
    confidence: float = 1.0
    learned_at_tick: int = 0


class RouteFact(BaseModel):
    fact_type: Literal["route"] = "route"
    from_id: str
    to_id: str
    vehicle_type: Optional[str] = None
    ticks_cost: int = 0
    confidence: float = 1.0
    learned_at_tick: int = 0


class LocationQualityFact(BaseModel):
    fact_type: Literal["location_quality"] = "location_quality"
    location_id: str
    quality: float = 0.5
    quality_type: Literal["sell", "spend"] = "spend"
    confidence: float = 1.0
    learned_at_tick: int = 0


class DirectiveFact(BaseModel):
    fact_type: Literal["directive"] = "directive"
    directive_id: str              # UUID string matching Directive.id
    directive_type: str            # "commerce"
    satisfying_action: str         # "sell" — what action fulfills this directive
    target_pop_location_id: str    # UUID of the PopLocation whose wealth this grows
    confidence: float = 1.0
    learned_at_tick: int = 0
    source_faction_id: Optional[str] = None


class PopFact(BaseModel):
    fact_type: Literal["pop"] = "pop"
    pop_id: str
    label: str = ""
    interaction_count: int = 0
    last_interaction_tick: int = 0


KnowledgeFact = Annotated[
    LocationFact | ResourceFact | RouteFact | LocationQualityFact | DirectiveFact | PopFact,
    Field(discriminator="fact_type"),
]


class KnowledgeBase(BaseModel):
    facts: list[KnowledgeFact] = Field(default_factory=list)

    def best_known_spend_location(self) -> Optional[str]:
        quality_facts = [
            f for f in self.facts
            if f.fact_type == "location_quality" and f.quality_type == "spend"
        ]
        if not quality_facts:
            return None
        return max(quality_facts, key=lambda f: f.quality * f.confidence).location_id

    def best_known_sell_location(self) -> Optional[str]:
        quality_facts = [
            f for f in self.facts
            if f.fact_type == "location_quality" and f.quality_type == "sell"
        ]
        if not quality_facts:
            return None
        return max(quality_facts, key=lambda f: f.quality * f.confidence).location_id

    def known_resource_locations(self) -> list[str]:
        return [f.location_id for f in self.facts if f.fact_type == "resource"]

    def route_to(self, to_id: str) -> Optional[RouteFact]:
        for f in self.facts:
            if f.fact_type == "route" and f.to_id == to_id:
                return f
        return None

    def route_ticks_to(self, to_id: str) -> int:
        fact = self.route_to(to_id)
        return fact.ticks_cost if fact else 0

    def directive_facts(self) -> list[DirectiveFact]:
        return [f for f in self.facts if f.fact_type == "directive"]

    def pop_facts(self) -> list[PopFact]:
        return [f for f in self.facts if f.fact_type == "pop"]

    def get_pop_fact(self, pop_id: str) -> Optional[PopFact]:
        return next((f for f in self.facts if f.fact_type == "pop" and f.pop_id == pop_id), None)


# ---------------------------------------------------------------------------
# Needs
# ---------------------------------------------------------------------------

class MortalNeed(BaseModel):
    name: str
    satisfaction: float = Field(ge=0.0, le=1.0, default=1.0)
    decay_rate: float = 0.05
    pressing_threshold: float = 0.65
    urgent_threshold: float = 0.35
    satiation_hold: int = 0

    @property
    def is_pressing(self) -> bool:
        return self.satisfaction < self.pressing_threshold

    @property
    def is_urgent(self) -> bool:
        return self.satisfaction < self.urgent_threshold


class MortalDesire(BaseModel):
    name: str
    satisfaction: float = Field(ge=0.0, le=1.0, default=0.7)
    decay_rate: float = 0.003
    pressing_threshold: float = 0.5
    satiation_hold: int = 0

    @property
    def is_pressing(self) -> bool:
        return self.satisfaction < self.pressing_threshold

    def urgency(self) -> float:
        if self.satiation_hold > 0 or not self.is_pressing:
            return 0.0
        return 1.0 - (self.satisfaction / self.pressing_threshold)


# ---------------------------------------------------------------------------
# Assets and collectible resources
# ---------------------------------------------------------------------------

class MortalAsset(BaseModel):
    asset_type: str
    label: str = ""
    cargo_capacity: Optional[float] = None


class CollectibleResource(BaseModel):
    resource_yield: float = 1.0
    cooldown_ticks: int = 3
    resource_type: str = "unobtanium"
    biochem_tags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Typed resource inventory
# ---------------------------------------------------------------------------

class Resource(BaseModel):
    resource_type: str
    quantity: float = 0.0
    base_value: float = 1.0
    converts_to: Optional[str] = None
    threshold: float = 1.0
    usable_for: list[str] = Field(default_factory=list)
    fills_need: Optional[str] = None
    biochem_tags: list[str] = Field(default_factory=list)


def species_can_consume(species: "Species", resource: Resource) -> bool:
    """True if the species can directly consume this resource for sustenance.

    A resource is consumable if all of its biochem_tags are satisfied by the species'
    basis and solvent. Tags not declared on the resource are unconstrained — a resource
    tagged only ["solvent:water"] matches any water-solvent species regardless of basis.
    An empty biochem_tags list means inert (not consumable by anyone).
    """
    if not resource.biochem_tags:
        return False
    species_tags = {f"basis:{species.life_basis.value}", f"solvent:{species.solvent.value}"}
    return all(tag in species_tags for tag in resource.biochem_tags)


# ---------------------------------------------------------------------------
# Mortal Agent State
# ---------------------------------------------------------------------------

class MortalAgentState(BaseModel):
    needs: list[MortalNeed] = Field(default_factory=list)
    desires: list[MortalDesire] = Field(default_factory=list)
    inventory: list[Resource] = Field(default_factory=list)
    action_cooldowns: dict[str, int] = Field(default_factory=dict)
    last_action: Optional[str] = None
    pending_travel_dest: Optional[str] = None
    collecting_ticks_remaining: int = 0
    pending_transfer: bool = False

    def pressing_needs(self) -> list[MortalNeed]:
        return [n for n in self.needs if n.is_pressing]

    def cooldown_expired(self, action_type: str, current_tick: int) -> bool:
        return self.action_cooldowns.get(action_type, 0) <= current_tick

    def get_resource(self, resource_type: str) -> Optional[Resource]:
        return next((r for r in self.inventory if r.resource_type == resource_type), None)

    def get_need(self, name: str) -> Optional[MortalNeed]:
        return next((n for n in self.needs if n.name == name), None)


class TravelIntent(BaseModel):
    travel_location_id: UUID
    target_pop_id: Optional[UUID] = None  # if set, mortal embeds in this Pop on arrival


class AgentActionChoice(str, Enum):
    PROMOTE_DOMAIN       = "promote_domain"
    BOLSTER_BELIEFS      = "bolster_beliefs"
    RESEARCH_DOMAIN      = "research_domain"
    TAKE_STOCK           = "take_stock"
    REPORT_TO_DEMIURGE   = "report_to_demiurge"
    PETITION_FOR_RELIEF  = "petition_for_relief"
    NOTHING              = "nothing"


class ProxiusGoal(BaseModel):
    """
    Active goal held by a Proxius agent.
    Set when a directive is issued; drives autonomous tick-by-tick behavior.
    Cleared when the directive is revoked.
    """
    imago_node_id: str
    label: str = ""          # human-readable summary, e.g. "Preaching Wheel of Change in Oros"
    target_location_id: UUID
    target_civilization_id: Optional[UUID] = None  # None = all civs at location (legacy path)
    domain_vectors: list[DomainVector] = Field(default_factory=list)
    culture_vectors: list[CultureVector] = Field(default_factory=list)
    # Culture-tag riders inherited from the framing Imago. Applied by Proxius
    # preaching alongside domain_vectors.
    latitude: float = 0.5                           # 0.0 strict → 1.0 open
    constraints: list[str] = Field(default_factory=list)
    started_at_tick: int = 0
    last_action_tick: int = -1
    last_action: Optional[AgentActionChoice] = None
    consecutive_promote_count: int = 0  # streak of PROMOTE_DOMAIN / BOLSTER_BELIEFS actions
    effectiveness_bonus: float = 0.0    # grows with streak, cap 0.30, resets on break
    petition_pending: bool = False      # true until Demiurge re-issues or revokes
    report_log: list[str] = Field(default_factory=list)  # last 5 entries
    research_domain: Optional[str] = None
    # When set: this is a Commission Inquiry research goal. domain:... tag being studied.
    # Mutually exclusive in practice with domain_vectors / target_civilization_id (directive goals).

    # Pop-level preaching fields (set when preach_imago targets a specific Pop):
    source_pop_id: Optional[UUID] = None
    # Pop A: the population being drawn from (player-selected at directive time).
    goal_pop_id: Optional[UUID] = None
    # Pop B: the splinter being grown. None until first PROMOTE_DOMAIN success creates it.
    goal_pop_name: Optional[str] = None
    # Player-supplied name for Pop B, captured at directive time when no splinter
    # exists yet. The Proxius "holds" this name until a successful action first
    # creates the splinter, at which point it is applied as `Pop.name`. Discarded
    # silently if the directive ends before a splinter forms.
    goal_pop_last_size: float = 0.0
    # Pop B's size_fractional at end of last tick; used to detect stagnation/re-absorption.
    stagnation_counter: int = 0
    # Ticks in a row where Pop B failed to grow. Drives petition weight up.

    petition_pending_ticks: int = 0
    # Consecutive ticks petition_pending has been True. Resets when petition clears.
    # At 5 the Proxius abandons their goal entirely.

    pop_b_belief_cap_reached: bool = False
    # True once Pop B's core domain belief reaches the 0.9 cap.
    # Triggers a petition for new orders; does NOT drain alignment on filing.

    pop_b_size_goal_reached: bool = False
    # True once Pop B's size_fractional >= 55% of Pop A's size_fractional.
    # Triggers a petition for new orders; does NOT drain alignment on filing.
    # When both flags are True the Proxius reports complete success and the
    # goal is cleared immediately (no 5-tick petition wait).
