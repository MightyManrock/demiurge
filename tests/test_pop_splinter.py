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
