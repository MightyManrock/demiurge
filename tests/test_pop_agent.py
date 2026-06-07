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
