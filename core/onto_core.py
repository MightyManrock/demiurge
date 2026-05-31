#!/usr/bin/env python3
"""
onto_core.py
Classes connected to the ontological structure of the
divine hierarchy.
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Annotated, Literal, Optional, Union
from uuid import UUID, uuid4


# ─────────────────────────────────────────
# OVERREAL
# ─────────────────────────────────────────

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


class NarrativeConstraint(BaseModel):
    """
    A constraint that is stored and displayed but not mechanically evaluated.
    Used for flavor, future expansion, or constraint types not yet implemented.
    """
    constraint_type: Literal["narrative"] = "narrative"
    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str
    domain_tag: Optional[str] = None
    enforcement_weight: float = Field(ge=0.0, le=1.0, default=0.5)


class FootprintConstraint(BaseModel):
    """
    A constraint that enforces per-category footprint tolerances.
    Evaluated each tick; violations produce disposition deltas scaled by enforcement_weight.
    Luminary-owned: affects only that Luminary's disposition.
    Pantheon-owned: fans out to every Luminary in the Pantheon.
    """
    constraint_type: Literal["footprint"] = "footprint"
    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str
    domain_tag: Optional[str] = None
    enforcement_weight: float = Field(ge=0.0, le=1.0, default=0.5)
    footprint_tolerances: dict[str, float]
    # Maps footprint category → tolerance ceiling, e.g. {"overt_miracles": 0.2}
    # Keys must be valid FootprintProfile field names. Values are [0, 1] ceilings.


class ResultsConstraint(BaseModel):
    """
    A constraint that enforces a minimum floor on the owning Luminary's
    disposition.results axis. Evaluated each tick; fires when results fall
    below min_results. No AttentionLevel dampening — Luminaries can read
    universe outcomes regardless of how closely they are watching.
    Luminary-owned: affects only that Luminary's disposition.
    Pantheon-owned: fans out to every Luminary.
    """
    constraint_type: Literal["results"] = "results"
    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str
    domain_tag: Optional[str] = None
    enforcement_weight: float = Field(ge=0.0, le=1.0, default=0.5)
    min_results: float = Field(ge=-1.0, le=1.0)
    # Floor for the owning Luminary's disposition.results.
    # delta = current_results - min_results; negative delta = violation.


Constraint = Annotated[
    Union[NarrativeConstraint, FootprintConstraint, ResultsConstraint],
    Field(discriminator="constraint_type"),
]


class Luminary(BaseModel):
    """
    A divine being of the Overreal, constituted by a combination of Domains.
    Luminaries are the Demiurge's lieges, patrons, and antagonists.
    """
    id: UUID = Field(default_factory=uuid4)
    name: str
    domains: dict[str, float]   # domain:... tag → affinity (0.0–1.0)
    pantheon_id: Optional[UUID] = None
    disposition: Disposition = Field(default_factory=Disposition)
    constraints: list[Constraint] = Field(default_factory=list)
    herald_ids: list[UUID] = Field(default_factory=list)        # Mortal Heralds assigned to the Demiurge's universe
    status_tags: list[str] = Field(default_factory=list)
    # e.g. ["status:liege"]
    essence_received_log: list[float] = Field(default_factory=list)
    # Weighted domain production per evaluation period; last 2 entries retained.
    # Used to assess whether the Luminary's Essence intake is above threshold and growing.
    essence_expectation_raised: float = 0.0
    # Additive bonus above the base threshold, accrued when the Luminary sees excess production.
    # Decays by 0.10 per two consecutive shortfall periods; floored at 0.0 (never below base).
    consecutive_essence_shortfalls: int = 0
    # Tracks back-to-back evaluation periods where production fell short of the raised threshold.
    # Resets to 0 on any above-threshold period or after triggering a 0.10 expectation reduction.

    # Snapshot of the most recent LuminaryEvaluation as a plain dict (model_dump'd).
    # Surfaced in the Luminary detail tab. The dict form sidesteps the
    # onto_core ↔ eval_core circular-import problem.
    last_evaluation: Optional[dict] = None
    previous_evaluation: Optional[dict] = None
    last_evaluation_tick: Optional[int] = None

    # Captured narrative from the most recent "Ask for Orders" action.
    last_orders_response: Optional[str] = None
    last_orders_response_tick: Optional[int] = None


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
    footprint: FootprintProfile = Field(default_factory=FootprintProfile)
    proxius_ids: list[UUID] = Field(default_factory=list)
    unlocked_domain_tags: list[str] = Field(default_factory=list)
    # domain:... tags the Demiurge has explored or promoted beyond their Luminaries'
    # granted domains. Each unlocked tag extends the Demiurge's accessible frontier.
    unlocked_imagines: list[str] = Field(default_factory=list)
    # imago node_ids (e.g. "change:t1:wheel") the Demiurge has purchased or drawn.
    affiliated_domains: list[str] = Field(default_factory=list)
    # domain:... tags the Demiurge has claimed as their own conceptual focus.
    # Default: top-N by aggregate Luminary affinity sum across all lieges,
    # where N = max_affiliated_domains.
    max_affiliated_domains: int = 3
    # Cap on len(affiliated_domains). Stronghold building slots are expected to
    # raise this at runtime; loader/UI cap and default-derivation slice both
    # honor it.
    tracked_essence_domains: list[str] = Field(default_factory=list)
    # Subset of domain:... tags for which per-tick Demiurge Essence claims are
    # recorded in SimulationState.domain_essence_claimed. Empty by default.
    revelation_pools: dict[str, float] = Field(default_factory=dict)
    # domain:... tag → accumulated Revelation points.
    # All 16 canonical tags are present (0.0 by default); filled in by the loader.
    revealed_imagines: int = 0
    # Count of Imagines unlocked via Reveal Imago (does not include starting Imagines).
    lifetime_revelation: float = 0.0
    # Running total of all Revelation ever gained (never decremented). Used to compute puissance.
    puissance: float = 0.0
    # Computed each tick: reflects accumulated power [0, 1]. See _compute_puissance() in tick_logic.

