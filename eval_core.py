#!/usr/bin/env python3
"""
eval_core.py
Classes and code concerning how the Luminaries view
the actions of the Demiurge.
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from uuid import UUID, uuid4


# ─────────────────────────────────────────
# ATTENTION
# How closely a Luminary is watching right now.
# ─────────────────────────────────────────

class AttentionLevel(str, Enum):
    NEGLIGENT  = "negligent"   # Barely aware your universe exists
    PASSIVE    = "passive"     # Periodic summary reads
    WATCHFUL   = "watchful"    # Actively monitoring
    SCRUTINOUS = "scrutinous"  # Looking hard — constraint violation suspected
    INVASIVE   = "invasive"    # Full audit — Herald deployed, nothing hidden


class AttentionTrigger(BaseModel):
    """
    Something that raised or lowered a Luminary's attention.
    Accumulated to explain why attention is at its current level.
    """
    trigger_type: str
    # e.g. "footprint_spike", "herald_report", "constraint_breach",
    #      "long_silence", "proactive_report", "competitor_complaint"

    delta: float
    # Positive = raised attention, negative = lowered it
    # Attention itself is tracked on the Luminary as a float 0.0-1.0

    timestamp: float
    note: str = ""


# ─────────────────────────────────────────
# DOMAIN ALIGNMENT SCORING
# How well the universe expresses a Luminary's Domains.
# ─────────────────────────────────────────

class DomainAlignmentScore(BaseModel):
    """
    How closely the current universe state reflects
    a specific Domain tag this Luminary holds.
    """
    domain_tag: str
    current_score: float = Field(ge=0.0, le=1.0)
    # Aggregate of matching domain_expression across all worlds,
    # weighted by civilization scale and health

    previous_score: float = Field(ge=0.0, le=1.0)
    # Score from last evaluation tick — used for trajectory

    @property
    def trajectory(self) -> float:
        """Positive = improving, negative = declining."""
        return self.current_score - self.previous_score

    @property
    def weighted_value(self) -> float:
        """
        Trajectory matters as much as absolute score.
        A rising 0.4 is worth more than a falling 0.7.
        """
        return self.current_score + (self.trajectory * 0.5)


class UniverseDomainProfile(BaseModel):
    """
    Snapshot of how strongly each Domain tag is expressed
    across the universe at a given evaluation tick.
    Built by surveying world domain_expression and
    civilization dominant_beliefs, weighted by scale.
    """
    timestamp: float
    scores: dict[str, float] = Field(default_factory=dict)
    # domain_tag -> 0.0-1.0 expression strength

    def for_tags(self, tags: list[str]) -> float:
        """Average expression score for a list of domain tags."""
        if not tags:
            return 0.0
        return sum(self.scores.get(t, 0.0) for t in tags) / len(tags)


# ─────────────────────────────────────────
# CONSTRAINT EVALUATION
# ─────────────────────────────────────────

class ConstraintComplianceLevel(str, Enum):
    EXEMPLARY  = "exemplary"   # Better than expected
    COMPLIANT  = "compliant"   # Within tolerance
    STRAINING  = "straining"   # Pushing the limit — Luminary notices
    BREACHING  = "breaching"   # Clear violation — disposition hit
    FLAGRANT   = "flagrant"    # Repeated or severe — attention spike


class ConstraintEvaluation(BaseModel):
    """
    Assessment of a single Constraint at evaluation time.
    """
    constraint_id: UUID
    constraint_name: str
    compliance: ConstraintComplianceLevel

    measured_value: Optional[float] = None
    # What was actually measured, for numeric constraints

    threshold: Optional[float] = None
    # What the constraint requires

    disposition_delta: float = 0.0
    # Contribution to methods disposition this tick.
    # Negative for violations, small positive for exemplary.

    attention_delta: float = 0.0
    # How much this raises/lowers Luminary attention.
    # Breaches raise attention; exemplary compliance can lower it slightly.

    note: str = ""


# ─────────────────────────────────────────
# FOOTPRINT ASSESSMENT
# ─────────────────────────────────────────

class FootprintAssessment(BaseModel):
    """
    How a Luminary reads the current footprint profile,
    filtered through their attention level and
    the scenario's FootprintTolerances.
    """
    luminary_id: UUID

    # What they can actually perceive given attention level.
    # At PASSIVE attention, subtle_influence may be invisible.
    # At INVASIVE, everything is visible.
    perceived_footprint: dict[str, float] = Field(default_factory=dict)
    # category -> perceived value (may differ from actual at low attention)

    tolerance_violations: list[str] = Field(default_factory=list)
    # Which categories exceed their tolerance threshold

    overall_methods_delta: float = 0.0
    # Net contribution to methods disposition

    attention_triggered: bool = False
    # Whether this reading is spiking their attention level


# ─────────────────────────────────────────
# ESSENCE SUSPICION
# What the Luminary suspects about hidden Essence.
# ─────────────────────────────────────────

class EssenceSuspicion(BaseModel):
    """
    Separate from footprint because Essence concealment
    is its own system. A Luminary can have zero footprint
    concerns and still be deeply suspicious about Essence.
    """
    luminary_id: UUID

    apparent_stockpile_reading: float = 0.0
    # What they see — matches EssenceStockpile.apparent
    # unless Herald investigation has revealed more

    suspicion_level: float = Field(ge=0.0, le=1.0, default=0.0)
    # Grows from: concealment_integrity degradation,
    # Herald reports, Underreal action patterns,
    # unexplained capability spikes

    suspicion_triggers: list[str] = Field(default_factory=list)
    # What's feeding suspicion this tick
    # e.g. ["underreal_action_detected", "concealment_degraded",
    #        "herald_reported_anomaly"]

    disposition_delta: float = 0.0
    # Suspicion contributes to methods disposition.
    # Low suspicion: minimal. High suspicion: significant.
    # Confirmed Essence accumulation: severe.

    attention_delta: float = 0.0


# ─────────────────────────────────────────
# DISPOSITION DELTA
# The actual change in a Luminary's stance this tick.
# ─────────────────────────────────────────

class DispositionDeltaReason(BaseModel):
    """A single contributing factor to a disposition change."""
    axis: str               # "results" or "methods"
    delta: float
    source: str
    # e.g. "domain_alignment:war", "constraint:footprint_tolerance",
    #      "essence_suspicion", "proactive_report", "herald_conflict"
    note: str = ""


class DispositionDelta(BaseModel):
    results: float = 0.0
    methods: float = 0.0
    reasons: list[DispositionDeltaReason] = Field(default_factory=list)

    def clamp_to(
        self,
        current_results: float,
        current_methods: float
    ) -> tuple[float, float]:
        """Return new values clamped to [-1.0, 1.0]."""
        return (
            max(-1.0, min(1.0, current_results + self.results)),
            max(-1.0, min(1.0, current_methods + self.methods)),
        )


# ─────────────────────────────────────────
# DIALOGUE TRIGGERS
# What the evaluation produces for the speech act system.
# ─────────────────────────────────────────

class DialogueTriggerType(str, Enum):
    ROUTINE_CHECK_IN       = "routine_check_in"
    PLEASED_WITH_RESULTS   = "pleased_with_results"
    DISPLEASED_WITH_RESULTS = "displeased_with_results"
    METHODS_CONCERN        = "methods_concern"
    CONSTRAINT_WARNING     = "constraint_warning"
    CONSTRAINT_ULTIMATUM   = "constraint_ultimatum"
    ESSENCE_INQUIRY        = "essence_inquiry"
    ESSENCE_ACCUSATION     = "essence_accusation"
    HERALD_REPORT          = "herald_report"
    DEMAND_ISSUED          = "demand_issued"
    PRAISE                 = "praise"
    THREAT                 = "threat"


class DialogueTrigger(BaseModel):
    """
    An event the evaluation layer flags for the dialogue system.
    The speech act query layer uses these to select
    appropriate Luminary speech acts.
    """
    id: UUID = Field(default_factory=uuid4)
    luminary_id: UUID
    trigger_type: DialogueTriggerType
    timestamp: float
    urgency: float = Field(ge=0.0, le=1.0, default=0.5)

    context_tags: list[str] = Field(default_factory=list)
    # Tags the speech act query will filter on.
    # Built from: Luminary domain tags + temperament +
    # current disposition bracket + trigger type
    # e.g. ["domain:war", "temperament:wrathful",
    #        "disposition:displeased", "trigger:constraint_warning"]

    subject_ref: Optional[str] = None
    # What specifically prompted this — event log key or
    # entity name — for the dialogue to reference concretely

    suppressed: bool = False
    # Some triggers are generated but not surfaced to the player
    # if disposition is high enough that the Luminary lets it pass


# ─────────────────────────────────────────
# FULL LUMINARY EVALUATION
# One complete assessment for one Luminary at one tick.
# ─────────────────────────────────────────

class LuminaryEvaluation(BaseModel):
    """
    The full output of evaluating one Luminary's view
    of the Demiurge's universe at a given moment.
    """
    id: UUID = Field(default_factory=uuid4)
    luminary_id: UUID
    timestamp: float

    attention_level: AttentionLevel
    attention_triggers: list[AttentionTrigger] = Field(default_factory=list)

    domain_alignment_scores: list[DomainAlignmentScore] = Field(
        default_factory=list
    )
    overall_domain_alignment: float = 0.0
    # Weighted average across all this Luminary's domains

    constraint_evaluations: list[ConstraintEvaluation] = Field(
        default_factory=list
    )

    footprint_assessment: FootprintAssessment

    essence_suspicion: EssenceSuspicion

    disposition_delta: DispositionDelta = Field(
        default_factory=DispositionDelta
    )

    dialogue_triggers: list[DialogueTrigger] = Field(default_factory=list)

    summary_note: str = ""
    # Human-readable digest for the event log and UI


# ─────────────────────────────────────────
# EVALUATION ENGINE
# The logic that produces LuminaryEvaluation from state.
# ─────────────────────────────────────────

class EvaluationEngine:
    """
    Produces LuminaryEvaluation for each Luminary
    at each evaluation tick.

    Takes:
      - The full world model (Universe, all entities)
      - The Luminary being evaluated
      - The current domain profile of the universe
      - Recent action log (since last evaluation)
      - Current EssenceStockpile

    Returns: LuminaryEvaluation
    """

    # ── Attention ─────────────────────────────────────

    @staticmethod
    def compute_attention_level(
        base_attention: float,
        recent_triggers: list[AttentionTrigger]
    ) -> AttentionLevel:
        """
        Map accumulated attention float to AttentionLevel enum.
        Triggers from this tick are factored in.
        """
        net = base_attention + sum(t.delta for t in recent_triggers)
        net = max(0.0, min(1.0, net))

        if net < 0.15:
            return AttentionLevel.NEGLIGENT
        elif net < 0.35:
            return AttentionLevel.PASSIVE
        elif net < 0.60:
            return AttentionLevel.WATCHFUL
        elif net < 0.80:
            return AttentionLevel.SCRUTINOUS
        else:
            return AttentionLevel.INVASIVE

    # ── Domain Alignment ─────────────────────────────

    @staticmethod
    def score_domain_alignment(
        luminary_domain_tags: list[str],
        current_profile: UniverseDomainProfile,
        previous_profile: UniverseDomainProfile,
    ) -> tuple[list[DomainAlignmentScore], float]:
        """
        Score how well the universe expresses each of the
        Luminary's domain tags. Returns per-domain scores
        and an overall weighted value.
        """
        scores = []
        for tag in luminary_domain_tags:
            score = DomainAlignmentScore(
                domain_tag=tag,
                current_score=current_profile.scores.get(tag, 0.0),
                previous_score=previous_profile.scores.get(tag, 0.0),
            )
            scores.append(score)

        if not scores:
            return [], 0.0

        overall = sum(s.weighted_value for s in scores) / len(scores)
        return scores, overall

    @staticmethod
    def domain_alignment_to_results_delta(
        overall_alignment: float,
        previous_alignment: float,
        temperament: str,
    ) -> DispositionDeltaReason:
        """
        Convert domain alignment into a results disposition delta.
        Temperament affects sensitivity — a zealous Luminary
        swings harder on both improvement and decline.
        """
        raw_delta = (overall_alignment - previous_alignment)

        temperament_multipliers = {
            "zealous":    2.0,
            "wrathful":   1.5,
            "orderly":    1.2,
            "patient":    0.7,
            "indifferent": 0.3,
            "capricious": 1.0,   # High variance applied separately
        }
        multiplier = temperament_multipliers.get(temperament, 1.0)

        return DispositionDeltaReason(
            axis="results",
            delta=raw_delta * multiplier,
            source="domain_alignment",
            note=(
                f"Universe domain alignment moved from "
                f"{previous_alignment:.2f} to {overall_alignment:.2f}"
            )
        )

    # ── Constraint Evaluation ────────────────────────

    @staticmethod
    def evaluate_footprint_constraint(
        category: str,
        actual_value: float,
        tolerance: float,
        enforcement_weight: float,
        attention_level: AttentionLevel,
    ) -> ConstraintEvaluation:
        """
        Evaluate a single footprint-based constraint.
        At low attention levels, perceived value is dampened —
        the Luminary isn't looking hard enough to see everything.
        """
        attention_perception = {
            AttentionLevel.NEGLIGENT:  0.2,
            AttentionLevel.PASSIVE:    0.5,
            AttentionLevel.WATCHFUL:   0.8,
            AttentionLevel.SCRUTINOUS: 0.95,
            AttentionLevel.INVASIVE:   1.0,
        }
        perceived = actual_value * attention_perception[attention_level]
        ratio = perceived / tolerance if tolerance > 0 else float('inf')

        if ratio <= 0.5:
            compliance = ConstraintComplianceLevel.EXEMPLARY
            disp_delta = 0.02 * enforcement_weight
            att_delta  = -0.02
        elif ratio <= 1.0:
            compliance = ConstraintComplianceLevel.COMPLIANT
            disp_delta = 0.0
            att_delta  = 0.0
        elif ratio <= 1.3:
            compliance = ConstraintComplianceLevel.STRAINING
            disp_delta = -0.05 * enforcement_weight
            att_delta  =  0.05
        elif ratio <= 1.6:
            compliance = ConstraintComplianceLevel.BREACHING
            disp_delta = -0.15 * enforcement_weight
            att_delta  =  0.15
        else:
            compliance = ConstraintComplianceLevel.FLAGRANT
            disp_delta = -0.35 * enforcement_weight
            att_delta  =  0.30

        return ConstraintEvaluation(
            constraint_id=uuid4(),      # Placeholder; real impl passes actual UUID
            constraint_name=f"footprint:{category}",
            compliance=compliance,
            measured_value=perceived,
            threshold=tolerance,
            disposition_delta=disp_delta,
            attention_delta=att_delta,
            note=f"{category} at {perceived:.2f} vs tolerance {tolerance:.2f}"
        )

    # ── Essence Suspicion ────────────────────────────

    @staticmethod
    def evaluate_essence_suspicion(
        luminary_id: UUID,
        apparent_stockpile: float,
        concealment_integrity: float,
        recent_underreal_actions: int,
        attention_level: AttentionLevel,
        herald_reported_anomaly: bool = False,
    ) -> EssenceSuspicion:
        """
        Compute suspicion level and its disposition contribution.
        A Luminary at NEGLIGENT attention won't notice
        mild concealment cracks; at INVASIVE they'll
        detect even well-hidden stockpiles.
        """
        triggers = []
        suspicion = 0.0

        # Apparent stockpile is always visible
        if apparent_stockpile > 0.1:
            suspicion += apparent_stockpile * 0.3
            triggers.append("apparent_essence_detected")

        # Concealment degradation raises suspicion at high attention
        if concealment_integrity < 0.8:
            attention_factor = {
                AttentionLevel.NEGLIGENT:  0.0,
                AttentionLevel.PASSIVE:    0.1,
                AttentionLevel.WATCHFUL:   0.3,
                AttentionLevel.SCRUTINOUS: 0.6,
                AttentionLevel.INVASIVE:   1.0,
            }[attention_level]
            suspicion += (1.0 - concealment_integrity) * attention_factor
            if concealment_integrity < 0.5:
                triggers.append("concealment_degraded")

        # Underreal action pattern is a signal even without detection
        if recent_underreal_actions > 0:
            suspicion += min(0.3, recent_underreal_actions * 0.08)
            triggers.append("underreal_action_pattern")

        if herald_reported_anomaly:
            suspicion += 0.25
            triggers.append("herald_reported_anomaly")

        suspicion = min(1.0, suspicion)

        # Disposition hit scales with suspicion
        # Low suspicion: minor methods concern
        # High suspicion: significant methods degradation
        if suspicion < 0.2:
            disp_delta = -suspicion * 0.1
        elif suspicion < 0.6:
            disp_delta = -suspicion * 0.3
        else:
            disp_delta = -suspicion * 0.6

        att_delta = suspicion * 0.2 if suspicion > 0.3 else 0.0

        return EssenceSuspicion(
            luminary_id=luminary_id,
            apparent_stockpile_reading=apparent_stockpile,
            suspicion_level=suspicion,
            suspicion_triggers=triggers,
            disposition_delta=disp_delta,
            attention_delta=att_delta,
        )

    # ── Dialogue Trigger Generation ──────────────────

    @staticmethod
    def generate_dialogue_triggers(
        luminary_id: UUID,
        luminary_domain_tags: list[str],
        temperament: str,
        current_disposition: "Disposition",
        delta: DispositionDelta,
        constraint_evals: list[ConstraintEvaluation],
        essence_suspicion: EssenceSuspicion,
        timestamp: float,
    ) -> list[DialogueTrigger]:
        """
        Decide what the Luminary wants to say this tick.
        Not every evaluation produces dialogue —
        only meaningful changes or thresholds crossed.
        """
        triggers = []
        base_tags = (
            luminary_domain_tags
            + [f"temperament:{temperament}"]
        )

        # Disposition bracket tag
        overall = current_disposition.overall
        if overall > 0.5:
            base_tags.append("disposition:pleased")
        elif overall > 0.0:
            base_tags.append("disposition:neutral")
        elif overall > -0.5:
            base_tags.append("disposition:displeased")
        else:
            base_tags.append("disposition:hostile")

        # Results movement
        if delta.results > 0.1:
            triggers.append(DialogueTrigger(
                luminary_id=luminary_id,
                trigger_type=DialogueTriggerType.PLEASED_WITH_RESULTS,
                timestamp=timestamp,
                urgency=0.3,
                context_tags=base_tags + ["trigger:pleased_results"],
                suppressed=(overall > 0.7),
                # High-disposition Luminaries don't always comment on good news
            ))
        elif delta.results < -0.1:
            triggers.append(DialogueTrigger(
                luminary_id=luminary_id,
                trigger_type=DialogueTriggerType.DISPLEASED_WITH_RESULTS,
                timestamp=timestamp,
                urgency=0.5 + abs(delta.results),
                context_tags=base_tags + ["trigger:displeased_results"],
            ))

        # Constraint violations
        for ce in constraint_evals:
            if ce.compliance == ConstraintComplianceLevel.STRAINING:
                triggers.append(DialogueTrigger(
                    luminary_id=luminary_id,
                    trigger_type=DialogueTriggerType.CONSTRAINT_WARNING,
                    timestamp=timestamp,
                    urgency=0.5,
                    context_tags=base_tags + [
                        "trigger:constraint_warning",
                        f"constraint:{ce.constraint_name}"
                    ],
                    subject_ref=ce.constraint_name,
                ))
            elif ce.compliance in (
                ConstraintComplianceLevel.BREACHING,
                ConstraintComplianceLevel.FLAGRANT
            ):
                triggers.append(DialogueTrigger(
                    luminary_id=luminary_id,
                    trigger_type=DialogueTriggerType.CONSTRAINT_ULTIMATUM,
                    timestamp=timestamp,
                    urgency=0.9,
                    context_tags=base_tags + [
                        "trigger:constraint_ultimatum",
                        f"constraint:{ce.constraint_name}"
                    ],
                    subject_ref=ce.constraint_name,
                ))

        # Essence suspicion
        if essence_suspicion.suspicion_level > 0.5:
            triggers.append(DialogueTrigger(
                luminary_id=luminary_id,
                trigger_type=DialogueTriggerType.ESSENCE_ACCUSATION,
                timestamp=timestamp,
                urgency=0.8,
                context_tags=base_tags + ["trigger:essence_accusation"],
            ))
        elif essence_suspicion.suspicion_level > 0.25:
            triggers.append(DialogueTrigger(
                luminary_id=luminary_id,
                trigger_type=DialogueTriggerType.ESSENCE_INQUIRY,
                timestamp=timestamp,
                urgency=0.5,
                context_tags=base_tags + ["trigger:essence_inquiry"],
                suppressed=(temperament == "indifferent"),
            ))

        return triggers
