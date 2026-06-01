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


# ── culture tag nudge on parent after splinter ────────────────────────────

def _make_splinter_state(pop_beliefs, pop_culture, civ_beliefs, civ_culture):
    """Build a minimal SimulationState that will fire a splinter on the first stride tick."""
    from uuid import uuid4
    from core.universe_core import Pop, SocialClass
    from logic.tick_logic import SPLINTER_CHECK_STRIDE
    civ_id = uuid4()
    pop = Pop(
        social_class=SocialClass.COMMON,
        occupation="Artist",
        current_location=uuid4(),
        size_fractional=7.0,
        dominant_beliefs=dict(pop_beliefs),
        culture_tags=dict(pop_culture),
        civilization_id=civ_id,
    )
    civ = MagicMock()
    civ.established_beliefs = dict(civ_beliefs)
    civ.established_culture_tags = dict(civ_culture)
    civ.scale.value = "continental"
    civ.pop_ids = []
    state = MagicMock()
    state.tick_number = SPLINTER_CHECK_STRIDE
    state.pops = {str(pop.id): pop}
    state.civilizations = {str(civ_id): civ}
    state.mortals = {}
    return state, pop


def _run_splinter(pop_beliefs, pop_culture, civ_beliefs, civ_culture):
    """Run _check_pop_splinters and assert a splinter fired. Returns (parent_pop, splinter_pop)."""
    from logic.tick_logic import TickLoop, MutationType
    state, pop = _make_splinter_state(pop_beliefs, pop_culture, civ_beliefs, civ_culture)
    loop = TickLoop(rng_seed=42)
    mutations, _ = loop._check_pop_splinters(state)
    pop_created = [m for m in mutations if m.mutation_type == MutationType.POP_SPLINTER]
    assert pop_created, "Expected a splinter to fire — check divergence setup"
    splinter = pop_created[0].new_value
    return pop, splinter


# Orthogonal beliefs → max divergence → guaranteed splinter with seed 42.
_BELIEFS_A = {"domain:order": 1.0}
_BELIEFS_B = {"domain:chaos": 1.0}


def test_culture_values_tag_nudged_toward_civ_after_splinter():
    parent, _ = _run_splinter(
        pop_beliefs=_BELIEFS_A,
        pop_culture={"values:community": 0.1},
        civ_beliefs=_BELIEFS_B,
        civ_culture={"values:community": 0.9},
    )
    # Parent should have moved toward civ value of 0.9
    assert parent.culture_tags["values:community"] > 0.1


def test_culture_religion_tag_nudged_toward_civ_after_splinter():
    parent, _ = _run_splinter(
        pop_beliefs=_BELIEFS_A,
        pop_culture={"religion:ancestor": 0.1},
        civ_beliefs=_BELIEFS_B,
        civ_culture={"religion:ancestor": 0.9},
    )
    assert parent.culture_tags["religion:ancestor"] > 0.1


def test_culture_religion_nudged_more_than_values_after_splinter():
    """religion: tags shift more than values: tags (1.1× weight)."""
    parent, _ = _run_splinter(
        pop_beliefs=_BELIEFS_A,
        pop_culture={"values:community": 0.1, "religion:ancestor": 0.1},
        civ_beliefs=_BELIEFS_B,
        civ_culture={"values:community": 0.9, "religion:ancestor": 0.9},
    )
    delta_values   = parent.culture_tags["values:community"]  - 0.1
    delta_religion = parent.culture_tags["religion:ancestor"] - 0.1
    assert delta_religion > delta_values


def test_culture_practice_tag_not_nudged_after_splinter():
    parent, _ = _run_splinter(
        pop_beliefs=_BELIEFS_A,
        pop_culture={"practice:art": 0.1},
        civ_beliefs=_BELIEFS_B,
        civ_culture={"practice:art": 0.9},
    )
    assert parent.culture_tags["practice:art"] == pytest.approx(0.1)


def test_splinter_gets_pre_nudge_culture_tags():
    """Splinter should carry the parent's original culture, not the nudged version."""
    parent, splinter = _run_splinter(
        pop_beliefs=_BELIEFS_A,
        pop_culture={"values:community": 0.1},
        civ_beliefs=_BELIEFS_B,
        civ_culture={"values:community": 0.9},
    )
    # Parent moved toward civ; splinter retains original
    assert splinter.culture_tags["values:community"] == pytest.approx(0.1)
    assert parent.culture_tags["values:community"] > splinter.culture_tags["values:community"]


# ── _culture_divergence ────────────────────────────────────────────────────

