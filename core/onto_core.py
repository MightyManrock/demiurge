#!/usr/bin/env python3
"""
onto_core.py
Classes connected to the ontological structure of the
divine hierarchy.
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from uuid import UUID, uuid4


# ─────────────────────────────────────────
# HIGHEST REAL
# ─────────────────────────────────────────

class Power(BaseModel):
    """
    An unconscious archetypal force in the Highest Real.
    Powers don't act — they radiate. Domains are how that
    radiation becomes structured and usable.
    """
    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str


class Domain(BaseModel):
    """
    A structured aspect of one or more Powers.
    Domains are the fundamental currency of divine identity —
    what a Luminary *is* is what Domains it embodies.
    Tags feed the evaluation and dialogue layers later.
    """
    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str
    source_powers: list[UUID]       # Most Domains flow from one Power; some bridge several
    tags: list[str] = Field(default_factory=list)
    # e.g. ["conflict", "change", "mortal_emotion"] — used for speech act queries


# ─────────────────────────────────────────
# OVERREAL
# ─────────────────────────────────────────

class Temperament(str, Enum):
    """
    Broad behavioral disposition of a Luminary.
    Shapes how they respond to the same disposition score
    — a wrathful Luminary and a patient one react differently
    to identical footprint readings.
    """
    WRATHFUL   = "wrathful"
    PATIENT    = "patient"
    CAPRICIOUS = "capricious"
    ORDERLY    = "orderly"
    INDIFFERENT = "indifferent"
    ZEALOUS    = "zealous"


class Disposition(BaseModel):
    """
    A Luminary's current stance toward the Demiurge.
    Split into two axes because they can diverge:
    a Luminary might be satisfied with outcomes but
    uneasy about how you're achieving them.
    """
    results: float = Field(ge=-1.0, le=1.0, default=0.0)
    # How pleased they are with the state of your universe
    # relative to their Domains and demands

    methods: float = Field(ge=-1.0, le=1.0, default=0.0)
    # How comfortable they are with *how* you operate
    # (footprint, Proxius use, subtlety, etc.)

    @property
    def overall(self) -> float:
        # Naive average for now; weighting can come later
        return (self.results + self.methods) / 2.0


class Constraint(BaseModel):
    """
    A specific behavioral expectation a Luminary imposes on their Demiurge.
    Constraints are what the evaluation layer checks against.
    A Pantheon can also carry collective constraints that
    supersede or supplement individual ones.
    """
    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str
    domain_source: Optional[UUID] = None    # Which Domain this flows from, if any
    enforcement_weight: float = Field(ge=0.0, le=1.0, default=0.5)
    # 0.0 = they'll grumble but not act; 1.0 = hard line


class Luminary(BaseModel):
    """
    A divine being of the Overreal, constituted by a combination of Domains.
    Luminaries are the Demiurge's lieges, patrons, and antagonists.
    """
    id: UUID = Field(default_factory=uuid4)
    name: str
    domains: list[UUID]
    pantheon_id: Optional[UUID] = None
    temperament: Temperament
    disposition: Disposition = Field(default_factory=Disposition)
    constraints: list[Constraint] = Field(default_factory=list)
    herald_ids: list[UUID] = Field(default_factory=list)        # Mortal Heralds assigned to the Demiurge's universe
    status_tags: list[str] = Field(default_factory=list)
    # e.g. ["status:liege"]


class Pantheon(BaseModel):
    """
    A coalition of Luminaries sharing oversight of a multiverse set.
    Collective constraints at this level represent pantheon-wide
    expectations that individual Luminaries may not personally care about
    but are bound to enforce.
    """
    id: UUID = Field(default_factory=uuid4)
    name: str
    luminary_ids: list[UUID]
    collective_constraints: list[Constraint] = Field(default_factory=list)


# ─────────────────────────────────────────
# THE REAL — Demiurge
# ─────────────────────────────────────────

class FootprintProfile(BaseModel):
    """
    Tracks divine visibility across different action categories.
    A single float obscures too much — your Luminaries may care
    about overt miracles but not care at all about subtle nudges,
    or vice versa depending on the scenario.
    """
    overt_miracles: float = Field(ge=0.0, le=1.0, default=0.0)
    subtle_influence: float = Field(ge=0.0, le=1.0, default=0.0)
    proxius_activity: float = Field(ge=0.0, le=1.0, default=0.0)
    direct_creation: float = Field(ge=0.0, le=1.0, default=0.0)


class Demiurge(BaseModel):
    """
    The player. Divine power over a single universe,
    accountable upward to liege Luminaries.
    """
    id: UUID = Field(default_factory=uuid4)
    name: str
    liege_luminary_ids: list[UUID]
    granted_domains: list[UUID]         # Domains the lieges have empowered you with
    footprint: FootprintProfile = Field(default_factory=FootprintProfile)
    proxius_ids: list[UUID] = Field(default_factory=list)
    unlocked_domain_tags: list[str] = Field(default_factory=list)
    # domain:... tags the Demiurge has explored or promoted beyond their Luminaries'
    # granted domains. Each unlocked tag extends the Demiurge's accessible frontier.
    unlocked_imagines: list[str] = Field(default_factory=list)
    # imago node_ids (e.g. "change:t1:wheel") the Demiurge has purchased or drawn.
