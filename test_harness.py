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
    MortalRole, MortalStatus, MortalProminence, NotableMortal,
    Species, SpeciesCondition,
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
    SalvageIntent, SeedWorldIntent, UpliftSpeciesIntent,
    DomainVector,
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
    is_mortal_visible, ALWAYS_VISIBLE_THRESHOLD, VISIBILITY_FLOOR,
)
from scenario_loader import load_scenario


# ─────────────────────────────────────────
# SCENARIO FACTORY
# Builds a concrete starting SimulationState.
# Tweak this to test different scenarios.
# ─────────────────────────────────────────

def build_scenario_default() -> SimulationState:
    """
    Scenario: 'The Warden's Compact'

    You are Demiurge of a young universe with two inhabited worlds and one
    barren candidate for seeding. Your two liege Luminaries have contradictory
    temperaments:
      - Cassiel, Luminary of Order and Silence — patient, demands subtlety
      - Vrath, Luminary of Conflict and Change — wrathful, demands results fast

    The Pantheon expects subtlety. Vrath privately does not care,
    but expects civilizational Domain alignment toward conflict within
    a short window. The tension is immediate.

    Spatial layout:
      The Nascent Coil (galaxy)
        Ardent System
          Neran          — stable, continental civilization (domain:order)
          Vel Arath      — barren, no life; candidate for seed_world
        The Outer Reach (system)
          Oros           — stable, nascent tribal society (domain:conflict seeds)
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

    # Ardent System — inner system, two worlds
    system = System(
        name="Ardent System",
        galaxy_id=galaxy.id,
        star_type=StarType.MAIN_SEQUENCE,
    )
    neran = World(
        name="Neran",
        system_id=system.id,
        condition=WorldCondition.STABLE,
        domain_expression=["domain:order"],
        age=600.0,
    )
    # Vel Arath — barren sibling world, no life yet
    vel_arath = World(
        name="Vel Arath",
        system_id=system.id,
        condition=WorldCondition.BARREN,
        domain_expression=[],
        age=900.0,
        # Older than Neran; conditions are inert but not hostile
    )

    galaxy.system_ids.append(system.id)
    system.world_ids.append(neran.id)
    system.world_ids.append(vel_arath.id)

    # The Outer Reach — distant system, one young world
    system_outer = System(
        name="The Outer Reach",
        galaxy_id=galaxy.id,
        star_type=StarType.DWARF,
        coordinates=CosmicCoordinates(x=12.0, y=3.0, z=-2.0),
    )
    oros = World(
        name="Oros",
        system_id=system_outer.id,
        condition=WorldCondition.STABLE,
        domain_expression=["domain:conflict"],
        age=275.0,
        # Young world; its first civilization is already war-shaped
    )

    galaxy.system_ids.append(system_outer.id)
    system_outer.world_ids.append(oros.id)

    # ── Civilizations ─────────────────────────────────

    # ── Species ───────────────────────────────────────

    # Naran — the humanoid people of Neran
    # Long-lived relative to their world's age; Veth (bio_age 260) is near end-of-life
    naran = Species(
        name="Naran",
        description="Humanoid species native to Neran. Ordered society, long memory.",
        origin_world_id=neran.id,
        sapient=True,
        lifespan_min=240,
        lifespan_max=340,
        trait_tags=["trait:bipedal", "trait:warm_blooded"],
        cultural_tags=["culture:institutional", "culture:ancestor_veneration"],
        condition=SpeciesCondition.STABLE,
    )
    neran.species_ids.append(naran.id)

    # Keth — the tribal wanderers of Oros
    # Shorter-lived; Asha (bio_age 145) is young and vigorous
    keth_species = Species(
        name="Keth",
        description="Nomadic humanoids of Oros. Pack-bonded, spiritually attuned.",
        origin_world_id=oros.id,
        sapient=True,
        lifespan_min=200,
        lifespan_max=280,
        trait_tags=["trait:bipedal", "trait:nocturnal"],
        cultural_tags=["culture:nomadic", "culture:oral_tradition"],
        condition=SpeciesCondition.STABLE,
    )
    oros.species_ids.append(keth_species.id)

    # ── Civilizations ─────────────────────────────────

    # Neran: established interstellar power, order-oriented
    civ = Civilization(
        name="The Neran Confederacy",
        world_id=neran.id,
        scale=CivilizationScale.INTERSTELLAR,
        health=CivilizationHealth(
            stability=0.6,
            prosperity=0.5,
            cohesion=0.55,
        ),
        primary_species_id=naran.id,
        dominant_beliefs=["domain:order", "domain:law"],
        theistic=True,
        divine_awareness=0.25,
        age=400.0,
    )
    neran.civilization_ids.append(civ.id)

    # Oros: nascent tribal confederation, conflict-and-change flavored
    keth = Civilization(
        name="The Keth Wanderers",
        world_id=oros.id,
        scale=CivilizationScale.TRIBAL,
        health=CivilizationHealth(
            stability=0.4,
            prosperity=0.3,
            cohesion=0.65,
            # Tight bonds within bands, but fragile overall
        ),
        primary_species_id=keth_species.id,
        dominant_beliefs=["domain:conflict", "domain:ancestor_worship"],
        theistic=True,
        divine_awareness=0.10,
        age=60.0,
    )
    oros.civilization_ids.append(keth.id)

    # ── Notable Mortals ───────────────────────────────

    # Neran: pragmatic administrator — strong proxius candidate (order)
    senna = NotableMortal(
        name="Senna Vaur",
        world_id=neran.id,
        civilization_id=civ.id,
        role=MortalRole.OTHER,
        status=MortalStatus.ACTIVE,
        species_id=naran.id,
        prominence_roles=[MortalProminence.LEADER],
        prominence=0.65,
        visibility=1.0,
        personal_tags=["domain:order", "ambitious", "pragmatic"],
        alignment=0.75,
        chrono_age=170.0,
        bio_age=170.0,
    )
    civ.notable_mortal_ids.append(senna.id)

    # Neran: military commander — aligned with conflict, personally ambitious
    karath = NotableMortal(
        name="Karath Omn",
        world_id=neran.id,
        civilization_id=civ.id,
        role=MortalRole.OTHER,
        status=MortalStatus.ACTIVE,
        species_id=naran.id,
        prominence_roles=[MortalProminence.MILITARY],
        prominence=0.80,
        visibility=1.0,
        personal_tags=["domain:conflict", "domain:war", "ambitious", "ruthless"],
        alignment=0.45,
        chrono_age=205.0,
        bio_age=205.0,
    )
    civ.notable_mortal_ids.append(karath.id)

    # Neran: temple keeper — devout, subtlety-inclined; Cassiel's natural ally
    # bio_age 260 — entering the Naran death-check zone (lifespan_min 240)
    veth = NotableMortal(
        name="Veth Sarai",
        world_id=neran.id,
        civilization_id=civ.id,
        role=MortalRole.OTHER,
        status=MortalStatus.ACTIVE,
        species_id=naran.id,
        prominence_roles=[MortalProminence.PRIEST],
        prominence=0.70,
        visibility=1.0,
        personal_tags=["domain:order", "domain:silence", "devout", "cautious"],
        alignment=0.85,
        chrono_age=260.0,
        bio_age=260.0,
    )
    civ.notable_mortal_ids.append(veth.id)

    # Neran: merchant guildmaster — influential but operates in shadow
    # prominence below ALWAYS_VISIBLE_THRESHOLD; starts known but will fade without attention
    durenn = NotableMortal(
        name="Durenn Vail",
        world_id=neran.id,
        civilization_id=civ.id,
        role=MortalRole.OTHER,
        status=MortalStatus.ACTIVE,
        species_id=naran.id,
        prominence_roles=[MortalProminence.MERCHANT],
        prominence=0.55,
        visibility=0.6,
        personal_tags=["domain:trade", "domain:law", "opportunistic", "pragmatic"],
        alignment=0.35,
        chrono_age=235.0,
        bio_age=235.0,
    )
    civ.notable_mortal_ids.append(durenn.id)

    # Oros: tribal war-chieftain — Vrath's natural instrument on Oros
    asha = NotableMortal(
        name="Asha Keln",
        world_id=oros.id,
        civilization_id=keth.id,
        role=MortalRole.OTHER,
        status=MortalStatus.ACTIVE,
        species_id=keth_species.id,
        prominence_roles=[MortalProminence.LEADER, MortalProminence.MILITARY],
        prominence=0.75,
        visibility=1.0,
        personal_tags=["domain:conflict", "domain:change", "tribal_leader", "spiritual"],
        alignment=0.60,
        chrono_age=145.0,
        bio_age=145.0,
    )
    keth.notable_mortal_ids.append(asha.id)

    # ── Hidden mortals (visibility=0.0, discoverable via scry) ───────────

    # Neran: political agitator — low-prominence rebel, dangerous if discovered
    orryn = NotableMortal(
        name="Orryn Vel",
        world_id=neran.id,
        civilization_id=civ.id,
        role=MortalRole.OTHER,
        status=MortalStatus.ACTIVE,
        species_id=naran.id,
        prominence_roles=[MortalProminence.REBEL],
        prominence=0.40,
        visibility=0.0,
        personal_tags=["domain:change", "domain:conflict", "agitator", "charismatic"],
        alignment=0.20,
        chrono_age=155.0,
        bio_age=155.0,
    )
    civ.notable_mortal_ids.append(orryn.id)

    # Neran: obsessive archivist — scholar who knows too much
    thessal = NotableMortal(
        name="Thessal Dour",
        world_id=neran.id,
        civilization_id=civ.id,
        role=MortalRole.OTHER,
        status=MortalStatus.ACTIVE,
        species_id=naran.id,
        prominence_roles=[MortalProminence.SCHOLAR],
        prominence=0.30,
        visibility=0.0,
        personal_tags=["domain:order", "domain:silence", "obsessive", "reclusive"],
        alignment=0.55,
        chrono_age=190.0,
        bio_age=190.0,
    )
    civ.notable_mortal_ids.append(thessal.id)

    # Neran: minor temple keeper — devout but obscure
    maeva = NotableMortal(
        name="Maeva Sorn",
        world_id=neran.id,
        civilization_id=civ.id,
        role=MortalRole.OTHER,
        status=MortalStatus.ACTIVE,
        species_id=naran.id,
        prominence_roles=[MortalProminence.PRIEST],
        prominence=0.25,
        visibility=0.0,
        personal_tags=["domain:silence", "domain:order", "devout", "receptive"],
        alignment=0.70,
        chrono_age=85.0,
        bio_age=85.0,
    )
    civ.notable_mortal_ids.append(maeva.id)

    # Oros: ambitious challenger to Asha's authority
    kael = NotableMortal(
        name="Kael Ash",
        world_id=oros.id,
        civilization_id=keth.id,
        role=MortalRole.OTHER,
        status=MortalStatus.ACTIVE,
        species_id=keth_species.id,
        prominence_roles=[MortalProminence.LEADER],
        prominence=0.50,
        visibility=0.0,
        personal_tags=["domain:conflict", "domain:change", "ambitious", "suspicious"],
        alignment=0.30,
        chrono_age=130.0,
        bio_age=130.0,
    )
    keth.notable_mortal_ids.append(kael.id)

    # Oros: wandering spirit-speaker — spiritually perceptive, may sense the divine
    urren = NotableMortal(
        name="Urren",
        world_id=oros.id,
        civilization_id=keth.id,
        role=MortalRole.OTHER,
        status=MortalStatus.ACTIVE,
        species_id=keth_species.id,
        prominence_roles=[MortalProminence.PRIEST, MortalProminence.SCHOLAR],
        prominence=0.35,
        visibility=0.0,
        personal_tags=["domain:change", "domain:ancestor_worship", "spiritual", "perceptive"],
        alignment=0.50,
        chrono_age=175.0,
        bio_age=175.0,
    )
    keth.notable_mortal_ids.append(urren.id)

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
        current_age=600.0,
    )

    return SimulationState(
        universe=universe,
        demiurge=demiurge,
        essence=essence,
        pantheon=pantheon,
        luminaries=luminaries,
        domains=domains,
        galaxies={
            str(galaxy.id): galaxy,
        },
        systems={
            str(system.id):       system,
            str(system_outer.id): system_outer,
        },
        worlds={
            str(neran.id):     neran,       # Neran
            str(vel_arath.id): vel_arath,   # barren
            str(oros.id):      oros,        # Keth tribal world
        },
        civilizations={
            str(civ.id):  civ,    # The Neran Confederacy
            str(keth.id): keth,   # The Keth Wanderers
        },
        mortals={
            str(senna.id):  senna,
            str(karath.id): karath,
            str(veth.id):   veth,
            str(durenn.id): durenn,
            str(asha.id):   asha,
            str(orryn.id):  orryn,
            str(thessal.id): thessal,
            str(maeva.id):  maeva,
            str(kael.id):   kael,
            str(urren.id):  urren,
        },
        species={
            str(naran.id):       naran,
            str(keth_species.id): keth_species,
        },
        civ_momentum={
            str(civ.id): CivilizationMomentum(
                civilization_id=civ.id,
                stability_delta=0.1,
                prosperity_delta=0.05,
                cohesion_delta=-0.05,
                # Slight internal fracturing despite surface stability
            ),
            str(keth.id): CivilizationMomentum(
                civilization_id=keth.id,
                stability_delta=-0.05,
                prosperity_delta=0.0,
                cohesion_delta=0.1,
                # Bands are consolidating, but overall stability is shaky
            ),
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
            tick_duration=0.5,
            evaluation_interval=5.0,
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
        if not is_mortal_visible(mortal):
            continue
        role_str = mortal.role.value.upper() if mortal.role != MortalRole.OTHER else "mortal"
        age_str = f"age:{mortal.chrono_age:.0f}"
        if mortal.bio_age != mortal.chrono_age:
            age_str += f"(bio:{mortal.bio_age:.0f})"
        prom_str = _prominence_label(mortal)
        vis_note = (
            f"  vis:{mortal.visibility:.2f}"
            if mortal.prominence < ALWAYS_VISIBLE_THRESHOLD else ""
        )
        lines.append(
            f"  {mortal.name:16s} [{role_str}]  "
            f"align:{mortal.alignment:.2f}  {age_str}{vis_note}  "
            f"{prom_str}"
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
# BRIEFING
# Full scenario context for the player.
# ─────────────────────────────────────────

def display_briefing(state: SimulationState) -> str:
    lines = [
        SEP2,
        f"  SCENARIO BRIEFING",
        f"  {state.universe.name}  (Age {state.universe.current_age:.1f})",
        SEP2,
        "",
    ]

    # ── Pantheon ──────────────────────────────────────
    pan = state.pantheon
    lines.append(f"PANTHEON: {pan.name}")
    if pan.collective_constraints:
        lines.append("  Collective Constraints:")
        for c in pan.collective_constraints:
            lines.append(f"    • {c.name}  [enforcement: {c.enforcement_weight:.2f}]")
            lines.append(f"      {c.description}")
    lines.append(SEP)

    # ── Liege Luminaries ──────────────────────────────
    lines.append("YOUR LIEGE LUMINARIES")
    for lid in [str(i) for i in state.demiurge.liege_luminary_ids]:
        lum = state.luminaries.get(lid)
        if not lum:
            continue
        lines.append("")
        lines.append(f"  {lum.name.upper()}  [{lum.temperament.value}]")

        domain_names = [
            state.domains[str(did)].name
            for did in lum.domains
            if str(did) in state.domains
        ]
        lines.append(f"  Domains: {', '.join(domain_names)}")

        for did in lum.domains:
            d = state.domains.get(str(did))
            if d:
                lines.append(f"    • {d.name}: {d.description}")
                if d.tags:
                    lines.append(f"      Tags: {', '.join(d.tags)}")

        if lum.constraints:
            lines.append("  Constraints imposed on you:")
            for c in lum.constraints:
                lines.append(
                    f"    • {c.name}  [enforcement: {c.enforcement_weight:.2f}]"
                )
                lines.append(f"      {c.description}")

        d = lum.disposition
        att = state.luminary_attention.get(lid, 0.0)
        lines.append(
            f"  Starting disposition:  results{d.results:+.2f}  "
            f"methods{d.methods:+.2f}  attention:{att:.2f}"
        )

    lines += ["", SEP]

    # ── Universe Rules ─────────────────────────────────
    rules = state.universe.rules
    tol   = rules.footprint_tolerances
    pp    = rules.proxii_policy
    cap_str = f"max {pp.max_per_world} per world" if pp.max_per_world else "no per-world limit"
    lines += [
        "UNIVERSE RULES",
        "  Footprint Tolerances:",
        f"    Overt Miracles:   {tol.overt_miracles:.2f}  |  "
        f"Subtle Influence: {tol.subtle_influence:.2f}",
        f"    Proxius Activity: {tol.proxius_activity:.2f}  |  "
        f"Direct Creation:  {tol.direct_creation:.2f}",
        f"  Proxii Policy: {cap_str}  (slack: {pp.tolerance_for_excess:.2f})",
        f"  Active shaping expected:    {'yes' if rules.active_shaping_expected else 'no'}",
        f"  Mortals perceive divinity:  {'yes' if rules.mortals_can_perceive_divinity else 'no'}",
    ]
    if rules.notes:
        lines.append(f"  Notes: {rules.notes}")
    if rules.special_flags:
        lines.append(f"  Special flags: {', '.join(rules.special_flags)}")
    lines.append(SEP)

    # ── Spatial hierarchy ─────────────────────────────
    lines.append("YOUR UNIVERSE")
    for gid, galaxy in state.galaxies.items():
        lines += ["", f"  Galaxy: {galaxy.name}"]
        for sid in galaxy.system_ids:
            sys_obj = state.systems.get(str(sid))
            if not sys_obj:
                continue
            lines.append(f"    System: {sys_obj.name}  [{sys_obj.star_type.value}]")
            for wid in sys_obj.world_ids:
                world = state.worlds.get(str(wid))
                if not world:
                    continue
                n_civs  = len(world.civilization_ids)
                life_str = f"{n_civs} civilization(s)" if n_civs else "no life"
                lines.append(
                    f"      {world.name}  [{world.condition.value}]"
                    f"  age:{world.age:.0f}  {life_str}"
                )
                if world.domain_expression:
                    lines.append(
                        f"        domain expression: {', '.join(world.domain_expression)}"
                    )
                for cid in world.civilization_ids:
                    civ = state.civilizations.get(str(cid))
                    if civ:
                        h = civ.health
                        lines.append(
                            f"        └─ {civ.name}  [{civ.scale.value}]"
                            f"  stab:{h.stability:.2f} pros:{h.prosperity:.2f}"
                            f" coh:{h.cohesion:.2f}"
                        )
                        if civ.dominant_beliefs:
                            lines.append(
                                f"           beliefs: {', '.join(civ.dominant_beliefs)}"
                            )
    lines += ["", SEP]

    # ── Species ────────────────────────────────────────
    if state.species:
        lines.append("SPECIES")
        for sid, sp in state.species.items():
            w_obj = state.worlds.get(str(sp.origin_world_id)) if sp.origin_world_id else None
            origin = w_obj.name if w_obj else "unknown"
            sapient_str = "sapient" if sp.sapient else "non-sapient"
            transplanted_str = "  [transplanted]" if sp.transplanted else ""
            lines.append(
                f"  {sp.name:16s} [{sapient_str}]  "
                f"origin:{origin}  "
                f"lifespan:{sp.lifespan_min:.0f}–{sp.lifespan_max:.0f}  "
                f"[{sp.condition.value}]{transplanted_str}"
            )
            if sp.trait_tags or sp.cultural_tags:
                tag_line = ", ".join(sp.trait_tags + sp.cultural_tags)
                lines.append(f"    {tag_line}")
        lines.append(SEP)

    # ── Notable Mortals ────────────────────────────────
    lines.append("NOTABLE MORTALS")
    for mid, mortal in state.mortals.items():
        if not is_mortal_visible(mortal):
            continue
        w_obj = state.worlds.get(str(mortal.world_id))
        c_obj = (
            state.civilizations.get(str(mortal.civilization_id))
            if mortal.civilization_id else None
        )
        loc      = w_obj.name if w_obj else "?"
        if c_obj:
            loc += f" · {c_obj.name}"
        role_str = mortal.role.value.upper() if mortal.role != MortalRole.OTHER else "mortal"
        age_str = f"age:{mortal.chrono_age:.0f}"
        if mortal.bio_age != mortal.chrono_age:
            age_str += f"(bio:{mortal.bio_age:.0f})"
        sp_obj = state.species.get(str(mortal.species_id)) if mortal.species_id else None
        sp_note = f"  [{sp_obj.name}]" if sp_obj else ""
        prom_str = _prominence_label(mortal)
        vis_note = (
            f"  vis:{mortal.visibility:.2f}"
            if mortal.prominence < ALWAYS_VISIBLE_THRESHOLD else ""
        )
        lines.append(
            f"  {mortal.name:16s} [{role_str:7s}]  "
            f"align:{mortal.alignment:.2f}  {age_str}{sp_note}{vis_note}   {loc}"
        )
        lines.append(f"    {prom_str}")
        if mortal.personal_tags:
            lines.append(f"    Tags: {', '.join(mortal.personal_tags)}")

    lines += ["", SEP2]
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

    # ── issue_directive: target and proxius are the same selection ───────
    if action_key == "issue_directive":
        include_dormant = "include_dormant_proxius" in defn.tags
        already_directed = {
            str(ai.proxius_id)
            for ai in state.action_queue
            if isinstance(ai.intent, ProxiusDirectiveIntent) and ai.proxius_id is not None
        }
        proxii = [
            (mid, m) for mid, m in state.mortals.items()
            if m.role == MortalRole.PROXIUS
            and mid not in already_directed
            and (m.status == MortalStatus.ACTIVE
                 or (include_dormant and m.status == MortalStatus.DORMANT))
        ]
        if not proxii:
            print("  No Proxii available to receive a directive this tick.")
            return None
        print("  Issue directive to which Proxius?")
        for i, (mid, m) in enumerate(proxii):
            w_obj = state.worlds.get(str(m.world_id))
            loc = w_obj.name if w_obj else "?"
            dormant_note = "  [DORMANT]" if m.status == MortalStatus.DORMANT else ""
            print(
                f"    {i+1}. {m.name:<16s}  align:{m.alignment:.2f}   {loc}{dormant_note}"
            )
        print("    0. Cancel")
        choice = _prompt_int("  > ", 0, len(proxii))
        if choice == 0:
            return None
        target_id = UUID(proxii[choice - 1][0])
        intent = _build_intent(action_key, defn, target_id, state)
        summary = f"{defn.name} → {_name_for_id(target_id, state)}"
        instance = ActionInstance(
            action_definition_id=defn.id,
            target_type=TargetType.MORTAL,
            target_id=target_id,
            timestamp=state.universe.current_age,
            demiurge_id=state.demiurge.id,
            proxius_id=target_id,
            intent=intent,
        )
        return instance, summary

    # ── Target selection ──────────────────────────────
    target_id = None
    target_type = defn.valid_targets[0]  # Default; refined below

    if TargetType.MORTAL in defn.valid_targets and state.mortals:
        mortals = [
            (mid, m) for mid, m in state.mortals.items()
            if is_mortal_visible(m)
        ]
        if not mortals:
            print("  No mortals are currently within your perception.")
            return None
        print("  Select target mortal:")
        for i, (mid, m) in enumerate(mortals):
            w_obj  = state.worlds.get(str(m.world_id))
            c_obj  = state.civilizations.get(str(m.civilization_id)) if m.civilization_id else None
            loc    = w_obj.name if w_obj else "?"
            if c_obj:
                loc += f" · {c_obj.name}"
            role_str = m.role.value if m.role != MortalRole.OTHER else "mortal"
            prom_str = _prominence_label(m)
            print(
                f"    {i+1}. {m.name:<16s} [{role_str}]  "
                f"align:{m.alignment:.2f}   {loc}  {prom_str}"
            )
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
            w_obj = state.worlds.get(str(c.world_id))
            loc   = w_obj.name if w_obj else "?"
            print(f"    {i+1}. {c.name:<30s} [{c.scale.value}]  {loc}")
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
            print(f"    {i+1}. {l.name}  [{l.temperament.value}]")
        print("    0. Cancel")
        choice = _prompt_int("  > ", 0, len(lums))
        if choice == 0:
            return None
        target_id = UUID(lums[choice - 1][0])
        target_type = TargetType.LUMINARY

    elif TargetType.SPECIES in defn.valid_targets and state.species:
        species_list = list(state.species.items())
        print("  Select target species:")
        for i, (sid, sp) in enumerate(species_list):
            w_obj = state.worlds.get(str(sp.origin_world_id)) if sp.origin_world_id else None
            origin = w_obj.name if w_obj else "unknown"
            sapient_str = "sapient" if sp.sapient else "non-sapient"
            print(f"    {i+1}. {sp.name:<16s} [{sapient_str}]  origin: {origin}")
        print("    0. Cancel")
        choice = _prompt_int("  > ", 0, len(species_list))
        if choice == 0:
            return None
        target_id = UUID(species_list[choice - 1][0])
        target_type = TargetType.SPECIES

    elif TargetType.UNDERREAL in defn.valid_targets:
        target_type = TargetType.UNDERREAL
        target_id = None

    elif TargetType.WORLD in defn.valid_targets and state.worlds:
        worlds = list(state.worlds.items())
        print("  Select target world:")
        for i, (wid, w) in enumerate(worlds):
            sys_obj  = state.systems.get(str(w.system_id))
            sys_name = sys_obj.name if sys_obj else "?"
            n_civs   = len(w.civilization_ids)
            life_str = f"{n_civs} civilization(s)" if n_civs else "no life"
            print(
                f"    {i+1}. {w.name:<14s} [{w.condition.value}]  "
                f"{sys_name:<20s}  {life_str}"
            )
        print("    0. Cancel")
        choice = _prompt_int("  > ", 0, len(worlds))
        if choice == 0:
            return None
        target_id = UUID(worlds[choice - 1][0])
        target_type = TargetType.WORLD

    # ── Proxius selection for directed actions ────────
    proxius_id = None
    if defn.requires_proxius:
        include_dormant = "include_dormant_proxius" in defn.tags
        proxii = [
            (mid, m) for mid, m in state.mortals.items()
            if m.role == MortalRole.PROXIUS
            and (m.status == MortalStatus.ACTIVE
                 or (include_dormant and m.status == MortalStatus.DORMANT))
        ]
        if not proxii:
            print("  No active Proxii available for this action.")
            return None
        print("  Select Proxius to act through:")
        for i, (mid, m) in enumerate(proxii):
            w_obj    = state.worlds.get(str(m.world_id))
            loc      = w_obj.name if w_obj else "?"
            dormant_note = "  [DORMANT]" if m.status == MortalStatus.DORMANT else ""
            print(f"    {i+1}. {m.name:<16s} align:{m.alignment:.2f}   {loc}{dormant_note}")
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

    if cat == ActionCategory.DIRECT_CREATION:
        if action_key == "seed_world":
            name = input("  Species name: ").strip() or "Life-Form Alpha"
            lifespan_min = _prompt_float("  Lifespan min (time units): ", 1.0, 100000.0, 100.0)
            lifespan_max = _prompt_float("  Lifespan max (time units): ", 1.0, 100000.0, 200.0)
            sapient_raw = input("  Sapient from the start? (y/n) [n]: ").strip().lower()
            sapient = sapient_raw == "y"
            tags_raw = input(
                "  Trait tags (comma-separated, e.g. trait:bipedal — blank to skip): "
            ).strip()
            trait_tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
            return SeedWorldIntent(
                species_name=name,
                lifespan_min=lifespan_min,
                lifespan_max=lifespan_max,
                sapient=sapient,
                trait_tags=trait_tags,
            )
        elif action_key == "uplift_species":
            dv = _prompt_domain_vector()
            return UpliftSpeciesIntent(
                species_id=target_id,
                domain_vectors=[dv] if dv else [],
            )

    elif cat == ActionCategory.SUBTLE_INFLUENCE:
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

    elif cat == ActionCategory.OVERT_MIRACLE:
        if action_key in ("manifest_omen", "divine_manifestation"):
            sign = input("  Sign description (what occurs): ").strip() or "A celestial anomaly appears"
            interpretation = (
                input("  Intended interpretation: ").strip() or "The gods demand action"
            )
            dv = _prompt_domain_vector()
            civ_scope = None
            if target_id:
                tid_str = str(target_id)
                if tid_str in state.civilizations:
                    civ_scope = target_id
                elif tid_str in state.mortals:
                    civ_scope = state.mortals[tid_str].civilization_id
            return OmenIntent(
                sign_description=sign,
                intended_interpretation=interpretation,
                domain_vectors=[dv] if dv else [],
                framing=_prompt_framing(),
                civilization_scope=civ_scope,
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

    # No structured intent needed (scry, appoint_proxius, etc.)
    return None


def _prominence_label(mortal: "NotableMortal") -> str:
    """Short display string showing role(s) and prominence tier."""
    if not mortal.prominence_roles or mortal.prominence_roles == [MortalProminence.NONE]:
        role_part = "no notable role"
    else:
        role_part = " · ".join(r.value.title() for r in mortal.prominence_roles)
    always = mortal.prominence >= ALWAYS_VISIBLE_THRESHOLD
    tier = "always visible" if always else f"prominence:{mortal.prominence:.2f}"
    return f"{role_part}  [{tier}]"


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

def _select_scenario() -> SimulationState:
    """
    Display a startup menu of available .db files in the scenarios/
    folder, plus an option to load the hardcoded default scenario.
    Returns a fully constructed SimulationState.
    """
    scenarios_dir = Path(__file__).parent / "scenarios"
    db_files = sorted(scenarios_dir.glob("*.db")) if scenarios_dir.exists() else []

    print()
    print("  SELECT SCENARIO")
    print("  ────────────────────────────────────────────────")

    if db_files:
        for i, path in enumerate(db_files, start=1):
            try:
                import sqlite3 as _sq
                with _sq.connect(path) as _c:
                    row = _c.execute("SELECT name, description FROM scenario_meta LIMIT 1").fetchone()
                scenario_name = row[0] if row else path.stem
                scenario_desc = row[1] if (row and row[1]) else ""
            except Exception:
                scenario_name = path.stem
                scenario_desc = ""
            print(f"  [{i}] {scenario_name}")
            if scenario_desc:
                print(f"       {scenario_desc}")
    else:
        print("  (no scenario files found in scenarios/)")

    print(f"  [D] Default scenario  (build_scenario_default)")
    if db_files:
        print(f"  [Q] Quit")
    print()

    while True:
        raw = input("  > ").strip().upper()

        if raw == "Q":
            raise SystemExit(0)

        if raw == "D":
            print("  Loading default scenario...")
            return build_scenario_default()

        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(db_files):
                path = db_files[idx]
                print(f"  Loading {path.name}...")
                return load_scenario(path)

        print(f"  Invalid choice — enter a number 1–{len(db_files)}, D, or Q.")


def main():
    print(SEP2)
    print("  DEMIURGE — TEST HARNESS")
    print(SEP2)

    state = _select_scenario()
    print()

    log_path = Path(os.path.join("logs", f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"))
    log = SessionLog(log_path)
    print(f"  Logging to: {log_path}\n")

    loop  = TickLoop()
    library = loop._action_library
    last_result: TickResult | None = None

    # Map action keys to definitions with a stable index
    action_index: list[tuple[str, ActionDefinition]] = list(library.items())

    briefing = display_briefing(state)
    print(briefing)
    log.write(briefing)
    print(display_state(state))
    log.write_state(state)

    while True:
        print()
        print("  ACTIONS")
        print("  ────────────────────────────────────────────────")
        print("  [A] Browse and queue actions")
        print("  [T] Advance time (execute queued actions + tick)")
        print("  [S] Show current state")
        print("  [B] Show scenario briefing")
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

        elif cmd == "B":
            out = display_briefing(state)
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

    # Enforce mutual exclusion between maintain_concealment and harvest_essence
    MUTEX_PAIR = frozenset({"maintain_concealment", "harvest_essence"})
    MUTEX_NAMES = {
        "maintain_concealment": "Maintain Concealment",
        "harvest_essence": "Harvest Essence",
    }
    if key in MUTEX_PAIR:
        key_by_id = {str(v.id): k for k, v in library.items()}
        queued_keys = {key_by_id.get(str(ai.action_definition_id)) for ai in state.action_queue}
        conflict = queued_keys & MUTEX_PAIR - {key}
        if conflict:
            conflicting = next(iter(conflict))
            print(
                f"\n  Blocked: {MUTEX_NAMES.get(key, key)} cannot be queued alongside "
                f"{MUTEX_NAMES.get(conflicting, conflicting)} in the same tick."
            )
            return

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
