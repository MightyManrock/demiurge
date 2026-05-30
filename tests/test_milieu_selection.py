"""Tests for zero-cost milieu selection among pops at same location."""
import pytest
from unittest.mock import MagicMock
from uuid import uuid4

from core.agent_core import CivilianAgentState, MortalNeed
from logic.civilian_agent_logic import _select_local_pop


LOC = "loc-neran"


def _need(name, satisfaction=0.3, pressing=True):
    threshold = 0.65 if pressing else 0.10  # threshold above satisfaction → pressing
    return MortalNeed(name=name, satisfaction=satisfaction,
                      pressing_threshold=threshold, urgent_threshold=0.05, decay_rate=0.04)


def _pop(loc=LOC, revelry=0.3, solidarity=0.3, practice_val=0.5):
    p = MagicMock()
    p.id = uuid4()
    p.current_location = loc
    p.culture_tags = {
        "practice:music": practice_val,
        "practice:revelry": revelry,
        "values:solidarity": solidarity,
    }
    return p


def _mortal(cs, loc=LOC, culture_tags=None):
    m = MagicMock()
    m.civilian_state = cs
    m.current_location = loc
    m.culture_tags = culture_tags or {"practice:music": 0.8}
    return m


def _state(pops):
    s = MagicMock()
    s.pops = {str(p.id): p for p in pops}
    return s


# ── No social needs pressing → no switch ─────────────────────────────────────

def test_no_switch_when_no_social_needs_pressing():
    cs = CivilianAgentState(needs=[_need("purpose", pressing=True)])  # only Purpose
    pop = _pop()
    result = _select_local_pop(_mortal(cs), _state([pop]))
    assert result is None


def test_no_switch_when_no_pops_at_location():
    cs = CivilianAgentState(needs=[_need("leisure"), _need("belonging")])
    pop = _pop(loc="other-loc")  # at a different location
    result = _select_local_pop(_mortal(cs), _state([pop]))
    assert result is None


# ── Single local pop → always selected when social needs pressing ─────────────

def test_single_pop_selected_when_leisure_pressing():
    cs = CivilianAgentState(needs=[_need("leisure")])
    pop = _pop()
    result = _select_local_pop(_mortal(cs), _state([pop]))
    assert result == str(pop.id)


def test_single_pop_selected_when_belonging_pressing():
    cs = CivilianAgentState(needs=[_need("belonging")])
    pop = _pop()
    result = _select_local_pop(_mortal(cs), _state([pop]))
    assert result == str(pop.id)


# ── Multiple pops → picks best for pressing needs ─────────────────────────────

def test_picks_high_revelry_pop_when_belonging_pressing():
    """Belonging pressing only → pop with higher solidarity+revelry wins."""
    cs = CivilianAgentState(needs=[_need("belonging")])
    pop_low  = _pop(revelry=0.2, solidarity=0.2)
    pop_high = _pop(revelry=0.9, solidarity=0.9)
    result = _select_local_pop(_mortal(cs), _state([pop_low, pop_high]))
    assert result == str(pop_high.id)


def test_picks_practice_match_when_leisure_pressing():
    """Leisure pressing only → pop whose practice tags match mortal culture wins."""
    cs = CivilianAgentState(needs=[_need("leisure")])
    mortal_tags = {"practice:music": 0.9}
    pop_music = _pop(practice_val=0.9)   # high music → good match
    pop_other = _pop(practice_val=0.1)   # low music → poor match
    result = _select_local_pop(_mortal(cs, culture_tags=mortal_tags), _state([pop_music, pop_other]))
    assert result == str(pop_music.id)


def test_both_needs_pressing_combines_scores():
    """Both leisure and belonging pressing → pop maximising combined score wins."""
    cs = CivilianAgentState(needs=[_need("leisure"), _need("belonging")])
    mortal_tags = {"practice:music": 0.8}
    # pop_a: great for leisure (high music), mediocre for belonging
    pop_a = _pop(practice_val=0.9, revelry=0.2, solidarity=0.2)
    # pop_b: great for belonging, mediocre for leisure
    pop_b = _pop(practice_val=0.1, revelry=0.9, solidarity=0.9)
    # pop_c: decent at both
    pop_c = _pop(practice_val=0.6, revelry=0.6, solidarity=0.6)
    result = _select_local_pop(_mortal(cs, culture_tags=mortal_tags), _state([pop_a, pop_b, pop_c]))
    # pop_a: ~0.9 + (0.2*0.5+0.2*0.5)=0.2 = 1.1; pop_b: ~0.1 + 0.9 = 1.0; pop_c: ~0.6 + 0.6 = 1.2
    # pop_c should win on combined score
    assert result == str(pop_c.id)
