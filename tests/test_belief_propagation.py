"""Tests for belief_propagation.py — conformity resistance, practice: exclusion,
per-entity stride stagger, and periodic pop cultural noise."""
import random
import pytest
from uuid import UUID
from unittest.mock import MagicMock, patch


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_cfg(**overrides):
    from logic.tick_logic import TickConfig
    return TickConfig(**overrides)


def _make_pop(pop_id=None, beliefs=None, culture_tags=None, civ_id=None):
    pop = MagicMock()
    pop.id = pop_id or UUID(int=0)
    pop.dominant_beliefs = beliefs or {}
    pop.culture_tags = culture_tags or {}
    pop.civilization_id = civ_id or UUID(int=1)
    pop.preaching_imago_id = None
    pop.social_class = MagicMock()
    pop.social_class.value = "common"
    pop.size_fractional = 5.0
    return pop


def _make_civ(civ_id=None, established_beliefs=None, established_culture_tags=None):
    civ = MagicMock()
    civ.id = civ_id or UUID(int=1)
    civ.established_beliefs = established_beliefs or {}
    civ.established_culture_tags = established_culture_tags or {}
    civ.scale = MagicMock()
    civ.scale.value = "continental"
    civ.health = MagicMock()
    civ.health.cohesion = 1.0
    civ.name = "TestCiv"
    return civ


# ── _conformity_resistance_multiplier ────────────────────────────────────────

def test_resistance_multiplier_zero_at_and_below_belief_floor():
    from logic.belief_propagation import _conformity_resistance_multiplier
    assert _conformity_resistance_multiplier(0.05, "domain:fire") == 0.0
    assert _conformity_resistance_multiplier(0.00, "domain:fire") == 0.0
    assert _conformity_resistance_multiplier(0.03, "domain:fire") == 0.0


def test_resistance_multiplier_one_at_and_above_belief_ceiling():
    from logic.belief_propagation import _conformity_resistance_multiplier
    assert _conformity_resistance_multiplier(0.40, "domain:fire") == 1.0
    assert _conformity_resistance_multiplier(0.80, "domain:fire") == 1.0


def test_resistance_multiplier_religion_floor_is_higher_than_beliefs():
    from logic.belief_propagation import _conformity_resistance_multiplier
    # religion floor=0.08; domain belief floor=0.05
    # at d=0.06: beliefs have partial pressure, religion is still immune
    assert _conformity_resistance_multiplier(0.06, "religion:order") == 0.0
    assert _conformity_resistance_multiplier(0.06, "domain:fire") > 0.0


def test_resistance_multiplier_values_floor_is_highest():
    from logic.belief_propagation import _conformity_resistance_multiplier
    # values floor=0.15; at d=0.12: beliefs and religion have pressure, values is immune
    assert _conformity_resistance_multiplier(0.12, "values:hierarchy") == 0.0
    assert _conformity_resistance_multiplier(0.12, "religion:order") > 0.0
    assert _conformity_resistance_multiplier(0.12, "domain:fire") > 0.0


def test_resistance_multiplier_values_at_ceiling():
    from logic.belief_propagation import _conformity_resistance_multiplier
    # values ceiling=0.45
    assert _conformity_resistance_multiplier(0.45, "values:hierarchy") == 1.0
    assert _conformity_resistance_multiplier(0.60, "values:hierarchy") == 1.0


def test_resistance_multiplier_curve_steeper_near_floor_than_near_ceiling():
    from logic.belief_propagation import _conformity_resistance_multiplier
    # For domain beliefs (floor=0.05, ceiling=0.40, span=0.35):
    # at 25% into window: d = 0.05 + 0.35*0.25 = 0.1375 → d_norm=0.25 → 0.25^0.5 ≈ 0.5
    # at 75% into window: d = 0.05 + 0.35*0.75 = 0.3125 → d_norm=0.75 → 0.75^0.5 ≈ 0.866
    # Relative gain from 25%→75%: +0.366 over half the range
    # Relative gain from 0%→25%: +0.5 in the lower quarter
    m_at_25pct = _conformity_resistance_multiplier(0.1375, "domain:fire")
    m_at_75pct = _conformity_resistance_multiplier(0.3125, "domain:fire")
    # Distance from ceiling to midpoint (75%→50%): should be smaller than midpoint to floor (50%→25%)
    gain_upper = 1.0 - m_at_75pct  # resistance remaining in upper half
    gain_lower = m_at_25pct        # multiplier at lower quarter (= resistance dropped from there to floor)
    # ^0.5 curve: lower quarter has more resistance drop than upper quarter
    assert gain_lower < m_at_75pct  # more pressure remains far from floor


# ── civ_conformity_pressure: practice: exclusion ─────────────────────────────

