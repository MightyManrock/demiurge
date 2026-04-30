#!/usr/bin/env python3
"""
scenario_exporter.py
Writes a SimulationState out to a scenario .db file.
Also contains build_scenario_default() — the canonical Warden's Compact
starting state used to regenerate scenarios/wardens_compact.db.

Usage:
    python scenario_exporter.py                        # exports wardens_compact.db
    python scenario_exporter.py path/to/output.db
"""

from __future__ import annotations
import json
import sqlite3
import sys
from pathlib import Path
from uuid import UUID

from onto_core import (
    Power, Domain, Temperament, Disposition, Constraint,
    Luminary, Pantheon, FootprintProfile, Demiurge,
)
from universe_core import (
    FootprintTolerances, ProxiiPolicy, UniverseRules,
    Galaxy, System, CosmicCoordinates, StarType,
    WorldCondition, World,
    CivilizationScale, CivilizationHealth, Civilization,
    MortalRole, MortalStatus, MortalProminence, NotableMortal,
    Species, SpeciesCondition,
    Universe,
)
from action_core import EssenceStockpile
from tick_logic import SimulationState, CivilizationMomentum, TickConfig


SCHEMA_PATH = Path(__file__).parent / "scenario_schema.sql"


def _j(value) -> str:
    """Serialize a list of UUIDs/strings, or a dict, to a JSON text column."""
    if isinstance(value, list):
        return json.dumps([str(v) for v in value])
    return json.dumps(value)  # dicts (belief weights, etc.) serialize directly


def export_scenario(
    state: SimulationState,
    db_path: str | Path,
    scenario_name: str = "Unnamed Scenario",
    description: str = "",
) -> None:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_PATH.read_text())

    _write_scenario_meta(conn, state, scenario_name, description)
    _write_powers(conn, state)
    _write_domains(conn, state)
    _write_luminaries(conn, state)
    _write_pantheon(conn, state)
    _write_universe_rules(conn, state)
    _write_galaxies(conn, state)
    _write_systems(conn, state)
    _write_species(conn, state)
    _write_worlds(conn, state)
    _write_civilizations(conn, state)
    _write_mortals(conn, state)
    _write_demiurge(conn, state)
    _write_essence(conn, state)
    _write_tick_config(conn, state)
    _write_civ_momentum(conn, state)
    _write_luminary_state(conn, state)
    _write_ongoing_actions(conn, state)

    conn.commit()
    conn.close()
    print(f"Exported scenario to {db_path}")


# ─────────────────────────────────────────
# Per-table writers
# ─────────────────────────────────────────

