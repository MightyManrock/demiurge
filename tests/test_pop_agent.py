import pytest
from uuid import UUID
from core.agent_core import PopNeed, PopAgentState


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
