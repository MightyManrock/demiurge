#!/usr/bin/env python3
"""
test_harness.py
Minimal CLI playtester for the Demiurge simulation.
Assumes all model/engine code is importable from sim_core.py.
"""

from __future__ import annotations
import json
import os
import sys
import textwrap
from datetime import datetime
from pathlib import Path
from uuid import uuid4, UUID

# ── All model imports ──────────────────────────────────────────────────────
from onto_core import (
    Power, Domain, Temperament, Disposition, Constraint,
    Luminary, Pantheon,
    # Demiurge
    FootprintProfile, Demiurge,
)
from universe_core import (
    FootprintTolerances, ProxiiPolicy, UniverseRules,
    Galaxy, System, CosmicCoordinates, StarType,
    WorldCondition, WorldFootprint, World,
    CivilizationScale, CivilizationHealth, Civilization,
    MortalRole, MortalStatus, NotableMortal,
    Universe,
)
from action_core import (
    EssenceStockpile,
    # Actions
    ActionCategory, TargetType, ActionDefinition,
    ActionReliability, FootprintCost,
    build_action_library, ActionInstance, ActionResult,
    # Intent types
    WhisperIntent, OmenIntent, ProbabilityNudgeIntent,
    DevelopmentIntent, ProxiusDirectiveIntent,
    LuminaryPetitionIntent, EssenceHarvestIntent,
    SalvageIntent, DomainVector,
    # Mutations
    StateMutation, MutationType, ActionOutcome,
)
from eval_core import (
    EvaluationEngine, UniverseDomainProfile,
    LuminaryEvaluation, DispositionDelta,
    FootprintAssessment, EssenceSuspicion,
)
from tick_logic import (
    TickConfig, SimulationState, CivilizationMomentum,
    TickLoop, TickResult, TerminalConditionType,
)


# ─────────────────────────────────────────
# SCENARIO FACTORY
# Builds a concrete starting SimulationState.
# Tweak this to test different scenarios.
# ─────────────────────────────────────────

