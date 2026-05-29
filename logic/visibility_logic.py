from __future__ import annotations
from typing import TYPE_CHECKING
from uuid import UUID

from core.universe_core import PopLocation, MortalStatus
from core.action_core import StateMutation, MutationType
from logic.sim_utils import resolve_world_id_for
from logic.belief_propagation import pops_on_world

if TYPE_CHECKING:
    from logic.tick_logic import SimulationState, TickConfig

# ─────────────────────────────────────────
# VISIBILITY CONSTANTS
# ─────────────────────────────────────────

ENTITY_VISIBILITY_FLOOR = 0.005
# Below this, any entity (location, civilization, species, mortal) is out of the Window.

VISIBILITY_STALL_ON_CAP = 30        # ticks of stall granted when visibility reaches 1.0
VISIBILITY_STALL_SCENARIO_START = 360  # ticks of stall set during scenario-start migration

# Fraction of the passive rate applied to each Proxius on a policy-compliant world.
# Compliant worlds have ≤ proxii_policy.max_per_world active Proxii.
PROXIUS_COMPLIANCE_FACTOR = 0.3


def process_visibility_decay(state: "SimulationState", cfg: "TickConfig") -> list[StateMutation]:
    """
    Emit visibility decay mutations for all entity types and accumulate passive
    footprint/concealment/attention changes. Also handles Pop visibility drift and
    TravelLocation derived visibility.

    Some stall counters are decremented directly on the state objects (not via mutation
    queue) to match existing behavior.

    Returns a flat list of StateMutation for the caller to route into the passive result.
    """
    from core.universe_core import MortalRole  # local to avoid top-level cycle risk
    mutations: list[StateMutation] = []

    # ── Mortal visibility decay ────────────────────
    for mid, mortal in state.mortals.items():
        if mortal.status == MortalStatus.DECEASED:
            continue
        if mortal.visibility <= 0.0:
            continue
        if mortal.pinned and mortal.visibility_stall_remaining <= VISIBILITY_STALL_ON_CAP:
            continue
        if mortal.visibility_stall_remaining > 0:
            mortal.visibility_stall_remaining -= 1
            continue
        effective_rate = cfg.mortal_visibility_decay_rate * (1.0 - mortal.prominence)
        new_vis = max(0.0, mortal.visibility - effective_rate)
        if 0.0 < new_vis < ENTITY_VISIBILITY_FLOOR:
            new_vis = 0.0
        if mortal.visibility - new_vis > 0.0001:
            mutations.append(StateMutation(
                mutation_type=MutationType.MORTAL_VISIBILITY,
                target_id=UUID(mid),
                field="visibility",
                delta=-(mortal.visibility - new_vis),
                note=f"{mortal.name} visibility decay",
            ))

    # ── Location visibility decay ──────────────────
    for lid, loc in state.locations.items():
        if getattr(loc, "location_type", None) == "travel_location":
            continue
        if loc.visibility <= 0.0:
            continue
        loc_stall = getattr(loc, "visibility_stall_remaining", 0)
        if getattr(loc, "pinned", False) and loc_stall <= VISIBILITY_STALL_ON_CAP:
            continue
        if loc_stall > 0:
            loc.visibility_stall_remaining = loc_stall - 1
            continue
        new_vis = max(0.0, loc.visibility - cfg.location_visibility_decay_rate)
        if 0.0 < new_vis < ENTITY_VISIBILITY_FLOOR:
            new_vis = 0.0
        if loc.visibility - new_vis > 0.0001:
            mutations.append(StateMutation(
                mutation_type=MutationType.ENTITY_VISIBILITY,
                target_id=UUID(lid),
                field="visibility",
                delta=-(loc.visibility - new_vis),
                note=f"{loc.name} visibility decay",
            ))

    # ── TravelLocation visibility (derived from endpoints) ─
    for lid, loc in state.locations.items():
        if getattr(loc, "location_type", None) != "travel_location":
            continue
        legs = getattr(loc, "legs", {})
        if not legs:
            continue
        leg_keys = list(legs.keys())
        origin_loc = state.locations.get(leg_keys[0])
        dest_key = next((k for k, v in legs.items() if v == 0), None)
        dest_loc = state.locations.get(dest_key) if dest_key else None
        def _in_window(e) -> bool:
            return getattr(e, "pinned", False) or e.visibility > ENTITY_VISIBILITY_FLOOR
        if origin_loc is not None and dest_loc is not None and _in_window(origin_loc) and _in_window(dest_loc):
            loc.visibility = 1.0
        else:
            loc.visibility = 0.0

    # ── Civilization visibility decay ──────────────
    for cid, civ in state.civilizations.items():
        if civ.visibility <= 0.0:
            continue
        if civ.pinned and civ.visibility_stall_remaining <= VISIBILITY_STALL_ON_CAP:
            continue
        if civ.visibility_stall_remaining > 0:
            civ.visibility_stall_remaining -= 1
            continue
        new_vis = max(0.0, civ.visibility - cfg.civ_visibility_decay_rate)
        if 0.0 < new_vis < ENTITY_VISIBILITY_FLOOR:
            new_vis = 0.0
        if civ.visibility - new_vis > 0.0001:
            mutations.append(StateMutation(
                mutation_type=MutationType.ENTITY_VISIBILITY,
                target_id=UUID(cid),
                field="visibility",
                delta=-(civ.visibility - new_vis),
                note=f"{civ.name} visibility decay",
            ))

    # ── Species visibility decay ───────────────────
    for sid, sp in state.species.items():
        if sp.visibility <= 0.0:
            continue
        if sp.pinned and sp.visibility_stall_remaining <= VISIBILITY_STALL_ON_CAP:
            continue
        if sp.visibility_stall_remaining > 0:
            sp.visibility_stall_remaining -= 1
            continue
        new_vis = max(0.0, sp.visibility - cfg.species_visibility_decay_rate)
        if 0.0 < new_vis < ENTITY_VISIBILITY_FLOOR:
            new_vis = 0.0
        if sp.visibility - new_vis > 0.0001:
            mutations.append(StateMutation(
                mutation_type=MutationType.ENTITY_VISIBILITY,
                target_id=UUID(sid),
                field="visibility",
                delta=-(sp.visibility - new_vis),
                note=f"{sp.name} visibility decay",
            ))

    # ── Pop visibility drift ───────────────────────
    # Pop visibility converges toward min(civ.visibility, world.visibility).
    _pop_loc_to_world: dict[str, str] = {}
    for wid, world in state.worlds.items():
        for cid in world.child_ids:
            loc = state.locations.get(str(cid))
            if loc and isinstance(loc, PopLocation):
                _pop_loc_to_world[str(cid)] = wid

    for pid, pop in state.pops.items():
        if pop.visibility <= 0.0:
            continue
        if pop.pinned and pop.visibility_stall_remaining <= VISIBILITY_STALL_ON_CAP:
            continue
        if pop.visibility_stall_remaining > 0:
            pop.visibility_stall_remaining -= 1
            continue
        civ = state.civilizations.get(str(pop.civilization_id)) if pop.civilization_id else None
        civ_vis = civ.visibility if civ else 0.0
        wid = _pop_loc_to_world.get(str(pop.current_location), str(pop.current_location))
        world_obj = state.worlds.get(wid)
        world_vis = world_obj.visibility if world_obj else 0.0
        baseline = min(civ_vis, world_vis)
        delta = (baseline - pop.visibility) * cfg.pop_visibility_drift_rate
        if delta < 0:
            new_pop_vis = pop.visibility + delta
            if 0.0 < new_pop_vis < ENTITY_VISIBILITY_FLOOR:
                delta = -pop.visibility
        if abs(delta) > 0.0001:
            mutations.append(StateMutation(
                mutation_type=MutationType.POP_VISIBILITY,
                target_id=UUID(pid),
                field="visibility",
                delta=delta,
                note="Pop visibility drift",
            ))

    # ── Passive Proxius footprint accumulation ────────
    if cfg.proxius_passive_footprint_rate > 0.0:
        policy = state.universe.rules.proxii_policy
        proxii_by_world: dict[str, int] = {}
        for mortal in state.mortals.values():
            if (mortal.role == MortalRole.PROXIUS
                    and mortal.status == MortalStatus.ACTIVE):
                wid = resolve_world_id_for(state, mortal.current_location)
                if wid is None:
                    continue
                proxii_by_world[wid] = proxii_by_world.get(wid, 0) + 1

        total_passive_fp = 0.0
        for count in proxii_by_world.values():
            if policy.max_per_world is not None:
                compliant = min(count, policy.max_per_world)
                excess    = max(0, count - policy.max_per_world)
            else:
                compliant = count
                excess    = 0
            total_passive_fp += (
                compliant * cfg.proxius_passive_footprint_rate * PROXIUS_COMPLIANCE_FACTOR
                + excess  * cfg.proxius_passive_footprint_rate
            )

        if total_passive_fp > 0.001:
            n_active = sum(proxii_by_world.values())
            mutations.append(StateMutation(
                mutation_type=MutationType.FOOTPRINT_CHANGE,
                target_id=state.demiurge.id,
                field="proxius_activity",
                delta=total_passive_fp,
                note=f"Passive Proxius activity ({n_active} active)",
            ))

    # ── Footprint decay ────────────────────────────
    fp = state.demiurge.footprint
    for category, multiplier in cfg.footprint_decay_multipliers.items():
        current = getattr(fp, category)
        decay = cfg.footprint_decay_rate * multiplier
        new_val = max(0.0, current - decay)
        if abs(new_val - current) > 0.0001:
            mutations.append(StateMutation(
                mutation_type=MutationType.FOOTPRINT_CHANGE,
                target_id=state.demiurge.id,
                field=category,
                delta=-(current - new_val),
                note=f"Footprint decay: {category}",
            ))

    # World-level footprint decay
    for wid, world in state.worlds.items():
        for category, multiplier in cfg.footprint_decay_multipliers.items():
            current = getattr(world.local_footprint, category)
            decay = cfg.footprint_decay_rate * multiplier
            new_val = max(0.0, current - decay)
            if abs(new_val - current) > 0.0001:
                mutations.append(StateMutation(
                    mutation_type=MutationType.FOOTPRINT_CHANGE,
                    target_id=UUID(wid),
                    field=f"local_footprint.{category}",
                    delta=-(current - new_val),
                    note=f"World footprint decay: {category}",
                ))

    # ── Concealment degradation ────────────────────
    if state.essence.concealment_integrity > 0.0:
        quiet = state.ticks_without_essence_gain
        if quiet >= 6:
            effective_decay = 0.0
        elif quiet >= 3:
            effective_decay = cfg.concealment_decay_rate * 0.5
        else:
            effective_decay = cfg.concealment_decay_rate

        if effective_decay > 0.0:
            new_integrity = max(
                0.0,
                state.essence.concealment_integrity - effective_decay
            )
            mutations.append(StateMutation(
                mutation_type=MutationType.CONCEALMENT_CHANGE,
                target_id=state.demiurge.id,
                field="concealment_integrity",
                delta=-(state.essence.concealment_integrity - new_integrity),
                note="Passive concealment degradation",
            ))

    # ── Luminary attention decay ───────────────────
    for lid in state.luminaries:
        current_att = state.luminary_attention.get(lid, 0.2)
        new_att = max(0.0, current_att - cfg.attention_decay_rate)
        if abs(new_att - current_att) > 0.0001:
            mutations.append(StateMutation(
                mutation_type=MutationType.FOOTPRINT_CHANGE,
                target_id=UUID(lid),
                field="attention",
                delta=-(current_att - new_att),
                note="Luminary attention decay",
            ))

    return mutations


