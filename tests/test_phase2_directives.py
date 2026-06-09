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


# ── Group 9: territory_pop_ids scoping on faction directives ──────────────────

def _pop_with_faction_hold_position(pop_id, faction_id, target_loc_id, territory_ids):
    """Pop belonging to a faction that has a scoped hold_position directive."""
    from core.agent_core import PopAgentState
    from unittest.mock import MagicMock
    d = Directive(
        directive_type="hold_position",
        target_location_id=target_loc_id,
        territory_pop_ids=territory_ids,
    )
    faction = MagicMock()
    faction.active_directives = [d]

    pop = MagicMock()
    pop.id = pop_id
    pop.occupation = MagicMock()
    pop.occupation.value = "nomad"
    pop.active_directives = []
    pop.culture_tags = {}
    pop.dominant_beliefs = {}
    pop.size_fractional = 1.0
    pop.current_location = target_loc_id
    pop.pop_state = PopAgentState(
        needs=[
            PopNeed(name="nourishment", satisfaction=1.0),
            PopNeed(name="hydration",   satisfaction=1.0),
            PopNeed(name="safety",      satisfaction=1.0),
            PopNeed(name="cohesion",    satisfaction=1.0),
            PopNeed(name="shelter",     satisfaction=1.0),
            PopNeed(name="wanderlust",  satisfaction=0.05),
        ]
    )
    return pop, {str(faction_id): faction}


def test_hold_position_suppresses_migrate_for_pop_in_territory():
    """Pop listed in territory_pop_ids gets migration suppressed."""
    from logic.pop_agent_logic import compute_pop_priorities
    pop_id = uuid4()
    faction_id = uuid4()
    target = uuid4()
    pop, factions = _pop_with_faction_hold_position(pop_id, faction_id, target, [pop_id])
    pop.faction_ids = [faction_id]
    priorities = compute_pop_priorities(pop, factions=factions)
    assert priorities.get("migrate", 0.0) <= 0.0


def test_hold_position_does_not_suppress_migrate_for_pop_outside_territory():
    """Pop NOT in territory_pop_ids is unaffected by the directive."""
    from logic.pop_agent_logic import compute_pop_priorities
    other_pop_id = uuid4()
    faction_id = uuid4()
    target = uuid4()
    pop_id = uuid4()  # different from territory list
    pop, factions = _pop_with_faction_hold_position(pop_id, faction_id, target, [other_pop_id])
    pop.faction_ids = [faction_id]
    priorities = compute_pop_priorities(pop, factions=factions)
    assert priorities.get("migrate", 0.0) > 0.0


# ── Group 10: patrol directive ────────────────────────────────────────────────

def test_patrol_adds_fortify_and_hunt_modifier_at_patrol_location():
    """_collect_directive_modifiers adds fortify+hunt boost when pop is at a patrol location."""
    from logic.pop_agent_logic import _collect_directive_modifiers
    loc_id = uuid4()
    d = Directive(directive_type="patrol", territory_location_ids=[loc_id])
    faction = MagicMock()
    faction.active_directives = [d]
    pop = MagicMock()
    pop.id = uuid4()
    pop.active_directives = []
    faction_id = uuid4()
    pop.faction_ids = [faction_id]
    pop.current_location = loc_id
    mods = _collect_directive_modifiers(pop, {str(faction_id): faction})
    assert mods.get("fortify", 0.0) > 0.0
    assert mods.get("hunt", 0.0) > 0.0
    assert mods.get("migrate", 0.0) == 0.0


def test_patrol_no_modifier_outside_patrol_location():
    """No modifiers applied when pop is not at any patrol location."""
    from logic.pop_agent_logic import _collect_directive_modifiers
    patrol_loc = uuid4()
    other_loc = uuid4()
    d = Directive(directive_type="patrol", territory_location_ids=[patrol_loc])
    faction = MagicMock()
    faction.active_directives = [d]
    pop = MagicMock()
    pop.id = uuid4()
    pop.active_directives = []
    faction_id = uuid4()
    pop.faction_ids = [faction_id]
    pop.current_location = other_loc
    mods = _collect_directive_modifiers(pop, {str(faction_id): faction})
    assert mods.get("fortify", 0.0) == 0.0
    assert mods.get("hunt", 0.0) == 0.0


