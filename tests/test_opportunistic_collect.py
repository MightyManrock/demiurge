"""Tests for opportunistic pre-travel collect and pending_travel_dest mechanic."""
import pytest
from unittest.mock import MagicMock
from core.agent_core import (
    CivilianAgentState, MortalNeed, KnowledgeBase,
    RouteFact, LocationQualityFact, ResourceFact, Resource,
)
from logic.civilian_agent_logic import evaluate_civilian_action


NERAN = "neran-surface"
SETHIS = "sethis-surface"


def _pressing_need(name="purpose"):
    return MortalNeed(name=name, satisfaction=0.3, pressing_threshold=0.60,
                      urgent_threshold=0.25, decay_rate=0.03)


def _cs(with_sellable=True, with_cargo_space=True):
    cs = CivilianAgentState(needs=[_pressing_need()])
    if with_sellable:
        quantity = 2.0 if with_cargo_space else 20.0  # above threshold either way
        cs.inventory = [Resource(resource_type="ore", quantity=quantity, threshold=2.0,
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
    m.civilian_state = cs
    m.knowledge_base = kb
    m.fatigue = 0.0
    m.assets = [MagicMock(asset_type="merchant_vessel", cargo_capacity=None)]
    m.travel_intent = None
    m.current_location = loc_id
    m.pop_id = None
    m.pop_milieu = None
    return m


def _state(resource_loc=SETHIS):
    loc = MagicMock()
    loc.collectible_resource = MagicMock()
    loc.location_type = "pop_location"
    s = MagicMock()
    s.locations = {resource_loc: loc}
    s.pops = {}
    return s


# ── Opportunistic collect before sell-travel ──────────────────────────────────

def test_opportunistic_collect_fires_before_travel():
    """At resource location with sellable goods, should collect first then travel."""
    cs = _cs(with_sellable=True)
    kb = _kb()
    mortal = _mortal(cs, kb, loc_id=SETHIS)
    state = _state(resource_loc=SETHIS)

    result = evaluate_civilian_action(mortal, state, 0)
    assert result == "collect"
    assert cs.pending_travel_dest == NERAN


def test_pending_travel_commits_next_tick():
    """After opportunistic collect, next tick commits to travel."""
    cs = _cs(with_sellable=True)
    cs.pending_travel_dest = NERAN
    kb = _kb()
    mortal = _mortal(cs, kb, loc_id=SETHIS)
    state = _state(resource_loc=SETHIS)

    result = evaluate_civilian_action(mortal, state, 0)
    assert result == f"travel:{NERAN}"
    assert cs.pending_travel_dest is None


def test_opportunistic_collect_always_fires_at_resource_before_sell_travel():
    """At resource location with sellable goods, collect always fires first (no cooldown gate)."""
    cs = _cs(with_sellable=True)
    kb = _kb()
    mortal = _mortal(cs, kb, loc_id=SETHIS)
    state = _state(resource_loc=SETHIS)

    result = evaluate_civilian_action(mortal, state, 0)
    assert result == "collect"
    assert cs.pending_travel_dest == NERAN


def test_no_opportunistic_collect_when_not_at_resource_location():
    """Not at a resource location — no opportunistic collect, travel directly."""
    cs = _cs(with_sellable=True)
    kb = _kb()
    # Mortal is somewhere else, not at Sethis resource location
    mortal = _mortal(cs, kb, loc_id="other-loc")
    state = _state(resource_loc=SETHIS)

    result = evaluate_civilian_action(mortal, state, 0)
    assert result == f"travel:{NERAN}"
    assert cs.pending_travel_dest is None


def test_pending_travel_fires_before_pressing_needs_check():
    """pending_travel_dest commits even when no pressing needs remain."""
    cs = CivilianAgentState()  # no needs at all
    cs.pending_travel_dest = NERAN
    cs.inventory = []
    kb = _kb()
    mortal = _mortal(cs, kb, loc_id=SETHIS)
    state = _state()

    result = evaluate_civilian_action(mortal, state, 0)
    assert result == f"travel:{NERAN}"
    assert cs.pending_travel_dest is None
