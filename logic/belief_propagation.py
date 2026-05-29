from __future__ import annotations
from typing import TYPE_CHECKING

from core.universe_core import PopLocation
from core.action_core import StateMutation, MutationType

if TYPE_CHECKING:
    from logic.tick_logic import SimulationState, TickConfig

# ─────────────────────────────────────────
# BELIEF SYSTEM CONSTANTS
# ─────────────────────────────────────────

BELIEF_FLOOR = 0.02

CULTURE_FLOOR = 0.01
# Minimum durable strength for culture_tags. Lower than BELIEF_FLOOR (0.02)
# because culture-tag riders propagate at smaller per-tick magnitudes than
# Domain-belief shifts (Imago `culture:*` mechanics top out at ~0.20 even at
# T1, vs. ~0.35 for `domain:*`). The lower floor lets repeated whispers'
# fingerprints accumulate visibly on a Pop's culture even when a single
# whisper's per-tick contribution would have been pruned at BELIEF_FLOOR.
# Belief/domain-expression entries below this strength are
# silently pruned each passive phase. Keeps dicts clean of

# ─────────────────────────────────────────
# POP CONTACT RANK TABLES
# Used by pop_contact_resistance() for cross-stratum
# and cross-scale resistance calculations.
# ─────────────────────────────────────────

_SOCIAL_CLASS_RANK: dict[str, int] = {
    "wild":       -2,   # No social structure at all (pre-sapient pods, true wilderness).
    "feral":      -1,   # Partially or recently de-civilized — outside class but not pre-social.
    "underclass":  0, "common": 1, "artisan": 2, "trader": 3,
    "warrior":     4, "scholar": 5, "elite":   6,
}

_CIV_SCALE_CONTACT_RANK: dict[str, int] = {
    "non_sentient": -2,  # Reserved for future non-sentient Pops.
    "pre_sapient":  -1,  # Pop with no civilization_id (wild population).
    "nascent":       0, "tribal":  1, "city_state":     2, "regional":     3,
    "continental":   4, "planetary":     5, "interplanetary": 6,
    "interstellar":  7, "intergalactic": 8,
}

# Flat susceptibility modifier applied after all other resistance factors.
# Negative = more open to outside influence; positive = more closed.
_STRATUM_SUSCEPTIBILITY: dict[str, float] = {
    "trader": -0.12,
    "elite":    -0.06,
    "warrior":  +0.06,
    "scholar":  +0.12,
}

_SCALE_CONFORMITY: dict[str, float] = {
    "nascent": 0.2, "tribal": 0.4, "city_state": 0.6,
    "regional": 0.8, "continental": 1.0, "planetary": 1.2,
    "interplanetary": 1.4, "interstellar": 1.6, "intergalactic": 2.0,
}


def belief_inertia(current: float, delta: float) -> float:
    """
    Returns a [0.0, 1.0] multiplier that slows belief/culture changes at extremes.

    High zone  (current > 0.7, pushing up):   1.0 → ~0.40 at cap.
    High zone  (current > 0.7, pushing down):  1.0 → ~0.65 at cap  (entrenched but not immovable).
    Low zone   (current < 0.2, pushing up):    0.65 → 1.0  (unfamiliar ideas face friction).
    Floor zone (current ≤ 0.1, pushing down):  0.75 → 1.0  (tiny remnants cling).
    Mid range  (0.2–0.7): multiplier = 1.0.
    """
    if delta > 0:
        if current >= 0.7:
            # Linear from 1.0 at 0.7 down to 0.40 at 0.9+
            t = min(1.0, (current - 0.7) / 0.2)
            return 1.0 - t * 0.60
        if current < 0.2:
            # Linear from 0.65 at 0.0 up to 1.0 at 0.2
            return 0.65 + (current / 0.2) * 0.35
    else:  # delta < 0 (downward pressure)
        if current >= 0.7:
            t = min(1.0, (current - 0.7) / 0.2)
            return 1.0 - t * 0.35
        if current <= 0.1:
            # Linear from 0.75 at 0.0 up to 1.0 at 0.1
            return 0.75 + (current / 0.1) * 0.25
    return 1.0


def location_distance_from_core(state: SimulationState, loc_id) -> int:
    """Return the PopLocation's `distance_from_core` for `loc_id`, or 0 for any
    other location type (world surface, system, galaxy, unknown)."""
    if loc_id is None:
        return 0
    loc = state.locations.get(str(loc_id))
    if isinstance(loc, PopLocation):
        return int(getattr(loc, "distance_from_core", 0) or 0)
    return 0


