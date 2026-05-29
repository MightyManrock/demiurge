from __future__ import annotations
from typing import TYPE_CHECKING

from core.universe_core import PopLocation
from core.action_core import StateMutation, MutationType
from logic.sim_utils import resolve_world_id_for

if TYPE_CHECKING:
    from logic.tick_logic import SimulationState, TickConfig

# Essence generation: per-CivilizationScale multipliers applied to Pop dominant_beliefs.
# Covers all scale tiers including pre-sapient. The multiplier modulates output only when
# belief-match > 0 (formula: essence_pop_weight * (1 + (scale_mult - 1) * match)).
# At match=0 all tiers produce the same baseline; at match=1 the range is 0.80–1.45.
_CIV_SCALE_ESSENCE_MULT: dict[str, float] = {
    "non_sentient":   0.80,
    "pre_sapient":    1.00,
    "nascent":        1.05,
    "tribal":         1.10,
    "city_state":     1.15,
    "regional":       1.20,
    "continental":    1.25,
    "planetary":      1.30,
    "interplanetary": 1.35,
    "interstellar":   1.40,
    "intergalactic":  1.45,
}


def belief_match(pop_beliefs: dict[str, float], civ_established: dict[str, float]) -> float:
    """
    Weighted overlap: fraction of the civilization's established belief expression
    that this Pop's beliefs cover. Returns 0.0–1.0.
    Used to scale the civ scope bonus on Pop Essence contribution.
    """
    if not civ_established:
        return 1.0
    numerator = sum(
        min(pop_beliefs.get(tag, 0.0), strength)
        for tag, strength in civ_established.items()
    )
    denominator = sum(civ_established.values())
    return numerator / denominator if denominator > 0.0 else 0.0