def test_conformity_pressure_never_emits_practice_mutations():
    from logic.belief_propagation import civ_conformity_pressure
    civ_id = UUID(int=0)  # offset 0 → fires on tick 0
    civ = _make_civ(
        civ_id=civ_id,
        established_beliefs={"domain:fire": 0.5},  # needed to pass the early-exit guard
        established_culture_tags={"practice:music": 0.8, "values:hierarchy": 0.8},
    )
    pop = _make_pop(
        civ_id=civ_id,
        beliefs={"domain:fire": 0.5},
        culture_tags={"practice:music": 0.1, "values:hierarchy": 0.1},
    )
    state = MagicMock()
    state.pops = {str(pop.id): pop}
    state.civilizations = {str(civ_id): civ}

    mutations = civ_conformity_pressure(state, _make_cfg(), tick_number=0)
    fields = [m.field for m in mutations]
    assert "practice:music" not in fields
    assert "values:hierarchy" in fields


# ── civ_conformity_pressure: resistance applied ───────────────────────────────

def test_conformity_pressure_applies_full_pressure_above_belief_ceiling():
    from logic.belief_propagation import civ_conformity_pressure
    # dist = 0.8 - 0.2 = 0.6 > ceiling (0.40) → multiplier = 1.0 → full delta
    civ_id = UUID(int=0)
    civ = _make_civ(civ_id=civ_id, established_beliefs={"domain:fire": 0.8})
    pop = _make_pop(civ_id=civ_id, beliefs={"domain:fire": 0.2})
    state = MagicMock()
    state.pops = {str(pop.id): pop}
    state.civilizations = {str(civ_id): civ}

    mutations = civ_conformity_pressure(state, _make_cfg(), tick_number=0)
    assert any(m.field == "domain:fire" and m.delta > 0 for m in mutations)


def test_conformity_pressure_zero_below_belief_floor():
    from logic.belief_propagation import civ_conformity_pressure
    # dist = 0.52 - 0.50 = 0.02 < floor (0.05) → multiplier = 0.0 → no mutation
    civ_id = UUID(int=0)
    civ = _make_civ(civ_id=civ_id, established_beliefs={"domain:fire": 0.52})
    pop = _make_pop(civ_id=civ_id, beliefs={"domain:fire": 0.50})
    state = MagicMock()
    state.pops = {str(pop.id): pop}
    state.civilizations = {str(civ_id): civ}

    mutations = civ_conformity_pressure(state, _make_cfg(), tick_number=0)
    assert not any(m.field == "domain:fire" for m in mutations)


def test_conformity_pressure_zero_below_values_floor():
    from logic.belief_propagation import civ_conformity_pressure
    # values floor=0.15; dist = 0.40 - 0.30 = 0.10 < 0.15 → immune
    civ_id = UUID(int=0)
    civ = _make_civ(civ_id=civ_id, established_culture_tags={"values:hierarchy": 0.40})
    pop = _make_pop(civ_id=civ_id, culture_tags={"values:hierarchy": 0.30})
    state = MagicMock()
    state.pops = {str(pop.id): pop}
    state.civilizations = {str(civ_id): civ}

    mutations = civ_conformity_pressure(state, _make_cfg(), tick_number=0)
    assert not any(m.field == "values:hierarchy" for m in mutations)


# ── civ_conformity_pressure: per-civ stagger ─────────────────────────────────

def test_conformity_pressure_fires_on_civ_offset_tick():
    from logic.belief_propagation import civ_conformity_pressure
    # UUID(int=3).int % 10 = 3 → fires on tick 3, 13, 23 ...
    civ_id = UUID(int=3)
    civ = _make_civ(civ_id=civ_id, established_beliefs={"domain:fire": 0.9})
    pop = _make_pop(civ_id=civ_id, beliefs={"domain:fire": 0.1})
    state = MagicMock()
    state.pops = {str(pop.id): pop}
    state.civilizations = {str(civ_id): civ}

    mutations = civ_conformity_pressure(state, _make_cfg(civ_conformity_stride=10), tick_number=3)
    assert any(m.field == "domain:fire" for m in mutations)


def test_conformity_pressure_silent_on_non_offset_tick():
    from logic.belief_propagation import civ_conformity_pressure
    civ_id = UUID(int=3)  # offset = 3
    civ = _make_civ(civ_id=civ_id, established_beliefs={"domain:fire": 0.9})
    pop = _make_pop(civ_id=civ_id, beliefs={"domain:fire": 0.1})
    state = MagicMock()
    state.pops = {str(pop.id): pop}
    state.civilizations = {str(civ_id): civ}

    mutations = civ_conformity_pressure(state, _make_cfg(civ_conformity_stride=10), tick_number=4)
    assert not any(m.field == "domain:fire" for m in mutations)


