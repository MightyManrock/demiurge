import random
from unittest.mock import MagicMock, patch
import pytest
from core.action_core import EssenceStockpile, MutationType, StateMutation
from logic.tick_logic import TickLoop


def _make_state(actual, suspicious, integrity=1.0):
    state = MagicMock()
    state.essence = EssenceStockpile(
        actual=actual,
        suspicious=suspicious,
        concealment_integrity=integrity,
    )
    return state


def _apply_essence_mutation(state, field, delta, seed=42):
    """Apply a single ESSENCE_CHANGE mutation through TickLoop._apply_mutations."""
    loop = TickLoop.__new__(TickLoop)
    loop._rng = random.Random(seed)
    m = StateMutation(
        mutation_type=MutationType.ESSENCE_CHANGE,
        target_id=None,
        field=field,
        delta=delta,
    )
    loop._apply_mutations(state, [m])
    return state


def test_spending_actual_drains_suspicious_proportionally():
    """Spending 10 from actual=50, suspicious=20 should drain ~4 suspicious."""
    state = _make_state(actual=50.0, suspicious=20.0)
    _apply_essence_mutation(state, "actual", -10.0, seed=0)
    assert state.essence.actual == pytest.approx(40.0)
    # drain ≈ 10 * (20/50) = 4.0, ±noise
    assert 0.0 < state.essence.suspicious < 20.0
    assert state.essence.suspicious == pytest.approx(20.0 - 4.0, abs=1.5)


def test_no_drain_when_suspicious_is_zero():
    state = _make_state(actual=30.0, suspicious=0.0)
    _apply_essence_mutation(state, "actual", -10.0)
    assert state.essence.suspicious == pytest.approx(0.0)
    assert state.essence.actual == pytest.approx(20.0)


def test_drain_clamped_to_suspicious_balance():
    """Drain can never exceed suspicious balance."""
    state = _make_state(actual=10.0, suspicious=1.0)
    _apply_essence_mutation(state, "actual", -9.0)
    assert state.essence.suspicious >= 0.0


def test_gain_does_not_drain_suspicious():
    """Positive ESSENCE_CHANGE (harvest) must not drain suspicious."""
    state = _make_state(actual=20.0, suspicious=10.0)
    _apply_essence_mutation(state, "actual", +5.0)
    assert state.essence.suspicious == pytest.approx(10.0)
    assert state.essence.actual == pytest.approx(25.0)


def test_suspicious_field_mutation_does_not_trigger_launder():
    """Direct suspicious mutations (harvest leak) must not loop back."""
    state = _make_state(actual=20.0, suspicious=5.0)
    _apply_essence_mutation(state, "suspicious", +3.0)
    assert state.essence.suspicious == pytest.approx(8.0)
    assert state.essence.actual == pytest.approx(20.0)
