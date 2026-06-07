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
    Luminary, Pantheon, Constraint, NarrativeConstraint, FootprintConstraint,
    ResultsConstraint, Disposition, FootprintProfile, Demiurge,
)
from core.universe_core import (
    FootprintTolerances, ProxiiPolicy, UniverseRules,
    Location, System, CosmicCoordinates, StarType,
    SignificantLocation, PopLocation, LocCondition, LocFootprint,
    CivilizationScale, CivilizationHealth, Civilization,
    MortalRole, MortalStatus, MortalProminence, NotableMortal,
    Species, SpeciesCondition, LifeBasis, Solvent,
    Pop, SocialClass, WildStratum,
    NetworkCondition, TravelEdge, TravelNetwork,
    Universe, EntityAge, Faction,
)
UniverseAge = EntityAge  # backward compat for helpers that still use the old name
from core.action_core import (
    EssenceStockpile, OngoingAction, TargetType,
    WhisperIntent, OmenIntent, ProbabilityNudgeIntent, DevelopmentIntent,
    ProxiusDirectiveIntent, LuminaryPetitionIntent, EssenceHarvestIntent,
    SalvageIntent, SeedWorldIntent, UpliftSpeciesIntent, ExploreBeliefIntent,
    ChangeAffiliatedDomainsIntent, ScryIntent,
    DomainVector, CultureVector, CategoryCooldowns,
)
from core.event_core import Event, EventType, StrengthCurve
from core.agent_core import (
    ProxiusGoal, AgentActionChoice, TravelIntent,
    KnowledgeBase, MortalAsset, MortalAgentState, CollectibleResource,
)
from logic.tick_logic import (
    SimulationState, CivilizationMomentum, TickConfig,
    PauseConfig, compute_mortal_alignment_base,
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


def _load_universe_age(meta: dict) -> EntityAge:
    """Load universe EntityAge; prefers 6-component columns, falls back to legacy age_year, then current_age float."""
    if meta.get("age_billions") is not None:
        return EntityAge(
            billions=meta["age_billions"], millions=meta["age_millions"],
            thousands=meta["age_thousands"], years=meta["age_years"],
            month=meta["age_month"], day=meta["age_day"],
        )
    if meta.get("age_year") is not None:
        return EntityAge.from_full_year(meta["age_year"], meta.get("age_month", 1), meta.get("age_day", 1))
    old = float(meta.get("current_age") or 0.0)
    return EntityAge.from_full_year(int(old))


def _load_entity_age(row: dict, universe_age: EntityAge) -> EntityAge:
    """Build an EntityAge for a Location or Civilization row.

    Current calendar position: use age_* columns when present; fall back to universe_age
    (correct for old DBs that didn't store per-entity date).
    Formation date: use formation_* columns when present; fall back to zero (Year 0).
    Caller is responsible for applying parent-fallback logic afterward."""
    if row.get("age_billions") is not None:
        cur = EntityAge(
            billions=int(row["age_billions"]),
            millions=int(row["age_millions"]),
            thousands=int(row["age_thousands"]),
            years=int(row["age_years"]),
            month=int(row["age_month"]),
            day=int(row["age_day"]),
        )
    else:
        cur = EntityAge(
            billions=universe_age.billions,
            millions=universe_age.millions,
            thousands=universe_age.thousands,
            years=universe_age.years,
            month=universe_age.month,
            day=universe_age.day,
        )
    if row.get("formation_billions") is not None:
        formation: tuple[int, int, int, int, int, int] = (
            int(row["formation_billions"]),
            int(row["formation_millions"]),
            int(row["formation_thousands"]),
            int(row["formation_year"]),
            int(row["formation_month"]),
            int(row["formation_day"]),
        )
    else:
        formation = (0, 0, 0, 0, 1, 1)
    return EntityAge(
        billions=cur.billions, millions=cur.millions, thousands=cur.thousands,
        years=cur.years, month=cur.month, day=cur.day,
        formation_date=formation,
    )


def _derive_founding_date(civ_age: float, universe_age: UniverseAge) -> tuple[int, int, int, int, int, int]:
    ua = UniverseAge.from_full_year(
        max(0, universe_age.full_year() - int(civ_age)),
        universe_age.month, universe_age.day,
    )
    return (ua.billions, ua.millions, ua.thousands, ua.years, ua.month, ua.day)


def _load_civ_age(row: dict, universe_age: EntityAge) -> EntityAge:
    """Build an EntityAge for a Civilization row.

    Current calendar position: age_* columns if present, else universe_age.
    Formation date: founding_* columns if present; fall back to deriving from legacy age REAL."""
    if row.get("age_billions") is not None:
        cur_bi, cur_mi, cur_th, cur_yr, cur_mo, cur_dy = (
            int(row["age_billions"]), int(row["age_millions"]), int(row["age_thousands"]),
            int(row["age_years"]), int(row["age_month"]), int(row["age_day"]),
        )
    else:
        cur_bi, cur_mi, cur_th, cur_yr = (
            universe_age.billions, universe_age.millions,
            universe_age.thousands, universe_age.years,
        )
        cur_mo, cur_dy = universe_age.month, universe_age.day

    if row.get("founding_billions") is not None:
        formation: tuple[int, int, int, int, int, int] = (
            int(row["founding_billions"]), int(row["founding_millions"]),
            int(row["founding_thousands"]), int(row["founding_year"]),
            int(row["founding_month"]), int(row["founding_day"]),
        )
    elif row.get("founding_year") is not None:
        formation = (0, 0, 0, int(row["founding_year"]),
                     int(row.get("founding_month", 1)), int(row.get("founding_day", 1)))
    else:
        formation = _derive_founding_date(float(row.get("age", 0.0)), universe_age)

    return EntityAge(
        billions=cur_bi, millions=cur_mi, thousands=cur_th, years=cur_yr,
        month=cur_mo, day=cur_dy, formation_date=formation,
    )


def _derive_birthday(chrono_age: float, universe_age: UniverseAge) -> tuple:
    born = UniverseAge.from_full_year(max(0, universe_age.full_year() - int(chrono_age)))
    return (born.billions, born.millions, born.thousands, born.years, universe_age.month, universe_age.day)


def _load_birthday(row: dict, universe_age: UniverseAge) -> tuple:
    """Load mortal birthday tuple.

    If upper components (billions/millions/thousands) are stored, use them directly.
    If NULL, derive the full birth date from chrono_age — this correctly handles
    mortals who crossed a millennium boundary during their lifetime."""
    bm = row.get("birthday_month", 1)
    bd = row.get("birthday_day", 1)
    bi = row.get("birthday_billions")
    if bi is not None:
        return (bi, row["birthday_millions"], row["birthday_thousands"],
                row["birthday_years"], bm, bd)
    # Derive all year components from birth year
    full_birth = max(0, universe_age.full_year() - int(row.get("chrono_age", 0)))
    born = UniverseAge.from_full_year(full_birth)
    yr = row.get("birthday_years", born.years)
    return (born.billions, born.millions, born.thousands, yr, bm, bd)


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
    universe_age = _load_universe_age(meta)
    locations = _load_locations(conn, universe_age)
    travel_networks = _load_travel_networks(conn)
    species  = _load_species(conn)
    civs     = _load_civilizations(conn, universe_age)
    pops     = _load_pops(conn)
    mortals  = _load_mortals(conn, universe_age)
    for m in mortals.values():
        if m.pop_milieu is None and m.pop_id is not None:
            m.pop_milieu = m.pop_id
    demiurge = _load_demiurge(conn)
    essence  = _load_essence(conn)
    cfg      = _load_tick_config(conn)
    civ_momentum = _load_civ_momentum(conn)
    category_cooldowns = CategoryCooldowns.model_validate_json(
        meta.get("category_cooldowns", "{}")
    )
    pause_config = PauseConfig.model_validate_json(
        meta.get("pause_config", "{}")
    )
    lum_attention, ticks_since = _load_luminary_state(conn)
    ongoing_actions = _load_ongoing_actions(conn)
    pending_resume = _load_pending_resume(conn)
    active_events = _load_active_events(conn)
    luminary_production_accum = _jd_str(meta.get("luminary_production_accum", "{}"))
    domain_essence_claimed = _jd_str(meta.get("domain_essence_claimed", "{}"))
    last_tick_essence_by_domain = _jd_str(meta.get("last_tick_essence_by_domain", "{}"))
    last_essence_capture_by_domain = _jd_str(meta.get("last_essence_capture_by_domain", "{}"))
    last_essence_capture_tick = meta.get("last_essence_capture_tick", 0) or 0
    last_harvest_amount = float(meta.get("last_harvest_amount", 0.0) or 0.0)
    last_harvest_tick   = meta.get("last_harvest_tick", 0) or 0
    rich_log_name = meta.get("rich_log_name", "") or ""

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
        age=_load_universe_age(meta),
        universe_domain_expression=_jd_str(meta.get("universe_domain_expression", "{}")),
    )

    state = SimulationState(
        universe=universe,
        demiurge=demiurge,
        essence=essence,
        pantheon=pantheon,
        luminaries={str(l.id): l for l in lums.values()},
        locations=locations,
        travel_networks=travel_networks,
        civilizations=civs,
        pops=pops,
        mortals=mortals,
        species=species,
        civ_momentum=civ_momentum,
        category_cooldowns=category_cooldowns,
        pause_config=pause_config,
        luminary_attention=lum_attention,
        ticks_since_evaluation=ticks_since,
        config=cfg,
        pending_actions=ongoing_actions,
        pending_resume=pending_resume,
        active_events=active_events,
        luminary_production_this_eval=luminary_production_accum,
        domain_essence_claimed=domain_essence_claimed,
        last_tick_essence_by_domain=last_tick_essence_by_domain,
        last_essence_capture_by_domain=last_essence_capture_by_domain,
        last_essence_capture_tick=last_essence_capture_tick,
        last_harvest_amount=last_harvest_amount,
        last_harvest_tick=last_harvest_tick,
        tick_number=meta.get("tick_number", 0),
        rich_log_name=rich_log_name,
        factions=_load_factions(conn),
    )

    # If the scenario DB didn't specify starting affiliated domains, derive them:
    # top-N by aggregate Luminary affinity, alphabetical tiebreak, where
    # N = demiurge.max_affiliated_domains.
    if not state.demiurge.affiliated_domains:
        from utilities.domain_registry import get_registry as get_domain_registry
        dreg = get_domain_registry()
        agg: dict[str, float] = {}
        for lum in state.luminaries.values():
            for tag, aff in lum.domains.items():
                if dreg.is_canonical(tag):
                    agg[tag] = agg.get(tag, 0.0) + aff
        cap = state.demiurge.max_affiliated_domains
        state.demiurge.affiliated_domains = sorted(agg, key=lambda t: (-agg[t], t))[:cap]

    # Compute natural alignment for mortals zeroed-out in the scenario.
    # Savegames always have non-zero values; only scenario DBs use 0.0 as a sentinel.
    #
    # "New Demiurge" penalty: starting alignment is reduced proportionally to how
    # far the natural base is below the NEW_DEMIURGE_THRESHOLD. Mortals already
    # well-aligned (base ≥ threshold) keep their natural base; mortals farther
    # below get a steeper dip. Alignment drifts back toward the natural base over
    # ticks via the standard alignment_drift mechanic, so this only shapes turn-1
    # perception — the long-run equilibrium is unchanged.
    NEW_DEMIURGE_THRESHOLD = 0.75
    if any(m.alignment == 0.0 for m in state.mortals.values()):
        from utilities.domain_registry import get_registry as get_domain_registry
        dreg = get_domain_registry()
        for mortal in state.mortals.values():
            if mortal.alignment == 0.0:
                base = compute_mortal_alignment_base(
                    mortal, state.demiurge.affiliated_domains, dreg
                )
                if base < NEW_DEMIURGE_THRESHOLD:
                    base = base - (NEW_DEMIURGE_THRESHOLD - base)
                cap = 1.0 if mortal.role == MortalRole.PROXIUS else 0.9
                mortal.alignment = max(0.05, min(cap, base))

    return state


