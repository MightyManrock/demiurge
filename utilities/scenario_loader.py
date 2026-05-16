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
from typing import Optional
from uuid import UUID, uuid4

from core.onto_core import (
    Luminary, Pantheon, Constraint,
    Disposition, FootprintProfile, Demiurge,
)
from core.universe_core import (
    FootprintTolerances, ProxiiPolicy, UniverseRules,
    Location, System, CosmicCoordinates, StarType,
    SignificantLocation, PopLocation, LocCondition, LocFootprint,
    CivilizationScale, CivilizationHealth, Civilization,
    MortalRole, MortalStatus, MortalProminence, NotableMortal,
    Species, SpeciesCondition,
    Pop, SocialClass, WildStratum,
    Universe,
)
from core.action_core import (
    EssenceStockpile, OngoingAction, TargetType,
    WhisperIntent, OmenIntent, ProbabilityNudgeIntent, DevelopmentIntent,
    ProxiusDirectiveIntent, LuminaryPetitionIntent, EssenceHarvestIntent,
    SalvageIntent, SeedWorldIntent, UpliftSpeciesIntent, ExploreBeliefIntent,
    ChangeAffiliatedDomainsIntent, ScryIntent,
    DomainVector,
)
from core.event_core import Event, EventType, StrengthCurve
from core.agent_core import ProxiusGoal, AgentActionChoice
from logic.tick_logic import (
    SimulationState, CivilizationMomentum, TickConfig,
)

_INTENT_CLASSES: dict[str, type] = {
    cls.__name__: cls
    for cls in [
        WhisperIntent, OmenIntent, ProbabilityNudgeIntent, DevelopmentIntent,
        ProxiusDirectiveIntent, LuminaryPetitionIntent, EssenceHarvestIntent,
        SalvageIntent, SeedWorldIntent, UpliftSpeciesIntent, ExploreBeliefIntent,
        ChangeAffiliatedDomainsIntent, ScryIntent,
    ]
}

SCHEMA_PATH = Path(__file__).parent.parent / "core" / "scenario_schema.sql"


_MAX_INDIVIDUAL_AFFINITY = 0.8   # no single Luminary may exceed this for any one domain
_MAX_PANTHEON_AFFINITY   = 0.9   # combined Luminary affinity across all Luminaries for one domain
_MAX_LUMINARY_AFFINITY   = 2.0   # sum of all domain affinities for a single Luminary


def validate_luminary_affinities(state: SimulationState) -> list[str]:
    """
    Check that all Luminary domain affinities satisfy the three design invariants.
    Returns a list of human-readable violation strings (empty = valid).
    """
    violations: list[str] = []
    pantheon_totals: dict[str, float] = {}

    for lum in state.luminaries.values():
        lum_sum = 0.0
        for domain, aff in lum.domains.items():
            if aff > _MAX_INDIVIDUAL_AFFINITY:
                violations.append(
                    f"{lum.name}: {domain} affinity {aff:.3f} exceeds {_MAX_INDIVIDUAL_AFFINITY}"
                )
            lum_sum += aff
            pantheon_totals[domain] = pantheon_totals.get(domain, 0.0) + aff
        if lum_sum > _MAX_LUMINARY_AFFINITY:
            violations.append(
                f"{lum.name}: total domain affinity {lum_sum:.3f} exceeds {_MAX_LUMINARY_AFFINITY}"
            )

    for domain, total in pantheon_totals.items():
        if total > _MAX_PANTHEON_AFFINITY:
            violations.append(
                f"Pantheon total for {domain}: {total:.3f} exceeds {_MAX_PANTHEON_AFFINITY}"
            )

    return violations


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


def _jd_str(text: str) -> dict[str, float]:
    """Parse a JSON dict of str→float with no legacy list handling."""
    val = json.loads(text) if text else {}
    return {str(k): float(v) for k, v in val.items()} if isinstance(val, dict) else {}