def emit_upward_visibility_splash(
    mutations: list,
    state: "SimulationState",
    boosted_pop_ids: set,
    boosted_mortal_ids: set,
) -> None:
    """Emit +0.003 visibility to all ancestor entities of boosted pops/mortals.

    Ancestors: civ, species, and each location up the parent chain
    (SignificantLocation → System → Galaxy). Deduplicated — each
    ancestor boosted at most once regardless of how many pops/mortals share it.
    """
    ancestor_ids: set = set()

    def _walk_loc_chain(loc_id_str: str) -> None:
        loc = state.locations.get(loc_id_str)
        while loc is not None and loc.parent_id is not None:
            ancestor_ids.add(loc.parent_id)
            loc = state.locations.get(str(loc.parent_id))

    for pid in boosted_pop_ids:
        pop = state.pops.get(pid)
        if not pop:
            continue
        if pop.civilization_id:
            ancestor_ids.add(pop.civilization_id)
        if pop.species_id:
            ancestor_ids.add(pop.species_id)
        _walk_loc_chain(str(pop.current_location))

    for mid in boosted_mortal_ids:
        mortal = state.mortals.get(mid)
        if not mortal:
            continue
        if mortal.civilization_id:
            ancestor_ids.add(mortal.civilization_id)
        if mortal.species_id:
            ancestor_ids.add(mortal.species_id)
        _walk_loc_chain(str(mortal.current_location))

    for uid in ancestor_ids:
        mutations.append(StateMutation(
            mutation_type=MutationType.ENTITY_VISIBILITY,
            target_id=uid,
            field="visibility",
            delta=0.003,
            note="Upward visibility splash",
        ))