def pop_distance_factor(state: SimulationState, src_loc_id, tgt_loc_id) -> float:
    """Symmetric distance-from-core penalty multiplier between two PopLocations
    on the same world. Compounds `0.7` per step of `|src.distance - tgt.distance|`.
    Same PopLocation → 1.0; surface ↔ orbital (d2) → 0.49; etc."""
    delta = abs(
        location_distance_from_core(state, src_loc_id)
        - location_distance_from_core(state, tgt_loc_id)
    )
    return 0.7 ** delta


def pops_on_world(world_id: str, state: SimulationState) -> list:
    """Return all Pops whose current_location is a PopLocation whose parent
    is `world_id`. Authoritative source is `pop.current_location` (not
    `PopLocation.pop_ids` or any home reference), so a Pop's presence on a
    world is decided solely by where it currently is."""
    wid = str(world_id)
    pops: list = []
    for pop in state.pops.values():
        ploc = state.locations.get(str(pop.current_location)) if pop.current_location else None
        if not isinstance(ploc, PopLocation):
            continue
        if str(ploc.parent_id) == wid:
            pops.append(pop)
    return pops


def pop_contact_resistance(
    target_pop,
    src_civ_id: str | None,
    src_species_id: str | None,
    src_class: str | None,
    state: SimulationState,
    cfg: TickConfig,
    src_size: float = 1.0,
) -> float:
    """
    Returns a resistance multiplier in [0.0, 1.0] representing how much
    cross-boundary friction slows belief drift from a source Pop/mortal
    onto target_pop.  Same-civ Pops return 1.0 (no reduction).
    """
    r = 1.0

    # Cross-civ resistance
    target_civ_id = str(target_pop.civilization_id) if target_pop.civilization_id else None
    if target_civ_id != src_civ_id:
        r *= cfg.cross_civ_contact_factor
        # Scale-gap penalty: civilizations have ranks; wild populations
        # (no civ_id) are treated as one step below `nascent`. This makes
        # wild→civ drift face the gap penalty too, since the conceptual
        # distance from a pre-sapient pod to a starfaring empire is at
        # least as large as the distance between any two civ scales.
        def _scale_rank_for(civ_id: str | None) -> int:
            if not civ_id:
                return _CIV_SCALE_CONTACT_RANK["pre_sapient"]
            civ = state.civilizations.get(civ_id)
            if civ is None:
                return _CIV_SCALE_CONTACT_RANK["pre_sapient"]
            scale = civ.scale.value if hasattr(civ.scale, "value") else str(civ.scale)
            return _CIV_SCALE_CONTACT_RANK.get(scale, 0)
        src_rank = _scale_rank_for(src_civ_id)
        tgt_rank = _scale_rank_for(target_civ_id)
        scale_gap = max(0, tgt_rank - src_rank)
        r *= max(0.05, 1.0 - scale_gap * cfg.cross_civ_scale_penalty)

    # Cross-species resistance
    target_species_id = str(target_pop.species_id) if target_pop.species_id else None
    if src_species_id and target_species_id and target_species_id != src_species_id:
        r *= cfg.cross_species_contact_factor

    # Cross-stratum resistance — wild populations (no social_class) are
    # assigned the `wild` rank, one step below `underclass`, so a wild Pop
    # talking to any actual stratum gets a distance-based penalty.
    tgt_class_str = target_pop.social_class.value if hasattr(target_pop.social_class, "value") else str(target_pop.social_class or "")
    src_rank = _SOCIAL_CLASS_RANK.get(src_class or "wild", _SOCIAL_CLASS_RANK["wild"])
    tgt_rank = _SOCIAL_CLASS_RANK.get(tgt_class_str or "wild", _SOCIAL_CLASS_RANK["wild"])
    stratum_distance = abs(tgt_rank - src_rank)
    if stratum_distance > 0:
        r *= cfg.cross_stratum_contact_factor ** stratum_distance

    # NOTE: `values:*` stubbornness used to be applied here, but it's
    # really about how hard values:* tags themselves are to change — not
    # about a Pop's general resistance to ideas. It now lives in the
    # POP_CULTURE_SHIFT / CIV_ESTABLISHED_CULTURE_SHIFT apply handlers
    # (which is where culture-tag values actually mutate).

    # Size ratio: a smaller source Pop has proportionally less sway over a larger target
    tgt_size = max(0.001, target_pop.size_fractional)
    r *= min(1.0, src_size / tgt_size)

    # Stratum susceptibility: applied last as a flat modifier to total resistance
    susceptibility = _STRATUM_SUSCEPTIBILITY.get(tgt_class_str, 0.0)
    r *= (1.0 + susceptibility)

    return max(0.0, min(1.0, r))