# ─────────────────────────────────────────
# Per-table loaders
# ─────────────────────────────────────────

def _load_luminaries(conn) -> tuple[dict[str, Luminary], dict[str, list[Constraint]]]:
    """Returns (luminaries dict, constraints_by_owner_id dict)."""
    # Load all constraints first, grouped by owner
    constraints_by_owner: dict[str, list[Constraint]] = {}
    for row in conn.execute("SELECT * FROM constraints"):
        d = dict(row)
        ctype = d.get("constraint_type", "narrative")
        base = dict(
            id=UUID(d["id"]),
            name=d["name"],
            description=d["description"],
            domain_tag=d.get("domain_tag"),
            enforcement_weight=d["enforcement_weight"],
        )
        if ctype == "footprint" and d.get("footprint_tolerances"):
            c: Constraint = FootprintConstraint(
                **base,
                footprint_tolerances=json.loads(d["footprint_tolerances"]),
            )
        elif ctype == "results" and d.get("min_results") is not None:
            c = ResultsConstraint(**base, min_results=d["min_results"])
        else:
            c = NarrativeConstraint(**base)
        constraints_by_owner.setdefault(d["owner_id"], []).append(c)

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
            last_evaluation=(json.loads(row["last_evaluation"]) if row.get("last_evaluation") else None),
            previous_evaluation=(json.loads(row["previous_evaluation"]) if row.get("previous_evaluation") else None),
            last_evaluation_tick=(int(row["last_evaluation_tick"]) if row.get("last_evaluation_tick") is not None else None),
            last_orders_response=row.get("last_orders_response"),
            last_orders_response_tick=(int(row["last_orders_response_tick"]) if row.get("last_orders_response_tick") is not None else None),
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