def _write_scenario_meta(conn, state: SimulationState, name: str, desc: str):
    conn.execute(
        """INSERT INTO scenario_meta
           (name, description, universe_name, current_age, tick_number,
            demiurge_id, pantheon_id)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            name,
            desc,
            state.universe.name,
            state.universe.current_age,
            state.tick_number,
            str(state.demiurge.id),
            str(state.pantheon.id),
        ),
    )


def _write_powers(conn, state: SimulationState):
    # Powers are referenced by domains; reconstruct from domain.source_powers
    seen: dict[str, tuple] = {}
    for domain in state.domains.values():
        for pid in domain.source_powers:
            sid = str(pid)
            if sid not in seen:
                # We don't have Power objects in SimulationState directly,
                # so we write a placeholder row. A full Power registry could
                # be added to SimulationState later.
                seen[sid] = (sid, f"Power:{sid[:8]}", "")
    for row in seen.values():
        conn.execute(
            "INSERT INTO powers (id, name, description) VALUES (?, ?, ?)",
            row,
        )


def _write_domains(conn, state: SimulationState):
    for domain in state.domains.values():
        conn.execute(
            """INSERT INTO domains (id, name, description, source_powers, tags)
               VALUES (?, ?, ?, ?, ?)""",
            (
                str(domain.id),
                domain.name,
                domain.description,
                _j(domain.source_powers),
                _j(domain.tags),
            ),
        )


def _write_luminaries(conn, state: SimulationState):
    for luminary in state.luminaries.values():
        conn.execute(
            """INSERT INTO luminaries
               (id, name, domains, pantheon_id, temperament,
                disposition_results, disposition_methods, herald_id, status_tags)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(luminary.id),
                luminary.name,
                _j(luminary.domains),
                str(luminary.pantheon_id) if luminary.pantheon_id else None,
                luminary.temperament.value,
                luminary.disposition.results,
                luminary.disposition.methods,
                str(luminary.herald_id) if luminary.herald_id else None,
                _j(luminary.status_tags),
            ),
        )
        for c in luminary.constraints:
            conn.execute(
                """INSERT INTO constraints
                   (id, name, description, domain_source, enforcement_weight,
                    owner_id, owner_type)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(c.id),
                    c.name,
                    c.description,
                    str(c.domain_source) if c.domain_source else None,
                    c.enforcement_weight,
                    str(luminary.id),
                    "luminary",
                ),
            )


def _write_pantheon(conn, state: SimulationState):
    p = state.pantheon
    conn.execute(
        "INSERT INTO pantheons (id, name, luminary_ids) VALUES (?, ?, ?)",
        (str(p.id), p.name, _j(p.luminary_ids)),
    )
    for c in p.collective_constraints:
        conn.execute(
            """INSERT INTO constraints
               (id, name, description, domain_source, enforcement_weight,
                owner_id, owner_type)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                str(c.id),
                c.name,
                c.description,
                str(c.domain_source) if c.domain_source else None,
                c.enforcement_weight,
                str(p.id),
                "pantheon",
            ),
        )


def _write_universe_rules(conn, state: SimulationState):
    r  = state.universe.rules
    ft = r.footprint_tolerances
    pp = r.proxii_policy
    conn.execute(
        """INSERT INTO universe_rules
           (fp_tolerance_overt_miracles, fp_tolerance_subtle_influence,
            fp_tolerance_proxius_activity, fp_tolerance_direct_creation,
            proxii_max_per_world, proxii_tolerance_for_excess,
            mortals_can_perceive_divinity, active_shaping_expected,
            special_flags, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            ft.overt_miracles,
            ft.subtle_influence,
            ft.proxius_activity,
            ft.direct_creation,
            pp.max_per_world,
            pp.tolerance_for_excess,
            int(r.mortals_can_perceive_divinity),
            int(r.active_shaping_expected),
            _j(r.special_flags),
            r.notes,
        ),
    )


def _write_species(conn, state: SimulationState):
    for sp in state.species.values():
        conn.execute(
            """INSERT INTO species
               (id, name, description, origin_world_id, sapient, transplanted,
                lifespan_min, lifespan_max, bio_tags, cultural_tags, condition)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(sp.id),
                sp.name,
                sp.description,
                str(sp.origin_world_id) if sp.origin_world_id else None,
                int(sp.sapient),
                int(sp.transplanted),
                sp.lifespan_min,
                sp.lifespan_max,
                _j(sp.bio_tags),
                _j(sp.cultural_tags),
                sp.condition.value,
            ),
        )


def _write_galaxies(conn, state: SimulationState):
    for g in state.galaxies.values():
        conn.execute(
            """INSERT INTO galaxies (id, name, x, y, z, dominant_domain_tags)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                str(g.id),
                g.name,
                g.coordinates.x,
                g.coordinates.y,
                g.coordinates.z,
                _j(g.dominant_domain_tags),
            ),
        )


def _write_systems(conn, state: SimulationState):
    for s in state.systems.values():
        conn.execute(
            "INSERT INTO systems (id, name, galaxy_id, star_type, x, y, z) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                str(s.id),
                s.name,
                str(s.galaxy_id),
                s.star_type.value,
                s.coordinates.x,
                s.coordinates.y,
                s.coordinates.z,
            ),
        )


def _write_worlds(conn, state: SimulationState):
    for w in state.worlds.values():
        conn.execute(
            """INSERT INTO worlds
               (id, name, system_id, condition, domain_expression,
                geo_tags, atmo_tags, species_ids, age)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(w.id),
                w.name,
                str(w.system_id),
                w.condition.value,
                _j(w.domain_expression),
                _j(w.geo_tags),
                _j(w.atmo_tags),
                _j(w.species_ids),
                w.age,
            ),
        )


