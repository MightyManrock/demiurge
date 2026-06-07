import pytest
from unittest.mock import MagicMock
from uuid import UUID, uuid4
from core.agent_core import PopNeed, PopAgentState
from core.universe_core import Directive, Pop, PopLocation


def test_pop_need_defaults():
    n = PopNeed(name="sustenance")
    assert n.satisfaction == 1.0
    assert n.decay_rate == 0.02
    assert n.pressing_threshold == 0.55
    assert n.urgent_threshold == 0.20
    assert n.satiation_hold == 0


def test_pop_need_is_pressing():
    n = PopNeed(name="sustenance", satisfaction=0.4, pressing_threshold=0.55)
    assert n.is_pressing


def test_pop_need_not_pressing():
    n = PopNeed(name="sustenance", satisfaction=0.8, pressing_threshold=0.55)
    assert not n.is_pressing


def test_pop_need_is_urgent():
    n = PopNeed(name="sustenance", satisfaction=0.10, urgent_threshold=0.20)
    assert n.is_urgent


def test_pop_need_not_urgent():
    n = PopNeed(name="sustenance", satisfaction=0.50, urgent_threshold=0.20)
    assert not n.is_urgent


def test_pop_agent_state_defaults():
    s = PopAgentState()
    assert s.needs == []
    assert s.action_priorities == {}
    assert s.fatigue == 0.0
    assert s.pending_migration_dest is None
    assert s.migration_ticks_remaining == 0


def test_pop_agent_state_get_need():
    n = PopNeed(name="sustenance", satisfaction=0.3)
    s = PopAgentState(needs=[n])
    assert s.get_need("sustenance") is n
    assert s.get_need("shelter") is None


def test_directive_new_fields_defaults():
    d = Directive()
    assert d.action_weight_modifiers == {}
    assert d.slot_modifier == 0


def test_directive_serializes_new_fields():
    d = Directive(
        action_weight_modifiers={"fortify": 0.5, "revel": -0.2},
        slot_modifier=1,
    )
    data = d.model_dump()
    assert data["action_weight_modifiers"] == {"fortify": 0.5, "revel": -0.2}
    assert data["slot_modifier"] == 1


def test_directive_roundtrips_via_model_validate():
    d = Directive(action_weight_modifiers={"build": 0.3}, slot_modifier=-1)
    restored = Directive.model_validate(d.model_dump())
    assert restored.action_weight_modifiers == {"build": 0.3}
    assert restored.slot_modifier == -1


def test_pop_pop_state_default_none():
    from core.agent_core import PopAgentState  # noqa: F401 — triggers forward-ref resolution
    Pop.model_rebuild()
    p = Pop(current_location=uuid4())
    assert p.pop_state is None


def test_pop_location_resource_stockpile_default():
    loc = PopLocation(id=uuid4(), name="test", location_type="city")
    assert loc.resource_stockpile == {}


def test_pop_agent_state_roundtrips_json():
    """PopAgentState survives model_dump_json → model_validate_json."""
    import json
    from core.agent_core import PopNeed, PopAgentState
    ps = PopAgentState(
        needs=[PopNeed(name="sustenance", satisfaction=0.6)],
        action_priorities={"forage": 0.4, "commune": 0.6},
        fatigue=0.3,
    )
    raw = ps.model_dump_json()
    restored = PopAgentState.model_validate_json(raw)
    assert len(restored.needs) == 1
    assert restored.needs[0].name == "sustenance"
    assert abs(restored.needs[0].satisfaction - 0.6) < 1e-6
    assert abs(restored.action_priorities["forage"] - 0.4) < 1e-6
    assert abs(restored.fatigue - 0.3) < 1e-6


def test_pop_agent_state_loads_from_none():
    """None pop_state column → None (not error)."""
    from utilities.scenario_loader import _load_pop_agent_state
    assert _load_pop_agent_state(None) is None
    assert _load_pop_agent_state("") is None


from logic.needs_config import (
    initialize_pop_state,
    compute_pop_need_profile,
    POP_CANONICAL_NEEDS,
    POP_NEED_DEFAULTS,
    POP_NEED_SUSTENANCE,
    POP_NEED_SHELTER,
    POP_NEED_WANDERLUST,
)


def _make_pop(culture_tags: dict) -> MagicMock:
    pop = MagicMock()
    pop.culture_tags = culture_tags
    return pop


def test_pop_all_canonical_needs_present():
    needs = compute_pop_need_profile({})
    names = {n.name for n in needs}
    assert names == set(POP_CANONICAL_NEEDS)


