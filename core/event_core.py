from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from uuid import UUID, uuid4

from core.action_core import DomainVector, CultureVector


class EventType(str, Enum):
    OMEN              = "omen"
    WHISPER           = "whisper"
    DEVELOPMENT_NUDGE = "development_nudge"


class StrengthCurve(str, Enum):
    SPIKE_FADE = "spike_fade"  # strong at creation, exponential decay
    RAMP_FADE  = "ramp_fade"   # rises to peak_offset, then falls
    FLAT       = "flat"        # constant for full duration


class Event(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    event_type: EventType
    curve: StrengthCurve

    source_action_id: Optional[UUID] = None
    created_at_tick: int

    duration: int                  # total active ticks (offset 0 through duration-1)
    base_strength: float = 1.0     # peak or initial strength
    peak_offset: int = 0           # RAMP_FADE: offset at which strength peaks
    decay_rate: float = 0.6        # SPIKE_FADE: per-tick decay multiplier

    # At most one target field is set; None means "all civilizations"
    target_world_id: Optional[UUID] = None
    target_civilization_id: Optional[UUID] = None
    target_mortal_id: Optional[UUID] = None

    target_loc_id: Optional[UUID] = None
    # Sub-location (PopLocation) the event manifests at — used by Omen echoes
    # for distance-from-core shielding of Pops in other sub-locations. None =
    # world surface (distance 0).

    domain_vectors: list[DomainVector] = Field(default_factory=list)
    culture_vectors: list[CultureVector] = Field(default_factory=list)
    # Culture-tag riders, applied with the same per-tick `domain_shift_rate`
    # scaling as domain_vectors (interpreted as the generic "shift rate" for
    # any vector type carried by the event).
    domain_shift_rate: float = 0.10      # per dv/cv: delta = vec.direction * strength * rate
    divine_awareness_rate: float = 0.0   # added to civ divine_awareness each tick
    attention_per_tick: float = 0.0      # AttentionTrigger delta for all Luminaries

    imago_node_id: Optional[str] = None
    framing: Optional[str] = None
    sign_description: str = ""
    concept: str = ""

    def current_strength(self, current_tick: int) -> float:
        offset = current_tick - self.created_at_tick
        if offset < 0 or offset >= self.duration:
            return 0.0
        if self.curve == StrengthCurve.SPIKE_FADE:
            return self.base_strength * (self.decay_rate ** offset)
        elif self.curve == StrengthCurve.RAMP_FADE:
            if offset <= self.peak_offset:
                return self.base_strength * (offset + 1) / (self.peak_offset + 1)
            remaining = self.duration - offset
            fade_span = self.duration - self.peak_offset
            return self.base_strength * remaining / max(1, fade_span)
        return self.base_strength  # FLAT

    def is_expired(self, current_tick: int) -> bool:
        return (current_tick - self.created_at_tick) >= self.duration
