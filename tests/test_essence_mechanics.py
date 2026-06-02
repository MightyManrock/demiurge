import random
from unittest.mock import MagicMock, patch
import pytest
from core.action_core import (
    EssenceStockpile, MutationType, StateMutation,
    EssenceHarvestIntent, ActionInstance, TargetType, OngoingAction,
    ActionCategory,
)
from logic.tick_logic import TickLoop, ActionOutcome, SimulationState


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


# ── Auto-stop condition tests ──────────────────────────────────────────────────

def _harvest_handler_setup(
    concealment=0.7,
    stop_suspicious=None,
    stop_integrity=None,
    stop_stockpile=None,
    actual=10.0,
    suspicious=0.0,
    integrity=1.0,
):
    """
    Build the minimal objects needed to call _resolve_intent_mutations
    for an EssenceHarvestIntent.
    """
    loop = TickLoop.__new__(TickLoop)
    loop._rng = random.Random(42)

    intent = EssenceHarvestIntent(
        concealment_priority=concealment,
        stop_at_suspicious=stop_suspicious,
        stop_at_integrity_below=stop_integrity,
        stop_at_stockpile=stop_stockpile,
    )

    instance = MagicMock()
    instance.intent = intent

    defn = MagicMock()
    defn.category = ActionCategory.UNDERREAL
    defn.name = "Harvest Essence from Underreal"

    state = MagicMock()
    state.essence = EssenceStockpile(
        actual=actual, suspicious=suspicious, concealment_integrity=integrity
    )
    from uuid import uuid4
    state.pending_actions = {
        ActionCategory.UNDERREAL.value: OngoingAction(
            action_key="harvest_essence",
            action_definition_id=uuid4(),
            target_type=TargetType.WORLD,
            repeating=True,
        )
    }
    state.demiurge = MagicMock()
    state.demiurge.id = uuid4()
    state.last_harvest_amount = 0.0
    state.last_harvest_tick = 0
    state.tick_number = 5

    return loop, instance, defn, state


def test_stop_at_suspicious_cancels_repeat():
    """When suspicious >= stop_at_suspicious, harvest pauses and repeating=False."""
    loop, instance, defn, state = _harvest_handler_setup(
        suspicious=15.0, stop_suspicious=10.0
    )
    mutations, narrative = loop._resolve_intent_mutations(
        instance, defn, state, ActionOutcome.SUCCESS, loop._rng
    )
    assert state.pending_actions[ActionCategory.UNDERREAL.value].repeating is False
    assert mutations == []
    assert "paused" in narrative.lower()


def test_stop_at_integrity_cancels_repeat():
    """When integrity < stop_at_integrity_below, harvest pauses."""
    loop, instance, defn, state = _harvest_handler_setup(
        integrity=0.3, stop_integrity=0.5
    )
    mutations, narrative = loop._resolve_intent_mutations(
        instance, defn, state, ActionOutcome.SUCCESS, loop._rng
    )
    assert state.pending_actions[ActionCategory.UNDERREAL.value].repeating is False
    assert mutations == []


def test_stop_at_stockpile_cancels_repeat():
    """When actual >= stop_at_stockpile, harvest pauses."""
    loop, instance, defn, state = _harvest_handler_setup(
        actual=50.0, stop_stockpile=40.0
    )
    mutations, narrative = loop._resolve_intent_mutations(
        instance, defn, state, ActionOutcome.SUCCESS, loop._rng
    )
    assert state.pending_actions[ActionCategory.UNDERREAL.value].repeating is False
    assert mutations == []


def test_no_stop_condition_proceeds_normally():
    """When all stop conditions are unmet, harvest proceeds and yields mutations."""
    loop, instance, defn, state = _harvest_handler_setup(
        actual=10.0, suspicious=2.0, integrity=0.9,
        stop_suspicious=20.0, stop_integrity=0.2, stop_stockpile=100.0,
    )
    mutations, narrative = loop._resolve_intent_mutations(
        instance, defn, state, ActionOutcome.SUCCESS, loop._rng
    )
    assert state.pending_actions[ActionCategory.UNDERREAL.value].repeating is True
    assert any(m.field == "actual" for m in mutations)
