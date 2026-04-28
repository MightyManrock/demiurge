from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from uuid import UUID, uuid4
import random
import math

from action_core import (
    DomainVector,
    StateMutation, MutationType,
    ActionOutcome,
    ActionInstance,
    EssenceStockpile,
    build_action_library,
    ActionDefinition,
    ActionReliability,
    WhisperIntent, ProbabilityNudgeIntent,
    ProxiusDirectiveIntent, EssenceHarvestIntent,
    TargetType,
)
from eval_core import (
    UniverseDomainProfile,
    LuminaryEvaluation,
    DialogueTrigger,
    EvaluationEngine,
    AttentionTrigger,
    FootprintAssessment,
    EssenceSuspicion,
    DispositionDelta,
    DispositionDeltaReason,
)
from onto_core import (
    Demiurge, Pantheon, Luminary, Domain,
)
from universe_core import (
    Universe, Galaxy, System, World, Civilization, NotableMortal,
    MortalRole,
)


# ─────────────────────────────────────────
# TICK CONFIGURATION
# Tunable constants separated from logic.
# ─────────────────────────────────────────

class TickConfig(BaseModel):
    """
    Simulation parameters. Scenarios can override these
    to change pacing — a fast-burn scenario might have
    higher decay rates and more volatile civilization momentum.
    """

    # Time
    tick_duration: float = 1.0
    # One tick = this many universe time units.
    # Scenario defines what a time unit means narratively.

    # Footprint decay
    # Divine traces fade naturally each tick.
    footprint_decay_rate: float = 0.05
    # Subtracted from each footprint category per tick,
    # floor 0.0. Subtle influence fades faster than
    # direct creation — handled by per-category multipliers.
    footprint_decay_multipliers: dict[str, float] = Field(
        default_factory=lambda: {
            "overt_miracles":  1.0,
            "subtle_influence": 1.8,  # Fades faster — it's deniable by design
            "proxius_activity": 0.8,
            "direct_creation":  0.4,  # Reshaping a world doesn't unhappen quickly
        }
    )

    # Concealment degradation
    concealment_decay_rate: float = 0.02
    # concealment_integrity drops this much per tick passively.
    # Spending Essence adds on top of this.

    # Civilization momentum
    # How much a civilization's stats move on their own per tick.
    civ_momentum_rate: float = 0.02
    civ_noise_factor: float = 0.01
    # Small random perturbation each tick — civilizations
    # are not perfectly predictable.

    # Mortal alignment drift
    # Proxii and Heralds slowly drift toward their personal tags
    # and away from their patron's agenda unless directed.
    alignment_drift_rate: float = 0.01

    # Luminary attention decay
    # Attention naturally falls when nothing interesting happens.
    attention_decay_rate: float = 0.03

    # Evaluation frequency
    # Not every tick triggers a full Luminary evaluation.
    # Evaluation happens when: attention crosses a threshold,
    # a constraint is breached, or this many ticks have elapsed.
    evaluation_interval: float = 10.0


# ─────────────────────────────────────────
# TICK PHASES
# ─────────────────────────────────────────

class TickPhase(str, Enum):
    PASSIVE_WORLD    = "passive_world"
    ACTION_PROCESSING = "action_processing"
    DOMAIN_PROFILING  = "domain_profiling"
    EVALUATION        = "evaluation"
    DISPOSITION_UPDATE = "disposition_update"
    TERMINAL_CHECK    = "terminal_check"


# ─────────────────────────────────────────
# PASSIVE CHANGES
# What happens without the Demiurge doing anything.
# ─────────────────────────────────────────

class CivilizationMomentum(BaseModel):
    """
    The direction a civilization is naturally trending.
    Set by recent history, current health, and any
    active subtle influence effects.
    Passive simulation moves it along this vector each tick.
    """
    civilization_id: UUID
    stability_delta:  float = 0.0
    prosperity_delta: float = 0.0
    cohesion_delta:   float = 0.0
    belief_drift: list["DomainVector"] = Field(default_factory=list)
    # Domain tags this civilization is naturally drifting toward/away from


class PassiveWorldResult(BaseModel):
    """What the passive simulation phase produced."""
    civilization_mutations: list["StateMutation"] = Field(default_factory=list)
    mortal_mutations:       list["StateMutation"] = Field(default_factory=list)
    footprint_mutations:    list["StateMutation"] = Field(default_factory=list)
    concealment_mutations:  list["StateMutation"] = Field(default_factory=list)
    attention_mutations:    list["StateMutation"] = Field(default_factory=list)
    narrative_events:       list[str] = Field(default_factory=list)
    # Brief descriptions of notable passive developments
    # e.g. "The Verath Confederation collapsed into civil war"
    #      "Proxius Aldren has begun acting outside their directive"


# ─────────────────────────────────────────
# ACTION PROCESSING RESULT
# ─────────────────────────────────────────

class ActionProcessingResult(BaseModel):
    """
    Results from processing all queued actions this tick.
    One entry per action instance attempted.
    """
    class ActionEntry(BaseModel):
        action_instance_id: UUID
        outcome:   "ActionOutcome"
        mutations: list["StateMutation"] = Field(default_factory=list)
        narrative: str = ""

    entries: list[ActionEntry] = Field(default_factory=list)


