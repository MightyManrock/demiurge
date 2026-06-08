"""Tests for Phase 2: Faction Directive Types.

Covers:
  - New Directive model fields (interval_ticks, last_triggered_tick,
    cargo_resource_type, cargo_quantity, target_pop_id, territory_pop_ids)
  - Purpose need gating: only included when pop / mortal has active directives
  - directive_purpose_increment dispatch function
  - compute_pop_priorities 'might as well' always-on forage/collect baseline
"""
import pytest
from uuid import uuid4, UUID
from unittest.mock import MagicMock

from core.universe_core import Directive
from core.agent_core import PopNeed


# ── Group 1: New Directive model fields ───────────────────────────────────────

def test_directive_interval_ticks_default():
    d = Directive()
    assert d.interval_ticks == 0


def test_directive_last_triggered_tick_default():
    d = Directive()
    assert d.last_triggered_tick == 0


def test_directive_cargo_resource_type_default():
    d = Directive()
    assert d.cargo_resource_type is None


def test_directive_cargo_quantity_default():
    d = Directive()
    assert d.cargo_quantity == 0


def test_directive_target_pop_id_default():
    d = Directive()
    assert d.target_pop_id is None


def test_directive_territory_pop_ids_default():
    d = Directive()
    assert d.territory_pop_ids == []


def test_directive_new_fields_settable():
    tp_id = uuid4()
    terr_a = uuid4()
    d = Directive(
        interval_ticks=5,
        last_triggered_tick=3,
        cargo_resource_type="grain",
        cargo_quantity=10,
        target_pop_id=tp_id,
        territory_pop_ids=[terr_a],
    )
    assert d.interval_ticks == 5
    assert d.last_triggered_tick == 3
    assert d.cargo_resource_type == "grain"
    assert d.cargo_quantity == 10
    assert d.target_pop_id == tp_id
    assert d.territory_pop_ids == [terr_a]


# ── Group 2: Purpose need gating in compute_pop_need_profile ─────────────────

def test_purpose_need_absent_without_directives():
    from logic.needs_config import compute_pop_need_profile
    needs = compute_pop_need_profile({}, has_directives=False)
    names = [n.name for n in needs]
    assert "purpose" not in names


def test_purpose_need_present_with_directives():
    from logic.needs_config import compute_pop_need_profile
    needs = compute_pop_need_profile({}, has_directives=True)
    names = [n.name for n in needs]
    assert "purpose" in names


def test_purpose_need_absent_by_default():
    """Calling with no has_directives arg preserves old behaviour."""
    from logic.needs_config import compute_pop_need_profile
    needs = compute_pop_need_profile({})
    names = [n.name for n in needs]
    assert "purpose" not in names


# ── Group 3: directive_purpose_increment dispatch ─────────────────────────────

def test_hold_position_increments_when_actor_at_target():
    from logic.pop_agent_logic import directive_purpose_increment
    loc_id = uuid4()
    d = Directive(directive_type="hold_position", target_location_id=loc_id)
    result = directive_purpose_increment(d, actor_location_id=loc_id)
    assert result > 0.0


def test_hold_position_no_increment_when_actor_elsewhere():
    from logic.pop_agent_logic import directive_purpose_increment
    d = Directive(directive_type="hold_position", target_location_id=uuid4())
    result = directive_purpose_increment(d, actor_location_id=uuid4())
    assert result == 0.0


def test_hold_position_no_increment_when_no_target():
    from logic.pop_agent_logic import directive_purpose_increment
    d = Directive(directive_type="hold_position", target_location_id=None)
    result = directive_purpose_increment(d, actor_location_id=uuid4())
    assert result == 0.0


def test_commerce_directive_returns_zero_for_now():
    """Commerce is not yet wired; dispatch returns 0 until implemented."""
    from logic.pop_agent_logic import directive_purpose_increment
    d = Directive(directive_type="commerce")
    result = directive_purpose_increment(d, actor_location_id=uuid4())
    assert result == 0.0


