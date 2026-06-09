from __future__ import annotations
import math
import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.universe_core import Pop, PopLocation, Faction

from core.agent_core import (
    PopAgentState, PopNeed, ResourceFact, StockpileFact, ResourceStockpile, can_access_stockpile,
    load_cargo as _load_cargo_fn, unload_cargo as _unload_cargo_fn, TravelIntent,
    MORTAL_CARGO_SLOT_CAPACITY,
)


def _cargo_slot_cap(pop) -> float:
    """Per-slot cargo capacity for this pop, scaled by headcount (10^size_fractional)."""
    return MORTAL_CARGO_SLOT_CAPACITY * (10 ** pop.size_fractional)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

POP_FOOD_RESOURCE_TYPES = ("food_flora", "food_fauna")
NEED_FILL_RATE = 0.08
SUSTENANCE_CONSUME_RATE = 0.05  # kept for back-compat; superseded by split rates below

NOURISHMENT_CONSUME_RATE = 0.05
HYDRATION_CONSUME_RATE   = 0.05
NOURISHMENT_FILL_RATE    = 0.08
HYDRATION_FILL_RATE      = 0.08
BASE_FORAGE_YIELD        = 0.1   # fallback when no matching collectible_resource

# Resource types → biochem categories for consumption pass
_RESOURCE_BIOCHEM: dict[str, str] = {
    "food_flora":            "basis",
    "food_fauna":            "basis",
    "silicate_flora":        "basis",
    "silicate_fauna":        "basis",
    "methane_flora":         "basis",
    "methane_fauna":         "basis",
    "potable_water":         "solvent",
    "potable_sulfuric_acid": "solvent",
    "potable_ammonia":       "solvent",
    "potable_methane_liq":   "solvent",
}

ACTION_NEED_MAP: dict[str, str] = {
    "forage":        "nourishment",
    "hunt":          "nourishment",
    "collect":       "nourishment",
    "commune":       "cohesion",
    "revel":         "cohesion",
    "enact_rituals": "purpose",
    "load_cargo":    "purpose",
    "deposit_cargo": "purpose",
    "build":         "shelter",
    "fortify":       "safety",
    "migrate":       "wanderlust",
    "raid":          "safety",
    "fight":         "safety",
    "rout":          "safety",
}

ALL_ACTIONS: list[str] = list(ACTION_NEED_MAP.keys())
STUB_ACTIONS: frozenset[str] = frozenset({"raid", "fight", "rout"})

_COMPETENCY: dict[str, dict[str, float]] = {
    "wild":       {"forage": 1.5, "hunt": 1.5, "collect": 1.2, "migrate": 1.3},
    "feral":      {"forage": 1.4, "hunt": 1.4, "migrate": 1.2},
    "underclass": {"forage": 1.2},
    "common":     {"forage": 1.3, "hunt": 1.2, "collect": 1.2},
    "artisan":    {"build": 1.5, "fortify": 1.2},
    "trader":     {"collect": 1.3},
    "warrior":    {"fortify": 1.5},
    "scholar":    {"enact_rituals": 1.5, "commune": 1.2},
    "elite":      {"commune": 1.1, "enact_rituals": 1.1},
}

OCCUPATION_BASELINE_WEIGHTS: dict[str, dict[str, float]] = {
    "forager":      {"forage": 0.25, "hunt": 0.20, "migrate": 0.15},
    "raider":       {"hunt": 0.25,   "migrate": 0.20, "forage": 0.10},
    "outcast":      {"forage": 0.20, "migrate": 0.25, "hunt": 0.15},
    "criminal":     {"forage": 0.15, "migrate": 0.20, "hunt": 0.15},
    "bonded":       {"build": 0.20,  "forage": 0.15},
    "dispossessed": {"forage": 0.20, "migrate": 0.15},
    "producer":     {"forage": 0.20, "hunt": 0.15, "collect": 0.10},
    "laborer":      {"build": 0.20,  "forage": 0.10, "collect": 0.15},
    "service":      {"commune": 0.15, "collect": 0.10},
    "transport":    {"migrate": 0.20, "collect": 0.15},
    "professional": {"collect": 0.20, "commune": 0.10},
    "crafter":      {"build": 0.25,  "collect": 0.15},
    "builder":      {"build": 0.30,  "fortify": 0.15},
    "engineer":     {"build": 0.25,  "fortify": 0.20},
    "technician":   {"build": 0.20,  "fortify": 0.15},
    "healer":       {"commune": 0.20, "enact_rituals": 0.10},
    "artist":       {"revel": 0.20,  "commune": 0.15},
    "merchant":     {"collect": 0.30, "migrate": 0.15},
    "financier":    {"collect": 0.25, "commune": 0.10},
    "executive":    {"collect": 0.20, "commune": 0.15},
    "soldier":      {"fortify": 0.25, "hunt": 0.15},
    "officer":      {"fortify": 0.20, "commune": 0.10},
    "guard":        {"fortify": 0.25, "build": 0.10},
    "mercenary":    {"fortify": 0.20, "hunt": 0.20},
    "militia":      {"fortify": 0.20, "hunt": 0.10},
    "clergy":       {"enact_rituals": 0.30, "commune": 0.20},
    "scientist":    {"collect": 0.20, "commune": 0.15},
    "academic":     {"commune": 0.20, "enact_rituals": 0.15},
    "poli_admin":   {"commune": 0.20, "revel": 0.15},
    "noble":        {"revel": 0.25,  "commune": 0.15},
}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _public_stockpile(pop_loc) -> ResourceStockpile:
    """Return the public ResourceStockpile at this location, creating one if absent."""
    for s in pop_loc.stockpiles:
        if s.owner_faction_id is None and s.owner_band_id is None:
            return s
    s = ResourceStockpile()
    pop_loc.stockpiles.append(s)
    return s


