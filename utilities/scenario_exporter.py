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

from core.onto_core import (
    Power, Domain, Disposition, Constraint,
    Luminary, Pantheon, FootprintProfile, Demiurge,
)
from core.universe_core import (
    FootprintTolerances, ProxiiPolicy, UniverseRules,
    Location, System, CosmicCoordinates, StarType,
    SignificantLocation, PopLocation, LocCondition, LocFootprint,
    CivilizationScale, CivilizationHealth, Civilization,
    MortalRole, MortalStatus, MortalProminence, NotableMortal,
    Species, SpeciesCondition,
    Universe,
)
from core.action_core import EssenceStockpile
from core.event_core import Event
from logic.tick_logic import SimulationState, CivilizationMomentum, TickConfig


SCHEMA_PATH = Path(__file__).parent.parent / "core" / "scenario_schema.sql"


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
    _write_locations(conn, state)
    _write_species(conn, state)
    _write_civilizations(conn, state)
    _write_mortals(conn, state)
    _write_demiurge(conn, state)
    _write_essence(conn, state)
    _write_tick_config(conn, state)
    _write_civ_momentum(conn, state)
    _write_luminary_state(conn, state)
    _write_ongoing_actions(conn, state)
    _write_active_events(conn, state)

    conn.commit()
    conn.close()
    print(f"Exported scenario to {db_path}")


# ─────────────────────────────────────────
# Per-table writers
# ─────────────────────────────────────────