def test_unknown_directive_type_returns_zero():
    from logic.pop_agent_logic import directive_purpose_increment
    d = Directive(directive_type="unknown_future_type")
    result = directive_purpose_increment(d, actor_location_id=uuid4())
    assert result == 0.0


# ── Group 4: compute_pop_priorities 'might as well' baseline ─────────────────

def _fully_satisfied_pop(occupation: str = "bonded") -> MagicMock:
    """Pop with all needs at 1.0 satisfaction and a known occupation."""
    from core.agent_core import PopAgentState
    pop = MagicMock()
    pop.occupation = MagicMock()
    pop.occupation.value = occupation
    pop.active_directives = []
    pop.culture_tags = {}
    pop.dominant_beliefs = {}
    pop.size_fractional = 1.0
    # Needs all at 1.0 → urgency 0 everywhere
    pop.pop_state = PopAgentState(
        needs=[
            PopNeed(name="nourishment", satisfaction=1.0),
            PopNeed(name="hydration",   satisfaction=1.0),
            PopNeed(name="safety",      satisfaction=1.0),
            PopNeed(name="cohesion",    satisfaction=1.0),
            PopNeed(name="shelter",     satisfaction=1.0),
            PopNeed(name="wanderlust",  satisfaction=1.0),
        ]
    )
    return pop


def test_forage_has_nonzero_weight_when_needs_all_satisfied():
    """Even with no pressing needs, forage gets a small 'might as well' baseline."""
    from logic.pop_agent_logic import compute_pop_priorities
    # Use an occupation with no forage occupation baseline to isolate the signal
    pop = _fully_satisfied_pop(occupation="professional")  # no forage baseline
    priorities = compute_pop_priorities(pop, factions={})
    assert priorities.get("forage", 0.0) > 0.0


def test_collect_has_nonzero_weight_when_needs_all_satisfied():
    """Even with no pressing needs, collect gets a small 'might as well' baseline."""
    from logic.pop_agent_logic import compute_pop_priorities
    # "raider" has hunt/migrate/forage occupation baselines but NO collect baseline
    pop = _fully_satisfied_pop(occupation="raider")
    priorities = compute_pop_priorities(pop, factions={})
    # collect must be > 0 even without occupation baseline driving it
    assert priorities.get("collect", 0.0) > 0.0


def test_might_as_well_baseline_is_small_relative_to_pressed_need():
    """When a need is pressing, its action's priority dominates the baseline."""
    from logic.pop_agent_logic import compute_pop_priorities
    from core.agent_core import PopAgentState
    pop = MagicMock()
    pop.occupation = MagicMock()
    pop.occupation.value = "outcast"  # has forage: 0.20 but no collect baseline
    pop.active_directives = []
    pop.culture_tags = {}
    pop.dominant_beliefs = {}
    pop.size_fractional = 1.0
    # Nourishment is urgent; everything else satisfied
    pop.pop_state = PopAgentState(
        needs=[
            PopNeed(name="nourishment", satisfaction=0.10),  # urgent
            PopNeed(name="hydration",   satisfaction=1.0),
            PopNeed(name="safety",      satisfaction=1.0),
            PopNeed(name="cohesion",    satisfaction=1.0),
            PopNeed(name="shelter",     satisfaction=1.0),
            PopNeed(name="wanderlust",  satisfaction=1.0),
        ]
    )
    priorities = compute_pop_priorities(pop, factions={})
    # forage has occupation: 0.20 (outcast) + urgency; collect has only might-as-well baseline
    # → forage must exceed collect
    assert priorities["forage"] > priorities.get("collect", 0.0)


# ── Group 5: Mortal purpose/status gating in compute_need_profile ────────────

def test_mortal_purpose_absent_without_directives():
    from logic.needs_config import compute_need_profile
    needs = compute_need_profile({}, has_directives=False)
    assert "purpose" not in [n.name for n in needs]