def _write_civilizations(conn, state: SimulationState):
    for c in state.civilizations.values():
        conn.execute(
            """INSERT INTO civilizations
               (id, name, world_id, scale,
                health_stability, health_prosperity, health_cohesion,
                primary_species_id, dominant_beliefs, culture_tags,
                theistic, divine_awareness, age)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(c.id),
                c.name,
                str(c.world_id),
                c.scale.value,
                c.health.stability,
                c.health.prosperity,
                c.health.cohesion,
                str(c.primary_species_id) if c.primary_species_id else None,
                _j(c.dominant_beliefs),
                _j(c.culture_tags),
                int(c.theistic),
                c.divine_awareness,
                c.age,
            ),
        )


def _write_mortals(conn, state: SimulationState):
    for m in state.mortals.values():
        conn.execute(
            """INSERT INTO mortals
               (id, name, world_id, civilization_id, role, status,
                species_id, prominence_roles, prominence, visibility,
                personal_tags, culture_tags, alignment, chrono_age, bio_age,
                appointed_by_demiurge, appointed_by_luminary)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(m.id),
                m.name,
                str(m.world_id),
                str(m.civilization_id) if m.civilization_id else None,
                m.role.value,
                m.status.value,
                str(m.species_id) if m.species_id else None,
                _j([r.value for r in m.prominence_roles]),
                m.prominence,
                m.visibility,
                _j(m.personal_tags),
                _j(m.culture_tags),
                m.alignment,
                m.chrono_age,
                m.bio_age,
                str(m.appointed_by_demiurge) if m.appointed_by_demiurge else None,
                str(m.appointed_by_luminary) if m.appointed_by_luminary else None,
            ),
        )


def _write_demiurge(conn, state: SimulationState):
    d  = state.demiurge
    fp = d.footprint
    conn.execute(
        """INSERT INTO demiurge
           (id, name, liege_luminary_ids, granted_domains,
            fp_overt_miracles, fp_subtle_influence,
            fp_proxius_activity, fp_direct_creation, proxius_ids)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            str(d.id),
            d.name,
            _j(d.liege_luminary_ids),
            _j(d.granted_domains),
            fp.overt_miracles,
            fp.subtle_influence,
            fp.proxius_activity,
            fp.direct_creation,
            _j(d.proxius_ids),
        ),
    )


def _write_essence(conn, state: SimulationState):
    e = state.essence
    conn.execute(
        "INSERT INTO essence (actual, apparent, concealment_integrity) VALUES (?, ?, ?)",
        (e.actual, e.apparent, e.concealment_integrity),
    )


def _write_tick_config(conn, state: SimulationState):
    cfg = state.config
    dm  = cfg.footprint_decay_multipliers
    conn.execute(
        """INSERT INTO tick_config
           (tick_duration, footprint_decay_rate,
            decay_mult_overt_miracles, decay_mult_subtle_influence,
            decay_mult_proxius_activity, decay_mult_direct_creation,
            concealment_decay_rate, civ_momentum_rate, civ_noise_factor,
            alignment_drift_rate, attention_decay_rate, evaluation_interval,
            mortal_visibility_decay_rate, proxius_passive_footprint_rate)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            cfg.tick_duration,
            cfg.footprint_decay_rate,
            dm.get("overt_miracles",   1.0),
            dm.get("subtle_influence", 1.8),
            dm.get("proxius_activity", 0.8),
            dm.get("direct_creation",  0.4),
            cfg.concealment_decay_rate,
            cfg.civ_momentum_rate,
            cfg.civ_noise_factor,
            cfg.alignment_drift_rate,
            cfg.attention_decay_rate,
            cfg.evaluation_interval,
            cfg.mortal_visibility_decay_rate,
            cfg.proxius_passive_footprint_rate,
        ),
    )


