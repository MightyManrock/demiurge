#!/usr/bin/env python3
"""
scenario_exporter.py
Writes a SimulationState out to a scenario .db file. The scenario .db is the
authoritative source of truth for any given scenario; this module is the
only writer (paired with utilities/scenario_loader.py as the only reader).

Scenarios are authored through `tools/scenario_builder/` (the TUI builder
or the `--inject` JSON-patch CLI), not generated from Python code. Schema
drift between an existing .db and the current `core/scenario_schema.sql`
is handled by `utilities/scenario_migrator.py`, invoked by
`python main.py --rebuild --scenario` and by the builder when loading.
"""

from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from uuid import UUID

from core.onto_core import (
    Disposition, Constraint, FootprintConstraint, ResultsConstraint,
    Luminary, Pantheon, FootprintProfile, Demiurge,
)
from core.universe_core import (
    FootprintTolerances, ProxiiPolicy, UniverseRules,
    Location, System, CosmicCoordinates, StarType,
    SignificantLocation, PopLocation, TravelLocation, LocCondition, LocFootprint,
    CivilizationScale, CivilizationHealth, Civilization,
    MortalRole, MortalStatus, MortalProminence, NotableMortal,
    Species, SpeciesCondition,
    Pop, SocialClass, WildStratum,
    Universe, TravelNetwork,
)
from core.action_core import EssenceStockpile, CategoryCooldowns
from core.event_core import Event
from logic.tick_logic import SimulationState, CivilizationMomentum, TickConfig, PauseConfig


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
    """Write `state` to `db_path` atomically. The actual write goes to a
    sibling temp file; on success it replaces the destination, on failure
    the original (if any) is left untouched."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = db_path.with_suffix(db_path.suffix + ".tmp")
    if tmp_path.exists():
        tmp_path.unlink()

    conn = sqlite3.connect(tmp_path)
    try:
        conn.executescript(SCHEMA_PATH.read_text())
        _write_scenario_meta(conn, state, scenario_name, description)
        _write_luminaries(conn, state)
        _write_pantheon(conn, state)
        _write_universe_rules(conn, state)
        _write_travel_networks(conn, state)
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
        _write_pending_resume(conn, state)
        _write_active_events(conn, state)
        conn.commit()
    except Exception:
        conn.close()
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise
    else:
        conn.close()
        # Atomic replace — on POSIX, rename is atomic; on Windows it'd fail
        # if the destination exists, so call unlink first.
        if db_path.exists():
            db_path.unlink()
        tmp_path.rename(db_path)
    print(f"Exported scenario to {db_path}")


# ─────────────────────────────────────────
# Per-table writers
# ─────────────────────────────────────────

def _write_scenario_meta(conn, state: SimulationState, name: str, desc: str):
    conn.execute(
        """INSERT INTO scenario_meta
           (name, description, universe_id, universe_name, universe_save_name,
            universe_description, current_age,
            age_billions, age_millions, age_thousands, age_years, age_month, age_day,
            tick_number, demiurge_id, pantheon_id,
            luminary_production_accum, domain_essence_claimed, universe_domain_expression,
            last_tick_essence_by_domain,
            last_essence_capture_by_domain, last_essence_capture_tick,
            last_harvest_amount, last_harvest_tick,
            category_cooldowns, pause_config, rich_log_name)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            name,
            desc,
            str(state.universe.id),
            state.universe.name,
            state.universe.save_name,
            state.universe.description,
            state.universe.age.to_float_years(),
            state.universe.age.billions,
            state.universe.age.millions,
            state.universe.age.thousands,
            state.universe.age.years,
            state.universe.age.month,
            state.universe.age.day,
            state.tick_number,
            str(state.demiurge.id),
            str(state.pantheon.id),
            json.dumps(state.luminary_production_this_eval),
            json.dumps(state.domain_essence_claimed),
            json.dumps(state.universe.universe_domain_expression),
            json.dumps(state.last_tick_essence_by_domain),
            json.dumps(state.last_essence_capture_by_domain),
            state.last_essence_capture_tick,
            state.last_harvest_amount,
            state.last_harvest_tick,
            state.category_cooldowns.model_dump_json(),
            state.pause_config.model_dump_json(),
            state.rich_log_name,
        ),
    )