def test_patrol_purpose_increment_at_patrol_location():
    """directive_purpose_increment returns > 0 when actor is at a patrol location."""
    from logic.pop_agent_logic import directive_purpose_increment
    loc_id = uuid4()
    d = Directive(directive_type="patrol", territory_location_ids=[loc_id])
    assert directive_purpose_increment(d, actor_location_id=loc_id) > 0.0


def test_patrol_no_purpose_increment_outside_patrol():
    """directive_purpose_increment returns 0 when not at any patrol location."""
    from logic.pop_agent_logic import directive_purpose_increment
    patrol_loc = uuid4()
    other_loc = uuid4()
    d = Directive(directive_type="patrol", territory_location_ids=[patrol_loc])
    assert directive_purpose_increment(d, actor_location_id=other_loc) == 0.0


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


# ── Group 11: supply_run directive ────────────────────────────────────────────

def _make_supply_run_directive(src_id, dst_pop_id):
    return Directive(
        directive_type="supply_run",
        target_location_id=src_id,
        target_pop_id=dst_pop_id,
        cargo_resource_type="food:grain",
        cargo_quantity=10,
    )


def test_supply_run_phase_load_at_source_empty_cargo():
    from logic.pop_agent_logic import _supply_run_phase
    from core.agent_core import PopAgentState
    src_id = uuid4()
    dst_pop_id = uuid4()
    d = _make_supply_run_directive(src_id, dst_pop_id)
    pop = MagicMock()
    pop.current_location = src_id
    pop.pop_state = PopAgentState()
    dest_pop = MagicMock(); dest_pop.current_location = uuid4()
    assert _supply_run_phase(pop, d, {str(dst_pop_id): dest_pop}) == "load"


def test_supply_run_phase_travel_to_dest_at_source_with_cargo():
    from logic.pop_agent_logic import _supply_run_phase
    from core.agent_core import PopAgentState
    src_id = uuid4()
    dst_pop_id = uuid4()
    d = _make_supply_run_directive(src_id, dst_pop_id)
    pop = MagicMock()
    pop.current_location = src_id
    state = PopAgentState()
    state.cargo.quantities["food:grain"] = 10.0
    pop.pop_state = state
    dest_pop = MagicMock(); dest_pop.current_location = uuid4()
    assert _supply_run_phase(pop, d, {str(dst_pop_id): dest_pop}) == "travel_to_dest"


def test_supply_run_phase_deposit_at_dest_with_cargo():
    from logic.pop_agent_logic import _supply_run_phase
    from core.agent_core import PopAgentState
    src_id = uuid4()
    dst_pop_id = uuid4()
    dst_loc_id = uuid4()
    d = _make_supply_run_directive(src_id, dst_pop_id)
    pop = MagicMock()
    pop.current_location = dst_loc_id
    state = PopAgentState()
    state.cargo.quantities["food:grain"] = 10.0
    pop.pop_state = state
    dest_pop = MagicMock(); dest_pop.current_location = dst_loc_id
    assert _supply_run_phase(pop, d, {str(dst_pop_id): dest_pop}) == "deposit"


def test_supply_run_phase_travel_home_elsewhere_empty_cargo():
    from logic.pop_agent_logic import _supply_run_phase
    from core.agent_core import PopAgentState
    src_id = uuid4()
    dst_pop_id = uuid4()
    d = _make_supply_run_directive(src_id, dst_pop_id)
    pop = MagicMock()
    pop.current_location = uuid4()  # neither source nor dest
    pop.pop_state = PopAgentState()
    dest_pop = MagicMock(); dest_pop.current_location = uuid4()
    assert _supply_run_phase(pop, d, {str(dst_pop_id): dest_pop}) == "travel_home"


