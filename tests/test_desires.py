import pytest
from unittest.mock import MagicMock
from core.agent_core import (
    CivilianAgentState, MortalNeed, MortalDesire, KnowledgeBase,
    LocationFact, LocationQualityFact, RouteFact, Resource,
)
from logic.civilian_agent_logic import evaluate_civilian_action


# ── Helpers ──────────────────────────────────────────────────────────────────

def _mortal_with_desires(cs, kb=None, fatigue=0.0, assets=None, loc_id="loc-A", culture_tags=None):
    m = MagicMock()
    m.civilian_state = cs
    m.knowledge_base = kb or KnowledgeBase()
    m.fatigue = fatigue
    m.assets = assets or []
    m.travel_intent = None
    m.current_location = loc_id
    m.skill_tags = {"skill:trade": 0.8}
    m.culture_tags = culture_tags or {}
    m.belief_tags = {}
    m.species_id = None
    m.pop_id = None
    m.pop_milieu = None
    return m


def _state():
    s = MagicMock()
    s.locations = {}
    s.pops = {}
    return s


# ── Group 1: MortalDesire model ───────────────────────────────────────────────

def test_desire_urgency_satisfied():
    """urgency() returns 0.0 when satisfaction is above pressing_threshold."""
    d = MortalDesire(name="accumulation", satisfaction=0.8, pressing_threshold=0.5)
    assert d.urgency() == 0.0


def test_desire_urgency_pressing():
    """urgency() returns correct value when satisfaction is below threshold."""
    d = MortalDesire(name="accumulation", satisfaction=0.25, pressing_threshold=0.5)
    # urgency = 1.0 - (0.25 / 0.5) = 0.5
    assert d.urgency() == pytest.approx(0.5)


def test_desire_urgency_satiation_hold():
    """urgency() returns 0.0 when satiation_hold > 0, even if pressing."""
    d = MortalDesire(name="exploration", satisfaction=0.1, pressing_threshold=0.5, satiation_hold=3)
    assert d.urgency() == 0.0


def test_desire_no_urgent_threshold():
    """MortalDesire has no is_urgent or urgent_threshold — only is_pressing."""
    d = MortalDesire(name="expression", satisfaction=0.0)
    assert hasattr(d, "is_pressing")
    assert not hasattr(d, "is_urgent")
    assert not hasattr(d, "urgent_threshold")


# ── Group 2: compute_desire_profile ──────────────────────────────────────────

def test_compute_desire_profile_vail_traits():
    """Vail's traits generate all three desires."""
    from logic.needs_config import compute_desire_profile, DESIRE_ACCUMULATION, DESIRE_EXPLORATION, DESIRE_EXPRESSION
    tags = {
        "values:prosperity": 0.85,
        "values:sedentism": -0.7,
        "values:xenophilia": 0.8,
        "practice:music": 0.75,
    }
    desires = compute_desire_profile(tags)
    names = {d.name for d in desires}
    assert DESIRE_ACCUMULATION in names
    assert DESIRE_EXPLORATION in names
    assert DESIRE_EXPRESSION in names


def test_compute_desire_profile_no_traits():
    """Mortal with no qualifying traits generates no desires."""
    from logic.needs_config import compute_desire_profile
    desires = compute_desire_profile({})
    assert desires == []


def test_compute_desire_profile_expression_excluded_practices():
    """practice:ritual and practice:revelry do NOT generate Expression desire."""
    from logic.needs_config import compute_desire_profile
    tags = {"practice:ritual": 0.9, "practice:revelry": 0.9}
    desires = compute_desire_profile(tags)
    assert all(d.name != "expression" for d in desires)


def test_compute_desire_profile_expression_included():
    """practice:music DOES generate Expression desire."""
    from logic.needs_config import compute_desire_profile, DESIRE_EXPRESSION
    tags = {"practice:music": 0.8}
    desires = compute_desire_profile(tags)
    assert any(d.name == DESIRE_EXPRESSION for d in desires)


# ── Group 3: Action scoring with desires ─────────────────────────────────────

def test_accumulation_desire_boosts_sell_without_purpose_pressure():
    """With Accumulation desire pressing and no purpose urgency, sell score is boosted enough to beat idle."""
    sell_loc_id = "loc-A"
    cs = CivilianAgentState(
        needs=[MortalNeed(name="purpose", satisfaction=1.0)],
        desires=[MortalDesire(name="accumulation", satisfaction=0.1, pressing_threshold=0.5)],
        inventory=[Resource(resource_type="unobtanium", quantity=5.0, threshold=2.0, usable_for=["sell"])],
    )
    kb = KnowledgeBase(facts=[
        LocationQualityFact(location_id=sell_loc_id, quality=0.9, quality_type="sell"),
    ])
    result = evaluate_civilian_action(_mortal_with_desires(cs, kb, loc_id=sell_loc_id), _state(), 0)
    assert result == "sell"


def test_wander_action_selected_for_unvisited_location():
    """With Exploration desire pressing, no needs pressing, known unvisited location → returns 'wander:<id>'."""
    cs = CivilianAgentState(
        needs=[MortalNeed(name="purpose", satisfaction=1.0)],
        desires=[MortalDesire(name="exploration", satisfaction=0.1, pressing_threshold=0.5)],
    )
    kb = KnowledgeBase(facts=[
        LocationFact(location_id="loc-B", visit_count=0),
        RouteFact(from_id="loc-A", to_id="loc-B", ticks_cost=3, vehicle_type=None),
    ])
    result = evaluate_civilian_action(_mortal_with_desires(cs, kb, loc_id="loc-A"), _state(), 0)
    assert result == "wander:loc-B"


def test_needs_dominate_desires_when_pressing():
    """When a survival need is urgent AND Exploration desire is pressing, wander is NOT chosen."""
    cs = CivilianAgentState(
        needs=[MortalNeed(
            name="sustenance",
            satisfaction=0.2,
            pressing_threshold=0.55,
            urgent_threshold=0.20,
            decay_rate=0.05,
        )],
        desires=[MortalDesire(name="exploration", satisfaction=0.1, pressing_threshold=0.5)],
    )
    kb = KnowledgeBase(facts=[
        LocationFact(location_id="loc-B", visit_count=0),
        RouteFact(from_id="loc-A", to_id="loc-B", ticks_cost=12, vehicle_type=None),
    ])
    result = evaluate_civilian_action(_mortal_with_desires(cs, kb, loc_id="loc-A"), _state(), 0)
    # Wander is blocked: trip is too long for urgent sustenance need
    assert not result.startswith("wander:")