def test_mortal_status_absent_without_directives():
    from logic.needs_config import compute_need_profile
    needs = compute_need_profile({}, has_directives=False)
    assert "status" not in [n.name for n in needs]


def test_mortal_purpose_present_with_directives():
    from logic.needs_config import compute_need_profile
    needs = compute_need_profile({}, has_directives=True)
    assert "purpose" in [n.name for n in needs]


def test_mortal_status_present_with_directives():
    from logic.needs_config import compute_need_profile
    needs = compute_need_profile({}, has_directives=True)
    assert "status" in [n.name for n in needs]


def test_mortal_purpose_absent_by_default():
    from logic.needs_config import compute_need_profile
    needs = compute_need_profile({})
    assert "purpose" not in [n.name for n in needs]


# ── Group 6: hold_position suppresses migration ───────────────────────────────

def test_hold_position_directive_suppresses_migrate_priority():
    """A pop with pressing wanderlust + hold_position directive should have near-zero migrate."""
    from logic.pop_agent_logic import compute_pop_priorities
    from core.agent_core import PopAgentState
    loc_id = uuid4()
    d = Directive(directive_type="hold_position", target_location_id=loc_id)
    pop = MagicMock()
    pop.occupation = MagicMock()
    pop.occupation.value = "nomad"
    pop.active_directives = [d]
    pop.culture_tags = {}
    pop.dominant_beliefs = {}
    pop.size_fractional = 1.0
    pop.current_location = loc_id
    # Wanderlust is urgent, everything else satisfied
    pop.pop_state = PopAgentState(
        needs=[
            PopNeed(name="nourishment", satisfaction=1.0),
            PopNeed(name="hydration",   satisfaction=1.0),
            PopNeed(name="safety",      satisfaction=1.0),
            PopNeed(name="cohesion",    satisfaction=1.0),
            PopNeed(name="shelter",     satisfaction=1.0),
            PopNeed(name="wanderlust",  satisfaction=0.05),  # urgent
        ]
    )
    priorities = compute_pop_priorities(pop, factions={})
    assert priorities.get("migrate", 0.0) <= 0.0


# ── Group 7: initialize_pop_state passes has_directives through ───────────────

def test_initialize_pop_state_no_directives_excludes_purpose():
    from logic.needs_config import initialize_pop_state
    from unittest.mock import MagicMock
    pop = MagicMock()
    pop.culture_tags = {}
    pop.active_directives = []
    state = initialize_pop_state(pop)
    assert "purpose" not in [n.name for n in state.needs]


def test_initialize_pop_state_with_directives_includes_purpose():
    from logic.needs_config import initialize_pop_state
    from unittest.mock import MagicMock
    pop = MagicMock()
    pop.culture_tags = {}
    pop.active_directives = [Directive(directive_type="hold_position")]
    state = initialize_pop_state(pop)
    assert "purpose" in [n.name for n in state.needs]


# ── Group 8: initialize_mortal_state passes has_directives through ────────────

def test_initialize_mortal_state_no_directives_excludes_purpose_and_status():
    from logic.needs_config import initialize_mortal_state
    from unittest.mock import MagicMock
    mortal = MagicMock()
    mortal.culture_tags = {}
    mortal.active_directives = []
    state = initialize_mortal_state(mortal)
    names = [n.name for n in state.needs]
    assert "purpose" not in names
    assert "status" not in names


def test_initialize_mortal_state_with_directives_includes_purpose_and_status():
    from logic.needs_config import initialize_mortal_state
    from unittest.mock import MagicMock
    mortal = MagicMock()
    mortal.culture_tags = {}
    mortal.active_directives = [Directive(directive_type="hold_position")]
    state = initialize_mortal_state(mortal)
    names = [n.name for n in state.needs]
    assert "purpose" in names
    assert "status" in names