def test_supply_run_load_cargo_modifier_boosted_at_source():
    from logic.pop_agent_logic import _collect_directive_modifiers
    from core.agent_core import PopAgentState
    src_id = uuid4()
    dst_pop_id = uuid4()
    d = _make_supply_run_directive(src_id, dst_pop_id)
    faction = MagicMock(); faction.active_directives = [d]
    faction_id = uuid4()
    pop = MagicMock()
    pop.id = uuid4()
    pop.active_directives = []
    pop.faction_ids = [faction_id]
    pop.current_location = src_id
    pop.pop_state = PopAgentState()  # empty cargo → load phase
    dest_pop = MagicMock(); dest_pop.current_location = uuid4()
    mods = _collect_directive_modifiers(pop, {str(faction_id): faction}, pops={str(dst_pop_id): dest_pop})
    assert mods.get("load_cargo", 0.0) > 0.0


def test_supply_run_purpose_increment_on_deposit():
    from logic.pop_agent_logic import directive_purpose_increment
    from core.agent_core import PopAgentState
    src_id = uuid4()
    dst_pop_id = uuid4()
    dst_loc_id = uuid4()
    d = _make_supply_run_directive(src_id, dst_pop_id)
    state = PopAgentState()
    state.cargo.quantities["food:grain"] = 10.0
    pop = MagicMock()
    pop.current_location = dst_loc_id
    pop.pop_state = state
    dest_pop = MagicMock(); dest_pop.current_location = dst_loc_id
    inc = directive_purpose_increment(d, actor_location_id=dst_loc_id, pop=pop, pops={str(dst_pop_id): dest_pop})
    assert inc > 0.0


# ── Group 12: supply_run skip logic ──────────────────────────────────────────

def _make_supply_run_directive_with_interval(src_id, dst_pop_id, interval_ticks=0):
    return Directive(
        directive_type="supply_run",
        target_location_id=src_id,
        target_pop_id=dst_pop_id,
        cargo_resource_type="food_flora",
        cargo_quantity=5,
        interval_ticks=interval_ticks,
    )


def test_supply_run_skip_still_executes_travel_home():
    """Carrier at destination with active skip still gets travel_home: pending_migration_dest = src_id.

    Skip only blocks the load phase. A carrier returning home after depositing must
    still be sent home even while the skip is active.
    """
    from logic.pop_agent_logic import resolve_pop_actions
    from core.agent_core import PopAgentState, ResourceStockpile
    from core.universe_core import PopLocation

    src_id = uuid4()
    dst_pop_id = uuid4()
    d = _make_supply_run_directive_with_interval(src_id, dst_pop_id)

    arbitrary_loc_id = uuid4()
    pop_loc = PopLocation(id=arbitrary_loc_id, name="Nowhere", location_type="city")

    dest_pop = MagicMock()
    dest_pop.current_location = uuid4()

    pop = MagicMock()
    pop.id = uuid4()
    pop.active_directives = [d]
    pop.faction_ids = []
    pop.band_id = None
    pop.size_fractional = 1.0
    pop.occupation = "producer"
    pop.stratum = "common"
    pop.current_location = arbitrary_loc_id
    pop.migration_travel_location_id = None
    ps = PopAgentState()
    # No cargo at non-home location → travel_home phase; skip is active
    ps.supply_run_skip_until[str(d.id)] = 999
    pop.pop_state = ps

    state = MagicMock()
    state.pops = {str(dst_pop_id): dest_pop}

    resolve_pop_actions(
        pop, pop_loc=pop_loc, priorities={}, n_slots=3,
        factions={}, current_tick=5,
        colocated_pops=[pop], state=state,
    )
    # travel_home still runs during skip — carrier is pointed home
    assert ps.pending_migration_dest == src_id


