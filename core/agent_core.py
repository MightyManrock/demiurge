from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from uuid import UUID

from core.action_core import DomainVector


class AgentActionChoice(str, Enum):
    PROMOTE_DOMAIN       = "promote_domain"
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
    target_location_id: UUID
    target_civilization_id: Optional[UUID] = None  # None = all civs at location
    domain_vectors: list[DomainVector] = Field(default_factory=list)
    latitude: float = 0.5                           # 0.0 strict → 1.0 open
    constraints: list[str] = Field(default_factory=list)
    started_at_tick: int = 0
    last_action_tick: int = -1
    last_action: Optional[AgentActionChoice] = None
    consecutive_promote_count: int = 0  # streak of PROMOTE_DOMAIN actions
    effectiveness_bonus: float = 0.0    # grows with streak, cap 0.30, resets on break
    petition_pending: bool = False      # true until Demiurge re-issues or revokes
    report_log: list[str] = Field(default_factory=list)  # last 5 entries