def _entitled_stockpile(pop, pop_loc, factions: dict) -> ResourceStockpile:
    """Return the stockpile this pop should gather into at pop_loc.

    At faction home_location: faction-owned stockpile (created if absent).
    Away from home with a band: band-owned stockpile (created if absent).
    Otherwise: public stockpile.
    """
    from uuid import UUID as _UUID
    try:
        _faction_id = _UUID(str(pop.faction_ids[0])) if pop.faction_ids else None
    except Exception:
        _faction_id = None
    try:
        _band_id = _UUID(str(pop.band_id)) if pop.band_id is not None else None
    except Exception:
        _band_id = None

    faction = factions.get(str(_faction_id)) if _faction_id else None
    if (
        faction is not None
        and faction.home_location_id is not None
        and str(faction.home_location_id) == str(pop_loc.id)
    ):
        for s in pop_loc.stockpiles:
            if s.owner_faction_id == _faction_id and s.owner_band_id is None:
                return s
        s = ResourceStockpile(owner_faction_id=_faction_id)
        pop_loc.stockpiles.append(s)
        return s
    if _band_id is not None:
        for s in pop_loc.stockpiles:
            if s.owner_band_id == _band_id:
                return s
        s = ResourceStockpile(owner_band_id=_band_id)
        pop_loc.stockpiles.append(s)
        return s
    return _public_stockpile(pop_loc)


def _charity_rate(pop, factions: dict) -> float:
    """Return the faction charity donation rate for this pop (0.0 if none)."""
    faction_id = pop.faction_ids[0] if pop.faction_ids else None
    if faction_id is None:
        return 0.0
    faction = factions.get(str(faction_id))
    return faction.values.get("charity", 0.0) if faction else 0.0


def _find_matching_resources(collectible_resources: list, action: str) -> list:
    """Return CollectibleResources usable by this action (action_types=[] means any)."""
    return [
        cr for cr in collectible_resources
        if (not cr.action_types or action in cr.action_types)
        and cr.current_yield > 0
    ]

def _pop_need_urgency(need: PopNeed) -> float:
    """Continuous urgency in [0, ~1.5]. 0 when held; small background when satisfied; >1 when urgent."""
    if need.satiation_hold > 0:
        return 0.0
    if need.satisfaction >= need.pressing_threshold:
        span = max(1.0 - need.pressing_threshold, 0.01)
        return need.decay_rate * (1.0 - need.satisfaction) / span
    if need.satisfaction <= need.urgent_threshold:
        return 1.0 + (need.urgent_threshold - need.satisfaction) / max(need.urgent_threshold, 0.01) * 0.5
    span = need.pressing_threshold - need.urgent_threshold
    return (need.pressing_threshold - need.satisfaction) / max(span, 0.01)


def _pop_competency_modifier(pop, action: str) -> float:
    stratum = pop.stratum if pop.stratum else "common"
    mod = _COMPETENCY.get(stratum, {}).get(action)
    if mod is None:
        # For wild pops with a wild_stratum set, stratum returns the wild stratum value
        # (e.g., "apex", "herd", "carrion") which isn't in _COMPETENCY.
        # Fall back to the "wild" entry for wild competency bonuses.
        from core.universe_core import SocialStratum
        if getattr(pop, "social_class", None) == SocialStratum.WILD:
            mod = _COMPETENCY.get("wild", {}).get(action)
    return mod if mod is not None else 1.0


def _pop_spillover_factor(actor, neighbor, factions: dict) -> float:
    """Return the need-satisfaction spillover multiplier from actor to neighbor.

    Tiers:
      cross-factional (both in factions, no overlap) → 0.0
      co-factional (share ≥1 faction)               → max(link_factor, 0.75)
      linked only                                    → link_factor
      neither / one unfactioned                      → 0.5
    """
    from logic.sim_utils import compute_link_factor
    actor_fids    = {str(fid) for fid in actor.faction_ids}
    neighbor_fids = {str(fid) for fid in neighbor.faction_ids}
    shared_fids   = actor_fids & neighbor_fids

    if actor_fids and neighbor_fids and not shared_fids:
        return 0.0  # cross-factional rivals

    base = actor.linked_pop_ids.get(str(neighbor.id))
    lf   = compute_link_factor(actor, neighbor, base) if base is not None else None

    if shared_fids:
        return max(lf if lf is not None else 0.0, 0.75)

    if lf is not None:
        return lf

    return 0.5


# Civic actions whose effects spill over to co-located pops.
_CIVIC_ACTIONS: frozenset[str] = frozenset({"fortify", "build", "commune", "revel", "enact_rituals"})


def _apply_spillover(actor, colocated_pops: list, need_name: str, gain: float, factions: dict) -> None:
    """Apply a fraction of `gain` to `need_name` on each co-located pop."""
    for neighbor in colocated_pops:
        if neighbor.pop_state is None:
            continue
        factor = _pop_spillover_factor(actor, neighbor, factions)
        if factor <= 0.0:
            continue
        nb_need = next((n for n in neighbor.pop_state.needs if n.name == need_name), None)
        if nb_need is not None:
            nb_need.satisfaction = min(1.0, nb_need.satisfaction + gain * factor)


def _collect_directive_modifiers(pop, factions: dict, pops: dict | None = None) -> dict[str, float]:
    mods: dict[str, float] = {}
    directives = list(pop.active_directives)
    for fid in pop.faction_ids:
        faction = factions.get(str(fid))
        if faction:
            directives.extend(faction.active_directives)
    pop_id_str = str(pop.id)
    for d in directives:
        # territory_pop_ids non-empty → directive only applies to listed pops
        if d.territory_pop_ids and pop_id_str not in {str(tid) for tid in d.territory_pop_ids}:
            continue
        for action, delta in d.action_weight_modifiers.items():
            mods[action] = mods.get(action, 0.0) + delta
        if d.directive_type == "hold_position":
            # Fully suppress migration: -10 exceeds max possible urgency (~1.5 * 1.5 competency)
            mods["migrate"] = mods.get("migrate", 0.0) - 10.0
        elif d.directive_type == "patrol":
            loc_ids = {str(lid) for lid in d.territory_location_ids}
            if loc_ids and str(pop.current_location) in loc_ids:
                mods["fortify"] = mods.get("fortify", 0.0) + _PATROL_FORTIFY_BOOST
                mods["hunt"]    = mods.get("hunt",    0.0) + _PATROL_HUNT_BOOST
        elif d.directive_type == "supply_run":
            phase = _supply_run_phase(pop, d, pops or {})
            if phase == "load":
                mods["load_cargo"]    = mods.get("load_cargo",    0.0) + _SUPPLY_RUN_CARGO_BOOST
            elif phase == "deposit":
                mods["deposit_cargo"] = mods.get("deposit_cargo", 0.0) + _SUPPLY_RUN_CARGO_BOOST
    return mods