def _write_scenario_meta(conn, state: SimulationState, name: str, desc: str):
    conn.execute(
        """INSERT INTO scenario_meta
           (name, description, universe_id, universe_name, universe_save_name,
            universe_description, current_age, tick_number, demiurge_id, pantheon_id,
            luminary_production_accum, domain_essence_claimed)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            name,
            desc,
            str(state.universe.id),
            state.universe.name,
            state.universe.save_name,
            state.universe.description,
            state.universe.current_age,
            state.tick_number,
            str(state.demiurge.id),
            str(state.pantheon.id),
            json.dumps(state.luminary_production_this_eval),
            json.dumps(state.domain_essence_claimed),
        ),
    )


def _write_powers(conn, state: SimulationState):
    # Powers are referenced by domains; reconstruct from domain.source_powers
    seen: dict[str, tuple] = {}
    for domain in state.domains.values():
        for pid in domain.source_powers:
            sid = str(pid)
            if sid not in seen:
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
               (id, name, domains, pantheon_id,
                disposition_results, disposition_methods, herald_ids, status_tags,
                essence_received_log, essence_expectation_raised,
                consecutive_essence_shortfalls)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(luminary.id),
                luminary.name,
                _j(luminary.domains),
                str(luminary.pantheon_id) if luminary.pantheon_id else None,
                luminary.disposition.results,
                luminary.disposition.methods,
                _j(luminary.herald_ids),
                _j(luminary.status_tags),
                json.dumps(luminary.essence_received_log),
                luminary.essence_expectation_raised,
                luminary.consecutive_essence_shortfalls,
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


def _loc_subclass(loc: Location) -> str:
    if isinstance(loc, SignificantLocation):
        return "significant_location"
    if isinstance(loc, System):
        return "system"
    if isinstance(loc, PopLocation):
        return "pop_location"
    return "location"


def _write_locations(conn, state: SimulationState):
    for loc in state.locations.values():
        subclass = _loc_subclass(loc)

        # Common fields
        parent_id_str = str(loc.parent_id) if loc.parent_id else None

        # Coordinates — present on all location types
        coords_x = loc.coordinates.x
        coords_y = loc.coordinates.y
        coords_z = loc.coordinates.z

        # Type-specific field defaults
        star_type = "main_sequence"
        domain_expression = "{}"
        lf_overt = lf_subtle = lf_proxius = lf_direct = 0.0
        civilization_ids = species_ids = proxius_ids = herald_ids_loc = "[]"
        geo_tags = atmo_tags = "[]"
        age = 0.0
        pop_ids = "[]"

        if isinstance(loc, System):
            star_type = loc.star_type.value
        elif isinstance(loc, SignificantLocation):
            domain_expression = _j(loc.domain_expression)
            lf = loc.local_footprint
            lf_overt   = lf.overt_miracles
            lf_subtle  = lf.subtle_influence
            lf_proxius = lf.proxius_activity
            lf_direct  = lf.direct_creation
            civilization_ids = _j(loc.civilization_ids)
            species_ids      = _j(loc.species_ids)
            proxius_ids      = _j(loc.proxius_ids)
            herald_ids_loc   = _j(loc.herald_ids)
            geo_tags  = _j(loc.geo_tags)
            atmo_tags = _j(loc.atmo_tags)
            age = loc.age
        elif isinstance(loc, PopLocation):
            pop_ids = _j(loc.pop_ids)

        conn.execute(
            """INSERT INTO locations
               (id, name, description, location_type, subclass, parent_id, child_ids,
                traits, condition,
                coordinates_x, coordinates_y, coordinates_z, star_type,
                domain_expression,
                lf_overt_miracles, lf_subtle_influence, lf_proxius_activity, lf_direct_creation,
                civilization_ids, species_ids, proxius_ids, herald_ids_loc,
                geo_tags, atmo_tags, age,
                pop_ids, visibility, pinned)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?,
                       ?, ?, ?, ?,
                       ?,
                       ?, ?, ?, ?,
                       ?, ?, ?, ?,
                       ?, ?, ?,
                       ?, ?, ?)""",
            (
                str(loc.id),
                loc.name,
                loc.description,
                loc.location_type,
                subclass,
                parent_id_str,
                _j(loc.child_ids),
                _j(loc.traits),
                loc.condition.value,
                coords_x, coords_y, coords_z,
                star_type,
                domain_expression,
                lf_overt, lf_subtle, lf_proxius, lf_direct,
                civilization_ids, species_ids, proxius_ids, herald_ids_loc,
                geo_tags, atmo_tags, age,
                pop_ids, loc.visibility, int(loc.pinned),
            ),
        )


def _write_species(conn, state: SimulationState):
    for sp in state.species.values():
        conn.execute(
            """INSERT INTO species
               (id, name, description, origin_world_id, sapient, transplanted,
                lifespan_min, lifespan_max, domain_tags, bio_tags, condition,
                visibility, pinned)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(sp.id),
                sp.name,
                sp.description,
                str(sp.origin_world_id) if sp.origin_world_id else None,
                int(sp.sapient),
                int(sp.transplanted),
                sp.lifespan_min,
                sp.lifespan_max,
                _j(sp.domain_tags),
                _j(sp.bio_tags),
                sp.condition.value,
                sp.visibility,
                int(sp.pinned),
            ),
        )


def _write_civilizations(conn, state: SimulationState):
    for c in state.civilizations.values():
        conn.execute(
            """INSERT INTO civilizations
               (id, name, description, origin_location_id, scale,
                health_stability, health_prosperity, health_cohesion,
                primary_species_id, dominant_beliefs, culture_tags,
                theistic, divine_awareness, age, visibility, pinned)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(c.id),
                c.name,
                c.description,
                str(c.origin_location_id) if c.origin_location_id else None,
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
                c.visibility,
                int(c.pinned),
            ),
        )


def _write_mortals(conn, state: SimulationState):
    for m in state.mortals.values():
        conn.execute(
            """INSERT INTO mortals
               (id, name, description, civilization_id, role, status,
                species_id, prominence_roles, prominence, visibility,
                belief_tags, personal_tags, culture_tags,
                alignment, chrono_age, bio_age,
                appointed_by_demiurge, appointed_by_luminary,
                home_location, current_location, starting_visible, pinned,
                active_goal_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(m.id),
                m.name,
                m.description,
                str(m.civilization_id) if m.civilization_id else None,
                m.role.value,
                m.status.value,
                str(m.species_id) if m.species_id else None,
                _j([r.value for r in m.prominence_roles]),
                m.prominence,
                m.visibility,
                _j(m.belief_tags),
                _j(m.personal_tags),
                _j(m.culture_tags),
                m.alignment,
                m.chrono_age,
                m.bio_age,
                str(m.appointed_by_demiurge) if m.appointed_by_demiurge else None,
                str(m.appointed_by_luminary) if m.appointed_by_luminary else None,
                str(m.home_location),
                str(m.current_location),
                int(m.starting_visible),
                int(m.pinned),
                m.active_goal.model_dump_json() if m.active_goal else None,
            ),
        )