def build_scenario_default() -> SimulationState:
    """
    Scenario: 'The Warden's Compact'

    You are Demiurge of a young universe containing one inhabited world.
    Your two liege Luminaries have contradictory temperaments:
      - Cassiel, Luminary of Order and Silence — patient, demands subtlety
      - Vrath, Luminary of Conflict and Change — wrathful, demands results fast

    The Pantheon expects subtlety. Vrath privately does not care,
    but expects civilizational Domain alignment toward conflict within
    a short window. The tension is immediate.
    """

    # ── Powers ──────────────────────────────────────
    p_order    = Power(name="Order",    description="The force of structure, law, silence.")
    p_conflict = Power(name="Conflict", description="The force of struggle, change, becoming.")
    p_silence  = Power(name="Silence",  description="Absence as presence; the space between.")
    p_change   = Power(name="Change",   description="Flux, transformation, impermanence.")

    # ── Domains ─────────────────────────────────────
    d_order = Domain(
        name="Order",
        description="Hierarchy, law, institutional permanence.",
        source_powers=[p_order.id],
        tags=["domain:order", "domain:law", "domain:hierarchy"],
    )
    d_silence = Domain(
        name="Silence",
        description="Restraint, hidden influence, the unseen hand.",
        source_powers=[p_silence.id],
        tags=["domain:silence", "domain:restraint", "domain:subtlety"],
    )
    d_conflict = Domain(
        name="Conflict",
        description="War, competition, the crucible of strength.",
        source_powers=[p_conflict.id],
        tags=["domain:conflict", "domain:war", "domain:struggle"],
    )
    d_change = Domain(
        name="Change",
        description="Revolution, dissolution, new forms from old.",
        source_powers=[p_change.id],
        tags=["domain:change", "domain:revolution", "domain:flux"],
    )

    domains = {
        str(d.id): d
        for d in [d_order, d_silence, d_conflict, d_change]
    }

    # ── Luminaries ───────────────────────────────────
    cassiel = Luminary(
        name="Cassiel",
        domains=[d_order.id, d_silence.id],
        temperament=Temperament.PATIENT,
        disposition=Disposition(results=0.1, methods=0.2),
        constraints=[
            Constraint(
                name="Subtlety Mandate",
                description="Overt miracles must remain minimal.",
                domain_source=d_silence.id,
                enforcement_weight=0.85,
            ),
            Constraint(
                name="Proxius Restraint",
                description="No more than one Proxius per world.",
                domain_source=d_order.id,
                enforcement_weight=0.6,
            ),
        ],
        speech_tags=[
            "domain:order", "domain:silence",
            "temperament:patient", "status:liege",
        ],
    )

    vrath = Luminary(
        name="Vrath",
        domains=[d_conflict.id, d_change.id],
        temperament=Temperament.WRATHFUL,
        disposition=Disposition(results=0.0, methods=-0.1),
        constraints=[
            Constraint(
                name="Results Demand",
                description=(
                    "The universe must show strong conflict/change domain "
                    "expression within a reasonable span."
                ),
                domain_source=d_conflict.id,
                enforcement_weight=0.9,
            ),
        ],
        speech_tags=[
            "domain:conflict", "domain:change",
            "temperament:wrathful", "status:liege",
        ],
    )

    luminaries = {str(l.id): l for l in [cassiel, vrath]}

    # ── Pantheon ─────────────────────────────────────
    pantheon = Pantheon(
        name="The Warden's Compact",
        luminary_ids=[cassiel.id, vrath.id],
        collective_constraints=[
            Constraint(
                name="Collective Subtlety Expectation",
                description="Neither Luminary sanctions flagrant divine display.",
                enforcement_weight=0.5,
            ),
        ],
    )

    # ── Universe Rules ────────────────────────────────
    rules = UniverseRules(
        footprint_tolerances=FootprintTolerances(
            overt_miracles=0.25,
            subtle_influence=0.75,
            proxius_activity=0.55,
            direct_creation=0.20,
        ),
        proxii_policy=ProxiiPolicy(max_per_world=1, tolerance_for_excess=0.25),
        mortals_can_perceive_divinity=True,
        active_shaping_expected=True,
        notes="Cassiel expects patience; Vrath expects results. They do not discuss this.",
    )

    # ── Spatial hierarchy ─────────────────────────────
    galaxy = Galaxy(
        name="The Nascent Coil",
        coordinates=CosmicCoordinates(x=0.0, y=0.0, z=0.0),
    )
    system = System(
        name="Ardent System",
        galaxy_id=galaxy.id,
        star_type=StarType.MAIN_SEQUENCE,
    )
    world = World(
        name="Neran",
        system_id=system.id,
        condition=WorldCondition.STABLE,
        domain_expression=["domain:order"],
        age=120.0,
    )

    galaxy.system_ids.append(system.id)
    system.world_ids.append(world.id)

    # ── Civilization ──────────────────────────────────
    civ = Civilization(
        name="The Neran Confederacy",
        world_id=world.id,
        scale=CivilizationScale.CONTINENTAL,
        health=CivilizationHealth(
            stability=0.6,
            prosperity=0.5,
            cohesion=0.55,
        ),
        dominant_beliefs=["domain:order", "domain:law"],
        theistic=True,
        divine_awareness=0.25,
        age=80.0,
    )
    world.civilization_ids.append(civ.id)

    # ── Notable Mortal (candidate for Proxius) ────────
    mortal = NotableMortal(
        name="Senna Vaur",
        world_id=world.id,
        civilization_id=civ.id,
        role=MortalRole.OTHER,
        status=MortalStatus.ACTIVE,
        personal_tags=["domain:order", "ambitious", "pragmatic"],
        alignment=0.75,
        age=34.0,
    )
    civ.notable_mortal_ids.append(mortal.id)

    # ── Demiurge ─────────────────────────────────────
    demiurge = Demiurge(
        name="The Unnamed",
        liege_luminary_ids=[cassiel.id, vrath.id],
        granted_domains=[d_order.id, d_conflict.id],
        footprint=FootprintProfile(),
    )

    essence = EssenceStockpile(
        actual=0.0,
        apparent=0.0,
        concealment_integrity=1.0,
    )

    # ── Universe ──────────────────────────────────────
    universe = Universe(
        name="The Neran Universe",
        demiurge_id=demiurge.id,
        pantheon_id=pantheon.id,
        rules=rules,
        galaxy_ids=[galaxy.id],
        current_age=120.0,
    )

    return SimulationState(
        universe=universe,
        demiurge=demiurge,
        essence=essence,
        pantheon=pantheon,
        luminaries=luminaries,
        domains=domains,
        galaxies={str(galaxy.id): galaxy},
        systems={str(system.id): system},
        worlds={str(world.id): world},
        civilizations={str(civ.id): civ},
        mortals={str(mortal.id): mortal},
        civ_momentum={
            str(civ.id): CivilizationMomentum(
                civilization_id=civ.id,
                stability_delta=0.1,
                prosperity_delta=0.05,
                cohesion_delta=-0.05,
                # Slight internal fracturing despite surface stability
            )
        },
        luminary_attention={
            str(cassiel.id): 0.15,
            str(vrath.id):   0.30,
            # Vrath is already watching
        },
        ticks_since_evaluation={
            str(cassiel.id): 0.0,
            str(vrath.id):   0.0,
        },
        config=TickConfig(
            tick_duration=5.0,
            evaluation_interval=8.0,
        ),
    )


