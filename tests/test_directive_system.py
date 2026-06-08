"""Tests for the Directive model and KnowledgeBase directive helpers."""
from unittest.mock import MagicMock
from uuid import uuid4

from core.agent_core import (
    KnowledgeBase,
    DirectiveFact,
    LocationFact,
)
from core.universe_core import Directive


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


# ── compute_world_wealth ─────────────────────────────────────────────────────

def test_compute_world_wealth():
    from logic.sim_utils import compute_world_wealth
    from core.universe_core import PopLocation

    child_a = MagicMock(spec=PopLocation)
    child_a.wealth = 0.4
    child_b = MagicMock(spec=PopLocation)
    child_b.wealth = 0.6
    non_pop = MagicMock()

    world = MagicMock()
    world.child_ids = ["a", "b", "c"]

    state = MagicMock()
    state.locations = {"world-1": world, "a": child_a, "b": child_b, "c": non_pop}

    result = compute_world_wealth("world-1", state)
    assert result == pytest.approx(1.0)


def test_compute_world_wealth_missing_world():
    from logic.sim_utils import compute_world_wealth

    state = MagicMock()
    state.locations = {}
    assert compute_world_wealth("nonexistent", state) == 0.0


import pytest
