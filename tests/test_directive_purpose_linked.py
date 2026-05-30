"""Tests for directive Purpose fulfillment: own pop (full) vs linked pop (scaled) vs stranger (none)."""
import pytest
from unittest.mock import MagicMock
from uuid import uuid4

from core.agent_core import CivilianAgentState, MortalNeed, DirectiveFact
from logic.needs_config import NEED_PURPOSE
from logic.sim_utils import compute_link_factor


def _need(name, satisfaction=0.3):
    return MortalNeed(
        name=name, satisfaction=satisfaction,
        pressing_threshold=0.60, urgent_threshold=0.25, decay_rate=0.03,
    )


def _pop(pop_id=None, linked=None, occupation="merchant"):
    p = MagicMock()
    p.id = pop_id or uuid4()
    p.linked_pop_ids = linked or {}
    p.stratum = MagicMock()
    p.stratum.value = "trader"
    p.occupation = occupation
    p.dominant_beliefs = {}
    p.culture_tags = {}
    return p


def _run_purpose_update(origin_pop, sell_pop, state, initial_satisfaction=0.3):
    """Simulate the directive Purpose block from the sell branch."""
    purpose = _need(NEED_PURPOSE, satisfaction=initial_satisfaction)
    cs = CivilianAgentState(needs=[purpose])

    origin_pop_id_str = str(origin_pop.id)
    sell_pop_id_str = str(sell_pop.id)

    purpose_need = cs.get_need(NEED_PURPOSE)
    _is_own = sell_pop_id_str == origin_pop_id_str
    if _is_own:
        purpose_need.satisfaction = 1.0
        purpose_need.satiation_hold = 10
    elif sell_pop_id_str in origin_pop.linked_pop_ids:
        _p_base = origin_pop.linked_pop_ids[sell_pop_id_str]
        _p_lf = compute_link_factor(origin_pop, sell_pop, _p_base)
        purpose_need.satisfaction = min(1.0, purpose_need.satisfaction + _p_lf)
        purpose_need.satiation_hold = round(10 * _p_lf)

    return cs.get_need(NEED_PURPOSE)


# ── Own pop: full fulfillment ─────────────────────────────────────────────────

def test_purpose_own_pop_full():
    pop = _pop()
    result = _run_purpose_update(pop, pop, MagicMock())
    assert result.satisfaction == pytest.approx(1.0)
    assert result.satiation_hold == 10


# ── Linked pop: scaled fulfillment ───────────────────────────────────────────

def test_purpose_linked_pop_partial():
    origin_pop = _pop(occupation="merchant")
    sell_pop = _pop(linked={}, occupation="merchant")
    # origin links to sell (origin→local direction for Purpose)
    origin_pop.linked_pop_ids = {str(sell_pop.id): 0.5}
    # With shared occupation (+0.10), shared stratum bonus (+0.05), cosine ~0 → lf ≈ 0.65
    result = _run_purpose_update(origin_pop, sell_pop, MagicMock(), initial_satisfaction=0.3)
    assert 0.3 < result.satisfaction < 1.0
    assert result.satiation_hold > 0


def test_purpose_linked_pop_high_base_caps_at_1():
    origin_pop = _pop(occupation="merchant")
    sell_pop = _pop(linked={}, occupation="merchant")
    origin_pop.linked_pop_ids = {str(sell_pop.id): 1.0}
    # lf clamped to 1.0 → satisfaction = min(1.0, 0.3 + 1.0) = 1.0
    result = _run_purpose_update(origin_pop, sell_pop, MagicMock(), initial_satisfaction=0.3)
    assert result.satisfaction == pytest.approx(1.0)
    assert result.satiation_hold == 10


def test_purpose_linked_pop_hold_proportional_to_link_factor():
    origin_pop = _pop(occupation="")  # no occupation bonus
    sell_pop = _pop(linked={}, occupation="")
    origin_pop.stratum = sell_pop.stratum  # same stratum: +0.05
    origin_pop.linked_pop_ids = {str(sell_pop.id): 0.4}
    # lf ≈ 0.4 + 0.05 = 0.45 (no occupation match, cosine ~0) → hold = round(10 * 0.45) = 5
    result = _run_purpose_update(origin_pop, sell_pop, MagicMock(), initial_satisfaction=0.0)
    assert result.satiation_hold == round(10 * compute_link_factor(origin_pop, sell_pop, 0.4))


# ── Stranger: no fulfillment ──────────────────────────────────────────────────

def test_purpose_stranger_no_boost():
    origin_pop = _pop()
    sell_pop = _pop()  # no link in either direction
    result = _run_purpose_update(origin_pop, sell_pop, MagicMock(), initial_satisfaction=0.3)
    assert result.satisfaction == pytest.approx(0.3)
    assert result.satiation_hold == 0


# ── Asymmetry: Status and Purpose use different link directions ───────────────

def test_purpose_uses_origin_to_local_direction():
    """Purpose fires on origin→local link; Status uses local→origin (different direction)."""
    origin_pop = _pop()
    sell_pop = _pop()
    # Only origin→local link exists (no reverse)
    origin_pop.linked_pop_ids = {str(sell_pop.id): 0.6}
    sell_pop.linked_pop_ids = {}

    result = _run_purpose_update(origin_pop, sell_pop, MagicMock(), initial_satisfaction=0.0)
    # Purpose fires because origin links to sell
    assert result.satisfaction > 0.0

    # Status check uses local→origin: no link on sell_pop → stranger tier
    from logic.tick_logic import _status_recognition_from_pop
    mortal = MagicMock()
    mortal.pop_id = origin_pop.id
    state = MagicMock()
    state.pops = {str(origin_pop.id): origin_pop}
    gain, hold = _status_recognition_from_pop(mortal, sell_pop, state, strong=True)
    assert gain == pytest.approx(0.12)  # stranger tier