# ─────────────────────────────────────────
# DISPLAY
# Compact state summaries for the terminal.
# ─────────────────────────────────────────

SEP  = "─" * 60
SEP2 = "═" * 60

def display_state(state: SimulationState) -> str:
    lines = [
        SEP2,
        f"  UNIVERSE: {state.universe.name}",
        f"  Age: {state.universe.current_age:.1f}  |  Tick: {state.tick_number}",
        SEP2,
    ]

    # ── Demiurge ──────────────────────────────────────
    fp = state.demiurge.footprint
    es = state.essence
    lines += [
        "DEMIURGE",
        f"  Footprint — overt:{fp.overt_miracles:.2f}  "
        f"subtle:{fp.subtle_influence:.2f}  "
        f"proxii:{fp.proxius_activity:.2f}  "
        f"creation:{fp.direct_creation:.2f}",
        f"  Essence   — actual:{es.actual:.2f}  "
        f"apparent:{es.apparent:.2f}  "
        f"concealment:{es.concealment_integrity:.2f}",
        SEP,
    ]

    # ── Luminaries ────────────────────────────────────
    lines.append("LUMINARIES")
    for lid, lum in state.luminaries.items():
        att = state.luminary_attention.get(lid, 0.0)
        d   = lum.disposition
        lines.append(
            f"  {lum.name:12s}  "
            f"results:{d.results:+.2f}  methods:{d.methods:+.2f}  "
            f"attention:{att:.2f}  [{lum.temperament.value}]"
        )
    lines.append(SEP)

    # ── Worlds ────────────────────────────────────────
    lines.append("WORLDS")
    for wid, world in state.worlds.items():
        lines.append(
            f"  {world.name}  [{world.condition.value}]  "
            f"beliefs: {', '.join(world.domain_expression) or 'none'}"
        )
        for cid in world.civilization_ids:
            civ = state.civilizations.get(str(cid))
            if civ:
                h = civ.health
                lines.append(
                    f"    └─ {civ.name} [{civ.scale.value}]  "
                    f"stab:{h.stability:.2f} pros:{h.prosperity:.2f} "
                    f"coh:{h.cohesion:.2f}"
                )
                lines.append(
                    f"       beliefs: {', '.join(civ.dominant_beliefs) or 'none'}"
                )
    lines.append(SEP)

    # ── Mortals of note ───────────────────────────────
    lines.append("NOTABLE MORTALS")
    for mid, mortal in state.mortals.items():
        if mortal.status == MortalStatus.DECEASED:
            continue
        role_str = mortal.role.value.upper() if mortal.role != MortalRole.OTHER else "mortal"
        lines.append(
            f"  {mortal.name:16s} [{role_str}]  "
            f"alignment:{mortal.alignment:.2f}  "
            f"tags: {', '.join(mortal.personal_tags)}"
        )
    lines.append(SEP2)

    return "\n".join(lines)


