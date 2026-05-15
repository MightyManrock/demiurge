from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from uuid import UUID, uuid4
import random
import math

from core.action_core import (
    DomainVector,
    StateMutation, MutationType,
    ActionOutcome,
    ActionInstance,
    OngoingAction,
    EssenceStockpile,
    build_action_library,
    ActionDefinition,
    ActionReliability,
    WhisperIntent, OmenIntent, ProbabilityNudgeIntent,
    DevelopmentIntent, ProxiusDirectiveIntent,
    LuminaryPetitionIntent, EssenceHarvestIntent, SalvageIntent,
    SeedWorldIntent, UpliftSpeciesIntent, ExploreBeliefIntent,
    ChangeAffiliatedDomainsIntent, ScryIntent, ScryScope, WeighCivilizationIntent,
    TargetType,
)
from core.eval_core import (
    UniverseDomainProfile,
    LuminaryEvaluation,
    DialogueTrigger,
    EvaluationEngine,
    AttentionTrigger,
    FootprintAssessment,
    EssenceSuspicion,
    EssenceSatisfaction,
    evaluate_essence_satisfaction,
    DispositionDelta,
    DispositionDeltaReason,
)
from core.onto_core import (
    Demiurge, Pantheon, Luminary,
)
from core.universe_core import (
    Universe, Location, System, SignificantLocation, PopLocation,
    Civilization, NotableMortal,
    MortalRole, MortalStatus, MortalProminence, LocCondition,
    Species, SpeciesCondition,
)
from utilities.domain_registry import DomainRegistry, LuminaryPersonality, get_registry as get_domain_registry
from utilities.culture_registry import CultureRegistry, get_registry as get_culture_registry
from core.event_core import Event, EventType, StrengthCurve
from core.agent_core import ProxiusGoal, AgentActionChoice


# ─────────────────────────────────────────
# MORTAL VISIBILITY CONSTANTS
# ─────────────────────────────────────────

ALWAYS_VISIBLE_THRESHOLD = 0.65

ENTITY_VISIBILITY_FLOOR = 0.05
# Below this, non-mortal entities (locations, civilizations, species) are out of the Window.

# ─────────────────────────────────────────
# PROXIUS POLICY CONSTANTS
# ─────────────────────────────────────────

# Fraction of the passive rate applied to each Proxius on a policy-compliant world.
# Compliant worlds have ≤ proxii_policy.max_per_world active Proxii.
PROXIUS_COMPLIANCE_FACTOR = 0.3

# ─────────────────────────────────────────
# BELIEF SYSTEM CONSTANTS
# ─────────────────────────────────────────

BELIEF_FLOOR = 0.02
# Belief/domain-expression entries below this strength are
# silently pruned each passive phase. Keeps dicts clean of
# ghost residue from many tiny-delta actions.
# Mortals at or above this prominence are always perceived —
# no visibility tracking needed.

# Essence generation: per-CivilizationScale multipliers applied to dominant_beliefs.
# Ordered so that inherent location weight (3.0) always exceeds even max-scale civ (1.60).
_CIV_SCALE_ESSENCE_MULT: dict[str, float] = {
    "nascent":        0.05,
    "tribal":         0.10,
    "city_state":     0.20,
    "regional":       0.35,
    "continental":    0.50,
    "planetary":      0.70,
    "interplanetary": 0.90,
    "interstellar":   1.20,
    "intergalactic":  1.60,
}

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


