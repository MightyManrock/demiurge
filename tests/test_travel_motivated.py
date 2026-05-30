import pytest
from unittest.mock import MagicMock
from core.agent_core import CivilianAgentState, MortalNeed, KnowledgeBase, RouteFact, DirectiveFact
from logic.civilian_agent_logic import _travel_motivated


def _cs(**need_overrides):
    cs = CivilianAgentState()
    defaults = {
        "purpose":  MortalNeed(name="purpose",  satisfaction=0.9, pressing_threshold=0.60, urgent_threshold=0.25, decay_rate=0.03),
        "status":   MortalNeed(name="status",   satisfaction=0.9, pressing_threshold=0.60, urgent_threshold=0.20, decay_rate=0.03),
        "leisure":  MortalNeed(name="leisure",  satisfaction=0.9, pressing_threshold=0.65, urgent_threshold=0.30, decay_rate=0.04),
    }
    defaults.update(need_overrides)
    cs.needs = list(defaults.values())
    return cs


def _kb(ticks_cost: int, with_directive: bool = False) -> KnowledgeBase:
    kb = KnowledgeBase()
    kb.facts = [RouteFact(from_id="here", to_id="dest", ticks_cost=ticks_cost)]
    if with_directive:
        kb.facts.append(DirectiveFact(
            directive_id="d1", directive_type="commerce",
            satisfying_action="sell", target_pop_location_id="p1",
        ))
    return kb


# ── Short trips always allowed ────────────────────────────────────────────────

def test_short_trip_always_allowed_no_pressing_needs():
    cs = _cs()  # all needs satisfied
    kb = _kb(ticks_cost=1)
    assert _travel_motivated(cs, kb, "dest") is True


def test_trip_at_threshold_always_allowed():
    cs = _cs()
    kb = _kb(ticks_cost=2)
    assert _travel_motivated(cs, kb, "dest") is True


# ── Long trips blocked without motivation ─────────────────────────────────────

def test_long_trip_blocked_when_needs_satisfied():
    cs = _cs()  # purpose 0.9, status 0.9 — neither pressing
    kb = _kb(ticks_cost=3)
    assert _travel_motivated(cs, kb, "dest") is False


def test_long_trip_blocked_purpose_pressing_but_no_directive():
    cs = _cs(purpose=MortalNeed(name="purpose", satisfaction=0.3, pressing_threshold=0.60, urgent_threshold=0.25, decay_rate=0.03))
    kb = _kb(ticks_cost=3, with_directive=False)
    assert _travel_motivated(cs, kb, "dest") is False


# ── Long trips allowed with motivation ───────────────────────────────────────

def test_long_trip_allowed_purpose_pressing_with_directive():
    cs = _cs(purpose=MortalNeed(name="purpose", satisfaction=0.3, pressing_threshold=0.60, urgent_threshold=0.25, decay_rate=0.03))
    kb = _kb(ticks_cost=5, with_directive=True)
    assert _travel_motivated(cs, kb, "dest") is True


def test_long_trip_allowed_status_pressing():
    cs = _cs(status=MortalNeed(name="status", satisfaction=0.4, pressing_threshold=0.60, urgent_threshold=0.20, decay_rate=0.03))
    kb = _kb(ticks_cost=4)
    assert _travel_motivated(cs, kb, "dest") is True


def test_long_trip_allowed_urgent_need():
    cs = _cs(leisure=MortalNeed(name="leisure", satisfaction=0.1, pressing_threshold=0.65, urgent_threshold=0.30, decay_rate=0.04))
    kb = _kb(ticks_cost=6)
    assert _travel_motivated(cs, kb, "dest") is True


# ── No route fact → always allowed ───────────────────────────────────────────

def test_no_route_always_allowed():
    cs = _cs()
    kb = KnowledgeBase()  # no route fact at all
    assert _travel_motivated(cs, kb, "dest") is True