# ─────────────────────────────────────────
# TERMINAL CONDITIONS
# ─────────────────────────────────────────

class TerminalConditionType(str, Enum):
    NONE               = "none"
    VICTORY_COMPLIANCE = "victory_compliance"
    # Met all Luminary demands to scenario end condition

    VICTORY_SUBVERSION = "victory_subversion"
    # Nominally satisfied demands while achieving a
    # contradictory hidden agenda

    VICTORY_OVERTHROW  = "victory_overthrow"
    # Successfully moved against one or more Luminaries

    DEFEAT_CAST_DOWN   = "defeat_cast_down"
    # Demoted to the Underreal

    DEFEAT_REPLACED    = "defeat_replaced"
    # Luminaries appointed a new Demiurge; you watch

    SCENARIO_EXPIRED   = "scenario_expired"
    # Time limit reached — evaluated against final state


class TerminalCheck(BaseModel):
    condition: TerminalConditionType = TerminalConditionType.NONE
    triggered: bool = False
    note: str = ""


# ─────────────────────────────────────────
# TICK RESULT
# The complete output of one tick.
# ─────────────────────────────────────────

class TickResult(BaseModel):
    """
    Everything that happened in one tick.
    The UI reads this, not raw state.
    The event log stores these.
    """
    tick_number: int
    universe_age_before: float
    universe_age_after:  float

    passive_result:     PassiveWorldResult
    action_result:      ActionProcessingResult
    domain_profile:     "UniverseDomainProfile"
    evaluations:        list["LuminaryEvaluation"] = Field(default_factory=list)
    disposition_changes: dict[str, tuple[float, float]] = Field(
        default_factory=dict
    )
    # luminary_id -> (results_new, methods_new)

    dialogue_triggers:  list["DialogueTrigger"] = Field(default_factory=list)
    # Unsuppressed triggers only — these go to the player

    terminal: TerminalCheck = Field(default_factory=TerminalCheck)

    seed: int = 0
    # RNG seed used this tick — for reproducibility


# ─────────────────────────────────────────
# SIMULATION STATE
# Everything the tick loop needs in one place.
# ─────────────────────────────────────────

class SimulationState(BaseModel):
    """
    The full live state of a running simulation.
    Passed into and returned from each tick.
    Serializable — this is your save file.
    """
    universe:      "Universe"
    demiurge:      "Demiurge"
    essence:       "EssenceStockpile"
    pantheon:      "Pantheon"
    luminaries:    dict[str, "Luminary"]    # str(UUID) -> Luminary
    domains:       dict[str, "Domain"]      # str(UUID) -> Domain
    galaxies:      dict[str, "Galaxy"]
    systems:       dict[str, "System"]
    worlds:        dict[str, "World"]
    civilizations: dict[str, "Civilization"]
    mortals:       dict[str, "NotableMortal"]

    # Momentum vectors for each civilization
    # Updated by actions and passive simulation
    civ_momentum: dict[str, CivilizationMomentum] = Field(
        default_factory=dict
    )

    # Queued actions waiting to be processed this tick
    action_queue: list["ActionInstance"] = Field(default_factory=list)

    # Previous domain profile for trajectory calculation
    previous_domain_profile: Optional["UniverseDomainProfile"] = None

    # Per-Luminary attention float (separate from the enum)
    luminary_attention: dict[str, float] = Field(default_factory=dict)
    # str(UUID) -> 0.0-1.0

    # Ticks since last full evaluation per Luminary
    ticks_since_evaluation: dict[str, float] = Field(default_factory=dict)

    tick_number: int = 0
    config: TickConfig = Field(default_factory=TickConfig)


# ─────────────────────────────────────────
# TICK LOOP
# ─────────────────────────────────────────