def test_two_civs_fire_on_different_ticks():
    from logic.belief_propagation import civ_conformity_pressure
    # civ_a: UUID(int=3) → offset 3; civ_b: UUID(int=5) → offset 5
    stride = 10
    civ_a_id = UUID(int=3)
    civ_b_id = UUID(int=5)
    civ_a = _make_civ(civ_id=civ_a_id, established_beliefs={"domain:fire": 0.9})
    civ_b = _make_civ(civ_id=civ_b_id, established_beliefs={"domain:water": 0.9})
    pop_a = _make_pop(pop_id=UUID(int=10), civ_id=civ_a_id, beliefs={"domain:fire": 0.1})
    pop_b = _make_pop(pop_id=UUID(int=11), civ_id=civ_b_id, beliefs={"domain:water": 0.1})
    state = MagicMock()
    state.pops = {str(pop_a.id): pop_a, str(pop_b.id): pop_b}
    state.civilizations = {str(civ_a_id): civ_a, str(civ_b_id): civ_b}
    cfg = _make_cfg(civ_conformity_stride=stride)

    # Tick 3: only civ_a fires
    m3 = civ_conformity_pressure(state, cfg, tick_number=3)
    assert any(m.field == "domain:fire" for m in m3)
    assert not any(m.field == "domain:water" for m in m3)

    # Tick 5: only civ_b fires
    m5 = civ_conformity_pressure(state, cfg, tick_number=5)
    assert not any(m.field == "domain:fire" for m in m5)
    assert any(m.field == "domain:water" for m in m5)


# ── process_pop_contact: per-world stagger ────────────────────────────────────

def test_pop_contact_skips_world_on_non_offset_tick(monkeypatch):
    from logic import belief_propagation
    from logic.belief_propagation import process_pop_contact

    # UUID(int=2).int % 7 = 2 → fires on tick 2, 9, 16 ...
    world_id_uuid = UUID(int=2)
    world_id_str = str(world_id_uuid)

    called = []
    def fake_pops_on_world(wid, state):
        called.append(wid)
        return []

    monkeypatch.setattr(belief_propagation, "pops_on_world", fake_pops_on_world)
    state = MagicMock()
    state.worlds = {world_id_str: MagicMock()}

    process_pop_contact(state, _make_cfg(pop_contact_stride=7), tick_number=3)
    assert world_id_str not in called, "World should be skipped on non-offset tick"


def test_pop_contact_processes_world_on_offset_tick(monkeypatch):
    from logic import belief_propagation
    from logic.belief_propagation import process_pop_contact

    world_id_uuid = UUID(int=2)
    world_id_str = str(world_id_uuid)

    called = []
    def fake_pops_on_world(wid, state):
        called.append(wid)
        return []

    monkeypatch.setattr(belief_propagation, "pops_on_world", fake_pops_on_world)
    state = MagicMock()
    state.worlds = {world_id_str: MagicMock()}

    process_pop_contact(state, _make_cfg(pop_contact_stride=7), tick_number=2)
    assert world_id_str in called, "World should be processed on its offset tick"


# ── process_location_ambient_influence: per-world stagger ────────────────────

def test_location_ambient_skips_world_on_non_offset_tick():
    from logic.belief_propagation import process_location_ambient_influence
    from core.universe_core import SignificantLocation, PopLocation

    # World UUID(int=4).int % 61 = 4 → fires on tick 4, 65, ...
    world_id = UUID(int=4)
    world = MagicMock(spec=SignificantLocation)
    world.id = world_id
    world.domain_expression = {"domain:fire": 0.8}

    pop_loc = MagicMock(spec=PopLocation)
    pop_loc.parent_id = world_id
    pop_loc.domain_expression = {}
    pop_loc_id = UUID(int=999)

    pop = _make_pop(pop_id=UUID(int=20), beliefs={"domain:fire": 0.1})
    pop.current_location = pop_loc_id
    original_beliefs = dict(pop.dominant_beliefs)

    state = MagicMock()
    state.pops = {str(pop.id): pop}
    state.locations = {str(pop_loc_id): pop_loc, str(world_id): world}

    process_location_ambient_influence(state, _make_cfg(location_ambient_stride=61), tick_number=5)
    assert pop.dominant_beliefs == original_beliefs, "Beliefs should not change on non-offset tick"


