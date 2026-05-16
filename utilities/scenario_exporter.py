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
    Disposition, Constraint,
    Luminary, Pantheon, FootprintProfile, Demiurge,
)
from core.universe_core import (
    FootprintTolerances, ProxiiPolicy, UniverseRules,
    Location, System, CosmicCoordinates, StarType,
    SignificantLocation, PopLocation, LocCondition, LocFootprint,
    CivilizationScale, CivilizationHealth, Civilization,
    MortalRole, MortalStatus, MortalProminence, NotableMortal,
    Species, SpeciesCondition,
    Pop, SocialClass,
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
    _write_luminaries(conn, state)
    _write_pantheon(conn, state)
    _write_universe_rules(conn, state)
    _write_locations(conn, state)
    _write_species(conn, state)
    _write_civilizations(conn, state)
    _write_pops(conn, state)
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
            luminary_production_accum, domain_essence_claimed, universe_domain_expression,
            starting_pinned_ids)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            json.dumps(state.universe.universe_domain_expression),
            json.dumps(state.starting_pinned_ids),
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
                primary_species_id, dominant_beliefs, established_beliefs, pop_ids,
                culture_tags, theistic, divine_awareness, age, visibility, pinned)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                _j(c.established_beliefs),
                _j(c.pop_ids),
                _j(c.culture_tags),
                int(c.theistic),
                c.divine_awareness,
                c.age,
                c.visibility,
                int(c.pinned),
            ),
        )