def process_essence_generation(
    state: "SimulationState",
    cfg: "TickConfig",
) -> tuple[list[StateMutation], dict[str, float]]:
    """
    Compute per-domain world pools → universe pool → claiming fractions.
    Adds Demiurge's share to essence.actual (no apparent/concealment impact).
    Accumulates each Luminary's share into state.luminary_production_this_eval.
    Returns (ESSENCE_CHANGE mutations, per-domain claim amounts).

    Belief contributions come from Pop.dominant_beliefs, scaled by a scope
    bonus proportional to how well the Pop's beliefs match the civilization's
    established_beliefs (weighted overlap).
    """
    universe_pool: dict[str, float] = {}

    # Build index: world_id → parent-world for PopLocations.
    pop_loc_to_world: dict[str, str] = {}
    for wid, world in state.worlds.items():
        for cid in world.child_ids:
            loc = state.locations.get(str(cid))
            if loc and isinstance(loc, PopLocation):
                pop_loc_to_world[str(cid)] = wid

    # Build index: world_id → list of mortals currently there
    mortals_by_world: dict[str, list] = {}
    for mortal in state.mortals.values():
        if mortal.status == "active":
            wid = resolve_world_id_for(state, mortal.current_location)
            if wid is not None:
                mortals_by_world.setdefault(wid, []).append(mortal)

    # World location weight: distribute each world's domain_expression contribution
    # evenly rather than per-Pop (location is an inherent property of the world).
    for wid, world in state.worlds.items():
        for tag, strength in world.domain_expression.items():
            amount = strength * cfg.essence_location_weight
            if amount > 0.0:
                universe_pool[tag] = universe_pool.get(tag, 0.0) + amount

    for loc in state.locations.values():
        if not isinstance(loc, PopLocation):
            continue
        for tag, strength in loc.domain_expression.items():
            amount = strength * cfg.essence_pop_location_weight
            if amount > 0.0:
                universe_pool[tag] = universe_pool.get(tag, 0.0) + amount

    # Pre-compute per-civ total Pop size so splitting a civ into multiple Pops
    # doesn't inflate its total essence output (contributions are size-weighted).
    civ_total_size: dict[str, float] = {}
    for pop in state.pops.values():
        if pop.civilization_id:
            cid = str(pop.civilization_id)
            civ_total_size[cid] = civ_total_size.get(cid, 0.0) + pop.size_fractional

    # Pop contributions: all Pops use the same formula; scale_mult from
    # _CIV_SCALE_ESSENCE_MULT covers every tier including non_sentient/pre_sapient.
    for pop in state.pops.values():
        if not pop.dominant_beliefs:
            continue
        civ = state.civilizations.get(str(pop.civilization_id)) if pop.civilization_id else None
        cid = str(pop.civilization_id) if pop.civilization_id else None

        if civ is not None:
            scale_key = civ.scale.value if hasattr(civ.scale, "value") else str(civ.scale)
            scale_mult = _CIV_SCALE_ESSENCE_MULT.get(scale_key, 1.0)
            match = belief_match(pop.dominant_beliefs, civ.established_beliefs)
            total_sz = civ_total_size.get(cid, pop.size_fractional)
            size_weight = pop.size_fractional / total_sz if total_sz > 0.0 else 1.0
        else:
            scale_mult = _CIV_SCALE_ESSENCE_MULT["pre_sapient"]
            match = 0.0
            size_weight = 1.0

        for tag, strength in pop.dominant_beliefs.items():
            amount = strength * size_weight * cfg.essence_pop_weight * (1.0 + (scale_mult - 1.0) * match)
            if amount > 0.0:
                universe_pool[tag] = universe_pool.get(tag, 0.0) + amount

    # Mortal contributions
    for mortal in state.mortals.values():
        if mortal.status != "active":
            continue
        for tag, strength in mortal.belief_tags.items():
            amount = strength * cfg.essence_mortal_weight
            if amount > 0.0:
                universe_pool[tag] = universe_pool.get(tag, 0.0) + amount

    if not universe_pool:
        return [], {}

    luminaries = list(state.luminaries.values())
    demiurge_affiliated = set(state.demiurge.affiliated_domains)
    tracked = set(state.demiurge.tracked_essence_domains)
    EXP = cfg.essence_claiming_exponent

    mutations: list[StateMutation] = []
    demiurge_total_claim = 0.0
    domain_claim_breakdown: dict[str, float] = {}

    for tag, pool in universe_pool.items():
        if pool <= 0.0:
            continue

        lum_total_aff = min(
            0.9, sum(lum.domains.get(tag, 0.0) for lum in luminaries)
        )

        if lum_total_aff == 0.0:
            # Uncontested domain — Demiurge claim capped by puissance (floor 0.25, ceil 0.50).
            if tag in demiurge_affiliated:
                uncontested_fraction = min(0.50, max(0.25, state.demiurge.puissance))
                claim = pool * uncontested_fraction
                demiurge_total_claim += claim
                domain_claim_breakdown[tag] = domain_claim_breakdown.get(tag, 0.0) + claim
                if tag in tracked:
                    state.domain_essence_claimed[tag] = (
                        state.domain_essence_claimed.get(tag, 0.0) + claim
                    )
            # else sinks to Underreal
            continue

        lum_fraction = lum_total_aff ** EXP
        dem_fraction = 1.0 - lum_fraction

        dem_claim = pool * dem_fraction if tag in demiurge_affiliated else 0.0

        net_pool = pool - dem_claim
        for lum in luminaries:
            lum_aff = min(0.8, lum.domains.get(tag, 0.0))
            if lum_aff <= 0.0:
                continue
            lid = str(lum.id)
            state.luminary_production_this_eval[lid] = (
                state.luminary_production_this_eval.get(lid, 0.0) + lum_aff * net_pool
            )
        demiurge_total_claim += dem_claim
        if dem_claim > 0.0:
            domain_claim_breakdown[tag] = domain_claim_breakdown.get(tag, 0.0) + dem_claim
        if tag in tracked and dem_claim > 0.0:
            state.domain_essence_claimed[tag] = (
                state.domain_essence_claimed.get(tag, 0.0) + dem_claim
            )

    if demiurge_total_claim > 0.001:
        mutations.append(StateMutation(
            mutation_type=MutationType.ESSENCE_CHANGE,
            target_id=state.demiurge.id,
            field="actual",
            delta=demiurge_total_claim,
            note=f"Domain-based Essence claim (+{demiurge_total_claim:.3f})",
        ))

    return mutations, domain_claim_breakdown