def _write_civ_momentum(conn, state: SimulationState):
    for cid, m in state.civ_momentum.items():
        conn.execute(
            """INSERT INTO civ_momentum
               (civilization_id, stability_delta, prosperity_delta, cohesion_delta)
               VALUES (?, ?, ?, ?)""",
            (cid, m.stability_delta, m.prosperity_delta, m.cohesion_delta),
        )
        for dv in m.belief_drift:
            conn.execute(
                """INSERT INTO civ_momentum_belief_drift
                   (civilization_id, domain_tag, direction, notes)
                   VALUES (?, ?, ?, ?)""",
                (cid, dv.domain_tag, dv.direction, dv.notes),
            )


def _write_luminary_state(conn, state: SimulationState):
    for lid in state.luminaries:
        conn.execute(
            """INSERT INTO luminary_state (luminary_id, attention, ticks_since_evaluation)
               VALUES (?, ?, ?)""",
            (
                lid,
                state.luminary_attention.get(lid, 0.2),
                state.ticks_since_evaluation.get(lid, 0.0),
            ),
        )


def _write_ongoing_actions(conn, state: SimulationState):
    for cat_val, oa in state.ongoing_actions.items():
        intent_type = type(oa.intent).__name__ if oa.intent is not None else None
        intent_data = oa.intent.model_dump_json() if oa.intent is not None else None
        conn.execute(
            """INSERT INTO ongoing_actions
               (category_key, action_key, action_definition_id, target_type,
                target_id, proxius_id, intent_type, intent_data,
                ticks_active, executed_ticks, started_at_tick)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                cat_val,
                oa.action_key,
                str(oa.action_definition_id),
                oa.target_type.value,
                str(oa.target_id) if oa.target_id else None,
                str(oa.proxius_id) if oa.proxius_id else None,
                intent_type,
                intent_data,
                oa.ticks_active,
                oa.executed_ticks,
                oa.started_at_tick,
            ),
        )


# ─────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────
# SCENARIO DEFINITION
# The Warden's Compact — canonical starting state for wardens_compact.db.
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
    p_order    = Power(name="Order",    description="The force of structure, rule, and stillness.")
    p_conflict = Power(name="Conflict", description="The force of struggle, competition, and upheaval.")
    p_silence  = Power(name="Silence",  description="Absence as presence; the space between.")
    p_change   = Power(name="Change",   description="Flux, transformation, impermanence.")

    # ── Domains ─────────────────────────────────────
    d_order = Domain(
        name="Order",
        description="Hierarchy, rule, institutional permanence.",
        source_powers=[p_order.id],
        tags=["domain:order"],
    )
    d_silence = Domain(
        name="Silence",
        description="Restraint, hidden influence, the unseen hand.",
        source_powers=[p_silence.id],
        tags=["domain:silence"],
    )
    d_conflict = Domain(
        name="Conflict",
        description="Competition, opposition, the crucible of strength.",
        source_powers=[p_conflict.id],
        tags=["domain:conflict"],
    )
    d_change = Domain(
        name="Change",
        description="Revolution, dissolution, new forms from old.",
        source_powers=[p_change.id],
        tags=["domain:change"],
    )

    domains = {str(d.id): d for d in [d_order, d_silence, d_conflict, d_change]}

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
        status_tags=["status:liege"],
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
        status_tags=["status:liege"],
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
    neran = World(
        name="Neran",
        system_id=system.id,
        condition=WorldCondition.STABLE,
        domain_expression={"domain:order": 0.6},
        geo_tags=["geo:terrestrial", "geo:temperate"],
        atmo_tags=["atmo:nitrogen_oxygen"],
        age=600.0,
    )
    vel_arath = World(
        name="Vel Arath",
        system_id=system.id,
        condition=WorldCondition.BARREN,
        domain_expression={},
        geo_tags=["geo:rocky", "geo:barren"],
        atmo_tags=["atmo:none"],
        age=900.0,
    )

    galaxy.system_ids.append(system.id)
    system.world_ids.append(neran.id)
    system.world_ids.append(vel_arath.id)

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
        domain_expression={"domain:conflict": 0.5},
        geo_tags=["geo:terrestrial", "geo:arid"],
        atmo_tags=["atmo:nitrogen_oxygen"],
        age=275.0,
    )

    galaxy.system_ids.append(system_outer.id)
    system_outer.world_ids.append(oros.id)

    # ── Species ───────────────────────────────────────
    naran = Species(
        name="Naran",
        description="Humanoid species native to Neran. Ordered society, long memory.",
        origin_world_id=neran.id,
        sapient=True,
        lifespan_min=240,
        lifespan_max=340,
        bio_tags=["bio:bipedal", "bio:warm_blooded", "bio:carbon_based"],
        cultural_tags={"culture:ancestor_worship": 0.70, "culture:hierarchy": 0.60},
        condition=SpeciesCondition.STABLE,
    )
    neran.species_ids.append(naran.id)

    keth_species = Species(
        name="Keth",
        description="Nomadic humanoids of Oros. Pack-bonded, spiritually attuned.",
        origin_world_id=oros.id,
        sapient=True,
        lifespan_min=200,
        lifespan_max=280,
        bio_tags=["bio:bipedal", "bio:nocturnal", "bio:carbon_based"],
        cultural_tags={"culture:nomadism": 0.80, "culture:animism": 0.55},
        condition=SpeciesCondition.STABLE,
    )
    oros.species_ids.append(keth_species.id)

    # ── Civilizations ─────────────────────────────────
    civ = Civilization(
        name="The Neran Confederacy",
        world_id=neran.id,
        scale=CivilizationScale.INTERSTELLAR,
        health=CivilizationHealth(stability=0.6, prosperity=0.5, cohesion=0.55),
        primary_species_id=naran.id,
        dominant_beliefs={"domain:order": 0.8, "domain:mastery": 0.5},
        culture_tags={
            "culture:sedentism": 0.90, "culture:hierarchy": 0.85,
            "culture:industrialism": 0.80, "culture:commerce": 0.75,
            "culture:diplomacy": 0.70, "culture:science": 0.65,
            "culture:luminary_worship": 0.60, "culture:ancestor_worship": 0.50,
        },
        theistic=True,
        divine_awareness=0.25,
        age=400.0,
    )
    neran.civilization_ids.append(civ.id)

    keth = Civilization(
        name="The Keth Wanderers",
        world_id=oros.id,
        scale=CivilizationScale.TRIBAL,
        health=CivilizationHealth(stability=0.4, prosperity=0.3, cohesion=0.65),
        primary_species_id=keth_species.id,
        dominant_beliefs={"domain:conflict": 0.7, "domain:memory": 0.5},
        culture_tags={
            "culture:nomadism": 0.95, "culture:ancestor_worship": 0.85,
            "culture:animism": 0.80, "culture:foraging": 0.70,
            "culture:conquest": 0.60, "culture:egalitarianism": 0.50,
        },
        theistic=True,
        divine_awareness=0.10,
        age=60.0,
    )
    oros.civilization_ids.append(keth.id)

    # ── Notable Mortals ───────────────────────────────
    senna = NotableMortal(
        name="Senna Vaur", world_id=neran.id, civilization_id=civ.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=naran.id,
        prominence_roles=[MortalProminence.LEADER], prominence=0.65, visibility=1.0,
        personal_tags=["domain:order", "status:senator", "personal:ambitious", "personal:pragmatic"],
        culture_tags={"culture:hierarchy": 0.80, "culture:diplomacy": 0.80, "culture:sedentism": 0.80},
        alignment=0.75, chrono_age=170.0, bio_age=170.0,
        home_location=neran.id, current_location=neran.id,
    )
    civ.notable_mortal_ids.append(senna.id)

    karath = NotableMortal(
        name="Karath Omn", world_id=neran.id, civilization_id=civ.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=naran.id,
        prominence_roles=[MortalProminence.MILITARY], prominence=0.80, visibility=1.0,
        personal_tags=["domain:conflict", "domain:mastery", "status:commander", "personal:ambitious", "personal:ruthless"],
        culture_tags={"culture:hierarchy": 0.90, "culture:sedentism": 0.80, "culture:industrialism": 0.70},
        alignment=0.45, chrono_age=205.0, bio_age=205.0,
        home_location=neran.id, current_location=neran.id,
    )
    civ.notable_mortal_ids.append(karath.id)

    veth = NotableMortal(
        name="Veth Sarai", world_id=neran.id, civilization_id=civ.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=naran.id,
        prominence_roles=[MortalProminence.PRIEST], prominence=0.70, visibility=1.0,
        personal_tags=["domain:order", "domain:silence", "status:high_priest", "personal:devout", "personal:cautious"],
        culture_tags={"culture:luminary_worship": 0.90, "culture:ancestor_worship": 0.80, "culture:sedentism": 0.80},
        alignment=0.85, chrono_age=260.0, bio_age=260.0,
        home_location=neran.id, current_location=neran.id,
    )
    civ.notable_mortal_ids.append(veth.id)

    durenn = NotableMortal(
        name="Durenn Vail", world_id=neran.id, civilization_id=civ.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=naran.id,
        prominence_roles=[MortalProminence.MERCHANT], prominence=0.55, visibility=0.6,
        personal_tags=["domain:community", "domain:order", "status:trade_magnate", "personal:opportunistic", "personal:pragmatic"],
        culture_tags={"culture:commerce": 0.85, "culture:sedentism": 0.80, "culture:hierarchy": 0.70},
        alignment=0.35, chrono_age=235.0, bio_age=235.0,
        home_location=neran.id, current_location=neran.id,
    )
    civ.notable_mortal_ids.append(durenn.id)

    asha = NotableMortal(
        name="Asha Keln", world_id=oros.id, civilization_id=keth.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=keth_species.id,
        prominence_roles=[MortalProminence.LEADER, MortalProminence.MILITARY],
        prominence=0.75, visibility=1.0,
        personal_tags=["domain:conflict", "domain:change", "status:tribal_leader", "personal:spiritual"],
        culture_tags={"culture:nomadism": 0.90, "culture:animism": 0.85, "culture:conquest": 0.80},
        alignment=0.60, chrono_age=145.0, bio_age=145.0,
        home_location=oros.id, current_location=oros.id,
    )
    keth.notable_mortal_ids.append(asha.id)

    orryn = NotableMortal(
        name="Orryn Vel", world_id=neran.id, civilization_id=civ.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=naran.id,
        prominence_roles=[MortalProminence.REBEL], prominence=0.40, visibility=0.0,
        personal_tags=["domain:change", "domain:conflict", "status:dissident", "personal:agitator", "personal:charismatic"],
        culture_tags={"culture:science": 0.80, "culture:sedentism": 0.70},
        alignment=0.20, chrono_age=155.0, bio_age=155.0,
        home_location=neran.id, current_location=neran.id,
    )
    civ.notable_mortal_ids.append(orryn.id)

    thessal = NotableMortal(
        name="Thessal Dour", world_id=neran.id, civilization_id=civ.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=naran.id,
        prominence_roles=[MortalProminence.SCHOLAR], prominence=0.30, visibility=0.0,
        personal_tags=["domain:order", "domain:silence", "personal:obsessive", "personal:reclusive"],
        culture_tags={"culture:science": 0.90, "culture:sedentism": 0.80},
        alignment=0.55, chrono_age=190.0, bio_age=190.0,
        home_location=neran.id, current_location=neran.id,
    )
    civ.notable_mortal_ids.append(thessal.id)

    maeva = NotableMortal(
        name="Maeva Sorn", world_id=neran.id, civilization_id=civ.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=naran.id,
        prominence_roles=[MortalProminence.PRIEST], prominence=0.25, visibility=0.0,
        personal_tags=["domain:silence", "domain:order", "personal:devout", "personal:receptive"],
        culture_tags={"culture:luminary_worship": 0.90, "culture:ancestor_worship": 0.85, "culture:sedentism": 0.80},
        alignment=0.70, chrono_age=85.0, bio_age=85.0,
        home_location=neran.id, current_location=neran.id,
    )
    civ.notable_mortal_ids.append(maeva.id)

    kael = NotableMortal(
        name="Kael Ash", world_id=oros.id, civilization_id=keth.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=keth_species.id,
        prominence_roles=[MortalProminence.LEADER], prominence=0.50, visibility=0.0,
        personal_tags=["domain:conflict", "domain:change", "status:clan_elder", "personal:ambitious", "personal:suspicious"],
        culture_tags={"culture:conquest": 0.85, "culture:nomadism": 0.90},
        alignment=0.30, chrono_age=130.0, bio_age=130.0,
        home_location=oros.id, current_location=oros.id,
    )
    keth.notable_mortal_ids.append(kael.id)

    urren = NotableMortal(
        name="Urren", world_id=oros.id, civilization_id=keth.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=keth_species.id,
        prominence_roles=[MortalProminence.PRIEST, MortalProminence.SCHOLAR],
        prominence=0.35, visibility=0.0,
        personal_tags=["domain:change", "domain:memory", "status:shaman", "personal:spiritual", "personal:perceptive"],
        culture_tags={"culture:animism": 0.90, "culture:ancestor_worship": 0.85, "culture:nomadism": 0.80},
        alignment=0.50, chrono_age=175.0, bio_age=175.0,
        home_location=oros.id, current_location=oros.id,
    )
    keth.notable_mortal_ids.append(urren.id)

    # ── Demiurge ─────────────────────────────────────
    demiurge = Demiurge(
        name="The Unnamed",
        liege_luminary_ids=[cassiel.id, vrath.id],
        granted_domains=[d_order.id, d_conflict.id],
        footprint=FootprintProfile(),
    )

    essence = EssenceStockpile(actual=0.0, apparent=0.0, concealment_integrity=1.0)

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
        galaxies={str(galaxy.id): galaxy},
        systems={
            str(system.id):       system,
            str(system_outer.id): system_outer,
        },
        worlds={
            str(neran.id):     neran,
            str(vel_arath.id): vel_arath,
            str(oros.id):      oros,
        },
        civilizations={
            str(civ.id):  civ,
            str(keth.id): keth,
        },
        mortals={
            str(senna.id):   senna,   str(karath.id): karath,
            str(veth.id):    veth,    str(durenn.id): durenn,
            str(asha.id):    asha,    str(orryn.id):  orryn,
            str(thessal.id): thessal, str(maeva.id):  maeva,
            str(kael.id):    kael,    str(urren.id):  urren,
        },
        species={
            str(naran.id):        naran,
            str(keth_species.id): keth_species,
        },
        civ_momentum={
            str(civ.id): CivilizationMomentum(
                civilization_id=civ.id,
                stability_delta=0.1, prosperity_delta=0.05, cohesion_delta=-0.05,
            ),
            str(keth.id): CivilizationMomentum(
                civilization_id=keth.id,
                stability_delta=-0.05, prosperity_delta=0.0, cohesion_delta=0.1,
            ),
        },
        luminary_attention={str(cassiel.id): 0.15, str(vrath.id): 0.30},
        ticks_since_evaluation={str(cassiel.id): 0.0, str(vrath.id): 0.0},
        config=TickConfig(tick_duration=0.5, evaluation_interval=5.0),
    )


# ─────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────

if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        Path(__file__).parent / "scenarios" / "wardens_compact.db"
    )

    state = build_scenario_default()
    export_scenario(
        state,
        out,
        scenario_name="The Warden's Compact",
        description=(
            "A young universe under two contradictory lieges: "
            "Cassiel (Order/Silence, patient) and Vrath (Conflict/Change, wrathful). "
            "Two inhabited worlds, one barren candidate for seeding."
        ),
    )
