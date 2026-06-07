import json
import pytest
from uuid import uuid4
from unittest.mock import MagicMock
from core.agent_core import CollectibleResource, Resource, PopAgentState, PopNeed
from core.universe_core import PopLocation, Pop
from logic.pop_agent_logic import resolve_pop_actions, ACTION_NEED_MAP
from utilities.scenario_loader import _load_collectible_resources
from logic.needs_config import (
    NEED_NOURISHMENT, NEED_HYDRATION,
    CANONICAL_MORTAL_NEED_NAMES, MORTAL_NEED_DEFAULTS,
    POP_NEED_NOURISHMENT, POP_NEED_HYDRATION,
    POP_NEED_DEFAULTS, compute_pop_need_profile, initialize_pop_state,
    compute_need_profile,
)


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


# ── Need split: sustenance → nourishment + hydration ─────────────────────────

def test_need_nourishment_constant():
    assert NEED_NOURISHMENT == "nourishment"

def test_need_hydration_constant():
    assert NEED_HYDRATION == "hydration"

def test_sustenance_not_in_canonical_mortal_needs():
    assert "sustenance" not in CANONICAL_MORTAL_NEED_NAMES

def test_nourishment_in_canonical_mortal_needs():
    assert "nourishment" in CANONICAL_MORTAL_NEED_NAMES

def test_hydration_in_canonical_mortal_needs():
    assert "hydration" in CANONICAL_MORTAL_NEED_NAMES

def test_hydration_decays_faster_than_nourishment():
    nour_decay = MORTAL_NEED_DEFAULTS["nourishment"]["decay_rate"]
    hydr_decay = MORTAL_NEED_DEFAULTS["hydration"]["decay_rate"]
    assert hydr_decay > nour_decay

def test_compute_need_profile_has_nourishment_and_hydration():
    needs = compute_need_profile({})
    names = [n.name for n in needs]
    assert "nourishment" in names
    assert "hydration" in names
    assert "sustenance" not in names

def test_pop_nourishment_and_hydration_constants():
    assert POP_NEED_NOURISHMENT == "nourishment"
    assert POP_NEED_HYDRATION == "hydration"

def test_pop_hydration_decays_faster():
    nour_decay = POP_NEED_DEFAULTS["nourishment"]["decay_rate"]
    hydr_decay = POP_NEED_DEFAULTS["hydration"]["decay_rate"]
    assert hydr_decay > nour_decay

def test_initialize_pop_state_has_nourishment_and_hydration():
    pop = MagicMock()
    pop.culture_tags = {}
    state = initialize_pop_state(pop)
    names = [n.name for n in state.needs]
    assert "nourishment" in names
    assert "hydration" in names
    assert "sustenance" not in names


# ── Task 4: Pop agent action_types gating ────────────────────────────────────

def _make_pop_state_with_needs(**need_satisfactions):
    needs = []
    defaults = {
        "nourishment": 1.0, "hydration": 1.0, "safety": 1.0,
        "cohesion": 1.0, "purpose": 1.0, "shelter": 1.0, "wanderlust": 1.0,
    }
    defaults.update(need_satisfactions)
    for name, sat in defaults.items():
        needs.append(PopNeed(name=name, satisfaction=sat,
                              decay_rate=0.02, pressing_threshold=0.55, urgent_threshold=0.20))
    return PopAgentState(needs=needs)

def _make_loc_with_resource(resource_type, max_yield, action_types, biochem_tags=None):
    cr = CollectibleResource(
        resource_type=resource_type, max_yield=max_yield,
        current_yield=max_yield, action_types=action_types,
        biochem_tags=biochem_tags or []
    )
    loc = PopLocation(id=uuid4(), name="Plains", location_type="city", parent_id=uuid4(),
                      collectible_resources=[cr])
    return loc


def test_action_need_map_forage_maps_to_nourishment():
    assert ACTION_NEED_MAP["forage"] == "nourishment"

def test_action_need_map_hunt_maps_to_nourishment():
    assert ACTION_NEED_MAP["hunt"] == "nourishment"

def test_action_need_map_no_sustenance_key():
    assert "sustenance" not in ACTION_NEED_MAP.values()

def test_forage_depletes_current_yield():
    pop = MagicMock()
    pop.id = uuid4()
    pop.pop_state = _make_pop_state_with_needs(nourishment=0.1)
    pop.size_fractional = 1.0
    pop.social_class = MagicMock()
    pop.social_class.value = "common"
    pop.occupation = "farmer"
    pop.active_directives = []
    pop.faction_ids = []

    loc = _make_loc_with_resource("food_flora", 10.0, ["forage"],
                                   biochem_tags=["basis:carbon"])
    state = MagicMock()
    state.factions = {}

    resolve_pop_actions(pop, loc, [], 1, state)

    assert loc.resource_stockpile.get("food_flora", 0.0) > 0
    assert loc.collectible_resources[0].current_yield < 10.0  # depleted

