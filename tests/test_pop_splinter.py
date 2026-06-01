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


# ── _check_pop_reabsorption ───────────────────────────────────────────────

from uuid import uuid4 as _uuid4r

def _make_loop_r():
    from logic.tick_logic import TickLoop
    return TickLoop(rng_seed=42)

def _make_pop_r(beliefs, size, location_id, civ_id, occupation="Artist", social_class_str="common"):
    from core.universe_core import Pop, SocialClass
    sc = SocialClass(social_class_str)
    return Pop(
        social_class=sc,
        occupation=occupation,
        current_location=location_id,
        size_fractional=size,
        dominant_beliefs=dict(beliefs),
        civilization_id=civ_id,
    )

def _make_reabsorb_state(pops_dict, tick=10):
    s = MagicMock()
    s.tick_number = tick
    s.pops = pops_dict
    s.civilizations = {}
    s.locations = {}
    s.mortals = {}
    return s

def test_reabsorption_skips_vessel_crew():
    from logic.tick_logic import SPLINTER_CHECK_STRIDE
    loc = _uuid4r(); civ = _uuid4r()
    crew = _make_pop_r({"domain:order": 0.6}, size=4.5, location_id=loc, civ_id=civ)
    crew.asset_crew_for = "ship"
    loop = _make_loop_r()
    state = _make_reabsorb_state({str(crew.id): crew}, tick=SPLINTER_CHECK_STRIDE)
    mutations, events = loop._check_pop_reabsorption(state)
    assert mutations == []

def test_reabsorption_skips_off_stride():
    from logic.tick_logic import SPLINTER_CHECK_STRIDE
    loc = _uuid4r(); civ = _uuid4r()
    source = _make_pop_r({"domain:order": 0.6}, size=4.5, location_id=loc, civ_id=civ)
    loop = _make_loop_r()
    state = _make_reabsorb_state({str(source.id): source}, tick=1)
    mutations, events = loop._check_pop_reabsorption(state)
    assert mutations == []

def test_reabsorption_drains_source_into_parent():
    from logic.tick_logic import SPLINTER_CHECK_STRIDE, REABSORPTION_DRAIN_FRACTION, MutationType
    loc = _uuid4r(); civ = _uuid4r()
    beliefs = {"domain:order": 0.6, "domain:change": 0.3}
    parent = _make_pop_r(beliefs, size=6.0, location_id=loc, civ_id=civ)
    source = _make_pop_r(beliefs, size=4.5, location_id=loc, civ_id=civ)
    source.parent_pop_id = parent.id

    loop = _make_loop_r()
    state = _make_reabsorb_state(
        {str(parent.id): parent, str(source.id): source},
        tick=SPLINTER_CHECK_STRIDE,
    )
    mutations, events = loop._check_pop_reabsorption(state)

    size_changes = [m for m in mutations if m.mutation_type == MutationType.POP_SIZE_CHANGE]
    assert len(size_changes) == 2
    source_mut = next(m for m in size_changes if str(m.target_id) == str(source.id))
    parent_mut = next(m for m in size_changes if str(m.target_id) == str(parent.id))
    assert source_mut.delta < 0
    assert parent_mut.delta > 0

def test_reabsorption_skips_when_not_convergent():
    from logic.tick_logic import SPLINTER_CHECK_STRIDE
    loc = _uuid4r(); civ = _uuid4r()
    # Use orthogonal belief vectors so cosine similarity is well below threshold
    parent = _make_pop_r({"domain:order": 0.9, "domain:change": 0.0}, size=6.0, location_id=loc, civ_id=civ)
    source = _make_pop_r({"domain:order": 0.0, "domain:change": 0.9}, size=4.5, location_id=loc, civ_id=civ)
    source.parent_pop_id = parent.id

    loop = _make_loop_r()
    state = _make_reabsorb_state(
        {str(parent.id): parent, str(source.id): source},
        tick=SPLINTER_CHECK_STRIDE,
    )
    mutations, events = loop._check_pop_reabsorption(state)
    assert mutations == []  # beliefs too different (orthogonal vectors → similarity ≈ 0)

def test_reabsorption_full_transfer_on_final_absorption():
    """When source drops below SPLINTER_MIN_SIZE, full remaining population is transferred."""
    import math
    from logic.tick_logic import (
        TickLoop, SPLINTER_CHECK_STRIDE, SPLINTER_MIN_SIZE,
        REABSORPTION_DRAIN_FRACTION, MutationType, REABSORPTION_CONVERGENCE_THRESHOLD,
    )
    loc = _uuid4r(); civ = _uuid4r()
    beliefs = {"domain:order": 0.6, "domain:change": 0.3}
    parent = _make_pop_r(beliefs, size=6.0, location_id=loc, civ_id=civ)
    # Source just above min size so one drain puts it below
    source_size = SPLINTER_MIN_SIZE + 0.05
    source = _make_pop_r(beliefs, size=source_size, location_id=loc, civ_id=civ)
    source.parent_pop_id = parent.id

    loop = _make_loop_r()
    state = _make_reabsorb_state(
        {str(parent.id): parent, str(source.id): source},
        tick=SPLINTER_CHECK_STRIDE,
    )
    mutations, events = loop._check_pop_reabsorption(state)

    # Should get: one POP_SIZE_CHANGE for target (full transfer) + one POP_ABSORBED
    size_changes = [m for m in mutations if m.mutation_type == MutationType.POP_SIZE_CHANGE]
    absorbed = [m for m in mutations if m.mutation_type == MutationType.POP_ABSORBED]
    # No POP_SIZE_CHANGE for source (absorbed instead), one for parent (full amount)
    assert len(size_changes) == 1
    assert str(size_changes[0].target_id) == str(parent.id)
    assert size_changes[0].delta > 0
    assert len(absorbed) == 1

    # Verify population conservation: parent gains exactly what source had
    full_transferred = 10 ** source_size
    expected_delta = math.log10(10 ** 6.0 + full_transferred) - 6.0
    assert abs(size_changes[0].delta - expected_delta) < 1e-9