def test_culture_divergence_zero_with_no_tags():
    from logic.tick_logic import _culture_divergence
    assert _culture_divergence({}, {}) == 0.0

def test_culture_divergence_zero_with_one_side_empty():
    from logic.tick_logic import _culture_divergence
    assert _culture_divergence({"values:community": 0.8}, {}) == 0.0
    assert _culture_divergence({}, {"values:community": 0.8}) == 0.0

def test_culture_divergence_ignores_practice_tags():
    from logic.tick_logic import _culture_divergence
    # Totally different practice: tags — should produce no divergence
    result = _culture_divergence({"practice:art": 0.9}, {"practice:ritual": 0.9})
    assert result == 0.0

def test_culture_divergence_zero_for_identical_values_tags():
    from logic.tick_logic import _culture_divergence
    tags = {"values:community": 0.8, "values:honor": 0.4}
    assert _culture_divergence(tags, tags) < 0.001

def test_culture_divergence_zero_for_identical_religion_tags():
    from logic.tick_logic import _culture_divergence
    tags = {"religion:ancestor_worship": 0.7}
    assert _culture_divergence(tags, tags) < 0.001

def test_culture_divergence_max_for_orthogonal_values_vectors():
    from logic.tick_logic import _culture_divergence
    # Completely different values: keys → orthogonal → cosine distance = 1.0
    result = _culture_divergence({"values:community": 1.0}, {"values:honor": 1.0})
    assert abs(result - 1.0) < 0.001

def test_culture_divergence_religion_mismatch_exceeds_values_mismatch():
    from logic.tick_logic import _culture_divergence
    # Both cases: one dimension matches, one differs.
    # religion mismatch should produce higher divergence than values mismatch
    # because religion tags are weighted 1.1x.
    div_religion_mismatch = _culture_divergence(
        {"religion:A": 1.0, "values:X": 1.0},
        {"religion:B": 1.0, "values:X": 1.0},  # religion differs, values same
    )
    div_values_mismatch = _culture_divergence(
        {"religion:A": 1.0, "values:X": 1.0},
        {"religion:A": 1.0, "values:Y": 1.0},  # values differs, religion same
    )
    assert div_religion_mismatch > div_values_mismatch

def test_culture_divergence_mixed_tags_ignores_practice():
    from logic.tick_logic import _culture_divergence
    # practice: keys present on both sides but shouldn't affect result
    result_with_practice = _culture_divergence(
        {"values:honor": 0.8, "practice:art": 0.9},
        {"values:honor": 0.8, "practice:ritual": 0.9},
    )
    result_without_practice = _culture_divergence(
        {"values:honor": 0.8},
        {"values:honor": 0.8},
    )
    assert abs(result_with_practice - result_without_practice) < 0.001


# ── divergence formula includes culture contribution ───────────────────────

def _make_civ_for_divergence(beliefs, culture_tags):
    from unittest.mock import MagicMock
    from core.universe_core import CivilizationScale
    civ = MagicMock()
    civ.established_beliefs = beliefs
    civ.established_culture_tags = culture_tags
    civ.scale.value = "continental"
    return civ

def test_divergence_nudged_up_by_mismatched_culture():
    """Culture disagreement pushes composite divergence above belief-only value."""
    from logic.tick_logic import _culture_divergence
    from logic.sim_utils import cosine_similarity
    beliefs_pop = {"domain:order": 0.55}
    beliefs_civ = {"domain:order": 0.60}
    culture_pop = {"values:community": 0.9}
    culture_civ = {"values:honor":     0.9}  # orthogonal — max culture divergence

    belief_div  = 1.0 - cosine_similarity(beliefs_pop, beliefs_civ)
    culture_div = _culture_divergence(culture_pop, culture_civ)
    composite   = 0.9 * belief_div + 0.1 * culture_div

    assert composite > belief_div

def test_divergence_nudged_down_by_matching_culture():
    """Culture agreement pulls composite divergence below belief-only value."""
    from logic.tick_logic import _culture_divergence
    from logic.sim_utils import cosine_similarity
    beliefs_pop = {"domain:order": 0.9, "domain:change": 0.1}
    beliefs_civ = {"domain:order": 0.1, "domain:change": 0.9}
    culture_tags = {"values:community": 0.8}  # identical → zero culture divergence

    belief_div  = 1.0 - cosine_similarity(beliefs_pop, beliefs_civ)
    culture_div = _culture_divergence(culture_tags, culture_tags)
    composite   = 0.9 * belief_div + 0.1 * culture_div

    assert composite < belief_div