def _write_luminaries(conn, state: SimulationState):
    for luminary in state.luminaries.values():
        conn.execute(
            """INSERT INTO luminaries
               (id, name, domains, pantheon_id,
                disposition_results, disposition_methods, herald_ids, status_tags,
                essence_received_log, essence_expectation_raised,
                consecutive_essence_shortfalls,
                last_evaluation, previous_evaluation, last_evaluation_tick,
                last_orders_response, last_orders_response_tick)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                json.dumps(luminary.last_evaluation) if luminary.last_evaluation else None,
                json.dumps(luminary.previous_evaluation) if luminary.previous_evaluation else None,
                luminary.last_evaluation_tick,
                luminary.last_orders_response,
                luminary.last_orders_response_tick,
            ),
        )
        for c in luminary.constraints:
            conn.execute(
                """INSERT INTO constraints
                   (id, name, description, domain_tag, enforcement_weight,
                    owner_id, owner_type, constraint_type, footprint_tolerances, min_results)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(c.id),
                    c.name,
                    c.description,
                    c.domain_tag,
                    c.enforcement_weight,
                    str(luminary.id),
                    "luminary",
                    c.constraint_type,
                    json.dumps(c.footprint_tolerances) if isinstance(c, FootprintConstraint) else None,
                    c.min_results if isinstance(c, ResultsConstraint) else None,
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
               (id, name, description, domain_tag, enforcement_weight,
                owner_id, owner_type, constraint_type, footprint_tolerances, min_results)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(c.id),
                c.name,
                c.description,
                c.domain_tag,
                c.enforcement_weight,
                str(p.id),
                "pantheon",
                c.constraint_type,
                json.dumps(c.footprint_tolerances) if isinstance(c, FootprintConstraint) else None,
                c.min_results if isinstance(c, ResultsConstraint) else None,
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


def _write_travel_networks(conn, state: SimulationState):
    for tn in state.travel_networks.values():
        conn.execute(
            "INSERT INTO travel_networks (id, name, member_ids) VALUES (?, ?, ?)",
            (str(tn.id), tn.name, _j(tn.member_ids)),
        )


def _loc_subclass(loc: Location) -> str:
    if isinstance(loc, SignificantLocation):
        return "significant_location"
    if isinstance(loc, System):
        return "system"
    if isinstance(loc, TravelLocation):
        return "travel_location"
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
        pop_ids = "[]"
        distance_from_core = 0
        travel_network_ids_val = "[]"
        commerce_quality = 0.5
        collectible_resource_val = None
        wealth_val = 0.5
        legs = "{}"
        travel_current_wp = ""
        travel_ticks_rem = 0
        travel_occupants = "[]"
        travel_pop_ids_val = "[]"

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
        elif isinstance(loc, PopLocation):
            domain_expression = _j(loc.domain_expression)
            pop_ids = _j(loc.pop_ids)
            distance_from_core = int(loc.distance_from_core)
            travel_network_ids_val = _j(loc.travel_network_ids)
            commerce_quality = loc.commerce_quality
            collectible_resource_val = loc.collectible_resource.model_dump_json() if loc.collectible_resource else None
            wealth_val = loc.wealth
        elif isinstance(loc, TravelLocation):
            legs             = _j(loc.legs)
            travel_current_wp = loc.current_waypoint
            travel_ticks_rem  = loc.ticks_remaining
            travel_occupants  = _j([str(oid) for oid in loc.occupants])
            travel_pop_ids_val = _j([str(pid) for pid in loc.pop_ids])

        # EntityAge fields — same for all location subclasses
        ea = loc.age
        fd = ea.formation_date

        conn.execute(
            """INSERT INTO locations
               (id, name, description, location_type, subclass, parent_id, child_ids,
                traits, condition,
                coordinates_x, coordinates_y, coordinates_z, star_type,
                domain_expression,
                lf_overt_miracles, lf_subtle_influence, lf_proxius_activity, lf_direct_creation,
                civilization_ids, species_ids, proxius_ids, herald_ids_loc,
                geo_tags, atmo_tags,
                age_billions, age_millions, age_thousands, age_years, age_month, age_day,
                formation_billions, formation_millions, formation_thousands,
                formation_year, formation_month, formation_day,
                pop_ids, distance_from_core,
                legs, travel_current_wp, travel_ticks_rem, travel_occupants, travel_pop_ids, travel_network_ids,
                commerce_quality, collectible_resource, wealth,
                visibility, pinned, visibility_stall_remaining)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?,
                       ?, ?, ?, ?,
                       ?,
                       ?, ?, ?, ?,
                       ?, ?, ?, ?,
                       ?, ?,
                       ?, ?, ?, ?, ?, ?,
                       ?, ?, ?, ?, ?, ?,
                       ?, ?,
                       ?, ?, ?, ?, ?, ?,
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
                geo_tags, atmo_tags,
                ea.billions, ea.millions, ea.thousands, ea.years, ea.month, ea.day,
                fd[0], fd[1], fd[2], fd[3], fd[4], fd[5],
                pop_ids, distance_from_core,
                legs, travel_current_wp, travel_ticks_rem, travel_occupants, travel_pop_ids_val, travel_network_ids_val,
                commerce_quality, collectible_resource_val, wealth_val,
                loc.visibility, int(loc.pinned), loc.visibility_stall_remaining,
            ),
        )


def _write_species(conn, state: SimulationState):
    for sp in state.species.values():
        conn.execute(
            """INSERT INTO species
               (id, name, description, origin_world_id, sapient, transplanted,
                lifespan_min, lifespan_max, domain_tags, bio_tags, condition,
                visibility, pinned, visibility_stall_remaining)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                sp.visibility_stall_remaining,
            ),
        )


