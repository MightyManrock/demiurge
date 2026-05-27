import pytest
from core.agent_core import (
    Resource, MortalNeed, CivilianAgentState,
    CollectibleResource, LocationQualityFact, RouteFact, ResourceFact,
    KnowledgeBase,
)


# Resource

def test_resource_defaults():
    r = Resource(resource_type="credits")
    assert r.quantity == 0.0
    assert r.converts_to is None
    assert r.usable_for == []
    assert r.fills_need is None


def test_resource_below_threshold():
    r = Resource(resource_type="unobtanium", quantity=0.5, threshold=2.0)
    assert r.quantity < r.threshold


# MortalNeed

def test_mortal_need_pressing_threshold_default():
    n = MortalNeed(name="indulgence")
    assert n.pressing_threshold == 0.65


def test_mortal_need_is_pressing():
    n = MortalNeed(name="indulgence", satisfaction=0.5, pressing_threshold=0.65)
    assert n.is_pressing


def test_mortal_need_is_urgent():
    n = MortalNeed(name="indulgence", satisfaction=0.2, urgent_threshold=0.35)
    assert n.is_urgent


def test_mortal_need_not_urgent():
    n = MortalNeed(name="indulgence", satisfaction=0.5, urgent_threshold=0.35)
    assert not n.is_urgent


# CivilianAgentState

def test_civilian_state_inventory_default():
    cs = CivilianAgentState()
    assert cs.inventory == []


def test_civilian_state_get_resource_found():
    r = Resource(resource_type="unobtanium", quantity=5.0)
    cs = CivilianAgentState(inventory=[r])
    found = cs.get_resource("unobtanium")
    assert found is r


def test_civilian_state_get_resource_missing():
    cs = CivilianAgentState()
    assert cs.get_resource("unobtanium") is None


def test_civilian_state_round_trips_json():
    r = Resource(resource_type="unobtanium", quantity=3.0, usable_for=["sell"], converts_to="credits")
    cs = CivilianAgentState(inventory=[r])
    restored = CivilianAgentState.model_validate_json(cs.model_dump_json())
    assert restored.inventory[0].resource_type == "unobtanium"
    assert restored.inventory[0].usable_for == ["sell"]


def test_old_json_with_resources_float_loads_cleanly():
    # Pydantic v2 ignores unknown fields — old DB rows must not crash
    old_json = '{"needs":[],"resources":5.0,"spend_threshold":2.0,"action_cooldowns":{}}'
    cs = CivilianAgentState.model_validate_json(old_json)
    assert cs.inventory == []


# CollectibleResource

def test_collectible_resource_has_resource_type():
    cr = CollectibleResource()
    assert cr.resource_type == "unobtanium"


# LocationQualityFact

def test_location_quality_fact_quality_type_default():
    f = LocationQualityFact(location_id="abc")
    assert f.quality_type == "spend"


# RouteFact

def test_route_fact_ticks_cost_default():
    f = RouteFact(from_id="a", to_id="b")
    assert f.ticks_cost == 0


# ResourceFact

def test_resource_fact_resource_type_default():
    f = ResourceFact(location_id="abc")
    assert f.resource_type == "unobtanium"


# KnowledgeBase helpers

def test_knowledge_base_best_known_spend_location():
    kb = KnowledgeBase(facts=[
        LocationQualityFact(location_id="neran", quality=0.9, quality_type="spend"),
        LocationQualityFact(location_id="sethis", quality=0.2, quality_type="sell"),
    ])
    assert kb.best_known_spend_location() == "neran"


def test_knowledge_base_best_known_sell_location():
    kb = KnowledgeBase(facts=[
        LocationQualityFact(location_id="neran", quality=0.9, quality_type="sell"),
        LocationQualityFact(location_id="sethis", quality=0.2, quality_type="spend"),
    ])
    assert kb.best_known_sell_location() == "neran"


def test_knowledge_base_route_ticks_to():
    kb = KnowledgeBase(facts=[
        RouteFact(from_id="a", to_id="b", ticks_cost=12),
    ])
    assert kb.route_ticks_to("b") == 12
    assert kb.route_ticks_to("c") == 0
