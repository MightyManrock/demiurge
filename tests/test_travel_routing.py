"""
tests/test_travel_routing.py

Unit tests for:
  - utilities.travel_routing._mortal_meets_condition
  - utilities.travel_routing.find_qualified_routes
  - logic.mortal_agent_logic._select_best_route
"""
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

from utilities.travel_routing import (
    _mortal_meets_condition,
    find_qualified_routes,
    TravelRoute,
)
from logic.mortal_agent_logic import _select_best_route
from core.agent_core import MortalAgentState, MortalNeed, Resource
from core.universe_core import NetworkCondition, ResourceCost, SocialClass, PopLocation, TravelNetwork


# ── helpers ──────────────────────────────────────────────────────────────────

def _pop_loc(loc_id: UUID, net_ids=None, danger: float = 0.0) -> PopLocation:
    """Minimal real PopLocation instance."""
    return PopLocation(
        id=loc_id,
        name="Test",
        location_type="city",
        travel_network_ids=net_ids or [],
        danger=danger,
    )


def _empty_condition() -> NetworkCondition:
    return NetworkCondition()


def _make_route(total_ticks: int = 5, resource_costs=None) -> TravelRoute:
    origin = uuid4()
    return TravelRoute(
        waypoints=[origin],
        legs={str(origin): 0},
        total_ticks=total_ticks,
        resource_costs=resource_costs or [],
        network_ids=[],
        total_danger=0.0,
        avg_danger_per_location=0.0,
        avg_danger_per_tick=0.0,
    )


# ── _mortal_meets_condition ───────────────────────────────────────────────────

def test_empty_condition_always_passes():
    cond = _empty_condition()
    mortal = MagicMock()
    state = MagicMock()
    assert _mortal_meets_condition(cond, mortal, state) is True


def test_faction_gate_pass():
    faction_id = uuid4()
    cond = NetworkCondition(faction_ids=[faction_id])

    mortal = MagicMock()
    mortal.faction_ids = [faction_id]

    state = MagicMock()

    assert _mortal_meets_condition(cond, mortal, state) is True


def test_faction_gate_fail():
    faction_id = uuid4()
    other_faction = uuid4()
    cond = NetworkCondition(faction_ids=[faction_id])

    mortal = MagicMock()
    mortal.faction_ids = [other_faction]

    state = MagicMock()

    assert _mortal_meets_condition(cond, mortal, state) is False


def test_no_faction_membership_blocks_faction_gate():
    faction_id = uuid4()
    cond = NetworkCondition(faction_ids=[faction_id])

    mortal = MagicMock()
    mortal.faction_ids = []

    state = MagicMock()

    assert _mortal_meets_condition(cond, mortal, state) is False


def test_asset_type_gate_pass():
    cond = NetworkCondition(asset_types=["freighter"])

    asset = MagicMock()
    asset.asset_type = "freighter"

    mortal = MagicMock()
    mortal.assets = [asset]

    state = MagicMock()

    assert _mortal_meets_condition(cond, mortal, state) is True


def test_occupation_gate_pass_and_fail():
    cond = NetworkCondition(pop_occupations=["trader"])

    mortal_pass = MagicMock()
    mortal_pass.occupation = "trader"

    mortal_fail = MagicMock()
    mortal_fail.occupation = "farmer"

    state = MagicMock()

    assert _mortal_meets_condition(cond, mortal_pass, state) is True
    assert _mortal_meets_condition(cond, mortal_fail, state) is False


# ── find_qualified_routes ─────────────────────────────────────────────────────

def _make_state(locations: dict, travel_networks: dict) -> MagicMock:
    state = MagicMock()
    state.locations = locations
    state.travel_networks = travel_networks
    return state


def test_trivial_same_origin_destination():
    loc_id = uuid4()
    loc = _pop_loc(loc_id)
    state = _make_state({str(loc_id): loc}, {})

    mortal = MagicMock()
    mortal.pop_id = None

    routes = find_qualified_routes(state, mortal, None, loc_id, loc_id)
    assert len(routes) == 1
    assert routes[0].total_ticks == 0