def test_supply_run_skip_prevents_load():
    """Carrier at home with active skip does not boost load_cargo priority.

    Skip blocks the load phase so the carrier acts on normal need priorities instead
    of immediately starting another outbound run.
    """
    from logic.pop_agent_logic import resolve_pop_actions
    from core.agent_core import PopAgentState, ResourceStockpile
    from core.universe_core import PopLocation

    src_id = uuid4()
    dst_pop_id = uuid4()
    d = _make_supply_run_directive_with_interval(src_id, dst_pop_id)

    # Carrier is at home (src_id) with no cargo → load phase
    home_loc = PopLocation(id=src_id, name="Home", location_type="city")

    dest_pop = MagicMock()
    dest_pop.current_location = uuid4()

    pop = MagicMock()
    pop.id = uuid4()
    pop.active_directives = [d]
    pop.faction_ids = []
    pop.band_id = None
    pop.size_fractional = 1.0
    pop.occupation = "producer"
    pop.stratum = "common"
    pop.current_location = src_id
    pop.migration_travel_location_id = None
    ps = PopAgentState()
    # Skip is active
    ps.supply_run_skip_until[str(d.id)] = 999
    pop.pop_state = ps

    state = MagicMock()
    state.pops = {str(dst_pop_id): dest_pop}

    priorities: dict = {}
    resolve_pop_actions(
        pop, pop_loc=home_loc, priorities=priorities, n_slots=3,
        factions={}, current_tick=5,
        colocated_pops=[pop], state=state,
    )
    # Skip active at home → load_cargo should NOT be boosted
    assert "load_cargo" not in priorities or priorities.get("load_cargo", 0.0) == 0.0


def test_supply_run_deposit_sets_skip_when_stockpile_adequate():
    """After depositing into a well-stocked destination, carrier sets skip_until.

    random.uniform is patched to 1.0 for determinism.
    Pre-stocked stockpile: 50 units; carrier delivers 5 → post-deposit = 55.
    1 small co-located Pop (demand = log(2) ≈ 0.69). Ratio ≈ 79 >> 1.0 → skip set.
    skip_until = current_tick + interval_ticks = 10 + 8 = 18.
    """
    from unittest.mock import patch
    from logic.pop_agent_logic import resolve_pop_actions
    from core.agent_core import PopAgentState, ResourceStockpile
    from core.universe_core import PopLocation

    src_id = uuid4()
    dst_pop_id = uuid4()
    dst_loc_id = uuid4()
    d = _make_supply_run_directive_with_interval(src_id, dst_pop_id, interval_ticks=8)

    pop_loc = PopLocation(id=dst_loc_id, name="Dest", location_type="city")
    # Pre-stock public stockpile with 50 units so post-deposit becomes 55
    pop_loc._public_stockpile().quantities["food_flora"] = 50.0

    dest_pop = MagicMock()
    dest_pop.current_location = dst_loc_id

    pop = MagicMock()
    pop.id = uuid4()
    pop.active_directives = [d]
    pop.faction_ids = []
    pop.band_id = None
    pop.size_fractional = 2.0
    pop.occupation = "producer"
    pop.stratum = "common"
    pop.current_location = dst_loc_id
    pop.migration_travel_location_id = None
    ps = PopAgentState()
    ps.cargo.quantities["food_flora"] = 5.0
    pop.pop_state = ps

    state = MagicMock()
    state.pops = {str(dst_pop_id): dest_pop}

    colocated = MagicMock()
    colocated.id = dst_pop_id
    colocated.size_fractional = 1.0
    colocated.faction_ids = []
    colocated.band_id = None

    with patch("logic.pop_agent_logic.random.uniform", return_value=1.0):
        resolve_pop_actions(
            pop, pop_loc=pop_loc, priorities={}, n_slots=3,
            factions={}, current_tick=10,
            colocated_pops=[pop, colocated], state=state,
        )
    # skip_until = current_tick + interval_ticks = 10 + 8 = 18
    assert ps.supply_run_skip_until.get(str(d.id), 0) == 18


