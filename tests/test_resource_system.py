import json
import pytest
from uuid import uuid4
from unittest.mock import MagicMock
from core.agent_core import CollectibleResource, Resource, PopAgentState, PopNeed, MortalInventory, MortalAgentState, MortalNeed, StockpileFact, KnowledgeBase
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
from logic.tick_logic import _MORTAL_FOOD_CONSUME_RATE


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
    pop.occupation = "producer"
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


# ── Task 6: MortalInventory ───────────────────────────────────────────────────

def test_mortal_inventory_empty_by_default():
    inv = MortalInventory()
    assert inv.items == []

def test_mortal_inventory_get_resource_found():
    inv = MortalInventory(items=[Resource(resource_type="food_flora", quantity=3.0)])
    res = inv.get_resource("food_flora")
    assert res is not None and res.quantity == 3.0

def test_mortal_inventory_get_resource_not_found():
    assert MortalInventory().get_resource("food_flora") is None

def test_mortal_inventory_add_resource_new():
    inv = MortalInventory()
    added = inv.add_resource("food_flora", 2.0, ["basis:carbon"])
    assert added == 2.0 and len(inv.items) == 1

def test_mortal_inventory_add_resource_stacks():
    inv = MortalInventory(items=[Resource(resource_type="food_flora", quantity=1.0)])
    inv.add_resource("food_flora", 2.0)
    assert inv.get_resource("food_flora").quantity == 3.0

def test_mortal_agent_state_has_mortal_inventory():
    cs = MortalAgentState()
    assert hasattr(cs, "mortal_inventory")
    assert isinstance(cs.mortal_inventory, MortalInventory)

def test_mortal_agent_state_backward_compat():
    import json
    old_json = json.dumps({
        "needs": [],
        "inventory": [{"resource_type": "food_flora", "quantity": 5.0,
                        "biochem_tags": ["basis:carbon"]}]
    })
    cs = MortalAgentState.model_validate_json(old_json)
    assert cs.mortal_inventory.get_resource("food_flora").quantity == 5.0


# ── entitlement_resolver ──────────────────────────────────────────────────────

def test_entitlement_home_pop_full_factor():
    pop_id = uuid4()
    pop = MagicMock()
    pop.linked_pop_ids = {}
    state = MagicMock()
    state.pops = {str(pop_id): pop}
    mortal = MagicMock()
    mortal.pop_id = pop_id
    mortal.pop_milieu = pop_id
    from logic.tick_logic import entitlement_resolver
    assert entitlement_resolver(mortal, state) == [(pop, 1.0)]

def test_entitlement_linked_pop_scaled():
    origin_id = uuid4()
    linked_id = uuid4()
    origin_pop = MagicMock()
    origin_pop.linked_pop_ids = {str(linked_id): 0.6}
    linked_pop = MagicMock()
    state = MagicMock()
    state.pops = {str(origin_id): origin_pop, str(linked_id): linked_pop}
    mortal = MagicMock()
    mortal.pop_id = origin_id
    mortal.pop_milieu = linked_id
    from logic.tick_logic import entitlement_resolver
    assert entitlement_resolver(mortal, state) == [(linked_pop, 0.6)]

def test_entitlement_unrelated_pop_empty():
    origin_id = uuid4()
    other_id = uuid4()
    origin_pop = MagicMock()
    origin_pop.linked_pop_ids = {}
    state = MagicMock()
    state.pops = {str(origin_id): origin_pop, str(other_id): MagicMock()}
    mortal = MagicMock()
    mortal.pop_id = origin_id
    mortal.pop_milieu = other_id
    from logic.tick_logic import entitlement_resolver
    assert entitlement_resolver(mortal, state) == []

def test_entitlement_no_milieu_empty():
    mortal = MagicMock()
    mortal.pop_milieu = None
    from logic.tick_logic import entitlement_resolver
    assert entitlement_resolver(mortal, MagicMock()) == []


# ── Task 7: Three-source mortal passive sustenance ────────────────────────────

