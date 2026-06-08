"""Tests for pop action spillover to co-located pops.

Spillover tiers (civic actions only — fortify, build, commune, revel, enact_rituals):
  linked + co-factional  → max(link_factor, 0.75)
  co-factional only      → 0.75
  linked only            → link_factor
  neither / one faction  → 0.5
  cross-factional        → 0.0
"""
import pytest
from uuid import uuid4, UUID

from core.universe_core import Pop, PopLocation, SocialStratum
from core.agent_core import PopAgentState, PopNeed
from logic.pop_agent_logic import resolve_pop_actions, _pop_spillover_factor


LOC_ID = uuid4()

FAC_A = uuid4()
FAC_B = uuid4()


def _need(name: str, satisfaction: float = 0.5) -> PopNeed:
    return PopNeed(name=name, satisfaction=satisfaction, decay_rate=0.01,
                   pressing_threshold=0.5, urgent_threshold=0.2)


def _pop_state(*need_names: str) -> PopAgentState:
    ps = PopAgentState()
    ps.needs = [_need(n) for n in need_names]
    return ps


def _pop(faction_ids=(), linked: dict | None = None, pop_state=None) -> Pop:
    return Pop(
        current_location=LOC_ID,
        social_class=SocialStratum.COMMON,
        faction_ids=list(faction_ids),
        linked_pop_ids=linked or {},
        pop_state=pop_state,
    )


def _pop_loc() -> PopLocation:
    return PopLocation(
        name="Test",
        location_type="city",
        collectible_resources=[],
    )


# ── _pop_spillover_factor ────────────────────────────────────────────────────

def test_spillover_no_faction_no_link():
    """Unaffiliated co-located pops → 0.5."""
    actor = _pop()
    neighbor = _pop()
    assert _pop_spillover_factor(actor, neighbor, {}) == pytest.approx(0.5)


def test_spillover_cross_factional():
    """Both in factions with no overlap → 0.0."""
    actor = _pop(faction_ids=[FAC_A])
    neighbor = _pop(faction_ids=[FAC_B])
    assert _pop_spillover_factor(actor, neighbor, {}) == pytest.approx(0.0)


def test_spillover_co_factional_not_linked():
    """Share a faction, no link → exactly 0.75."""
    actor = _pop(faction_ids=[FAC_A])
    neighbor = _pop(faction_ids=[FAC_A])
    assert _pop_spillover_factor(actor, neighbor, {}) == pytest.approx(0.75)


def test_spillover_linked_not_co_factional():
    """Linked but no shared faction → link_factor (not 0.75)."""
    neighbor = _pop()
    actor = _pop(linked={str(neighbor.id): 0.4})
    factor = _pop_spillover_factor(actor, neighbor, {})
    # link_factor = compute_link_factor with base=0.4, no stratum/occupation/cosine bonus
    # should be ~0.4, definitely < 0.75
    assert 0.0 < factor < 0.75


def test_spillover_linked_and_co_factional_weak_link():
    """Linked (weak) + co-factional → max(link_factor, 0.75) = 0.75."""
    neighbor = _pop(faction_ids=[FAC_A])
    actor = _pop(faction_ids=[FAC_A], linked={str(neighbor.id): 0.2})
    factor = _pop_spillover_factor(actor, neighbor, {})
    assert factor == pytest.approx(0.75)


def test_spillover_linked_and_co_factional_strong_link():
    """Linked (strong) + co-factional → max(link_factor, 0.75) = link_factor > 0.75."""
    neighbor = _pop(faction_ids=[FAC_A])
    actor = _pop(faction_ids=[FAC_A], linked={str(neighbor.id): 0.9})
    factor = _pop_spillover_factor(actor, neighbor, {})
    assert factor > 0.75


def test_spillover_one_faction_other_none():
    """Actor in a faction, neighbor has none → not cross-factional → 0.5."""
    actor = _pop(faction_ids=[FAC_A])
    neighbor = _pop(faction_ids=[])
    assert _pop_spillover_factor(actor, neighbor, {}) == pytest.approx(0.5)


