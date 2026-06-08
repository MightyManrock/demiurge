"""Tests for resource-type-aware travel scoring and KB deduplication."""
import pytest
from unittest.mock import MagicMock
from core.agent_core import (
    KnowledgeBase, ResourceFact, RouteFact, LocationFact,
    MortalAgentState, MortalNeed,
)
from logic.mortal_agent_logic import evaluate_mortal_action


# ── KnowledgeBase.known_resource_locations deduplication ─────────────────────

def test_known_resource_locations_deduplicates():
    """Multiple ResourceFacts for the same location → only one entry returned."""
    kb = KnowledgeBase(facts=[
        ResourceFact(location_id="loc-A", resource_type="food_flora"),
        ResourceFact(location_id="loc-A", resource_type="food_fauna"),
        ResourceFact(location_id="loc-A", resource_type="potable_water"),
        ResourceFact(location_id="loc-B", resource_type="food_flora"),
    ])
    locs = kb.known_resource_locations()
    assert locs.count("loc-A") == 1
    assert locs.count("loc-B") == 1
    assert len(locs) == 2


def test_known_resource_locations_for_filters_by_type():
    """known_resource_locations_for returns only locations with a matching resource."""
    kb = KnowledgeBase(facts=[
        ResourceFact(location_id="loc-water", resource_type="potable_water"),
        ResourceFact(location_id="loc-food",  resource_type="food_flora"),
        ResourceFact(location_id="loc-both",  resource_type="potable_water"),
        ResourceFact(location_id="loc-both",  resource_type="food_flora"),
    ])
    water_locs = kb.known_resource_locations_for({"potable_water"})
    assert set(water_locs) == {"loc-water", "loc-both"}

    food_locs = kb.known_resource_locations_for({"food_flora", "food_fauna"})
    assert set(food_locs) == {"loc-food", "loc-both"}


def test_known_resource_locations_for_empty_types_returns_nothing():
    kb = KnowledgeBase(facts=[ResourceFact(location_id="loc-A", resource_type="food_flora")])
    assert kb.known_resource_locations_for(set()) == []


# ── Travel scoring: resource-type filtering ──────────────────────────────────

def _mortal(cs, kb, loc_id="loc-home"):
    m = MagicMock()
    m.mortal_state = cs
    m.knowledge_base = kb
    m.fatigue = 0.0
    m.assets = []
    m.travel_intent = None
    m.current_location = loc_id
    m.skill_tags = {}
    m.culture_tags = {}
    m.belief_tags = {}
    m.species_id = None
    m.pop_id = None
    m.pop_milieu = None
    return m


def _state():
    s = MagicMock()
    s.locations = {}
    s.pops = {}
    return s


def test_thirsty_mortal_travels_to_water_not_food():
    """With pressing hydration and two equidistant locations, mortal prefers the one with water.
    Food is listed first to ensure ordering can't cause a false pass."""
    cs = MortalAgentState(needs=[
        MortalNeed(name="hydration", satisfaction=0.2, pressing_threshold=0.55, urgent_threshold=0.20),
        MortalNeed(name="nourishment", satisfaction=1.0),
    ])
    kb = KnowledgeBase(facts=[
        ResourceFact(location_id="loc-food",  resource_type="food_flora",    resource_yield=3.0),
        ResourceFact(location_id="loc-water", resource_type="potable_water", resource_yield=3.0),
        RouteFact(from_id="loc-home", to_id="loc-food",  ticks_cost=2),
        RouteFact(from_id="loc-home", to_id="loc-water", ticks_cost=2),
    ])
    result = evaluate_mortal_action(_mortal(cs, kb), _state(), 0)
    assert result == "travel:loc-water"


def test_hungry_mortal_travels_to_food_not_unrelated():
    """With pressing nourishment, mortal targets food location not unrelated mineral location.
    Mineral is listed first to ensure ordering can't cause a false pass."""
    cs = MortalAgentState(needs=[
        MortalNeed(name="nourishment", satisfaction=0.2, pressing_threshold=0.55, urgent_threshold=0.20),
        MortalNeed(name="hydration", satisfaction=1.0),
    ])
    kb = KnowledgeBase(facts=[
        ResourceFact(location_id="loc-mineral", resource_type="salt_mineral", resource_yield=3.0),
        ResourceFact(location_id="loc-food",    resource_type="food_flora",  resource_yield=3.0),
        RouteFact(from_id="loc-home", to_id="loc-mineral", ticks_cost=2),
        RouteFact(from_id="loc-home", to_id="loc-food",    ticks_cost=2),
    ])
    result = evaluate_mortal_action(_mortal(cs, kb), _state(), 0)
    assert result == "travel:loc-food"


def test_both_needs_pressing_considers_both_resource_types():
    """With both nourishment and hydration pressing, food OR water locations are valid candidates."""
    cs = MortalAgentState(needs=[
        MortalNeed(name="nourishment", satisfaction=0.2, pressing_threshold=0.55, urgent_threshold=0.20),
        MortalNeed(name="hydration",   satisfaction=0.2, pressing_threshold=0.55, urgent_threshold=0.20),
    ])
    kb = KnowledgeBase(facts=[
        ResourceFact(location_id="loc-water", resource_type="potable_water", resource_yield=3.0),
        ResourceFact(location_id="loc-food",  resource_type="food_flora",    resource_yield=3.0),
        RouteFact(from_id="loc-home", to_id="loc-water", ticks_cost=2),
        RouteFact(from_id="loc-home", to_id="loc-food",  ticks_cost=2),
    ])
    result = evaluate_mortal_action(_mortal(cs, kb), _state(), 0)
    assert result in ("travel:loc-water", "travel:loc-food")


def test_no_pressing_need_considers_all_resource_locations():
    """With no pressing survival need, the might-as-well roll can still drive collect
    and all known resource locations remain candidates for travel."""
    cs = MortalAgentState(needs=[
        MortalNeed(name="nourishment", satisfaction=1.0),
        MortalNeed(name="hydration",   satisfaction=1.0),
    ])
    # Force a high might-as-well roll by including a directive fact
    from core.agent_core import DirectiveFact
    kb = KnowledgeBase(facts=[
        ResourceFact(location_id="loc-mineral", resource_type="salt_mineral", resource_yield=3.0),
        RouteFact(from_id="loc-home", to_id="loc-mineral", ticks_cost=1),
        DirectiveFact(
            directive_id="d1", directive_type="commerce",
            satisfying_action="collect", target_pop_location_id="loc-mineral",
            source_faction_id="f1",
        ),
    ])
    result = evaluate_mortal_action(_mortal(cs, kb), _state(), 0)
    # When directive is active, collect/travel scores should fire — mineral is valid
    assert result in ("travel:loc-mineral", "collect", "idle")