def _make_mortal_with_needs(**sats):
    needs = []
    defaults = {"nourishment": 1.0, "hydration": 1.0, "safety": 1.0,
                "belonging": 1.0, "status": 1.0, "purpose": 1.0, "leisure": 1.0}
    defaults.update(sats)
    for name, sat in defaults.items():
        needs.append(MortalNeed(name=name, satisfaction=sat,
                                 decay_rate=0.02, pressing_threshold=0.55,
                                 urgent_threshold=0.20))
    return MortalAgentState(needs=needs)


def _make_state_with_entitled_pop(pop_id, stockpile: dict):
    pop = MagicMock()
    pop.linked_pop_ids = {}
    loc = PopLocation(id=pop_id, name="Plains", location_type="city", parent_id=uuid4(),
                      resource_stockpile=dict(stockpile))
    state = MagicMock()
    state.pops = {str(pop_id): pop}
    state.locations = {str(pop_id): loc}
    return state, loc


def test_mortal_draws_nourishment_from_entitled_stockpile():
    pop_id = uuid4()
    state, loc = _make_state_with_entitled_pop(pop_id, {"food_flora": 10.0})
    cs = _make_mortal_with_needs(nourishment=0.3)
    mortal = MagicMock()
    mortal.mortal_state = cs
    mortal.pop_id = pop_id
    mortal.pop_milieu = pop_id

    from logic.tick_logic import _tick_mortal_passive_sustenance
    _tick_mortal_passive_sustenance(mortal, loc, state)

    assert cs.get_need("nourishment").satisfaction > 0.3
    assert loc.resource_stockpile["food_flora"] < 10.0

def test_mortal_stockpile_draw_scaled_by_link_factor():
    origin_id = uuid4()
    linked_id = uuid4()
    origin_pop = MagicMock()
    origin_pop.linked_pop_ids = {str(linked_id): 0.5}
    linked_pop = MagicMock()
    loc = PopLocation(id=linked_id, name="Plains", location_type="city", parent_id=uuid4(),
                      resource_stockpile={"food_flora": 10.0})
    state = MagicMock()
    state.pops = {str(origin_id): origin_pop, str(linked_id): linked_pop}
    state.locations = {str(linked_id): loc}
    cs = _make_mortal_with_needs(nourishment=0.3)
    mortal = MagicMock()
    mortal.mortal_state = cs
    mortal.pop_id = origin_id
    mortal.pop_milieu = linked_id

    from logic.tick_logic import _tick_mortal_passive_sustenance
    _tick_mortal_passive_sustenance(mortal, loc, state)

    drawn = 10.0 - loc.resource_stockpile["food_flora"]
    assert 0 < drawn <= _MORTAL_FOOD_CONSUME_RATE * 0.5 + 1e-9

def test_mortal_falls_back_to_inventory_when_stockpile_empty():
    pop_id = uuid4()
    state, loc = _make_state_with_entitled_pop(pop_id, {})
    cs = _make_mortal_with_needs(nourishment=0.3)
    food = Resource(resource_type="food_flora", biochem_tags=["basis:carbon"], quantity=5.0)
    cs.mortal_inventory.items.append(food)
    mortal = MagicMock()
    mortal.mortal_state = cs
    mortal.pop_id = pop_id
    mortal.pop_milieu = pop_id

    from logic.tick_logic import _tick_mortal_passive_sustenance
    _tick_mortal_passive_sustenance(mortal, loc, state)

    assert cs.get_need("nourishment").satisfaction > 0.3
    assert food.quantity < 5.0

def test_mortal_commerce_fallback_fills_when_no_resources():
    pop_id = uuid4()
    state, loc = _make_state_with_entitled_pop(pop_id, {})
    cs = _make_mortal_with_needs(nourishment=0.3)
    mortal = MagicMock()
    mortal.mortal_state = cs
    mortal.pop_id = pop_id
    mortal.pop_milieu = pop_id

    from logic.tick_logic import _tick_mortal_passive_sustenance
    _tick_mortal_passive_sustenance(mortal, loc, state, commerce_quality=0.8)

    assert cs.get_need("nourishment").satisfaction > 0.3


# ── Task 8: Mortal forage + hunt ─────────────────────────────────────────────

from logic.mortal_agent_logic import evaluate_mortal_action


