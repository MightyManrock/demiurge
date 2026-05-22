from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from uuid import UUID

from core.action_core import DomainVector, CultureVector


class TravelIntent(BaseModel):
    travel_location_id: UUID


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
