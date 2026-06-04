import pytest
from uuid import UUID, uuid4
from unittest.mock import MagicMock

from core.universe_core import Directive, Pop, Faction
from core.agent_core import DirectiveFact, KnowledgeBase


def test_directive_required_skill_default_none():
    d = Directive(directive_type="commerce", label="test")
    assert d.required_skill is None


def test_directive_required_skill_set():
    d = Directive(directive_type="commerce", label="test", required_skill="skill:trade")
    assert d.required_skill == "skill:trade"


def test_pop_faction_ids_default_empty():
    assert "faction_ids" in Pop.model_fields


def test_directive_fact_source_faction_id_default_none():
    df = DirectiveFact(
        directive_id="abc",
        directive_type="commerce",
        satisfying_action="sell",
        target_pop_location_id="",
    )
    assert df.source_faction_id is None


def test_faction_defaults():
    f = Faction(name="Test Guild")
    assert f.member_pop_ids == []
    assert f.active_directives == []
    assert f.civilization_id is None
    assert f.visibility == 1.0
    assert f.pinned is False


def test_faction_with_members_and_directives():
    pop_id = uuid4()
    d = Directive(directive_type="commerce", required_skill="skill:trade")
    f = Faction(
        name="Trade Guild",
        member_pop_ids=[pop_id],
        active_directives=[d],
    )
    assert pop_id in f.member_pop_ids
    assert f.active_directives[0].required_skill == "skill:trade"