def test_pop_need_defaults_with_no_traits():
    needs = compute_pop_need_profile({})
    by_name = {n.name: n for n in needs}
    for need_name, defaults in POP_NEED_DEFAULTS.items():
        n = by_name[need_name]
        assert abs(n.decay_rate - defaults["decay_rate"]) < 1e-6
        assert abs(n.pressing_threshold - defaults["pressing_threshold"]) < 1e-6
        assert abs(n.urgent_threshold - defaults["urgent_threshold"]) < 1e-6


def test_sedentism_amplifies_shelter_need():
    needs = compute_pop_need_profile({"values:sedentism": 0.8})
    by_name = {n.name: n for n in needs}
    shelter = by_name[POP_NEED_SHELTER]
    assert shelter.decay_rate > POP_NEED_DEFAULTS[POP_NEED_SHELTER]["decay_rate"]


def test_sedentism_suppresses_wanderlust():
    needs = compute_pop_need_profile({"values:sedentism": 0.8})
    by_name = {n.name: n for n in needs}
    wanderlust = by_name[POP_NEED_WANDERLUST]
    assert wanderlust.decay_rate < POP_NEED_DEFAULTS[POP_NEED_WANDERLUST]["decay_rate"]


def test_anti_sedentism_suppresses_shelter():
    needs = compute_pop_need_profile({"values:sedentism": -0.8})
    by_name = {n.name: n for n in needs}
    shelter = by_name[POP_NEED_SHELTER]
    assert shelter.decay_rate < POP_NEED_DEFAULTS[POP_NEED_SHELTER]["decay_rate"]


def test_initialize_pop_state_returns_pop_agent_state():
    from core.agent_core import PopAgentState
    pop = _make_pop({"values:sedentism": 0.5})
    state = initialize_pop_state(pop)
    assert isinstance(state, PopAgentState)
    assert len(state.needs) == len(POP_CANONICAL_NEEDS)
    assert state.fatigue == 0.0


from logic.pop_agent_logic import (
    compute_pop_priorities,
    compute_active_slots,
    _pop_need_urgency,
    _pop_competency_modifier,
)
from core.universe_core import SocialClass
import math


def _make_pop_with_state(needs, social_class=SocialClass.COMMON, size=3.0, directives=None):
    pop = MagicMock()
    pop.pop_state = PopAgentState(needs=needs)
    pop.social_class = social_class
    pop.stratum = social_class.value
    pop.wild_stratum = None
    pop.size_fractional = size
    pop.active_directives = directives or []
    pop.faction_ids = []
    return pop


def test_urgency_zero_when_satisfied():
    n = PopNeed(name="sustenance", satisfaction=1.0, pressing_threshold=0.55)
    assert _pop_need_urgency(n) == 0.0


def test_urgency_zero_when_satiation_hold():
    n = PopNeed(name="sustenance", satisfaction=0.3, pressing_threshold=0.55, satiation_hold=3)
    assert _pop_need_urgency(n) == 0.0


def test_urgency_positive_when_pressing():
    n = PopNeed(name="sustenance", satisfaction=0.3, pressing_threshold=0.55, urgent_threshold=0.20)
    u = _pop_need_urgency(n)
    assert 0 < u <= 1.0


def test_urgency_above_one_when_urgent():
    n = PopNeed(name="sustenance", satisfaction=0.05, pressing_threshold=0.55, urgent_threshold=0.20)
    assert _pop_need_urgency(n) > 1.0


def test_competency_warrior_fortify():
    pop = _make_pop_with_state([], social_class=SocialClass.WARRIOR)
    assert _pop_competency_modifier(pop, "fortify") > 1.0


def test_competency_common_forage():
    pop = _make_pop_with_state([], social_class=SocialClass.COMMON)
    assert _pop_competency_modifier(pop, "forage") > 1.0


def test_competency_default_one():
    pop = _make_pop_with_state([], social_class=SocialClass.COMMON)
    assert _pop_competency_modifier(pop, "build") == 1.0


def test_competency_wild_with_wild_stratum_forage():
    """Pops with SocialClass.WILD + a wild_stratum still get wild competency bonuses."""
    from core.universe_core import WildStratum
    pop = _make_pop_with_state([], social_class=SocialClass.WILD)
    pop.wild_stratum = WildStratum.APEX
    # When wild_stratum is set, stratum property returns its value ("apex")
    # which isn't in _COMPETENCY, so we should fall back to "wild" bonuses.
    pop.stratum = WildStratum.APEX.value  # Simulate what Pop.stratum property does
    assert _pop_competency_modifier(pop, "forage") > 1.0
    assert _pop_competency_modifier(pop, "forage") == 1.5