def emit_omen_visibility_splash(
    mutations: list,
    state: "SimulationState",
    world_id: str,
) -> tuple[set, set]:
    """Boost visibility of above-floor pops and mortals on world_id.

    Attenuation: 0.6 / (distance_from_core + 1).
    Returns (boosted_pop_ids, boosted_mortal_ids) for upward splash.
    """
    boosted_pop_ids: set = set()
    boosted_mortal_ids: set = set()

    pop_locs = {
        lid: loc for lid, loc in state.locations.items()
        if isinstance(loc, PopLocation) and str(loc.parent_id) == world_id
    }

    for lid, ploc in pop_locs.items():
        boost = min(1.0, 0.6 / (ploc.distance_from_core + 1))
        for pop in state.pops.values():
            if str(pop.current_location) != lid:
                continue
            if pop.visibility <= ENTITY_VISIBILITY_FLOOR:
                continue
            mutations.append(StateMutation(
                mutation_type=MutationType.POP_VISIBILITY,
                target_id=pop.id,
                field="visibility",
                new_value=min(1.0, pop.visibility + boost),
                note="Omen visibility splash",
            ))
            boosted_pop_ids.add(str(pop.id))

    for mortal in state.mortals.values():
        if mortal.status != MortalStatus.ACTIVE:
            continue
        ploc_id = str(mortal.current_location) if mortal.current_location else None
        if ploc_id not in pop_locs:
            continue
        if mortal.visibility <= ENTITY_VISIBILITY_FLOOR:
            continue
        boost = min(1.0, 0.6 / (pop_locs[ploc_id].distance_from_core + 1))
        mutations.append(StateMutation(
            mutation_type=MutationType.MORTAL_VISIBILITY,
            target_id=mortal.id,
            field="visibility",
            new_value=min(1.0, mortal.visibility + boost),
            note="Omen visibility splash",
        ))
        boosted_mortal_ids.add(str(mortal.id))

    emit_upward_visibility_splash(mutations, state, boosted_pop_ids, boosted_mortal_ids)
    return boosted_pop_ids, boosted_mortal_ids