def _load_locations(conn, universe_age: EntityAge) -> dict[str, Location]:
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
        visibility_stall_remaining = int(row.get("visibility_stall_remaining", 0))
        coordinates = CosmicCoordinates(
            x=row.get("coordinates_x", 0.0),
            y=row.get("coordinates_y", 0.0),
            z=row.get("coordinates_z", 0.0),
        )
        entity_age = _load_entity_age(row, universe_age)

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
                visibility_stall_remaining=visibility_stall_remaining,
                star_type=StarType(row.get("star_type", "main_sequence")),
                age=entity_age,
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
                visibility_stall_remaining=visibility_stall_remaining,
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
                age=entity_age,
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
                visibility_stall_remaining=visibility_stall_remaining,
                domain_expression=_jd(row.get("domain_expression", "{}")),
                pop_ids=[UUID(x) for x in _j(row.get("pop_ids", "[]"))],
                distance_from_core=int(row.get("distance_from_core", 0) or 0),
                travel_network_ids=[UUID(x) for x in _j(row.get("travel_network_ids", "[]"))],
                commerce_quality=float(row.get("commerce_quality") or 0.5),
                collectible_resource=_load_collectible_resource(row.get("collectible_resource")),
                wealth=float(row.get("wealth", 0.5) or 0.5),
                danger=float(row.get("danger", 0.0) or 0.0),
                resource_stockpile=_jd(row.get("resource_stockpile", "{}")),
                age=entity_age,
            )
        elif subclass == "travel_location":
            from core.universe_core import TravelLocation
            loc = TravelLocation(
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
                visibility_stall_remaining=visibility_stall_remaining,
                legs=_jd(row.get("legs", "{}")),
                current_waypoint=row.get("travel_current_wp", ""),
                ticks_remaining=int(row.get("travel_ticks_rem", 0) or 0),
                occupants=[UUID(x) for x in _j(row.get("travel_occupants", "[]"))],
                pop_ids=[UUID(x) for x in _j(row.get("travel_pop_ids", "[]"))],
                age=entity_age,
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
                visibility_stall_remaining=visibility_stall_remaining,
                age=entity_age,
            )

        out[str(loc.id)] = loc

    # Post-load pass: propagate formation_date from parent for locations that had no
    # formation data stored (old DBs or newly created blank entries).
    # Chain: System → SignificantLocation → PopLocation
    _ZERO_FORMATION = (0, 0, 0, 0, 1, 1)
    for loc in out.values():
        if loc.age.formation_date != _ZERO_FORMATION:
            continue
        if loc.parent_id is None:
            continue
        parent = out.get(str(loc.parent_id))
        if parent is None:
            continue
        if parent.age.formation_date != _ZERO_FORMATION:
            loc.age = EntityAge(
                billions=loc.age.billions, millions=loc.age.millions,
                thousands=loc.age.thousands, years=loc.age.years,
                month=loc.age.month, day=loc.age.day,
                formation_date=parent.age.formation_date,
            )

    return out