def test_priorities_sum_to_one():
    needs = [
        PopNeed(name="sustenance", satisfaction=0.3, pressing_threshold=0.55, urgent_threshold=0.20),
        PopNeed(name="safety", satisfaction=0.8),
        PopNeed(name="cohesion", satisfaction=0.8),
        PopNeed(name="purpose", satisfaction=0.8),
        PopNeed(name="shelter", satisfaction=0.8),
        PopNeed(name="wanderlust", satisfaction=0.8),
    ]
    pop = _make_pop_with_state(needs)
    priorities = compute_pop_priorities(pop, {})
    assert abs(sum(priorities.values()) - 1.0) < 1e-6


def test_stubs_have_zero_weight():
    needs = [PopNeed(name=n, satisfaction=0.3) for n in
             ["sustenance", "safety", "cohesion", "purpose", "shelter", "wanderlust"]]
    pop = _make_pop_with_state(needs)
    priorities = compute_pop_priorities(pop, {})
    assert priorities["raid"] == 0.0
    assert priorities["fight"] == 0.0
    assert priorities["rout"] == 0.0


def test_directive_boosts_action():
    needs = [PopNeed(name="sustenance", satisfaction=0.5, pressing_threshold=0.55),
             PopNeed(name="safety", satisfaction=0.9),
             PopNeed(name="cohesion", satisfaction=0.9),
             PopNeed(name="purpose", satisfaction=0.9),
             PopNeed(name="shelter", satisfaction=0.9),
             PopNeed(name="wanderlust", satisfaction=0.9)]
    d = Directive(action_weight_modifiers={"fortify": 5.0})
    pop_with = _make_pop_with_state(needs, directives=[d])
    pop_without = _make_pop_with_state(needs, directives=[])
    p_with = compute_pop_priorities(pop_with, {})
    p_without = compute_pop_priorities(pop_without, {})
    assert p_with["fortify"] > p_without["fortify"]


def test_active_slots_floor_two():
    pop = _make_pop_with_state([], size=1.0)
    assert compute_active_slots(pop, {}) == 2


def test_active_slots_scales_with_size():
    pop = _make_pop_with_state([], size=5.0)
    assert compute_active_slots(pop, {}) == 5


def test_slot_modifier_blocked_when_fatigued():
    pop = _make_pop_with_state([], size=3.0, directives=[Directive(slot_modifier=1)])
    pop.pop_state.fatigue = 1.0
    assert compute_active_slots(pop, {}) == 3


def test_slot_modifier_applied_when_not_fatigued():
    pop = _make_pop_with_state([], size=3.0, directives=[Directive(slot_modifier=1)])
    pop.pop_state.fatigue = 0.0
    assert compute_active_slots(pop, {}) == 4


from logic.pop_agent_logic import resolve_pop_actions
from core.agent_core import CollectibleResource
from uuid import uuid4


def _make_pop_loc(resource_type=None, max_yield=2.0):
    loc = PopLocation(id=uuid4(), name="Test Location", location_type="city")
    if resource_type:
        loc.collectible_resources = [CollectibleResource(
            resource_type=resource_type, max_yield=max_yield
        )]
    return loc


def _make_pop_for_resolution(needs, social_class=SocialClass.COMMON, size=3.0):
    return _make_pop_with_state(needs, social_class=social_class, size=size)


def _full_priorities(dominant: str) -> dict:
    """Return a priorities dict with dominant action at 1.0, all others 0.0."""
    from logic.pop_agent_logic import ALL_ACTIONS
    return {a: (1.0 if a == dominant else 0.0) for a in ALL_ACTIONS}


def test_forage_deposits_to_stockpile():
    needs = [PopNeed(name="sustenance", satisfaction=0.3, pressing_threshold=0.55, urgent_threshold=0.20)]
    pop = _make_pop_for_resolution(needs)
    loc = _make_pop_loc()
    resolve_pop_actions(pop, loc, _full_priorities("forage"), n_slots=1, factions={}, current_tick=1)
    assert loc.resource_stockpile.get("food_flora", 0.0) > 0.0


def test_collect_uses_collectible_resource():
    needs = [PopNeed(name="sustenance", satisfaction=0.3, pressing_threshold=0.55, urgent_threshold=0.20)]
    pop = _make_pop_for_resolution(needs)
    loc = _make_pop_loc(resource_type="amber_resin", max_yield=3.0)
    resolve_pop_actions(pop, loc, _full_priorities("collect"), n_slots=1, factions={}, current_tick=1)
    assert loc.resource_stockpile.get("amber_resin", 0.0) > 0.0