def display_tick_result(result: TickResult) -> str:
    lines = [
        "",
        f"  TICK {result.tick_number} RESULT  "
        f"(age {result.universe_age_before:.1f} → {result.universe_age_after:.1f})",
        SEP,
    ]

    # Passive narrative events
    if result.passive_result.narrative_events:
        lines.append("WORLD EVENTS")
        for ev in result.passive_result.narrative_events:
            lines.append(f"  • {ev}")
        lines.append("")

    # Action outcomes
    if result.action_result.entries:
        lines.append("YOUR ACTIONS")
        for entry in result.action_result.entries:
            lines.append(
                f"  [{entry.outcome.value.upper()}] {entry.narrative}"
            )
        lines.append("")

    # Disposition changes
    if result.disposition_changes:
        lines.append("LUMINARY REACTIONS")
        for lid, (r, m) in result.disposition_changes.items():
            # Find luminary name from evaluations
            ev = next(
                (e for e in result.evaluations if str(e.luminary_id) == lid),
                None
            )
            name = ev.summary_note.split(":")[0] if ev else lid[:8]
            lines.append(
                f"  {name:12s}  results→{r:+.2f}  methods→{m:+.2f}"
            )
        lines.append("")

    # Dialogue triggers
    if result.dialogue_triggers:
        lines.append("DIVINE COMMUNICATIONS")
        for trig in result.dialogue_triggers:
            lines.append(
                f"  [{trig.trigger_type.value.upper()}]  "
                f"urgency:{trig.urgency:.1f}  "
                f"re: {trig.subject_ref or 'general'}"
            )
        lines.append("")

    # Terminal condition
    if result.terminal.triggered:
        lines += [
            SEP2,
            f"  SCENARIO END: {result.terminal.condition.value.upper()}",
            f"  {result.terminal.note}",
            SEP2,
        ]

    return "\n".join(lines)


# ─────────────────────────────────────────
# ACTION MENU
# Let the playtester browse and queue actions.
# ─────────────────────────────────────────