def _uuid(text: str | None) -> UUID | None:
    return UUID(text) if text else None


def _build_state(conn: sqlite3.Connection) -> SimulationState:
    meta    = dict(conn.execute("SELECT * FROM scenario_meta").fetchone())
    lums, constraints_by_owner = _load_luminaries(conn)
    pantheon = _load_pantheon(conn, constraints_by_owner)
    rules    = _load_universe_rules(conn)
    locations = _load_locations(conn)
    species  = _load_species(conn)
    civs     = _load_civilizations(conn)
    pops     = _load_pops(conn)
    mortals  = _load_mortals(conn)
    demiurge = _load_demiurge(conn)
    essence  = _load_essence(conn)
    cfg      = _load_tick_config(conn)
    civ_momentum = _load_civ_momentum(conn)
    lum_attention, ticks_since = _load_luminary_state(conn)
    ongoing_actions = _load_ongoing_actions(conn)
    active_events = _load_active_events(conn)
    luminary_production_accum = _jd_str(meta.get("luminary_production_accum", "{}"))
    domain_essence_claimed = _jd_str(meta.get("domain_essence_claimed", "{}"))
    starting_pinned_ids = _j(meta.get("starting_pinned_ids", "[]"))

    # Universe ID: stored in scenario_meta if present, else generate one.
    universe_id_str = meta.get("universe_id", "")
    universe_id = UUID(universe_id_str) if universe_id_str else uuid4()

    # Universe child_ids are the galaxy UUIDs (locations with no parent).
    galaxy_ids = [
        UUID(k) for k, v in locations.items()
        if v.parent_id is None and v.location_type == "galaxy"
    ]

    universe = Universe(
        id=universe_id,
        name=meta["universe_name"],
        description=meta.get("universe_description", ""),
        save_name=meta.get("universe_save_name", ""),
        demiurge_id=demiurge.id,
        pantheon_id=pantheon.id,
        rules=rules,
        child_ids=galaxy_ids,
        current_age=meta["current_age"],
        universe_domain_expression=_jd_str(meta.get("universe_domain_expression", "{}")),
    )

    state = SimulationState(
        universe=universe,
        demiurge=demiurge,
        essence=essence,
        pantheon=pantheon,
        luminaries={str(l.id): l for l in lums.values()},
        locations=locations,
        civilizations=civs,
        pops=pops,
        mortals=mortals,
        species=species,
        civ_momentum=civ_momentum,
        luminary_attention=lum_attention,
        ticks_since_evaluation=ticks_since,
        config=cfg,
        ongoing_actions=ongoing_actions,
        active_events=active_events,
        luminary_production_this_eval=luminary_production_accum,
        domain_essence_claimed=domain_essence_claimed,
        tick_number=meta.get("tick_number", 0),
        starting_pinned_ids=starting_pinned_ids,
    )

    # If the scenario DB didn't specify starting affiliated domains, derive them:
    # top-4 by aggregate Luminary affinity, alphabetical tiebreak.
    if not state.demiurge.affiliated_domains:
        from utilities.domain_registry import get_registry as get_domain_registry
        dreg = get_domain_registry()
        agg: dict[str, float] = {}
        for lum in state.luminaries.values():
            for tag, aff in lum.domains.items():
                if dreg.is_canonical(tag):
                    agg[tag] = agg.get(tag, 0.0) + aff
        state.demiurge.affiliated_domains = sorted(agg, key=lambda t: (-agg[t], t))[:4]

    return state


