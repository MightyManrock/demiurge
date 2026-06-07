"""Tests for opportunistic pre-travel collect and pending_travel_dest mechanic."""
import pytest
from unittest.mock import MagicMock
from core.agent_core import (
    MortalAgentState, MortalNeed, KnowledgeBase,
    RouteFact, LocationQualityFact, ResourceFact, Resource,
    CollectibleResource,
)
from logic.mortal_agent_logic import evaluate_mortal_action


NERAN = "neran-surface"
SETHIS = "sethis-surface"


def _pressing_need(name="purpose"):
    return MortalNeed(name=name, satisfaction=0.3, pressing_threshold=0.60,
                      urgent_threshold=0.25, decay_rate=0.03)


def _cs(with_sellable=True, with_cargo_space=True):
    cs = MortalAgentState(needs=[_pressing_need()])
    if with_sellable:
        quantity = 2.0 if with_cargo_space else 20.0  # above threshold either way
        cs.mortal_inventory.items = [Resource(resource_type="ore", quantity=quantity, threshold=2.0,
                                              usable_for=["sell"], converts_to="credits")]
    return cs


def _kb(sell_loc=NERAN, resource_loc=SETHIS):
    return KnowledgeBase(facts=[
        LocationQualityFact(location_id=sell_loc, quality=0.9, quality_type="sell"),
        ResourceFact(location_id=resource_loc),
        RouteFact(from_id=SETHIS, to_id=NERAN, ticks_cost=12),
        RouteFact(from_id=NERAN, to_id=SETHIS, ticks_cost=12),
    ])


def _mortal(cs, kb, loc_id=SETHIS):
    m = MagicMock()
    m.mortal_state = cs
    m.knowledge_base = kb
    m.fatigue = 0.0
    m.assets = [MagicMock(asset_type="merchant_vessel", cargo_capacity=None)]
    m.travel_intent = None
    m.current_location = loc_id
    m.pop_id = None
    m.pop_milieu = None
    m.skill_tags = {}
    return m


def _state(resource_loc=SETHIS):
    loc = MagicMock()
    loc.collectible_resources = [CollectibleResource(resource_type="food_flora", max_yield=5.0)]
    loc.location_type = "pop_location"
    s = MagicMock()
    s.locations = {resource_loc: loc}
    s.pops = {}
    return s


# ── Opportunistic collect before sell-travel ──────────────────────────────────

def test_opportunistic_collect_fires_before_travel():
    """At resource location with sellable goods and pressing purpose, travel to sell wins by
    score (sqrt distance scaling makes 12-tick sell-trip beat local collect), so the
    intercept fires: collect is returned and pending_travel_dest is locked in."""
    cs = _cs(with_sellable=True)
    kb = _kb()
    mortal = _mortal(cs, kb, loc_id=SETHIS)
    state = _state(resource_loc=SETHIS)

    result = evaluate_mortal_action(mortal, state, 0)
    assert result == "collect"
    assert cs.pending_travel_dest == NERAN


def test_pending_travel_commits_next_tick():
    """After opportunistic collect, next tick commits to travel."""
    cs = _cs(with_sellable=True)
    cs.pending_travel_dest = NERAN
    kb = _kb()
    mortal = _mortal(cs, kb, loc_id=SETHIS)
    state = _state(resource_loc=SETHIS)

    result = evaluate_mortal_action(mortal, state, 0)
    assert result == f"travel:{NERAN}"
    assert cs.pending_travel_dest is None


def test_intercept_fires_when_travel_beats_local_collect():
    """When cargo is heavily loaded, sell-travel score dominates — intercept fires,
    pending_travel_dest is set, and collect is returned for one final load."""
    from core.agent_core import MortalNeed
    cs = MortalAgentState(needs=[
        MortalNeed(name="purpose", satisfaction=0.55, pressing_threshold=0.60,
                   urgent_threshold=0.25, decay_rate=0.03),
    ])
    # No cargo cap; large quantity → sigmoid load_fraction≈0.98 → sell_score >> collect_score.
    # (With a cap, quantity must reach the cap to be sellable; uncapped uses Resource.threshold.)
    cs.mortal_inventory.items = [Resource(resource_type="ore", quantity=50.0, threshold=2.0,
                                          usable_for=["sell"], converts_to="credits")]
    kb = _kb()
    mortal = _mortal(cs, kb, loc_id=SETHIS)  # cargo_capacity=None (default)
    state = _state(resource_loc=SETHIS)

    result = evaluate_mortal_action(mortal, state, 0)
    # load_fraction≈0.98; sell_score≈1.06; collect_score≈0.0017;
    # travel:NERAN = (1.06−0.0017)/12 ≈ 0.088 > 0.0017 → intercept fires.
    assert result == "collect"
    assert cs.pending_travel_dest == NERAN


def test_no_opportunistic_collect_when_not_at_resource_location():
    """Not at a resource location — no opportunistic collect, travel directly."""
    cs = _cs(with_sellable=True)
    kb = _kb()
    # Mortal is somewhere else, not at Sethis resource location
    mortal = _mortal(cs, kb, loc_id="other-loc")
    state = _state(resource_loc=SETHIS)

    result = evaluate_mortal_action(mortal, state, 0)
    assert result == f"travel:{NERAN}"
    assert cs.pending_travel_dest is None


def test_pending_travel_fires_before_pressing_needs_check():
    """pending_travel_dest commits even when no pressing needs remain."""
    cs = MortalAgentState()  # no needs at all
    cs.pending_travel_dest = NERAN
    cs.mortal_inventory.items = []
    kb = _kb()
    mortal = _mortal(cs, kb, loc_id=SETHIS)
    state = _state()

    result = evaluate_mortal_action(mortal, state, 0)
    assert result == f"travel:{NERAN}"
    assert cs.pending_travel_dest is None
