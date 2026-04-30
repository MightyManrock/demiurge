#!/usr/bin/env python3
"""
scenario_exporter.py
Writes a SimulationState out to a scenario .db file.

Used to:
  - Bootstrap the first .db from the hardcoded build_scenario_default()
  - Save a mid-run state as a new scenario starting point

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

from tick_logic import SimulationState


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

if __name__ == "__main__":
    from test_harness import build_scenario_default

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