class TickLoop:

    def __init__(self, rng_seed: Optional[int] = None):
        self.rng_seed = rng_seed or random.randint(0, 2**32)
        self._rng = random.Random(self.rng_seed)

    def advance(
        self,
        state: SimulationState,
    ) -> tuple[SimulationState, TickResult]:
        """
        Advance the simulation by one tick.
        Returns updated state and the tick result.
        Pure(-ish) function — state mutations are
        collected as StateMutation lists and applied
        at the end of each phase.
        """
        cfg = state.config
        seed = self._rng.randint(0, 2**32)
        phase_rng = random.Random(seed)

        result = TickResult(
            tick_number=state.tick_number,
            universe_age_before=state.universe.current_age,
            universe_age_after=state.universe.current_age + cfg.tick_duration,
            passive_result=PassiveWorldResult(),
            action_result=ActionProcessingResult(),
            domain_profile=UniverseDomainProfile(
                timestamp=state.universe.current_age
            ),
            seed=seed,
        )

        # ── Phase 1: Passive World ─────────────────────
        passive = self._run_passive_phase(state, cfg, phase_rng)
        result.passive_result = passive
        state = self._apply_passive_mutations(state, passive)

        # ── Phase 2: Action Processing ─────────────────
        action_result = self._process_action_queue(state, cfg, phase_rng)
        result.action_result = action_result
        state = self._apply_action_mutations(state, action_result)
        state.action_queue = []

        # ── Phase 3: Domain Profiling ──────────────────
        profile = self._build_domain_profile(state)
        result.domain_profile = profile

        # ── Phase 4: Evaluation ────────────────────────
        evaluations = self._run_evaluations(state, profile, cfg)
        result.evaluations = evaluations

        # ── Phase 5: Disposition Update ───────────────
        state, disposition_changes = self._apply_disposition_deltas(
            state, evaluations
        )
        result.disposition_changes = disposition_changes

        # Collect unsuppressed dialogue triggers
        for ev in evaluations:
            result.dialogue_triggers.extend(
                t for t in ev.dialogue_triggers if not t.suppressed
            )

        # ── Phase 6: Terminal Check ────────────────────
        terminal = self._check_terminal_conditions(state, profile)
        result.terminal = terminal

        # ── Bookkeeping ────────────────────────────────
        state.universe.current_age += cfg.tick_duration
        state.previous_domain_profile = profile
        state.tick_number += 1

        return state, result

    # ─────────────────────────────────────────
    # PHASE 1: PASSIVE WORLD
    # ─────────────────────────────────────────

    def _run_passive_phase(
        self,
        state: SimulationState,
        cfg: TickConfig,
        rng: random.Random,
    ) -> PassiveWorldResult:

        result = PassiveWorldResult()

        # ── Civilization momentum ──────────────────────
        for cid, civ in state.civilizations.items():
            momentum = state.civ_momentum.get(
                cid,
                CivilizationMomentum(civilization_id=UUID(cid))
            )

            for stat, delta in [
                ("stability",  momentum.stability_delta),
                ("prosperity", momentum.prosperity_delta),
                ("cohesion",   momentum.cohesion_delta),
            ]:
                noise = rng.gauss(0, cfg.civ_noise_factor)
                effective_delta = (delta * cfg.civ_momentum_rate) + noise
                current = getattr(civ.health, stat)
                new_val = max(0.0, min(1.0, current + effective_delta))

                if abs(new_val - current) > 0.001:
                    result.civilization_mutations.append(StateMutation(
                        mutation_type=MutationType.CIVILIZATION_STAT,
                        target_id=UUID(cid),
                        field=f"health.{stat}",
                        delta=effective_delta,
                        note=f"{civ.name} {stat} passive drift",
                    ))

            # Narrative event if a civilization crosses a threshold
            new_stability = civ.health.stability + momentum.stability_delta * cfg.civ_momentum_rate
            if new_stability < 0.2 and civ.health.stability >= 0.2:
                result.narrative_events.append(
                    f"{civ.name} has entered a state of critical instability."
                )
            elif new_stability > 0.8 and civ.health.stability <= 0.8:
                result.narrative_events.append(
                    f"{civ.name} has achieved remarkable stability."
                )

        # ── Mortal alignment drift ─────────────────────
        for mid, mortal in state.mortals.items():
            if mortal.status != "active":
                continue

            # Alignment drifts toward 0.5 (personal agenda)
            # unless a recent directive is holding it up
            drift_toward = 0.5
            drift = (drift_toward - mortal.alignment) * cfg.alignment_drift_rate
            new_alignment = max(0.0, min(1.0, mortal.alignment + drift))

            if abs(new_alignment - mortal.alignment) > 0.001:
                result.mortal_mutations.append(StateMutation(
                    mutation_type=MutationType.MORTAL_ALIGNMENT,
                    target_id=UUID(mid),
                    field="alignment",
                    delta=drift,
                    note=f"{mortal.name} alignment drift",
                ))

            # Flag a Proxius going significantly rogue
            if (mortal.role == "proxius"
                    and mortal.alignment < 0.4
                    and (mortal.alignment - drift) >= 0.4):
                result.narrative_events.append(
                    f"Proxius {mortal.name} appears to be pursuing "
                    f"their own agenda more than yours."
                )

        # ── Footprint decay ────────────────────────────
        fp = state.demiurge.footprint
        for category, multiplier in cfg.footprint_decay_multipliers.items():
            current = getattr(fp, category)
            decay = cfg.footprint_decay_rate * multiplier
            new_val = max(0.0, current - decay)
            if abs(new_val - current) > 0.0001:
                result.footprint_mutations.append(StateMutation(
                    mutation_type=MutationType.FOOTPRINT_CHANGE,
                    target_id=state.demiurge.id,
                    field=category,
                    delta=-(current - new_val),
                    note=f"Footprint decay: {category}",
                ))

        # World-level footprint decay (same logic)
        for wid, world in state.worlds.items():
            for category, multiplier in cfg.footprint_decay_multipliers.items():
                current = getattr(world.local_footprint, category)
                decay = cfg.footprint_decay_rate * multiplier
                new_val = max(0.0, current - decay)
                if abs(new_val - current) > 0.0001:
                    result.footprint_mutations.append(StateMutation(
                        mutation_type=MutationType.FOOTPRINT_CHANGE,
                        target_id=UUID(wid),
                        field=f"local_footprint.{category}",
                        delta=-(current - new_val),
                        note=f"World footprint decay: {category}",
                    ))

        # ── Concealment degradation ────────────────────
        if state.essence.concealment_integrity > 0.0:
            new_integrity = max(
                0.0,
                state.essence.concealment_integrity - cfg.concealment_decay_rate
            )
            result.concealment_mutations.append(StateMutation(
                mutation_type=MutationType.CONCEALMENT_CHANGE,
                target_id=state.demiurge.id,
                field="concealment_integrity",
                delta=-(state.essence.concealment_integrity - new_integrity),
                note="Passive concealment degradation",
            ))

        # ── Luminary attention decay ───────────────────
        for lid in state.luminaries:
            current_att = state.luminary_attention.get(lid, 0.2)
            new_att = max(0.0, current_att - cfg.attention_decay_rate)
            if abs(new_att - current_att) > 0.0001:
                result.attention_mutations.append(StateMutation(
                    mutation_type=MutationType.FOOTPRINT_CHANGE,
                    # Reusing mutation type; a dedicated ATTENTION_CHANGE
                    # type can be added later
                    target_id=UUID(lid),
                    field="attention",
                    delta=-(current_att - new_att),
                    note="Luminary attention decay",
                ))

        return result

    def _apply_passive_mutations(
        self,
        state: SimulationState,
        passive: PassiveWorldResult,
    ) -> SimulationState:

        all_mutations = (
            passive.civilization_mutations
            + passive.mortal_mutations
            + passive.footprint_mutations
            + passive.concealment_mutations
            + passive.attention_mutations
        )
        return self._apply_mutations(state, all_mutations)

    # ─────────────────────────────────────────
    # PHASE 2: ACTION PROCESSING
    # ─────────────────────────────────────────

    def _process_action_queue(
        self,
        state: SimulationState,
        cfg: TickConfig,
        rng: random.Random,
    ) -> ActionProcessingResult:

        result = ActionProcessingResult()
        library = build_action_library()

        for instance in state.action_queue:
            defn_id = str(instance.action_definition_id)
            # Match by name since we're using string keys in the library
            defn = next(
                (v for v in library.values()
                 if str(v.id) == defn_id or v.name == defn_id),
                None
            )
            if defn is None:
                continue

            outcome, mutations, narrative = self._execute_action(
                instance, defn, state, rng
            )

            result.entries.append(
                ActionProcessingResult.ActionEntry(
                    action_instance_id=instance.id,
                    outcome=outcome,
                    mutations=mutations,
                    narrative=narrative,
                )
            )

        return result

    def _execute_action(
        self,
        instance: "ActionInstance",
        defn: "ActionDefinition",
        state: SimulationState,
        rng: random.Random,
    ) -> tuple["ActionOutcome", list["StateMutation"], str]:

        mutations: list[StateMutation] = []

        # ── Reliability roll ───────────────────────────
        outcome = self._roll_reliability(defn.reliability, rng)
        if outcome == ActionOutcome.FAILURE:
            return outcome, [], f"{defn.name} failed to produce any effect."

        partial = (outcome == ActionOutcome.PARTIAL)

        # ── Footprint application ──────────────────────
        scale = 0.5 if partial else 1.0

        for category in ["overt_miracles", "subtle_influence",
                          "proxius_activity", "direct_creation"]:
            cost = getattr(defn.footprint_cost, category) * scale
            if cost > 0.0:
                # Universe-wide footprint
                mutations.append(StateMutation(
                    mutation_type=MutationType.FOOTPRINT_CHANGE,
                    target_id=state.demiurge.id,
                    field=category,
                    delta=cost,
                    note=f"{defn.name}: footprint {category}",
                ))
                # World-level footprint if target is a world/civ/mortal
                world_id = self._resolve_world_id(instance, state)
                if world_id:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.FOOTPRINT_CHANGE,
                        target_id=world_id,
                        field=f"local_footprint.{category}",
                        delta=cost,
                        note=f"{defn.name}: local footprint {category}",
                    ))

        # ── Essence handling ───────────────────────────
        if defn.essence_cost != 0.0:
            effective_cost = defn.essence_cost * scale
            mutations.append(StateMutation(
                mutation_type=MutationType.ESSENCE_CHANGE,
                target_id=state.demiurge.id,
                field="actual",
                delta=-effective_cost,
                # Negative cost = harvest (essence_cost is negative in definition)
                note=f"{defn.name}: essence {'harvest' if effective_cost < 0 else 'spend'}",
            ))
            if defn.concealment_impact > 0.0:
                apparent_leak = defn.concealment_impact * scale
                mutations.append(StateMutation(
                    mutation_type=MutationType.CONCEALMENT_CHANGE,
                    target_id=state.demiurge.id,
                    field="apparent",
                    delta=apparent_leak,
                    note=f"{defn.name}: concealment leak",
                ))

        # ── Attention spike for high-footprint actions ─
        fp_total = defn.footprint_cost.total() * scale
        if fp_total > 0.3:
            for lid in state.luminaries:
                current = state.luminary_attention.get(lid, 0.2)
                spike = fp_total * 0.3
                mutations.append(StateMutation(
                    mutation_type=MutationType.FOOTPRINT_CHANGE,
                    target_id=UUID(lid),
                    field="attention",
                    delta=spike,
                    note=f"Attention spike from {defn.name}",
                ))

        # ── Intent-specific mutations ──────────────────
        intent_mutations, narrative = self._resolve_intent_mutations(
            instance, defn, state, outcome, rng
        )
        mutations.extend(intent_mutations)

        return outcome, mutations, narrative

    def _roll_reliability(
        self,
        reliability: "ActionReliability",
        rng: random.Random,
    ) -> "ActionOutcome":

        roll = rng.random()
        if reliability == ActionReliability.CERTAIN:
            return ActionOutcome.SUCCESS
        elif reliability == ActionReliability.PROBABLE:
            if roll < 0.75:
                return ActionOutcome.SUCCESS
            elif roll < 0.90:
                return ActionOutcome.PARTIAL
            else:
                return ActionOutcome.FAILURE
        elif reliability == ActionReliability.UNCERTAIN:
            if roll < 0.50:
                return ActionOutcome.SUCCESS
            elif roll < 0.75:
                return ActionOutcome.PARTIAL
            else:
                return ActionOutcome.FAILURE
        else:  # CHAOTIC
            if roll < 0.30:
                return ActionOutcome.SUCCESS
            elif roll < 0.60:
                return ActionOutcome.PARTIAL
            elif roll < 0.80:
                return ActionOutcome.FAILURE
            else:
                return ActionOutcome.CHAOTIC_RESULT

    def _resolve_intent_mutations(
        self,
        instance: "ActionInstance",
        defn: "ActionDefinition",
        state: SimulationState,
        outcome: "ActionOutcome",
        rng: random.Random,
    ) -> tuple[list[StateMutation], str]:
        """
        Produce state mutations from the action's specific intent.
        This is where WhisperIntent, OmenIntent, etc. are read
        and translated into belief shifts, stat changes, etc.
        """
        mutations: list[StateMutation] = []
        narrative = f"{defn.name} executed."

        intent = instance.intent
        if intent is None:
            return mutations, narrative

        # ── Whisper / Dream ───────────────────────────
        if isinstance(intent, WhisperIntent):
            if outcome == ActionOutcome.FAILURE:
                return mutations, f"{defn.name} found no purchase in the mortal's mind."

            mortal = state.mortals.get(str(instance.target_id))
            if not mortal:
                return mutations, narrative

            effectiveness = 1.0 if outcome == ActionOutcome.SUCCESS else 0.4
            effectiveness *= mortal.alignment
            # A drifting Proxius is also harder to reach with whispers

            for dv in intent.domain_vectors:
                civ_id = str(mortal.civilization_id) if mortal.civilization_id else None
                if civ_id and civ_id in state.civilizations:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.BELIEF_SHIFT,
                        target_id=mortal.civilization_id,
                        field="dominant_beliefs",
                        delta=dv.direction * effectiveness * 0.1,
                        new_value=dv.domain_tag,
                        note=(
                            f"Whisper to {mortal.name}: "
                            f"'{intent.concept[:40]}...'"
                        ),
                    ))

            narrative = (
                f"You whispered to {mortal.name}: '{intent.concept}'. "
                f"Effectiveness: {effectiveness:.0%}."
            )

        # ── Probability Nudge ─────────────────────────
        elif isinstance(intent, ProbabilityNudgeIntent):
            if outcome == ActionOutcome.FAILURE:
                return mutations, "The probability nudge dissipated without effect."

            effectiveness = intent.nudge_strength
            if outcome == ActionOutcome.PARTIAL:
                effectiveness *= 0.4

            target_id = instance.target_id
            for dv in intent.domain_vectors:
                mutations.append(StateMutation(
                    mutation_type=MutationType.BELIEF_SHIFT,
                    target_id=target_id,
                    field="dominant_beliefs",
                    delta=dv.direction * effectiveness * 0.15,
                    new_value=dv.domain_tag,
                    note=(
                        f"Probability nudge: '{intent.event_description[:40]}' "
                        f"toward '{intent.desired_outcome[:40]}'"
                    ),
                ))

            narrative = (
                f"You nudged the odds around '{intent.event_description}'. "
                f"Desired outcome: '{intent.desired_outcome}'. "
                f"Strength applied: {effectiveness:.0%}."
            )

        # ── Proxius Directive ─────────────────────────
        elif isinstance(intent, ProxiusDirectiveIntent):
            proxius = state.mortals.get(str(instance.proxius_id))
            if not proxius:
                return mutations, "No Proxius found to receive directive."

            # How faithfully they interpret the directive
            # depends on alignment and how much latitude you gave
            interpretation_fidelity = (
                proxius.alignment * (1.0 - intent.latitude * 0.5)
            )
            if outcome == ActionOutcome.PARTIAL:
                interpretation_fidelity *= 0.6

            # Narrative note about fidelity
            if interpretation_fidelity > 0.7:
                fidelity_note = "faithfully"
            elif interpretation_fidelity > 0.4:
                fidelity_note = "with some personal interpretation"
            else:
                fidelity_note = "with significant deviation from your intent"

            # Resistance to alignment drift while directive is active
            # — temporary alignment boost toward 1.0
            alignment_boost = interpretation_fidelity * 0.2
            mutations.append(StateMutation(
                mutation_type=MutationType.MORTAL_ALIGNMENT,
                target_id=proxius.id,
                field="alignment",
                delta=alignment_boost,
                note=f"Directive received: '{intent.goal_statement[:40]}'",
            ))

            # Domain expression shift proportional to fidelity
            world_id = state.worlds.get(str(proxius.world_id))
            if world_id:
                for dv in intent.domain_vectors:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.DOMAIN_EXPRESSION,
                        target_id=proxius.world_id,
                        field="domain_expression",
                        delta=dv.direction * interpretation_fidelity * 0.08,
                        new_value=dv.domain_tag,
                        note=f"Proxius {proxius.name} acting on directive {fidelity_note}",
                    ))

            narrative = (
                f"Proxius {proxius.name} received directive: "
                f"'{intent.goal_statement}'. "
                f"They are likely to act {fidelity_note}."
            )

        # ── Essence Harvest ───────────────────────────
        elif isinstance(intent, EssenceHarvestIntent):
            if outcome == ActionOutcome.FAILURE:
                return mutations, "The Underreal offered nothing this time."

            # Yield modulated by concealment priority
            # High concealment = slower, but less apparent leak
            base_yield = 0.3
            if outcome == ActionOutcome.PARTIAL:
                base_yield *= 0.5
            concealment_factor = intent.concealment_priority
            actual_yield = base_yield * (0.5 + concealment_factor * 0.5)
            apparent_leak = base_yield * (1.0 - concealment_factor) * 0.5

            mutations.append(StateMutation(
                mutation_type=MutationType.ESSENCE_CHANGE,
                target_id=state.demiurge.id,
                field="actual",
                delta=actual_yield,
                note="Essence harvested from Underreal",
            ))
            if apparent_leak > 0.0:
                mutations.append(StateMutation(
                    mutation_type=MutationType.ESSENCE_CHANGE,
                    target_id=state.demiurge.id,
                    field="apparent",
                    delta=apparent_leak,
                    note="Essence concealment leak during harvest",
                ))

            narrative = (
                f"Harvested {actual_yield:.2f} Essence from the Underreal. "
                f"Apparent leak: {apparent_leak:.2f}. "
                f"Concealment integrity held at {intent.concealment_priority:.0%} priority."
            )

        return mutations, narrative

    def _apply_action_mutations(
        self,
        state: SimulationState,
        action_result: ActionProcessingResult,
    ) -> SimulationState:
        all_mutations = [
            m for entry in action_result.entries
            for m in entry.mutations
        ]
        return self._apply_mutations(state, all_mutations)

    # ─────────────────────────────────────────
    # PHASE 3: DOMAIN PROFILING
    # ─────────────────────────────────────────

    def _build_domain_profile(
        self,
        state: SimulationState,
    ) -> "UniverseDomainProfile":
        """
        Survey all civilizations and aggregate their
        domain_expression and dominant_beliefs into a
        universe-wide profile. Weighted by civilization
        scale and health.
        """
        from collections import defaultdict

        scale_weights = {
            "nascent":        0.1,
            "tribal":         0.2,
            "city_state":     0.3,
            "regional":       0.5,
            "continental":    0.7,
            "planetary":      1.0,
            "interplanetary": 1.5,
            "interstellar":   2.0,
        }

        raw_scores: dict[str, float] = defaultdict(float)
        total_weight = 0.0

        for civ in state.civilizations.values():
            w = scale_weights.get(civ.scale, 0.5) * civ.health.overall()
            total_weight += w
            for belief_tag in civ.dominant_beliefs:
                raw_scores[belief_tag] += w

        # Also factor in world-level domain_expression
        for world in state.worlds.values():
            world_weight = 0.3  # Worlds contribute less than civilizations
            for tag in world.domain_expression:
                raw_scores[tag] += world_weight
                total_weight += world_weight

        if total_weight == 0.0:
            return UniverseDomainProfile(
                timestamp=state.universe.current_age
            )

        normalized = {
            tag: min(1.0, score / total_weight)
            for tag, score in raw_scores.items()
        }

        return UniverseDomainProfile(
            timestamp=state.universe.current_age,
            scores=normalized,
        )

    # ─────────────────────────────────────────
    # PHASE 4: EVALUATION
    # ─────────────────────────────────────────

    def _run_evaluations(
        self,
        state: SimulationState,
        profile: "UniverseDomainProfile",
        cfg: TickConfig,
    ) -> list["LuminaryEvaluation"]:

        evaluations = []
        engine = EvaluationEngine()
        prev_profile = state.previous_domain_profile or profile

        for lid, luminary in state.luminaries.items():
            ticks_since = state.ticks_since_evaluation.get(lid, cfg.evaluation_interval)
            current_att = state.luminary_attention.get(lid, 0.2)

            # Evaluate if: interval elapsed, attention is high, or constraint breach
            should_evaluate = (
                ticks_since >= cfg.evaluation_interval
                or current_att > 0.6
            )
            if not should_evaluate:
                state.ticks_since_evaluation[lid] = ticks_since + 1
                continue

            state.ticks_since_evaluation[lid] = 0.0

            # Gather Luminary domain tags from its domain objects
            luminary_domain_tags = []
            for did in luminary.domains:
                domain = state.domains.get(str(did))
                if domain:
                    luminary_domain_tags.extend(domain.tags)

            # Attention level
            attention_triggers: list[AttentionTrigger] = []
            attention_level = engine.compute_attention_level(
                current_att, attention_triggers
            )

            # Domain alignment
            domain_scores, overall_alignment = engine.score_domain_alignment(
                luminary_domain_tags, profile, prev_profile
            )

            prev_overall = sum(
                prev_profile.scores.get(t, 0.0)
                for t in luminary_domain_tags
            ) / max(1, len(luminary_domain_tags))

            # Constraint evaluations
            constraint_evals = []
            tolerances = state.universe.rules.footprint_tolerances
            for category in ["overt_miracles", "subtle_influence",
                              "proxius_activity", "direct_creation"]:
                fp_value = getattr(state.demiurge.footprint, category)
                tolerance = getattr(tolerances, category)

                ce = engine.evaluate_footprint_constraint(
                    category=category,
                    actual_value=fp_value,
                    tolerance=tolerance,
                    enforcement_weight=0.6,
                    attention_level=attention_level,
                )
                constraint_evals.append(ce)

            # Footprint assessment
            fp_assessment = FootprintAssessment(
                luminary_id=luminary.id,
                perceived_footprint={},
                overall_methods_delta=sum(
                    ce.disposition_delta for ce in constraint_evals
                ),
            )

            # Essence suspicion
            recent_underreal = sum(
                1 for entry in []  # Would scan recent action log
                # Placeholder — real impl checks event log
            )
            essence_suspicion = engine.evaluate_essence_suspicion(
                luminary_id=luminary.id,
                apparent_stockpile=state.essence.apparent,
                concealment_integrity=state.essence.concealment_integrity,
                recent_underreal_actions=recent_underreal,
                attention_level=attention_level,
            )

            # Disposition delta assembly
            delta = DispositionDelta()

            results_reason = engine.domain_alignment_to_results_delta(
                overall_alignment, prev_overall, luminary.temperament.value
            )
            delta.results += results_reason.delta
            delta.reasons.append(results_reason)

            # Capricious temperament: random amplification
            if luminary.temperament.value == "capricious":
                capricious_swing = self._rng.gauss(0, 0.1)
                delta.results += capricious_swing
                delta.methods += capricious_swing * 0.5

            methods_delta = (
                fp_assessment.overall_methods_delta
                + essence_suspicion.disposition_delta
            )
            delta.methods += methods_delta
            delta.reasons.append(DispositionDeltaReason(
                axis="methods",
                delta=methods_delta,
                source="footprint_and_essence",
            ))

            # Dialogue triggers
            triggers = engine.generate_dialogue_triggers(
                luminary_id=luminary.id,
                luminary_domain_tags=luminary_domain_tags,
                temperament=luminary.temperament.value,
                current_disposition=luminary.disposition,
                delta=delta,
                constraint_evals=constraint_evals,
                essence_suspicion=essence_suspicion,
                timestamp=state.universe.current_age,
            )

            ev = LuminaryEvaluation(
                luminary_id=luminary.id,
                timestamp=state.universe.current_age,
                attention_level=attention_level,
                attention_triggers=attention_triggers,
                domain_alignment_scores=domain_scores,
                overall_domain_alignment=overall_alignment,
                constraint_evaluations=constraint_evals,
                footprint_assessment=fp_assessment,
                essence_suspicion=essence_suspicion,
                disposition_delta=delta,
                dialogue_triggers=triggers,
                summary_note=self._summarize_evaluation(
                    luminary, delta, overall_alignment
                ),
            )
            evaluations.append(ev)

        return evaluations

    # ─────────────────────────────────────────
    # PHASE 5: DISPOSITION UPDATE
    # ─────────────────────────────────────────

    def _apply_disposition_deltas(
        self,
        state: SimulationState,
        evaluations: list["LuminaryEvaluation"],
    ) -> tuple[SimulationState, dict[str, tuple[float, float]]]:

        changes: dict[str, tuple[float, float]] = {}

        for ev in evaluations:
            lid = str(ev.luminary_id)
            luminary = state.luminaries.get(lid)
            if not luminary:
                continue

            new_results, new_methods = ev.disposition_delta.clamp_to(
                luminary.disposition.results,
                luminary.disposition.methods,
            )
            luminary.disposition.results = new_results
            luminary.disposition.methods = new_methods
            changes[lid] = (new_results, new_methods)

            # Update attention
            att_delta = sum(
                t.delta for t in ev.attention_triggers
            ) + ev.essence_suspicion.attention_delta
            current_att = state.luminary_attention.get(lid, 0.2)
            state.luminary_attention[lid] = max(
                0.0, min(1.0, current_att + att_delta)
            )

        return state, changes

    # ─────────────────────────────────────────
    # PHASE 6: TERMINAL CHECK
    # ─────────────────────────────────────────

    def _check_terminal_conditions(
        self,
        state: SimulationState,
        profile: "UniverseDomainProfile",
    ) -> TerminalCheck:

        # Defeat: all Luminaries hostile
        all_hostile = all(
            lum.disposition.overall < -0.8
            for lum in state.luminaries.values()
        )
        if all_hostile:
            return TerminalCheck(
                condition=TerminalConditionType.DEFEAT_CAST_DOWN,
                triggered=True,
                note=(
                    "Every liege Luminary has turned against you. "
                    "The Underreal awaits."
                ),
            )

        # Victory: overthrow — checked elsewhere when action resolves,
        # but disposition-based collapse of Luminary authority
        # could trigger here too in future iterations.

        # Scenario expiry would check universe age against
        # a scenario end_time field (not yet modeled).

        return TerminalCheck(condition=TerminalConditionType.NONE)

    # ─────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────

    def _resolve_world_id(
        self,
        instance: "ActionInstance",
        state: SimulationState,
    ) -> Optional[UUID]:
        """Find the world ID associated with an action target."""
        if instance.target_type == TargetType.WORLD:
            return instance.target_id
        elif instance.target_type == TargetType.CIVILIZATION:
            civ = state.civilizations.get(str(instance.target_id))
            return civ.world_id if civ else None
        elif instance.target_type == TargetType.MORTAL:
            mortal = state.mortals.get(str(instance.target_id))
            return mortal.world_id if mortal else None
        return None

    def _summarize_evaluation(
        self,
        luminary: "Luminary",
        delta: DispositionDelta,
        alignment: float,
    ) -> str:
        direction = "improving" if delta.results > 0 else "declining"
        return (
            f"{luminary.name}: domain alignment {alignment:.2f} ({direction}), "
            f"results Δ{delta.results:+.2f}, methods Δ{delta.methods:+.2f}."
        )

    def _apply_mutations(
        self,
        state: SimulationState,
        mutations: list["StateMutation"],
    ) -> SimulationState:
        """
        Apply a list of StateMutations to state.
        Numeric deltas are additive; new_value assignments
        are direct sets.
        """
        for m in mutations:
            tid = str(m.target_id) if m.target_id else None

            if m.mutation_type == MutationType.FOOTPRINT_CHANGE:
                if tid == str(state.demiurge.id):
                    obj = state.demiurge.footprint
                    current = getattr(obj, m.field, 0.0)
                    setattr(obj, m.field, max(0.0, min(1.0, current + (m.delta or 0))))
                elif tid in state.worlds:
                    # e.g. field = "local_footprint.overt_miracles"
                    parts = m.field.split(".")
                    if len(parts) == 2:
                        obj = getattr(state.worlds[tid], parts[0])
                        current = getattr(obj, parts[1], 0.0)
                        setattr(obj, parts[1], max(0.0, min(1.0, current + (m.delta or 0))))
                elif tid in state.luminary_attention:
                    current = state.luminary_attention[tid]
                    state.luminary_attention[tid] = max(0.0, min(1.0, current + (m.delta or 0)))
                elif tid in state.luminaries:
                    current = state.luminary_attention.get(tid, 0.2)
                    state.luminary_attention[tid] = max(0.0, min(1.0, current + (m.delta or 0)))

            elif m.mutation_type == MutationType.ESSENCE_CHANGE:
                current = getattr(state.essence, m.field, 0.0)
                setattr(state.essence, m.field, max(0.0, current + (m.delta or 0)))
                # Enforce apparent <= actual
                if state.essence.apparent > state.essence.actual:
                    state.essence.apparent = state.essence.actual

            elif m.mutation_type == MutationType.CONCEALMENT_CHANGE:
                current = getattr(state.essence, m.field, 0.0)
                setattr(state.essence, m.field, max(0.0, min(1.0, current + (m.delta or 0))))

            elif m.mutation_type == MutationType.MORTAL_ALIGNMENT:
                if tid in state.mortals:
                    current = state.mortals[tid].alignment
                    state.mortals[tid].alignment = max(
                        0.0, min(1.0, current + (m.delta or 0))
                    )

            elif m.mutation_type == MutationType.CIVILIZATION_STAT:
                if tid in state.civilizations:
                    parts = m.field.split(".")
                    if len(parts) == 2:
                        obj = getattr(state.civilizations[tid], parts[0])
                        current = getattr(obj, parts[1], 0.0)
                        setattr(obj, parts[1], max(0.0, min(1.0, current + (m.delta or 0))))

            elif m.mutation_type in (
                MutationType.BELIEF_SHIFT,
                MutationType.DOMAIN_EXPRESSION,
            ):
                # Tag-based list mutations — add tag if direction positive,
                # remove if strongly negative. Full weight system later.
                if tid in state.civilizations and m.new_value:
                    beliefs = state.civilizations[tid].dominant_beliefs
                    tag = m.new_value
                    if (m.delta or 0) > 0 and tag not in beliefs:
                        beliefs.append(tag)
                    elif (m.delta or 0) < -0.3 and tag in beliefs:
                        beliefs.remove(tag)
                elif tid in state.worlds and m.new_value:
                    tags = state.worlds[tid].domain_expression
                    tag = m.new_value
                    if (m.delta or 0) > 0 and tag not in tags:
                        tags.append(tag)
                    elif (m.delta or 0) < -0.3 and tag in tags:
                        tags.remove(tag)

        return state