# ── resolve_pop_actions spillover ────────────────────────────────────────────

def _run_fortify(actor, neighbor, factions=None):
    loc = _pop_loc()
    resolve_pop_actions(
        actor, loc,
        priorities={"fortify": 1.0},
        n_slots=1,
        factions=factions or {},
        colocated_pops=[neighbor],
    )


def test_fortify_spills_safety_to_neutral_neighbor():
    """fortify: unaffiliated neighbor receives ~0.5× the actor's safety gain."""
    actor = _pop(pop_state=_pop_state("safety"))
    neighbor = _pop(pop_state=_pop_state("safety"))
    before = neighbor.pop_state.needs[0].satisfaction

    _run_fortify(actor, neighbor)

    after = neighbor.pop_state.needs[0].satisfaction
    assert after > before


def test_fortify_no_spill_to_cross_factional():
    """fortify: rival-faction neighbor receives no spillover."""
    actor = _pop(faction_ids=[FAC_A], pop_state=_pop_state("safety"))
    neighbor = _pop(faction_ids=[FAC_B], pop_state=_pop_state("safety"))
    before = neighbor.pop_state.needs[0].satisfaction

    _run_fortify(actor, neighbor)

    assert neighbor.pop_state.needs[0].satisfaction == pytest.approx(before)


def test_commune_spills_cohesion():
    """commune: co-located neighbor's cohesion rises."""
    actor = _pop(pop_state=_pop_state("cohesion"))
    neighbor = _pop(pop_state=_pop_state("cohesion"))
    before = neighbor.pop_state.needs[0].satisfaction

    loc = _pop_loc()
    resolve_pop_actions(actor, loc, priorities={"commune": 1.0}, n_slots=1, factions={},
                        colocated_pops=[neighbor])

    assert neighbor.pop_state.needs[0].satisfaction > before


def test_forage_no_spillover():
    """forage is a survival action — it should NOT spill to neighbors."""
    actor = _pop(pop_state=_pop_state("nourishment"))
    # Give the actor something to forage (a food collectible on the loc)
    from core.agent_core import CollectibleResource
    loc = _pop_loc()
    loc.collectible_resources = [CollectibleResource(resource_type="food_flora", max_yield=5.0)]
    neighbor = _pop(pop_state=_pop_state("nourishment"))
    before = neighbor.pop_state.needs[0].satisfaction

    resolve_pop_actions(actor, loc, priorities={"forage": 1.0}, n_slots=1, factions={},
                        colocated_pops=[neighbor])

    assert neighbor.pop_state.needs[0].satisfaction == pytest.approx(before)


def test_spillover_scales_with_tier():
    """Co-factional neighbor gains more than unaffiliated neighbor from the same fortify."""
    actor = _pop(faction_ids=[FAC_A], pop_state=_pop_state("safety"))
    cofac_neighbor = _pop(faction_ids=[FAC_A], pop_state=_pop_state("safety"))
    plain_neighbor = _pop(pop_state=_pop_state("safety"))

    loc = _pop_loc()
    resolve_pop_actions(actor, loc, priorities={"fortify": 1.0}, n_slots=1, factions={},
                        colocated_pops=[cofac_neighbor, plain_neighbor])

    cofac_gain = cofac_neighbor.pop_state.needs[0].satisfaction - 0.5
    plain_gain = plain_neighbor.pop_state.needs[0].satisfaction - 0.5
    assert cofac_gain > plain_gain > 0.0


def test_no_colocated_pops_no_error():
    """resolve_pop_actions with empty colocated_pops runs without error."""
    actor = _pop(pop_state=_pop_state("safety"))
    loc = _pop_loc()
    resolve_pop_actions(actor, loc, priorities={"fortify": 1.0}, n_slots=1, factions={},
                        colocated_pops=[])