def _max_slot_modifier(pop, factions: dict) -> int:
    directives = list(pop.active_directives)
    for fid in pop.faction_ids:
        faction = factions.get(str(fid))
        if faction:
            directives.extend(faction.active_directives)
    for d in directives:
        if d.slot_modifier != 0:
            return d.slot_modifier
    return 0

# ---------------------------------------------------------------------------
# Directive fulfillment
# ---------------------------------------------------------------------------

_IDLE_FLOOR            = 0.01   # small uniform baseline preventing all-zero distributions
_PATROL_FORTIFY_BOOST  = 0.30
_PATROL_HUNT_BOOST     = 0.20
_SUPPLY_RUN_CARGO_BOOST = 0.40


def _supply_run_phase(pop, directive, pops: dict):
    """Return the current phase of a supply_run directive for this pop.

    Phases: "load", "travel_to_dest", "deposit", "travel_home", or None if the
    destination pop cannot be resolved this tick.

    target_location_id = the HOME/SOURCE location (where cargo is loaded).
    Destination = target_pop.current_location.
    """
    from uuid import UUID

    target_pop = pops.get(str(directive.target_pop_id)) if directive.target_pop_id else None
    if target_pop is None:
        return None
    dest_loc = target_pop.current_location
    if dest_loc is None:
        return None

    def _same(a, b) -> bool:
        return a is not None and b is not None and UUID(str(a)) == UUID(str(b))

    # cargo_manifest overrides single-type fields when non-empty
    manifest: dict[str, float] = directive.cargo_manifest or {}
    if not manifest and directive.cargo_resource_type:
        manifest = {directive.cargo_resource_type: float(directive.cargo_quantity)}
    has_cargo = any(pop.pop_state.cargo.quantities.get(rt, 0.0) > 0.0 for rt in manifest)

    if _same(pop.current_location, directive.target_location_id):
        # At home/source: load if empty, travel to dest if loaded
        return "travel_to_dest" if has_cargo else "load"
    if _same(pop.current_location, dest_loc):
        # At destination: deposit if loaded, head home if empty
        return "deposit" if has_cargo else "travel_home"
    # In transit
    return "travel_to_dest" if has_cargo else "travel_home"


def _resupply_phase(pop, directive, pop_loc=None) -> str:
    """Return the current phase of a resupply directive for this pop.

    Phases: "dormant", "travel_to_source", "dwell_and_load", "travel_home", "deposit"
    """
    from uuid import UUID

    ps = pop.pop_state
    if ps is None:
        return "dormant"

    manifest: dict[str, float] = directive.cargo_manifest or {}
    if not manifest and directive.cargo_resource_type:
        manifest = {directive.cargo_resource_type: float(directive.cargo_quantity)}

    has_cargo = (
        any(ps.cargo.quantities.get(rt, 0.0) > 0.0 for rt in manifest)
        if manifest else bool(ps.cargo.quantities)
    )

    def _same(a, b) -> bool:
        return a is not None and b is not None and UUID(str(a)) == UUID(str(b))

    at_source = _same(pop.current_location, directive.target_location_id)
    at_home   = _same(pop.current_location, directive.return_location_id)

    if at_source:
        needs_ok = all(
            n.satisfaction >= 0.9
            for n in ps.needs
            if n.name in ("nourishment", "hydration")
        )
        cargo_ok = not manifest or all(
            ps.cargo.quantities.get(rt, 0.0) >= qty
            for rt, qty in manifest.items()
        )
        if needs_ok and cargo_ok:
            return "travel_home"
        # Escape: source is depleted — no manifest resources available to load
        if pop_loc is not None and manifest and not has_cargo:
            source_has_supply = any(
                stk.quantities.get(rt, 0.0) > 0
                for stk in pop_loc.stockpiles
                if can_access_stockpile(pop, stk)
                for rt in manifest
            )
            if not source_has_supply:
                return "travel_home"
        return "dwell_and_load"

    if at_home:
        if has_cargo:
            return "deposit"
        if any(
            n.name in ("nourishment", "hydration") and n.is_pressing
            for n in ps.needs
        ):
            # Only go to source if home can't supply the need locally
            if pop_loc is not None and manifest:
                home_has_supply = any(
                    stk.quantities.get(rt, 0.0) > 0
                    for stk in pop_loc.stockpiles
                    if can_access_stockpile(pop, stk)
                    for rt in manifest
                )
                if home_has_supply:
                    return "dormant"  # Stay and drink locally
            return "travel_to_source"
        return "dormant"

    return "travel_home" if has_cargo else "travel_to_source"