def _load_travel_edges(raw: Optional[str]) -> list[TravelEdge]:
    if not raw:
        return []
    try:
        return [TravelEdge.model_validate(item) for item in json.loads(raw)]
    except Exception:
        return []

def _load_network_conditions(raw: Optional[str]) -> list[NetworkCondition]:
    if not raw:
        return []
    try:
        items = json.loads(raw)
        for item in items:
            # backward compat: promote old singular keys to plural lists
            for old, new in [
                ("faction_id", "faction_ids"),
                ("civilization_id", "civilization_ids"),
                ("asset_type", "asset_types"),
                ("pop_stratum", "pop_strata"),
                ("pop_occupation", "pop_occupations"),
            ]:
                if old in item and new not in item:
                    v = item.pop(old)
                    item[new] = [v] if v is not None else []
        return [NetworkCondition.model_validate(item) for item in items]
    except Exception:
        return []


def _load_travel_networks(conn) -> dict[str, TravelNetwork]:
    """Load all TravelNetworks from DB. Returns {} if table doesn't exist (old DBs)."""
    if not conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='travel_networks'"
    ).fetchone():
        return {}
    out: dict[str, TravelNetwork] = {}
    for raw in conn.execute("SELECT * FROM travel_networks"):
        row = dict(raw)
        tn = TravelNetwork(
            id=UUID(row["id"]),
            name=row["name"],
            member_ids=[UUID(x) for x in _j(row.get("member_ids", "[]"))],
            edges=_load_travel_edges(row.get("edges", "[]")),
            conditions=_load_network_conditions(row.get("conditions", "[]")),
        )
        out[str(tn.id)] = tn
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
            visibility_stall_remaining=int(row.get("visibility_stall_remaining", 0)),
            life_basis=LifeBasis(row.get("life_basis", "carbon")),
            solvent=Solvent(row.get("solvent", "water")),
        )
        out[str(sp.id)] = sp
    return out