def _write_pops(conn, state: SimulationState):
    for p in state.pops.values():
        conn.execute(
            """INSERT INTO pops
               (id, civilization_id, species_id, social_class, wild_stratum,
                current_location, size_fractional,
                dominant_beliefs, culture_tags, rider_traits,
                notable_mortal_ids, parent_pop_id, child_pop_ids,
                visibility, pinned)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(p.id),
                str(p.civilization_id) if p.civilization_id else None,
                str(p.species_id) if p.species_id else None,
                p.social_class.value if p.social_class else None,
                p.wild_stratum.value if p.wild_stratum else None,
                str(p.current_location),
                p.size_fractional,
                _j(p.dominant_beliefs),
                _j(p.culture_tags),
                _j(p.rider_traits),
                _j(p.notable_mortal_ids),
                str(p.parent_pop_id) if p.parent_pop_id else None,
                _j(p.child_pop_ids),
                p.visibility,
                int(p.pinned),
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
                home_location, current_location, pinned,
                active_goal_json,
                pop_id, proxius_appointed_tick, herald_appointed_tick)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                int(m.pinned),
                m.active_goal.model_dump_json() if m.active_goal else None,
                str(m.pop_id) if m.pop_id else None,
                m.proxius_appointed_tick,
                m.herald_appointed_tick,
            ),
        )


def _write_demiurge(conn, state: SimulationState):
    d  = state.demiurge
    fp = d.footprint
    conn.execute(
        """INSERT INTO demiurge
           (id, name, liege_luminary_ids,
            fp_overt_miracles, fp_subtle_influence,
            fp_proxius_activity, fp_direct_creation,
            proxius_ids, unlocked_domain_tags, unlocked_imagines,
            affiliated_domains, tracked_essence_domains,
            revelation_pools, revealed_imagines)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            str(d.id),
            d.name,
            _j(d.liege_luminary_ids),
            fp.overt_miracles,
            fp.subtle_influence,
            fp.proxius_activity,
            fp.direct_creation,
            _j(d.proxius_ids),
            _j(d.unlocked_domain_tags),
            _j(d.unlocked_imagines),
            _j(d.affiliated_domains),
            _j(d.tracked_essence_domains),
            _j(d.revelation_pools),
            d.revealed_imagines,
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
            species_visibility_decay_rate,
            pop_conformity_base, pop_visibility_drift_rate, established_drift_base)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            cfg.pop_conformity_base,
            cfg.pop_visibility_drift_rate,
            cfg.established_drift_base,
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
          Vel Arath      — barren candidate for seeding (domain:decay)
        The Outer Reach (system)
          Oros           — stable, nascent tribal society (domain:conflict seeds)
        Irriman System   [hidden]
          Kiddis         — stable world, Damtal kingdoms
          Pellum         — barren inner rock
        The Velar Corridor [hidden, dwarf star]
          Sethis         — Neran Confederacy frontier colony; Surathi native clans (domain:community)
      The Pale Margin (galaxy)
        Sullen Eye (giant star)
          Cinder         — scorched barren rock (domain:fire)
        The Drift (dwarf star)
          Mireth         — dim, cold world; Veldan city-state (domain:memory)
      The Sunken Veil (galaxy)
        Amarant System (main sequence)
          Ossian         — Vehn homeworld; interplanetary Quietude civ (domain:silence, domain:truth)
          Lethis         — Vehn colony; no native life (domain:silence, domain:secrecy)
    """

    # ── Luminaries ───────────────────────────────────
    cassiel = Luminary(
        name="Cassiel",
        domains={"domain:order": 0.8, "domain:silence": 0.8},
        disposition=Disposition(results=0.1, methods=0.2),
        constraints=[
            Constraint(
                name="Subtlety Mandate",
                description="Overt miracles must remain minimal.",
                enforcement_weight=0.85,
            ),
            Constraint(
                name="Proxius Restraint",
                description="No more than one Proxius per world.",
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
        description="A dead world slowly dissolving into itself. Dust storms strip the surface bare each cycle.",
        location_type="planet",
        parent_id=system.id,
        condition=LocCondition.BARREN,
        domain_expression={"domain:decay": 0.25},
        geo_tags=["geo:rocky", "geo:barren"],
        atmo_tags=["atmo:none"],
        age=900.0,
        visibility=0.0, pinned=False,
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

    pellum = SignificantLocation(
        name="Pellum",
        description="A scorched inner rock locked in tight orbit around Irriman's star. No atmosphere to speak of; surface cracked with ancient tectonic scars.",
        location_type="planet",
        parent_id=system_hidden.id,
        condition=LocCondition.BARREN,
        domain_expression={"domain:void":0.15},
        geo_tags=["geo:rocky", "geo:barren"],
        atmo_tags=["atmo:none"],
        age=420.0,
        visibility=0.0, pinned=False,
    )

    galaxy.child_ids.append(system_hidden.id)
    system_hidden.child_ids.append(kiddis.id)
    system_hidden.child_ids.append(pellum.id)

    system_colony = System(
        name="The Velar Corridor",
        parent_id=galaxy.id,
        star_type=StarType.DWARF,
        coordinates=CosmicCoordinates(x=8.0, y=4.0, z=-2.0),
        visibility=0.0, pinned=False,
    )
    sethis = SignificantLocation(
        name="Sethis",
        description="A frontier colony established by the Neran Confederacy, sharing the world with the native Surathi clans. The two peoples have begun to trade and intermarry at the margins.",
        location_type="planet",
        parent_id=system_colony.id,
        condition=LocCondition.STABLE,
        domain_expression={"domain:community": 0.25},
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
        description="A scorched, airless rock baked by the bloated giant above it. The surface radiates heat even in the dim light.",
        location_type="planet",
        parent_id=system_b1.id,
        condition=LocCondition.BARREN,
        domain_expression={"domain:fire": 0.35},
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
    mireth = SignificantLocation(
        name="Mireth",
        description="A dim, cold world at the edge of its star's habitable band. The Veldan have endured here for millennia, building their quiet assembly in cavern-cities beneath the ice-crusted plains.",
        location_type="planet",
        parent_id=system_b2.id,
        condition=LocCondition.STABLE,
        domain_expression={"domain:memory": 0.40},
        geo_tags=["geo:terrestrial", "geo:cold"],
        atmo_tags=["atmo:nitrogen_oxygen"],
        age=820.0,
        visibility=0.0, pinned=False,
    )

    galaxy_b.child_ids.extend([system_b1.id, system_b2.id])
    system_b1.child_ids.append(cinder.id)
    system_b2.child_ids.append(mireth.id)

    # ── Third galaxy: The Sunken Veil ─────────────────
    # A sparse cluster of aged stars at the far edge of perception. The Vehn
    # found it suitable precisely because no one else had. Coordinates at
    # (-4, 3, 1.5) place it well away from both inhabited clusters.
    galaxy_c = Location(
        name="The Sunken Veil",
        location_type="galaxy",
        description="A tenuous cluster of aged stars at the far edge of perception. No other sapient life has found it — or if they have, they said nothing.",
        coordinates=CosmicCoordinates(x=-4.0, y=3.0, z=1.5),
        visibility=0.0, pinned=False,
    )

    system_c1 = System(
        name="Amarant System",
        parent_id=galaxy_c.id,
        star_type=StarType.MAIN_SEQUENCE,
        coordinates=CosmicCoordinates(x=1.0, y=-1.0, z=0.0),
        visibility=0.0, pinned=False,
    )
    ossian = SignificantLocation(
        name="Ossian",
        description="The Vehn homeworld: a temperate planet of wide plains and deep cave networks. Most of Vehn civilization lives below the surface, where sound travels differently and silence is easier to keep.",
        location_type="planet",
        parent_id=system_c1.id,
        condition=LocCondition.STABLE,
        domain_expression={"domain:silence": 0.30, "domain:truth": 0.20},
        geo_tags=["geo:terrestrial", "geo:temperate"],
        atmo_tags=["atmo:nitrogen_oxygen"],
        age=750.0,
        visibility=0.0, pinned=False,
    )
    lethis = SignificantLocation(
        name="Lethis",
        description="A dry, windswept world colonized by the Vehn roughly two centuries ago. No native life ever took root here. The Quietude settled it precisely because it was empty — and because emptiness, to them, is a virtue.",
        location_type="planet",
        parent_id=system_c1.id,
        condition=LocCondition.STABLE,
        domain_expression={"domain:silence": 0.25, "domain:secrecy": 0.20},
        geo_tags=["geo:terrestrial", "geo:arid"],
        atmo_tags=["atmo:nitrogen_oxygen"],
        age=620.0,
        visibility=0.0, pinned=False,
    )

    galaxy_c.child_ids.append(system_c1.id)
    system_c1.child_ids.extend([ossian.id, lethis.id])

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
        description="Low-slung quadrupeds of Kiddis. Territorial and hierarchical, with a complex system of clan-kingship that has persisted for centuries.",
        origin_world_id=kiddis.id,
        sapient=True,
        lifespan_min=60,
        lifespan_max=100,
        bio_tags=["bio:quadripedal", "bio:warm_blooded", "bio:silicon_based"],
        condition=SpeciesCondition.STABLE,
        visibility=0.0, pinned=False,
    )
    kiddis.species_ids.append(damtal_species.id)

    surathi_species = Species(
        name="Surathi",
        description="The sun-bronzed native people of Sethis. Clan-based hunter-traders with a rich oral tradition and a pragmatic curiosity about the Naran settlers.",
        origin_world_id=sethis.id,
        sapient=True,
        lifespan_min=90,
        lifespan_max=130,
        bio_tags=["bio:bipedal", "bio:warm_blooded", "bio:carbon_based"],
        # domain_tags=["domain:community"],
        condition=SpeciesCondition.STABLE,
        visibility=0.0, pinned=False,
    )
    sethis.species_ids.append(surathi_species.id)

    veldan_species = Species(
        name="Veldan",
        description="A slow-metabolizing, cold-adapted people native to Mireth. Their cavern-city culture prizes collective memory and deliberate governance over expansion.",
        origin_world_id=mireth.id,
        sapient=True,
        lifespan_min=180,
        lifespan_max=260,
        bio_tags=["bio:bipedal", "bio:cold_blooded", "bio:carbon_based"],
        # domain_tags=["domain:memory"],
        condition=SpeciesCondition.STABLE,
        visibility=0.0, pinned=False,
    )
    mireth.species_ids.append(veldan_species.id)

    vehn_species = Species(
        name="Vehn",
        description="A long-lived, contemplative people native to Ossian. The Vehn communicate through sparse speech woven with elaborate somatic gesture; a long silence in conversation carries as much meaning as words. Their social philosophy treats noise — metaphorical or literal — as a form of pollution.",
        origin_world_id=ossian.id,
        sapient=True,
        lifespan_min=300,
        lifespan_max=420,
        bio_tags=["bio:bipedal", "bio:cold_blooded", "bio:carbon_based"],
        domain_tags=["domain:silence", "domain:secrecy"],
        condition=SpeciesCondition.STABLE,
        visibility=0.0, pinned=False,
    )
    ossian.species_ids.append(vehn_species.id)

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
        description="A fractious collection of clan-kingdoms spread across Kiddis's major continents. United in name by the Paramount King, divided in practice by ancient territorial rivalries.",
        origin_location_id=kiddis.id,
        scale=CivilizationScale.CONTINENTAL,
        health=CivilizationHealth(stability=0.5, prosperity=0.35, cohesion=0.2),
        primary_species_id=damtal_species.id,
        dominant_beliefs={"domain:growth": 0.45, "domain:community": 0.35, "domain:mastery": 0.25},
        culture_tags={
            "structure:hierarchy": 0.80, "religion:animism": 0.70,
            "practice:agriculture": 0.65, "practice:sedentism": 0.60,
            "relations:conquest": 0.55, "religion:ancestor_worship": 0.50,
        },
        theistic=False,
        divine_awareness=0.10,
        age=260.0,
        visibility=0.0, pinned=False,
    )
    kiddis.civilization_ids.append(damtal_civ.id)

    surathi_clans = Civilization(
        name="The Surathi Clans",
        description="The loose confederation of nomadic Surathi hunter-clans who ranged across Sethis long before the Naran colony ships arrived. They watch the settlers with cautious pragmatism.",
        origin_location_id=sethis.id,
        scale=CivilizationScale.TRIBAL,
        health=CivilizationHealth(stability=0.55, prosperity=0.40, cohesion=0.70),
        primary_species_id=surathi_species.id,
        dominant_beliefs={"domain:community": 0.65, "domain:change": 0.30},
        culture_tags={
            "practice:nomadism": 0.90, "religion:animism": 0.80,
            "structure:egalitarianism": 0.70, "practice:foraging": 0.65,
            "relations:commerce": 0.40,
        },
        theistic=False,
        divine_awareness=0.12,
        age=300.0,
        visibility=0.0, pinned=False,
    )
    sethis.civilization_ids.append(surathi_clans.id)

    veldan_assembly = Civilization(
        name="The Veldan Assembly",
        description="A single city-state built across the cavern systems beneath Mireth's largest plateau. Decisions are made by council of memory-keepers whose authority derives from custodianship of the historical record.",
        origin_location_id=mireth.id,
        scale=CivilizationScale.CITY_STATE,
        health=CivilizationHealth(stability=0.70, prosperity=0.45, cohesion=0.80),
        primary_species_id=veldan_species.id,
        dominant_beliefs={"domain:memory": 0.60, "domain:mastery": 0.35},
        culture_tags={
            "practice:sedentism": 0.95, "religion:ancestor_worship": 0.85,
            "techno:science": 0.70, "structure:hierarchy": 0.60,
            "relations:diplomacy": 0.50,
        },
        theistic=True,
        divine_awareness=0.22,
        age=550.0,
        visibility=0.0, pinned=False,
    )
    mireth.civilization_ids.append(veldan_assembly.id)

    vehn_quietude = Civilization(
        name="The Vehn Quietude",
        description="An interplanetary civilization that has mastered the art of not being noticed. The Quietude enforces strict communication silence with any external presence and maintains it internally through a blend of cultural reverence and legal sanction. Their expansion to Lethis was conducted without announcement; they have no interest in being found.",
        origin_location_id=ossian.id,
        scale=CivilizationScale.INTERPLANETARY,
        health=CivilizationHealth(stability=0.72, prosperity=0.50, cohesion=0.88),
        primary_species_id=vehn_species.id,
        dominant_beliefs={
            "domain:silence": 0.70, "domain:secrecy": 0.55,
            "domain:mastery": 0.35, "domain:truth": 0.30,
        },
        culture_tags={
            "practice:sedentism": 0.95, "religion:ancestor_worship": 0.80,
            "structure:hierarchy": 0.70, "techno:science": 0.75,
            "relations:diplomacy": 0.20,
        },
        theistic=True,
        divine_awareness=0.18,
        age=800.0,
        visibility=0.0, pinned=False,
    )
    ossian.civilization_ids.append(vehn_quietude.id)
    lethis.civilization_ids.append(vehn_quietude.id)

    # ── PopLocations and starting Pops ───────────────
    # One PopLocation per inhabited world (surface settlement placeholder).
    # One starting Pop per civilization, mirroring its dominant_beliefs exactly
    # so the simulation baseline is unchanged at tick 0.

    pop_loc_neran = PopLocation(
        name="Neran Surface", location_type="pop_location", parent_id=neran.id,
        visibility=1.0, pinned=True,
    )
    pop_loc_oros = PopLocation(
        name="Oros Surface", location_type="pop_location", parent_id=oros.id,
        visibility=1.0, pinned=True,
    )
    pop_loc_kiddis = PopLocation(
        name="Kiddis Surface", location_type="pop_location", parent_id=kiddis.id,
        visibility=0.0, pinned=False,
    )
    pop_loc_sethis = PopLocation(
        name="Sethis Surface", location_type="pop_location", parent_id=sethis.id,
        visibility=0.0, pinned=False,
    )
    pop_loc_mireth = PopLocation(
        name="Mireth Caverns", location_type="pop_location", parent_id=mireth.id,
        visibility=0.0, pinned=False,
    )
    pop_loc_ossian = PopLocation(
        name="Ossian Surface", location_type="pop_location", parent_id=ossian.id,
        visibility=0.0, pinned=False,
    )

    neran.child_ids.append(pop_loc_neran.id)
    oros.child_ids.append(pop_loc_oros.id)
    kiddis.child_ids.append(pop_loc_kiddis.id)
    sethis.child_ids.append(pop_loc_sethis.id)
    mireth.child_ids.append(pop_loc_mireth.id)
    ossian.child_ids.append(pop_loc_ossian.id)

    pop_loc_neran.pop_ids  # populated below

    # Starting Pops — 2–3 per civilization with class and belief diversity.
    # established_beliefs seeded from the civ's canonical dominant_beliefs (institutional baseline).
    # Pop aggregates differ slightly, creating immediate push/pull tension.
    # Total size_fractional per civ approximates the original single-Pop value.

    # ── Neran Confederacy (INTERSTELLAR): elite technocrats, civilian majority, reform artisans ──
    pop_neran_elite = Pop(
        civilization_id=neran_confed.id, species_id=naran_species.id,
        social_class=SocialClass.ELITE,
        current_location=pop_loc_neran.id,
        size_fractional=2.0,
        dominant_beliefs={"domain:order": 0.90, "domain:mastery": 0.65, "domain:truth": 0.30},
        culture_tags={"structure:hierarchy": 0.95, "relations:diplomacy": 0.80,
                      "techno:science": 0.75, "techno:industrialism": 0.70},
        visibility=1.0, pinned=True,
    )
    pop_neran_common = Pop(
        civilization_id=neran_confed.id, species_id=naran_species.id,
        social_class=SocialClass.COMMON,
        current_location=pop_loc_neran.id,
        size_fractional=6.0,
        dominant_beliefs={"domain:order": 0.75, "domain:mastery": 0.40},
        culture_tags={"practice:sedentism": 0.90, "structure:hierarchy": 0.80,
                      "techno:industrialism": 0.80, "relations:commerce": 0.75,
                      "religion:luminary_worship": 0.60, "religion:ancestor_worship": 0.50},
        visibility=1.0, pinned=True,
    )
    pop_neran_artisan = Pop(
        civilization_id=neran_confed.id, species_id=naran_species.id,
        social_class=SocialClass.ARTISAN,
        current_location=pop_loc_neran.id,
        size_fractional=1.0,
        dominant_beliefs={"domain:mastery": 0.70, "domain:change": 0.35, "domain:order": 0.50},
        culture_tags={"techno:science": 0.85, "techno:industrialism": 0.90,
                      "relations:commerce": 0.70, "practice:sedentism": 0.80},
        visibility=0.0, pinned=False,
    )
    for p in (pop_neran_elite, pop_neran_common, pop_neran_artisan):
        neran_confed.pop_ids.append(p.id)
        pop_loc_neran.pop_ids.append(p.id)
    neran_confed.established_beliefs = dict(neran_confed.dominant_beliefs)

    # ── Keth Wanderers (TRIBAL): warriors dominate, memory-keepers preserve ──
    pop_keth_warrior = Pop(
        civilization_id=keth_civ.id, species_id=keth_species.id,
        social_class=SocialClass.WARRIOR,
        current_location=pop_loc_oros.id,
        size_fractional=2.0,
        dominant_beliefs={"domain:conflict": 0.85, "domain:change": 0.30},
        culture_tags={"practice:nomadism": 0.95, "relations:conquest": 0.80,
                      "structure:egalitarianism": 0.50},
        visibility=1.0, pinned=True,
    )
    pop_keth_common = Pop(
        civilization_id=keth_civ.id, species_id=keth_species.id,
        social_class=SocialClass.COMMON,
        current_location=pop_loc_oros.id,
        size_fractional=3.0,
        dominant_beliefs={"domain:conflict": 0.55, "domain:memory": 0.65},
        culture_tags={"practice:nomadism": 0.95, "religion:ancestor_worship": 0.85,
                      "religion:animism": 0.80, "practice:foraging": 0.70,
                      "structure:egalitarianism": 0.55},
        visibility=0.0, pinned=False,
    )
    for p in (pop_keth_warrior, pop_keth_common):
        keth_civ.pop_ids.append(p.id)
        pop_loc_oros.pop_ids.append(p.id)
    keth_civ.established_beliefs = dict(keth_civ.dominant_beliefs)

    # ── Kingdoms of the Damtal (CONTINENTAL): rival nobles vs. agrarian commons ──
    pop_damtal_elite = Pop(
        civilization_id=damtal_civ.id, species_id=damtal_species.id,
        social_class=SocialClass.ELITE,
        current_location=pop_loc_kiddis.id,
        size_fractional=2.0,
        dominant_beliefs={"domain:mastery": 0.60, "domain:growth": 0.30, "domain:conflict": 0.30},
        culture_tags={"structure:hierarchy": 0.90, "relations:conquest": 0.70,
                      "practice:sedentism": 0.60},
        visibility=0.0, pinned=False,
    )
    pop_damtal_common = Pop(
        civilization_id=damtal_civ.id, species_id=damtal_species.id,
        social_class=SocialClass.COMMON,
        current_location=pop_loc_kiddis.id,
        size_fractional=5.0,
        dominant_beliefs={"domain:growth": 0.55, "domain:community": 0.45},
        culture_tags={"practice:agriculture": 0.80, "practice:sedentism": 0.75,
                      "religion:animism": 0.70, "religion:ancestor_worship": 0.50},
        visibility=0.0, pinned=False,
    )
    for p in (pop_damtal_elite, pop_damtal_common):
        damtal_civ.pop_ids.append(p.id)
        pop_loc_kiddis.pop_ids.append(p.id)
    damtal_civ.established_beliefs = dict(damtal_civ.dominant_beliefs)

    # ── Surathi Clans (TRIBAL): spirit-speaker elders vs. restless hunter commons ──
    pop_surathi_priest = Pop(
        civilization_id=surathi_clans.id, species_id=surathi_species.id,
        social_class=SocialClass.PRIEST,
        current_location=pop_loc_sethis.id,
        size_fractional=1.5,
        dominant_beliefs={"domain:community": 0.70, "domain:memory": 0.40, "domain:growth": 0.20},
        culture_tags={"religion:animism": 0.90, "religion:ancestor_worship": 0.70,
                      "structure:egalitarianism": 0.60},
        visibility=0.0, pinned=False,
    )
    pop_surathi_common = Pop(
        civilization_id=surathi_clans.id, species_id=surathi_species.id,
        social_class=SocialClass.COMMON,
        current_location=pop_loc_sethis.id,
        size_fractional=3.5,
        dominant_beliefs={"domain:community": 0.60, "domain:change": 0.40},
        culture_tags={"practice:nomadism": 0.90, "practice:foraging": 0.65,
                      "structure:egalitarianism": 0.75, "relations:commerce": 0.40},
        visibility=0.0, pinned=False,
    )
    for p in (pop_surathi_priest, pop_surathi_common):
        surathi_clans.pop_ids.append(p.id)
        pop_loc_sethis.pop_ids.append(p.id)
    surathi_clans.established_beliefs = dict(surathi_clans.dominant_beliefs)

    # ── Veldan Assembly (CITY_STATE): memory-keeper council vs. practical craftspeople ──
    pop_veldan_council = Pop(
        civilization_id=veldan_assembly.id, species_id=veldan_species.id,
        social_class=SocialClass.PRIEST,
        current_location=pop_loc_mireth.id,
        size_fractional=2.0,
        dominant_beliefs={"domain:memory": 0.80, "domain:truth": 0.50, "domain:mastery": 0.25},
        culture_tags={"religion:ancestor_worship": 0.90, "techno:science": 0.75,
                      "structure:hierarchy": 0.70, "practice:sedentism": 0.95},
        visibility=0.0, pinned=False,
    )
    pop_veldan_common = Pop(
        civilization_id=veldan_assembly.id, species_id=veldan_species.id,
        social_class=SocialClass.COMMON,
        current_location=pop_loc_mireth.id,
        size_fractional=4.0,
        dominant_beliefs={"domain:memory": 0.50, "domain:mastery": 0.45},
        culture_tags={"practice:sedentism": 0.95, "techno:science": 0.65,
                      "relations:diplomacy": 0.50, "religion:ancestor_worship": 0.70},
        visibility=0.0, pinned=False,
    )
    for p in (pop_veldan_council, pop_veldan_common):
        veldan_assembly.pop_ids.append(p.id)
        pop_loc_mireth.pop_ids.append(p.id)
    veldan_assembly.established_beliefs = dict(veldan_assembly.dominant_beliefs)

    # ── Vehn Quietude (INTERPLANETARY): doctrine-enforcers vs. practical workers ──
    pop_vehn_council = Pop(
        civilization_id=vehn_quietude.id, species_id=vehn_species.id,
        social_class=SocialClass.ELITE,
        current_location=pop_loc_ossian.id,
        size_fractional=2.5,
        dominant_beliefs={"domain:silence": 0.85, "domain:secrecy": 0.70, "domain:truth": 0.35},
        culture_tags={"structure:hierarchy": 0.80, "practice:sedentism": 0.95,
                      "techno:science": 0.70, "religion:ancestor_worship": 0.75},
        visibility=0.0, pinned=False,
    )
    pop_vehn_common = Pop(
        civilization_id=vehn_quietude.id, species_id=vehn_species.id,
        social_class=SocialClass.COMMON,
        current_location=pop_loc_ossian.id,
        size_fractional=5.5,
        dominant_beliefs={"domain:silence": 0.60, "domain:secrecy": 0.45, "domain:mastery": 0.50},
        culture_tags={"practice:sedentism": 0.95, "techno:science": 0.75,
                      "structure:hierarchy": 0.65, "religion:ancestor_worship": 0.80},
        visibility=0.0, pinned=False,
    )
    for p in (pop_vehn_council, pop_vehn_common):
        vehn_quietude.pop_ids.append(p.id)
        pop_loc_ossian.pop_ids.append(p.id)
    vehn_quietude.established_beliefs = dict(vehn_quietude.dominant_beliefs)

    # ── Notable Mortals ───────────────────────────────
    senna = NotableMortal(
        name="Senna Vaur", civilization_id=neran_confed.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=naran_species.id,
        prominence_roles=[MortalProminence.LEADER], prominence=0.65, visibility=1.0,
        personal_tags=["domain:order", "status:senator", "personal:ambitious", "personal:pragmatic"],
        culture_tags={"structure:hierarchy": 0.80, "relations:diplomacy": 0.80, "practice:sedentism": 0.80},
        alignment=0.75, chrono_age=170.0, bio_age=170.0,
        home_location=neran.id, current_location=neran.id,
        pinned=True,
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
        pinned=True,
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
        pinned=True,
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
        pinned=True,
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
        pinned=True,
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

    # ── Sethis mortals — Naran colonists ─────────────
    ren_caleth = NotableMortal(
        name="Ren Caleth", civilization_id=neran_confed.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=naran_species.id,
        prominence_roles=[MortalProminence.LEADER], prominence=0.42, visibility=0.0,
        personal_tags=["domain:order", "domain:community", "status:colony_governor", "personal:pragmatic", "personal:cautious"],
        culture_tags={"structure:hierarchy": 0.80, "relations:diplomacy": 0.75, "practice:sedentism": 0.70},
        alignment=0.65, chrono_age=148.0, bio_age=148.0,
        home_location=sethis.id, current_location=sethis.id,
    )
    neran_confed.notable_mortal_ids.append(ren_caleth.id)

    yssa_tharn = NotableMortal(
        name="Yssa Tharn", civilization_id=neran_confed.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=naran_species.id,
        prominence_roles=[MortalProminence.SCHOLAR], prominence=0.28, visibility=0.0,
        personal_tags=["domain:mastery", "domain:order", "status:colonial_surveyor", "personal:methodical"],
        culture_tags={"techno:science": 0.85, "techno:industrialism": 0.70, "practice:sedentism": 0.65},
        alignment=0.60, chrono_age=112.0, bio_age=112.0,
        home_location=sethis.id, current_location=sethis.id,
    )
    neran_confed.notable_mortal_ids.append(yssa_tharn.id)

    # ── Sethis mortals — Surathi clans ───────────────
    orrath = NotableMortal(
        name="Orrath", civilization_id=surathi_clans.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=surathi_species.id,
        prominence_roles=[MortalProminence.LEADER], prominence=0.50, visibility=0.0,
        personal_tags=["domain:community", "domain:change", "status:clan_elder", "personal:patient", "personal:perceptive"],
        culture_tags={"practice:nomadism": 0.90, "structure:egalitarianism": 0.80, "relations:commerce": 0.45},
        alignment=0.55, chrono_age=74.0, bio_age=74.0,
        home_location=sethis.id, current_location=sethis.id,
    )
    surathi_clans.notable_mortal_ids.append(orrath.id)

    deva = NotableMortal(
        name="Deva", civilization_id=surathi_clans.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=surathi_species.id,
        prominence_roles=[MortalProminence.PRIEST], prominence=0.38, visibility=0.0,
        personal_tags=["domain:community", "domain:memory", "status:spirit_caller", "personal:spiritual", "personal:receptive"],
        culture_tags={"religion:animism": 0.90, "practice:nomadism": 0.85, "religion:ancestor_worship": 0.70},
        alignment=0.62, chrono_age=58.0, bio_age=58.0,
        home_location=sethis.id, current_location=sethis.id,
    )
    surathi_clans.notable_mortal_ids.append(deva.id)

    yakkel = NotableMortal(
        name="Yakkel", civilization_id=surathi_clans.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=surathi_species.id,
        prominence_roles=[MortalProminence.MILITARY], prominence=0.35, visibility=0.0,
        personal_tags=["domain:conflict", "domain:community", "status:hunt_chief", "personal:fierce", "personal:loyal"],
        culture_tags={"practice:nomadism": 0.90, "practice:foraging": 0.80, "relations:conquest": 0.50},
        alignment=0.45, chrono_age=41.0, bio_age=41.0,
        home_location=sethis.id, current_location=sethis.id,
    )
    surathi_clans.notable_mortal_ids.append(yakkel.id)

    # ── Sethis — Surathi convert to the Confederacy ──
    sirak = NotableMortal(
        name="Sirak Vendir", civilization_id=neran_confed.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=surathi_species.id,
        prominence_roles=[MortalProminence.MERCHANT], prominence=0.32, visibility=0.0,
        personal_tags=["domain:community", "domain:order", "status:liaison", "personal:opportunistic", "personal:charismatic"],
        culture_tags={"relations:commerce": 0.80, "relations:diplomacy": 0.70, "structure:hierarchy": 0.50},
        alignment=0.50, chrono_age=36.0, bio_age=36.0,
        home_location=sethis.id, current_location=sethis.id,
    )
    neran_confed.notable_mortal_ids.append(sirak.id)

    # ── Kiddis mortals — Kingdoms of the Damtal ──────
    var_keth = NotableMortal(
        name="Var-Keth", civilization_id=damtal_civ.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=damtal_species.id,
        prominence_roles=[MortalProminence.LEADER], prominence=0.58, visibility=0.0,
        personal_tags=["domain:mastery", "domain:community", "status:paramount_king", "personal:ambitious", "personal:ruthless"],
        culture_tags={"structure:hierarchy": 0.90, "relations:conquest": 0.75, "practice:sedentism": 0.70},
        alignment=0.35, chrono_age=52.0, bio_age=52.0,
        home_location=kiddis.id, current_location=kiddis.id,
    )
    damtal_civ.notable_mortal_ids.append(var_keth.id)

    issel = NotableMortal(
        name="Issel", civilization_id=damtal_civ.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=damtal_species.id,
        prominence_roles=[MortalProminence.PRIEST], prominence=0.48, visibility=0.0,
        personal_tags=["domain:growth", "domain:community", "status:high_priestess", "personal:devout", "personal:patient"],
        culture_tags={"religion:animism": 0.90, "religion:ancestor_worship": 0.80, "practice:sedentism": 0.70},
        alignment=0.65, chrono_age=67.0, bio_age=67.0,
        home_location=kiddis.id, current_location=kiddis.id,
    )
    damtal_civ.notable_mortal_ids.append(issel.id)

    durrak = NotableMortal(
        name="Durrak", civilization_id=damtal_civ.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=damtal_species.id,
        prominence_roles=[MortalProminence.MILITARY], prominence=0.44, visibility=0.0,
        personal_tags=["domain:conflict", "domain:mastery", "status:warlord", "personal:aggressive", "personal:pragmatic"],
        culture_tags={"relations:conquest": 0.85, "structure:hierarchy": 0.80, "practice:sedentism": 0.60},
        alignment=0.25, chrono_age=45.0, bio_age=45.0,
        home_location=kiddis.id, current_location=kiddis.id,
    )
    damtal_civ.notable_mortal_ids.append(durrak.id)

    yellan = NotableMortal(
        name="Yellan", civilization_id=damtal_civ.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=damtal_species.id,
        prominence_roles=[MortalProminence.SCHOLAR], prominence=0.30, visibility=0.0,
        personal_tags=["domain:growth", "domain:memory", "status:lore_keeper", "personal:obsessive", "personal:perceptive"],
        culture_tags={"religion:ancestor_worship": 0.85, "practice:sedentism": 0.80, "techno:science": 0.40},
        alignment=0.55, chrono_age=78.0, bio_age=78.0,
        home_location=kiddis.id, current_location=kiddis.id,
    )
    damtal_civ.notable_mortal_ids.append(yellan.id)

    # ── Mireth mortals — Veldan Assembly ─────────────
    councilor_yeth = NotableMortal(
        name="Yeth Orvain", civilization_id=veldan_assembly.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=veldan_species.id,
        prominence_roles=[MortalProminence.LEADER], prominence=0.52, visibility=0.0,
        personal_tags=["domain:memory", "domain:mastery", "status:first_councilor", "personal:deliberate", "personal:wise"],
        culture_tags={"structure:hierarchy": 0.80, "religion:ancestor_worship": 0.85, "practice:sedentism": 0.90},
        alignment=0.72, chrono_age=198.0, bio_age=198.0,
        home_location=mireth.id, current_location=mireth.id,
    )
    veldan_assembly.notable_mortal_ids.append(councilor_yeth.id)

    keeper_orvan = NotableMortal(
        name="Orvan", civilization_id=veldan_assembly.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=veldan_species.id,
        prominence_roles=[MortalProminence.PRIEST, MortalProminence.SCHOLAR],
        prominence=0.45, visibility=0.0,
        personal_tags=["domain:memory", "domain:silence", "status:archive_keeper", "personal:reclusive", "personal:perceptive"],
        culture_tags={"religion:ancestor_worship": 0.90, "techno:science": 0.80, "practice:sedentism": 0.85},
        alignment=0.68, chrono_age=231.0, bio_age=231.0,
        home_location=mireth.id, current_location=mireth.id,
    )
    veldan_assembly.notable_mortal_ids.append(keeper_orvan.id)

    # ── Ossian mortals — The Vehn Quietude ───────────
    sivel = NotableMortal(
        name="Sivel", civilization_id=vehn_quietude.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=vehn_species.id,
        prominence_roles=[MortalProminence.LEADER], prominence=0.68, visibility=0.0,
        personal_tags=["domain:silence", "domain:truth", "status:first_arbiter", "personal:deliberate", "personal:wise"],
        culture_tags={"structure:hierarchy": 0.80, "practice:sedentism": 0.90, "religion:ancestor_worship": 0.85},
        alignment=0.78, chrono_age=312.0, bio_age=312.0,
        home_location=ossian.id, current_location=ossian.id,
    )
    vehn_quietude.notable_mortal_ids.append(sivel.id)

    orveth = NotableMortal(
        name="Orveth", civilization_id=vehn_quietude.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=vehn_species.id,
        prominence_roles=[MortalProminence.PRIEST, MortalProminence.SCHOLAR],
        prominence=0.50, visibility=0.0,
        personal_tags=["domain:silence", "domain:memory", "status:deep_keeper", "personal:reclusive", "personal:obsessive"],
        culture_tags={"religion:ancestor_worship": 0.95, "practice:sedentism": 0.90, "techno:science": 0.70},
        alignment=0.82, chrono_age=388.0, bio_age=388.0,
        home_location=ossian.id, current_location=ossian.id,
    )
    vehn_quietude.notable_mortal_ids.append(orveth.id)

    valn = NotableMortal(
        name="Valn", civilization_id=vehn_quietude.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=vehn_species.id,
        prominence_roles=[MortalProminence.MILITARY], prominence=0.46, visibility=0.0,
        personal_tags=["domain:mastery", "domain:secrecy", "status:fleet_commander", "personal:pragmatic", "personal:disciplined"],
        culture_tags={"structure:hierarchy": 0.85, "techno:science": 0.80, "practice:sedentism": 0.70},
        alignment=0.60, chrono_age=245.0, bio_age=245.0,
        home_location=ossian.id, current_location=ossian.id,
    )
    vehn_quietude.notable_mortal_ids.append(valn.id)

    taleth = NotableMortal(
        name="Taleth", civilization_id=vehn_quietude.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=vehn_species.id,
        prominence_roles=[MortalProminence.REBEL], prominence=0.32, visibility=0.0,
        personal_tags=["domain:truth", "domain:change", "status:dissident", "personal:agitator", "personal:charismatic"],
        culture_tags={"techno:science": 0.85, "relations:diplomacy": 0.70, "practice:sedentism": 0.60},
        alignment=0.30, chrono_age=178.0, bio_age=178.0,
        home_location=ossian.id, current_location=ossian.id,
    )
    vehn_quietude.notable_mortal_ids.append(taleth.id)

    kern = NotableMortal(
        name="Kern", civilization_id=vehn_quietude.id,
        role=MortalRole.OTHER, status=MortalStatus.ACTIVE, species_id=vehn_species.id,
        prominence_roles=[MortalProminence.LEADER], prominence=0.40, visibility=0.0,
        personal_tags=["domain:silence", "domain:secrecy", "status:colonial_warden", "personal:methodical", "personal:patient"],
        culture_tags={"practice:sedentism": 0.90, "structure:hierarchy": 0.75, "religion:ancestor_worship": 0.70},
        alignment=0.65, chrono_age=207.0, bio_age=207.0,
        home_location=lethis.id, current_location=lethis.id,
    )
    vehn_quietude.notable_mortal_ids.append(kern.id)

    # ── Demiurge ─────────────────────────────────────
    # affiliated_domains left empty — loader derives top-4 from Luminary affinities.
    demiurge = Demiurge(
        name="The Unnamed",
        liege_luminary_ids=[cassiel.id, vrath.id],
        footprint=FootprintProfile(),
        unlocked_imagines=[
            "order:t1:warden",      # Cassiel (Order) — quiet cost of stable boundaries
            "silence:t1:veil",      # Cassiel (Silence) — the concealed god, subtlety mandate
            "conflict:t1:banner",   # Vrath (Conflict) — defiance past the point of hope
            "change:t1:wheel",      # Vrath (Change) — costly, unstoppable transformation
        ],
    )

    essence = EssenceStockpile(actual=1.0, apparent=0.0, concealment_integrity=1.0)

    # Collect all entities pinned at scenario creation; these are unpinned at tick 10.
    _all_scenario_entities: list = [
        galaxy, system, system_outer, system_hidden, system_colony,
        neran, vel_arath, oros, kiddis, pellum, sethis,
        galaxy_b, system_b1, system_b2, cinder, mireth,
        galaxy_c, system_c1, ossian, lethis,
        pop_loc_neran, pop_loc_oros, pop_loc_kiddis,
        pop_loc_sethis, pop_loc_mireth, pop_loc_ossian,
        pop_neran_elite, pop_neran_common, pop_neran_artisan,
        pop_keth_warrior, pop_keth_common,
        pop_damtal_elite, pop_damtal_common,
        pop_surathi_priest, pop_surathi_common,
        pop_veldan_council, pop_veldan_common,
        pop_vehn_council, pop_vehn_common,
        naran_species, ultir_species, keth_species, damtal_species,
        surathi_species, veldan_species, vehn_species,
        neran_confed, keth_civ, damtal_civ, surathi_clans,
        veldan_assembly, vehn_quietude,
        senna, karath, veth, durenn, asha, orryn, thessal, maeva,
        kael, urren, korax,
        ren_caleth, yssa_tharn, orrath, deva, yakkel, sirak,
        var_keth, issel, durrak, yellan,
        councilor_yeth, keeper_orvan, sivel, orveth, valn, taleth, kern,
    ]
    starting_pinned_ids = [str(e.id) for e in _all_scenario_entities if e.pinned]

    universe = Universe(
        name="Warden's Compact",
        save_name="WC",
        demiurge_id=demiurge.id,
        pantheon_id=pantheon.id,
        rules=rules,
        child_ids=[galaxy.id, galaxy_b.id, galaxy_c.id],
        current_age=600.0,
    )

    return SimulationState(
        universe=universe,
        demiurge=demiurge,
        essence=essence,
        pantheon=pantheon,
        luminaries=luminaries,
        locations={
            str(galaxy.id):           galaxy,
            str(system.id):           system,
            str(system_outer.id):     system_outer,
            str(system_hidden.id):    system_hidden,
            str(system_colony.id):    system_colony,
            str(neran.id):            neran,
            str(vel_arath.id):        vel_arath,
            str(oros.id):             oros,
            str(kiddis.id):           kiddis,
            str(pellum.id):           pellum,
            str(sethis.id):           sethis,
            str(galaxy_b.id):         galaxy_b,
            str(system_b1.id):        system_b1,
            str(system_b2.id):        system_b2,
            str(cinder.id):           cinder,
            str(mireth.id):           mireth,
            str(galaxy_c.id):         galaxy_c,
            str(system_c1.id):        system_c1,
            str(ossian.id):           ossian,
            str(lethis.id):           lethis,
            str(pop_loc_neran.id):    pop_loc_neran,
            str(pop_loc_oros.id):     pop_loc_oros,
            str(pop_loc_kiddis.id):   pop_loc_kiddis,
            str(pop_loc_sethis.id):   pop_loc_sethis,
            str(pop_loc_mireth.id):   pop_loc_mireth,
            str(pop_loc_ossian.id):   pop_loc_ossian,
        },
        civilizations={
            str(neran_confed.id):    neran_confed,
            str(keth_civ.id):        keth_civ,
            str(damtal_civ.id):      damtal_civ,
            str(surathi_clans.id):   surathi_clans,
            str(veldan_assembly.id): veldan_assembly,
            str(vehn_quietude.id):   vehn_quietude,
        },
        mortals={
            str(senna.id):          senna,          str(karath.id):       karath,
            str(veth.id):           veth,            str(durenn.id):       durenn,
            str(asha.id):           asha,            str(orryn.id):        orryn,
            str(thessal.id):        thessal,         str(maeva.id):        maeva,
            str(kael.id):           kael,            str(urren.id):        urren,
            str(korax.id):          korax,
            str(ren_caleth.id):     ren_caleth,      str(yssa_tharn.id):   yssa_tharn,
            str(orrath.id):         orrath,          str(deva.id):         deva,
            str(yakkel.id):         yakkel,          str(sirak.id):        sirak,
            str(var_keth.id):       var_keth,        str(issel.id):        issel,
            str(durrak.id):         durrak,          str(yellan.id):       yellan,
            str(councilor_yeth.id): councilor_yeth,  str(keeper_orvan.id): keeper_orvan,
            str(sivel.id):          sivel,            str(orveth.id):       orveth,
            str(valn.id):           valn,             str(taleth.id):       taleth,
            str(kern.id):           kern,
        },
        pops={
            str(pop_neran_elite.id):   pop_neran_elite,
            str(pop_neran_common.id):  pop_neran_common,
            str(pop_neran_artisan.id): pop_neran_artisan,
            str(pop_keth_warrior.id):  pop_keth_warrior,
            str(pop_keth_common.id):   pop_keth_common,
            str(pop_damtal_elite.id):  pop_damtal_elite,
            str(pop_damtal_common.id): pop_damtal_common,
            str(pop_surathi_priest.id): pop_surathi_priest,
            str(pop_surathi_common.id): pop_surathi_common,
            str(pop_veldan_council.id): pop_veldan_council,
            str(pop_veldan_common.id):  pop_veldan_common,
            str(pop_vehn_council.id):   pop_vehn_council,
            str(pop_vehn_common.id):    pop_vehn_common,
        },
        species={
            str(naran_species.id):   naran_species,
            str(ultir_species.id):   ultir_species,
            str(keth_species.id):    keth_species,
            str(damtal_species.id):  damtal_species,
            str(surathi_species.id): surathi_species,
            str(veldan_species.id):  veldan_species,
            str(vehn_species.id):    vehn_species,
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
            str(damtal_civ.id): CivilizationMomentum(
                civilization_id=damtal_civ.id,
                stability_delta=0.0, prosperity_delta=-0.05, cohesion_delta=-0.1,
            ),
            str(surathi_clans.id): CivilizationMomentum(
                civilization_id=surathi_clans.id,
                stability_delta=-0.05, prosperity_delta=0.05, cohesion_delta=0.0,
            ),
            str(veldan_assembly.id): CivilizationMomentum(
                civilization_id=veldan_assembly.id,
                stability_delta=0.05, prosperity_delta=0.0, cohesion_delta=0.05,
            ),
            str(vehn_quietude.id): CivilizationMomentum(
                civilization_id=vehn_quietude.id,
                stability_delta=0.05, prosperity_delta=0.02, cohesion_delta=0.05,
            ),
        },
        luminary_attention={str(cassiel.id): 0.15, str(vrath.id): 0.30},
        ticks_since_evaluation={str(cassiel.id): 0.0, str(vrath.id): 0.0},
        config=TickConfig(tick_duration=0.5, evaluation_interval=5.0),
        starting_pinned_ids=starting_pinned_ids,
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