# ─────────────────────────────────────────
# Per-table loaders
# ─────────────────────────────────────────

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
    for raw in conn.execute("SELECT * FROM luminaries"):
        row = dict(raw)
        lid = row["id"]
        raw_domains = json.loads(row["domains"]) if row["domains"] else {}
        domains: dict[str, float] = raw_domains if isinstance(raw_domains, dict) else {}
        l = Luminary(
            id=UUID(lid),
            name=row["name"],
            domains=domains,
            pantheon_id=_uuid(row["pantheon_id"]),
            disposition=Disposition(
                results=row["disposition_results"],
                methods=row["disposition_methods"],
            ),
            constraints=constraints_by_owner.get(lid, []),
            herald_ids=[UUID(x) for x in _j(row["herald_ids"])],
            status_tags=_j(row.get("status_tags", row.get("speech_tags", "[]"))),
            essence_received_log=[float(x) for x in _j(row.get("essence_received_log", "[]"))],
            essence_expectation_raised=float(row.get("essence_expectation_raised", 0.0)),
            consecutive_essence_shortfalls=int(row.get("consecutive_essence_shortfalls", 0)),
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


def _load_locations(conn) -> dict[str, Location]:
    """Load all locations from the unified locations table."""
    out: dict[str, Location] = {}
    try:
        rows = conn.execute("SELECT * FROM locations").fetchall()
    except Exception:
        return out  # table absent in old DBs

    for raw in rows:
        row = dict(raw)
        subclass = row.get("subclass", "location")
        loc_id = UUID(row["id"])
        parent_id = _uuid(row.get("parent_id"))
        child_ids = [UUID(x) for x in _j(row.get("child_ids", "[]"))]
        traits = _j(row.get("traits", "[]"))
        condition = LocCondition(row.get("condition", "stable"))
        location_type = row.get("location_type", "location")
        description = row.get("description", "")
        visibility = float(row.get("visibility", 0.0))
        pinned = bool(row.get("pinned", 0))
        coordinates = CosmicCoordinates(
            x=row.get("coordinates_x", 0.0),
            y=row.get("coordinates_y", 0.0),
            z=row.get("coordinates_z", 0.0),
        )

        if subclass == "system":
            loc = System(
                id=loc_id,
                name=row["name"],
                description=description,
                location_type=location_type,
                parent_id=parent_id,
                child_ids=child_ids,
                traits=traits,
                condition=condition,
                coordinates=coordinates,
                visibility=visibility,
                pinned=pinned,
                star_type=StarType(row.get("star_type", "main_sequence")),
            )
        elif subclass == "significant_location":
            loc = SignificantLocation(
                id=loc_id,
                name=row["name"],
                description=description,
                location_type=location_type,
                parent_id=parent_id,
                child_ids=child_ids,
                traits=traits,
                condition=condition,
                coordinates=coordinates,
                visibility=visibility,
                pinned=pinned,
                domain_expression=_jd(row.get("domain_expression", "{}")),
                local_footprint=LocFootprint(
                    overt_miracles=row.get("lf_overt_miracles", 0.0),
                    subtle_influence=row.get("lf_subtle_influence", 0.0),
                    proxius_activity=row.get("lf_proxius_activity", 0.0),
                    direct_creation=row.get("lf_direct_creation", 0.0),
                ),
                civilization_ids=[UUID(x) for x in _j(row.get("civilization_ids", "[]"))],
                species_ids=[UUID(x) for x in _j(row.get("species_ids", "[]"))],
                proxius_ids=[UUID(x) for x in _j(row.get("proxius_ids", "[]"))],
                herald_ids=[UUID(x) for x in _j(row.get("herald_ids_loc", "[]"))],
                geo_tags=_j(row.get("geo_tags", "[]")),
                atmo_tags=_j(row.get("atmo_tags", "[]")),
                age=row.get("age", 0.0),
            )
        elif subclass == "pop_location":
            loc = PopLocation(
                id=loc_id,
                name=row["name"],
                description=description,
                location_type=location_type,
                parent_id=parent_id,
                child_ids=child_ids,
                traits=traits,
                condition=condition,
                coordinates=coordinates,
                visibility=visibility,
                pinned=pinned,
                pop_ids=[UUID(x) for x in _j(row.get("pop_ids", "[]"))],
            )
        else:
            # Base Location (galaxies and any freeform locations)
            loc = Location(
                id=loc_id,
                name=row["name"],
                description=description,
                location_type=location_type,
                parent_id=parent_id,
                child_ids=child_ids,
                traits=traits,
                condition=condition,
                coordinates=coordinates,
                visibility=visibility,
                pinned=pinned,
            )

        out[str(loc.id)] = loc

    return out


def _load_species(conn) -> dict[str, Species]:
    out = {}
    for raw in conn.execute("SELECT * FROM species"):
        row = dict(raw)
        sp = Species(
            id=UUID(row["id"]),
            name=row["name"],
            description=row.get("description", ""),
            origin_world_id=_uuid(row["origin_world_id"]),
            sapient=bool(row["sapient"]),
            transplanted=bool(row["transplanted"]),
            lifespan_min=row["lifespan_min"],
            lifespan_max=row["lifespan_max"],
            domain_tags=_j(row.get("domain_tags", "[]")),
            bio_tags=_j(row.get("bio_tags", row.get("trait_tags", "[]"))),
            condition=SpeciesCondition(row["condition"]),
            visibility=float(row.get("visibility", 0.0)),
            pinned=bool(row.get("pinned", 0)),
        )
        out[str(sp.id)] = sp
    return out


def _load_civilizations(conn) -> dict[str, Civilization]:
    out = {}
    for raw in conn.execute("SELECT * FROM civilizations"):
        row = dict(raw)
        # Handle legacy world_id column for old DBs
        origin_loc_str = row.get("origin_location_id") or row.get("world_id")
        dominant = _jd(row["dominant_beliefs"])
        # established_beliefs: fall back to a copy of dominant_beliefs on old DBs
        established_raw = row.get("established_beliefs", "{}")
        established = _jd(established_raw) if established_raw and established_raw != "{}" else dict(dominant)
        c = Civilization(
            id=UUID(row["id"]),
            name=row["name"],
            description=row.get("description", ""),
            origin_location_id=_uuid(origin_loc_str),
            scale=CivilizationScale(row["scale"]),
            health=CivilizationHealth(
                stability=row["health_stability"],
                prosperity=row["health_prosperity"],
                cohesion=row["health_cohesion"],
            ),
            primary_species_id=_uuid(row["primary_species_id"]),
            dominant_beliefs=dominant,
            established_beliefs=established,
            pop_ids=[UUID(x) for x in _j(row.get("pop_ids", "[]"))],
            culture_tags=_jd(row.get("culture_tags", "{}")),
            theistic=bool(row["theistic"]),
            divine_awareness=row["divine_awareness"],
            age=row["age"],
            visibility=float(row.get("visibility", 0.0)),
            pinned=bool(row.get("pinned", 0)),
        )
        # Re-attach mortal IDs
        for mrow in conn.execute(
            "SELECT id FROM mortals WHERE civilization_id = ?", (row["id"],)
        ):
            c.notable_mortal_ids.append(UUID(mrow["id"]))
        out[str(c.id)] = c
    return out


def _load_pops(conn) -> dict[str, Pop]:
    out: dict[str, Pop] = {}
    try:
        rows = conn.execute("SELECT * FROM pops").fetchall()
    except Exception:
        return out  # table absent in old DBs
    for raw in rows:
        row = dict(raw)
        sc_raw = row.get("social_class")
        ws_raw = row.get("wild_stratum")
        p = Pop(
            id=UUID(row["id"]),
            civilization_id=_uuid(row.get("civilization_id")),
            species_id=_uuid(row.get("species_id")),
            social_class=SocialClass(sc_raw) if sc_raw else None,
            wild_stratum=WildStratum(ws_raw) if ws_raw else None,
            current_location=UUID(row["current_location"]),
            size_fractional=float(row.get("size_fractional", 6.0)),
            dominant_beliefs=_jd(row.get("dominant_beliefs", "{}")),
            culture_tags=_jd(row.get("culture_tags", "{}")),
            rider_traits=_jd(row.get("rider_traits", "{}")),
            notable_mortal_ids=[UUID(x) for x in _j(row.get("notable_mortal_ids", "[]"))],
            parent_pop_id=_uuid(row.get("parent_pop_id")),
            child_pop_ids=[UUID(x) for x in _j(row.get("child_pop_ids", "[]"))],
            visibility=float(row.get("visibility", 0.0)),
            pinned=bool(row.get("pinned", 0)),
        )
        out[str(p.id)] = p
    return out


def _load_mortals(conn) -> dict[str, NotableMortal]:
    out = {}
    for raw in conn.execute("SELECT * FROM mortals"):
        row = dict(raw)
        m = NotableMortal(
            id=UUID(row["id"]),
            name=row["name"],
            description=row.get("description", ""),
            civilization_id=_uuid(row["civilization_id"]),
            role=MortalRole(row["role"]),
            status=MortalStatus(row["status"]),
            species_id=_uuid(row["species_id"]),
            prominence_roles=[MortalProminence(v) for v in _j(row["prominence_roles"])],
            prominence=row["prominence"],
            visibility=row["visibility"],
            belief_tags=_jd(row.get("belief_tags", "{}")),
            personal_tags=_j(row["personal_tags"]),
            culture_tags=_jd(row.get("culture_tags", "{}")),
            alignment=row["alignment"],
            chrono_age=row["chrono_age"],
            bio_age=row["bio_age"],
            appointed_by_demiurge=_uuid(row["appointed_by_demiurge"]),
            appointed_by_luminary=_uuid(row["appointed_by_luminary"]),
            home_location=UUID(row["home_location"]),
            current_location=UUID(row["current_location"]),
            pinned=bool(row.get("pinned", 0)),
            active_goal=_load_proxius_goal(row.get("active_goal_json")),
        )
        out[str(m.id)] = m
    return out


def _load_proxius_goal(raw: Optional[str]) -> Optional[ProxiusGoal]:
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if "last_action" in data and data["last_action"] is not None:
            data["last_action"] = AgentActionChoice(data["last_action"])
        return ProxiusGoal.model_validate(data)
    except Exception:
        return None


def _load_revelation_pools(row: dict) -> dict[str, float]:
    """Load revelation_pools from DB row, filling in any missing canonical tags with 0.0."""
    from utilities.domain_registry import get_registry as get_domain_registry
    dreg = get_domain_registry()
    raw: dict = _jd(row.get("revelation_pools", "{}"))
    pools = {tag: 0.0 for tag in dreg.all_tags}
    for tag, val in raw.items():
        if tag in pools:
            pools[tag] = float(val)
    return pools


def _load_demiurge(conn) -> Demiurge:
    row = dict(conn.execute("SELECT * FROM demiurge").fetchone())
    return Demiurge(
        id=UUID(row["id"]),
        name=row["name"],
        liege_luminary_ids=[UUID(x) for x in _j(row["liege_luminary_ids"])],
        footprint=FootprintProfile(
            overt_miracles=row["fp_overt_miracles"],
            subtle_influence=row["fp_subtle_influence"],
            proxius_activity=row["fp_proxius_activity"],
            direct_creation=row["fp_direct_creation"],
        ),
        proxius_ids=[UUID(x) for x in _j(row["proxius_ids"])],
        unlocked_domain_tags=_j(row.get("unlocked_domain_tags", "[]")),
        unlocked_imagines=_j(row.get("unlocked_imagines", "[]")),
        affiliated_domains=_j(row.get("affiliated_domains", "[]")),
        tracked_essence_domains=_j(row.get("tracked_essence_domains", "[]")),
        revelation_pools=_load_revelation_pools(row),
        revealed_imagines=int(row.get("revealed_imagines", 0) or 0),
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
        proxius_passive_footprint_rate=row.get("proxius_passive_footprint_rate", 0.03),
        location_visibility_decay_rate=row.get("location_visibility_decay_rate", 0.01),
        civ_visibility_decay_rate=row.get("civ_visibility_decay_rate", 0.01),
        species_visibility_decay_rate=row.get("species_visibility_decay_rate", 0.01),
        pop_conformity_base=float(row.get("pop_conformity_base", 0.005)),
        pop_visibility_drift_rate=float(row.get("pop_visibility_drift_rate", 0.02)),
        established_drift_base=float(row.get("established_drift_base", 0.01)),
    )


def _load_civ_momentum(conn) -> dict[str, CivilizationMomentum]:
    out = {}
    for row in conn.execute("SELECT * FROM civ_momentum"):
        cid = row["civilization_id"]
        out[cid] = CivilizationMomentum(
            civilization_id=UUID(cid),
            stability_delta=row["stability_delta"],
            prosperity_delta=row["prosperity_delta"],
            cohesion_delta=row["cohesion_delta"],
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


def _load_ongoing_actions(conn) -> dict[str, OngoingAction]:
    out: dict[str, OngoingAction] = {}
    try:
        rows = conn.execute("SELECT * FROM ongoing_actions").fetchall()
    except Exception:
        return out  # table absent in old DBs
    for raw in rows:
        row = dict(raw)
        intent = None
        intent_type = row.get("intent_type")
        intent_data = row.get("intent_data")
        if intent_type and intent_data and intent_type in _INTENT_CLASSES:
            intent = _INTENT_CLASSES[intent_type].model_validate_json(intent_data)
        out[row["category_key"]] = OngoingAction(
            action_key=row["action_key"],
            action_definition_id=UUID(row["action_definition_id"]),
            target_type=TargetType(row["target_type"]),
            target_id=_uuid(row.get("target_id")),
            proxius_id=_uuid(row.get("proxius_id")),
            intent=intent,
            ticks_active=row["ticks_active"],
            executed_ticks=row["executed_ticks"],
            started_at_tick=row["started_at_tick"],
        )
    return out


def _load_active_events(conn) -> dict[str, Event]:
    out: dict[str, Event] = {}
    try:
        rows = conn.execute("SELECT * FROM active_events").fetchall()
    except Exception:
        return out  # table absent in old DBs
    for raw in rows:
        row = dict(raw)
        domain_vectors: list[DomainVector] = []
        dv_data = row.get("domain_vectors", "[]")
        for dv_dict in json.loads(dv_data) if dv_data else []:
            domain_vectors.append(DomainVector(
                domain_tag=dv_dict["domain_tag"],
                direction=dv_dict["direction"],
                notes=dv_dict.get("notes", ""),
            ))
        event = Event(
            id=UUID(row["id"]),
            event_type=EventType(row["event_type"]),
            curve=StrengthCurve(row["curve"]),
            source_action_id=_uuid(row.get("source_action_id")),
            created_at_tick=row["created_at_tick"],
            duration=row["duration"],
            base_strength=row.get("base_strength", 1.0),
            peak_offset=row.get("peak_offset", 0),
            decay_rate=row.get("decay_rate", 0.6),
            target_world_id=_uuid(row.get("target_world_id")),
            target_civilization_id=_uuid(row.get("target_civilization_id")),
            target_mortal_id=_uuid(row.get("target_mortal_id")),
            domain_vectors=domain_vectors,
            domain_shift_rate=row.get("domain_shift_rate", 0.10),
            divine_awareness_rate=row.get("divine_awareness_rate", 0.0),
            attention_per_tick=row.get("attention_per_tick", 0.0),
            imago_node_id=row.get("imago_node_id"),
            framing=row.get("framing"),
            sign_description=row.get("sign_description", ""),
            concept=row.get("concept", ""),
        )
        out[row["id"]] = event
    return out