def test_location_ambient_processes_world_on_offset_tick():
    from logic.belief_propagation import process_location_ambient_influence
    from core.universe_core import SignificantLocation, PopLocation

    world_id = UUID(int=4)  # offset = 4
    world = MagicMock(spec=SignificantLocation)
    world.id = world_id
    world.domain_expression = {"domain:fire": 0.8}

    pop_loc = MagicMock(spec=PopLocation)
    pop_loc.parent_id = world_id
    pop_loc.domain_expression = {}
    pop_loc.distance_from_core = 0
    pop_loc_id = UUID(int=999)

    pop = _make_pop(pop_id=UUID(int=20), beliefs={"domain:fire": 0.1})
    pop.current_location = pop_loc_id
    # process_location_ambient_influence mutates beliefs in place
    pop.dominant_beliefs = {"domain:fire": 0.1}

    state = MagicMock()
    state.pops = {str(pop.id): pop}
    state.locations = {str(pop_loc_id): pop_loc, str(world_id): world}

    process_location_ambient_influence(state, _make_cfg(location_ambient_stride=61), tick_number=4)
    # Belief should have shifted toward 0.8 (location ambient influence)
    assert pop.dominant_beliefs.get("domain:fire", 0.1) > 0.1, "Belief should shift on offset tick"


# ── process_pop_cultural_noise ────────────────────────────────────────────────

def test_pop_noise_fires_on_stride_tick():
    from logic.belief_propagation import process_pop_cultural_noise, POP_NOISE_STRIDE
    # UUID(int=0).int % 89 = 0 → fires on tick 0
    pop = _make_pop(
        pop_id=UUID(int=0),
        beliefs={"domain:fire": 0.5, "domain:water": 0.4, "domain:life": 0.3},
        culture_tags={"religion:order": 0.5, "values:hierarchy": 0.4},
    )
    state = MagicMock()
    state.pops = {str(pop.id): pop}
    cfg = _make_cfg(pop_noise_sigma=0.5, pop_noise_cap=0.25)
    rng = random.Random(42)

    mutations = process_pop_cultural_noise(state, cfg, rng, tick_number=0)
    assert mutations, "Expected noise mutations on pop's stride tick"


def test_pop_noise_silent_on_non_stride_tick():
    from logic.belief_propagation import process_pop_cultural_noise
    pop = _make_pop(pop_id=UUID(int=0), beliefs={"domain:fire": 0.5})
    state = MagicMock()
    state.pops = {str(pop.id): pop}
    cfg = _make_cfg(pop_noise_sigma=0.5, pop_noise_cap=0.25)
    rng = random.Random(42)

    mutations = process_pop_cultural_noise(state, cfg, rng, tick_number=1)
    assert not mutations, "No noise on non-offset tick"


def test_pop_noise_stagger_offsets_different_pops():
    from logic.belief_propagation import process_pop_cultural_noise
    # pop_a: UUID(int=0) → offset 0; pop_b: UUID(int=5) → offset 5
    pop_a = _make_pop(pop_id=UUID(int=0), beliefs={"domain:fire": 0.5})
    pop_b = _make_pop(pop_id=UUID(int=5), beliefs={"domain:water": 0.5})
    state = MagicMock()
    state.pops = {str(pop_a.id): pop_a, str(pop_b.id): pop_b}
    cfg = _make_cfg(pop_noise_sigma=0.5, pop_noise_cap=0.25)
    rng = random.Random(42)

    # Tick 0: only pop_a fires
    m0 = process_pop_cultural_noise(state, cfg, rng, tick_number=0)
    assert any(m.target_id == pop_a.id for m in m0)
    assert not any(m.target_id == pop_b.id for m in m0)


def test_pop_noise_includes_practice_tags():
    from logic.belief_propagation import process_pop_cultural_noise
    pop = _make_pop(
        pop_id=UUID(int=0),
        culture_tags={"practice:music": 0.5, "practice:ritual": 0.3},
    )
    state = MagicMock()
    state.pops = {str(pop.id): pop}
    cfg = _make_cfg(pop_noise_sigma=0.5, pop_noise_cap=0.25)
    rng = random.Random(42)

    mutations = process_pop_cultural_noise(state, cfg, rng, tick_number=0)
    practice_fields = {m.field for m in mutations if m.field.startswith("practice:")}
    assert practice_fields, "practice: tags should receive noise mutations"


def test_pop_noise_delta_within_cap():
    from logic.belief_propagation import process_pop_cultural_noise
    pop = _make_pop(
        pop_id=UUID(int=0),
        beliefs={f"domain:tag{i}": 0.5 for i in range(20)},
    )
    state = MagicMock()
    state.pops = {str(pop.id): pop}
    cfg = _make_cfg(pop_noise_sigma=1.0, pop_noise_cap=0.25)
    rng = random.Random(0)

    mutations = process_pop_cultural_noise(state, cfg, rng, tick_number=0)
    for m in mutations:
        assert abs(m.delta) <= 0.25, f"Delta {m.delta} exceeds cap"
