import math
import pytest
from unittest.mock import MagicMock


# ── _splinter_probability ──────────────────────────────────────────────────

def test_splinter_probability_near_zero_at_threshold():
    from logic.tick_logic import _splinter_probability, SPLINTER_PROB_MIDPOINT
    p = _splinter_probability(0.50, SPLINTER_PROB_MIDPOINT)
    assert p < 0.15

def test_splinter_probability_half_at_midpoint():
    from logic.tick_logic import _splinter_probability, SPLINTER_PROB_MIDPOINT
    p = _splinter_probability(SPLINTER_PROB_MIDPOINT, SPLINTER_PROB_MIDPOINT)
    assert abs(p - 0.5) < 0.01

def test_splinter_probability_near_certain_at_high_divergence():
    from logic.tick_logic import _splinter_probability, SPLINTER_PROB_MIDPOINT
    p = _splinter_probability(0.90, SPLINTER_PROB_MIDPOINT)
    assert p > 0.88

def test_splinter_probability_shifts_with_civ_offset():
    from logic.tick_logic import _splinter_probability, SPLINTER_PROB_MIDPOINT
    p_base   = _splinter_probability(0.65, SPLINTER_PROB_MIDPOINT)
    p_tribal = _splinter_probability(0.65, SPLINTER_PROB_MIDPOINT + 0.15)
    assert p_tribal < p_base


# ── _splinter_fraction ─────────────────────────────────────────────────────

def test_splinter_fraction_min_at_threshold():
    from logic.tick_logic import _splinter_fraction, SPLINTER_MIN_FRACTION, SPLINTER_DIVERGENCE_THRESHOLD
    f = _splinter_fraction(SPLINTER_DIVERGENCE_THRESHOLD)
    assert abs(f - SPLINTER_MIN_FRACTION) < 0.001

def test_splinter_fraction_max_at_full_divergence():
    from logic.tick_logic import _splinter_fraction, SPLINTER_MAX_FRACTION
    f = _splinter_fraction(1.0)
    assert abs(f - SPLINTER_MAX_FRACTION) < 0.001

def test_splinter_fraction_midpoint():
    from logic.tick_logic import _splinter_fraction, SPLINTER_MIN_FRACTION, SPLINTER_MAX_FRACTION, SPLINTER_DIVERGENCE_THRESHOLD
    mid_div = (SPLINTER_DIVERGENCE_THRESHOLD + 1.0) / 2.0
    f = _splinter_fraction(mid_div)
    expected = (SPLINTER_MIN_FRACTION + SPLINTER_MAX_FRACTION) / 2.0
    assert abs(f - expected) < 0.01


# ── _check_pop_splinters stride gate ──────────────────────────────────────

def _make_loop():
    from logic.tick_logic import TickLoop
    return TickLoop(rng_seed=42)

def test_splinter_check_returns_empty_off_stride():
    from logic.tick_logic import SPLINTER_CHECK_STRIDE
    loop = _make_loop()
    state = MagicMock()
    state.tick_number = 1  # not on stride
    state.pops = {}
    mutations, events = loop._check_pop_splinters(state)
    assert mutations == []
    assert events == []

def test_splinter_check_runs_on_stride():
    from logic.tick_logic import SPLINTER_CHECK_STRIDE
    loop = _make_loop()
    state = MagicMock()
    state.tick_number = SPLINTER_CHECK_STRIDE
    state.pops = {}
    state.civilizations = {}
    mutations, events = loop._check_pop_splinters(state)
    assert mutations == []  # no pops → nothing to do


# ── _redistribute_mortals_on_splinter ─────────────────────────────────────

from uuid import uuid4 as _uuid4

def _make_pop_for_redistrib(beliefs, occupation="Artist"):
    from core.universe_core import Pop, SocialClass
    return Pop(
        social_class=SocialClass.COMMON,
        occupation=occupation,
        current_location=_uuid4(),
        size_fractional=6.0,
        dominant_beliefs=beliefs,
        civilization_id=_uuid4(),
    )

def _make_mortal_for_redistrib(beliefs, pop_id):
    from core.universe_core import NotableMortal
    loc = _uuid4()
    return NotableMortal(name="Test Mortal", pop_id=pop_id, belief_tags=beliefs,
                         home_location=loc, current_location=loc)

def test_mortal_stays_with_parent_when_more_similar():
    parent   = _make_pop_for_redistrib({"domain:order": 0.6, "domain:change": 0.2})
    splinter = _make_pop_for_redistrib({"domain:order": 0.1, "domain:change": 0.8})
    mortal   = _make_mortal_for_redistrib({"domain:order": 0.55, "domain:change": 0.25}, pop_id=parent.id)
    parent.notable_mortal_ids = [mortal.id]
    splinter.notable_mortal_ids = []

    from logic.tick_logic import _redistribute_mortals_on_splinter
    moved = _redistribute_mortals_on_splinter(parent, splinter, {str(mortal.id): mortal})

    assert mortal.id not in moved
    assert mortal.pop_id == parent.id
    assert mortal.id in parent.notable_mortal_ids
    assert mortal.id not in splinter.notable_mortal_ids

def test_mortal_moves_to_splinter_when_more_similar():
    parent   = _make_pop_for_redistrib({"domain:order": 0.6, "domain:change": 0.2})
    splinter = _make_pop_for_redistrib({"domain:order": 0.1, "domain:change": 0.8})
    mortal   = _make_mortal_for_redistrib({"domain:order": 0.15, "domain:change": 0.75}, pop_id=parent.id)
    parent.notable_mortal_ids = [mortal.id]
    splinter.notable_mortal_ids = []

    from logic.tick_logic import _redistribute_mortals_on_splinter
    moved = _redistribute_mortals_on_splinter(parent, splinter, {str(mortal.id): mortal})

    assert mortal.id in moved
    assert mortal.pop_id == splinter.id
    assert mortal.id in splinter.notable_mortal_ids
    assert mortal.id not in parent.notable_mortal_ids

def test_redistribute_skips_missing_mortals():
    from uuid import uuid4
    parent   = _make_pop_for_redistrib({"domain:order": 0.6})
    splinter = _make_pop_for_redistrib({"domain:order": 0.1})
    missing_id = uuid4()
    parent.notable_mortal_ids = [missing_id]

    from logic.tick_logic import _redistribute_mortals_on_splinter
    moved = _redistribute_mortals_on_splinter(parent, splinter, {})
    assert moved == []
