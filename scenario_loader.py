#!/usr/bin/env python3
"""
scenario_loader.py
Reads a scenario .db file and returns a fully constructed SimulationState.

The engine (tick_logic, eval_core, etc.) is never aware SQL exists —
it only ever receives Pydantic models from this module.

Usage:
    from scenario_loader import load_scenario
    state = load_scenario("scenarios/wardens_compact.db")
"""

from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from uuid import UUID

from onto_core import (
    Domain, Luminary, Pantheon, Constraint,
    Temperament, Disposition, FootprintProfile, Demiurge,
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
from action_core import EssenceStockpile
from tick_logic import (
    SimulationState, CivilizationMomentum, TickConfig, DomainVector,
)

SCHEMA_PATH = Path(__file__).parent / "scenario_schema.sql"


def load_scenario(db_path: str | Path) -> SimulationState:
    """Open a scenario .db file and return the initial SimulationState."""
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"Scenario file not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    state = _build_state(conn)
    conn.close()
    return state


def _j(text: str) -> list:
    """Parse a JSON text column back to a Python list."""
    return json.loads(text) if text else []


def _jd(text: str) -> dict[str, float]:
    """Parse a JSON belief/domain dict. Handles legacy list format for backward compat."""
    val = json.loads(text) if text else {}
    if isinstance(val, list):
        # Legacy format: list of tag strings — convert to dict with default strength 0.7
        return {tag: 0.7 for tag in val}
    return val


def _uuid(text: str | None) -> UUID | None:
    return UUID(text) if text else None


def _build_state(conn: sqlite3.Connection) -> SimulationState:
    meta    = dict(conn.execute("SELECT * FROM scenario_meta").fetchone())
    domains = _load_domains(conn)
    lums, constraints_by_owner = _load_luminaries(conn)
    pantheon = _load_pantheon(conn, constraints_by_owner)
    rules    = _load_universe_rules(conn)
    galaxies = _load_galaxies(conn)
    systems  = _load_systems(conn)
    species  = _load_species(conn)
    worlds   = _load_worlds(conn)
    civs     = _load_civilizations(conn)
    mortals  = _load_mortals(conn)
    demiurge = _load_demiurge(conn)
    essence  = _load_essence(conn)
    cfg      = _load_tick_config(conn)
    civ_momentum = _load_civ_momentum(conn)
    lum_attention, ticks_since = _load_luminary_state(conn)

    universe = Universe(
        name=meta["universe_name"],
        demiurge_id=demiurge.id,
        pantheon_id=pantheon.id,
        rules=rules,
        galaxy_ids=[UUID(k) for k in galaxies.keys()],
        current_age=meta["current_age"],
    )

    return SimulationState(
        universe=universe,
        demiurge=demiurge,
        essence=essence,
        pantheon=pantheon,
        luminaries={str(l.id): l for l in lums.values()},
        domains=domains,
        galaxies=galaxies,
        systems=systems,
        worlds=worlds,
        civilizations=civs,
        mortals=mortals,
        species=species,
        civ_momentum=civ_momentum,
        luminary_attention=lum_attention,
        ticks_since_evaluation=ticks_since,
        config=cfg,
    )


# ─────────────────────────────────────────
# Per-table loaders
# ─────────────────────────────────────────

def _load_domains(conn) -> dict[str, Domain]:
    out = {}
    for row in conn.execute("SELECT * FROM domains"):
        d = Domain(
            id=UUID(row["id"]),
            name=row["name"],
            description=row["description"],
            source_powers=[UUID(x) for x in _j(row["source_powers"])],
            tags=_j(row["tags"]),
        )
        out[str(d.id)] = d
    return out


def _load_luminaries(conn) -> tuple[dict[str, Luminary], dict[str, list[Constraint]]]:
    """Returns (luminaries dict, constraints_by_owner_id dict)."""
    # Load all constraints first, grouped by owner
    constraints_by_owner: dict[str, list[Constraint]] = {}
    for row in conn.execute("SELECT * FROM constraints"):
        c = Constraint(
            id=UUID(row["id"]),
            name=row["name"],
            description=row["description"],
            domain_source=_uuid(row["domain_source"]),
            enforcement_weight=row["enforcement_weight"],
        )
        constraints_by_owner.setdefault(row["owner_id"], []).append(c)

    lums = {}
    for row in conn.execute("SELECT * FROM luminaries"):
        lid = row["id"]
        l = Luminary(
            id=UUID(lid),
            name=row["name"],
            domains=[UUID(x) for x in _j(row["domains"])],
            pantheon_id=_uuid(row["pantheon_id"]),
            temperament=Temperament(row["temperament"]),
            disposition=Disposition(
                results=row["disposition_results"],
                methods=row["disposition_methods"],
            ),
            constraints=constraints_by_owner.get(lid, []),
            herald_id=_uuid(row["herald_id"]),
            speech_tags=_j(row["speech_tags"]),
        )
        lums[str(l.id)] = l

    return lums, constraints_by_owner


def _load_pantheon(conn, constraints_by_owner: dict[str, list[Constraint]]) -> Pantheon:
    row = conn.execute("SELECT * FROM pantheons").fetchone()
    pid = row["id"]
    return Pantheon(
        id=UUID(pid),
        name=row["name"],
        luminary_ids=[UUID(x) for x in _j(row["luminary_ids"])],
        collective_constraints=constraints_by_owner.get(pid, []),
    )


def _load_universe_rules(conn) -> UniverseRules:
    row = dict(conn.execute("SELECT * FROM universe_rules").fetchone())
    return UniverseRules(
        footprint_tolerances=FootprintTolerances(
            overt_miracles=row["fp_tolerance_overt_miracles"],
            subtle_influence=row["fp_tolerance_subtle_influence"],
            proxius_activity=row["fp_tolerance_proxius_activity"],
            direct_creation=row["fp_tolerance_direct_creation"],
        ),
        proxii_policy=ProxiiPolicy(
            max_per_world=row["proxii_max_per_world"],
            tolerance_for_excess=row["proxii_tolerance_for_excess"],
        ),
        mortals_can_perceive_divinity=bool(row["mortals_can_perceive_divinity"]),
        active_shaping_expected=bool(row["active_shaping_expected"]),
        special_flags=_j(row["special_flags"]),
        notes=row["notes"],
    )


def _load_species(conn) -> dict[str, Species]:
    out = {}
    for row in conn.execute("SELECT * FROM species"):
        sp = Species(
            id=UUID(row["id"]),
            name=row["name"],
            description=row["description"],
            origin_world_id=_uuid(row["origin_world_id"]),
            sapient=bool(row["sapient"]),
            transplanted=bool(row["transplanted"]),
            lifespan_min=row["lifespan_min"],
            lifespan_max=row["lifespan_max"],
            trait_tags=_j(row["trait_tags"]),
            cultural_tags=_j(row["cultural_tags"]),
            condition=SpeciesCondition(row["condition"]),
        )
        out[str(sp.id)] = sp
    return out


def _load_galaxies(conn) -> dict[str, Galaxy]:
    out = {}
    for row in conn.execute("SELECT * FROM galaxies"):
        g = Galaxy(
            id=UUID(row["id"]),
            name=row["name"],
            coordinates=CosmicCoordinates(x=row["x"], y=row["y"], z=row["z"]),
            dominant_domain_tags=_j(row["dominant_domain_tags"]),
        )
        # Re-attach system IDs
        for srow in conn.execute(
            "SELECT id FROM systems WHERE galaxy_id = ?", (row["id"],)
        ):
            g.system_ids.append(UUID(srow["id"]))
        out[str(g.id)] = g
    return out


def _load_systems(conn) -> dict[str, System]:
    out = {}
    for row in conn.execute("SELECT * FROM systems"):
        s = System(
            id=UUID(row["id"]),
            name=row["name"],
            galaxy_id=UUID(row["galaxy_id"]),
            coordinates=CosmicCoordinates(x=row["x"], y=row["y"], z=row["z"]),
            star_type=StarType(row["star_type"]),
        )
        # Re-attach world IDs
        for wrow in conn.execute(
            "SELECT id FROM worlds WHERE system_id = ?", (row["id"],)
        ):
            s.world_ids.append(UUID(wrow["id"]))
        out[str(s.id)] = s
    return out


def _load_worlds(conn) -> dict[str, World]:
    out = {}
    for row in conn.execute("SELECT * FROM worlds"):
        w = World(
            id=UUID(row["id"]),
            name=row["name"],
            system_id=UUID(row["system_id"]),
            condition=WorldCondition(row["condition"]),
            domain_expression=_jd(row["domain_expression"]),
            species_ids=[UUID(x) for x in _j(row["species_ids"])],
            age=row["age"],
        )
        # Re-attach civilization IDs
        for crow in conn.execute(
            "SELECT id FROM civilizations WHERE world_id = ?", (row["id"],)
        ):
            w.civilization_ids.append(UUID(crow["id"]))
        out[str(w.id)] = w
    return out


def _load_civilizations(conn) -> dict[str, Civilization]:
    out = {}
    for row in conn.execute("SELECT * FROM civilizations"):
        c = Civilization(
            id=UUID(row["id"]),
            name=row["name"],
            world_id=UUID(row["world_id"]),
            scale=CivilizationScale(row["scale"]),
            health=CivilizationHealth(
                stability=row["health_stability"],
                prosperity=row["health_prosperity"],
                cohesion=row["health_cohesion"],
            ),
            primary_species_id=_uuid(row["primary_species_id"]),
            dominant_beliefs=_jd(row["dominant_beliefs"]),
            theistic=bool(row["theistic"]),
            divine_awareness=row["divine_awareness"],
            age=row["age"],
        )
        # Re-attach mortal IDs
        for mrow in conn.execute(
            "SELECT id FROM mortals WHERE civilization_id = ?", (row["id"],)
        ):
            c.notable_mortal_ids.append(UUID(mrow["id"]))
        out[str(c.id)] = c
    return out


def _load_mortals(conn) -> dict[str, NotableMortal]:
    out = {}
    for row in conn.execute("SELECT * FROM mortals"):
        m = NotableMortal(
            id=UUID(row["id"]),
            name=row["name"],
            world_id=UUID(row["world_id"]),
            civilization_id=_uuid(row["civilization_id"]),
            role=MortalRole(row["role"]),
            status=MortalStatus(row["status"]),
            species_id=_uuid(row["species_id"]),
            prominence_roles=[MortalProminence(v) for v in _j(row["prominence_roles"])],
            prominence=row["prominence"],
            visibility=row["visibility"],
            personal_tags=_j(row["personal_tags"]),
            alignment=row["alignment"],
            chrono_age=row["chrono_age"],
            bio_age=row["bio_age"],
            appointed_by_demiurge=_uuid(row["appointed_by_demiurge"]),
            appointed_by_luminary=_uuid(row["appointed_by_luminary"]),
        )
        out[str(m.id)] = m
    return out


def _load_demiurge(conn) -> Demiurge:
    row = dict(conn.execute("SELECT * FROM demiurge").fetchone())
    return Demiurge(
        id=UUID(row["id"]),
        name=row["name"],
        liege_luminary_ids=[UUID(x) for x in _j(row["liege_luminary_ids"])],
        granted_domains=[UUID(x) for x in _j(row["granted_domains"])],
        footprint=FootprintProfile(
            overt_miracles=row["fp_overt_miracles"],
            subtle_influence=row["fp_subtle_influence"],
            proxius_activity=row["fp_proxius_activity"],
            direct_creation=row["fp_direct_creation"],
        ),
        proxius_ids=[UUID(x) for x in _j(row["proxius_ids"])],
        unlocked_domain_tags=_j(row.get("unlocked_domain_tags", "[]")),
    )


def _load_essence(conn) -> EssenceStockpile:
    row = dict(conn.execute("SELECT * FROM essence").fetchone())
    return EssenceStockpile(
        actual=row["actual"],
        apparent=row["apparent"],
        concealment_integrity=row["concealment_integrity"],
    )


def _load_tick_config(conn) -> TickConfig:
    row = dict(conn.execute("SELECT * FROM tick_config").fetchone())
    return TickConfig(
        tick_duration=row["tick_duration"],
        footprint_decay_rate=row["footprint_decay_rate"],
        footprint_decay_multipliers={
            "overt_miracles":  row["decay_mult_overt_miracles"],
            "subtle_influence": row["decay_mult_subtle_influence"],
            "proxius_activity": row["decay_mult_proxius_activity"],
            "direct_creation":  row["decay_mult_direct_creation"],
        },
        concealment_decay_rate=row["concealment_decay_rate"],
        civ_momentum_rate=row["civ_momentum_rate"],
        civ_noise_factor=row["civ_noise_factor"],
        alignment_drift_rate=row["alignment_drift_rate"],
        attention_decay_rate=row["attention_decay_rate"],
        evaluation_interval=row["evaluation_interval"],
        mortal_visibility_decay_rate=row["mortal_visibility_decay_rate"],
    )


def _load_civ_momentum(conn) -> dict[str, CivilizationMomentum]:
    out = {}
    drifts: dict[str, list[DomainVector]] = {}
    for row in conn.execute("SELECT * FROM civ_momentum_belief_drift"):
        drifts.setdefault(row["civilization_id"], []).append(
            DomainVector(
                domain_tag=row["domain_tag"],
                direction=row["direction"],
                notes=row["notes"],
            )
        )
    for row in conn.execute("SELECT * FROM civ_momentum"):
        cid = row["civilization_id"]
        out[cid] = CivilizationMomentum(
            civilization_id=UUID(cid),
            stability_delta=row["stability_delta"],
            prosperity_delta=row["prosperity_delta"],
            cohesion_delta=row["cohesion_delta"],
            belief_drift=drifts.get(cid, []),
        )
    return out


def _load_luminary_state(
    conn,
) -> tuple[dict[str, float], dict[str, float]]:
    attention: dict[str, float] = {}
    ticks: dict[str, float] = {}
    for row in conn.execute("SELECT * FROM luminary_state"):
        lid = row["luminary_id"]
        attention[lid] = row["attention"]
        ticks[lid]     = row["ticks_since_evaluation"]
    return attention, ticks