def directive_purpose_increment(directive, actor_location_id, *, pop=None, pops=None) -> float:
    """Return the purpose satisfaction increment earned by executing a directive this tick.

    Each directive_type defines its own completion condition.  Types not yet
    wired return 0.0 so callers don't need to guard for missing cases.
    """
    from uuid import UUID

    def _same_loc(a, b) -> bool:
        if a is None or b is None:
            return False
        return UUID(str(a)) == UUID(str(b))

    if directive.directive_type == "hold_position":
        if _same_loc(directive.target_location_id, actor_location_id):
            return 0.25
        return 0.0

    if directive.directive_type == "patrol":
        loc_ids = {str(lid) for lid in directive.territory_location_ids}
        if loc_ids and str(actor_location_id) in loc_ids:
            return 0.20
        return 0.0

    if directive.directive_type == "supply_run":
        if pop is not None and _supply_run_phase(pop, directive, pops or {}) == "deposit":
            return 0.30
        return 0.0

    if directive.directive_type == "resupply":
        if pop is not None:
            _rs_phase = _resupply_phase(pop, directive)
            if _rs_phase == "deposit":
                return 0.30
            if _rs_phase == "dwell_and_load":
                return 0.05
        return 0.0

    # Other types not yet implemented
    return 0.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_pop_priorities(pop, factions: dict) -> dict[str, float]:
    """4-pass priority computation. Returns dict over ALL_ACTIONS summing to 1.0."""
    ps = pop.pop_state
    if ps is None:
        return {a: 0.0 for a in ALL_ACTIONS}

    needs_by_name = {n.name: n for n in ps.needs}

    # Pass 1: need urgency (stubs always 0; sharing actions split urgency)
    raw: dict[str, float] = {}
    for action in ALL_ACTIONS:
        if action in STUB_ACTIONS:
            raw[action] = 0.0
            continue
        need_name = ACTION_NEED_MAP[action]
        need = needs_by_name.get(need_name)
        urgency = _pop_need_urgency(need) if need else 0.0
        sharing_count = sum(
            1 for a in ALL_ACTIONS
            if a not in STUB_ACTIONS and ACTION_NEED_MAP.get(a) == need_name
        )
        raw[action] = urgency / max(sharing_count, 1)

    # Occupation baseline: additive offset before competency scaling.
    occ_key = pop.occupation.value if hasattr(pop.occupation, "value") else str(pop.occupation)
    for action, baseline in OCCUPATION_BASELINE_WEIGHTS.get(occ_key, {}).items():
        if action in raw and action not in STUB_ACTIONS:
            raw[action] += baseline

    # Uniform idle floor: prevents all-zero distributions when no needs are pressing.
    for action in raw:
        if action not in STUB_ACTIONS:
            raw[action] += _IDLE_FLOOR

    # Pass 2: competency scaling
    weighted = {action: raw[action] * _pop_competency_modifier(pop, action) for action in ALL_ACTIONS}

    # Pass 3: directive weight modifiers (additive; floor at 0)
    mods = _collect_directive_modifiers(pop, factions)
    for action, delta in mods.items():
        if action in weighted:
            weighted[action] = max(0.0, weighted[action] + delta)

    # Pass 4: normalize
    total = sum(weighted.values())
    if total <= 0.0:
        non_stub = [a for a in ALL_ACTIONS if a not in STUB_ACTIONS]
        return {a: (1.0 / len(non_stub) if a not in STUB_ACTIONS else 0.0) for a in ALL_ACTIONS}

    return {action: weighted[action] / total for action in ALL_ACTIONS}


def compute_active_slots(pop, factions: dict) -> int:
    """Compute how many priority slots are active this tick."""
    base = max(2, int(math.floor(pop.size_fractional)))
    ps = pop.pop_state
    if ps is not None and ps.fatigue < 1.0:
        modifier = _max_slot_modifier(pop, factions)
        base = max(1, base + modifier)
    return base