def test_commune_fills_cohesion_need():
    needs = [
        PopNeed(name="sustenance", satisfaction=1.0),
        PopNeed(name="cohesion", satisfaction=0.2, pressing_threshold=0.45, urgent_threshold=0.20),
        PopNeed(name="safety", satisfaction=1.0),
        PopNeed(name="purpose", satisfaction=1.0),
        PopNeed(name="shelter", satisfaction=1.0),
        PopNeed(name="wanderlust", satisfaction=1.0),
    ]
    pop = _make_pop_for_resolution(needs)
    loc = _make_pop_loc()
    initial = pop.pop_state.get_need("cohesion").satisfaction
    resolve_pop_actions(pop, loc, _full_priorities("commune"), n_slots=1, factions={}, current_tick=1)
    assert pop.pop_state.get_need("cohesion").satisfaction > initial


def test_sustenance_filled_from_stockpile():
    needs = [PopNeed(name="sustenance", satisfaction=0.3, pressing_threshold=0.55, urgent_threshold=0.20),
             PopNeed(name="safety", satisfaction=1.0),
             PopNeed(name="cohesion", satisfaction=1.0),
             PopNeed(name="purpose", satisfaction=1.0),
             PopNeed(name="shelter", satisfaction=1.0),
             PopNeed(name="wanderlust", satisfaction=1.0)]
    pop = _make_pop_for_resolution(needs, size=3.0)
    loc = _make_pop_loc()
    loc.resource_stockpile["food_flora"] = 10.0
    initial = pop.pop_state.get_need("sustenance").satisfaction
    resolve_pop_actions(pop, loc, _full_priorities("commune"), n_slots=1, factions={}, current_tick=1)
    assert pop.pop_state.get_need("sustenance").satisfaction > initial


def test_empty_stockpile_leaves_sustenance_unmet():
    needs = [PopNeed(name="sustenance", satisfaction=0.3, pressing_threshold=0.55, urgent_threshold=0.20),
             PopNeed(name="safety", satisfaction=1.0),
             PopNeed(name="cohesion", satisfaction=1.0),
             PopNeed(name="purpose", satisfaction=1.0),
             PopNeed(name="shelter", satisfaction=1.0),
             PopNeed(name="wanderlust", satisfaction=1.0)]
    pop = _make_pop_for_resolution(needs, size=3.0)
    loc = _make_pop_loc()
    initial = pop.pop_state.get_need("sustenance").satisfaction
    narratives = resolve_pop_actions(pop, loc, _full_priorities("commune"), n_slots=1, factions={}, current_tick=1)
    assert pop.pop_state.get_need("sustenance").satisfaction == initial
    assert any("has no food" in n for n in narratives)


def test_fortify_reduces_location_danger():
    needs = [PopNeed(name="safety", satisfaction=0.2, pressing_threshold=0.50, urgent_threshold=0.20),
             PopNeed(name="sustenance", satisfaction=1.0),
             PopNeed(name="cohesion", satisfaction=1.0),
             PopNeed(name="purpose", satisfaction=1.0),
             PopNeed(name="shelter", satisfaction=1.0),
             PopNeed(name="wanderlust", satisfaction=1.0)]
    pop = _make_pop_for_resolution(needs, social_class=SocialClass.WARRIOR, size=3.0)
    loc = _make_pop_loc()
    loc.danger = 0.5
    resolve_pop_actions(pop, loc, _full_priorities("fortify"), n_slots=1, factions={}, current_tick=1)
    assert loc.danger < 0.5


def test_migrate_partially_fills_wanderlust():
    needs = [PopNeed(name="wanderlust", satisfaction=0.2, pressing_threshold=0.40, urgent_threshold=0.18),
             PopNeed(name="sustenance", satisfaction=1.0),
             PopNeed(name="safety", satisfaction=1.0),
             PopNeed(name="cohesion", satisfaction=1.0),
             PopNeed(name="purpose", satisfaction=1.0),
             PopNeed(name="shelter", satisfaction=1.0)]
    pop = _make_pop_for_resolution(needs)
    loc = _make_pop_loc()
    initial = pop.pop_state.get_need("wanderlust").satisfaction
    resolve_pop_actions(pop, loc, _full_priorities("migrate"), n_slots=1, factions={}, current_tick=1)
    assert pop.pop_state.get_need("wanderlust").satisfaction > initial
