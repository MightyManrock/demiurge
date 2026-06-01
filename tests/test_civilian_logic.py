import pytest
from unittest.mock import MagicMock, patch
from core.agent_core import (
    CivilianAgentState, Resource, MortalNeed, KnowledgeBase,
    RouteFact, LocationQualityFact, ResourceFact, DirectiveFact,
)
from logic.civilian_agent_logic import evaluate_civilian_action, _trip_too_long_for_urgent_need


def _mortal(cs, kb=None, fatigue=0.0, assets=None, travel_intent=None, loc_id="loc-A"):
    m = MagicMock()
    m.civilian_state = cs
    m.knowledge_base = kb or KnowledgeBase()
    m.fatigue = fatigue
    m.assets = assets or []
    m.travel_intent = travel_intent
    m.current_location = loc_id
    return m


def _state(locations=None):
    s = MagicMock()
    s.locations = locations or {}
    return s


def _pressing_need():
    # satisfaction=0.5: pressing (< 0.65) but NOT urgent (>= 0.35), so trip guard won't fire
    return MortalNeed(name="indulgence", satisfaction=0.5, pressing_threshold=0.65)


# No pressing needs → idle

def test_no_pressing_needs_returns_idle():
    cs = CivilianAgentState(
        needs=[MortalNeed(name="indulgence", satisfaction=1.0)],
    )
    result = evaluate_civilian_action(_mortal(cs), _state(), 0)
    assert result == "idle"


# Fatigue gate

def test_fatigue_blocks_action():
    cs = CivilianAgentState(needs=[_pressing_need()])
    result = evaluate_civilian_action(_mortal(cs, fatigue=0.9), _state(), 0)
    assert result == "idle"


# Sell priority: already at sell location

def test_sell_at_sell_location():
    sell_loc_id = "neran-surface"
    cs = CivilianAgentState(
        needs=[_pressing_need()],
        inventory=[Resource(resource_type="unobtanium", quantity=5.0, threshold=2.0, usable_for=["sell"])],
    )
    kb = KnowledgeBase(facts=[
        LocationQualityFact(location_id=sell_loc_id, quality=0.9, quality_type="sell"),
    ])
    result = evaluate_civilian_action(_mortal(cs, kb, loc_id=sell_loc_id), _state(), 0)
    assert result == "sell"


# Sell priority: needs to travel to sell location

def test_sell_triggers_travel_to_sell_location():
    sell_loc_id = "neran-surface"
    cs = CivilianAgentState(
        needs=[_pressing_need()],
        inventory=[Resource(resource_type="unobtanium", quantity=5.0, threshold=2.0, usable_for=["sell"])],
    )
    kb = KnowledgeBase(facts=[
        LocationQualityFact(location_id=sell_loc_id, quality=0.9, quality_type="sell"),
        RouteFact(from_id="sethis", to_id=sell_loc_id, ticks_cost=12),
    ])
    result = evaluate_civilian_action(_mortal(cs, kb, loc_id="sethis"), _state(), 0)
    assert result == f"travel:{sell_loc_id}"


# Sell skipped when unobtanium below threshold

def test_sell_skipped_below_threshold():
    sell_loc_id = "neran-surface"
    cs = CivilianAgentState(
        needs=[_pressing_need()],
        inventory=[Resource(resource_type="unobtanium", quantity=1.0, threshold=2.0, usable_for=["sell"])],
    )
    kb = KnowledgeBase(facts=[
        LocationQualityFact(location_id=sell_loc_id, quality=0.9, quality_type="sell"),
        RouteFact(from_id="sethis", to_id=sell_loc_id, ticks_cost=12),
    ])
    result = evaluate_civilian_action(_mortal(cs, kb, loc_id="sethis"), _state(), 0)
    assert result != f"travel:{sell_loc_id}"


# Spend priority: already at spend location

def test_spend_at_spend_location():
    spend_loc_id = "neran-surface"
    cs = CivilianAgentState(
        needs=[_pressing_need()],
        inventory=[Resource(resource_type="credits", quantity=3.0, threshold=1.0, usable_for=["spend"])],
    )
    kb = KnowledgeBase(facts=[
        LocationQualityFact(location_id=spend_loc_id, quality=0.9, quality_type="spend"),
    ])
    result = evaluate_civilian_action(_mortal(cs, kb, loc_id=spend_loc_id), _state(), 0)
    assert result == "spend"