def _write_demiurge(conn, state: SimulationState):
    d  = state.demiurge
    fp = d.footprint
    conn.execute(
        """INSERT INTO demiurge
           (id, name, liege_luminary_ids, granted_domains,
            fp_overt_miracles, fp_subtle_influence,
            fp_proxius_activity, fp_direct_creation,
            proxius_ids, unlocked_domain_tags, unlocked_imagines,
            affiliated_domains, tracked_essence_domains)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            _j(d.unlocked_domain_tags),
            _j(d.unlocked_imagines),
            _j(d.affiliated_domains),
            _j(d.tracked_essence_domains),
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
            mortal_visibility_decay_rate, proxius_passive_footprint_rate,
            location_visibility_decay_rate, civ_visibility_decay_rate,
            species_visibility_decay_rate, starting_visible_decay_rate)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            cfg.location_visibility_decay_rate,
            cfg.civ_visibility_decay_rate,
            cfg.species_visibility_decay_rate,
            cfg.starting_visible_decay_rate,
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


def _write_active_events(conn, state: SimulationState):
    for eid, ev in state.active_events.items():
        dv_json = json.dumps([
            {"domain_tag": dv.domain_tag, "direction": dv.direction, "notes": dv.notes}
            for dv in ev.domain_vectors
        ])
        conn.execute(
            """INSERT INTO active_events
               (id, event_type, curve, source_action_id, created_at_tick,
                duration, base_strength, peak_offset, decay_rate,
                target_world_id, target_civilization_id, target_mortal_id,
                domain_vectors, domain_shift_rate, divine_awareness_rate,
                attention_per_tick, imago_node_id, framing,
                sign_description, concept)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(ev.id),
                ev.event_type.value,
                ev.curve.value,
                str(ev.source_action_id) if ev.source_action_id else None,
                ev.created_at_tick,
                ev.duration,
                ev.base_strength,
                ev.peak_offset,
                ev.decay_rate,
                str(ev.target_world_id) if ev.target_world_id else None,
                str(ev.target_civilization_id) if ev.target_civilization_id else None,
                str(ev.target_mortal_id) if ev.target_mortal_id else None,
                dv_json,
                ev.domain_shift_rate,
                ev.divine_awareness_rate,
                ev.attention_per_tick,
                ev.imago_node_id,
                ev.framing,
                ev.sign_description,
                ev.concept,
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
# SCENARIO DEFINITION
# The Warden's Compact — canonical starting state for wardens_compact.db.
# ─────────────────────────────────────────

def build_scenario_default() -> SimulationState:
    """
    Scenario: 'The Warden's Compact'

    You are Demiurge of a young universe with two inhabited worlds and one
    barren candidate for seeding. Your two liege Luminaries have contradictory
    natures:
      - Cassiel, Luminary of Order and Silence — stable, authoritative, demands subtlety
      - Vrath, Luminary of Conflict and Change — volatile, harsh, demands results fast

    The Pantheon expects subtlety. Vrath privately does not care,
    but expects civilizational Domain alignment toward conflict within
    a short window. The tension is immediate.

    Spatial layout:
      The Nascent Coil (galaxy)
        Ardent System
          Neran          — stable, interstellar civilization (domain:order)
          Vel Arath      — barren, no life; candidate for seed_world
        The Outer Reach (system)
          Oros           — stable, nascent tribal society (domain:conflict seeds)
        Irriman System   [hidden]
          Kiddis         — stable world, Damtal species
        The Velar Corridor [hidden, dwarf star]
          Sethis         — Neran Confederacy frontier colony
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
        domains={"domain:order": 0.8, "domain:silence": 0.8},
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
        domains={"domain:conflict": 0.8, "domain:change": 0.8},
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

    # ── Spatial hierarchy (new Location model) ────────
    galaxy = Location(
        name="The Nascent Coil",
        location_type="galaxy",
        coordinates=CosmicCoordinates(x=0.0, y=0.0, z=0.0),
        visibility=1.0, pinned=True,
    )

    system = System(
        name="Ardent System",
        parent_id=galaxy.id,
        star_type=StarType.MAIN_SEQUENCE,
        visibility=1.0, pinned=True,
    )
    neran = SignificantLocation(
        name="Neran",
        location_type="planet",
        parent_id=system.id,
        condition=LocCondition.STABLE,
        domain_expression={"domain:order": 0.6},
        geo_tags=["geo:terrestrial", "geo:temperate"],
        atmo_tags=["atmo:nitrogen_oxygen"],
        age=600.0,
        visibility=1.0, pinned=True,
    )
    vel_arath = SignificantLocation(
        name="Vel Arath",
        location_type="planet",
        parent_id=system.id,
        condition=LocCondition.BARREN,
        geo_tags=["geo:rocky", "geo:barren"],
        atmo_tags=["atmo:none"],
        age=900.0,
        visibility=1.0, pinned=True,
    )

    galaxy.child_ids.append(system.id)
    system.child_ids.append(neran.id)
    system.child_ids.append(vel_arath.id)

    system_outer = System(
        name="The Outer Reach",
        parent_id=galaxy.id,
        star_type=StarType.DWARF,
        coordinates=CosmicCoordinates(x=12.0, y=3.0, z=-2.0),
        visibility=1.0, pinned=True,
    )
    oros = SignificantLocation(
        name="Oros",
        location_type="planet",
        parent_id=system_outer.id,
        condition=LocCondition.STABLE,
        domain_expression={"domain:conflict": 0.5},
        geo_tags=["geo:terrestrial", "geo:arid"],
        atmo_tags=["atmo:nitrogen_oxygen"],
        age=275.0,
        visibility=1.0, pinned=True,
    )

    galaxy.child_ids.append(system_outer.id)
    system_outer.child_ids.append(oros.id)

    system_hidden = System(
        name="Irriman System",
        parent_id=galaxy.id,
        star_type=StarType.MAIN_SEQUENCE,
        coordinates=CosmicCoordinates(x=-5.0, y=-2.0, z=1.0),
        visibility=0.0, pinned=False,
    )
    kiddis = SignificantLocation(
        name="Kiddis",
        location_type="planet",
        parent_id=system_hidden.id,
        condition=LocCondition.STABLE,
        domain_expression={"domain:growth":0.3},
        geo_tags=["geo:terrestrial", "geo:humid"],
        atmo_tags=["atmo:nitrogen_oxygen", "atmo:high_co2"],
        age=248.0,
        visibility=0.0, pinned=False,
    )

    galaxy.child_ids.append(system_hidden.id)
    system_hidden.child_ids.append(kiddis.id)

    system_colony = System(
        name="The Velar Corridor",
        parent_id=galaxy.id,
        star_type=StarType.DWARF,
        coordinates=CosmicCoordinates(x=8.0, y=4.0, z=-2.0),
        visibility=0.0, pinned=False,
    )
    sethis = SignificantLocation(
        name="Sethis",
        description="A frontier colony established by the Neran Confederacy. Order-aligned but still finding its footing.",
        location_type="planet",
        parent_id=system_colony.id,
        condition=LocCondition.STABLE,
        domain_expression={"domain:order": 0.2},
        geo_tags=["geo:terrestrial", "geo:arid"],
        atmo_tags=["atmo:nitrogen_oxygen"],
        age=60.0,
        visibility=0.0, pinned=False,
    )
    galaxy.child_ids.append(system_colony.id)
    system_colony.child_ids.append(sethis.id)

    # ── Second galaxy: The Pale Margin ────────────────
    # A distant, lightless cluster of spent stars —
    # coordinates at (3, 1, 0) in galaxy-space, putting
    # it ~3162 effective units from the Nascent Coil.
    galaxy_b = Location(
        name="The Pale Margin",
        location_type="galaxy",
        description="A ragged cluster of dimming stars at the edge of known space. No sapient life has been detected.",
        coordinates=CosmicCoordinates(x=3.0, y=1.0, z=0.0),
        visibility=0.0, pinned=False,
    )

    system_b1 = System(
        name="Sullen Eye",
        parent_id=galaxy_b.id,
        star_type=StarType.GIANT,
        coordinates=CosmicCoordinates(x=2.0, y=-1.0, z=0.5),
        visibility=0.0, pinned=False,
    )
    cinder = SignificantLocation(
        name="Cinder",
        description="A scorched, airless rock. Whatever once lived here left no trace.",
        location_type="planet",
        parent_id=system_b1.id,
        condition=LocCondition.BARREN,
        geo_tags=["geo:rocky", "geo:barren"],
        atmo_tags=["atmo:none"],
        age=1800.0,
        visibility=0.0, pinned=False,
    )

    system_b2 = System(
        name="The Drift",
        parent_id=galaxy_b.id,
        star_type=StarType.DWARF,
        coordinates=CosmicCoordinates(x=-1.0, y=2.0, z=-1.0),
        visibility=0.0, pinned=False,
    )

    galaxy_b.child_ids.extend([system_b1.id, system_b2.id])
    system_b1.child_ids.append(cinder.id)

    # ── Species ───────────────────────────────────────
    naran_species = Species(
        name="Naran",
        description="Humanoid species native to Neran. Ordered society, long memory.",
        origin_world_id=neran.id,
        sapient=True,
        lifespan_min=240,
        lifespan_max=340,
        bio_tags=["bio:bipedal", "bio:warm_blooded", "bio:carbon_based"],
        condition=SpeciesCondition.STABLE,
        visibility=1.0, pinned=True,
    )
    neran.species_ids.append(naran_species.id)

    ultir_species = Species(
        name="Ultir",
        description="Deep-ocean, near-sapient species native to Neran.",
        origin_world_id=neran.id,
        sapient=False,
        lifespan_min=620,
        lifespan_max=860,
        bio_tags=["bio:water-breathing", "bio:radial_symm", "bio:carbon_based"],
        condition=SpeciesCondition.ENDANGERED,
        visibility=0.0, pinned=False,
    )
    neran.species_ids.append(ultir_species.id)

    keth_species = Species(
        name="Keth",
        description="Nomadic humanoids of Oros. Pack-bonded, spiritually attuned.",
        origin_world_id=oros.id,
        sapient=True,
        lifespan_min=200,
        lifespan_max=280,
        bio_tags=["bio:bipedal", "bio:nocturnal", "bio:carbon_based"],
        condition=SpeciesCondition.STABLE,
        visibility=1.0, pinned=True,
    )
    oros.species_ids.append(keth_species.id)

    damtal_species = Species(
        name="Damtal",
        description="",
        origin_world_id=kiddis.id,
        sapient=True,
        lifespan_min=60,
        lifespan_max=100,
        bio_tags=["bio:quadripedal", "bio:warm_blooded", "bio:silicon_based"],
        condition=SpeciesCondition.STABLE,
        visibility=0.0, pinned=False,
    )
    kiddis.species_ids.append(damtal_species.id)

    # ── Civilizations ─────────────────────────────────
    neran_confed = Civilization(
        name="The Neran Confederacy",
        origin_location_id=neran.id,
        scale=CivilizationScale.INTERSTELLAR,
        health=CivilizationHealth(stability=0.6, prosperity=0.5, cohesion=0.55),
        primary_species_id=naran_species.id,
        dominant_beliefs={"domain:order": 0.8, "domain:mastery": 0.5},
        culture_tags={
            "practice:sedentism": 0.90, "structure:hierarchy": 0.85,
            "techno:industrialism": 0.80, "relations:commerce": 0.75,
            "relations:diplomacy": 0.70, "techno:science": 0.65,
            "religion:luminary_worship": 0.60, "religion:ancestor_worship": 0.50,
        },
        theistic=True,
        divine_awareness=0.25,
        age=400.0,
        visibility=1.0, pinned=True,
    )
    neran.civilization_ids.append(neran_confed.id)
    sethis.civilization_ids.append(neran_confed.id)

    keth_civ = Civilization(
        name="The Keth Wanderers",
        origin_location_id=oros.id,
        scale=CivilizationScale.TRIBAL,
        health=CivilizationHealth(stability=0.4, prosperity=0.3, cohesion=0.65),
        primary_species_id=keth_species.id,
        dominant_beliefs={"domain:conflict": 0.7, "domain:memory": 0.5},
        culture_tags={
            "practice:nomadism": 0.95, "religion:ancestor_worship": 0.85,
            "religion:animism": 0.80, "practice:foraging": 0.70,
            "relations:conquest": 0.60, "structure:egalitarianism": 0.50,
        },
        theistic=False,
        divine_awareness=0.10,
        age=60.0,
        visibility=1.0, pinned=True,
    )
    oros.civilization_ids.append(keth_civ.id)

    damtal_civ = Civilization(
        name="Kingdoms of the Damtal",
        origin_location_id=kiddis.id,
        scale=CivilizationScale.CONTINENTAL,
        health=CivilizationHealth(stability=0.5, prosperity=0.35, cohesion=0.2),
        primary_species_id=damtal_species.id,
        dominant_beliefs={},
        culture_tags={},
        theistic=False,
        divine_awareness=0.0,
        age=260.0,
        visibility=0.0, pinned=False,
    )
    kiddis.civilization_ids.append(damtal_civ.id)

    # ── Notable Mortals ───────────────────────────────
    senna = NotableMortal(
        name="Senna Vaur", civilization_id=neran_confed.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=naran_species.id,
        prominence_roles=[MortalProminence.LEADER], prominence=0.65, visibility=1.0,
        personal_tags=["domain:order", "status:senator", "personal:ambitious", "personal:pragmatic"],
        culture_tags={"structure:hierarchy": 0.80, "relations:diplomacy": 0.80, "practice:sedentism": 0.80},
        alignment=0.75, chrono_age=170.0, bio_age=170.0,
        home_location=neran.id, current_location=neran.id,
        starting_visible=True,
    )
    neran_confed.notable_mortal_ids.append(senna.id)

    karath = NotableMortal(
        name="Karath Omn", civilization_id=neran_confed.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=naran_species.id,
        prominence_roles=[MortalProminence.MILITARY], prominence=0.80, visibility=1.0,
        personal_tags=["domain:conflict", "domain:mastery", "status:commander", "personal:ambitious", "personal:ruthless"],
        culture_tags={"structure:hierarchy": 0.90, "practice:sedentism": 0.80, "techno:industrialism": 0.70},
        alignment=0.45, chrono_age=205.0, bio_age=205.0,
        home_location=neran.id, current_location=neran.id,
        starting_visible=True,
    )
    neran_confed.notable_mortal_ids.append(karath.id)

    veth = NotableMortal(
        name="Veth Sarai", civilization_id=neran_confed.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=naran_species.id,
        prominence_roles=[MortalProminence.PRIEST], prominence=0.70, visibility=1.0,
        personal_tags=["domain:order", "domain:silence", "status:high_priest", "personal:devout", "personal:cautious"],
        culture_tags={"religion:luminary_worship": 0.90, "religion:ancestor_worship": 0.80, "practice:sedentism": 0.80},
        alignment=0.85, chrono_age=260.0, bio_age=260.0,
        home_location=neran.id, current_location=neran.id,
        starting_visible=True,
    )
    neran_confed.notable_mortal_ids.append(veth.id)

    durenn = NotableMortal(
        name="Durenn Vail", civilization_id=neran_confed.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=naran_species.id,
        prominence_roles=[MortalProminence.MERCHANT], prominence=0.55, visibility=0.6,
        personal_tags=["domain:community", "domain:order", "status:trade_magnate", "personal:opportunistic", "personal:pragmatic"],
        culture_tags={"relations:commerce": 0.85, "practice:sedentism": 0.80, "structure:hierarchy": 0.70},
        alignment=0.35, chrono_age=235.0, bio_age=235.0,
        home_location=neran.id, current_location=neran.id,
        starting_visible=True,
    )
    neran_confed.notable_mortal_ids.append(durenn.id)

    asha = NotableMortal(
        name="Asha Keln", civilization_id=keth_civ.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=keth_species.id,
        prominence_roles=[MortalProminence.LEADER, MortalProminence.MILITARY],
        prominence=0.75, visibility=1.0,
        personal_tags=["domain:conflict", "domain:change", "status:tribal_leader", "personal:spiritual"],
        culture_tags={"practice:nomadism": 0.90, "religion:animism": 0.85, "relations:conquest": 0.80},
        alignment=0.60, chrono_age=145.0, bio_age=145.0,
        home_location=oros.id, current_location=oros.id,
        starting_visible=True,
    )
    keth_civ.notable_mortal_ids.append(asha.id)

    orryn = NotableMortal(
        name="Orryn Vel", civilization_id=neran_confed.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=naran_species.id,
        prominence_roles=[MortalProminence.REBEL], prominence=0.40, visibility=0.0,
        personal_tags=["domain:change", "domain:conflict", "status:dissident", "personal:agitator", "personal:charismatic"],
        culture_tags={"techno:science": 0.80, "practice:sedentism": 0.70},
        alignment=0.20, chrono_age=155.0, bio_age=155.0,
        home_location=neran.id, current_location=neran.id,
    )
    neran_confed.notable_mortal_ids.append(orryn.id)

    thessal = NotableMortal(
        name="Thessal Dour", civilization_id=neran_confed.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=naran_species.id,
        prominence_roles=[MortalProminence.SCHOLAR], prominence=0.30, visibility=0.0,
        personal_tags=["domain:order", "domain:silence", "personal:obsessive", "personal:reclusive"],
        culture_tags={"techno:science": 0.90, "practice:sedentism": 0.80},
        alignment=0.55, chrono_age=190.0, bio_age=190.0,
        home_location=neran.id, current_location=neran.id,
    )
    neran_confed.notable_mortal_ids.append(thessal.id)

    maeva = NotableMortal(
        name="Maeva Sorn", civilization_id=neran_confed.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=naran_species.id,
        prominence_roles=[MortalProminence.PRIEST], prominence=0.25, visibility=0.0,
        personal_tags=["domain:silence", "domain:order", "personal:devout", "personal:receptive"],
        culture_tags={"religion:luminary_worship": 0.90, "religion:ancestor_worship": 0.85, "practice:sedentism": 0.80},
        alignment=0.70, chrono_age=85.0, bio_age=85.0,
        home_location=neran.id, current_location=neran.id,
    )
    neran_confed.notable_mortal_ids.append(maeva.id)

    kael = NotableMortal(
        name="Kael Ash", civilization_id=keth_civ.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=keth_species.id,
        prominence_roles=[MortalProminence.LEADER], prominence=0.50, visibility=0.0,
        personal_tags=["domain:conflict", "domain:change", "status:clan_elder", "personal:ambitious", "personal:suspicious"],
        culture_tags={"relations:conquest": 0.85, "practice:nomadism": 0.90},
        alignment=0.30, chrono_age=130.0, bio_age=130.0,
        home_location=oros.id, current_location=oros.id,
    )
    keth_civ.notable_mortal_ids.append(kael.id)

    urren = NotableMortal(
        name="Urren", civilization_id=keth_civ.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=keth_species.id,
        prominence_roles=[MortalProminence.PRIEST, MortalProminence.SCHOLAR],
        prominence=0.35, visibility=0.0,
        personal_tags=["domain:change", "domain:memory", "status:shaman", "personal:spiritual", "personal:perceptive"],
        culture_tags={"religion:animism": 0.90, "religion:ancestor_worship": 0.85, "practice:nomadism": 0.80},
        alignment=0.50, chrono_age=175.0, bio_age=175.0,
        home_location=oros.id, current_location=oros.id,
    )
    keth_civ.notable_mortal_ids.append(urren.id)

    korax = NotableMortal(
        name="Korax", civilization_id=None,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=ultir_species.id,
        prominence_roles=[MortalProminence.APEX], prominence=0.16, visibility=0.0,
        personal_tags=["domain:void", "domain:memory", "status:biggest_fish", "personal:almost_sapient", "personal:ambitious"],
        culture_tags={},
        alignment=0.5, chrono_age=534.0, bio_age=534.0,
        home_location=neran.id, current_location=neran.id,
    )

    # ── Demiurge ─────────────────────────────────────
    # Affiliated domains: aggregate affinity sum across all lieges.
    # All 4 liege domains tie at 1.0 each; alphabetical tiebreak.
    demiurge = Demiurge(
        name="The Unnamed",
        liege_luminary_ids=[cassiel.id, vrath.id],
        granted_domains=[d_order.id, d_conflict.id],
        footprint=FootprintProfile(),
        unlocked_imagines=[
            "order:t1:warden",      # Cassiel (Order) — quiet cost of stable boundaries
            "silence:t1:veil",      # Cassiel (Silence) — the concealed god, subtlety mandate
            "conflict:t1:banner",   # Vrath (Conflict) — defiance past the point of hope
            "change:t1:wheel",      # Vrath (Change) — costly, unstoppable transformation
        ],
        affiliated_domains=[
            "domain:change", "domain:conflict", "domain:order", "domain:silence",
        ],
    )

    essence = EssenceStockpile(actual=1.0, apparent=0.0, concealment_integrity=1.0)

    universe = Universe(
        name="Warden's Compact",
        save_name="WC",
        demiurge_id=demiurge.id,
        pantheon_id=pantheon.id,
        rules=rules,
        child_ids=[galaxy.id, galaxy_b.id],
        current_age=600.0,
    )

    return SimulationState(
        universe=universe,
        demiurge=demiurge,
        essence=essence,
        pantheon=pantheon,
        luminaries=luminaries,
        domains=domains,
        locations={
            str(galaxy.id):        galaxy,
            str(system.id):        system,
            str(system_outer.id):  system_outer,
            str(system_hidden.id): system_hidden,
            str(system_colony.id): system_colony,
            str(neran.id):         neran,
            str(vel_arath.id):     vel_arath,
            str(oros.id):          oros,
            str(kiddis.id):        kiddis,
            str(sethis.id):        sethis,
            str(galaxy_b.id):      galaxy_b,
            str(system_b1.id):     system_b1,
            str(system_b2.id):     system_b2,
            str(cinder.id):        cinder,
        },
        civilizations={
            str(neran_confed.id): neran_confed,
            str(keth_civ.id):     keth_civ,
            str(damtal_civ.id):   damtal_civ,
        },
        mortals={
            str(senna.id):   senna,   str(karath.id): karath,
            str(veth.id):    veth,    str(durenn.id): durenn,
            str(asha.id):    asha,    str(orryn.id):  orryn,
            str(thessal.id): thessal, str(maeva.id):  maeva,
            str(kael.id):    kael,    str(urren.id):  urren,
            str(korax.id):   korax,
        },
        species={
            str(naran_species.id):  naran_species,
            str(ultir_species.id):  ultir_species,
            str(keth_species.id):   keth_species,
            str(damtal_species.id): damtal_species,
        },
        civ_momentum={
            str(neran_confed.id): CivilizationMomentum(
                civilization_id=neran_confed.id,
                stability_delta=0.1, prosperity_delta=0.05, cohesion_delta=-0.05,
            ),
            str(keth_civ.id): CivilizationMomentum(
                civilization_id=keth_civ.id,
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

def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        Path(__file__).parent.parent / "scenarios" / "wardens_compact.db"
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

if __name__ == "__main__":
    main()