def build_intent_interactively(
    action_key: str,
    defn: ActionDefinition,
    state: SimulationState,
) -> tuple[ActionInstance, str] | None:
    """
    Prompt the playtester for intent fields appropriate
    to the chosen action. Returns (ActionInstance, display_summary)
    or None if they cancel.
    """
    print(f"\n  Action: {defn.name}")
    print(f"  {defn.description}")
    print(f"  Footprint cost: {defn.footprint_cost.total():.2f} total")
    if defn.essence_cost != 0.0:
        verb = "yields" if defn.essence_cost < 0 else "costs"
        print(f"  Essence: {verb} {abs(defn.essence_cost):.2f}")
    print()

    # ── Target selection ──────────────────────────────
    target_id = None
    target_type = defn.valid_targets[0]  # Default; refined below

    if TargetType.MORTAL in defn.valid_targets and state.mortals:
        mortals = list(state.mortals.items())
        print("  Select target mortal:")
        for i, (mid, m) in enumerate(mortals):
            print(f"    {i+1}. {m.name} [{m.role.value}]  alignment:{m.alignment:.2f}")
        print("    0. Cancel")
        choice = _prompt_int("  > ", 0, len(mortals))
        if choice == 0:
            return None
        target_id = UUID(mortals[choice - 1][0])
        target_type = TargetType.MORTAL

    elif TargetType.CIVILIZATION in defn.valid_targets and state.civilizations:
        civs = list(state.civilizations.items())
        print("  Select target civilization:")
        for i, (cid, c) in enumerate(civs):
            print(f"    {i+1}. {c.name}")
        print("    0. Cancel")
        choice = _prompt_int("  > ", 0, len(civs))
        if choice == 0:
            return None
        target_id = UUID(civs[choice - 1][0])
        target_type = TargetType.CIVILIZATION

    elif TargetType.LUMINARY in defn.valid_targets and state.luminaries:
        lums = list(state.luminaries.items())
        print("  Select target Luminary:")
        for i, (lid, l) in enumerate(lums):
            print(f"    {i+1}. {l.name}")
        print("    0. Cancel")
        choice = _prompt_int("  > ", 0, len(lums))
        if choice == 0:
            return None
        target_id = UUID(lums[choice - 1][0])
        target_type = TargetType.LUMINARY

    elif TargetType.UNDERREAL in defn.valid_targets:
        target_type = TargetType.UNDERREAL
        target_id = None

    elif TargetType.WORLD in defn.valid_targets and state.worlds:
        worlds = list(state.worlds.items())
        print("  Select target world:")
        for i, (wid, w) in enumerate(worlds):
            print(f"    {i+1}. {w.name}")
        print("    0. Cancel")
        choice = _prompt_int("  > ", 0, len(worlds))
        if choice == 0:
            return None
        target_id = UUID(worlds[choice - 1][0])
        target_type = TargetType.WORLD

    # ── Proxius selection for directed actions ────────
    proxius_id = None
    if defn.requires_proxius:
        proxii = [
            (mid, m) for mid, m in state.mortals.items()
            if m.role == MortalRole.PROXY and m.status == MortalStatus.ACTIVE
        ]
        if not proxii:
            print("  No active Proxii available for this action.")
            return None
        print("  Select Proxius to act through:")
        for i, (mid, m) in enumerate(proxii):
            print(f"    {i+1}. {m.name}  alignment:{m.alignment:.2f}")
        choice = _prompt_int("  > ", 1, len(proxii))
        proxius_id = UUID(proxii[choice - 1][0])

    # ── Intent construction ───────────────────────────
    intent = _build_intent(action_key, defn, target_id, state)

    summary = f"{defn.name}"
    if target_id:
        summary += f" → {_name_for_id(target_id, state)}"

    instance = ActionInstance(
        action_definition_id=defn.id,
        target_type=target_type,
        target_id=target_id,
        timestamp=state.universe.current_age,
        demiurge_id=state.demiurge.id,
        proxius_id=proxius_id,
        intent=intent,
    )
    return instance, summary


