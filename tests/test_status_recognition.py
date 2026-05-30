"""Tests for Status recognition via sell (commerce) and socialize actions."""
import pytest
from unittest.mock import MagicMock
from uuid import uuid4

from core.agent_core import CivilianAgentState, MortalNeed
from logic.needs_config import NEED_STATUS, NEED_BELONGING
from logic.tick_logic import _status_recognition_from_pop


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _pop(pop_id=None, linked=None):
    """Minimal Pop mock."""
    p = MagicMock()
    p.id = pop_id or uuid4()
    p.linked_pop_ids = linked or {}
    # Fields needed by compute_link_factor (called for linked-pop path)
    p.stratum = MagicMock()
    p.occupation = ""
    p.dominant_beliefs = {}
    p.culture_tags = {}
    return p


def _mortal(pop_id=None):
    m = MagicMock()
    m.pop_id = pop_id or uuid4()
    return m


def _state(pops=None):
    s = MagicMock()
    s.pops = pops or {}
    return s


# ── Own-pop relationship ──────────────────────────────────────────────────────

def test_status_sell_own_pop():
    pop = _pop()
    mortal = _mortal(pop_id=pop.id)
    gain, hold = _status_recognition_from_pop(mortal, pop, _state(), strong=True)
    assert gain == pytest.approx(0.60)
    assert hold == 14


def test_status_socialize_own_pop():
    pop = _pop()
    mortal = _mortal(pop_id=pop.id)
    gain, hold = _status_recognition_from_pop(mortal, pop, _state(), strong=False)
    assert gain == pytest.approx(0.10)
    assert hold == 3


# ── Linked-pop relationship ───────────────────────────────────────────────────

def test_status_sell_linked_pop():
    # Status direction: local_pop links toward origin_pop (local recognizes Durenn's people)
    origin_pop = _pop()
    local_pop = _pop(linked={str(origin_pop.id): 1.0})
    mortal = _mortal(pop_id=origin_pop.id)
    state = _state(pops={str(origin_pop.id): origin_pop})
    gain, hold = _status_recognition_from_pop(mortal, local_pop, state, strong=True)
    # link_scale=0.50, lf ≥ base=1.0 (clamped to 1.0) → gain ≈ 0.50
    assert 0.0 < gain <= 0.50
    assert hold == 10


def test_status_socialize_linked_pop():
    origin_pop = _pop()
    local_pop = _pop(linked={str(origin_pop.id): 0.5})
    mortal = _mortal(pop_id=origin_pop.id)
    state = _state(pops={str(origin_pop.id): origin_pop})
    gain, hold = _status_recognition_from_pop(mortal, local_pop, state, strong=False)
    assert 0.0 < gain <= 0.10
    assert hold == 2


# ── Stranger relationship ─────────────────────────────────────────────────────

def test_status_sell_stranger():
    local_pop = _pop()
    mortal = _mortal()  # pop_id has no link to local_pop
    gain, hold = _status_recognition_from_pop(mortal, local_pop, _state(), strong=True)
    assert gain == pytest.approx(0.12)
    assert hold == 6


def test_status_socialize_stranger():
    local_pop = _pop()
    mortal = _mortal()
    gain, hold = _status_recognition_from_pop(mortal, local_pop, _state(), strong=False)
    assert gain == pytest.approx(0.02)
    assert hold == 0


# ── Magnitude ordering ────────────────────────────────────────────────────────

def test_status_sell_greater_than_socialize_own_pop():
    pop = _pop()
    mortal = _mortal(pop_id=pop.id)
    sell_gain, _ = _status_recognition_from_pop(mortal, pop, _state(), strong=True)
    soc_gain,  _ = _status_recognition_from_pop(mortal, pop, _state(), strong=False)
    assert sell_gain > soc_gain


def test_status_own_pop_greater_than_stranger():
    pop = _pop()
    mortal_own = _mortal(pop_id=pop.id)
    mortal_str = _mortal()
    own_gain, _    = _status_recognition_from_pop(mortal_own, pop, _state(), strong=True)
    stranger_gain, _ = _status_recognition_from_pop(mortal_str, pop, _state(), strong=True)
    assert own_gain > stranger_gain


# ── Satisfaction clamping ─────────────────────────────────────────────────────

def test_status_capped_at_1():
    pop = _pop()
    mortal = _mortal(pop_id=pop.id)
    status = MortalNeed(name=NEED_STATUS, satisfaction=0.95, pressing_threshold=0.60)
    cs = CivilianAgentState(needs=[status])
    gain, hold = _status_recognition_from_pop(mortal, pop, _state(), strong=True)
    status.satisfaction = min(1.0, status.satisfaction + gain)
    assert status.satisfaction == pytest.approx(1.0)


# ── Hold gating ───────────────────────────────────────────────────────────────

def test_status_hold_not_set_when_below_pressing_threshold():
    """Hold should not be applied when satisfaction stays below pressing_threshold."""
    pop = _pop()
    mortal = _mortal(pop_id=pop.id)
    # Start very low; even +0.60 won't exceed pressing_threshold=0.80
    status = MortalNeed(name=NEED_STATUS, satisfaction=0.0, pressing_threshold=0.80)
    gain, hold = _status_recognition_from_pop(mortal, pop, _state(), strong=True)
    # gain=0.60, new satisfaction=0.60, still below 0.80
    new_sat = status.satisfaction + gain
    assert new_sat < status.pressing_threshold
    # The hold guard: only set if new_sat >= pressing_threshold
    if hold and new_sat >= status.pressing_threshold:
        status.satiation_hold = hold
    assert status.satiation_hold == 0  # unchanged