def process_pop_contact(
    state: SimulationState,
    cfg: TickConfig,
) -> list[StateMutation]:
    """
    Passive belief drift between all co-located Pops.
    For each world, iterates ordered pairs (a→b) and emits POP_BELIEF_SHIFT
    mutations scaled by pop_contact_resistance(). Same-civ pairs are included;
    the resistance function applies cross-civ and cross-stratum factors as appropriate.
    """
    mutations: list[StateMutation] = []
    for world_id in state.worlds:
        world_pops = pops_on_world(world_id, state)
        if len(world_pops) < 2:
            continue
        for i, pop_a in enumerate(world_pops):
            for pop_b in world_pops:
                if pop_a is pop_b:
                    continue
                src_civ_id = str(pop_a.civilization_id) if pop_a.civilization_id else None
                src_species_id = str(pop_a.species_id) if pop_a.species_id else None
                src_class = (pop_a.social_class.value if hasattr(pop_a.social_class, "value") else str(pop_a.social_class or "")) or None
                resistance = pop_contact_resistance(
                    pop_b, src_civ_id, src_species_id, src_class, state, cfg,
                    src_size=pop_a.size_fractional,
                )
                # PopLocation distance penalty: bridges across orbital/abyssal
                # PopLocations still contact, just at diminished strength.
                dist_factor = pop_distance_factor(
                    state, pop_a.current_location, pop_b.current_location,
                )
                for tag, a_strength in pop_a.dominant_beliefs.items():
                    if a_strength <= BELIEF_FLOOR:
                        continue
                    b_strength = pop_b.dominant_beliefs.get(tag, 0.0)
                    raw_delta = (a_strength - b_strength) * cfg.pop_contact_base_rate
                    delta = raw_delta * resistance * dist_factor
                    if abs(delta) > 1e-5:
                        mutations.append(StateMutation(
                            mutation_type=MutationType.POP_BELIEF_SHIFT,
                            target_id=pop_b.id,
                            field=tag,
                            delta=delta,
                            note=f"Pop contact drift ({tag})",
                        ))
    return mutations


def recompute_civ_dominant_beliefs(state: SimulationState, cfg: TickConfig) -> None:
    """
    Overwrite each Civilization.dominant_beliefs with the size-fractional-weighted
    average of its constituent Pop beliefs. Prunes entries below BELIEF_FLOOR.
    Pops at non-core locations (not in civ.core_locs) are weighted down by
    cfg.peripheral_pop_belief_weight. Called once per tick after Phase 2.5.
    """

    # Build PopLocation → parent world index
    pop_loc_to_world: dict[str, str] = {}
    for wid, world in state.worlds.items():
        for cid in world.child_ids:
            loc = state.locations.get(str(cid))
            if loc is not None and hasattr(loc, "pop_ids"):
                pop_loc_to_world[str(cid)] = wid

    for civ in state.civilizations.values():
        if not civ.pop_ids:
            continue

        core_loc_strs = {str(loc_id) for loc_id in civ.core_locs}

        weighted: dict[str, float] = {}
        total_weight = 0.0

        for pid in civ.pop_ids:
            pop = state.pops.get(str(pid))
            if pop is None:
                continue
            world_id = pop_loc_to_world.get(str(pop.current_location), "")
            is_core = (not core_loc_strs) or (world_id in core_loc_strs)
            base_w = max(0.001, pop.size_fractional)
            w = base_w if is_core else base_w * cfg.peripheral_pop_belief_weight
            total_weight += w
            for tag, strength in pop.dominant_beliefs.items():
                weighted[tag] = weighted.get(tag, 0.0) + strength * w

        if total_weight == 0.0:
            continue

        new_beliefs = {
            tag: min(1.0, val / total_weight)
            for tag, val in weighted.items()
            if val / total_weight > BELIEF_FLOOR
        }
        civ.dominant_beliefs = new_beliefs


