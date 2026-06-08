"""Tests for Phase 1: Real Pop Migration.

Covers:
  - New Pop migration fields (migration_ticks_remaining, migration_destination_id,
    migration_travel_location_id) and their defaults
  - _process_pop_travel tick phase: decrement, arrival, field clearing
  - Migration decision in resolve_pop_actions: sets fields, creates TravelLocation
  - Band cascade migration: band members join at same origin
  - Mortal embedding: mortals with matching band_id enter the same TravelLocation
"""
from unittest.mock import MagicMock
from uuid import uuid4, UUID
from core.agent_core import PopAgentState, PopNeed
from core.universe_core import Pop, PopLocation, TravelLocation, NotableMortal


# ── Helpers ────────────────────────────────────────────────────────────────────

def _pop(loc_id: str | UUID, **kw) -> Pop:
    return Pop(
        current_location=UUID(str(loc_id)),
        social_class=None,
        **kw,
    )


def _pop_loc(loc_id: str | UUID | None = None) -> PopLocation:
    lid = uuid4() if loc_id is None else UUID(str(loc_id))
    return PopLocation(
        id=lid,
        name="Somewhere",
        location_type="pop_location",
        pop_ids=[],
    )


def _simple_state(locs: dict, pops: dict, mortals: dict | None = None):
    state = MagicMock()
    state.locations = locs
    state.pops = pops
    state.mortals = mortals or {}
    return state


# ── Group 1: New Pop model fields ─────────────────────────────────────────────

def test_pop_migration_ticks_remaining_default():
    p = _pop(uuid4())
    assert p.migration_ticks_remaining == 0


def test_pop_migration_destination_id_default():
    p = _pop(uuid4())
    assert p.migration_destination_id is None


def test_pop_migration_travel_location_id_default():
    p = _pop(uuid4())
    assert p.migration_travel_location_id is None


def test_pop_migration_fields_settable():
    dest = uuid4()
    tl_id = uuid4()
    p = _pop(uuid4(), migration_ticks_remaining=5, migration_destination_id=dest,
             migration_travel_location_id=tl_id)
    assert p.migration_ticks_remaining == 5
    assert p.migration_destination_id == dest
    assert p.migration_travel_location_id == tl_id


# ── Group 2: _process_pop_travel tick phase ───────────────────────────────────

def _make_travel_state(ticks: int, dest_id: str | None = None):
    """Build a minimal state with one pop in a TravelLocation."""
    origin_id = str(uuid4())
    destination_id = dest_id or str(uuid4())

    dest_loc = _pop_loc(destination_id)
    dest_loc.pop_ids = []

    tl_id = str(uuid4())
    tl = TravelLocation(
        id=UUID(tl_id),
        name="In transit",
        legs={origin_id: ticks, destination_id: 0},
        current_waypoint=origin_id,
        ticks_remaining=ticks,
        pop_ids=[],
    )

    pop = _pop(
        origin_id,
        migration_ticks_remaining=ticks,
        migration_destination_id=UUID(destination_id),
        migration_travel_location_id=UUID(tl_id),
    )
    pop_id = pop.id
    tl.pop_ids.append(pop_id)

    locs = {tl_id: tl, destination_id: dest_loc}
    pops = {str(pop_id): pop}
    return _simple_state(locs, pops), pop, tl, dest_loc


def test_process_pop_travel_decrements_ticks():
    from logic.tick_logic import TickLoop
    state, pop, tl, dest = _make_travel_state(ticks=3)
    loop = TickLoop.__new__(TickLoop)
    loop._process_pop_travel(state)
    assert pop.migration_ticks_remaining == 2


def test_process_pop_travel_does_not_move_pop_while_in_transit():
    from logic.tick_logic import TickLoop
    dest_id = str(uuid4())
    state, pop, tl, dest = _make_travel_state(ticks=3, dest_id=dest_id)
    original_loc = pop.current_location
    loop = TickLoop.__new__(TickLoop)
    loop._process_pop_travel(state)
    assert pop.current_location == original_loc


def test_process_pop_travel_arrival_moves_pop_to_destination():
    from logic.tick_logic import TickLoop
    dest_id = str(uuid4())
    state, pop, tl, dest = _make_travel_state(ticks=1, dest_id=dest_id)
    loop = TickLoop.__new__(TickLoop)
    loop._process_pop_travel(state)
    assert pop.current_location == UUID(dest_id)


def test_process_pop_travel_arrival_clears_migration_fields():
    from logic.tick_logic import TickLoop
    state, pop, tl, dest = _make_travel_state(ticks=1)
    loop = TickLoop.__new__(TickLoop)
    loop._process_pop_travel(state)
    assert pop.migration_ticks_remaining == 0
    assert pop.migration_destination_id is None
    assert pop.migration_travel_location_id is None


def test_process_pop_travel_arrival_adds_pop_to_destination_pop_ids():
    from logic.tick_logic import TickLoop
    state, pop, tl, dest = _make_travel_state(ticks=1)
    loop = TickLoop.__new__(TickLoop)
    loop._process_pop_travel(state)
    assert pop.id in dest.pop_ids


def test_process_pop_travel_arrival_removes_travel_location():
    from logic.tick_logic import TickLoop
    state, pop, tl, dest = _make_travel_state(ticks=1)
    loop = TickLoop.__new__(TickLoop)
    loop._process_pop_travel(state)
    assert str(tl.id) not in state.locations


def test_process_pop_travel_skip_initial_tick():
    """TravelLocation created mid-tick with skip_initial_tick=True should not decrement on first pass."""
    from logic.tick_logic import TickLoop
    state, pop, tl, dest = _make_travel_state(ticks=2)
    tl.skip_initial_tick = True
    loop = TickLoop.__new__(TickLoop)
    loop._process_pop_travel(state)
    assert pop.migration_ticks_remaining == 2
    assert tl.skip_initial_tick is False