def _load_civilizations(conn, universe_age: UniverseAge) -> dict[str, Civilization]:
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
                wealth=row["health_wealth"] if "health_wealth" in row.keys() else row["health_prosperity"],
                cohesion=row["health_cohesion"],
            ),
            primary_species_id=_uuid(row["primary_species_id"]),
            dominant_beliefs=dominant,
            established_beliefs=established,
            pop_ids=[UUID(x) for x in _j(row.get("pop_ids", "[]"))],
            culture_tags=_jd(row.get("culture_tags", "{}")),
            established_culture_tags=_jd(row.get("established_culture_tags", "{}")),
            theistic=bool(row["theistic"]),
            divine_awareness=row["divine_awareness"],
            core_locs=[UUID(x) for x in _j(row.get("core_locs", "[]"))],
            age=_load_civ_age(row, universe_age),
            visibility=float(row.get("visibility", 0.0)),
            pinned=bool(row.get("pinned", 0)),
            visibility_stall_remaining=int(row.get("visibility_stall_remaining", 0)),
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
        if sc_raw == "priest":    # migrate old DB value
            sc_raw = "scholar"
        if sc_raw == "merchant":  # migrate old DB value
            sc_raw = "trader"
        ws_raw = row.get("wild_stratum")
        p = Pop(
            id=UUID(row["id"]),
            name=row.get("name") or None,
            demiurge_authored=bool(row.get("demiurge_authored", 0)),
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
            splinter_cooldown=int(row.get("splinter_cooldown") or 0),
            identity_anchor=_jd(row["identity_anchor"]) if row.get("identity_anchor") else None,
            visibility=float(row.get("visibility", 0.0)),
            pinned=bool(row.get("pinned", 0)),
            visibility_stall_remaining=int(row.get("visibility_stall_remaining", 0)),
            preaching_imago_id=row.get("preaching_imago_id"),
            preaching_goal_cooldown_until=int(row.get("preaching_goal_cooldown_until") or 0),
            occupation=row.get("occupation", ""),
            linked_pop_ids=_jd(row.get("linked_pop_ids", "{}")),
            active_directives=_load_directives(row.get("active_directives", "[]")),
            asset_crew_for=row.get("asset_crew_for") or None,
            faction_ids=[UUID(fid) for fid in _j(row.get("faction_ids", "[]"))],
            pop_state=_load_pop_agent_state(row.get("pop_state")),
        )
        out[str(p.id)] = p
    return out