def test_unreachable_destination():
    loc_a = uuid4()
    loc_b = uuid4()
    # Each location has no travel networks — no shared membership possible
    state = _make_state(
        {str(loc_a): _pop_loc(loc_a), str(loc_b): _pop_loc(loc_b)},
        {},
    )

    mortal = MagicMock()
    mortal.pop_id = None

    routes = find_qualified_routes(state, mortal, None, loc_a, loc_b)
    assert routes == []


def test_basic_two_hop_route():
    loc_a = uuid4()
    loc_b = uuid4()
    loc_c = uuid4()

    net = TravelNetwork(name="Test Net", member_ids=[loc_a, loc_b, loc_c], conditions=[])
    net_str = str(net.id)

    a = _pop_loc(loc_a, net_ids=[net.id])
    b = _pop_loc(loc_b, net_ids=[net.id])
    c = _pop_loc(loc_c, net_ids=[net.id])

    # Give locations intra-world depth so leg_cost works (same parent → intra-world formula)
    # distance_from_core defaults to 0 so leg_cost returns max(1, 0+0) = 1

    state = _make_state(
        {str(loc_a): a, str(loc_b): b, str(loc_c): c},
        {net_str: net},
    )
    # leg_cost calls state.locations.get and checks isinstance(loc, PopLocation)
    # parent_id defaults to None, so _divergence_coordinates returns None → intra-world

    mortal = MagicMock()
    mortal.pop_id = None

    routes = find_qualified_routes(state, mortal, None, loc_a, loc_c)
    assert len(routes) == 1
    assert routes[0].total_ticks > 0


def test_hard_gate_filters_network():
    loc_a = uuid4()
    loc_b = uuid4()  # reachable only via blocked net_x
    loc_c = uuid4()  # reachable via open net_y (A→C direct)

    faction_id = uuid4()
    hard_condition = NetworkCondition(faction_ids=[faction_id], hard_gate=True)
    open_condition = NetworkCondition()  # no restrictions

    net_x = TravelNetwork(name="Blocked Net", member_ids=[loc_a, loc_b], conditions=[hard_condition])
    net_y = TravelNetwork(name="Open Net",    member_ids=[loc_a, loc_c], conditions=[open_condition])

    a = _pop_loc(loc_a, net_ids=[net_x.id, net_y.id])
    b = _pop_loc(loc_b, net_ids=[net_x.id])
    c = _pop_loc(loc_c, net_ids=[net_y.id])

    state = _make_state(
        {str(loc_a): a, str(loc_b): b, str(loc_c): c},
        {str(net_x.id): net_x, str(net_y.id): net_y},
    )

    # Mortal belongs to a different faction — fails the hard gate on net_x
    mortal = MagicMock()
    mortal.faction_ids = [uuid4()]  # not faction_id
    mortal.occupation = "farmer"
    mortal.assets = []
    mortal.civilization_id = None

    # Route to B (only via blocked net_x) should fail
    routes_to_b = find_qualified_routes(state, mortal, None, loc_a, loc_b)
    assert routes_to_b == []

    # Route to C (via open net_y) should succeed
    routes_to_c = find_qualified_routes(state, mortal, None, loc_a, loc_c)
    assert len(routes_to_c) == 1


# ── _select_best_route ────────────────────────────────────────────────────────

def test_empty_routes_returns_none():
    result = _select_best_route([], mortal_state=None)
    assert result is None


def test_picks_lowest_tick_count():
    slow = _make_route(total_ticks=10)
    fast = _make_route(total_ticks=5)

    result = _select_best_route([slow, fast], mortal_state=None)
    assert result is fast


def test_filters_unaffordable_resource_cost():
    rc = ResourceCost(resource_type="food", amount=10, consumed=True)
    route = _make_route(total_ticks=3, resource_costs=[rc])

    inventory = Resource(resource_type="food", quantity=3.0)
    mortal_state = MortalAgentState(inventory=[inventory])

    result = _select_best_route([route], mortal_state=mortal_state)
    assert result is None


def test_no_mortal_state_returns_route():
    rc = ResourceCost(resource_type="food", amount=10, consumed=True)
    route = _make_route(total_ticks=3, resource_costs=[rc])

    # No mortal_state means no affordability check — route passes through
    result = _select_best_route([route], mortal_state=None)
    assert result is route
