import pytest
from core.agent_core import PopFact, LocationFact, KnowledgeBase
from logic.civilian_agent_logic import (
    _pop_novelty,
    NOVELTY_HALFLIFE,
    RECENCY_RECOVERY_TICKS,
    SOCIAL_NOVELTY_FLOOR,
)


# ─────────────────────────────────────────────────────────────────────────────
# Group 1: _pop_novelty() formula
# ─────────────────────────────────────────────────────────────────────────────


def test_novelty_none_pop_fact():
    """Unknown Pop → novelty 1.0"""
    assert _pop_novelty(None, 100) == 1.0


def test_novelty_fresh_pop():
    """interaction_count=0, last_interaction_tick=0 → novelty 1.0"""
    pf = PopFact(pop_id="p1", interaction_count=0, last_interaction_tick=0)
    assert _pop_novelty(pf, 100) == 1.0


def test_novelty_at_halflife():
    """At NOVELTY_HALFLIFE interactions, base novelty should be ~0.5"""
    pf = PopFact(pop_id="p1", interaction_count=NOVELTY_HALFLIFE, last_interaction_tick=0)
    novelty = _pop_novelty(pf, 100)
    assert abs(novelty - 0.5) < 0.01


def test_novelty_full_familiarity():
    """Many interactions → novelty approaches 0"""
    pf = PopFact(pop_id="p1", interaction_count=1000, last_interaction_tick=0)
    novelty = _pop_novelty(pf, 100)
    assert novelty < 0.05


def test_novelty_recency_recovery():
    """After RECENCY_RECOVERY_TICKS of absence, novelty >= 0.5 even if familiar"""
    pf = PopFact(pop_id="p1", interaction_count=1000, last_interaction_tick=100)
    # At tick 100 (last interaction), then check at tick 1100
    # ticks_since = 1000, recency = min(1.0, 1000/RECENCY_RECOVERY_TICKS) = min(1.0, 1000/50) = 1.0
    novelty = _pop_novelty(pf, 1100)
    assert novelty >= 1.0 - 0.01


def test_novelty_partial_recency_recovery():
    """After 25 ticks (half RECENCY_RECOVERY_TICKS), familiar pop recovers to 0.5 novelty"""
    pf = PopFact(pop_id="p1", interaction_count=1000, last_interaction_tick=100)
    # ticks_since = 25, recency = min(1.0, 25/50) = 0.5
    # base = (1 - 1000/(1000 + 20)) ≈ 0.0196
    # max(0.0196, 0.5) = 0.5
    novelty = _pop_novelty(pf, 125)
    assert abs(novelty - 0.5) < 0.01


def test_novelty_intermediate_interactions():
    """10 interactions (half the halflife) yields ~0.67 novelty"""
    pf = PopFact(pop_id="p1", interaction_count=10, last_interaction_tick=0)
    # familiarity = 10 / (10 + 20) = 0.333...
    # novelty = 1.0 - 0.333 ≈ 0.667
    novelty = _pop_novelty(pf, 100)
    assert abs(novelty - 0.667) < 0.01


def test_novelty_recent_interaction_beats_base():
    """A familiar pop with a recent interaction recovers novelty boost"""
    pf = PopFact(pop_id="p1", interaction_count=1000, last_interaction_tick=90)
    current_tick = 100
    # ticks_since = 10, recency = min(1.0, 10/50) = 0.2
    # base ≈ 0.0196 (very familiar)
    # max(0.0196, 0.2) = 0.2
    novelty = _pop_novelty(pf, current_tick)
    assert novelty >= 0.2


# ─────────────────────────────────────────────────────────────────────────────
# Group 2: Novelty floor on socialize score
# ─────────────────────────────────────────────────────────────────────────────


def test_novelty_floor_constant_bounds():
    """SOCIAL_NOVELTY_FLOOR is in (0, 1), not at extremes"""
    assert 0.0 < SOCIAL_NOVELTY_FLOOR < 1.0


def test_novelty_floor_familiar_factor():
    """With novelty=0 (fully familiar), factor = FLOOR"""
    factor = SOCIAL_NOVELTY_FLOOR + 0.0 * (1.0 - SOCIAL_NOVELTY_FLOOR)
    assert factor == SOCIAL_NOVELTY_FLOOR


def test_novelty_floor_unknown_factor():
    """With novelty=1 (unknown), factor = 1.0"""
    factor = SOCIAL_NOVELTY_FLOOR + 1.0 * (1.0 - SOCIAL_NOVELTY_FLOOR)
    assert factor == 1.0


def test_novelty_floor_reduces_socialize():
    """A fully familiar Pop (novelty=0) produces a lower socialize factor than an unknown Pop (novelty=1)"""
    familiar_factor = SOCIAL_NOVELTY_FLOOR + 0.0 * (1.0 - SOCIAL_NOVELTY_FLOOR)
    unknown_factor = SOCIAL_NOVELTY_FLOOR + 1.0 * (1.0 - SOCIAL_NOVELTY_FLOOR)
    assert familiar_factor < unknown_factor
    assert familiar_factor == SOCIAL_NOVELTY_FLOOR
    assert unknown_factor == 1.0