def is_in_window(entity: object) -> bool:
    """True if the Demiurge has this entity (location, civilization, or species) in the Window."""
    vis = getattr(entity, "visibility", 0.0)
    pinned = getattr(entity, "pinned", False)
    return pinned or vis > ENTITY_VISIBILITY_FLOOR


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
    # Mortals visible at scenario start use this slower rate instead.
    starting_visible_decay_rate: float = 0.005

    # Window visibility decay for non-mortal entities
    location_visibility_decay_rate: float = 0.01
    civ_visibility_decay_rate: float = 0.01
    species_visibility_decay_rate: float = 0.01

    # Luminary attention decay
    # Attention naturally falls when nothing interesting happens.
    attention_decay_rate: float = 0.03

    # Passive Proxius footprint
    # Each active Proxius generates this much proxius_activity per tick.
    # Policy-compliant worlds (≤ max_per_world Proxii) contribute at
    # PROXIUS_COMPLIANCE_FACTOR of this rate; excess Proxii contribute at full rate.
    proxius_passive_footprint_rate: float = 0.03

    # Evaluation frequency
    # Not every tick triggers a full Luminary evaluation.
    # Evaluation happens when: attention crosses a threshold,
    # a constraint is breached, or this many ticks have elapsed.
    evaluation_interval: float = 10.0

    # Essence generation weights (tuning targets; adjust after playtesting)
    essence_location_weight: float = 3.0
    # Multiplier for SignificantLocation.domain_expression contributions.
    # Intentionally higher than the max civ scale multiplier so a world's
    # inherent character outweighs any single civilization.

    essence_mortal_weight: float = 0.05
    # Multiplier for NotableMortal.belief_tags contributions.

    essence_claiming_exponent: float = 0.40
    # Exponent applied to total pantheon affinity to derive the Luminary group's
    # claim fraction: lum_fraction = lum_total_aff ** essence_claiming_exponent.
    # At 0.40: aff=0.2→52.5%, aff=0.5→75.8%, aff=0.8→91.5%, aff=0.9→95.9%.
    # Demiurge gets 1 − lum_fraction of any affiliated domain pool.

    luminary_essence_baseline_rate: float = 1.0
    # Expected weighted domain production per effective-affinity-point per tick.
    # Threshold = effective_affinity × baseline_rate × ticks_since_last_eval,
    # where effective_affinity uses diminishing returns (see luminary_essence_decay).

    luminary_essence_decay: float = 0.65
    # Geometric decay applied to each successive domain affinity when computing
    # a Luminary's effective affinity for the satisfaction threshold.
    # Affinities are sorted descending (ties broken alphabetically); each rank i
    # is multiplied by decay**i.  At 0.65: a 3-domain Luminary at [0.7,0.7,0.5]
    # scores 0.700 + 0.455 + 0.211 = 1.366 instead of the raw sum 1.90.

    luminary_essence_recall: float = 0.20
    # Fraction of last-period excess above base threshold that persists as a raised
    # expectation this period.  At 0.20: giving a Luminary 14 units above their base
    # of 6 (excess=8) adds 8×0.20=1.6 to their expectation floor next period.
    # Raised expectations decay by 0.10 per two consecutive shortfall periods.


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
    entity_mutations:       list["StateMutation"] = Field(default_factory=list)
    footprint_mutations:    list["StateMutation"] = Field(default_factory=list)
    concealment_mutations:  list["StateMutation"] = Field(default_factory=list)
    attention_mutations:    list["StateMutation"] = Field(default_factory=list)
    narrative_events:       list[str] = Field(default_factory=list)
    # Brief descriptions of notable passive developments
    # e.g. "The Verath Confederation collapsed into civil war"
    #      "Proxius Aldren has begun acting outside their directive"

    # Death mutations held back until after Phase 2 so that a same-tick
    # appoint_proxius action can save a mortal before the death is committed.
    pending_death_mutations:  list["StateMutation"] = Field(default_factory=list)
    pending_death_narratives: list[str]             = Field(default_factory=list)


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

    essence_claimed_by_domain: dict[str, float] = Field(default_factory=dict)
    # domain tag -> Demiurge's claim this tick

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
    locations:     dict[str, "Location"]    # str(UUID) -> Location (all spatial entities)
    civilizations: dict[str, "Civilization"]
    mortals:       dict[str, "NotableMortal"]
    species:       dict[str, "Species"] = Field(default_factory=dict)

    @property
    def worlds(self) -> "dict[str, SignificantLocation]":
        return {k: v for k, v in self.locations.items() if isinstance(v, SignificantLocation)}

    @property
    def galaxies(self) -> "dict[str, Location]":
        return {k: v for k, v in self.locations.items() if v.location_type == "galaxy"}

    @property
    def systems(self) -> "dict[str, System]":
        return {k: v for k, v in self.locations.items() if isinstance(v, System)}

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

    # Persistent actions that auto-execute each tick.
    # Keyed by ActionCategory.value; appended to action_queue before Phase 2.
    # Manually queued actions in the same category take priority and block the ongoing one.
    ongoing_actions: dict[str, OngoingAction] = Field(default_factory=dict)

    # Active events: divine acts that continue to affect the world across multiple ticks.
    # Keyed by str(Event.id). Populated by EVENT_EMITTED mutations; pruned when expired.
    active_events: dict[str, Event] = Field(default_factory=dict)

    # Transient per-tick attention triggers accumulated during Phase 1 event processing.
    # Keyed by str(luminary UUID). Cleared after Phase 4 evaluations. Never persisted.
    pending_attention_triggers: dict[str, list[AttentionTrigger]] = Field(
        default_factory=dict
    )

    # Weighted domain production accumulated per Luminary since their last evaluation.
    # Each tick adds sum(lum.domains[D] × universe_pool[D]) for that Luminary.
    # Keyed by str(luminary UUID). Reset per Luminary at evaluation time. Persisted.
    luminary_production_this_eval: dict[str, float] = Field(default_factory=dict)

    # Cumulative Demiurge Essence claimed per tracked domain (see Demiurge.tracked_essence_domains).
    # Persisted so the player can see long-run domain income.
    domain_essence_claimed: dict[str, float] = Field(default_factory=dict)


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
        self._domain_registry: Optional[DomainRegistry] = get_domain_registry()
        self._culture_registry: Optional[CultureRegistry] = get_culture_registry()

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

        # ── Active event continuation (Phase 1 extension) ─
        # Runs at offset ≥ 1; tick-0 effects are applied by the action handler directly.
        event_mutations = self._process_active_events(state)
        state = self._apply_mutations(state, event_mutations)

        state = self._apply_passive_mutations(state, passive)
        state = self._prune_weak_beliefs(state)

        # ── Essence generation (Phase 1 tail) ─────────
        essence_gen_mutations, essence_by_domain = self._process_essence_generation(state, cfg)
        state = self._apply_mutations(state, essence_gen_mutations)
        result.essence_claimed_by_domain = essence_by_domain

        # ── Inject ongoing actions (appended after manual queue) ──────────
        # Manually queued actions in the same category take priority;
        # _validate_and_filter_queue blocks any duplicate-category entry.
        # Map instance.id -> category so we can credit executed_ticks after.
        ongoing_instance_ids: dict[str, str] = {}
        for cat_val, ongoing in list(state.ongoing_actions.items()):
            defn = self._action_library.get(ongoing.action_key)
            if defn is None:
                continue
            instance = ActionInstance(
                action_definition_id=defn.id,
                target_type=ongoing.target_type,
                target_id=ongoing.target_id,
                timestamp=state.universe.current_age,
                demiurge_id=state.demiurge.id,
                proxius_id=ongoing.proxius_id,
                intent=ongoing.intent,
            )
            state.action_queue.append(instance)
            ongoing_instance_ids[str(instance.id)] = cat_val
            ongoing.ticks_active += 1

        # ── Phase 2: Action Processing ─────────────────
        _essence_before = state.essence.actual
        action_result = self._process_action_queue(state, cfg, phase_rng)
        result.action_result = action_result
        state = self._apply_action_mutations(state, action_result)
        state.action_queue = []

        # Credit executed_ticks for ongoing actions that weren't category-blocked.
        # Accepted entries keep their original instance.id; rejected entries get
        # a fresh uuid4(), so membership in this set is unambiguous.
        executed_ids = {str(e.action_instance_id) for e in action_result.entries}
        for iid, cat_val in ongoing_instance_ids.items():
            if iid in executed_ids:
                oa = state.ongoing_actions.get(cat_val)
                if oa:
                    oa.executed_ticks += 1

        # ── Deferred death check ───────────────────────
        # Applied after Phase 2 so a same-tick appoint_proxius saves the mortal.
        # pending_death_mutations and pending_death_narratives are parallel lists.
        for mut, narrative in zip(passive.pending_death_mutations, passive.pending_death_narratives):
            mortal = state.mortals.get(str(mut.target_id))
            if mortal and mortal.role in (MortalRole.PROXIUS, MortalRole.HERALD):
                continue  # appointment this tick saved them; suppress death
            if mortal and mortal.status != MortalStatus.DECEASED:
                mortal.status = MortalStatus.DECEASED
            result.passive_result.narrative_events.append(narrative)

        # Track how long since the Demiurge last gained Essence (for concealment stall)
        if state.essence.actual > _essence_before:
            state.ticks_without_essence_gain = 0
        else:
            state.ticks_without_essence_gain += 1

        # ── Phase 2.5: Proxius Agent Actions ───────────
        agent_mutations = self._resolve_proxius_agents(state, phase_rng)
        state = self._apply_mutations(state, agent_mutations)

        # ── Phase 3: Domain Profiling ──────────────────
        profile = self._build_domain_profile(state)
        result.domain_profile = profile

        # ── Phase 4: Evaluation ────────────────────────
        evaluations = self._run_evaluations(state, profile, cfg)
        result.evaluations = evaluations
        state.pending_attention_triggers = {}  # consumed by evaluations; clear for next tick

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
                        result.pending_death_mutations.append(StateMutation(
                            mutation_type=MutationType.MORTAL_STATUS,
                            target_id=UUID(mid),
                            field="status",
                            new_value=MortalStatus.DECEASED.value,
                            note=f"{mortal.name} died of natural causes (bio_age {new_bio_age:.0f})",
                        ))
                        result.pending_death_narratives.append(
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
            rate = (cfg.starting_visible_decay_rate if mortal.starting_visible
                    else cfg.mortal_visibility_decay_rate)
            new_vis = max(0.0, mortal.visibility - rate)
            result.mortal_mutations.append(StateMutation(
                mutation_type=MutationType.MORTAL_VISIBILITY,
                target_id=UUID(mid),
                field="visibility",
                delta=-(mortal.visibility - new_vis),
                note=f"{mortal.name} visibility decay",
            ))

        # ── Location visibility decay ──────────────────
        for lid, loc in state.locations.items():
            if getattr(loc, "pinned", False) or loc.visibility <= 0.0:
                continue
            new_vis = max(0.0, loc.visibility - cfg.location_visibility_decay_rate)
            if loc.visibility - new_vis > 0.0001:
                result.entity_mutations.append(StateMutation(
                    mutation_type=MutationType.ENTITY_VISIBILITY,
                    target_id=UUID(lid),
                    field="visibility",
                    delta=-(loc.visibility - new_vis),
                    note=f"{loc.name} visibility decay",
                ))

        # ── Civilization visibility decay ──────────────
        for cid, civ in state.civilizations.items():
            if civ.pinned or civ.visibility <= 0.0:
                continue
            new_vis = max(0.0, civ.visibility - cfg.civ_visibility_decay_rate)
            if civ.visibility - new_vis > 0.0001:
                result.entity_mutations.append(StateMutation(
                    mutation_type=MutationType.ENTITY_VISIBILITY,
                    target_id=UUID(cid),
                    field="visibility",
                    delta=-(civ.visibility - new_vis),
                    note=f"{civ.name} visibility decay",
                ))

        # ── Species visibility decay ───────────────────
        for sid, sp in state.species.items():
            if sp.pinned or sp.visibility <= 0.0:
                continue
            new_vis = max(0.0, sp.visibility - cfg.species_visibility_decay_rate)
            if sp.visibility - new_vis > 0.0001:
                result.entity_mutations.append(StateMutation(
                    mutation_type=MutationType.ENTITY_VISIBILITY,
                    target_id=UUID(sid),
                    field="visibility",
                    delta=-(sp.visibility - new_vis),
                    note=f"{sp.name} visibility decay",
                ))

        # ── Passive Proxius footprint accumulation ────────
        # Active Proxii generate proxius_activity each tick.
        # Policy-compliant worlds contribute at PROXIUS_COMPLIANCE_FACTOR of
        # the base rate; excess Proxii on a world contribute at full rate.
        if cfg.proxius_passive_footprint_rate > 0.0:
            policy = state.universe.rules.proxii_policy
            proxii_by_world: dict[str, int] = {}
            for mortal in state.mortals.values():
                if (mortal.role == MortalRole.PROXIUS
                        and mortal.status == MortalStatus.ACTIVE):
                    loc = str(mortal.current_location)
                    proxii_by_world[loc] = proxii_by_world.get(loc, 0) + 1

            total_passive_fp = 0.0
            for count in proxii_by_world.values():
                if policy.max_per_world is not None:
                    compliant = min(count, policy.max_per_world)
                    excess    = max(0, count - policy.max_per_world)
                else:
                    compliant = count
                    excess    = 0
                total_passive_fp += (
                    compliant * cfg.proxius_passive_footprint_rate * PROXIUS_COMPLIANCE_FACTOR
                    + excess  * cfg.proxius_passive_footprint_rate
                )

            if total_passive_fp > 0.001:
                n_active = sum(proxii_by_world.values())
                result.footprint_mutations.append(StateMutation(
                    mutation_type=MutationType.FOOTPRINT_CHANGE,
                    target_id=state.demiurge.id,
                    field="proxius_activity",
                    delta=total_passive_fp,
                    note=f"Passive Proxius activity ({n_active} active)",
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

    def _process_essence_generation(
        self,
        state: SimulationState,
        cfg: TickConfig,
    ) -> tuple[list["StateMutation"], dict[str, float]]:
        """
        Compute per-domain world pools → universe pool → claiming fractions.
        Adds Demiurge's share to essence.actual (no apparent/concealment impact).
        Accumulates each Luminary's share into state.luminary_essence_this_eval.
        Returns (ESSENCE_CHANGE mutations, per-domain claim amounts).
        """
        # Build per-domain universe pool by summing across all SignificantLocations.
        universe_pool: dict[str, float] = {}

        # Build index: world_id → list of civilizations present there
        civs_by_world: dict[str, list["Civilization"]] = {}
        for civ in state.civilizations.values():
            for wid, world in state.worlds.items():
                if str(civ.id) in [str(x) for x in world.civilization_ids]:
                    civs_by_world.setdefault(wid, []).append(civ)

        # Build index: world_id → list of mortals currently there
        mortals_by_world: dict[str, list["NotableMortal"]] = {}
        for mortal in state.mortals.values():
            if mortal.status == "active":
                wid = str(mortal.current_location)
                mortals_by_world.setdefault(wid, []).append(mortal)

        for wid, world in state.worlds.items():
            domain_tags: set[str] = set()
            # Collect all domain tags that appear on this world
            domain_tags.update(world.domain_expression.keys())
            for civ in civs_by_world.get(wid, []):
                domain_tags.update(civ.dominant_beliefs.keys())
            for mortal in mortals_by_world.get(wid, []):
                domain_tags.update(mortal.belief_tags.keys())

            for tag in domain_tags:
                amount = (
                    world.domain_expression.get(tag, 0.0) * cfg.essence_location_weight
                    + sum(
                        civ.dominant_beliefs.get(tag, 0.0)
                        * _CIV_SCALE_ESSENCE_MULT.get(civ.scale.value if hasattr(civ.scale, "value") else str(civ.scale), 0.1)
                        for civ in civs_by_world.get(wid, [])
                    )
                    + sum(
                        mortal.belief_tags.get(tag, 0.0) * cfg.essence_mortal_weight
                        for mortal in mortals_by_world.get(wid, [])
                    )
                )
                if amount > 0.0:
                    universe_pool[tag] = universe_pool.get(tag, 0.0) + amount

        if not universe_pool:
            return []

        luminaries = list(state.luminaries.values())
        demiurge_affiliated = set(state.demiurge.affiliated_domains)
        tracked = set(state.demiurge.tracked_essence_domains)
        EXP = cfg.essence_claiming_exponent

        mutations: list[StateMutation] = []
        demiurge_total_claim = 0.0
        domain_claim_breakdown: dict[str, float] = {}

        for tag, pool in universe_pool.items():
            if pool <= 0.0:
                continue

            lum_total_aff = min(
                0.9, sum(lum.domains.get(tag, 0.0) for lum in luminaries)
            )

            # Accumulate weighted production for each Luminary that has affinity here.
            # This is the satisfaction metric: how much of their domain is being expressed.
            for lum in luminaries:
                lum_aff = min(0.8, lum.domains.get(tag, 0.0))
                if lum_aff <= 0.0:
                    continue
                lid = str(lum.id)
                state.luminary_production_this_eval[lid] = (
                    state.luminary_production_this_eval.get(lid, 0.0) + lum_aff * pool
                )

            if lum_total_aff == 0.0:
                # No Luminary claims this domain — Demiurge gets 100% if affiliated
                if tag in demiurge_affiliated:
                    demiurge_total_claim += pool
                    domain_claim_breakdown[tag] = domain_claim_breakdown.get(tag, 0.0) + pool
                    if tag in tracked:
                        state.domain_essence_claimed[tag] = (
                            state.domain_essence_claimed.get(tag, 0.0) + pool
                        )
                # else sinks to Underreal
                continue

            # lum_fraction = lum_total_aff ** EXP (concave curve; see TickConfig comment)
            lum_fraction = lum_total_aff ** EXP
            dem_fraction = 1.0 - lum_fraction

            dem_claim = pool * dem_fraction if tag in demiurge_affiliated else 0.0
            demiurge_total_claim += dem_claim
            if dem_claim > 0.0:
                domain_claim_breakdown[tag] = domain_claim_breakdown.get(tag, 0.0) + dem_claim
            if tag in tracked and dem_claim > 0.0:
                state.domain_essence_claimed[tag] = (
                    state.domain_essence_claimed.get(tag, 0.0) + dem_claim
                )

        if demiurge_total_claim > 0.001:
            mutations.append(StateMutation(
                mutation_type=MutationType.ESSENCE_CHANGE,
                target_id=state.demiurge.id,
                field="actual",
                delta=demiurge_total_claim,
                note=f"Domain-based Essence claim (+{demiurge_total_claim:.3f})",
            ))

        return mutations, domain_claim_breakdown

    def _apply_passive_mutations(
        self,
        state: SimulationState,
        passive: PassiveWorldResult,
    ) -> SimulationState:

        all_mutations = (
            passive.civilization_mutations
            + passive.mortal_mutations
            + passive.entity_mutations
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
                for collection in (state.civilizations, state.mortals, state.locations):
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
                        LocCondition.DYING, LocCondition.BARREN,
                        LocCondition.STRESSED, LocCondition.STABLE,
                        LocCondition.THRIVING,
                    ]
                    try:
                        idx = condition_ladder.index(world_obj.condition)
                        new_condition = condition_ladder[min(idx + 1, len(condition_ladder) - 1)]
                    except ValueError:
                        new_condition = LocCondition.STABLE
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
                goal_section = ""
                if mortal.active_goal:
                    g = mortal.active_goal
                    ticks_active = state.tick_number - g.started_at_tick
                    last_act = g.last_action.value.replace("_", " ") if g.last_action else "none yet"
                    goal_section = (
                        f" Active directive: imago [{g.imago_node_id}], "
                        f"{ticks_active} tick(s) active, "
                        f"last action: {last_act}"
                        + (f", streak: {g.consecutive_promote_count}" if g.consecutive_promote_count > 0 else "")
                        + (" [PETITION PENDING]" if g.petition_pending else "")
                        + ("." if not g.report_log else f". Last report: {g.report_log[-1]}")
                    )
                else:
                    goal_section = " No active directive."
                narrative = (
                    f"Silent audit of {mortal.name} complete. "
                    f"Alignment: {mortal.alignment:.2f} ({alignment_desc}). "
                    f"Status: {mortal.status.value}. "
                    f"Personal convictions: {tags}."
                    + goal_section
                )
                # No mutations — purely observational; they do not know you checked.

            elif defn.name == "Read Divine Traces":
                target_world_id = str(instance.target_id) if instance.target_id else None
                world_obj = state.worlds.get(target_world_id) if target_world_id else None
                if not world_obj:
                    return mutations, "No world found to read traces on."

                # Find events associated with this world
                relevant: list[Event] = []
                for ev in state.active_events.values():
                    if ev.is_expired(state.tick_number):
                        continue
                    if str(ev.target_world_id) == target_world_id:
                        relevant.append(ev)
                        continue
                    if ev.target_civilization_id is not None:
                        civ = state.civilizations.get(str(ev.target_civilization_id))
                        if civ and str(civ.origin_location_id) == target_world_id:
                            relevant.append(ev)
                            continue
                    if ev.target_mortal_id is not None:
                        mortal = state.mortals.get(str(ev.target_mortal_id))
                        if mortal and str(mortal.current_location) == target_world_id:
                            relevant.append(ev)

                if not relevant:
                    narrative = (
                        f"No divine traces discernible on {world_obj.name}. "
                        f"The world appears untouched by recent divine influence."
                    )
                elif outcome == ActionOutcome.PARTIAL:
                    strongest = max(relevant, key=lambda e: e.current_strength(state.tick_number))
                    age = state.tick_number - strongest.created_at_tick
                    narrative = (
                        f"{len(relevant)} active divine event(s) detected on {world_obj.name}. "
                        f"Dominant type: {strongest.event_type.value}, "
                        f"approximately {age} tick(s) old."
                    )
                else:
                    lines = [f"Divine traces on {world_obj.name} ({len(relevant)} active event(s)):"]
                    for ev in sorted(relevant, key=lambda e: -e.current_strength(state.tick_number)):
                        age = state.tick_number - ev.created_at_tick
                        strength = ev.current_strength(state.tick_number)
                        remaining = ev.duration - age
                        domains = ", ".join(dv.domain_tag for dv in ev.domain_vectors) or "none"
                        lines.append(
                            f"  [{ev.event_type.value}] age {age}, "
                            f"strength {strength:.2f}, "
                            f"{remaining} tick(s) remaining — domains: {domains}"
                        )
                    narrative = "\n".join(lines)
                # Purely observational — no mutations.

            elif defn.name == "Ask for Orders":
                luminary = state.luminaries.get(str(instance.target_id)) if instance.target_id else None
                if not luminary:
                    return mutations, "No Luminary found to petition."

                lid = str(luminary.id)
                cfg = state.config

                # Raise attention — asking for orders reminds them you're here
                mutations.append(StateMutation(
                    mutation_type=MutationType.FOOTPRINT_CHANGE,
                    target_id=luminary.id,
                    field="attention",
                    delta=0.06,
                    note=f"Ask for Orders: {luminary.name} attention raised",
                ))

                # Compute threshold parameters
                sorted_affs = [
                    min(0.8, v)
                    for _, v in sorted(luminary.domains.items(), key=lambda x: (-x[1], x[0]))
                ]
                effective_affinity = sum(
                    aff * (cfg.luminary_essence_decay ** i)
                    for i, aff in enumerate(sorted_affs)
                )
                ticks_since = state.ticks_since_evaluation.get(lid, cfg.evaluation_interval)
                base_threshold_so_far = effective_affinity * cfg.luminary_essence_baseline_rate * ticks_since
                raised = luminary.essence_expectation_raised
                threshold_so_far = base_threshold_so_far + raised

                # Project threshold at next evaluation (use eval_interval ticks as horizon)
                eval_interval = max(5.0, cfg.evaluation_interval)
                projected_threshold = effective_affinity * cfg.luminary_essence_baseline_rate * eval_interval + raised

                domain_production = state.luminary_production_this_eval.get(lid, 0.0)
                surplus = domain_production - threshold_so_far

                # Per-domain contribution from current universe expression
                profile = state.previous_domain_profile
                report = [f"Orders from {luminary.name}"]

                # Essence expectations section
                report.append("  Essence Expectations:")
                for tag, aff in sorted(luminary.domains.items(), key=lambda x: (-x[1], x[0])):
                    universe_pool = profile.scores.get(tag, 0.0) if profile else 0.0
                    short = tag.split(":", 1)[1] if ":" in tag else tag
                    report.append(f"    {short:<14} affinity {aff:.2f}  universe expression {universe_pool:.3f}")

                report.append(f"  Effective affinity: {effective_affinity:.3f}")
                report.append(
                    f"  Threshold so far:   {threshold_so_far:.3f}  "
                    f"(over {ticks_since:.0f} tick(s), +{raised:.3f} raised expectation)"
                )
                report.append(f"  Projected at eval:  {projected_threshold:.3f}")
                report.append(
                    f"  Produced this period: {domain_production:.3f}  "
                    f"({'above' if surplus >= 0 else 'below'} threshold by {abs(surplus):.3f})"
                )

                # Previous period trend
                if luminary.essence_received_log:
                    prev = luminary.essence_received_log[-1]
                    trend = "improving" if domain_production >= prev else "declining"
                    report.append(f"  Last period: {prev:.3f}  (trend: {trend})")

                # Disposition section
                disp = luminary.disposition
                def _disp_label(v: float, axis: str) -> str:
                    if axis == "results":
                        if v >= 0.4:   return "very pleased"
                        if v >= 0.15:  return "satisfied"
                        if v >= -0.15: return "neutral"
                        if v >= -0.4:  return "dissatisfied"
                        return "deeply displeased"
                    else:  # methods
                        if v >= 0.4:   return "fully approving"
                        if v >= 0.15:  return "comfortable"
                        if v >= -0.15: return "neutral"
                        if v >= -0.4:  return "uneasy"
                        return "strongly opposed"

                report.append("  Disposition:")
                report.append(
                    f"    Results:  {disp.results:+.3f}  ({_disp_label(disp.results, 'results')})"
                )
                report.append(
                    f"    Methods:  {disp.methods:+.3f}  ({_disp_label(disp.methods, 'methods')})"
                )
                report.append(
                    f"    Overall:  {disp.overall:+.3f}"
                )

                # Constraints context
                if luminary.constraints:
                    report.append(f"  Active Constraints: {len(luminary.constraints)}")
                    for con in luminary.constraints:
                        weight_str = f"weight {con.enforcement_weight:.2f}"
                        report.append(f"    · {con.name}  ({weight_str})")

                narrative = "\n".join(report)

            return mutations, narrative

        # ── Weigh Civilization ────────────────────────
        if isinstance(intent, WeighCivilizationIntent):
            civ = state.civilizations.get(str(instance.target_id)) if instance.target_id else None
            if not civ:
                return mutations, "No civilization found to weigh."

            snap = intent

            def _snap_delta(cur: float, prev: float) -> str:
                d = cur - prev
                return f"  ({d:+.3f})" if abs(d) >= 0.001 else ""

            theistic_str = "Yes" if civ.theistic else "No"
            da_d = _snap_delta(civ.divine_awareness, snap.divine_awareness_snapshot)
            report = [
                f"Civilization Report: {civ.name}",
                f"  Scale: {civ.scale.value}  |  Age: {civ.age:.0f}  |  Theistic: {theistic_str}",
                f"  Divine Awareness: {civ.divine_awareness:.2f}{da_d}",
            ]

            # Worlds
            origin_world = state.worlds.get(str(civ.origin_location_id)) if civ.origin_location_id else None
            if origin_world:
                report.append(f"  Origin: {origin_world.name}")
            present_elsewhere = [
                w for wid, w in state.worlds.items()
                if any(str(x) == str(civ.id) for x in w.civilization_ids)
                and wid != str(civ.origin_location_id)
            ]
            for w in present_elsewhere:
                win_note = "" if is_in_window(w) else "  [not in Window]"
                report.append(f"  Also present: {w.name}{win_note}")

            # Health
            report.append("  Health (delta from last tick):")
            for field_name in ("stability", "prosperity", "cohesion"):
                cur_val = getattr(civ.health, field_name)
                d = _snap_delta(cur_val, snap.health_snapshot.get(field_name, cur_val))
                report.append(f"    {field_name.capitalize():<12} {cur_val:.2f}{d}")

            # Domain beliefs
            all_belief_tags = sorted(set(civ.dominant_beliefs) | set(snap.beliefs_snapshot))
            if all_belief_tags:
                report.append("  Domain Beliefs:")
                for tag in all_belief_tags:
                    cur_val = civ.dominant_beliefs.get(tag, 0.0)
                    short = tag.split(":", 1)[1] if ":" in tag else tag
                    if cur_val < 0.001:
                        report.append(f"    {short:<16} (removed this tick)")
                    else:
                        d = _snap_delta(cur_val, snap.beliefs_snapshot.get(tag, 0.0))
                        report.append(f"    {short:<16} {cur_val:.3f}{d}")

            # Cultural profile
            all_culture_tags = sorted(set(civ.culture_tags) | set(snap.culture_snapshot))
            if all_culture_tags:
                report.append("  Cultural Profile:")
                for tag in all_culture_tags:
                    cur_val = civ.culture_tags.get(tag, 0.0)
                    short = tag.split(":", 1)[1] if ":" in tag else tag
                    if cur_val < 0.001:
                        report.append(f"    {short:<16} (removed this tick)")
                    else:
                        d = _snap_delta(cur_val, snap.culture_snapshot.get(tag, 0.0))
                        report.append(f"    {short:<16} {cur_val:.3f}{d}")

            return mutations, "\n".join(report)
            # Purely observational — no mutations.

        # ── Scry ─────────────────────────────────────
        if isinstance(intent, ScryIntent):
            scope = intent.scope

            scope_fp: dict[ScryScope, float] = {
                ScryScope.WORLD:    0.05,
                ScryScope.SYSTEM:   0.10,
                ScryScope.GALAXY:   0.20,
                ScryScope.UNIVERSE: 0.35,
            }
            fp_delta = scope_fp[scope] - 0.05  # definition already adds 0.05
            if fp_delta > 0.0:
                mutations.append(StateMutation(
                    mutation_type=MutationType.FOOTPRINT_CHANGE,
                    target_id=state.demiurge.id,
                    field="subtle_influence",
                    delta=fp_delta,
                    note=f"Scry ({scope.value}) extra footprint",
                ))

            scope_essence: dict[ScryScope, float] = {
                ScryScope.WORLD:    0.0,
                ScryScope.SYSTEM:   0.0,
                ScryScope.GALAXY:   0.3,
                ScryScope.UNIVERSE: 0.5,
            }
            scry_essence_cost = scope_essence[scope]
            if scry_essence_cost > 0.0:
                mutations.append(StateMutation(
                    mutation_type=MutationType.ESSENCE_CHANGE,
                    target_id=state.demiurge.id,
                    field="actual",
                    delta=-scry_essence_cost,
                    note=f"Scry ({scope.value}) essence cost",
                ))

            scope_anchor: dict[ScryScope, int] = {
                ScryScope.WORLD:    3,
                ScryScope.SYSTEM:   2,
                ScryScope.GALAXY:   1,
                ScryScope.UNIVERSE: 0,
            }
            anchor = scope_anchor[scope]

            scope_start_vis: dict[ScryScope, float] = {
                ScryScope.WORLD:    0.70,
                ScryScope.SYSTEM:   0.60,
                ScryScope.GALAXY:   0.45,
                ScryScope.UNIVERSE: 0.30,
            }
            start_vis = scope_start_vis[scope]

            def _depth_chance(delta: int) -> float:
                if delta == 0: return 0.85
                if delta == 1: return 0.55
                if delta == 2: return 0.30
                if delta == 3: return 0.06
                if delta == 4: return 0.02
                return 0.005

            # ── Spatial proximity ──────────────────────────────────────
            # Galaxy coordinates are multiplied by this factor so that
            # cross-galaxy distances dwarf intra-galaxy ones automatically.
            _GALAXY_SCALE = 1000.0
            # Distance at which the proximity factor drops to 0.5.
            _SPATIAL_SCALE = 8.0

            def _effective_pos(loc_id: str) -> tuple[float, float, float]:
                """Effective 3-D position accounting for galaxy-level offset."""
                loc = state.locations.get(loc_id)
                if loc is None:
                    return (0.0, 0.0, 0.0)
                cx, cy, cz = loc.coordinates.x, loc.coordinates.y, loc.coordinates.z
                if loc.parent_id is not None:
                    px, py, pz = _effective_pos(str(loc.parent_id))
                    return (px * _GALAXY_SCALE + cx,
                            py * _GALAXY_SCALE + cy,
                            pz * _GALAXY_SCALE + cz)
                return (cx, cy, cz)

            # Resolve the focus position for WORLD, SYSTEM, and GALAXY scopes.
            # UNIVERSE has no spatial focus — factor is always 1.0.
            _focus_pos: Optional[tuple[float, float, float]] = None
            if scope in (ScryScope.WORLD, ScryScope.SYSTEM, ScryScope.GALAXY) and instance.target_id:
                target_loc = state.locations.get(str(instance.target_id))
                if target_loc is not None:
                    if scope == ScryScope.WORLD and target_loc.parent_id is not None:
                        # Focus on the parent system of the targeted world
                        _focus_pos = _effective_pos(str(target_loc.parent_id))
                    else:
                        _focus_pos = _effective_pos(str(instance.target_id))

            def _spatial_factor(candidate_loc_id: str) -> float:
                """
                Distance-based multiplier on discovery probability.
                Returns 1.0 when there is no spatial focus (galaxy/universe scope).
                Uses the candidate's effective position at the system level —
                i.e., if the candidate is a world, its parent system's position.
                """
                if _focus_pos is None:
                    return 1.0
                loc = state.locations.get(candidate_loc_id)
                if loc is None:
                    return 1.0
                # Walk up to system level for the distance calculation
                if loc.location_type not in ("galaxy", "system"):
                    ref_id = str(loc.parent_id) if loc.parent_id else candidate_loc_id
                else:
                    ref_id = candidate_loc_id
                rx, ry, rz = _effective_pos(ref_id)
                fx, fy, fz = _focus_pos
                dist = math.sqrt((rx - fx) ** 2 + (ry - fy) ** 2 + (rz - fz) ** 2)
                return 1.0 / (1.0 + dist / _SPATIAL_SCALE)

            dreg = self._domain_registry
            affiliated = state.demiurge.affiliated_domains

            def _domain_bonus(entity_tags: list[str], base: float) -> float:
                """Domain affinity bonus, scaled down proportionally at high depths."""
                if not dreg or not affiliated or not entity_tags:
                    return 0.0
                total = 0.0
                for etag in entity_tags:
                    for atag in affiliated:
                        try:
                            total += max(0.0, dreg.similarity(etag, atag)) * 0.05
                        except Exception:
                            pass
                bonus_scale = min(1.0, base / 0.55)
                return min(0.20, total) * bonus_scale

            # eligible_locs: location IDs that are already in window OR discovered
            # this tick. Entities can only be found if their container is eligible.
            eligible_locs: set[str] = {
                lid for lid, loc in state.locations.items() if is_in_window(loc)
            }

            discovered_locs:  list[str] = []
            discovered_civs:  list[str] = []
            discovered_sp:    list[str] = []
            discovered_mort:  list[str] = []
            refreshed_locs:   list[str] = []
            refreshed_civs:   list[str] = []
            refreshed_sp:     list[str] = []
            refreshed_mort:   list[str] = []

            # Civilization scale → effective discovery depth
            _CIV_SCALE_DEPTH: dict[str, int] = {
                "nascent": 4, "tribal": 4, "city_state": 4,
                "regional": 4, "continental": 4, "planetary": 4,
                "interplanetary": 3,
                "interstellar": 2,
                "intergalactic": 1,
            }

            def _civ_anchor(civ: "Civilization") -> tuple[Optional[str], int]:
                """Returns (anchor_location_id, depth) for a civilization."""
                depth = _CIV_SCALE_DEPTH.get(civ.scale.value, 4)
                if civ.origin_location_id is None:
                    return (None, depth)
                loc_id = str(civ.origin_location_id)
                # Walk up the hierarchy the required number of steps above the world
                for _ in range(4 - depth):
                    loc = state.locations.get(loc_id)
                    if loc is None or loc.parent_id is None:
                        break
                    loc_id = str(loc.parent_id)
                return (loc_id, depth)

            # ── Locations: process galaxy → system → world/plane to build eligible_locs
            # incrementally so container prerequisites cascade within a single tick.
            loc_passes = (
                [(lid, loc) for lid, loc in state.locations.items()
                 if loc.location_type == "galaxy"   and not getattr(loc, "pinned", False)],
                [(lid, loc) for lid, loc in state.locations.items()
                 if loc.location_type == "system"   and not getattr(loc, "pinned", False)],
                [(lid, loc) for lid, loc in state.locations.items()
                 if loc.location_type not in ("galaxy", "system") and not getattr(loc, "pinned", False)],
            )
            for pass_items in loc_passes:
                for lid, loc in pass_items:
                    depth = 1 if loc.location_type == "galaxy" else (2 if loc.location_type == "system" else 3)
                    # Galaxies have no parent entity; deeper locations require parent in window.
                    if depth > 1 and (loc.parent_id is None or str(loc.parent_id) not in eligible_locs):
                        continue
                    delta = abs(depth - anchor)
                    base = _depth_chance(delta)
                    sf = _spatial_factor(lid)
                    expr_tags = list(getattr(loc, "domain_expression", {}).keys())
                    p = max(0.0, min(1.0, (base + _domain_bonus(expr_tags + loc.traits, base)) * sf))
                    if rng.random() < p:
                        was_visible = is_in_window(loc)
                        new_vis = max(loc.visibility, start_vis)
                        mutations.append(StateMutation(
                            mutation_type=MutationType.ENTITY_VISIBILITY,
                            target_id=UUID(lid),
                            field="visibility",
                            new_value=new_vis,
                            note=f"Scry ({scope.value}): {loc.name} sighted",
                        ))
                        eligible_locs.add(lid)
                        if was_visible:
                            refreshed_locs.append(loc.name)
                        else:
                            discovered_locs.append(loc.name)

            # ── Civilizations
            for cid, civ in state.civilizations.items():
                if civ.pinned:
                    continue
                anchor_id, depth = _civ_anchor(civ)
                if anchor_id is not None and anchor_id not in eligible_locs:
                    continue
                delta = abs(depth - anchor)
                base = _depth_chance(delta)
                sf = _spatial_factor(anchor_id) if anchor_id else 1.0
                # Extra bonus if homeworld is already known, even for high-scale civs
                origin_prox = 0.0
                if depth < 4 and civ.origin_location_id is not None:
                    if str(civ.origin_location_id) in eligible_locs:
                        origin_prox = 0.15 * min(1.0, base / 0.55)
                p = max(0.0, min(1.0,
                    (base + _domain_bonus(list(civ.dominant_beliefs.keys()), base) + origin_prox) * sf
                ))
                if rng.random() < p:
                    was_visible = is_in_window(civ)
                    new_vis = max(civ.visibility, start_vis)
                    mutations.append(StateMutation(
                        mutation_type=MutationType.ENTITY_VISIBILITY,
                        target_id=UUID(cid),
                        field="visibility",
                        new_value=new_vis,
                        note=f"Scry ({scope.value}): {civ.name} sighted",
                    ))
                    if was_visible:
                        refreshed_civs.append(civ.name)
                    else:
                        discovered_civs.append(civ.name)

            # ── Species
            for sid, sp in state.species.items():
                if sp.pinned:
                    continue
                origin_id = str(sp.origin_world_id) if sp.origin_world_id else None
                if origin_id is not None and origin_id not in eligible_locs:
                    continue
                delta = abs(4 - anchor)
                base = _depth_chance(delta)
                sf = _spatial_factor(origin_id) if origin_id else 1.0
                p = max(0.0, min(1.0, (base + _domain_bonus(sp.domain_tags, base)) * sf))
                if rng.random() < p:
                    was_visible = is_in_window(sp)
                    new_vis = max(sp.visibility, start_vis)
                    mutations.append(StateMutation(
                        mutation_type=MutationType.ENTITY_VISIBILITY,
                        target_id=UUID(sid),
                        field="visibility",
                        new_value=new_vis,
                        note=f"Scry ({scope.value}): {sp.name} sighted",
                    ))
                    if was_visible:
                        refreshed_sp.append(sp.name)
                    else:
                        discovered_sp.append(sp.name)

            # ── Mortals
            for mid, mortal in state.mortals.items():
                if (mortal.status == MortalStatus.DECEASED
                        or mortal.prominence >= ALWAYS_VISIBLE_THRESHOLD):
                    continue
                if str(mortal.current_location) not in eligible_locs:
                    continue
                delta = abs(5 - anchor)
                base = _depth_chance(delta)
                sf = _spatial_factor(str(mortal.current_location))
                p = max(0.0, min(1.0,
                    (base + _domain_bonus(list(mortal.belief_tags.keys()) + mortal.personal_tags, base)) * sf
                ))
                if rng.random() < p:
                    was_visible = mortal.visibility > VISIBILITY_FLOOR
                    new_vis = max(mortal.visibility, start_vis)
                    mutations.append(StateMutation(
                        mutation_type=MutationType.MORTAL_VISIBILITY,
                        target_id=UUID(mid),
                        field="visibility",
                        new_value=new_vis,
                        note=f"Scry ({scope.value}): {mortal.name} sighted",
                    ))
                    if was_visible:
                        refreshed_mort.append(mortal.name)
                    else:
                        discovered_mort.append(mortal.name)

            parts = [f"You scryed at {scope.value} scope."]
            all_discovered = discovered_locs + discovered_civs + discovered_sp + discovered_mort
            all_refreshed  = refreshed_locs  + refreshed_civs  + refreshed_sp  + refreshed_mort
            if discovered_locs:
                parts.append(f"Locations sighted: {', '.join(discovered_locs)}.")
            if discovered_civs:
                parts.append(f"Civilizations sighted: {', '.join(discovered_civs)}.")
            if discovered_sp:
                parts.append(f"Species sighted: {', '.join(discovered_sp)}.")
            if discovered_mort:
                parts.append(f"Mortals sighted: {', '.join(discovered_mort)}.")
            if all_refreshed and not all_discovered:
                parts.append(f"Sight maintained on: {', '.join(all_refreshed)}.")
            elif all_refreshed:
                parts.append(f"Also maintained: {', '.join(all_refreshed)}.")
            if not all_discovered and not all_refreshed:
                parts.append("Nothing new came into view.")
            return mutations, " ".join(parts)

        # ── Change Affiliated Domain ──────────────────
        if isinstance(intent, ChangeAffiliatedDomainsIntent):
            old_tag = intent.old_domain
            new_tag = intent.new_domain
            if old_tag not in state.demiurge.affiliated_domains:
                return mutations, f"{old_tag} is not one of your affiliated domains."
            if new_tag in state.demiurge.affiliated_domains:
                return mutations, f"{new_tag} is already one of your affiliated domains."
            mutations.append(StateMutation(
                mutation_type=MutationType.AFFILIATED_DOMAIN_CHANGE,
                target_id=state.demiurge.id,
                field="affiliated_domains",
                new_value=f"{old_tag}→{new_tag}",
                note=f"Demiurge reoriented affiliation: {old_tag} → {new_tag}",
            ))
            old_short = old_tag.split(":", 1)[1] if ":" in old_tag else old_tag
            new_short = new_tag.split(":", 1)[1] if ":" in new_tag else new_tag
            return mutations, (
                f"You release your conceptual hold on {old_short.title()} and turn your focus "
                f"toward {new_short.title()}. The reorientation settles into your nature."
            )

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
                f"You turn your awareness inward and contemplate {short.title()}. "
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

            # Emit a RAMP_FADE event so the whisper builds then fades over 4 ticks
            mutations.append(StateMutation(
                mutation_type=MutationType.EVENT_EMITTED,
                target_id=None,
                field="active_events",
                new_value=Event(
                    event_type=EventType.WHISPER,
                    curve=StrengthCurve.RAMP_FADE,
                    source_action_id=instance.action_definition_id,
                    created_at_tick=state.tick_number,
                    duration=4,
                    base_strength=effectiveness,
                    peak_offset=1,
                    target_mortal_id=instance.target_id,
                    target_civilization_id=mortal.civilization_id,
                    domain_vectors=intent.domain_vectors,
                    domain_shift_rate=0.06,
                    attention_per_tick=0.01,
                    imago_node_id=getattr(intent, "imago_node_id", None),
                    concept=intent.concept,
                ),
            ))

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

            if outcome == ActionOutcome.FAILURE:
                narrative = (
                    f"The directive did not reach {proxius.name} clearly. "
                    f"They remain without guidance."
                )
            else:
                # Set goal on the Proxius — they will act autonomously each tick
                imago_id = intent.imago_node_id or ""
                goal = ProxiusGoal(
                    imago_node_id=imago_id,
                    target_location_id=proxius.current_location,
                    target_civilization_id=intent.target_civilization_id,
                    domain_vectors=list(intent.domain_vectors),
                    latitude=intent.latitude,
                    constraints=list(intent.constraints),
                    started_at_tick=state.tick_number,
                )
                mutations.append(StateMutation(
                    mutation_type=MutationType.PROXIUS_GOAL_SET,
                    target_id=proxius.id,
                    field="active_goal",
                    new_value=goal,
                    note=f"Directive set: '{intent.goal_statement[:60]}'",
                ))

                dedication = proxius.alignment * (1.0 - intent.latitude * 0.3)
                if dedication > 0.7:
                    dedication_note = "with clear purpose"
                elif dedication > 0.4:
                    dedication_note = "with some reservation"
                else:
                    dedication_note = "reluctantly"
                narrative = (
                    f"Proxius {proxius.name} has been given a directive: "
                    f"'{intent.goal_statement}'. "
                    f"They will pursue it {dedication_note}."
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

            # Emit a SPIKE_FADE event so the omen echoes for 4 more ticks
            omen_world_id = self._resolve_world_id(instance, state)
            mutations.append(StateMutation(
                mutation_type=MutationType.EVENT_EMITTED,
                target_id=None,
                field="active_events",
                new_value=Event(
                    event_type=EventType.OMEN,
                    curve=StrengthCurve.SPIKE_FADE,
                    source_action_id=instance.action_definition_id,
                    created_at_tick=state.tick_number,
                    duration=5,
                    base_strength=effectiveness,
                    decay_rate=0.6,
                    target_civilization_id=intent.civilization_scope,
                    target_world_id=omen_world_id,
                    domain_vectors=intent.domain_vectors,
                    domain_shift_rate=0.08,
                    divine_awareness_rate=0.03,
                    attention_per_tick=0.04,
                    imago_node_id=getattr(intent, "imago_node_id", None),
                    sign_description=intent.sign_description,
                ),
            ))

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

            # Emit a FLAT event for multi-tick continuation.
            # If an active DEVELOPMENT_NUDGE already targets this civ, give it a
            # sustained bonus instead of stacking a second event.
            existing_dev_event: Optional[Event] = None
            for ev in state.active_events.values():
                if (
                    ev.event_type == EventType.DEVELOPMENT_NUDGE
                    and ev.target_civilization_id == civ_obj.id
                    and not ev.is_expired(state.tick_number)
                ):
                    existing_dev_event = ev
                    break

            if existing_dev_event is not None:
                existing_dev_event.base_strength = min(
                    1.0, existing_dev_event.base_strength + 0.05
                )
            else:
                mutations.append(StateMutation(
                    mutation_type=MutationType.EVENT_EMITTED,
                    target_id=None,
                    field="active_events",
                    new_value=Event(
                        event_type=EventType.DEVELOPMENT_NUDGE,
                        curve=StrengthCurve.FLAT,
                        source_action_id=instance.action_definition_id,
                        created_at_tick=state.tick_number,
                        duration=6,
                        base_strength=effectiveness,
                        target_civilization_id=civ_obj.id,
                        domain_vectors=intent.domain_vectors,
                        domain_shift_rate=0.05,
                    ),
                ))

        # ── Luminary Petition ─────────────────────────
        elif isinstance(intent, LuminaryPetitionIntent):
            luminary = state.luminaries.get(str(instance.target_id)) if instance.target_id else None
            if not luminary:
                return mutations, "Target Luminary not found."

            if defn.name == "Report to Luminary":
                if outcome == ActionOutcome.SUCCESS:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.DISPOSITION_CHANGE,
                        target_id=luminary.id,
                        field="results",
                        delta=0.05,
                        note=f"Report to {luminary.name}: favorable reception",
                    ))
                    mutations.append(StateMutation(
                        mutation_type=MutationType.FOOTPRINT_CHANGE,
                        target_id=luminary.id,
                        field="attention",
                        delta=-0.07,
                        note=f"Report to {luminary.name}: attention eased",
                    ))
                    narrative = (
                        f"Your report on '{intent.subject}' was well received by {luminary.name}. "
                        f"Their attention eases slightly."
                    )
                elif outcome == ActionOutcome.PARTIAL:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.FOOTPRINT_CHANGE,
                        target_id=luminary.id,
                        field="attention",
                        delta=-0.03,
                        note=f"Report to {luminary.name}: partial acknowledgement",
                    ))
                    narrative = (
                        f"Your report on '{intent.subject}' was received without comment. "
                        f"{luminary.name} seems mildly satisfied."
                    )
                else:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.DISPOSITION_CHANGE,
                        target_id=luminary.id,
                        field="methods",
                        delta=-0.02,
                        note=f"Report to {luminary.name}: poorly received",
                    ))
                    mutations.append(StateMutation(
                        mutation_type=MutationType.FOOTPRINT_CHANGE,
                        target_id=luminary.id,
                        field="attention",
                        delta=0.05,
                        note=f"Report to {luminary.name}: raised suspicion",
                    ))
                    narrative = (
                        f"Your report on '{intent.subject}' was poorly received. "
                        f"{luminary.name} appears displeased."
                    )

            elif defn.name == "Dispute Demand":
                if outcome == ActionOutcome.SUCCESS:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.DISPOSITION_CHANGE,
                        target_id=luminary.id,
                        field="methods",
                        delta=0.04,
                        note=f"Dispute with {luminary.name}: argument accepted",
                    ))
                    narrative = (
                        f"Your dispute regarding '{intent.subject}' was acknowledged. "
                        f"{luminary.name} conceded the point."
                    )
                elif outcome == ActionOutcome.PARTIAL:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.DISPOSITION_CHANGE,
                        target_id=luminary.id,
                        field="methods",
                        delta=-0.03,
                        note=f"Dispute with {luminary.name}: poorly received",
                    ))
                    mutations.append(StateMutation(
                        mutation_type=MutationType.FOOTPRINT_CHANGE,
                        target_id=luminary.id,
                        field="attention",
                        delta=0.08,
                        note=f"Dispute with {luminary.name}: attention spike",
                    ))
                    narrative = (
                        f"Your dispute regarding '{intent.subject}' was heard but did not land well. "
                        f"{luminary.name} is watching more closely."
                    )
                else:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.DISPOSITION_CHANGE,
                        target_id=luminary.id,
                        field="methods",
                        delta=-0.10,
                        note=f"Dispute with {luminary.name}: infuriated",
                    ))
                    mutations.append(StateMutation(
                        mutation_type=MutationType.FOOTPRINT_CHANGE,
                        target_id=luminary.id,
                        field="attention",
                        delta=0.15,
                        note=f"Dispute with {luminary.name}: severe attention spike",
                    ))
                    narrative = (
                        f"Your dispute regarding '{intent.subject}' infuriated {luminary.name}. "
                        f"This has consequences."
                    )

            elif defn.name == "Petition for Constraint Relaxation":
                if outcome == ActionOutcome.SUCCESS:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.DISPOSITION_CHANGE,
                        target_id=luminary.id,
                        field="methods",
                        delta=0.02,
                        note=f"Constraint petition to {luminary.name}: acknowledged",
                    ))
                    mutations.append(StateMutation(
                        mutation_type=MutationType.DISPOSITION_CHANGE,
                        target_id=luminary.id,
                        field="results",
                        delta=-0.02,
                        note=f"Constraint petition: reveals strain against constraint",
                    ))
                    narrative = (
                        f"Your petition regarding '{intent.subject}' was acknowledged by {luminary.name}. "
                        f"The latitude may widen — though the petition itself signals you have been straining."
                    )
                elif outcome == ActionOutcome.PARTIAL:
                    narrative = (
                        f"{luminary.name} heard your petition regarding '{intent.subject}' "
                        f"but offered no commitments."
                    )
                else:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.DISPOSITION_CHANGE,
                        target_id=luminary.id,
                        field="methods",
                        delta=-0.05,
                        note=f"Constraint petition to {luminary.name}: impertinent",
                    ))
                    mutations.append(StateMutation(
                        mutation_type=MutationType.FOOTPRINT_CHANGE,
                        target_id=luminary.id,
                        field="attention",
                        delta=0.10,
                        note=f"Constraint petition rejected: scrutiny raised",
                    ))
                    narrative = (
                        f"{luminary.name} found your petition regarding '{intent.subject}' impertinent. "
                        f"The request has drawn greater scrutiny."
                    )

            elif outcome == ActionOutcome.SUCCESS:
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

            target_world = state.worlds.get(str(intent.target_world_id))  # type: ignore[assignment]
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
            if world_obj.condition != LocCondition.BARREN:
                return mutations, (
                    f"{world_obj.name} already sustains life — seeding had no effect."
                )
            if outcome == ActionOutcome.FAILURE:
                return mutations, (
                    f"The seeding of {world_obj.name} failed to take hold. "
                    f"The world remains barren."
                )

            new_condition = (
                LocCondition.STABLE if outcome == ActionOutcome.SUCCESS
                else LocCondition.STRESSED
            )
            new_species = Species(
                name=intent.species_name,
                origin_world_id=world_obj.id,
                sapient=intent.sapient,
                transplanted=False,
                lifespan_min=intent.lifespan_min,
                lifespan_max=intent.lifespan_max,
                bio_tags=intent.bio_tags,
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
            all_lum_domain_tags[lid_inner] = list(lum_inner.domains.keys())

        for lid, luminary in state.luminaries.items():
            ticks_since = state.ticks_since_evaluation.get(lid, cfg.evaluation_interval)
            current_att = state.luminary_attention.get(lid, 0.2)

            personality = (
                self._domain_registry.compute_personality(luminary.domains)
                if self._domain_registry else LuminaryPersonality()
            )

            # Evaluation interval scaled by reactivity: [5, 15]
            effective_interval = cfg.evaluation_interval * (1.0 - personality.reactivity * 0.5)
            if personality.capriciousness > 0:
                effective_interval += self._rng.gauss(0, personality.capriciousness * 1.5)
            effective_interval = max(5.0, effective_interval)

            # Attention threshold scaled by reactivity: [0.4, 0.8]
            effective_attention_threshold = 0.6 - personality.reactivity * 0.2

            should_evaluate = (
                ticks_since >= effective_interval
                or current_att > effective_attention_threshold
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

            # Attention level — populated by active event continuation in Phase 1
            attention_triggers: list[AttentionTrigger] = (
                state.pending_attention_triggers.get(lid, [])
            )
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

            # Essence satisfaction — record period weighted production, reset accumulator
            domain_production = state.luminary_production_this_eval.get(lid, 0.0)
            sorted_affs = [
                min(0.8, v)
                for _, v in sorted(luminary.domains.items(), key=lambda x: (-x[1], x[0]))
            ]
            effective_affinity = sum(aff * (cfg.luminary_essence_decay ** i) for i, aff in enumerate(sorted_affs))
            base_threshold = effective_affinity * cfg.luminary_essence_baseline_rate * ticks_since
            lum_threshold = base_threshold + luminary.essence_expectation_raised
            essence_satisfaction = evaluate_essence_satisfaction(
                luminary_id=luminary.id,
                domain_production=domain_production,
                production_log=luminary.essence_received_log,
                threshold=lum_threshold,
            )
            luminary.essence_received_log.append(domain_production)
            if len(luminary.essence_received_log) > 2:
                luminary.essence_received_log = luminary.essence_received_log[-2:]
            state.luminary_production_this_eval[lid] = 0.0

            # Update raised expectations and shortfall counter
            if essence_satisfaction.above_threshold:
                excess = max(0.0, domain_production - base_threshold)
                luminary.essence_expectation_raised = excess * cfg.luminary_essence_recall
                luminary.consecutive_essence_shortfalls = 0
            else:
                luminary.consecutive_essence_shortfalls += 1
                if luminary.consecutive_essence_shortfalls >= 2:
                    luminary.essence_expectation_raised = max(
                        0.0, luminary.essence_expectation_raised - 0.10
                    )
                    luminary.consecutive_essence_shortfalls = 0

            # Disposition delta assembly
            delta = DispositionDelta()

            results_reason = engine.domain_alignment_to_results_delta(
                overall_alignment, prev_overall, personality
            )
            delta.results += results_reason.delta
            delta.reasons.append(results_reason)

            # Similarity-weighted influence from related/opposing expressed domains
            sim_modifier = engine.similarity_results_modifier(
                luminary_domain_tags=luminary_domain_tags,
                fellow_luminary_tags=fellow_lum_tags,
                current_profile=profile,
                personality=personality,
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

            # Capriciousness: mercurial Luminaries add random variance to evaluations
            sigma = max(0.0, personality.capriciousness) * 0.1
            if sigma > 0.01:
                capricious_swing = self._rng.gauss(0, sigma)
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

            # Essence satisfaction feeds results disposition
            if abs(essence_satisfaction.disposition_delta) > 0.001:
                delta.results += essence_satisfaction.disposition_delta
                delta.reasons.append(DispositionDeltaReason(
                    axis="results",
                    delta=essence_satisfaction.disposition_delta,
                    source="essence_satisfaction",
                    note=(
                        f"Domain production {domain_production:.2f} "
                        f"({'above' if essence_satisfaction.above_threshold else 'below'} threshold, "
                        f"{'growing' if essence_satisfaction.growing else 'flat/declining'})"
                    ),
                ))

            # Dialogue triggers
            triggers = engine.generate_dialogue_triggers(
                luminary_id=luminary.id,
                luminary_domain_tags=luminary_domain_tags,
                personality=personality,
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
                essence_satisfaction=essence_satisfaction,
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

    def _process_active_events(
        self,
        state: SimulationState,
    ) -> list[StateMutation]:
        """
        Apply continuation effects from active_events for the current tick.
        Skips offset-0 (action handler covers that tick directly).
        Populates state.pending_attention_triggers for Phase 4 consumption.
        Prunes expired events.
        """
        mutations: list[StateMutation] = []
        expired_ids: list[str] = []

        for eid, event in state.active_events.items():
            if event.is_expired(state.tick_number):
                expired_ids.append(eid)
                continue

            offset = state.tick_number - event.created_at_tick
            if offset == 0:
                continue  # tick-0 handled by the action handler

            strength = event.current_strength(state.tick_number)

            # Resolve target civilization IDs
            target_civ_ids: list[str] = []
            if event.target_civilization_id is not None:
                cid = str(event.target_civilization_id)
                if cid in state.civilizations:
                    target_civ_ids.append(cid)
                else:
                    expired_ids.append(eid)  # target gone; expire the event
                    continue
            elif event.target_mortal_id is not None:
                mortal = state.mortals.get(str(event.target_mortal_id))
                if mortal and mortal.civilization_id:
                    cid = str(mortal.civilization_id)
                    if cid in state.civilizations:
                        target_civ_ids.append(cid)
            elif event.target_world_id is not None:
                wid = str(event.target_world_id)
                for cid, civ in state.civilizations.items():
                    if str(civ.origin_location_id) == wid:
                        target_civ_ids.append(cid)
            else:
                target_civ_ids = list(state.civilizations.keys())

            # Emit belief-shift mutations
            for cid in target_civ_ids:
                civ_obj = state.civilizations[cid]
                for dv in event.domain_vectors:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.BELIEF_SHIFT,
                        target_id=civ_obj.id,
                        field="dominant_beliefs",
                        delta=dv.direction * strength * event.domain_shift_rate,
                        new_value=dv.domain_tag,
                        note=f"Event echo ({event.event_type}, offset {offset})",
                    ))
                if event.divine_awareness_rate > 0.0:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.CIVILIZATION_STAT,
                        target_id=civ_obj.id,
                        field="divine_awareness",
                        delta=event.divine_awareness_rate * strength,
                        note=f"Event echo ({event.event_type}) awareness",
                    ))

            # Populate attention triggers for Phase 4
            if event.attention_per_tick > 0.0:
                trigger = AttentionTrigger(
                    trigger_type=f"event_{event.event_type}",
                    delta=event.attention_per_tick * strength,
                    timestamp=float(state.tick_number),
                    note=f"{event.event_type} echo (offset {offset})",
                )
                for lid in state.luminaries:
                    state.pending_attention_triggers.setdefault(lid, []).append(trigger)

        for eid in expired_ids:
            state.active_events.pop(eid, None)

        return mutations

    def _resolve_proxius_agents(
        self,
        state: SimulationState,
        phase_rng: random.Random,
    ) -> list[StateMutation]:
        """
        Phase 2.5 — autonomous Proxius agent actions.
        Each active Proxius with an active_goal chooses and executes one
        action per tick, weighted by dedication (alignment × leeway).
        Generates StateMutations directly; does not go through ActionInstance machinery.
        """
        mutations: list[StateMutation] = []

        for mortal in state.mortals.values():
            if mortal.role != MortalRole.PROXIUS:
                continue
            if mortal.status != MortalStatus.ACTIVE:
                continue
            goal = mortal.active_goal
            if goal is None:
                continue

            # Dedication: high alignment + low latitude → near-certain, frequent action
            dedication = mortal.alignment * (1.0 - goal.latitude * 0.3)
            dedication = max(0.0, min(1.0, dedication))

            # Frequency gate — probabilistic skip
            if phase_rng.random() > dedication:
                goal.last_action = AgentActionChoice.NOTHING
                goal.last_action_tick = state.tick_number
                goal.consecutive_promote_count = 0
                goal.effectiveness_bonus = max(0.0, goal.effectiveness_bonus - 0.05)
                continue

            # Action weight table
            promote_w    = 0.60
            take_stock_w = 0.10
            report_w     = 0.10 + (1.0 - goal.latitude) * 0.15
            petition_w   = 0.05 if not goal.petition_pending else 0.0
            nothing_w    = max(0.0, 0.15 - dedication * 0.10)

            weights = [promote_w, take_stock_w, report_w, petition_w, nothing_w]
            choices = [
                AgentActionChoice.PROMOTE_DOMAIN,
                AgentActionChoice.TAKE_STOCK,
                AgentActionChoice.REPORT_TO_DEMIURGE,
                AgentActionChoice.PETITION_FOR_RELIEF,
                AgentActionChoice.NOTHING,
            ]
            chosen = phase_rng.choices(choices, weights=weights, k=1)[0]
            goal.last_action = chosen
            goal.last_action_tick = state.tick_number

            if chosen == AgentActionChoice.PROMOTE_DOMAIN and goal.domain_vectors:
                # Belief shift per domain vector, boosted by streak and Proxius's own beliefs
                goal.consecutive_promote_count += 1
                goal.effectiveness_bonus = min(
                    0.30,
                    goal.consecutive_promote_count * 0.05,
                )
                base_rate = 0.06
                target_civ_ids: list[str] = []
                if goal.target_civilization_id:
                    cid = str(goal.target_civilization_id)
                    if cid in state.civilizations:
                        target_civ_ids.append(cid)
                else:
                    loc_id = str(goal.target_location_id)
                    target_civ_ids = [
                        cid for cid, civ in state.civilizations.items()
                        if str(civ.origin_location_id) == loc_id
                    ]

                for cid in target_civ_ids:
                    for dv in goal.domain_vectors:
                        # Proxius's own belief_tags augment aligned vectors
                        belief_affinity = mortal.belief_tags.get(dv.domain_tag, 0.0)
                        rate = base_rate * (1.0 + goal.effectiveness_bonus) + belief_affinity * 0.02
                        mutations.append(StateMutation(
                            mutation_type=MutationType.BELIEF_SHIFT,
                            target_id=UUID(cid),
                            field="dominant_beliefs",
                            delta=dv.direction * rate,
                            new_value=dv.domain_tag,
                            note=f"Proxius {mortal.name} promoting {dv.domain_tag} (streak {goal.consecutive_promote_count})",
                        ))
                # Passive proxius footprint for the work done
                mutations.append(StateMutation(
                    mutation_type=MutationType.FOOTPRINT_CHANGE,
                    target_id=state.demiurge.id,
                    field="proxius_activity",
                    delta=0.02,
                    note=f"Proxius {mortal.name} promoting domain",
                ))

            elif chosen == AgentActionChoice.TAKE_STOCK:
                goal.consecutive_promote_count = 0
                goal.effectiveness_bonus = max(0.0, goal.effectiveness_bonus - 0.02)
                mutations.append(StateMutation(
                    mutation_type=MutationType.MORTAL_ALIGNMENT,
                    target_id=mortal.id,
                    field="alignment",
                    delta=0.01,
                    note=f"{mortal.name} taking stock of their work",
                ))

            elif chosen == AgentActionChoice.REPORT_TO_DEMIURGE:
                tick = state.tick_number + 1  # tick_number increments after Phase 2.5
                streak = goal.consecutive_promote_count
                ticks_active = state.tick_number + 1 - goal.started_at_tick
                imago_short = goal.imago_node_id.split(":")[-1] if goal.imago_node_id else "directive"
                if streak >= 3:
                    progress = f"momentum is building — {streak} consecutive pushes of [{imago_short}]"
                elif streak > 0:
                    progress = f"work on [{imago_short}] is underway, {streak} push(es) this stretch"
                elif goal.effectiveness_bonus > 0:
                    progress = f"[{imago_short}] work has stalled momentarily; prior gains hold"
                else:
                    progress = f"no meaningful progress on [{imago_short}] yet"
                entry = (
                    f"[Tick {tick}] {mortal.name} reports after {ticks_active} tick(s): "
                    + progress
                    + (f"; effectiveness at +{goal.effectiveness_bonus:.0%}" if goal.effectiveness_bonus > 0 else "")
                    + "."
                )
                goal.report_log = (goal.report_log + [entry])[-5:]

            elif chosen == AgentActionChoice.PETITION_FOR_RELIEF:
                goal.petition_pending = True
                goal.consecutive_promote_count = 0
                goal.effectiveness_bonus = 0.0
                tick = state.tick_number + 1
                ticks_active = state.tick_number + 1 - goal.started_at_tick
                imago_short = goal.imago_node_id.split(":")[-1] if goal.imago_node_id else "directive"
                entry = (
                    f"[Tick {tick}] {mortal.name} petitions after {ticks_active} tick(s): "
                    f"[{imago_short}] directive yields diminishing returns. Requesting new orders."
                )
                goal.report_log = (goal.report_log + [entry])[-5:]
                mutations.append(StateMutation(
                    mutation_type=MutationType.MORTAL_ALIGNMENT,
                    target_id=mortal.id,
                    field="alignment",
                    delta=-0.02,
                    note=f"{mortal.name} frustrated with current directive",
                ))

            elif chosen == AgentActionChoice.NOTHING:
                goal.consecutive_promote_count = 0
                goal.effectiveness_bonus = max(0.0, goal.effectiveness_bonus - 0.05)

        return mutations

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
            return civ.origin_location_id if civ else None
        elif instance.target_type == TargetType.MORTAL:
            mortal = state.mortals.get(str(instance.target_id))
            return mortal.current_location if mortal else None
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
                elif tid in state.locations:
                    # e.g. field = "local_footprint.overt_miracles"
                    parts = m.field.split(".")
                    if len(parts) == 2:
                        obj = getattr(state.locations[tid], parts[0])
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
                elif tid in state.locations:
                    loc = state.locations[tid]
                    if isinstance(loc, SignificantLocation):
                        domain = loc.domain_expression
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
                    mortal.visibility = 1.0
                    mortal.pinned = True
                    if mortal.id not in state.demiurge.proxius_ids:
                        state.demiurge.proxius_ids.append(mortal.id)
                    loc_id_str = str(mortal.current_location)
                    loc = state.locations.get(loc_id_str)
                    if loc and isinstance(loc, SignificantLocation):
                        if mortal.id not in loc.proxius_ids:
                            loc.proxius_ids.append(mortal.id)

            elif m.mutation_type == MutationType.PROXIUS_DISMISSED:
                if tid in state.mortals:
                    mortal = state.mortals[tid]
                    mortal.role = MortalRole.OTHER
                    mortal.pinned = False
                    if mortal.id in state.demiurge.proxius_ids:
                        state.demiurge.proxius_ids.remove(mortal.id)
                    loc_id_str = str(mortal.current_location)
                    loc = state.locations.get(loc_id_str)
                    if loc and isinstance(loc, SignificantLocation):
                        if mortal.id in loc.proxius_ids:
                            loc.proxius_ids.remove(mortal.id)

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

            elif m.mutation_type == MutationType.ENTITY_VISIBILITY:
                entity = (
                    state.locations.get(tid)
                    or state.civilizations.get(tid)
                    or state.species.get(tid)
                )
                if entity is not None:
                    if m.new_value is not None:
                        entity.visibility = max(0.0, min(1.0, float(m.new_value)))
                    elif m.delta is not None:
                        entity.visibility = max(0.0, min(1.0, entity.visibility + m.delta))

            elif m.mutation_type == MutationType.WORLD_CONDITION:
                if tid in state.locations and m.new_value:
                    loc = state.locations[tid]
                    if isinstance(loc, SignificantLocation):
                        loc.condition = LocCondition(m.new_value)

            elif m.mutation_type == MutationType.ENTITY_DESTROYED:
                if tid in state.civilizations:
                    civ = state.civilizations.pop(tid)
                    loc_id = str(civ.origin_location_id) if civ.origin_location_id else None
                    world = state.worlds.get(loc_id) if loc_id else None
                    if world and civ.id in world.civilization_ids:
                        world.civilization_ids.remove(civ.id)
                elif tid in state.mortals:
                    state.mortals[tid].status = MortalStatus.DECEASED

            elif m.mutation_type == MutationType.EXILED_TO_UNDERREAL:
                if tid in state.civilizations:
                    civ = state.civilizations.pop(tid)
                    loc_id = str(civ.origin_location_id) if civ.origin_location_id else None
                    world = state.worlds.get(loc_id) if loc_id else None
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
                    world = state.worlds.get(str(mortal.current_location))
                    if world:
                        world.domain_expression["domain:underreal_trace"] = min(
                            1.0,
                            world.domain_expression.get("domain:underreal_trace", 0.0) + 0.2,
                        )
                elif tid in state.locations:
                    loc = state.locations[tid]
                    if isinstance(loc, SignificantLocation):
                        loc.condition = LocCondition.BARREN
                        loc.domain_expression = {"domain:underreal_trace": 1.0}

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
                    if tid and tid in state.locations:
                        loc = state.locations[tid]
                        if isinstance(loc, SignificantLocation) and sp.id not in loc.species_ids:
                            loc.species_ids.append(sp.id)

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

            elif m.mutation_type == MutationType.AFFILIATED_DOMAIN_CHANGE:
                val = str(m.new_value) if m.new_value else ""
                if "→" in val:
                    old_tag, new_tag = val.split("→", 1)
                    if old_tag in state.demiurge.affiliated_domains:
                        state.demiurge.affiliated_domains.remove(old_tag)
                    if new_tag not in state.demiurge.affiliated_domains:
                        state.demiurge.affiliated_domains.append(new_tag)

            elif m.mutation_type == MutationType.EVENT_EMITTED:
                if isinstance(m.new_value, Event):
                    eid = str(m.new_value.id)
                    if eid not in state.active_events:
                        state.active_events[eid] = m.new_value

            elif m.mutation_type == MutationType.PROXIUS_GOAL_SET:
                if tid in state.mortals and isinstance(m.new_value, ProxiusGoal):
                    state.mortals[tid].active_goal = m.new_value

            elif m.mutation_type == MutationType.PROXIUS_GOAL_CLEARED:
                if tid in state.mortals:
                    state.mortals[tid].active_goal = None

        return state
