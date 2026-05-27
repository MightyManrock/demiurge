import pytest
from unittest.mock import MagicMock
from core.agent_core import (
    CivilianAgentState, Resource, MortalNeed, KnowledgeBase,
    RouteFact, LocationQualityFact, ResourceFact,
)
from logic.civilian_agent_logic import evaluate_civilian_action, _trip_too_long_for_urgent_need


def _mortal(cs, kb=None, fatigue=0.0, assets=None, travel_intent=None, loc_id="loc-A"):
    m = MagicMock()
    m.civilian_state = cs
    m.knowledge_base = kb or KnowledgeBase()
    m.fatigue = fatigue
    m.assets = assets or []
    m.travel_intent = travel_intent
    m.current_location = loc_id
    return m


def _state(locations=None):
    s = MagicMock()
    s.locations = locations or {}
    return s


def _pressing_need():
    # satisfaction=0.5: pressing (< 0.65) but NOT urgent (>= 0.35), so trip guard won't fire
    return MortalNeed(name="indulgence", satisfaction=0.5, pressing_threshold=0.65)


# No pressing needs → idle

def test_no_pressing_needs_returns_idle():
    cs = CivilianAgentState(
        needs=[MortalNeed(name="indulgence", satisfaction=1.0)],
    )
    result = evaluate_civilian_action(_mortal(cs), _state(), 0)
    assert result == "idle"


# Fatigue gate

def test_fatigue_blocks_action():
    cs = CivilianAgentState(needs=[_pressing_need()])
    result = evaluate_civilian_action(_mortal(cs, fatigue=0.9), _state(), 0)
    assert result == "idle"


# Sell priority: already at sell location

def test_sell_at_sell_location():
    sell_loc_id = "neran-surface"
    cs = CivilianAgentState(
        needs=[_pressing_need()],
        inventory=[Resource(resource_type="unobtanium", quantity=5.0, threshold=2.0, usable_for=["sell"])],
    )
    kb = KnowledgeBase(facts=[
        LocationQualityFact(location_id=sell_loc_id, quality=0.9, quality_type="sell"),
    ])
    result = evaluate_civilian_action(_mortal(cs, kb, loc_id=sell_loc_id), _state(), 0)
    assert result == "sell"


# Sell priority: needs to travel to sell location

def test_sell_triggers_travel_to_sell_location():
    sell_loc_id = "neran-surface"
    cs = CivilianAgentState(
        needs=[_pressing_need()],
        inventory=[Resource(resource_type="unobtanium", quantity=5.0, threshold=2.0, usable_for=["sell"])],
    )
    kb = KnowledgeBase(facts=[
        LocationQualityFact(location_id=sell_loc_id, quality=0.9, quality_type="sell"),
        RouteFact(from_id="sethis", to_id=sell_loc_id, ticks_cost=12),
    ])
    result = evaluate_civilian_action(_mortal(cs, kb, loc_id="sethis"), _state(), 0)
    assert result == f"travel:{sell_loc_id}"


# Sell skipped when unobtanium below threshold

def test_sell_skipped_below_threshold():
    sell_loc_id = "neran-surface"
    cs = CivilianAgentState(
        needs=[_pressing_need()],
        inventory=[Resource(resource_type="unobtanium", quantity=1.0, threshold=2.0, usable_for=["sell"])],
    )
    kb = KnowledgeBase(facts=[
        LocationQualityFact(location_id=sell_loc_id, quality=0.9, quality_type="sell"),
        RouteFact(from_id="sethis", to_id=sell_loc_id, ticks_cost=12),
    ])
    result = evaluate_civilian_action(_mortal(cs, kb, loc_id="sethis"), _state(), 0)
    assert result != f"travel:{sell_loc_id}"


# Spend priority: already at spend location

def test_spend_at_spend_location():
    spend_loc_id = "neran-surface"
    cs = CivilianAgentState(
        needs=[_pressing_need()],
        inventory=[Resource(resource_type="credits", quantity=3.0, threshold=1.0, usable_for=["spend"])],
    )
    kb = KnowledgeBase(facts=[
        LocationQualityFact(location_id=spend_loc_id, quality=0.9, quality_type="spend"),
    ])
    result = evaluate_civilian_action(_mortal(cs, kb, loc_id=spend_loc_id), _state(), 0)
    assert result == "spend"


# Collect priority: at resource location

def test_collect_at_resource_location():
    loc_id = "sethis-surface"
    loc = MagicMock()
    loc.collectible_resource = MagicMock()
    loc.location_type = "pop_location"
    cs = CivilianAgentState(needs=[_pressing_need()])
    kb = KnowledgeBase(facts=[ResourceFact(location_id=loc_id)])
    result = evaluate_civilian_action(_mortal(cs, kb, loc_id=loc_id), _state({loc_id: loc}), 0)
    assert result == "collect"


# Trip-length awareness: helper correctly identifies trips that are too long

def test_trip_too_long_for_urgent_need_true():
    # satisfaction=0.2, decay_rate=0.05 → ticks_until_desperate = 4; trip=12 → too long
    urgent_need = MortalNeed(name="indulgence", satisfaction=0.2, decay_rate=0.05,
                             pressing_threshold=0.65, urgent_threshold=0.35)
    cs = CivilianAgentState(needs=[urgent_need])
    kb = KnowledgeBase(facts=[RouteFact(from_id="sethis", to_id="neran", ticks_cost=12)])
    assert _trip_too_long_for_urgent_need(cs, kb, "neran") is True


def test_trip_too_long_for_urgent_need_false_when_not_urgent():
    # satisfaction=0.5 → not urgent
    need = MortalNeed(name="indulgence", satisfaction=0.5, decay_rate=0.05,
                      pressing_threshold=0.65, urgent_threshold=0.35)
    cs = CivilianAgentState(needs=[need])
    kb = KnowledgeBase(facts=[RouteFact(from_id="sethis", to_id="neran", ticks_cost=12)])
    assert _trip_too_long_for_urgent_need(cs, kb, "neran") is False