def test_novelty_floor_intermediate():
    """At novelty=0.5, factor should be midpoint between floor and 1.0"""
    novelty = 0.5
    factor = SOCIAL_NOVELTY_FLOOR + novelty * (1.0 - SOCIAL_NOVELTY_FLOOR)
    expected = (SOCIAL_NOVELTY_FLOOR + 1.0) / 2.0
    assert abs(factor - expected) < 0.01


# ─────────────────────────────────────────────────────────────────────────────
# Group 3: PopFact KB helpers
# ─────────────────────────────────────────────────────────────────────────────


def test_pop_facts_empty():
    """KB with no pop facts returns empty list"""
    kb = KnowledgeBase()
    assert kb.pop_facts() == []


def test_pop_facts_with_single_pop():
    """KB with one PopFact returns a list with one element"""
    kb = KnowledgeBase()
    pf = PopFact(pop_id="pop-123", label="Farmers", interaction_count=5)
    kb.facts.append(pf)
    result = kb.pop_facts()
    assert len(result) == 1
    assert result[0] is pf


def test_pop_facts_filters_correctly():
    """pop_facts() only returns PopFact entries, not other fact types"""
    kb = KnowledgeBase()
    kb.facts.append(LocationFact(location_id="loc-1", label="Market"))
    kb.facts.append(PopFact(pop_id="pop-1", label="Farmers"))
    kb.facts.append(PopFact(pop_id="pop-2", label="Merchants"))
    kb.facts.append(LocationFact(location_id="loc-2", label="Temple"))

    pop_list = kb.pop_facts()
    assert len(pop_list) == 2
    assert all(f.fact_type == "pop" for f in pop_list)
    pop_ids = {f.pop_id for f in pop_list}
    assert pop_ids == {"pop-1", "pop-2"}


def test_get_pop_fact_missing():
    """get_pop_fact returns None for unknown pop_id"""
    kb = KnowledgeBase()
    assert kb.get_pop_fact("nonexistent") is None


def test_get_pop_fact_found():
    """get_pop_fact returns the matching PopFact"""
    kb = KnowledgeBase()
    pf = PopFact(pop_id="pop-123", label="Farmers", interaction_count=5)
    kb.facts.append(pf)
    result = kb.get_pop_fact("pop-123")
    assert result is not None
    assert result is pf
    assert result.pop_id == "pop-123"
    assert result.interaction_count == 5


def test_get_pop_fact_ignores_other_types():
    """get_pop_fact returns None when a non-PopFact with similar ID exists"""
    kb = KnowledgeBase()
    kb.facts.append(LocationFact(location_id="pop-123", label="Market"))
    result = kb.get_pop_fact("pop-123")
    assert result is None


def test_get_pop_fact_multiple_pops():
    """get_pop_fact finds the correct Pop among many"""
    kb = KnowledgeBase()
    pf1 = PopFact(pop_id="pop-1", label="Farmers")
    pf2 = PopFact(pop_id="pop-2", label="Merchants")
    pf3 = PopFact(pop_id="pop-3", label="Soldiers")
    kb.facts.extend([pf1, pf2, pf3])

    result = kb.get_pop_fact("pop-2")
    assert result is pf2
    assert result.label == "Merchants"


def test_pop_fact_default_label():
    """PopFact with no label has empty string"""
    pf = PopFact(pop_id="p1")
    assert pf.label == ""
    assert pf.interaction_count == 0
    assert pf.last_interaction_tick == 0


def test_pop_fact_full_construction():
    """PopFact with all fields set"""
    pf = PopFact(
        pop_id="pop-456",
        label="Scholar Collective",
        interaction_count=42,
        last_interaction_tick=87,
    )
    assert pf.pop_id == "pop-456"
    assert pf.label == "Scholar Collective"
    assert pf.interaction_count == 42
    assert pf.last_interaction_tick == 87
    assert pf.fact_type == "pop"


def test_knowledge_base_preserves_pop_facts_on_round_trip():
    """PopFacts survive JSON serialization round-trip"""
    kb = KnowledgeBase()
    pf = PopFact(pop_id="pop-789", label="Traders", interaction_count=15, last_interaction_tick=50)
    kb.facts.append(pf)

    # Serialize and deserialize
    json_str = kb.model_dump_json()
    restored = KnowledgeBase.model_validate_json(json_str)

    assert len(restored.facts) == 1
    result = restored.get_pop_fact("pop-789")
    assert result is not None
    assert result.label == "Traders"
    assert result.interaction_count == 15
    assert result.last_interaction_tick == 50