def emit_influence_visibility_splash(
    mutations: list,
    state: "SimulationState",
    mortal,
) -> tuple[set, set, set]:
    """Boost pop visibility from a Whisper / Shape Dream action.

    Own Pop receives +0.8; all other Pops on the world receive
    0.6 / (distance_from_core + 1). No floor guard — sub-floor Pops
    can be reached via the mortal vector (discovery by contact).

    Returns (boosted_pop_ids, boosted_mortal_ids, discovered_pop_ids).
    """
    boosted_pop_ids: set = set()
    boosted_mortal_ids: set = set()
    discovered_pop_ids: set = set()

    if not mortal:
        return boosted_pop_ids, boosted_mortal_ids, discovered_pop_ids

    world_id = resolve_world_id_for(state, mortal.current_location)
    if not world_id:
        return boosted_pop_ids, boosted_mortal_ids, discovered_pop_ids

    boosted_mortal_ids.add(str(mortal.id))
    own_pop_id = str(mortal.pop_id) if mortal.pop_id else None

    for pop in pops_on_world(world_id, state):
        pid = str(pop.id)
        ploc = state.locations.get(str(pop.current_location)) if pop.current_location else None
        if not isinstance(ploc, PopLocation):
            continue
        boost = 0.8 if pid == own_pop_id else min(1.0, 0.6 / (ploc.distance_from_core + 1))
        was_zero = pop.visibility == 0.0
        new_vis = min(1.0, pop.visibility + boost)
        mutations.append(StateMutation(
            mutation_type=MutationType.POP_VISIBILITY,
            target_id=pop.id,
            field="visibility",
            new_value=new_vis,
            note="Influence visibility splash",
        ))
        boosted_pop_ids.add(pid)
        if was_zero and new_vis >= ENTITY_VISIBILITY_FLOOR:
            discovered_pop_ids.add(pid)

    emit_upward_visibility_splash(mutations, state, boosted_pop_ids, boosted_mortal_ids)
    return boosted_pop_ids, boosted_mortal_ids, discovered_pop_ids