def resolve_pop_actions(
    pop,
    pop_loc,
    priorities: dict[str, float],
    n_slots: int,
    factions: dict,
    current_tick: int = 0,
    colocated_pops: list | None = None,
    state=None,
    in_transit: bool = False,
) -> list[str]:
    """Execute top-N priority actions; return narrative strings for notable events.

    If ``priorities`` is empty (``{}`` or ``[]``), priorities are computed from
    the pop's current needs via ``compute_pop_priorities``.
    """
    narratives: list[str] = []
    ps = pop.pop_state
    if ps is None:
        return narratives

    needs_by_name = {n.name: n for n in ps.needs}

    factions_dict = factions if isinstance(factions, dict) else {}

    # Compute priorities on demand when caller passes none
    if not priorities:
        priorities = compute_pop_priorities(pop, factions_dict)

    # KB co-location sync + yield-aware priority dampening.
    # Pops update their ResourceFacts from the actual current yield at their
    # location each tick, then dampen gathering priorities when yield is low
    # relative to the demand from entitled co-located Pops.
    if pop_loc is not None:
        _loc_id_str = str(pop_loc.id)
        _cr_by_type = {cr.resource_type: cr for cr in pop_loc.collectible_resources}
        # Sync KB ResourceFacts to actual current yields
        for _cr in pop_loc.collectible_resources:
            _rf = next(
                (f for f in ps.knowledge_base.facts
                 if f.fact_type == "resource"
                 and f.location_id == _loc_id_str
                 and f.resource_type == _cr.resource_type),
                None,
            )
            if _rf is not None:
                _rf.resource_yield = _cr.current_yield
                _rf.learned_at_tick = current_tick
            else:
                ps.knowledge_base.facts.append(ResourceFact(
                    location_id=_loc_id_str,
                    resource_type=_cr.resource_type,
                    resource_yield=_cr.current_yield,
                    confidence=1.0,
                    learned_at_tick=current_tick,
                ))
        if not in_transit:
            _ent_d = _entitled_stockpile(pop, pop_loc, factions_dict)

            # Sync StockpileFact: snapshot the entitled stockpile for this location
            _sf = ps.knowledge_base.get_stockpile_fact(_loc_id_str)
            if _sf is not None:
                _sf.quantities = dict(_ent_d.quantities)
                _sf.learned_at_tick = current_tick
            else:
                ps.knowledge_base.facts.append(StockpileFact(
                    location_id=_loc_id_str,
                    quantities=dict(_ent_d.quantities),
                    learned_at_tick=current_tick,
                ))

        # Demand = log-sum of sizes of entitled Pops, with noise.
        # For owned stockpiles (faction or band), sweep all pops in state who can access it
        # so absent entitled pops count against demand and resident gatherers don't under-stock.
        # Public stockpiles use co-located pops. In transit, no shared stockpile exists.
        _stockpile_qtys: dict[str, float] = {} if in_transit else _ent_d.quantities
        if in_transit:
            _demand_pops = []
        elif (_ent_d.owner_faction_id is not None or _ent_d.owner_band_id is not None) and state is not None:
            _demand_pops = [p for p in state.pops.values() if can_access_stockpile(p, _ent_d)]
        else:
            _demand_pops = [p for p in (colocated_pops or []) if can_access_stockpile(p, _ent_d)]
        _demand = sum(
            math.log(p.size_fractional + 1)
            for p in _demand_pops
        ) * random.uniform(0.6, 1.4)
        _demand = max(_demand, 1e-6)
        # Apply asymptotic dampening: yield × stockpile each via ratio / (ratio + 1).
        # Yield dampening: low current yield → deprioritise gathering.
        # Stockpile dampening: large existing stockpile → no need to gather more.
        # Both are multiplied together so either signal independently reduces priority.
        for _ga in ("forage", "hunt", "collect"):
            if _ga not in priorities:
                continue
            _mf = [
                f for f in ps.knowledge_base.facts
                if f.fact_type == "resource"
                and f.location_id == _loc_id_str
                and f.resource_type in _cr_by_type
                and (
                    not _cr_by_type[f.resource_type].action_types
                    or _ga in _cr_by_type[f.resource_type].action_types
                )
            ]
            if _mf:
                _avg_yield = sum(f.resource_yield for f in _mf) / len(_mf)
                _yield_ratio = _avg_yield / _demand
                _yield_d = _yield_ratio / (_yield_ratio + 1.0)
                _stk_qty = sum(_stockpile_qtys.get(f.resource_type, 0.0) for f in _mf) / len(_mf)
                _stk_ratio = _stk_qty / _demand
                _stk_d = 1.0 / (_stk_ratio + 1.0)
                priorities[_ga] *= _yield_d * _stk_d

    # Supply-run travel: set pending destination and boost migrate priority
    _pops_dict: dict = getattr(state, "pops", {}) if state else {}
    _factions_dict_sr = factions if isinstance(factions, dict) else {}
    _pop_id_str = str(pop.id)
    def _sr_scoped(d) -> bool:
        return not d.territory_pop_ids or _pop_id_str in {str(t) for t in d.territory_pop_ids}
    _sr_directives = [d for d in pop.active_directives if d.directive_type == "supply_run" and _sr_scoped(d)]
    for _fid_sr in pop.faction_ids:
        _f_sr = _factions_dict_sr.get(str(_fid_sr))
        if _f_sr:
            _sr_directives.extend(d for d in _f_sr.active_directives if d.directive_type == "supply_run" and _sr_scoped(d))
    for _sd in _sr_directives:
        _sr_phase = _supply_run_phase(pop, _sd, _pops_dict)
        if current_tick < ps.supply_run_skip_until.get(str(_sd.id), 0) and _sr_phase == "load":
            continue  # skip active: delay next outbound run; travel_home still executes
        if _sr_phase == "travel_to_dest":
            _dest_pop_sr = _pops_dict.get(str(_sd.target_pop_id))
            if _dest_pop_sr is not None and _dest_pop_sr.current_location is not None:
                ps.pending_migration_dest = _dest_pop_sr.current_location
                priorities["migrate"] = priorities.get("migrate", 0.0) + 1.0
        elif _sr_phase == "travel_home":
            ps.pending_migration_dest = _sd.target_location_id
            priorities["migrate"] = priorities.get("migrate", 0.0) + 1.0
        elif _sr_phase == "load":
            priorities["load_cargo"] = priorities.get("load_cargo", 0.0) + _SUPPLY_RUN_CARGO_BOOST
            ps.pending_migration_dest = None
        elif _sr_phase == "deposit":
            priorities["deposit_cargo"] = priorities.get("deposit_cargo", 0.0) + _SUPPLY_RUN_CARGO_BOOST
            ps.pending_migration_dest = None
        else:
            # None (dest pop unresolved) — clear stale pending destination
            ps.pending_migration_dest = None
        break  # one supply_run directive at a time

    # Resupply: need-triggered reactive resupply for resource-scarce bands
    _resupply_directives = [d for d in pop.active_directives if d.directive_type == "resupply" and _sr_scoped(d)]
    for _fid_rs in pop.faction_ids:
        _f_rs = _factions_dict_sr.get(str(_fid_rs))
        if _f_rs:
            _resupply_directives.extend(
                d for d in _f_rs.active_directives if d.directive_type == "resupply" and _sr_scoped(d)
            )
    for _rd in _resupply_directives:
        _rs_phase = _resupply_phase(pop, _rd, pop_loc=pop_loc)
        if _rs_phase == "dormant":
            break
        elif _rs_phase == "travel_to_source":
            if _rd.target_location_id is not None:
                ps.pending_migration_dest = _rd.target_location_id
            priorities["migrate"] = priorities.get("migrate", 0.0) + 1.0
        elif _rs_phase == "dwell_and_load":
            priorities["load_cargo"] = priorities.get("load_cargo", 0.0) + _SUPPLY_RUN_CARGO_BOOST
            priorities["forage"]     = priorities.get("forage",     0.0) + 0.5
            priorities["hunt"]       = priorities.get("hunt",       0.0) + 0.5
            _purpose_rs = needs_by_name.get("purpose")
            if _purpose_rs:
                _purpose_rs.satisfaction = max(_purpose_rs.satisfaction, 0.4)
            ps.pending_migration_dest = None
        elif _rs_phase == "travel_home":
            if _rd.return_location_id is not None:
                ps.pending_migration_dest = _rd.return_location_id
            priorities["migrate"] = priorities.get("migrate", 0.0) + 1.0
        elif _rs_phase == "deposit":
            priorities["deposit_cargo"] = priorities.get("deposit_cargo", 0.0) + _SUPPLY_RUN_CARGO_BOOST
            ps.pending_migration_dest = None
        break  # one resupply directive at a time

    # Disable actions unavailable while in transit
    if in_transit:
        for _blocked in ("collect", "load_cargo", "deposit_cargo", "migrate"):
            priorities.pop(_blocked, None)

    # Select top-N active (non-stub, non-zero) actions by weight
    ranked = sorted(
        [(a, w) for a, w in priorities.items() if a not in STUB_ACTIONS and w > 0],
        key=lambda x: x[1],
        reverse=True,
    )
    active = [action for action, _ in ranked[:n_slots]]

    for action in active:
        weight = priorities[action]
        competency = _pop_competency_modifier(pop, action)
        output = weight * (10 ** pop.size_fractional) * competency

        if action in ("forage", "hunt", "collect"):
            matching = _find_matching_resources(pop_loc.collectible_resources, action)
            if not in_transit:
                _ent = _entitled_stockpile(pop, pop_loc, factions_dict)
                _charity = _charity_rate(pop, factions_dict)
            if matching:
                per_resource_output = output / len(matching)
                for cr in matching:
                    actual = min(per_resource_output, cr.current_yield)
                    cr.current_yield = max(0.0, cr.current_yield - actual)
                    if in_transit:
                        # Deposit gathered resources into the pop's own cargo
                        _c_cur = ps.cargo.quantities.get(cr.resource_type, 0.0)
                        if cr.resource_type in ps.cargo.quantities or len(ps.cargo.quantities) < ps.cargo.max_slots:
                            _room = _cargo_slot_cap(pop) - _c_cur
                            _dep = min(actual, max(0.0, _room))
                            if _dep > 0:
                                ps.cargo.quantities[cr.resource_type] = _c_cur + _dep
                    else:
                        _charity_amt = actual * _charity
                        _ent_amt = actual - _charity_amt
                        _ent.quantities[cr.resource_type] = _ent.quantities.get(cr.resource_type, 0.0) + _ent_amt
                        if _charity_amt > 0:
                            _pub_shared = _public_stockpile(pop_loc)
                            _pub_shared.quantities[cr.resource_type] = _pub_shared.quantities.get(cr.resource_type, 0.0) + _charity_amt
                            _pub_shared.is_charity = True
            elif not in_transit:
                # Environment fallback (stationary pops only)
                _charity_amt_f = output * BASE_FORAGE_YIELD * _charity
                _ent_amt_f = output * BASE_FORAGE_YIELD - _charity_amt_f
                if action == "forage":
                    _ent.quantities["food_flora"] = _ent.quantities.get("food_flora", 0.0) + _ent_amt_f
                    if _charity_amt_f > 0:
                        _pub_f = _public_stockpile(pop_loc)
                        _pub_f.quantities["food_flora"] = _pub_f.quantities.get("food_flora", 0.0) + _charity_amt_f
                        _pub_f.is_charity = True
                elif action == "hunt":
                    _ent.quantities["food_fauna"] = _ent.quantities.get("food_fauna", 0.0) + _ent_amt_f
                    if _charity_amt_f > 0:
                        _pub_h = _public_stockpile(pop_loc)
                        _pub_h.quantities["food_fauna"] = _pub_h.quantities.get("food_fauna", 0.0) + _charity_amt_f
                        _pub_h.is_charity = True
                # collect with no matching resource → no output

        elif action == "commune":
            gain = output * 0.10
            need = needs_by_name.get("cohesion")
            if need:
                need.satisfaction = min(1.0, need.satisfaction + gain)
            _apply_spillover(pop, colocated_pops or [], "cohesion", gain, factions)

        elif action == "revel":
            gain = output * 0.15
            need = needs_by_name.get("cohesion")
            if need:
                need.satisfaction = min(1.0, need.satisfaction + gain)
            _apply_spillover(pop, colocated_pops or [], "cohesion", gain, factions)

        elif action == "enact_rituals":
            gain = output * NEED_FILL_RATE
            need = needs_by_name.get("purpose")
            if need:
                need.satisfaction = min(1.0, need.satisfaction + gain)
            _apply_spillover(pop, colocated_pops or [], "purpose", gain, factions)

        elif action == "build":
            gain = output * NEED_FILL_RATE
            need = needs_by_name.get("shelter")
            if need:
                need.satisfaction = min(1.0, need.satisfaction + gain)
            _apply_spillover(pop, colocated_pops or [], "shelter", gain, factions)

        elif action == "fortify":
            gain = output * NEED_FILL_RATE
            need = needs_by_name.get("safety")
            if need:
                need.satisfaction = min(1.0, need.satisfaction + gain)
            _apply_spillover(pop, colocated_pops or [], "safety", gain, factions)
            pop_loc.danger = max(0.0, pop_loc.danger - output * 0.005)

        elif action == "load_cargo":
            _load_handled = False
            for _sd in _sr_directives:
                if _supply_run_phase(pop, _sd, _pops_dict) == "load":
                    _pub = _entitled_stockpile(pop, pop_loc, factions_dict)
                    _manifest = _sd.cargo_manifest or {}
                    if not _manifest and _sd.cargo_resource_type:
                        _manifest = {_sd.cargo_resource_type: float(_sd.cargo_quantity)}
                    _any_loaded = False
                    _cap = _cargo_slot_cap(pop)
                    for _rt, _qty in _manifest.items():
                        if _load_cargo_fn(ps.cargo, _pub, _rt, _qty, _cap) > 0:
                            _any_loaded = True
                    if _any_loaded:
                        _purpose = needs_by_name.get("purpose")
                        if _purpose:
                            _purpose.satisfaction = min(1.0, _purpose.satisfaction + 0.10)
                    _load_handled = True
                    break
            if not _load_handled:
                for _rd in _resupply_directives:
                    if _resupply_phase(pop, _rd) == "dwell_and_load":
                        _pub = _entitled_stockpile(pop, pop_loc, factions_dict)
                        _manifest = _rd.cargo_manifest or {}
                        if not _manifest and _rd.cargo_resource_type:
                            _manifest = {_rd.cargo_resource_type: float(_rd.cargo_quantity)}
                        _any_loaded = False
                        _cap = _cargo_slot_cap(pop)
                        for _rt, _qty in _manifest.items():
                            if _load_cargo_fn(ps.cargo, _pub, _rt, _qty, _cap) > 0:
                                _any_loaded = True
                        if _any_loaded:
                            _purpose = needs_by_name.get("purpose")
                            if _purpose:
                                _purpose.satisfaction = min(1.0, _purpose.satisfaction + 0.10)
                        break

        elif action == "deposit_cargo":
            _deposit_handled = False
            for _sd in _sr_directives:
                if _supply_run_phase(pop, _sd, _pops_dict) == "deposit":
                    _pub = _public_stockpile(pop_loc)
                    _manifest = _sd.cargo_manifest or {}
                    if not _manifest and _sd.cargo_resource_type:
                        _manifest = {_sd.cargo_resource_type: float(_sd.cargo_quantity)}
                    # Adaptive interval: compare pre-deposit stockpile to last_deposit_qty
                    # to infer how much was consumed since the last run.
                    _loc_id_str_dep = str(pop_loc.id)
                    _sf_dep = ps.knowledge_base.get_stockpile_fact(_loc_id_str_dep)
                    _default_interval = _sd.interval_ticks if _sd.interval_ticks > 0 else 5
                    _interval = ps.supply_run_interval.get(str(_sd.id), _default_interval)
                    if _sf_dep and _sf_dep.last_deposit_qty:
                        _last = _sf_dep.last_deposit_qty
                        _total_last = sum(_last.values())
                        if _total_last > 0:
                            _pre_qty = _sf_dep.quantities  # synced this tick before deposit
                            _consumed = sum(
                                max(0.0, _last.get(_rt, 0.0) - _pre_qty.get(_rt, 0.0))
                                for _rt in _last
                            )
                            _ratio = _consumed / _total_last
                            if _ratio >= 0.8:
                                _interval = max(1, _interval - 1)   # hungry — come back sooner
                            elif _ratio <= 0.2:
                                _interval += 1                       # barely touched — wait longer
                    ps.supply_run_interval[str(_sd.id)] = _interval

                    for _rt, _qty in _manifest.items():
                        _unload_cargo_fn(ps.cargo, _pub, _rt, _qty)

                    # Record what was deposited so the next visit can estimate consumption.
                    if _sf_dep is not None:
                        _sf_dep.last_deposit_qty = {
                            _rt: _qty for _rt, _qty in _manifest.items() if _qty > 0
                        }

                    # At-deposit check: if destination is well-stocked relative to demand,
                    # delay the next run by the current adapted interval.
                    _post_qtys = _pub.quantities
                    _total_stocked = sum(_post_qtys.get(_rt, 0.0) for _rt in _manifest)
                    _is_pub_owned = _pub.owner_faction_id is not None or _pub.owner_band_id is not None
                    if _is_pub_owned and state is not None:
                        _dep_demand_pops = [p for p in state.pops.values() if can_access_stockpile(p, _pub) and p.id != pop.id]
                    else:
                        _dep_demand_pops = [p for p in (colocated_pops or []) if can_access_stockpile(p, _pub) and p.id != pop.id]
                    _dest_demand = sum(
                        math.log(p.size_fractional + 1) for p in _dep_demand_pops
                    ) * random.uniform(0.6, 1.4)
                    _dest_demand = max(_dest_demand, 1e-6)
                    if _total_stocked / _dest_demand >= 1.0:
                        ps.supply_run_skip_until[str(_sd.id)] = current_tick + _interval
                    _deposit_handled = True
                    break
            if not _deposit_handled:
                for _rd in _resupply_directives:
                    if _resupply_phase(pop, _rd) == "deposit":
                        _pub = _entitled_stockpile(pop, pop_loc, factions_dict)
                        _manifest = _rd.cargo_manifest or {}
                        if not _manifest and _rd.cargo_resource_type:
                            _manifest = {_rd.cargo_resource_type: float(_rd.cargo_quantity)}
                        for _rt, _qty in _manifest.items():
                            _unload_cargo_fn(ps.cargo, _pub, _rt, _qty)
                        _purpose = needs_by_name.get("purpose")
                        if _purpose:
                            _purpose.satisfaction = min(1.0, _purpose.satisfaction + 0.30)
                        break

        elif action == "migrate":
            _dest_id = ps.pending_migration_dest
            if _dest_id is not None and state is not None and pop.migration_travel_location_id is None:
                _origin_id = pop.current_location
                from utilities.travel_routing import find_route, route_fact_cost
                from utilities.travel_routing import get_or_create_travel_location
                _route = find_route(state, _origin_id, _dest_id)
                if _route and len(_route) >= 2:
                    # Build legs dict: each waypoint → tick cost for leg starting there
                    _legs: dict[str, int] = {}
                    for _i, _wp in enumerate(_route):
                        _wp_str = str(_wp)
                        if _i < len(_route) - 1:
                            _cost = route_fact_cost(state, _route[_i], _route[_i + 1])
                            _legs[_wp_str] = math.floor(_cost * math.sqrt(pop.size_fractional)) + 1
                        else:
                            _legs[_wp_str] = 0  # destination marker
                    _total_ticks = sum(v for v in _legs.values())
                    _tl = get_or_create_travel_location(state, _legs)
                    _tl.skip_initial_tick = True
                    if pop.id not in _tl.pop_ids:
                        _tl.pop_ids.append(pop.id)
                    pop.migration_ticks_remaining = _total_ticks
                    pop.migration_destination_id = _dest_id
                    pop.migration_travel_location_id = _tl.id

                    # Pre-departure: fill cargo from accessible stockpiles at origin.
                    # Skip for supply_run/resupply carriers — those directives manage cargo
                    # explicitly; loading here would silently take back what was just deposited.
                    _cargo_directive_active = any(
                        d.directive_type in ("supply_run", "resupply")
                        for d in pop.active_directives
                    ) or any(
                        d.directive_type in ("supply_run", "resupply")
                        for _f in factions_dict.values()
                        for d in getattr(_f, "active_directives", [])
                        if hasattr(_f, "member_pop_ids") and pop.id in _f.member_pop_ids
                    )
                    if not _cargo_directive_active and pop_loc is not None:
                        _cap = _cargo_slot_cap(pop)
                        for _stk in pop_loc.stockpiles:
                            if not can_access_stockpile(pop, _stk):
                                continue
                            for _rt, _avail in list(_stk.quantities.items()):
                                if _avail > 0:
                                    _load_cargo_fn(ps.cargo, _stk, _rt, _avail, _cap)

                    # Leave origin immediately
                    pop.current_location = _tl.id

                    # Band cascade: other band members at this location join automatically
                    _band_id = pop.band_id
                    if _band_id is not None and state is not None:
                        for _bp in state.pops.values():
                            if (
                                _bp.id != pop.id
                                and _bp.band_id == _band_id
                                and _bp.current_location == _origin_id
                                and _bp.migration_travel_location_id is None
                            ):
                                if _bp.id not in _tl.pop_ids:
                                    _tl.pop_ids.append(_bp.id)
                                _bp.migration_ticks_remaining = _total_ticks
                                _bp.migration_destination_id = _dest_id
                                _bp.migration_travel_location_id = _tl.id
                                _bp.current_location = _tl.id

                    # Mortal embedding: mortals with matching band_id and no active travel
                    if _band_id is not None and state is not None:
                        for _m in state.mortals.values():
                            _m_ti = getattr(_m, "travel_intent", None)
                            _m_ti_active = (
                                _m_ti is not None
                                and _m_ti.travel_location_id is not None
                                and state.locations.get(str(_m_ti.travel_location_id)) is not None
                            )
                            if (
                                getattr(_m, "band_id", None) == _band_id
                                and _m.current_location == _origin_id
                                and not _m_ti_active
                            ):
                                if _m.id not in _tl.occupants:
                                    _tl.occupants.append(_m.id)
                                _m.current_location = _tl.id
                                _m.travel_intent = TravelIntent(
                                    travel_location_id=_tl.id,
                                    target_pop_id=pop.id,
                                )

            # Partial wanderlust satisfaction for initiating or continuing migration
            need = needs_by_name.get("wanderlust")
            if need:
                need.satisfaction = min(1.0, need.satisfaction + output * NEED_FILL_RATE * 0.5)

    # Consumption pass: draw basis/solvent resources from stockpile → fill nourishment/hydration
    # Build resource_type → "basis" | "solvent" map (collectible_resource biochem_tags take priority)
    _biochem_map: dict[str, str] = dict(_RESOURCE_BIOCHEM)
    for _cr in pop_loc.collectible_resources:
        if _cr.biochem_tags:
            if any(t.startswith("basis:") for t in _cr.biochem_tags):
                _biochem_map[_cr.resource_type] = "basis"
            elif any(t.startswith("solvent:") for t in _cr.biochem_tags):
                _biochem_map[_cr.resource_type] = "solvent"

    nourishment = needs_by_name.get("nourishment")
    hydration    = needs_by_name.get("hydration")

    _pop_scale = 10 ** pop.size_fractional

    # Collect resource types reserved for active supply_run/resupply deliveries.
    # These are never consumed from cargo — they are goods in transit, not provisions.
    _reserved_cargo: set[str] = set()
    _factions_dict_c = factions if isinstance(factions, dict) else {}
    _pop_id_str_c = str(pop.id)
    for _d in pop.active_directives:
        if _d.directive_type in ("supply_run", "resupply"):
            _m = _d.cargo_manifest or {}
            if not _m and _d.cargo_resource_type:
                _m = {_d.cargo_resource_type: float(_d.cargo_quantity)}
            _reserved_cargo.update(_m.keys())
    for _fid_c in pop.faction_ids:
        _f_c = _factions_dict_c.get(str(_fid_c))
        if _f_c:
            for _d in _f_c.active_directives:
                if _d.directive_type in ("supply_run", "resupply"):
                    _pop_id_str_c_check = _pop_id_str_c
                    if _d.territory_pop_ids and _pop_id_str_c_check not in {str(t) for t in _d.territory_pop_ids}:
                        continue
                    _m = _d.cargo_manifest or {}
                    if not _m and _d.cargo_resource_type:
                        _m = {_d.cargo_resource_type: float(_d.cargo_quantity)}
                    _reserved_cargo.update(_m.keys())

    # Source 1: Pop's own CargoStockpile (in-hand resources — consumed before shared stockpiles)
    for _rt, _qty in list(ps.cargo.quantities.items()):
        if _qty <= 0 or _rt in _reserved_cargo:
            continue
        _cat = _biochem_map.get(_rt)
        if _cat == "basis" and nourishment and nourishment.satisfaction < 1.0:
            _consumed = min(_qty, NOURISHMENT_CONSUME_RATE * _pop_scale)
            ps.cargo.quantities[_rt] -= _consumed
            nourishment.satisfaction = min(1.0, nourishment.satisfaction + NOURISHMENT_FILL_RATE)
        elif _cat == "solvent" and hydration and hydration.satisfaction < 1.0:
            _consumed = min(_qty, HYDRATION_CONSUME_RATE * _pop_scale)
            ps.cargo.quantities[_rt] -= _consumed
            hydration.satisfaction = min(1.0, hydration.satisfaction + HYDRATION_FILL_RATE)

    # Source 2: accessible ResourceStockpiles at location (spillover from cargo if still hungry)
    _accessible = [s for s in pop_loc.stockpiles if can_access_stockpile(pop, s)]
    for _s in _accessible:
        for resource_type, quantity in list(_s.quantities.items()):
            if quantity <= 0:
                continue
            category = _biochem_map.get(resource_type)
            if category == "basis" and nourishment and nourishment.satisfaction < 1.0:
                consumed = min(quantity, NOURISHMENT_CONSUME_RATE * _pop_scale)
                _s.quantities[resource_type] -= consumed
                nourishment.satisfaction = min(1.0, nourishment.satisfaction + NOURISHMENT_FILL_RATE)
            elif category == "solvent" and hydration and hydration.satisfaction < 1.0:
                consumed = min(quantity, HYDRATION_CONSUME_RATE * _pop_scale)
                _s.quantities[resource_type] -= consumed
                hydration.satisfaction = min(1.0, hydration.satisfaction + HYDRATION_FILL_RATE)

    # Narrative: unmet nourishment or hydration
    if nourishment and nourishment.is_pressing and not any(
        _biochem_map.get(rt) == "basis" and q > 0
        for _s in _accessible
        for rt, q in _s.quantities.items()
    ):
        from core.universe_core import pop_label as _pop_label
        narratives.append(
            f"§pop§{pop.id}§{_pop_label(pop)}§ has no food — nourishment unmet."
        )
    if hydration and hydration.is_pressing and not any(
        _biochem_map.get(rt) == "solvent" and q > 0
        for _s in _accessible
        for rt, q in _s.quantities.items()
    ):
        from core.universe_core import pop_label as _pop_label
        narratives.append(
            f"§pop§{pop.id}§{_pop_label(pop)}§ has no water — hydration unmet."
        )

    # Directive fulfillment: purpose satisfaction for hold_position and future types
    _all_directives = list(pop.active_directives)
    for _fid in pop.faction_ids:
        _faction = factions.get(str(_fid)) if factions else None
        if _faction:
            _all_directives.extend(_faction.active_directives)
    if _all_directives:
        _purpose_need = needs_by_name.get("purpose")
        if _purpose_need is not None:
            for _d in _all_directives:
                _inc = directive_purpose_increment(_d, actor_location_id=pop.current_location, pop=pop, pops=_pops_dict)
                if _inc > 0.0:
                    _purpose_need.satisfaction = min(1.0, _purpose_need.satisfaction + _inc)
                    break  # one directive fills purpose per tick

    return narratives