def _make_mortal_for_forage(nourishment_sat=0.3, has_forage_resource=True):
    cs = _make_mortal_with_needs(nourishment=nourishment_sat)
    mortal = MagicMock()
    mortal.mortal_state = cs
    mortal.knowledge_base = MagicMock()
    mortal.knowledge_base.facts = []
    mortal.knowledge_base.directive_facts = MagicMock(return_value=[])
    mortal.fatigue = 0.0
    mortal.pinned = False
    mortal.assets = []
    mortal.pop_milieu = None
    mortal.pop_id = uuid4()
    mortal.current_location = uuid4()
    mortal.travel_intent = None

    if has_forage_resource:
        cr = CollectibleResource(resource_type="food_flora", max_yield=10.0,
                                  action_types=["forage"], biochem_tags=["basis:carbon"])
        loc = PopLocation(id=mortal.current_location, name="Plains", location_type="city",
                          parent_id=uuid4(), collectible_resources=[cr])
    else:
        loc = PopLocation(id=mortal.current_location, name="Plains", location_type="city",
                          parent_id=uuid4(), collectible_resources=[])

    state = MagicMock()
    state.locations = {str(mortal.current_location): loc}
    state.pops = {}
    return mortal, state


def test_mortal_forage_fires_when_nourishment_pressing():
    mortal, state = _make_mortal_for_forage(nourishment_sat=0.1, has_forage_resource=True)
    action = evaluate_mortal_action(mortal, state, 1)
    assert action == "forage"

def test_mortal_forage_does_not_fire_without_matching_resource():
    mortal, state = _make_mortal_for_forage(nourishment_sat=0.1, has_forage_resource=False)
    action = evaluate_mortal_action(mortal, state, 1)
    assert action != "forage"

def test_mortal_forage_does_not_fire_when_nourishment_ok():
    mortal, state = _make_mortal_for_forage(nourishment_sat=0.9, has_forage_resource=True)
    action = evaluate_mortal_action(mortal, state, 1)
    assert action != "forage"

def test_mortal_forage_produces_resource_in_inventory():
    mortal, state = _make_mortal_for_forage(nourishment_sat=0.1, has_forage_resource=True)

    loc = list(state.locations.values())[0]
    initial_yield = loc.collectible_resources[0].current_yield

    from logic.tick_logic import _resolve_mortal_forage
    narratives = []
    _resolve_mortal_forage(mortal, loc, "forage", state, narratives)

    # Use mortal_inventory.items (not the old .inventory)
    assert any(r.resource_type == "food_flora" for r in mortal.mortal_state.mortal_inventory.items)
    assert loc.collectible_resources[0].current_yield < initial_yield

def test_mortal_hunt_fires_when_nourishment_pressing_and_hunt_resource():
    cs = _make_mortal_with_needs(nourishment=0.1)
    mortal = MagicMock()
    mortal.mortal_state = cs
    mortal.knowledge_base = MagicMock()
    mortal.knowledge_base.facts = []
    mortal.knowledge_base.directive_facts = MagicMock(return_value=[])
    mortal.fatigue = 0.0
    mortal.pinned = False
    mortal.assets = []
    mortal.pop_milieu = None
    mortal.pop_id = uuid4()
    mortal.current_location = uuid4()
    mortal.travel_intent = None

    cr = CollectibleResource(resource_type="food_fauna", max_yield=10.0,
                              action_types=["hunt"], biochem_tags=["basis:carbon"])
    loc = PopLocation(id=mortal.current_location, name="Plains", location_type="city",
                      parent_id=uuid4(), collectible_resources=[cr])
    state = MagicMock()
    state.locations = {str(mortal.current_location): loc}
    state.pops = {}

    action = evaluate_mortal_action(mortal, state, 1)
    assert action == "hunt"


# ── StockpileFact ─────────────────────────────────────────────────────────────

def test_stockpile_fact_fact_type():
    sf = StockpileFact(location_id="loc-1", quantities={"food_flora": 5.0})
    assert sf.fact_type == "stockpile"

def test_stockpile_fact_stores_quantities():
    sf = StockpileFact(location_id="loc-1", quantities={"food_flora": 5.0, "potable_water": 3.0})
    assert sf.quantities["food_flora"] == 5.0
    assert sf.quantities["potable_water"] == 3.0

def test_stockpile_fact_defaults():
    sf = StockpileFact(location_id="loc-1", quantities={})
    assert sf.confidence == 1.0
    assert sf.learned_at_tick == 0