# ── Group 3: Migration decision wires travel state ────────────────────────────

def test_migrate_action_sets_migration_fields():
    """When resolve_pop_actions fires the 'migrate' action and a route exists,
    the pop's migration fields are set and it is added to a TravelLocation."""
    from logic.pop_agent_logic import resolve_pop_actions

    origin_id = str(uuid4())
    dest_id = str(uuid4())

    origin_loc = _pop_loc(origin_id)
    dest_loc = _pop_loc(dest_id)

    # Share a TravelNetwork so find_route finds a path
    from core.universe_core import TravelNetwork
    net_id = uuid4()
    net = TravelNetwork(id=net_id, name="Road", member_ids=[UUID(origin_id), UUID(dest_id)])
    origin_loc.travel_network_ids = [net_id]
    dest_loc.travel_network_ids = [net_id]

    pop = _pop(origin_id)
    pop_state = PopAgentState(
        needs=[PopNeed(name="wanderlust", satisfaction=0.1)],
        pending_migration_dest=UUID(dest_id),
    )
    pop.pop_state = pop_state

    state = MagicMock()
    state.locations = {origin_id: origin_loc, dest_id: dest_loc}
    state.travel_networks = {str(net_id): net}
    state.pops = {str(pop.id): pop}
    state.mortals = {}
    state.bands = {}

    _full_priorities = {"migrate": 1.0}
    resolve_pop_actions(pop, origin_loc, _full_priorities, n_slots=1,
                        factions={}, current_tick=1, state=state)

    # Pop should now have migration fields set
    assert pop.migration_destination_id == UUID(dest_id)
    assert pop.migration_travel_location_id is not None
    assert pop.migration_ticks_remaining > 0


# ── Group 4: Band cascade migration ───────────────────────────────────────────

def test_band_cascade_joins_band_members_at_origin():
    """When a pop migrates, other pops sharing its band_id at the same origin
    are automatically added to the same TravelLocation."""
    from logic.pop_agent_logic import resolve_pop_actions
    from core.universe_core import TravelNetwork

    band_id = uuid4()
    origin_id = str(uuid4())
    dest_id = str(uuid4())

    origin_loc = _pop_loc(origin_id)
    dest_loc = _pop_loc(dest_id)
    net_id = uuid4()
    net = TravelNetwork(id=net_id, name="Road", member_ids=[UUID(origin_id), UUID(dest_id)])
    origin_loc.travel_network_ids = [net_id]
    dest_loc.travel_network_ids = [net_id]

    # Primary migrating pop
    pop_a = _pop(origin_id, band_id=band_id)
    pop_a.pop_state = PopAgentState(
        needs=[PopNeed(name="wanderlust", satisfaction=0.1)],
        pending_migration_dest=UUID(dest_id),
    )

    # Band member at same location
    pop_b = _pop(origin_id, band_id=band_id)
    pop_b.pop_state = PopAgentState(needs=[PopNeed(name="wanderlust", satisfaction=0.9)])

    pops = {str(pop_a.id): pop_a, str(pop_b.id): pop_b}
    state = MagicMock()
    state.locations = {origin_id: origin_loc, dest_id: dest_loc}
    state.travel_networks = {str(net_id): net}
    state.pops = pops
    state.mortals = {}
    state.bands = {}

    resolve_pop_actions(pop_a, origin_loc, {"migrate": 1.0}, n_slots=1,
                        factions={}, current_tick=1, state=state)

    # pop_b should be in the same TravelLocation as pop_a
    assert pop_b.migration_travel_location_id is not None
    assert pop_b.migration_travel_location_id == pop_a.migration_travel_location_id


# ── Group 5: Mortal embedding ─────────────────────────────────────────────────

def test_mortal_embedding_on_pop_migration():
    """When a pop migrates, mortals with matching band_id and no pending travel
    are embedded in the same TravelLocation."""
    from logic.pop_agent_logic import resolve_pop_actions
    from core.universe_core import TravelNetwork

    band_id = uuid4()
    origin_id = str(uuid4())
    dest_id = str(uuid4())

    origin_loc = _pop_loc(origin_id)
    dest_loc = _pop_loc(dest_id)
    net_id = uuid4()
    net = TravelNetwork(id=net_id, name="Road", member_ids=[UUID(origin_id), UUID(dest_id)])
    origin_loc.travel_network_ids = [net_id]
    dest_loc.travel_network_ids = [net_id]

    pop_a = _pop(origin_id, band_id=band_id)
    pop_a.pop_state = PopAgentState(
        needs=[PopNeed(name="wanderlust", satisfaction=0.1)],
        pending_migration_dest=UUID(dest_id),
    )

    mortal = NotableMortal(
        name="Asha Keln",
        home_location=UUID(origin_id),
        current_location=UUID(origin_id),
        band_id=band_id,
        travel_intent=None,
    )

    pops = {str(pop_a.id): pop_a}
    mortals = {str(mortal.id): mortal}
    state = MagicMock()
    state.locations = {origin_id: origin_loc, dest_id: dest_loc}
    state.travel_networks = {str(net_id): net}
    state.pops = pops
    state.mortals = mortals
    state.bands = {}

    resolve_pop_actions(pop_a, origin_loc, {"migrate": 1.0}, n_slots=1,
                        factions={}, current_tick=1, state=state)

    # Mortal should be in a TravelLocation (its current_location points to a TravelLocation)
    tl_id = str(pop_a.migration_travel_location_id)
    travel_loc = state.locations.get(tl_id)
    assert travel_loc is not None
    assert mortal.id in travel_loc.occupants