def recompute_civ_culture_tags(state: SimulationState, cfg: TickConfig) -> None:
    """
    Overwrite each Civilization.culture_tags with the size-fractional-weighted
    average of its constituent Pop culture_tags. Pops at non-core locations are
    weighted down by cfg.peripheral_pop_culture_weight.
    """

    pop_loc_to_world: dict[str, str] = {}
    for wid, world in state.worlds.items():
        for cid in world.child_ids:
            loc = state.locations.get(str(cid))
            if loc is not None and hasattr(loc, "pop_ids"):
                pop_loc_to_world[str(cid)] = wid

    for civ in state.civilizations.values():
        if not civ.pop_ids:
            continue

        core_loc_strs = {str(loc_id) for loc_id in civ.core_locs}

        weighted: dict[str, float] = {}
        total_weight = 0.0

        for pid in civ.pop_ids:
            pop = state.pops.get(str(pid))
            if pop is None:
                continue
            world_id = pop_loc_to_world.get(str(pop.current_location), "")
            is_core = (not core_loc_strs) or (world_id in core_loc_strs)
            base_w = max(0.001, pop.size_fractional)
            w = base_w if is_core else base_w * cfg.peripheral_pop_culture_weight
            total_weight += w
            for tag, strength in pop.culture_tags.items():
                weighted[tag] = weighted.get(tag, 0.0) + strength * w

        if total_weight == 0.0:
            continue

        civ.culture_tags = {
            tag: (max(-1.0, min(1.0, val / total_weight))
                  if tag.startswith(("values:", "practice:"))
                  else min(1.0, val / total_weight))
            for tag, val in weighted.items()
            if abs(val / total_weight) > CULTURE_FLOOR
        }


def civ_conformity_pressure(state: SimulationState, cfg: TickConfig) -> list[StateMutation]:
    """
    For each Pop belonging to a civilization, emit belief and culture mutations
    that nudge Pop values toward civ.established_beliefs / established_culture_tags.
    """
    mutations: list[StateMutation] = []
    for pop in state.pops.values():
        if not pop.civilization_id:
            continue
        civ = state.civilizations.get(str(pop.civilization_id))
        if civ is None or not civ.established_beliefs:
            continue
        scale_key = civ.scale.value if hasattr(civ.scale, "value") else str(civ.scale)
        conformity_rate = (
            cfg.pop_conformity_base
            * _SCALE_CONFORMITY.get(scale_key, 1.0)
            * civ.health.cohesion
        )
        # Actively preached Pops (goal targets) resist institutional pull at half rate
        if pop.preaching_imago_id is not None:
            conformity_rate *= 0.5
        # Stratum susceptibility: priests and warriors resist institutional pull;
        # merchants are more responsive to it
        pop_class = pop.social_class.value if hasattr(pop.social_class, "value") else str(pop.social_class or "")
        susceptibility = _STRATUM_SUSCEPTIBILITY.get(pop_class, 0.0)
        conformity_rate *= max(0.1, 1.0 + susceptibility)
        for tag in set(civ.established_beliefs) | set(pop.dominant_beliefs):
            est_val = civ.established_beliefs.get(tag, 0.0)
            pop_val = pop.dominant_beliefs.get(tag, 0.0)
            delta = (est_val - pop_val) * conformity_rate
            if abs(delta) > 0.0001:
                mutations.append(StateMutation(
                    mutation_type=MutationType.POP_BELIEF_SHIFT,
                    target_id=pop.id,
                    field=tag,
                    new_value=tag,
                    delta=delta,
                    note=f"{civ.name} conformity pressure on Pop ({tag})",
                ))

        # Culture conformity: nudge Pop culture_tags toward civ.established_culture_tags
        if civ.established_culture_tags:
            for tag in set(civ.established_culture_tags) | set(pop.culture_tags):
                est_val = civ.established_culture_tags.get(tag, 0.0)
                pop_val = pop.culture_tags.get(tag, 0.0)
                delta = (est_val - pop_val) * conformity_rate
                if abs(delta) > 0.0001:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.POP_CULTURE_SHIFT,
                        target_id=pop.id,
                        field=tag,
                        delta=delta,
                        note=f"{civ.name} culture conformity on Pop ({tag})",
                    ))
    return mutations