def _build_intent(
    action_key: str,
    defn: ActionDefinition,
    target_id,
    state: SimulationState,
):
    """Prompt for intent fields based on action category."""
    cat = defn.category

    if cat == ActionCategory.SUBTLE_INFLUENCE:
        if action_key in ("whisper", "shape_dream"):
            concept = input("  Concept to plant: ").strip() or "You could shape the future."
            dv = _prompt_domain_vector()
            return WhisperIntent(
                concept=concept,
                domain_vectors=[dv] if dv else [],
                framing=_prompt_framing(),
            )
        elif action_key == "nudge_probability":
            event = input("  Event to nudge: ").strip() or "Upcoming succession conflict"
            outcome = input("  Desired outcome: ").strip() or "The reformist faction prevails"
            dv = _prompt_domain_vector()
            return ProbabilityNudgeIntent(
                event_description=event,
                desired_outcome=outcome,
                domain_vectors=[dv] if dv else [],
            )
        elif action_key == "accelerate_development":
            aspect = input("  Which aspect to develop: ").strip() or "military doctrine"
            dv = _prompt_domain_vector()
            return DevelopmentIntent(
                domain_vectors=[dv] if dv else [],
                target_aspect=aspect,
            )

    elif cat == ActionCategory.PROXIUS_DIRECTION:
        if action_key == "issue_directive":
            goal = input("  Directive goal: ").strip() or "Strengthen the reformist faction"
            dv = _prompt_domain_vector()
            latitude = _prompt_float("  Latitude (0.0 strict – 1.0 open): ", 0.0, 1.0, 0.5)
            return ProxiusDirectiveIntent(
                goal_statement=goal,
                domain_vectors=[dv] if dv else [],
                latitude=latitude,
            )

    elif cat == ActionCategory.UNDERREAL:
        if action_key == "harvest_essence":
            concept_type = input(
                "  Target concept type (enter to skip): "
            ).strip() or None
            concealment = _prompt_float(
                "  Concealment priority (0.0 fast/risky – 1.0 slow/safe): ",
                0.0, 1.0, 0.7
            )
            return EssenceHarvestIntent(
                target_concept_type=concept_type,
                concealment_priority=concealment,
            )
        elif action_key == "salvage_concept":
            desired = input("  What are you hoping to find: ").strip()
            worlds = list(state.worlds.items())
            print("  Target world for salvage:")
            for i, (wid, w) in enumerate(worlds):
                print(f"    {i+1}. {w.name}")
            choice = _prompt_int("  > ", 1, len(worlds))
            world_id = UUID(worlds[choice-1][0])
            dv = _prompt_domain_vector()
            return SalvageIntent(
                desired_concept=desired,
                target_world_id=world_id,
                domain_vectors=[dv] if dv else [],
            )

    elif cat == ActionCategory.LUMINARY_RELATIONS:
        subject = input("  Subject of communication: ").strip() or "Current universe state"
        position = input("  Your position / what you want: ").strip() or "Continued patience"
        tone = input("  Tone (deferential/confident/urgent/firm): ").strip() or "deferential"
        return LuminaryPetitionIntent(
            subject=subject,
            your_position=position,
            tone=tone,
        )

    # No structured intent needed (scry, appoint_proxy, etc.)
    return None


def _prompt_domain_vector() -> DomainVector | None:
    tag = input(
        "  Domain tag to push (e.g. domain:conflict, blank to skip): "
    ).strip()
    if not tag:
        return None
    direction = _prompt_float("  Direction (-1.0 away → +1.0 toward): ", -1.0, 1.0, 0.5)
    return DomainVector(domain_tag=tag, direction=direction)


def _prompt_framing():
    from action_core import Framing
    options = [f.value for f in Framing]
    print(f"  Framing: {', '.join(options)}")
    choice = input("  > ").strip().lower()
    return Framing(choice) if choice in options else Framing.INSPIRATIONAL


def _prompt_int(prompt: str, lo: int, hi: int) -> int:
    while True:
        try:
            val = int(input(prompt))
            if lo <= val <= hi:
                return val
        except ValueError:
            pass
        print(f"  Enter a number between {lo} and {hi}.")


def _prompt_float(prompt: str, lo: float, hi: float, default: float) -> float:
    raw = input(f"{prompt}[{default}] ").strip()
    if not raw:
        return default
    try:
        val = float(raw)
        return max(lo, min(hi, val))
    except ValueError:
        return default


def _name_for_id(uid: UUID, state: SimulationState) -> str:
    sid = str(uid)
    for d in [state.mortals, state.civilizations, state.worlds,
              state.luminaries, state.galaxies]:
        if sid in d:
            obj = d[sid]
            return getattr(obj, "name", sid[:8])
    return sid[:8]


# ─────────────────────────────────────────
# SESSION LOG
# ─────────────────────────────────────────