def test_kb_get_stockpile_fact_found():
    kb = KnowledgeBase()
    sf = StockpileFact(location_id="loc-1", quantities={"food_flora": 5.0})
    kb.facts.append(sf)
    assert kb.get_stockpile_fact("loc-1") is sf

def test_kb_get_stockpile_fact_absent():
    kb = KnowledgeBase()
    assert kb.get_stockpile_fact("loc-1") is None

def test_kb_stockpile_facts_returns_all():
    kb = KnowledgeBase()
    sf1 = StockpileFact(location_id="loc-1", quantities={})
    sf2 = StockpileFact(location_id="loc-2", quantities={})
    kb.facts.extend([sf1, sf2])
    assert set(id(f) for f in kb.stockpile_facts()) == {id(sf1), id(sf2)}

def test_pop_agent_state_has_supply_run_skip_until():
    ps = PopAgentState()
    assert ps.supply_run_skip_until == {}

def test_supply_run_skip_until_is_mutable_per_instance():
    ps1 = PopAgentState()
    ps2 = PopAgentState()
    ps1.supply_run_skip_until["dir-1"] = 10
    assert ps2.supply_run_skip_until == {}


# ── Task 2 (KB stockpile sync) ────────────────────────────────────────────────

def test_resolve_pop_actions_syncs_stockpile_fact_to_kb():
    from uuid import uuid4
    from unittest.mock import MagicMock
    from core.agent_core import PopAgentState, ResourceStockpile
    from core.universe_core import PopLocation
    from logic.pop_agent_logic import resolve_pop_actions

    loc_id = uuid4()
    pop_loc = PopLocation(id=loc_id, name="Test", location_type="city", parent_id=uuid4())
    stockpile = ResourceStockpile(quantities={"food_flora": 7.5})
    pop_loc.stockpiles = [stockpile]

    pop = MagicMock()
    pop.id = uuid4()
    pop.faction_ids = []
    pop.active_directives = []
    pop.band_id = None
    pop.size_fractional = 1.0
    pop.occupation = "producer"
    pop.stratum = "common"
    pop.current_location = loc_id
    pop.migration_travel_location_id = None
    ps = PopAgentState()
    pop.pop_state = ps

    resolve_pop_actions(pop, pop_loc, {}, 0, factions={}, current_tick=5, colocated_pops=[pop])

    sf = ps.knowledge_base.get_stockpile_fact(str(loc_id))
    assert sf is not None
    assert sf.quantities.get("food_flora", 0.0) == pytest.approx(7.5)
    assert sf.learned_at_tick == 5

def test_resolve_pop_actions_updates_existing_stockpile_fact():
    from uuid import uuid4
    from unittest.mock import MagicMock
    from core.agent_core import PopAgentState, ResourceStockpile, StockpileFact
    from core.universe_core import PopLocation
    from logic.pop_agent_logic import resolve_pop_actions

    loc_id = uuid4()
    pop_loc = PopLocation(id=loc_id, name="Test", location_type="city", parent_id=uuid4())
    stockpile = ResourceStockpile(quantities={"food_flora": 3.0})
    pop_loc.stockpiles = [stockpile]

    pop = MagicMock()
    pop.id = uuid4()
    pop.faction_ids = []
    pop.active_directives = []
    pop.band_id = None
    pop.size_fractional = 1.0
    pop.occupation = "producer"
    pop.stratum = "common"
    pop.current_location = loc_id
    pop.migration_travel_location_id = None
    ps = PopAgentState()
    # Pre-populate a stale fact
    ps.knowledge_base.facts.append(StockpileFact(location_id=str(loc_id), quantities={"food_flora": 99.0}, learned_at_tick=0))
    pop.pop_state = ps

    resolve_pop_actions(pop, pop_loc, {}, 0, factions={}, current_tick=10, colocated_pops=[pop])

    sf = ps.knowledge_base.get_stockpile_fact(str(loc_id))
    assert sf is not None
    assert sf.quantities.get("food_flora", 0.0) == pytest.approx(3.0)
    assert sf.learned_at_tick == 10
    # Should be one fact, not two
    assert len(ps.knowledge_base.stockpile_facts()) == 1