# Collect priority: at resource location

def test_collect_at_resource_location():
    loc_id = "sethis-surface"
    loc = MagicMock()
    loc.collectible_resource = MagicMock()
    loc.location_type = "pop_location"
    # Collect scores via purpose urgency — mortal collects when purpose is pressing
    cs = CivilianAgentState(needs=[MortalNeed(name="purpose", satisfaction=0.5, pressing_threshold=0.65)])
    kb = KnowledgeBase(facts=[ResourceFact(location_id=loc_id)])
    result = evaluate_civilian_action(_mortal(cs, kb, loc_id=loc_id), _state({loc_id: loc}), 0)
    assert result == "collect"


# Trip-length awareness: helper correctly identifies trips that are too long

def test_trip_too_long_for_urgent_need_true():
    # sustenance is a survival need — satisfaction=0.2, decay=0.05 → 4 ticks to zero < 12-tick trip
    urgent_need = MortalNeed(name="sustenance", satisfaction=0.2, decay_rate=0.05,
                             pressing_threshold=0.65, urgent_threshold=0.35)
    cs = CivilianAgentState(needs=[urgent_need])
    kb = KnowledgeBase(facts=[RouteFact(from_id="sethis", to_id="neran", ticks_cost=12)])
    assert _trip_too_long_for_urgent_need(cs, kb, "neran") is True


# Spend skipped when its target need is not pressing — falls through to collect

def test_spend_skipped_when_target_need_not_pressing():
    """Credits available but indulgence is full → spend doesn't intercept; mortal travels to collect."""
    spend_loc_id = "neran-surface"
    resource_loc_id = "sethis-surface"
    loc = MagicMock()
    loc.collectible_resource = MagicMock()
    loc.location_type = "pop_location"
    cs = CivilianAgentState(
        needs=[
            MortalNeed(name="purpose", satisfaction=0.5, pressing_threshold=0.65),
            MortalNeed(name="indulgence", satisfaction=1.0, pressing_threshold=0.65),
        ],
        inventory=[
            Resource(resource_type="credits", quantity=81.0, threshold=1.0,
                     usable_for=["spend"], fills_need="indulgence"),
        ],
    )
    kb = KnowledgeBase(facts=[
        LocationQualityFact(location_id=spend_loc_id, quality=0.9, quality_type="spend"),
        ResourceFact(location_id=resource_loc_id),
        RouteFact(from_id=spend_loc_id, to_id=resource_loc_id, ticks_cost=2),
    ])
    result = evaluate_civilian_action(
        _mortal(cs, kb, loc_id=spend_loc_id),
        _state({resource_loc_id: loc}),
        0,
    )
    assert result == f"travel:{resource_loc_id}"


def test_trip_too_long_for_urgent_need_false_when_not_urgent():
    # sustenance not yet urgent → no block
    need = MortalNeed(name="sustenance", satisfaction=0.5, decay_rate=0.05,
                      pressing_threshold=0.65, urgent_threshold=0.35)
    cs = CivilianAgentState(needs=[need])
    kb = KnowledgeBase(facts=[RouteFact(from_id="sethis", to_id="neran", ticks_cost=12)])
    assert _trip_too_long_for_urgent_need(cs, kb, "neran") is False


def test_trip_too_long_non_survival_need_does_not_block():
    # status urgent → must NOT block travel
    urgent_need = MortalNeed(name="status", satisfaction=0.1, decay_rate=0.03,
                             pressing_threshold=0.60, urgent_threshold=0.25)
    cs = CivilianAgentState(needs=[urgent_need])
    kb = KnowledgeBase(facts=[RouteFact(from_id="neran", to_id="sethis", ticks_cost=12)])
    assert _trip_too_long_for_urgent_need(cs, kb, "sethis") is False


# ── Leisure and socialize actions ────────────────────────────────────────────

POP_ID = "pop-abc"


def _mortal_with_pop(cs, pop_id=POP_ID, pop_milieu=None, fatigue=0.0, loc_id="loc-A"):
    m = MagicMock()
    m.civilian_state = cs
    m.knowledge_base = KnowledgeBase()
    m.fatigue = fatigue
    m.assets = []
    m.travel_intent = None
    m.current_location = loc_id
    m.pop_id = pop_id
    m.pop_milieu = pop_milieu
    m.culture_tags = {}
    return m