def test_supply_run_deposit_no_skip_when_demand_exceeds_stockpile():
    """After depositing a small amount into a high-demand destination, no skip is set.

    random.uniform is patched to 1.0 for determinism.
    5 large co-located Pops (demand = 5 * log(6) ≈ 8.97).
    Carrier delivers 5 units into empty stockpile → post-deposit = 5 units.
    Ratio = 5 / 8.97 ≈ 0.56 < 1.0 → no skip.
    """
    from unittest.mock import patch
    from logic.pop_agent_logic import resolve_pop_actions
    from core.agent_core import PopAgentState, ResourceStockpile
    from core.universe_core import PopLocation

    src_id = uuid4()
    dst_pop_id = uuid4()
    dst_loc_id = uuid4()
    d = _make_supply_run_directive_with_interval(src_id, dst_pop_id, interval_ticks=8)

    pop_loc = PopLocation(id=dst_loc_id, name="Dest", location_type="city")

    dest_pop = MagicMock()
    dest_pop.current_location = dst_loc_id

    pop = MagicMock()
    pop.id = uuid4()
    pop.active_directives = [d]
    pop.faction_ids = []
    pop.band_id = None
    pop.size_fractional = 2.0
    pop.occupation = "producer"
    pop.stratum = "common"
    pop.current_location = dst_loc_id
    pop.migration_travel_location_id = None
    ps = PopAgentState()
    ps.cargo.quantities["food_flora"] = 5.0
    pop.pop_state = ps

    state = MagicMock()
    state.pops = {str(dst_pop_id): dest_pop}

    # 5 large co-located Pops (size=5.0 each), all different from carrier
    colocated_pops = [pop]
    for _ in range(5):
        cp = MagicMock()
        cp.id = uuid4()
        cp.size_fractional = 5.0
        cp.faction_ids = []
        cp.band_id = None
        colocated_pops.append(cp)

    with patch("logic.pop_agent_logic.random.uniform", return_value=1.0):
        resolve_pop_actions(
            pop, pop_loc=pop_loc, priorities={}, n_slots=3,
            factions={}, current_tick=10,
            colocated_pops=colocated_pops, state=state,
        )
    assert ps.supply_run_skip_until.get(str(d.id), 0) == 0


# ── Group 13: Pop TravelLocation integration ──────────────────────────────────

def _make_migrate_pop(origin_id, dest_id):
    """Return a minimal pop mock ready to trigger migrate action."""
    from core.agent_core import PopAgentState
    pop = MagicMock()
    pop.id = uuid4()
    pop.current_location = origin_id
    pop.migration_travel_location_id = None
    pop.migration_ticks_remaining = 0
    pop.migration_destination_id = None
    pop.band_id = None
    pop.faction_ids = []
    pop.size_fractional = 1.0
    pop.occupation = "producer"
    pop.stratum = "common"
    pop.active_directives = []
    ps = PopAgentState()
    ps.pending_migration_dest = dest_id
    pop.pop_state = ps
    return pop, ps


def test_migrate_sets_current_location_to_travel_location():
    """After resolving a migrate action, pop.current_location is the TravelLocation, not the origin."""
    from unittest.mock import patch, MagicMock
    from logic.pop_agent_logic import resolve_pop_actions
    from core.universe_core import PopLocation

    origin_id = uuid4()
    dest_id = uuid4()
    tl_id = uuid4()

    pop, ps = _make_migrate_pop(origin_id, dest_id)
    pop_loc = PopLocation(id=origin_id, name="Origin", location_type="city")

    mock_tl = MagicMock()
    mock_tl.id = tl_id
    mock_tl.pop_ids = []

    state = MagicMock()
    state.pops = {}
    state.mortals = {}

    with patch("utilities.travel_routing.find_route", return_value=[origin_id, dest_id]), \
         patch("utilities.travel_routing.route_fact_cost", return_value=2), \
         patch("utilities.travel_routing.get_or_create_travel_location", return_value=mock_tl):
        resolve_pop_actions(
            pop, pop_loc=pop_loc, priorities={"migrate": 5.0},
            n_slots=2, factions={}, current_tick=1, state=state,
        )

    assert pop.current_location == tl_id
    assert pop.id in mock_tl.pop_ids
    assert pop.migration_travel_location_id == tl_id


