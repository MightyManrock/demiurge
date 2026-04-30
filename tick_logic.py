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
    WhisperIntent, OmenIntent, ProbabilityNudgeIntent,
    DevelopmentIntent, ProxiusDirectiveIntent,
    LuminaryPetitionIntent, EssenceHarvestIntent, SalvageIntent,
    SeedWorldIntent, UpliftSpeciesIntent, ExploreBeliefIntent,
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
    MortalRole, MortalStatus, MortalProminence, WorldCondition,
    Species, SpeciesCondition,
)
from domain_registry import DomainRegistry, get_registry


# ─────────────────────────────────────────
# MORTAL VISIBILITY CONSTANTS
# ─────────────────────────────────────────

ALWAYS_VISIBLE_THRESHOLD = 0.65

# ─────────────────────────────────────────
# BELIEF SYSTEM CONSTANTS
# ─────────────────────────────────────────

BELIEF_FLOOR = 0.02
# Belief/domain-expression entries below this strength are
# silently pruned each passive phase. Keeps dicts clean of
# ghost residue from many tiny-delta actions.
# Mortals at or above this prominence are always perceived —
# no visibility tracking needed.

VISIBILITY_FLOOR = 0.1
# Below this value a mortal has slipped from the Demiurge's awareness.


def is_mortal_visible(mortal: "NotableMortal") -> bool:
    """True if the Demiurge can currently perceive this mortal."""
    return (
        mortal.status != MortalStatus.DECEASED
        and (
            mortal.prominence >= ALWAYS_VISIBLE_THRESHOLD
            or mortal.visibility > VISIBILITY_FLOOR
        )
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

    # Mortal visibility decay
    # How quickly a non-prominent mortal fades from the Demiurge's awareness.
    mortal_visibility_decay_rate: float = 0.03

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
    species:       dict[str, "Species"] = Field(default_factory=dict)

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

    # Consecutive ticks where essence.actual did not increase.
    # Used to stall passive concealment decay when the Demiurge goes quiet.
    ticks_without_essence_gain: int = 0


# ─────────────────────────────────────────
# TICK LOOP
# ─────────────────────────────────────────

class TickLoop:

    def __init__(self, rng_seed: Optional[int] = None):
        self.rng_seed = rng_seed or random.randint(0, 2**32)
        self._rng = random.Random(self.rng_seed)
        self._action_library = build_action_library()
        self._action_key_by_id: dict[str, str] = {
            str(v.id): k for k, v in self._action_library.items()
        }
        self._overthrow_this_tick: Optional[ActionOutcome] = None
        self._domain_registry: Optional[DomainRegistry] = get_registry()

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
        self._overthrow_this_tick = None
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
        state = self._prune_weak_beliefs(state)

        # ── Phase 2: Action Processing ─────────────────
        _essence_before = state.essence.actual
        action_result = self._process_action_queue(state, cfg, phase_rng)
        result.action_result = action_result
        state = self._apply_action_mutations(state, action_result)
        state.action_queue = []

        # Track how long since the Demiurge last gained Essence (for concealment stall)
        if state.essence.actual > _essence_before:
            state.ticks_without_essence_gain = 0
        else:
            state.ticks_without_essence_gain += 1

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

            # Apply belief_drift from momentum
            for dv in momentum.belief_drift:
                result.civilization_mutations.append(StateMutation(
                    mutation_type=MutationType.BELIEF_SHIFT,
                    target_id=UUID(cid),
                    field="dominant_beliefs",
                    delta=dv.direction * cfg.civ_momentum_rate,
                    new_value=dv.domain_tag,
                    note=f"{civ.name} belief drift: {dv.domain_tag}",
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

        # ── Mortal aging ───────────────────────────────
        for mid, mortal in state.mortals.items():
            if mortal.status == MortalStatus.DECEASED:
                continue

            # chrono_age always increments
            result.mortal_mutations.append(StateMutation(
                mutation_type=MutationType.MORTAL_AGE,
                target_id=UUID(mid),
                field="chrono_age",
                delta=cfg.tick_duration,
                note=f"{mortal.name} chrono_age +{cfg.tick_duration}",
            ))

            # bio_age frozen for active Proxii/Heralds, slow for dormant Proxii
            if (mortal.status == MortalStatus.ACTIVE
                    and mortal.role in (MortalRole.PROXIUS, MortalRole.HERALD)):
                bio_delta = 0.0
            elif (mortal.status == MortalStatus.DORMANT
                    and mortal.role == MortalRole.PROXIUS):
                bio_delta = cfg.tick_duration / 5.0
            else:
                bio_delta = cfg.tick_duration

            if bio_delta > 0.0:
                new_bio_age = mortal.bio_age + bio_delta
                result.mortal_mutations.append(StateMutation(
                    mutation_type=MutationType.MORTAL_AGE,
                    target_id=UUID(mid),
                    field="bio_age",
                    delta=bio_delta,
                    note=f"{mortal.name} bio_age +{bio_delta}",
                ))

                # Death check fires once bio_age enters the species lifespan range
                sp = state.species.get(str(mortal.species_id)) if mortal.species_id else None
                if sp and new_bio_age >= sp.lifespan_min:
                    range_width = max(1.0, sp.lifespan_max - sp.lifespan_min)
                    progress = min(1.0, (new_bio_age - sp.lifespan_min) / range_width)
                    death_prob = progress * 0.3  # peaks at 30%/tick at lifespan_max
                    if rng.random() < death_prob:
                        result.mortal_mutations.append(StateMutation(
                            mutation_type=MutationType.MORTAL_STATUS,
                            target_id=UUID(mid),
                            field="status",
                            new_value=MortalStatus.DECEASED.value,
                            note=f"{mortal.name} died of natural causes (bio_age {new_bio_age:.0f})",
                        ))
                        result.narrative_events.append(
                            f"{mortal.name} has died of natural causes at age {new_bio_age:.0f}."
                        )

        # ── Mortal visibility decay ────────────────────
        for mid, mortal in state.mortals.items():
            if mortal.status == MortalStatus.DECEASED:
                continue
            if mortal.prominence >= ALWAYS_VISIBLE_THRESHOLD:
                continue
            if mortal.visibility <= 0.0:
                continue
            new_vis = max(0.0, mortal.visibility - cfg.mortal_visibility_decay_rate)
            result.mortal_mutations.append(StateMutation(
                mutation_type=MutationType.MORTAL_VISIBILITY,
                target_id=UUID(mid),
                field="visibility",
                delta=-(mortal.visibility - new_vis),
                note=f"{mortal.name} visibility decay",
            ))

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
        # Decay stalls when the Demiurge has gone quiet on Essence for several ticks.
        # 3+ quiet ticks → half rate; 6+ quiet ticks → full stall.
        if state.essence.concealment_integrity > 0.0:
            quiet = state.ticks_without_essence_gain
            if quiet >= 6:
                effective_decay = 0.0
            elif quiet >= 3:
                effective_decay = cfg.concealment_decay_rate * 0.5
            else:
                effective_decay = cfg.concealment_decay_rate

            if effective_decay > 0.0:
                new_integrity = max(
                    0.0,
                    state.essence.concealment_integrity - effective_decay
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

    def _validate_and_filter_queue(
        self,
        queue: list["ActionInstance"],
    ) -> tuple[list["ActionInstance"], list[str]]:
        """
        Enforce declarative action queue constraints. Returns (filtered_queue, rejection_messages).

        Rule: at most one action per ActionCategory per tick.
        """
        accepted: list[ActionInstance] = []
        rejected: list[str] = []
        seen_categories: dict[str, str] = {}  # category value -> name of action that claimed it

        for instance in queue:
            key = self._action_key_by_id.get(str(instance.action_definition_id))
            defn = self._action_library.get(key) if key else None
            if defn is None:
                continue

            cat = defn.category.value
            if cat in seen_categories:
                rejected.append(
                    f"{defn.name} blocked: a {cat.replace('_', ' ')} action "
                    f"({seen_categories[cat]}) is already queued this tick."
                )
                continue

            seen_categories[cat] = defn.name
            accepted.append(instance)

        return accepted, rejected

    def _process_action_queue(
        self,
        state: SimulationState,
        cfg: TickConfig,
        rng: random.Random,
    ) -> ActionProcessingResult:

        result = ActionProcessingResult()

        validated_queue, rejections = self._validate_and_filter_queue(state.action_queue)
        for msg in rejections:
            result.entries.append(ActionProcessingResult.ActionEntry(
                action_instance_id=uuid4(),
                outcome=ActionOutcome.FAILURE,
                mutations=[],
                narrative=msg,
            ))

        for instance in validated_queue:
            defn_id = str(instance.action_definition_id)
            defn = next(
                (v for v in self._action_library.values()
                 if str(v.id) == defn_id),
                None
            )
            if defn is None:
                continue

            outcome, mutations, narrative = self._execute_action(
                instance, defn, state, rng
            )

            if defn.name == "Move Against Luminary":
                self._overthrow_this_tick = outcome

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
        # Positive cost = spending; negative cost (harvests) are handled
        # entirely by the EssenceHarvestIntent handler to avoid double-counting.
        if defn.essence_cost > 0.0:
            effective_cost = defn.essence_cost * scale
            mutations.append(StateMutation(
                mutation_type=MutationType.ESSENCE_CHANGE,
                target_id=state.demiurge.id,
                field="actual",
                delta=-effective_cost,
                note=f"{defn.name}: essence spend",
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

        # ── Visibility refresh for mortal-targeted actions ─
        if instance.target_type == TargetType.MORTAL and instance.target_id:
            mortal = state.mortals.get(str(instance.target_id))
            if mortal and mortal.prominence < ALWAYS_VISIBLE_THRESHOLD:
                mutations.append(StateMutation(
                    mutation_type=MutationType.MORTAL_VISIBILITY,
                    target_id=instance.target_id,
                    field="visibility",
                    new_value=1.0,
                    note=f"Visibility refreshed by {defn.name}",
                ))

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

        # ── Intent-less actions with defined effects ───
        if intent is None:
            if defn.name == "Appoint Proxius":
                mortal = state.mortals.get(str(instance.target_id))
                if not mortal:
                    return mutations, "No mortal found to appoint."
                if mortal.role == MortalRole.PROXIUS:
                    return mutations, f"{mortal.name} is already a Proxius."
                if outcome != ActionOutcome.FAILURE:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.PROXIUS_APPOINTED,
                        target_id=mortal.id,
                        field="role",
                        new_value=MortalRole.PROXIUS.value,
                        note=f"{mortal.name} elevated to Proxius",
                    ))
                    narrative = f"{mortal.name} has been elevated to Proxius."
                else:
                    narrative = f"The elevation of {mortal.name} did not take hold."

            elif defn.name == "Dismiss Proxius":
                mortal = state.mortals.get(str(instance.target_id))
                if not mortal:
                    return mutations, "No mortal found to dismiss."
                if mortal.role != MortalRole.PROXIUS:
                    return mutations, f"{mortal.name} is not a Proxius."
                mutations.append(StateMutation(
                    mutation_type=MutationType.PROXIUS_DISMISSED,
                    target_id=mortal.id,
                    field="role",
                    new_value=MortalRole.OTHER.value,
                    note=f"{mortal.name} dismissed from Proxius role",
                ))
                narrative = f"{mortal.name} has been relieved of their Proxius appointment."

            elif defn.name == "Seed World with Life":
                return mutations, (
                    "Seed World requires a SeedWorldIntent specifying the species. "
                    "Use the action browser to provide species details."
                )

            elif defn.name == "Extinguish Civilization":
                civ = state.civilizations.get(str(instance.target_id))
                if not civ:
                    return mutations, "Target civilization not found."
                if outcome != ActionOutcome.FAILURE:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.ENTITY_DESTROYED,
                        target_id=civ.id,
                        field="",
                        note=f"{civ.name} extinguished by divine decree",
                    ))
                    narrative = (
                        f"{civ.name} has been extinguished. "
                        f"The world falls silent where they once stood."
                    )
                else:
                    narrative = f"The attempt to extinguish {civ.name} failed. They endure."

            elif defn.name == "Exile to Underreal":
                tid_str = str(instance.target_id) if instance.target_id else None
                target_name = "the target"
                for collection in (state.civilizations, state.mortals, state.worlds):
                    if tid_str and tid_str in collection:
                        target_name = getattr(collection[tid_str], "name", target_name)
                        break
                if outcome != ActionOutcome.FAILURE:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.EXILED_TO_UNDERREAL,
                        target_id=instance.target_id,
                        field="",
                        note=f"{target_name} cast into the Underreal",
                    ))
                    narrative = (
                        f"{target_name} has been cast into the Underreal. "
                        f"A distinctive trace lingers where they were."
                    )
                else:
                    narrative = (
                        f"The exile of {target_name} failed — "
                        f"the target resisted the conceptual unraveling."
                    )

            elif defn.name == "Perform Direct Miracle":
                mortal = state.mortals.get(str(instance.target_id)) if instance.target_id else None
                if not mortal:
                    return mutations, "Target mortal not found."
                if outcome != ActionOutcome.FAILURE:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.MORTAL_ALIGNMENT,
                        target_id=mortal.id,
                        field="alignment",
                        delta=0.3 if outcome == ActionOutcome.SUCCESS else 0.1,
                        note=f"Direct miracle witnessed by {mortal.name}",
                    ))
                    if mortal.civilization_id:
                        mutations.append(StateMutation(
                            mutation_type=MutationType.CIVILIZATION_STAT,
                            target_id=mortal.civilization_id,
                            field="divine_awareness",
                            delta=0.15 if outcome == ActionOutcome.SUCCESS else 0.05,
                            note=f"Divine awareness spike from miracle on {mortal.name}",
                        ))
                    narrative = (
                        f"A direct miracle was performed for {mortal.name}. "
                        f"Their faith is confirmed; word will spread."
                    )
                else:
                    narrative = (
                        f"The miracle for {mortal.name} failed to manifest. "
                        f"They were left waiting."
                    )

            elif defn.name == "Empower Proxius":
                proxius = state.mortals.get(str(instance.target_id)) if instance.target_id else None
                if not proxius or proxius.role != MortalRole.PROXIUS:
                    return mutations, "No active Proxius found to empower."
                if outcome != ActionOutcome.FAILURE:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.MORTAL_ALIGNMENT,
                        target_id=proxius.id,
                        field="alignment",
                        delta=0.2 if outcome == ActionOutcome.SUCCESS else 0.08,
                        note=f"{proxius.name} granted temporary divine capability",
                    ))
                    narrative = (
                        f"{proxius.name} has been granted a surge of divine capability. "
                        f"Their alignment to your will is reinforced."
                    )
                else:
                    narrative = f"The empowerment of {proxius.name} failed to take hold."

            elif defn.name == "Reshape World Geography":
                world_obj = state.worlds.get(str(instance.target_id)) if instance.target_id else None
                if not world_obj:
                    return mutations, "Target world not found."
                if outcome == ActionOutcome.SUCCESS:
                    condition_ladder = [
                        WorldCondition.DYING, WorldCondition.BARREN,
                        WorldCondition.STRESSED, WorldCondition.STABLE,
                        WorldCondition.THRIVING,
                    ]
                    try:
                        idx = condition_ladder.index(world_obj.condition)
                        new_condition = condition_ladder[min(idx + 1, len(condition_ladder) - 1)]
                    except ValueError:
                        new_condition = WorldCondition.STABLE
                    mutations.append(StateMutation(
                        mutation_type=MutationType.WORLD_CONDITION,
                        target_id=world_obj.id,
                        field="condition",
                        new_value=new_condition.value,
                        note=f"Geography reshaped on {world_obj.name}",
                    ))
                    narrative = (
                        f"The geography of {world_obj.name} has been reshaped. "
                        f"Continents shifted; the world's condition improved."
                    )
                elif outcome == ActionOutcome.PARTIAL:
                    narrative = (
                        f"The reshaping of {world_obj.name} is complete, "
                        f"though the results are imperfect."
                    )
                else:
                    narrative = (
                        f"The attempt to reshape {world_obj.name} failed. "
                        f"The world resists divine remolding."
                    )

            elif defn.name == "Move Against Luminary":
                luminary = state.luminaries.get(str(instance.target_id)) if instance.target_id else None
                lum_name = luminary.name if luminary else "the Luminary"
                if outcome == ActionOutcome.SUCCESS:
                    narrative = (
                        f"The accumulated Essence unleashed against {lum_name} found its mark. "
                        f"Their hold on your universe shatters."
                    )
                elif outcome == ActionOutcome.PARTIAL:
                    narrative = (
                        f"The challenge to {lum_name} landed but did not sever. "
                        f"They will retaliate."
                    )
                else:
                    narrative = (
                        f"The move against {lum_name} was deflected. "
                        f"They are now aware of your intent."
                    )

            elif defn.name == "Scry":
                world_obj = state.worlds.get(str(instance.target_id)) if instance.target_id else None
                if not world_obj:
                    return mutations, "Target world not found."

                effectiveness = 1.0 if outcome == ActionOutcome.SUCCESS else 0.5
                discovery_bonus = 0.3 if outcome == ActionOutcome.SUCCESS else 0.0

                discovered: list[str] = []
                refreshed: list[str] = []

                world_mortals = [
                    (mid, m) for mid, m in state.mortals.items()
                    if str(m.world_id) == str(world_obj.id)
                    and m.status != MortalStatus.DECEASED
                    and m.prominence < ALWAYS_VISIBLE_THRESHOLD
                ]
                for mid, mortal in world_mortals:
                    if rng.random() < mortal.prominence + discovery_bonus:
                        new_vis = min(1.0, 0.5 + mortal.prominence * 0.4 * effectiveness)
                        was_visible = mortal.visibility > VISIBILITY_FLOOR
                        mutations.append(StateMutation(
                            mutation_type=MutationType.MORTAL_VISIBILITY,
                            target_id=UUID(mid),
                            field="visibility",
                            new_value=new_vis,
                            note=f"Scry on {world_obj.name}: {mortal.name} sighted",
                        ))
                        if was_visible:
                            refreshed.append(mortal.name)
                        else:
                            discovered.append(mortal.name)

                parts = [f"You scried {world_obj.name}."]
                if discovered:
                    parts.append(f"Newly sighted: {', '.join(discovered)}.")
                if refreshed:
                    parts.append(f"Sight maintained on: {', '.join(refreshed)}.")
                if not discovered and not refreshed:
                    parts.append("No low-prominence mortals came to your attention.")
                narrative = " ".join(parts)

            elif defn.name == "Maintain Concealment":
                if outcome == ActionOutcome.FAILURE:
                    return mutations, "The concealment maintenance failed to take hold."

                effectiveness = 1.0 if outcome == ActionOutcome.SUCCESS else 0.4
                current_integrity = state.essence.concealment_integrity
                # Diminishing returns: less useful when integrity is already high
                restore = 0.30 * effectiveness * (1.0 - current_integrity * 0.5)
                restore = max(0.0, restore)
                if restore > 0.0:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.CONCEALMENT_CHANGE,
                        target_id=state.demiurge.id,
                        field="concealment_integrity",
                        delta=restore,
                        note="Concealment integrity maintained",
                    ))
                narrative = (
                    f"Concealment reinforced. "
                    f"Integrity restored by {restore:.2f} "
                    f"(was {current_integrity:.2f}, "
                    f"now {min(1.0, current_integrity + restore):.2f})."
                )

            elif defn.name == "Go Quiet":
                mortal = state.mortals.get(str(instance.target_id)) if instance.target_id else None
                if not mortal or mortal.role != MortalRole.PROXIUS:
                    return mutations, "No Proxius found to go quiet."
                if mortal.status == MortalStatus.DORMANT:
                    return mutations, f"{mortal.name} is already dormant."
                mutations.append(StateMutation(
                    mutation_type=MutationType.MORTAL_STATUS,
                    target_id=mortal.id,
                    field="status",
                    new_value=MortalStatus.DORMANT.value,
                    note=f"{mortal.name} goes quiet — proxius_activity suspended",
                ))
                narrative = (
                    f"{mortal.name} has gone quiet. "
                    f"Their activity is suspended; bio-age resumes at reduced rate. "
                    f"Issue a directive to reactivate them."
                )

            elif defn.name == "Audit Proxius":
                mortal = state.mortals.get(str(instance.target_id)) if instance.target_id else None
                if not mortal or mortal.role != MortalRole.PROXIUS:
                    return mutations, "No Proxius found to audit."
                alignment_desc = (
                    "faithfully aligned"    if mortal.alignment > 0.7 else
                    "drifting"              if mortal.alignment > 0.4 else
                    "significantly divergent"
                )
                tags = ", ".join(mortal.personal_tags) if mortal.personal_tags else "none"
                narrative = (
                    f"Silent audit of {mortal.name} complete. "
                    f"Alignment: {mortal.alignment:.2f} ({alignment_desc}). "
                    f"Status: {mortal.status.value}. "
                    f"Personal convictions: {tags}."
                )
                # No mutations — purely observational; they do not know you checked.

            return mutations, narrative

        # ── Explore Beliefs ───────────────────────────
        if isinstance(intent, ExploreBeliefIntent):
            tag = intent.domain_tag
            if tag in state.demiurge.unlocked_domain_tags:
                return mutations, f"{tag} is already part of your explored beliefs."
            mutations.append(StateMutation(
                mutation_type=MutationType.DEMIURGE_UNLOCK,
                target_id=state.demiurge.id,
                field="unlocked_domain_tags",
                new_value=tag,
                note=f"Demiurge explored: {tag}",
            ))
            short = tag.split(":", 1)[1] if ":" in tag else tag
            return mutations, (
                f"You turn your awareness inward and contemplate {short}. "
                f"The domain takes shape in your understanding — "
                f"a new frontier, not yet manifested in the world."
            )

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

            # Reactivate a dormant Proxius when a directive is issued
            if proxius.status == MortalStatus.DORMANT:
                mutations.append(StateMutation(
                    mutation_type=MutationType.MORTAL_STATUS,
                    target_id=proxius.id,
                    field="status",
                    new_value=MortalStatus.ACTIVE.value,
                    note=f"{proxius.name} reactivated by directive",
                ))

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

            # Domain belief shift into the target civilization
            if intent.domain_vectors and intent.target_civilization_id:
                civ_obj = state.civilizations.get(str(intent.target_civilization_id))
                if civ_obj:
                    for dv in intent.domain_vectors:
                        mutations.append(StateMutation(
                            mutation_type=MutationType.BELIEF_SHIFT,
                            target_id=civ_obj.id,
                            field="dominant_beliefs",
                            delta=dv.direction * interpretation_fidelity * 0.08,
                            new_value=dv.domain_tag,
                            note=f"Proxius {proxius.name} promoting {dv.domain_tag} {fidelity_note}",
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

        # ── Omen / Manifestation ──────────────────────
        elif isinstance(intent, OmenIntent):
            if outcome == ActionOutcome.FAILURE:
                return mutations, "The omen dissipated — mortals found no meaning in it."

            effectiveness = 1.0 if outcome == ActionOutcome.SUCCESS else 0.5

            target_civs: list = []
            if intent.civilization_scope:
                civ_obj = state.civilizations.get(str(intent.civilization_scope))
                if civ_obj:
                    target_civs.append((str(intent.civilization_scope), civ_obj))
            else:
                target_civs = list(state.civilizations.items())

            for cid, civ_obj in target_civs:
                for dv in intent.domain_vectors:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.BELIEF_SHIFT,
                        target_id=civ_obj.id,
                        field="dominant_beliefs",
                        delta=dv.direction * effectiveness * 0.15,
                        new_value=dv.domain_tag,
                        note=f"Omen: '{intent.sign_description[:40]}'",
                    ))
                mutations.append(StateMutation(
                    mutation_type=MutationType.CIVILIZATION_STAT,
                    target_id=civ_obj.id,
                    field="divine_awareness",
                    delta=0.1 * effectiveness,
                    note=f"Omen raises divine awareness in {civ_obj.name}",
                ))

            scope_desc = (
                state.civilizations[str(intent.civilization_scope)].name
                if intent.civilization_scope
                and str(intent.civilization_scope) in state.civilizations
                else "all civilizations"
            )
            narrative = (
                f"The omen '{intent.sign_description}' manifested for {scope_desc}. "
                f"Intended: '{intent.intended_interpretation}'. "
                f"Effectiveness: {effectiveness:.0%}."
            )

        # ── Civilizational Development ────────────────
        elif isinstance(intent, DevelopmentIntent):
            if outcome == ActionOutcome.FAILURE:
                return mutations, "The developmental nudge failed to take root."

            effectiveness = 1.0 if outcome == ActionOutcome.SUCCESS else 0.4
            civ_obj = state.civilizations.get(str(instance.target_id)) if instance.target_id else None
            if not civ_obj:
                return mutations, "Target civilization not found."

            for dv in intent.domain_vectors:
                mutations.append(StateMutation(
                    mutation_type=MutationType.BELIEF_SHIFT,
                    target_id=civ_obj.id,
                    field="dominant_beliefs",
                    delta=dv.direction * effectiveness * 0.1,
                    new_value=dv.domain_tag,
                    note=f"Development nudge: '{intent.target_aspect[:40]}'",
                ))

            narrative = (
                f"Civilizational development nudge toward '{intent.target_aspect}' "
                f"applied to {civ_obj.name}. "
                f"Effectiveness: {effectiveness:.0%}."
            )

        # ── Luminary Petition ─────────────────────────
        elif isinstance(intent, LuminaryPetitionIntent):
            luminary = state.luminaries.get(str(instance.target_id)) if instance.target_id else None
            if not luminary:
                return mutations, "Target Luminary not found."

            if outcome == ActionOutcome.SUCCESS:
                mutations.append(StateMutation(
                    mutation_type=MutationType.DISPOSITION_CHANGE,
                    target_id=luminary.id,
                    field="results",
                    delta=0.05,
                    note=f"Petition '{intent.subject[:40]}' received favorably",
                ))
                narrative = (
                    f"Your petition regarding '{intent.subject}' was received. "
                    f"{luminary.name} acknowledged your position ({intent.tone})."
                )
            elif outcome == ActionOutcome.PARTIAL:
                narrative = (
                    f"Your petition regarding '{intent.subject}' was heard but not acted upon. "
                    f"{luminary.name} remains noncommittal."
                )
            else:
                mutations.append(StateMutation(
                    mutation_type=MutationType.DISPOSITION_CHANGE,
                    target_id=luminary.id,
                    field="methods",
                    delta=-0.03,
                    note=f"Petition '{intent.subject[:40]}' dismissed",
                ))
                narrative = (
                    f"Your petition regarding '{intent.subject}' was dismissed. "
                    f"{luminary.name} appeared displeased by the request."
                )

        # ── Salvage from Underreal ────────────────────
        elif isinstance(intent, SalvageIntent):
            if outcome == ActionOutcome.FAILURE:
                return mutations, (
                    "The Underreal yielded nothing coherent. "
                    "The concept dissolved on contact."
                )

            target_world = state.worlds.get(str(intent.target_world_id))
            if not target_world:
                return mutations, "Target world for salvage not found."

            if outcome == ActionOutcome.CHAOTIC_RESULT:
                for dv in intent.domain_vectors:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.DOMAIN_EXPRESSION,
                        target_id=target_world.id,
                        field="domain_expression",
                        delta=-dv.direction * 0.2,
                        new_value=dv.domain_tag,
                        note=f"Chaotic salvage on {target_world.name}: concept inverted",
                    ))
                narrative = (
                    f"Something emerged from the Underreal, but not '{intent.desired_concept}'. "
                    f"The concept manifested on {target_world.name} in an unexpected form."
                )
            else:
                effectiveness = 1.0 if outcome == ActionOutcome.SUCCESS else 0.5
                for dv in intent.domain_vectors:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.DOMAIN_EXPRESSION,
                        target_id=target_world.id,
                        field="domain_expression",
                        delta=dv.direction * effectiveness * 0.2,
                        new_value=dv.domain_tag,
                        note=f"Salvaged '{intent.desired_concept[:40]}' on {target_world.name}",
                    ))
                narrative = (
                    f"Salvaged '{intent.desired_concept}' from the Underreal. "
                    f"The concept has taken root on {target_world.name}. "
                    f"Effectiveness: {effectiveness:.0%}."
                )

        # ── Seed World ────────────────────────────────
        elif isinstance(intent, SeedWorldIntent):
            world_obj = state.worlds.get(str(instance.target_id)) if instance.target_id else None
            if not world_obj:
                return mutations, "Target world not found."
            if world_obj.condition != WorldCondition.BARREN:
                return mutations, (
                    f"{world_obj.name} already sustains life — seeding had no effect."
                )
            if outcome == ActionOutcome.FAILURE:
                return mutations, (
                    f"The seeding of {world_obj.name} failed to take hold. "
                    f"The world remains barren."
                )

            new_condition = (
                WorldCondition.STABLE if outcome == ActionOutcome.SUCCESS
                else WorldCondition.STRESSED
            )
            new_species = Species(
                name=intent.species_name,
                origin_world_id=world_obj.id,
                sapient=intent.sapient,
                transplanted=False,
                lifespan_min=intent.lifespan_min,
                lifespan_max=intent.lifespan_max,
                trait_tags=intent.trait_tags,
            )
            mutations.append(StateMutation(
                mutation_type=MutationType.WORLD_CONDITION,
                target_id=world_obj.id,
                field="condition",
                new_value=new_condition.value,
                note=f"Life seeded on {world_obj.name}",
            ))
            mutations.append(StateMutation(
                mutation_type=MutationType.SPECIES_CREATED,
                target_id=world_obj.id,
                field="",
                new_value=new_species,
                note=f"Species '{intent.species_name}' introduced to {world_obj.name}",
            ))
            sapient_note = " They are already sapient." if intent.sapient else ""
            if outcome == ActionOutcome.SUCCESS:
                narrative = (
                    f"Life has taken root on {world_obj.name}: the {intent.species_name}."
                    f"{sapient_note}"
                )
            else:
                narrative = (
                    f"Life clings to {world_obj.name} — the {intent.species_name} survive, "
                    f"but the world is stressed. They will need tending."
                )

        # ── Uplift Species ────────────────────────────
        elif isinstance(intent, UpliftSpeciesIntent):
            sp = state.species.get(str(intent.species_id))
            if not sp:
                return mutations, "Target species not found."
            if sp.sapient:
                return mutations, f"The {sp.name} are already sapient."
            if outcome == ActionOutcome.FAILURE:
                return mutations, (
                    f"The uplift of the {sp.name} failed to catalyze. "
                    f"They remain pre-sapient."
                )

            effectiveness = 1.0 if outcome == ActionOutcome.SUCCESS else 0.5
            mutations.append(StateMutation(
                mutation_type=MutationType.SPECIES_UPLIFTED,
                target_id=sp.id,
                field="sapient",
                new_value=True,
                note=f"{sp.name} uplifted to sapience",
            ))
            for dv in intent.domain_vectors:
                # Sapience flavor pushes domain expression on origin world
                if sp.origin_world_id:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.DOMAIN_EXPRESSION,
                        target_id=sp.origin_world_id,
                        field="domain_expression",
                        delta=dv.direction * effectiveness * 0.15,
                        new_value=dv.domain_tag,
                        note=f"Uplift of {sp.name}: emergent domain flavor",
                    ))
            narrative = (
                f"The {sp.name} have crossed the threshold into sapience. "
                f"A civilization will emerge from them in time."
            )
            if outcome == ActionOutcome.PARTIAL:
                narrative += " The transition is incomplete — they are fragile."

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
            for belief_tag, strength in civ.dominant_beliefs.items():
                raw_scores[belief_tag] += w * strength

        # Also factor in world-level domain_expression
        for world in state.worlds.values():
            world_weight = 0.3  # Worlds contribute less than civilizations
            for tag, strength in world.domain_expression.items():
                raw_scores[tag] += world_weight * strength
                total_weight += world_weight * strength

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

        # Pre-collect domain tags for every Luminary for Realpolitik lookups.
        # Map: luminary_id_str -> list[str] of domain tags
        all_lum_domain_tags: dict[str, list[str]] = {}
        for lid_inner, lum_inner in state.luminaries.items():
            tags_inner: list[str] = []
            for did in lum_inner.domains:
                domain = state.domains.get(str(did))
                if domain:
                    tags_inner.extend(domain.tags)
            all_lum_domain_tags[lid_inner] = tags_inner

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

            luminary_domain_tags = all_lum_domain_tags[lid]

            # Combined domain tags of all fellow Luminaries (for Realpolitik)
            fellow_lum_tags: set[str] = set()
            for other_lid, other_tags in all_lum_domain_tags.items():
                if other_lid != lid:
                    fellow_lum_tags.update(other_tags)

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

            # Similarity-weighted influence from related/opposing expressed domains
            sim_modifier = engine.similarity_results_modifier(
                luminary_domain_tags=luminary_domain_tags,
                fellow_luminary_tags=fellow_lum_tags,
                current_profile=profile,
                temperament=luminary.temperament.value,
                registry=self._domain_registry,
            )
            if abs(sim_modifier) > 0.001:
                delta.results += sim_modifier
                delta.reasons.append(DispositionDeltaReason(
                    axis="results",
                    delta=sim_modifier,
                    source="domain_similarity_influence",
                    note="Expressed domains adjacent or opposing to Luminary domains",
                ))

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

        # Victory: overthrow
        if self._overthrow_this_tick == ActionOutcome.SUCCESS:
            return TerminalCheck(
                condition=TerminalConditionType.VICTORY_OVERTHROW,
                triggered=True,
                note=(
                    "You have severed the Luminary's hold on your universe. "
                    "The throne is yours — for now."
                ),
            )
        if self._overthrow_this_tick == ActionOutcome.CHAOTIC_RESULT:
            return TerminalCheck(
                condition=TerminalConditionType.DEFEAT_CAST_DOWN,
                triggered=True,
                note=(
                    "The overthrow attempt unraveled catastrophically. "
                    "The Luminaries cast you into the Underreal."
                ),
            )

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

        return TerminalCheck(condition=TerminalConditionType.NONE)

    # ─────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────

    def _prune_weak_beliefs(self, state: SimulationState) -> SimulationState:
        """
        Remove belief and domain-expression entries whose strength has fallen
        below BELIEF_FLOOR. Runs every passive phase to prevent ghost residue
        from accumulating via many small-delta mutations.
        """
        for civ in state.civilizations.values():
            civ.dominant_beliefs = {
                tag: s for tag, s in civ.dominant_beliefs.items() if s > BELIEF_FLOOR
            }
        for world in state.worlds.values():
            world.domain_expression = {
                tag: s for tag, s in world.domain_expression.items() if s > BELIEF_FLOOR
            }
        return state

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
                    elif len(parts) == 1:
                        current = getattr(state.civilizations[tid], parts[0], 0.0)
                        setattr(
                            state.civilizations[tid], parts[0],
                            max(0.0, min(1.0, current + (m.delta or 0)))
                        )

            elif m.mutation_type in (
                MutationType.BELIEF_SHIFT,
                MutationType.DOMAIN_EXPRESSION,
            ):
                tag = str(m.new_value) if m.new_value else None
                if not tag:
                    pass
                elif tid in state.civilizations:
                    beliefs = state.civilizations[tid].dominant_beliefs
                    current = beliefs.get(tag, 0.0)
                    new_strength = max(0.0, min(1.0, current + (m.delta or 0.0)))
                    if new_strength > 0.0:
                        beliefs[tag] = new_strength
                    elif tag in beliefs:
                        del beliefs[tag]
                elif tid in state.worlds:
                    domain = state.worlds[tid].domain_expression
                    current = domain.get(tag, 0.0)
                    new_strength = max(0.0, min(1.0, current + (m.delta or 0.0)))
                    if new_strength > 0.0:
                        domain[tag] = new_strength
                    elif tag in domain:
                        del domain[tag]

            elif m.mutation_type == MutationType.PROXIUS_APPOINTED:
                if tid in state.mortals:
                    mortal = state.mortals[tid]
                    mortal.role = MortalRole.PROXIUS
                    mortal.visibility = 1.0  # Appointing means you now fully see them
                    if mortal.id not in state.demiurge.proxius_ids:
                        state.demiurge.proxius_ids.append(mortal.id)
                    world_id_str = str(mortal.world_id)
                    if world_id_str in state.worlds:
                        world = state.worlds[world_id_str]
                        if mortal.id not in world.proxius_ids:
                            world.proxius_ids.append(mortal.id)

            elif m.mutation_type == MutationType.PROXIUS_DISMISSED:
                if tid in state.mortals:
                    mortal = state.mortals[tid]
                    mortal.role = MortalRole.OTHER
                    if mortal.id in state.demiurge.proxius_ids:
                        state.demiurge.proxius_ids.remove(mortal.id)
                    world_id_str = str(mortal.world_id)
                    if world_id_str in state.worlds:
                        world = state.worlds[world_id_str]
                        if mortal.id in world.proxius_ids:
                            world.proxius_ids.remove(mortal.id)

            elif m.mutation_type == MutationType.MORTAL_STATUS:
                if tid in state.mortals and m.new_value:
                    state.mortals[tid].status = MortalStatus(m.new_value)

            elif m.mutation_type == MutationType.MORTAL_AGE:
                if tid in state.mortals and m.field in ("chrono_age", "bio_age"):
                    current = getattr(state.mortals[tid], m.field, 0.0)
                    setattr(state.mortals[tid], m.field, current + (m.delta or 0))

            elif m.mutation_type == MutationType.MORTAL_VISIBILITY:
                if tid in state.mortals:
                    if m.new_value is not None:
                        state.mortals[tid].visibility = max(0.0, min(1.0, float(m.new_value)))
                    elif m.delta is not None:
                        current = state.mortals[tid].visibility
                        state.mortals[tid].visibility = max(0.0, min(1.0, current + m.delta))

            elif m.mutation_type == MutationType.WORLD_CONDITION:
                if tid in state.worlds and m.new_value:
                    state.worlds[tid].condition = WorldCondition(m.new_value)

            elif m.mutation_type == MutationType.ENTITY_DESTROYED:
                if tid in state.civilizations:
                    civ = state.civilizations.pop(tid)
                    world = state.worlds.get(str(civ.world_id))
                    if world and civ.id in world.civilization_ids:
                        world.civilization_ids.remove(civ.id)
                elif tid in state.mortals:
                    state.mortals[tid].status = MortalStatus.DECEASED

            elif m.mutation_type == MutationType.EXILED_TO_UNDERREAL:
                if tid in state.civilizations:
                    civ = state.civilizations.pop(tid)
                    world = state.worlds.get(str(civ.world_id))
                    if world:
                        if civ.id in world.civilization_ids:
                            world.civilization_ids.remove(civ.id)
                        world.domain_expression["domain:underreal_trace"] = min(
                            1.0,
                            world.domain_expression.get("domain:underreal_trace", 0.0) + 0.4,
                        )
                elif tid in state.mortals:
                    mortal = state.mortals[tid]
                    mortal.status = MortalStatus.DECEASED
                    world = state.worlds.get(str(mortal.world_id))
                    if world:
                        world.domain_expression["domain:underreal_trace"] = min(
                            1.0,
                            world.domain_expression.get("domain:underreal_trace", 0.0) + 0.2,
                        )
                elif tid in state.worlds:
                    state.worlds[tid].condition = WorldCondition.BARREN
                    state.worlds[tid].domain_expression = {"domain:underreal_trace": 1.0}

            elif m.mutation_type == MutationType.DISPOSITION_CHANGE:
                if tid in state.luminaries:
                    lum = state.luminaries[tid]
                    if m.field == "results":
                        lum.disposition.results = max(
                            -1.0, min(1.0, lum.disposition.results + (m.delta or 0))
                        )
                    elif m.field == "methods":
                        lum.disposition.methods = max(
                            -1.0, min(1.0, lum.disposition.methods + (m.delta or 0))
                        )

            elif m.mutation_type == MutationType.SPECIES_CREATED:
                if isinstance(m.new_value, Species):
                    sp = m.new_value
                    state.species[str(sp.id)] = sp
                    if tid and tid in state.worlds:
                        if sp.id not in state.worlds[tid].species_ids:
                            state.worlds[tid].species_ids.append(sp.id)

            elif m.mutation_type == MutationType.SPECIES_UPLIFTED:
                if tid in state.species:
                    state.species[tid].sapient = True
                    state.species[tid].condition = SpeciesCondition.THRIVING

            elif m.mutation_type == MutationType.SPECIES_CONDITION:
                if tid in state.species and m.new_value:
                    state.species[tid].condition = SpeciesCondition(m.new_value)

            elif m.mutation_type == MutationType.DEMIURGE_UNLOCK:
                tag = str(m.new_value) if m.new_value else None
                if tag and tag not in state.demiurge.unlocked_domain_tags:
                    state.demiurge.unlocked_domain_tags.append(tag)

        return state