def _state_with_pop(pop_id=POP_ID, pop_tags=None):
    pop = MagicMock()
    pop.culture_tags = pop_tags or {"values:solidarity": 0.6, "practice:music": 0.7}
    s = MagicMock()
    s.locations = {}
    s.pops = {pop_id: pop}
    return s


def _pressing(name: str) -> MortalNeed:
    return MortalNeed(name=name, satisfaction=0.4, pressing_threshold=0.65, urgent_threshold=0.20)


def test_leisure_action_when_pressing_at_pop():
    cs = CivilianAgentState(needs=[_pressing("leisure")])
    result = evaluate_civilian_action(
        _mortal_with_pop(cs),
        _state_with_pop(),
        0,
    )
    assert result == "leisure"


def test_leisure_skipped_when_gain_below_decay_rate():
    """Leisure is bypassed (→ idle) when expected gain would not cover per-tick decay."""
    # High decay_rate ensures gain < decay, so leisure is pointless
    cs = CivilianAgentState(
        needs=[MortalNeed(name="leisure", satisfaction=0.4,
                          pressing_threshold=0.65, decay_rate=0.99)]
    )
    result = evaluate_civilian_action(_mortal_with_pop(cs), _state_with_pop(), 0)
    assert result == "idle"


def test_socialize_action_when_pressing_at_pop():
    cs = CivilianAgentState(needs=[_pressing("belonging")])
    result = evaluate_civilian_action(
        _mortal_with_pop(cs),
        _state_with_pop(),
        0,
    )
    assert result == "socialize"


def test_leisure_skipped_when_not_pressing():
    cs = CivilianAgentState(
        needs=[MortalNeed(name="leisure", satisfaction=0.9, pressing_threshold=0.65)]
    )
    result = evaluate_civilian_action(
        _mortal_with_pop(cs),
        _state_with_pop(),
        0,
    )
    assert result == "idle"


def test_socialize_skipped_when_not_pressing():
    cs = CivilianAgentState(
        needs=[MortalNeed(name="belonging", satisfaction=0.9, pressing_threshold=0.65)]
    )
    result = evaluate_civilian_action(
        _mortal_with_pop(cs),
        _state_with_pop(),
        0,
    )
    assert result == "idle"


def test_leisure_skipped_without_pop_in_state():
    cs = CivilianAgentState(needs=[_pressing("leisure")])
    s = MagicMock()
    s.locations = {}
    s.pops = {}  # no pop present
    result = evaluate_civilian_action(_mortal_with_pop(cs), s, 0)
    assert result == "idle"


def test_leisure_uses_pop_milieu_over_pop_id():
    """pop_milieu takes precedence over pop_id for location lookup."""
    milieu_id = "pop-milieu-xyz"
    other_id  = "pop-other"
    cs = CivilianAgentState(needs=[_pressing("leisure")])
    mortal = _mortal_with_pop(cs, pop_id=other_id, pop_milieu=milieu_id)
    pop = MagicMock()
    pop.culture_tags = {"practice:music": 0.8}
    s = MagicMock()
    s.locations = {}
    s.pops = {milieu_id: pop}  # only milieu is present
    result = evaluate_civilian_action(mortal, s, 0)
    assert result == "leisure"



def test_leisure_priority_above_collect():
    """Leisure fires before collect when both leisure need is pressing and resource exists."""
    resource_loc = "resource-loc"
    cs = CivilianAgentState(
        needs=[_pressing("leisure")],
        # no sellable or spendable items, but a known resource location
    )
    kb = KnowledgeBase(facts=[ResourceFact(location_id=resource_loc)])
    mortal = _mortal_with_pop(cs)
    mortal.knowledge_base = kb
    loc = MagicMock()
    loc.collectible_resource = MagicMock()
    result = evaluate_civilian_action(
        mortal,
        _state_with_pop(),
        0,
    )
    assert result == "leisure"


# ── "Might as well" factor ────────────────────────────────────────────────────

