import json
import pytest
from uuid import uuid4
from core.agent_core import CollectibleResource, Resource
from core.universe_core import PopLocation
from utilities.scenario_loader import _load_collectible_resources


# ── CollectibleResource ───────────────────────────────────────────────────────

def test_cr_max_yield_field():
    cr = CollectibleResource(resource_type="food_flora", max_yield=5.0)
    assert cr.max_yield == 5.0

def test_cr_current_yield_defaults_to_max_yield():
    cr = CollectibleResource(resource_type="food_flora", max_yield=3.0)
    assert cr.current_yield == 3.0

def test_cr_current_yield_can_be_set_explicitly():
    cr = CollectibleResource(resource_type="food_flora", max_yield=10.0, current_yield=4.0)
    assert cr.current_yield == 4.0

def test_cr_yield_renew_rate_field():
    cr = CollectibleResource(resource_type="food_flora", max_yield=10.0, yield_renew_rate=0.1)
    assert cr.yield_renew_rate == 0.1

def test_cr_yield_renew_rate_default():
    cr = CollectibleResource(resource_type="food_flora", max_yield=10.0)
    assert cr.yield_renew_rate == 0.2

def test_cr_action_types_empty_by_default():
    cr = CollectibleResource(resource_type="food_flora", max_yield=5.0)
    assert cr.action_types == []

def test_cr_action_types_can_be_set():
    cr = CollectibleResource(resource_type="food_flora", max_yield=5.0,
                              action_types=["forage", "collect"])
    assert "forage" in cr.action_types
    assert "collect" in cr.action_types

def test_cr_no_resource_yield_field():
    with pytest.raises(Exception):
        CollectibleResource(resource_type="food_flora", resource_yield=5.0)

def test_cr_current_yield_zero_is_not_none():
    cr = CollectibleResource(resource_type="food_flora", max_yield=5.0, current_yield=0.0)
    assert cr.current_yield == 0.0


# ── PopLocation.collectible_resources ─────────────────────────────────────────

def _make_pop_loc(**kwargs):
    defaults = {"id": uuid4(), "name": "Plains", "location_type": "city", "parent_id": uuid4()}
    defaults.update(kwargs)
    return PopLocation(**defaults)

def test_pop_location_has_collectible_resources_list():
    loc = _make_pop_loc()
    assert loc.collectible_resources == []

def test_pop_location_accepts_multiple_collectible_resources():
    cr1 = CollectibleResource(resource_type="food_flora", max_yield=5.0,
                               action_types=["forage"])
    cr2 = CollectibleResource(resource_type="potable_water", max_yield=8.0,
                               action_types=["collect"],
                               biochem_tags=["solvent:water"])
    loc = _make_pop_loc(collectible_resources=[cr1, cr2])
    assert len(loc.collectible_resources) == 2
    assert loc.collectible_resources[0].resource_type == "food_flora"
    assert loc.collectible_resources[1].resource_type == "potable_water"


# ── Resource.decay_rate ───────────────────────────────────────────────────────

def test_resource_decay_rate_defaults_to_zero():
    r = Resource(resource_type="food_flora")
    assert r.decay_rate == 0.0


# ── Persistence ───────────────────────────────────────────────────────────────

def test_load_collectible_resources_empty_list():
    assert _load_collectible_resources("[]", None) == []

def test_load_collectible_resources_from_none():
    assert _load_collectible_resources(None, None) == []

def test_load_collectible_resources_from_new_format():
    raw = json.dumps([{
        "resource_type": "food_flora", "max_yield": 5.0, "yield_renew_rate": 0.2,
        "action_types": ["forage"], "biochem_tags": ["basis:carbon"]
    }])
    result = _load_collectible_resources(raw, None)
    assert len(result) == 1
    assert result[0].resource_type == "food_flora"
    assert result[0].max_yield == 5.0
    assert result[0].current_yield == 5.0   # initialized from max_yield

def test_load_collectible_resources_preserves_depleted_current_yield():
    raw = json.dumps([{
        "resource_type": "food_flora", "max_yield": 10.0, "current_yield": 3.0,
        "yield_renew_rate": 0.1, "action_types": []
    }])
    result = _load_collectible_resources(raw, None)
    assert result[0].current_yield == 3.0  # not reset to max

def test_load_collectible_resources_old_format_fallback():
    # Old single-object with resource_yield (not max_yield)
    old_raw = json.dumps({"resource_yield": 3.0, "cooldown_ticks": 3,
                           "resource_type": "food_flora"})
    result = _load_collectible_resources(None, old_raw)
    assert len(result) == 1
    assert result[0].max_yield == 3.0
    assert result[0].current_yield == 3.0

def test_load_collectible_resources_old_format_already_max_yield():
    # Old format that somehow already has max_yield
    old_raw = json.dumps({"max_yield": 4.0, "cooldown_ticks": 3,
                           "resource_type": "potable_water"})
    result = _load_collectible_resources(None, old_raw)
    assert result[0].max_yield == 4.0
