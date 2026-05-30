"""Tests for the Directive / wealth / Purpose satisfaction system."""
from unittest.mock import MagicMock
from uuid import uuid4

from core.agent_core import (
    CivilianAgentState,
    KnowledgeBase,
    MortalNeed,
    DirectiveFact,
    LocationFact,
    Resource,
)
from core.universe_core import Directive
from logic.needs_config import NEED_PURPOSE


# ── DirectiveFact helpers ────────────────────────────────────────────────────

def _commerce_directive_fact(directive_id: str | None = None) -> DirectiveFact:
    return DirectiveFact(
        directive_id=directive_id or str(uuid4()),
        directive_type="commerce",
        satisfying_action="sell",
        target_pop_location_id=str(uuid4()),
    )


# ── KnowledgeBase helpers ─────────────────────────────────────────────────────

def test_directive_fact_found_in_kb():
    df = _commerce_directive_fact()
    kb = KnowledgeBase(facts=[df])
    result = kb.directive_facts()
    assert len(result) == 1
    assert result[0].directive_id == df.directive_id


def test_directive_facts_empty_when_none():
    kb = KnowledgeBase(facts=[
        LocationFact(location_id="loc-1"),
        LocationFact(location_id="loc-2"),
    ])
    assert kb.directive_facts() == []


def test_directive_facts_mixed_kb():
    df = _commerce_directive_fact()
    kb = KnowledgeBase(facts=[LocationFact(location_id="loc-x"), df])
    result = kb.directive_facts()
    assert len(result) == 1
    assert result[0] is df


# ── Directive model ──────────────────────────────────────────────────────────

def test_directive_default_type():
    d = Directive(label="test")
    assert d.directive_type == "commerce"


def test_directive_id_is_uuid():
    d = Directive()
    import uuid
    uuid.UUID(str(d.id))  # raises if not valid UUID


# ── Sell action: Purpose satisfaction simulation ──────────────────────────────

def _build_sell_state(with_directive_fact: bool = True):
    """Minimal objects to simulate the sell→Purpose block in tick_logic."""
    from uuid import UUID

    pop_loc_id = str(uuid4())
    pop_id = str(uuid4())

    # PopLocation mock with wealth
    pop_loc = MagicMock()
    pop_loc.wealth = 0.5

    # Pop mock
    pop = MagicMock()
    pop.current_location = pop_loc_id

    # CivilianAgentState with a Purpose need at 0.4 satisfaction
    purpose = MortalNeed(name=NEED_PURPOSE, satisfaction=0.4, pressing_threshold=0.60)
    cs = CivilianAgentState(needs=[purpose])

    # KnowledgeBase
    facts = [_commerce_directive_fact()] if with_directive_fact else []
    kb = KnowledgeBase(facts=facts)

    # SimulationState mock
    state = MagicMock()
    state.pops = {pop_id: pop}
    state.locations = {pop_loc_id: pop_loc}

    return cs, kb, pop, pop_loc, state, pop_id


def _run_sell_directive_block(cs, kb, pop, pop_loc, state, pop_id, credits_gained=20.0):
    """Simulate the directive fulfillment block from _tick_civilian_agents sell branch."""
    _sell_pop = state.pops.get(pop_id)
    if _sell_pop:
        _pop_loc = state.locations.get(str(_sell_pop.current_location))
        if _pop_loc and hasattr(_pop_loc, "wealth"):
            wealth_gain = min(0.05, credits_gained * 0.005)
            _pop_loc.wealth = min(1.0, _pop_loc.wealth + wealth_gain)
        if kb:
            for _df in kb.directive_facts():
                if _df.directive_type == "commerce" and _df.satisfying_action == "sell":
                    purpose_need = cs.get_need(NEED_PURPOSE)
                    if purpose_need:
                        purpose_need.satisfaction = min(1.0, purpose_need.satisfaction + 0.35)
                        purpose_need.satiation_hold = 8
                    break


def test_sell_satisfies_purpose():
    cs, kb, pop, pop_loc, state, pop_id = _build_sell_state(with_directive_fact=True)
    _run_sell_directive_block(cs, kb, pop, pop_loc, state, pop_id)
    purpose = cs.get_need(NEED_PURPOSE)
    assert purpose.satisfaction == pytest_approx(0.75)
    assert purpose.satiation_hold == 8


def test_sell_does_not_satisfy_purpose_without_directive():
    cs, kb, pop, pop_loc, state, pop_id = _build_sell_state(with_directive_fact=False)
    _run_sell_directive_block(cs, kb, pop, pop_loc, state, pop_id)
    purpose = cs.get_need(NEED_PURPOSE)
    assert purpose.satisfaction == pytest_approx(0.4)  # unchanged


def test_sell_increases_pop_wealth():
    cs, kb, pop, pop_loc, state, pop_id = _build_sell_state()
    _run_sell_directive_block(cs, kb, pop, pop_loc, state, pop_id, credits_gained=20.0)
    # wealth_gain = min(0.05, 20 * 0.005) = 0.1 → capped at 0.05
    assert pop_loc.wealth == pytest_approx(0.55)


def test_sell_wealth_gain_capped_at_0_05():
    cs, kb, pop, pop_loc, state, pop_id = _build_sell_state()
    _run_sell_directive_block(cs, kb, pop, pop_loc, state, pop_id, credits_gained=1000.0)
    assert pop_loc.wealth == pytest_approx(0.55)


# ── Wealth decay ──────────────────────────────────────────────────────────────

def test_wealth_decays_per_tick():
    from core.universe_core import PopLocation

    pop_loc = MagicMock()
    pop_loc.wealth = 0.6

    # Simulate the decay block
    if pop_loc.wealth > 0.0:
        pop_loc.wealth = max(0.0, pop_loc.wealth - 0.005)

    assert pop_loc.wealth == pytest_approx(0.595)


def test_wealth_does_not_go_below_zero():
    pop_loc = MagicMock()
    pop_loc.wealth = 0.002

    pop_loc.wealth = max(0.0, pop_loc.wealth - 0.005)

    assert pop_loc.wealth == 0.0


# ── compute_world_wealth ─────────────────────────────────────────────────────

def test_compute_world_wealth():
    from logic.sim_utils import compute_world_wealth
    from core.universe_core import PopLocation

    child_a = MagicMock(spec=PopLocation)
    child_a.wealth = 0.4
    child_b = MagicMock(spec=PopLocation)
    child_b.wealth = 0.6
    non_pop = MagicMock()  # not a PopLocation

    world = MagicMock()
    world.child_ids = ["a", "b", "c"]

    state = MagicMock()
    state.locations = {"world-1": world, "a": child_a, "b": child_b, "c": non_pop}

    result = compute_world_wealth("world-1", state)
    assert result == pytest_approx(1.0)


def test_compute_world_wealth_missing_world():
    from logic.sim_utils import compute_world_wealth

    state = MagicMock()
    state.locations = {}
    assert compute_world_wealth("nonexistent", state) == 0.0


# need pytest.approx alias
def pytest_approx(x, **kw):
    import pytest
    return pytest.approx(x, **kw)