class SessionLog:
    def __init__(self, path: Path):
        self.path = path
        self.entries: list[str] = []
        self.path.write_text(
            f"DEMIURGE SESSION LOG\n"
            f"Started: {datetime.now().isoformat()}\n"
            f"{'='*60}\n\n"
        )

    def write(self, text: str):
        self.entries.append(text)
        with self.path.open("a") as f:
            f.write(text + "\n")

    def write_state(self, state: SimulationState):
        self.write(display_state(state))

    def write_tick(self, result: TickResult):
        self.write(display_tick_result(result))

    def write_action(self, summary: str):
        self.write(f"  > QUEUED: {summary}")

    def finalize(self, state: SimulationState, result: TickResult | None):
        self.write("\n" + "="*60)
        self.write("SESSION END")
        self.write(f"Final age: {state.universe.current_age:.1f}")
        self.write(f"Final tick: {state.tick_number}")
        if result and result.terminal.triggered:
            self.write(f"Outcome: {result.terminal.condition.value}")
        self.write(f"Ended: {datetime.now().isoformat()}")


# ─────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────

def main():
    print(SEP2)
    print("  DEMIURGE — TEST HARNESS")
    print(SEP2)

    log_path = Path(f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    log = SessionLog(log_path)
    print(f"  Logging to: {log_path}\n")

    state = build_scenario_default()
    loop  = TickLoop()
    library = build_action_library()
    last_result: TickResult | None = None

    # Map action keys to definitions with a stable index
    action_index: list[tuple[str, ActionDefinition]] = list(library.items())

    print(display_state(state))
    log.write_state(state)

    while True:
        print()
        print("  ACTIONS")
        print("  ────────────────────────────────────────────────")
        print("  [A] Browse and queue actions")
        print("  [T] Advance time (execute queued actions + tick)")
        print("  [S] Show current state")
        print("  [Q] Quit")
        if state.action_queue:
            print(f"\n  Queued: {len(state.action_queue)} action(s) pending")
        print()

        cmd = input("  > ").strip().upper()

        if cmd == "Q":
            log.finalize(state, last_result)
            print(f"\n  Session saved to {log_path}")
            break

        elif cmd == "S":
            out = display_state(state)
            print(out)
            log.write(out)

        elif cmd == "A":
            _action_browser(state, library, action_index, log)

        elif cmd == "T":
            print("\n  Advancing time...")
            state, result = loop.advance(state)
            last_result = result
            out = display_tick_result(result)
            print(out)
            log.write_tick(result)

            if result.terminal.triggered:
                log.finalize(state, result)
                print(f"\n  Session saved to {log_path}")
                break
        else:
            print("  Unknown command.")


def _action_browser(
    state: SimulationState,
    library: dict,
    action_index: list,
    log: SessionLog,
):
    # Group by category for readability
    categories: dict[ActionCategory, list] = {}
    for key, defn in action_index:
        categories.setdefault(defn.category, []).append((key, defn))

    print("\n  ACTION CATEGORIES")
    cat_list = list(categories.items())
    for i, (cat, _) in enumerate(cat_list):
        print(f"    {i+1}. {cat.value.replace('_',' ').title()}")
    print("    0. Back")

    cat_choice = _prompt_int("  > ", 0, len(cat_list))
    if cat_choice == 0:
        return

    cat, actions = cat_list[cat_choice - 1]
    print(f"\n  {cat.value.upper()}")
    for i, (key, defn) in enumerate(actions):
        fp_total = defn.footprint_cost.total()
        essence_str = ""
        if defn.essence_cost != 0:
            verb = "↑" if defn.essence_cost < 0 else "↓"
            essence_str = f"  Ess{verb}{abs(defn.essence_cost):.1f}"
        print(
            f"    {i+1}. {defn.name:35s}"
            f"  FP:{fp_total:.2f}{essence_str}"
            f"  [{defn.reliability.value}]"
        )
    print("    0. Back")

    action_choice = _prompt_int("  > ", 0, len(actions))
    if action_choice == 0:
        return

    key, defn = actions[action_choice - 1]
    result = build_intent_interactively(key, defn, state)
    if result is None:
        print("  Cancelled.")
        return

    instance, summary = result
    state.action_queue.append(instance)
    log.write_action(summary)
    print(f"\n  Queued: {summary}")


if __name__ == "__main__":
    main()