def test_forage_bounded_by_current_yield():
    pop = MagicMock()
    pop.id = uuid4()
    pop.pop_state = _make_pop_state_with_needs(nourishment=0.1)
    pop.size_fractional = 5.0
    pop.social_class = MagicMock()
    pop.social_class.value = "common"
    pop.occupation = "farmer"
    pop.active_directives = []
    pop.faction_ids = []

    loc = _make_loc_with_resource("food_flora", 2.0, ["forage"])
    loc.collectible_resources[0].current_yield = 0.5  # nearly depleted
    state = MagicMock()
    state.factions = {}

    resolve_pop_actions(pop, loc, [], 1, state)

    assert loc.resource_stockpile.get("food_flora", 0.0) <= 0.5
    assert loc.collectible_resources[0].current_yield >= 0.0

def test_consumption_pass_basis_resource_fills_nourishment():
    pop = MagicMock()
    pop.id = uuid4()
    pop.pop_state = _make_pop_state_with_needs(nourishment=0.3)
    pop.size_fractional = 1.0
    pop.social_class = MagicMock()
    pop.social_class.value = "common"
    pop.occupation = "farmer"
    pop.active_directives = []
    pop.faction_ids = []

    loc = PopLocation(id=uuid4(), name="Plains", location_type="city", parent_id=uuid4(),
                      resource_stockpile={"food_flora": 10.0},
                      collectible_resources=[])
    state = MagicMock()
    state.factions = {}

    before = pop.pop_state.get_need("nourishment").satisfaction
    resolve_pop_actions(pop, loc, [], 1, state)
    after = pop.pop_state.get_need("nourishment").satisfaction
    assert after >= before

def test_consumption_pass_solvent_resource_fills_hydration():
    pop = MagicMock()
    pop.id = uuid4()
    pop.pop_state = _make_pop_state_with_needs(hydration=0.3)
    pop.size_fractional = 1.0
    pop.social_class = MagicMock()
    pop.social_class.value = "common"
    pop.occupation = "farmer"
    pop.active_directives = []
    pop.faction_ids = []

    loc = PopLocation(id=uuid4(), name="Plains", location_type="city", parent_id=uuid4(),
                      resource_stockpile={"potable_water": 10.0},
                      collectible_resources=[])
    state = MagicMock()
    state.factions = {}

    before = pop.pop_state.get_need("hydration").satisfaction
    resolve_pop_actions(pop, loc, [], 1, state)
    after = pop.pop_state.get_need("hydration").satisfaction
    assert after >= before


# ── Task 5: Yield renewal ─────────────────────────────────────────────────────

def _make_state_with_location(cr):
    from core.universe_core import PopLocation
    loc = PopLocation(id=uuid4(), name="Plains", parent_id=uuid4(),
                      location_type="city", collectible_resources=[cr])
    state = MagicMock()
    state.locations = {str(loc.id): loc}
    return state, loc


def test_yield_renewal_increases_current_yield():
    cr = CollectibleResource(resource_type="food_flora", max_yield=10.0,
                              yield_renew_rate=0.1, current_yield=5.0)
    state, loc = _make_state_with_location(cr)

    from logic.tick_logic import _tick_yield_renewal
    _tick_yield_renewal(state)

    assert loc.collectible_resources[0].current_yield == pytest.approx(6.0)

def test_yield_renewal_capped_at_max_yield():
    cr = CollectibleResource(resource_type="food_flora", max_yield=10.0,
                              yield_renew_rate=0.5, current_yield=9.0)
    state, loc = _make_state_with_location(cr)

    from logic.tick_logic import _tick_yield_renewal
    _tick_yield_renewal(state)

    # 9.0 + 0.5 * 10.0 = 14.0 → capped at 10.0
    assert loc.collectible_resources[0].current_yield == pytest.approx(10.0)

def test_yield_renewal_already_full_stays_full():
    cr = CollectibleResource(resource_type="food_flora", max_yield=10.0,
                              yield_renew_rate=0.2, current_yield=10.0)
    state, loc = _make_state_with_location(cr)

    from logic.tick_logic import _tick_yield_renewal
    _tick_yield_renewal(state)

    assert loc.collectible_resources[0].current_yield == pytest.approx(10.0)

def test_yield_renewal_skips_non_pop_locations():
    from core.universe_core import SignificantLocation
    sig_loc = SignificantLocation(id=uuid4(), name="Region", parent_id=uuid4(),
                                  location_type="planet")
    state = MagicMock()
    state.locations = {str(sig_loc.id): sig_loc}

    from logic.tick_logic import _tick_yield_renewal
    _tick_yield_renewal(state)  # should not raise
