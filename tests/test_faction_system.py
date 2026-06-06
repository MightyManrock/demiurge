import pytest
from uuid import UUID, uuid4
from unittest.mock import MagicMock

from core.universe_core import Directive, Pop, Faction
from core.agent_core import DirectiveFact, KnowledgeBase
from logic.tick_logic import _sync_faction_directives


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


def _make_state(faction=None, pop=None):
    state = MagicMock()
    state.factions = {str(faction.id): faction} if faction else {}
    state.pops = {str(pop.id): pop} if pop else {}
    return state


def _make_mortal(pop_id=None, skill_tags=None, facts=None, faction_ids=None):
    mortal = MagicMock()
    mortal.pop_id = pop_id
    mortal.faction_ids = faction_ids or []
    mortal.skill_tags = skill_tags or {}
    kb = KnowledgeBase()
    if facts:
        kb.facts.extend(facts)
    mortal.knowledge_base = kb
    return mortal


def test_sync_adds_directive_fact_for_member_with_required_skill():
    directive = Directive(directive_type="commerce", required_skill="skill:trade")
    faction = Faction(name="Guild", active_directives=[directive])
    mortal = _make_mortal(skill_tags={"skill:trade": 0.8}, faction_ids=[faction.id])
    state = _make_state(faction=faction)

    _sync_faction_directives(mortal, state, tick=1)

    df_facts = mortal.knowledge_base.directive_facts()
    assert len(df_facts) == 1
    assert df_facts[0].directive_type == "commerce"
    assert df_facts[0].satisfying_action == "sell"
    assert df_facts[0].source_faction_id == str(faction.id)


def test_sync_skips_directive_when_required_skill_absent():
    pop_id = uuid4()
    directive = Directive(directive_type="commerce", required_skill="skill:trade")
    faction = Faction(name="Guild", member_pop_ids=[pop_id], active_directives=[directive])
    pop = MagicMock()
    pop.id = pop_id
    mortal = _make_mortal(pop_id=pop_id, skill_tags={"skill:craft": 0.9})
    state = _make_state(faction=faction, pop=pop)

    _sync_faction_directives(mortal, state, tick=1)

    assert mortal.knowledge_base.directive_facts() == []


def test_sync_skips_directive_when_not_member():
    directive = Directive(directive_type="commerce")
    faction = Faction(name="Guild", active_directives=[directive])
    mortal = _make_mortal(skill_tags={"skill:trade": 0.8})  # faction_ids=[] by default
    state = _make_state(faction=faction)

    _sync_faction_directives(mortal, state, tick=1)

    assert mortal.knowledge_base.directive_facts() == []


def test_sync_adds_directive_when_no_required_skill():
    """Faction directive with no skill gate applies to all members."""
    directive = Directive(directive_type="commerce", required_skill=None)
    faction = Faction(name="Guild", active_directives=[directive])
    mortal = _make_mortal(skill_tags={}, faction_ids=[faction.id])
    state = _make_state(faction=faction)

    _sync_faction_directives(mortal, state, tick=1)

    assert len(mortal.knowledge_base.directive_facts()) == 1


def test_sync_removes_stale_faction_facts_on_each_call():
    """Stale Faction-sourced DirectiveFacts are cleared and rebuilt each call."""
    pop_id = uuid4()
    old_faction_id = str(uuid4())
    stale = DirectiveFact(
        directive_id=str(uuid4()),
        directive_type="commerce",
        satisfying_action="sell",
        target_pop_location_id="",
        source_faction_id=old_faction_id,
    )
    mortal = _make_mortal(pop_id=pop_id, facts=[stale])
    state = _make_state()
    state.pops = {}

    _sync_faction_directives(mortal, state, tick=5)

    assert mortal.knowledge_base.directive_facts() == []


def test_sync_preserves_non_faction_directive_facts():
    """Manually-seeded DirectiveFacts without source_faction_id are not touched."""
    pop_id = uuid4()
    manual = DirectiveFact(
        directive_id=str(uuid4()),
        directive_type="commerce",
        satisfying_action="sell",
        target_pop_location_id="",
        source_faction_id=None,
    )
    mortal = _make_mortal(pop_id=pop_id, facts=[manual])
    state = _make_state()
    state.pops = {}

    _sync_faction_directives(mortal, state, tick=1)

    assert len(mortal.knowledge_base.directive_facts()) == 1
    assert mortal.knowledge_base.directive_facts()[0].source_faction_id is None