def test_in_transit_blocks_migrate_and_collect():
    """When in_transit=True, migrate and collect are stripped from the priority list."""
    from logic.pop_agent_logic import resolve_pop_actions
    from core.agent_core import PopAgentState
    from core.universe_core import PopLocation

    loc_id = uuid4()
    pop = MagicMock()
    pop.id = uuid4()
    pop.current_location = loc_id
    pop.migration_travel_location_id = uuid4()
    pop.migration_ticks_remaining = 2
    pop.band_id = None
    pop.faction_ids = []
    pop.size_fractional = 1.0
    pop.occupation = "producer"
    pop.stratum = "common"
    pop.active_directives = []
    ps = PopAgentState()
    ps.pending_migration_dest = uuid4()
    pop.pop_state = ps

    pop_loc = PopLocation(id=loc_id, name="Waypoint", location_type="wilderness")

    state = MagicMock()
    state.pops = {}
    state.mortals = {}

    resolved = resolve_pop_actions(
        pop, pop_loc=pop_loc,
        priorities={"migrate": 5.0, "collect": 3.0, "forage": 1.0},
        n_slots=2, factions={}, current_tick=1, state=state, in_transit=True,
    )

    assert "migrate" not in resolved
    assert "collect" not in resolved


def test_predeparture_cargo_loads_from_accessible_stockpile():
    """Before migrating, the pop's cargo is filled from accessible stockpiles at origin."""
    from unittest.mock import patch
    from logic.pop_agent_logic import resolve_pop_actions
    from core.agent_core import PopAgentState, ResourceStockpile
    from core.universe_core import PopLocation

    origin_id = uuid4()
    dest_id = uuid4()
    tl_id = uuid4()

    pop, ps = _make_migrate_pop(origin_id, dest_id)
    # Give pop access to the stockpile (band_id=None, faction_ids=[] → only public)
    stk = ResourceStockpile()  # public stockpile
    stk.quantities["food_flora"] = 15.0
    pop_loc = PopLocation(id=origin_id, name="Origin", location_type="city")
    pop_loc.stockpiles.append(stk)

    mock_tl = MagicMock()
    mock_tl.id = tl_id
    mock_tl.pop_ids = []

    state = MagicMock()
    state.pops = {}
    state.mortals = {}

    with patch("utilities.travel_routing.find_route", return_value=[origin_id, dest_id]), \
         patch("utilities.travel_routing.route_fact_cost", return_value=1), \
         patch("utilities.travel_routing.get_or_create_travel_location", return_value=mock_tl):
        resolve_pop_actions(
            pop, pop_loc=pop_loc, priorities={"migrate": 5.0},
            n_slots=2, factions={}, current_tick=1, state=state,
        )

    assert sum(ps.cargo.quantities.values()) > 0
    assert stk.quantities.get("food_flora", 0.0) < 15.0


def test_in_transit_forage_goes_to_cargo():
    """While in transit, forage output is routed to CargoStockpile, not the public stockpile."""
    from logic.pop_agent_logic import resolve_pop_actions
    from core.agent_core import PopAgentState, CollectibleResource
    from core.universe_core import PopLocation

    loc_id = uuid4()
    pop = MagicMock()
    pop.id = uuid4()
    pop.current_location = loc_id
    pop.migration_travel_location_id = uuid4()
    pop.migration_ticks_remaining = 2
    pop.band_id = None
    pop.faction_ids = []
    pop.size_fractional = 1.0
    pop.occupation = "forager"
    pop.stratum = "common"
    pop.active_directives = []
    ps = PopAgentState()
    ps.pending_migration_dest = uuid4()
    pop.pop_state = ps

    cr = CollectibleResource(resource_type="food_flora", action_types=["forage"], current_yield=20.0)
    pop_loc = PopLocation(id=loc_id, name="Waypoint", location_type="wilderness")
    pop_loc.collectible_resources.append(cr)

    state = MagicMock()
    state.pops = {}
    state.mortals = {}

    initial_public = sum(s.quantities.get("food_flora", 0.0) for s in pop_loc.stockpiles)

    resolve_pop_actions(
        pop, pop_loc=pop_loc,
        priorities={"forage": 5.0},
        n_slots=1, factions={}, current_tick=1, state=state, in_transit=True,
    )

    public_after = sum(s.quantities.get("food_flora", 0.0) for s in pop_loc.stockpiles)
    assert public_after == initial_public  # nothing went to shared stockpile
    assert ps.cargo.quantities.get("food_flora", 0.0) > 0