def _directive_mortal(resource_loc_id="res-loc", loc_id="res-loc", culture_tags=None):
    """Mortal with a commerce directive, all needs satisfied (none pressing)."""
    cs = CivilianAgentState(
        needs=[MortalNeed(name="purpose", satisfaction=0.9, pressing_threshold=0.65)],
    )
    kb = KnowledgeBase(facts=[
        DirectiveFact(directive_id="d1", directive_type="commerce",
                      satisfying_action="sell", target_pop_location_id="loc-123"),
        ResourceFact(location_id=resource_loc_id),
    ])
    m = MagicMock()
    m.civilian_state = cs
    m.knowledge_base = kb
    m.fatigue = 0.0
    m.assets = []
    m.travel_intent = None
    m.current_location = loc_id
    m.culture_tags = culture_tags or {}
    return m


def test_might_as_well_roll_succeeds_triggers_collect():
    """When roll succeeds the mortal collects despite purpose not being pressing."""
    mortal = _directive_mortal()
    loc = MagicMock()
    loc.collectible_resource = MagicMock()
    loc.location_type = "pop_location"
    state = MagicMock()
    state.locations = {"res-loc": loc}
    state.pops = {}
    with patch("logic.civilian_agent_logic.random.random", return_value=0.0):  # always succeeds
        result = evaluate_civilian_action(mortal, state, 0)
    assert result == "collect"


def test_might_as_well_roll_fails_returns_idle():
    """When roll fails the mortal idles even with an active directive."""
    mortal = _directive_mortal()
    state = MagicMock()
    state.locations = {}
    state.pops = {}
    with patch("logic.civilian_agent_logic.random.random", return_value=1.0):  # always fails
        result = evaluate_civilian_action(mortal, state, 0)
    assert result == "idle"


def test_might_as_well_culture_boosts_prob():
    """values:tenacity and values:prowess raise probability above base."""
    from logic.civilian_agent_logic import _might_as_well_prob, MIGHT_AS_WELL_BASE_PROB
    tags = {"values:tenacity": 1.0, "values:prowess": 1.0}
    assert _might_as_well_prob(tags) > MIGHT_AS_WELL_BASE_PROB


def test_might_as_well_culture_reduces_prob():
    """values:indulgence and values:moderation lower probability below base."""
    from logic.civilian_agent_logic import _might_as_well_prob, MIGHT_AS_WELL_BASE_PROB
    tags = {"values:indulgence": 1.0, "values:moderation": 1.0}
    assert _might_as_well_prob(tags) < MIGHT_AS_WELL_BASE_PROB


def test_might_as_well_prob_clamped():
    """Probability stays within [0.05, 0.60] regardless of tag extremes."""
    from logic.civilian_agent_logic import _might_as_well_prob
    extreme_boost = {t: 10.0 for t in ["values:tenacity", "values:prowess", "values:prosperity", "values:pragmatism"]}
    extreme_reduce = {t: 10.0 for t in ["values:indulgence", "values:moderation"]}
    assert _might_as_well_prob(extreme_boost) == pytest.approx(0.60)
    assert _might_as_well_prob(extreme_reduce) == pytest.approx(0.05)


# ── Cosine similarity and new _pop_social_quality signature tests ──────────────

from logic.civilian_agent_logic import _cosine_sim, _pop_social_quality


def test_cosine_sim_identical_vectors():
    v = {"domain:fire": 0.8, "values:honor": 0.5}
    assert _cosine_sim(v, v) == pytest.approx(1.0, abs=0.01)


def test_cosine_sim_empty_returns_neutral():
    assert _cosine_sim({}, {}) == pytest.approx(0.5)
    assert _cosine_sim({"a": 0.5}, {}) == pytest.approx(0.5)


def test_cosine_sim_orthogonal_vectors():
    a = {"domain:fire": 0.8}
    b = {"domain:water": 0.8}
    assert _cosine_sim(a, b) == pytest.approx(0.5)  # no overlap → normalized 0.5


def test_pop_social_quality_new_signature_accepted():
    score = _pop_social_quality(
        mortal_beliefs={"domain:fire": 0.7},
        mortal_culture={"values:honor": 0.6},
        pop_beliefs={"domain:fire": 0.7},
        pop_culture={"values:honor": 0.6, "values:solidarity": 0.8, "practice:revelry": 0.7},
        same_species=True,
        same_civ=True,
    )
    assert 0.0 <= score <= 1.0