def _write_civilizations(conn, state: SimulationState):
    for c in state.civilizations.values():
        # core_locs: default to [origin_location_id] if not explicitly set
        core_locs = list(c.core_locs)
        if not core_locs and c.origin_location_id:
            core_locs = [c.origin_location_id]
        ea = c.age
        fd = ea.formation_date
        conn.execute(
            """INSERT INTO civilizations
               (id, name, description, origin_location_id, scale,
                health_stability, health_wealth, health_cohesion,
                primary_species_id, dominant_beliefs, established_beliefs, pop_ids,
                culture_tags, established_culture_tags,
                theistic, divine_awareness, core_locs,
                age_billions, age_millions, age_thousands, age_years, age_month, age_day,
                founding_billions, founding_millions, founding_thousands,
                founding_year, founding_month, founding_day,
                visibility, pinned, visibility_stall_remaining)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                       ?, ?, ?, ?, ?, ?,
                       ?, ?, ?, ?, ?, ?,
                       ?, ?, ?)""",
            (
                str(c.id),
                c.name,
                c.description,
                str(c.origin_location_id) if c.origin_location_id else None,
                c.scale.value,
                c.health.stability,
                c.health.wealth,
                c.health.cohesion,
                str(c.primary_species_id) if c.primary_species_id else None,
                _j(c.dominant_beliefs),
                _j(c.established_beliefs),
                _j(c.pop_ids),
                _j(c.culture_tags),
                _j(c.established_culture_tags),
                int(c.theistic),
                c.divine_awareness,
                json.dumps([str(x) for x in core_locs]),
                ea.billions, ea.millions, ea.thousands, ea.years, ea.month, ea.day,
                fd[0], fd[1], fd[2], fd[3], fd[4], fd[5],
                c.visibility,
                int(c.pinned),
                c.visibility_stall_remaining,
            ),
        )


def _write_pops(conn, state: SimulationState):
    for p in state.pops.values():
        conn.execute(
            """INSERT INTO pops
               (id, name, demiurge_authored, civilization_id, species_id,
                social_class, wild_stratum,
                current_location, size_fractional,
                dominant_beliefs, culture_tags, rider_traits,
                notable_mortal_ids, parent_pop_id, child_pop_ids, splinter_cooldown,
                identity_anchor,
                visibility, pinned, visibility_stall_remaining,
                preaching_imago_id, preaching_goal_cooldown_until,
                occupation, linked_pop_ids, active_directives, asset_crew_for)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(p.id),
                p.name,
                int(p.demiurge_authored),
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
                p.splinter_cooldown,
                _j(p.identity_anchor) if p.identity_anchor else None,
                p.visibility,
                int(p.pinned),
                p.visibility_stall_remaining,
                p.preaching_imago_id,
                p.preaching_goal_cooldown_until,
                p.occupation,
                _j(p.linked_pop_ids),
                _j([d.model_dump() for d in p.active_directives]),
                p.asset_crew_for,
            ),
        )


def _write_mortals(conn, state: SimulationState):
    for m in state.mortals.values():
        conn.execute(
            """INSERT INTO mortals
               (id, name, description, civilization_id, role, status,
                species_id, prominence_roles, prominence, visibility,
                belief_tags, personal_tags, status_tags, culture_tags, skill_tags,
                alignment, chrono_age, bio_age,
                birthday_billions, birthday_millions, birthday_thousands, birthday_years,
                birthday_month, birthday_day,
                appointed_by_demiurge, appointed_by_luminary,
                home_location, current_location, pinned, visibility_stall_remaining,
                active_goal_json,
                pop_id, pop_milieu, proxius_appointed_tick, herald_appointed_tick,
                origin_pop_subsumed, last_audit_text, last_audit_tick,
                travel_intent_json,
                fatigue, assets, knowledge_base, civilian_state,
                occupation)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                _j(m.status_tags),
                _j(m.culture_tags),
                _j(m.skill_tags),
                m.alignment,
                m.chrono_age,
                m.bio_age,
                m.birthday[0],  # billions (None → NULL)
                m.birthday[1],  # millions (None → NULL)
                m.birthday[2],  # thousands (None → NULL)
                m.birthday[3],  # years
                m.birthday[4],  # month
                m.birthday[5],  # day
                str(m.appointed_by_demiurge) if m.appointed_by_demiurge else None,
                str(m.appointed_by_luminary) if m.appointed_by_luminary else None,
                str(m.home_location),
                str(m.current_location),
                int(m.pinned),
                m.visibility_stall_remaining,
                m.active_goal.model_dump_json() if m.active_goal else None,
                str(m.pop_id) if m.pop_id else None,
                str(m.pop_milieu) if m.pop_milieu else None,
                m.proxius_appointed_tick,
                m.herald_appointed_tick,
                int(m.origin_pop_subsumed),
                m.last_audit_text,
                m.last_audit_tick,
                m.travel_intent.model_dump_json() if m.travel_intent else None,
                m.fatigue,
                json.dumps([a.model_dump() for a in m.assets]),
                m.knowledge_base.model_dump_json() if m.knowledge_base else None,
                m.civilian_state.model_dump_json() if m.civilian_state else None,
                m.occupation,
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
            affiliated_domains, max_affiliated_domains, tracked_essence_domains,
            revelation_pools, revealed_imagines, lifetime_revelation)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            d.max_affiliated_domains,
            _j(d.tracked_essence_domains),
            _j(d.revelation_pools),
            d.revealed_imagines,
            d.lifetime_revelation,
        ),
    )