def _load_mortals(conn, universe_age: UniverseAge) -> dict[str, NotableMortal]:
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
            status_tags=_j(row.get("status_tags", "[]")),
            culture_tags=_jd(row.get("culture_tags", "{}")),
            skill_tags=_jd(row.get("skill_tags", "{}")),
            alignment=row["alignment"],
            chrono_age=row["chrono_age"],
            bio_age=row["bio_age"],
            birthday=_load_birthday(row, universe_age),
            appointed_by_demiurge=_uuid(row["appointed_by_demiurge"]),
            appointed_by_luminary=_uuid(row["appointed_by_luminary"]),
            home_location=UUID(row["home_location"]),
            current_location=UUID(row["current_location"]),
            pinned=bool(row.get("pinned", 0)),
            visibility_stall_remaining=int(row.get("visibility_stall_remaining", 0)),
            active_goal=_load_proxius_goal(row.get("active_goal_json")),
            travel_intent=_load_travel_intent(row.get("travel_intent_json")),
            fatigue=float(row.get("fatigue") or 0.0),
            faction_ids=[UUID(x) for x in _j(row.get("faction_ids", "[]"))],
            led_faction_ids=[UUID(x) for x in _j(row.get("led_faction_ids", "[]"))],
            assets=_load_mortal_assets(row.get("assets")),
            knowledge_base=_load_knowledge_base(row.get("knowledge_base")),
            mortal_state=_load_mortal_state(row.get("mortal_state") or row.get("civilian_state")),
            pop_id=_uuid(row.get("pop_id")),
            pop_milieu=_uuid(row.get("pop_milieu")),
            proxius_appointed_tick=row.get("proxius_appointed_tick"),
            herald_appointed_tick=row.get("herald_appointed_tick"),
            origin_pop_subsumed=bool(row.get("origin_pop_subsumed", 0)),
            last_audit_text=row.get("last_audit_text"),
            last_audit_tick=(int(row["last_audit_tick"]) if row.get("last_audit_tick") is not None else None),
            occupation=row.get("occupation", ""),
        )
        out[str(m.id)] = m
    return out


def _load_mortal_assets(raw: Optional[str]) -> list[MortalAsset]:
    if not raw:
        return []
    try:
        return [MortalAsset.model_validate(a) for a in json.loads(raw)]
    except Exception:
        return []


def _load_knowledge_base(raw: Optional[str]) -> Optional[KnowledgeBase]:
    if not raw:
        return None
    try:
        return KnowledgeBase.model_validate_json(raw)
    except Exception:
        return None


def _load_mortal_state(raw: Optional[str]) -> Optional[MortalAgentState]:
    if not raw:
        return None
    try:
        return MortalAgentState.model_validate_json(raw)
    except Exception:
        return None


def _load_directives(raw: Optional[str]) -> list:
    if not raw:
        return []
    try:
        from core.universe_core import Directive
        import json
        items = json.loads(raw)
        return [Directive.model_validate(d) for d in items]
    except Exception:
        return []


def _load_pop_agent_state(raw):
    if not raw:
        return None
    try:
        from core.agent_core import PopAgentState
        return PopAgentState.model_validate_json(raw)
    except Exception:
        return None


def _load_factions(conn) -> "dict[str, Faction]":
    try:
        rows = conn.execute("SELECT * FROM factions").fetchall()
    except Exception:
        return {}  # table absent in old DBs
    result: dict[str, Faction] = {}
    for raw in rows:
        row = dict(raw)
        directives = _load_directives(row.get("active_directives", "[]"))
        f = Faction(
            id=UUID(row["id"]),
            name=row["name"],
            description=row.get("description", ""),
            civilization_id=_uuid(row.get("civilization_id")),
            member_pop_ids=[UUID(mid) for mid in _j(row.get("member_pop_ids", "[]"))],
            member_mortal_ids=[UUID(mid) for mid in _j(row.get("member_mortal_ids", "[]"))],
            mortal_leader_ids=[UUID(mid) for mid in _j(row.get("mortal_leader_ids", "[]"))],
            active_directives=directives,
            visibility=float(row.get("visibility", 1.0)),
            pinned=bool(row.get("pinned", 0)),
        )
        result[str(f.id)] = f
    return result


