"""Tests for TravelLocation tick processing — specifically the skip_initial_tick fix."""
from unittest.mock import MagicMock
from uuid import uuid4

from core.universe_core import TravelLocation
from logic.tick_logic import TickLoop


def _travel_loc(ticks_remaining: int, *, skip_initial_tick: bool = False) -> TravelLocation:
    origin_id = str(uuid4())
    dest_id = str(uuid4())
    tl = TravelLocation(
        name="In transit",
        legs={origin_id: ticks_remaining, dest_id: 0},
        current_waypoint=origin_id,
        ticks_remaining=ticks_remaining,
        skip_initial_tick=skip_initial_tick,
    )
    return tl


def _state_with(tl: TravelLocation):
    state = MagicMock()
    lid = str(tl.id)
    state.locations = {lid: tl}
    state.mortals = {}
    state.pops = {}
    return state


def test_skip_initial_tick_prevents_first_decrement():
    """TravelLocation created in the same tick as decision (skip_initial_tick=True) should
    not have ticks_remaining decremented on the first _process_mortal_travel pass."""
    tl = _travel_loc(2, skip_initial_tick=True)
    loop = TickLoop.__new__(TickLoop)
    loop._process_mortal_travel(_state_with(tl))
    assert tl.ticks_remaining == 2
    assert tl.skip_initial_tick is False


def test_skip_initial_tick_false_decrements_normally():
    """Without skip_initial_tick, first pass decrements as before."""
    tl = _travel_loc(2, skip_initial_tick=False)
    loop = TickLoop.__new__(TickLoop)
    loop._process_mortal_travel(_state_with(tl))
    assert tl.ticks_remaining == 1


def test_two_tick_journey_takes_two_ticks():
    """A journey with ticks_remaining=2 and skip_initial_tick=True should arrive
    after exactly 2 subsequent passes of _process_mortal_travel."""
    tl = _travel_loc(2, skip_initial_tick=True)
    state = _state_with(tl)
    loop = TickLoop.__new__(TickLoop)

    # Pass 1 (same tick as creation): skip flag cleared, no decrement
    loop._process_mortal_travel(state)
    assert tl.ticks_remaining == 2  # still in transit

    # Pass 2 (tick 1): decrement to 1
    loop._process_mortal_travel(state)
    assert tl.ticks_remaining == 1  # still in transit

    # Pass 3 (tick 2): decrement to 0 → arrival (removed from locations)
    loop._process_mortal_travel(state)
    assert str(tl.id) not in state.locations or tl.ticks_remaining == 0