def _write_essence(conn, state: SimulationState):
    e = state.essence
    conn.execute(
        "INSERT INTO essence (actual, suspicious, concealment_integrity) VALUES (?, ?, ?)",
        (e.actual, e.suspicious, e.concealment_integrity),
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
            pop_conformity_base, pop_visibility_drift_rate, established_drift_base,
            pop_contact_base_rate, cross_civ_contact_factor, cross_civ_scale_penalty,
            cross_species_contact_factor, cross_stratum_contact_factor,
            values_stubbornness_factor, peripheral_pop_belief_weight,
            peripheral_pop_culture_weight, civ_culture_drift_rate)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                   ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            cfg.pop_contact_base_rate,
            cfg.cross_civ_contact_factor,
            cfg.cross_civ_scale_penalty,
            cfg.cross_species_contact_factor,
            cfg.cross_stratum_contact_factor,
            cfg.values_stubbornness_factor,
            cfg.peripheral_pop_belief_weight,
            cfg.peripheral_pop_culture_weight,
            0.03,  # civ_culture_drift_rate stored for record; logic uses established_drift_base
        ),
    )


def _write_civ_momentum(conn, state: SimulationState):
    for cid, m in state.civ_momentum.items():
        conn.execute(
            """INSERT INTO civ_momentum
               (civilization_id, stability_delta, wealth_delta, cohesion_delta)
               VALUES (?, ?, ?, ?)""",
            (cid, m.stability_delta, m.wealth_delta, m.cohesion_delta),
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
        cv_json = json.dumps([
            {"culture_tag": cv.culture_tag, "direction": cv.direction, "notes": cv.notes}
            for cv in ev.culture_vectors
        ])
        conn.execute(
            """INSERT INTO active_events
               (id, event_type, curve, source_action_id, created_at_tick,
                duration, base_strength, peak_offset, decay_rate,
                target_world_id, target_civilization_id, target_mortal_id,
                target_loc_id, domain_vectors, culture_vectors,
                domain_shift_rate, divine_awareness_rate,
                attention_per_tick, imago_node_id, framing,
                concept)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                str(ev.target_loc_id) if ev.target_loc_id else None,
                dv_json,
                cv_json,
                ev.domain_shift_rate,
                ev.divine_awareness_rate,
                ev.attention_per_tick,
                ev.imago_node_id,
                ev.framing,
                ev.concept,
            ),
        )


def _write_ongoing_actions(conn, state: SimulationState):
    for cat_val, oa in state.pending_actions.items():
        intent_type = type(oa.intent).__name__ if oa.intent is not None else None
        intent_data = oa.intent.model_dump_json() if oa.intent is not None else None
        conn.execute(
            """INSERT INTO ongoing_actions
               (category_key, action_key, action_definition_id, target_type,
                target_id, proxius_id, intent_type, intent_data,
                ticks_active, executed_ticks, successful_ticks, started_at_tick,
                repeating, momentum)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                oa.successful_ticks,
                oa.started_at_tick,
                int(oa.repeating),
                oa.momentum,
            ),
        )


def _write_pending_resume(conn, state: SimulationState):
    for cat_val, oa in state.pending_resume.items():
        intent_type = type(oa.intent).__name__ if oa.intent is not None else None
        intent_data = oa.intent.model_dump_json() if oa.intent is not None else None
        conn.execute(
            """INSERT INTO pending_resume
               (category_key, action_key, action_definition_id, target_type,
                target_id, proxius_id, intent_type, intent_data,
                ticks_active, executed_ticks, successful_ticks, started_at_tick,
                repeating, momentum)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                oa.successful_ticks,
                oa.started_at_tick,
                int(oa.repeating),
                oa.momentum,
            ),
        )