def _load_collectible_resource(raw: Optional[str]) -> Optional[CollectibleResource]:
    if not raw:
        return None
    try:
        return CollectibleResource.model_validate_json(raw)
    except Exception:
        return None


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


def _load_travel_intent(raw: Optional[str]) -> Optional[TravelIntent]:
    if not raw:
        return None
    try:
        return TravelIntent.model_validate_json(raw)
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
        max_affiliated_domains=int(row.get("max_affiliated_domains", 3) or 3),
        tracked_essence_domains=_j(row.get("tracked_essence_domains", "[]")),
        revelation_pools=_load_revelation_pools(row),
        revealed_imagines=int(row.get("revealed_imagines", 0) or 0),
        lifetime_revelation=float(row.get("lifetime_revelation", 0.0) or 0.0),
    )


def _load_essence(conn) -> EssenceStockpile:
    row = dict(conn.execute("SELECT * FROM essence").fetchone())
    return EssenceStockpile(
        actual=row["actual"],
        suspicious=float(row["suspicious"] if "suspicious" in row else row.get("apparent", 0.0)),
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
        pop_contact_base_rate=float(row.get("pop_contact_base_rate", 0.005)),
        cross_civ_contact_factor=float(row.get("cross_civ_contact_factor", 0.15)),
        cross_civ_scale_penalty=float(row.get("cross_civ_scale_penalty", 0.08)),
        cross_species_contact_factor=float(row.get("cross_species_contact_factor", 0.50)),
        cross_stratum_contact_factor=float(row.get("cross_stratum_contact_factor", 0.70)),
        values_stubbornness_factor=float(row.get("values_stubbornness_factor", 0.1)),
        peripheral_pop_belief_weight=float(row.get("peripheral_pop_belief_weight", 0.25)),
        peripheral_pop_culture_weight=float(row.get("peripheral_pop_culture_weight", 0.25)),
    )


def _load_civ_momentum(conn) -> dict[str, CivilizationMomentum]:
    out = {}
    for row in conn.execute("SELECT * FROM civ_momentum"):
        cid = row["civilization_id"]
        out[cid] = CivilizationMomentum(
            civilization_id=UUID(cid),
            stability_delta=row["stability_delta"],
            wealth_delta=row["wealth_delta"] if "wealth_delta" in row.keys() else row["prosperity_delta"],
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
            successful_ticks=row.get("successful_ticks", 0),
            started_at_tick=row["started_at_tick"],
            repeating=bool(row.get("repeating", 0)),
            momentum=float(row.get("momentum", 0.0)),
        )
    return out


def _load_pending_resume(conn) -> dict[str, OngoingAction]:
    out: dict[str, OngoingAction] = {}
    try:
        rows = conn.execute("SELECT * FROM pending_resume").fetchall()
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
            successful_ticks=row.get("successful_ticks", 0),
            started_at_tick=row["started_at_tick"],
            repeating=bool(row.get("repeating", 0)),
            momentum=float(row.get("momentum", 0.0)),
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
        culture_vectors: list[CultureVector] = []
        cv_data = row.get("culture_vectors", "[]")
        for cv_dict in json.loads(cv_data) if cv_data else []:
            culture_vectors.append(CultureVector(
                culture_tag=cv_dict["culture_tag"],
                direction=cv_dict["direction"],
                notes=cv_dict.get("notes", ""),
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
            target_loc_id=_uuid(row.get("target_loc_id")),
            domain_vectors=domain_vectors,
            culture_vectors=culture_vectors,
            domain_shift_rate=row.get("domain_shift_rate", 0.10),
            divine_awareness_rate=row.get("divine_awareness_rate", 0.0),
            attention_per_tick=row.get("attention_per_tick", 0.0),
            imago_node_id=row.get("imago_node_id"),
            framing=row.get("framing"),
            concept=row.get("concept", ""),
        )
        out[row["id"]] = event
    return out
