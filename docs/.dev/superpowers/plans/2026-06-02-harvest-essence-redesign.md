# Harvest Essence Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename `apparent` Essence to `suspicious` across the entire codebase, add an Essence-laundering mechanic (spending Essence passively drains suspicious Essence proportionally), clean up the dead `EssenceHarvestIntent` fields, add three auto-stop conditions to that intent, and replace the TextFormModal for Harvest Essence with a proper `HarvestEssenceConfigModal` featuring a slider and toggleable stop conditions.

**Architecture:** The rename is a mechanical find-replace across model, DB schema, loader, exporter, and all display sites. The laundering mechanic is a single addition to the `ESSENCE_CHANGE` branch in `_apply_mutations`. The new modal and intent fields are self-contained in `ui/modals.py` + `ui/ui.py`. Stop-condition logic lives in `_resolve_intent_mutations` alongside the existing harvest handler.

**Tech Stack:** Python/Pydantic, Textual TUI (Slider, Checkbox, Input widgets), SQLite (scenario DB schema), pytest.

---

## Files Modified

| File | What changes |
|---|---|
| `core/action_core.py` | Rename `EssenceStockpile.apparent` → `suspicious`; strip `EssenceHarvestIntent` of dead fields; add three stop-condition fields |
| `core/scenario_schema.sql` | Rename `apparent` column → `suspicious` in `essence` table |
| `utilities/scenario_loader.py` | Read `suspicious` with backward-compat fallback to `apparent` |
| `utilities/scenario_exporter.py` | Write `suspicious` column |
| `logic/tick_logic.py` | Update all `.apparent` / `field="apparent"` refs; add laundering in `_apply_mutations`; add stop-condition checks in harvest handler; update narrative string |
| `core/eval_core.py` | Rename `apparent_stockpile` param/field |
| `ui/widgets.py` | Rename display label |
| `ui/display.py` | Rename display label |
| `autoplay/autoplay.py` | Rename print labels |
| `ui/modals.py` | New `HarvestEssenceConfigModal` |
| `ui/ui.py` | Wire `HarvestEssenceConfigModal`, update `EssenceHarvestIntent` construction |
| `tests/test_essence_mechanics.py` | New: laundering unit tests + stop-condition unit tests |

---

## Task 1: Rename `apparent` in the data model and DB layer

**Files:**
- Modify: `core/action_core.py`
- Modify: `core/scenario_schema.sql`
- Modify: `utilities/scenario_loader.py`
- Modify: `utilities/scenario_exporter.py`

- [ ] **Step 1: Rename `EssenceStockpile.apparent` → `suspicious` in `core/action_core.py`**

In `core/action_core.py`, lines 21–53, replace the `EssenceStockpile` class:

```python
class EssenceStockpile(BaseModel):
    """
    Divine Essence — raw conceptual power drawn primarily
    from the Underreal. Split into actual vs. suspicious
    because concealment is an active, maintained gap
    between the two.

    Luminaries evaluate suspicious, not actual.
    The player manages both.
    """
    actual: float = Field(ge=0.0, default=0.0)
    suspicious: float = Field(ge=0.0, default=0.0)
    # suspicious <= actual always; enforced on mutation

    concealment_integrity: float = Field(ge=0.0, le=1.0, default=1.0)
    # 1.0 = perfectly hidden; 0.0 = fully exposed
    # Degrades on: essence spending, Luminary scrutiny,
    # Herald investigation, passage of time without maintenance

    def hidden_amount(self) -> float:
        """How much is successfully concealed."""
        return self.actual - self.suspicious

    def exposure_risk(self) -> float:
        """
        Rough probability a Luminary audit reveals
        more than suspicious. Rises as concealment degrades
        and hidden amount grows.
        """
        if self.actual == 0.0:
            return 0.0
        hidden_ratio = self.hidden_amount() / self.actual
        return hidden_ratio * (1.0 - self.concealment_integrity)
```

- [ ] **Step 2: Rename column in `core/scenario_schema.sql`**

Find the `essence` table definition and rename the column:

```sql
-- Before:
apparent                REAL NOT NULL DEFAULT 0.0,
-- After:
suspicious              REAL NOT NULL DEFAULT 0.0,
```

- [ ] **Step 3: Update loader with backward-compat fallback in `utilities/scenario_loader.py`**

Find the line `apparent=row["apparent"],` and replace it:

```python
suspicious=float(row["suspicious"] if "suspicious" in row.keys() else row.get("apparent", 0.0)),
```

- [ ] **Step 4: Update exporter in `utilities/scenario_exporter.py`**

Find the INSERT statement for essence. Replace both the column name and the field reference:

```python
"INSERT INTO essence (actual, suspicious, concealment_integrity) VALUES (?, ?, ?)",
(e.actual, e.suspicious, e.concealment_integrity),
```

- [ ] **Step 5: Run tests to verify nothing broke**

```bash
cd /root/demiurge && source venv/bin/activate && pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add core/action_core.py core/scenario_schema.sql utilities/scenario_loader.py utilities/scenario_exporter.py
git commit -m "refactor: rename EssenceStockpile.apparent → suspicious, update DB schema and loader/exporter"
```

---

## Task 2: Propagate rename through engine and display layers

**Files:**
- Modify: `logic/tick_logic.py`
- Modify: `core/eval_core.py`
- Modify: `ui/widgets.py`
- Modify: `ui/display.py`
- Modify: `autoplay/autoplay.py`

- [ ] **Step 1: Update `logic/tick_logic.py` — all `.apparent` and `field="apparent"` references**

There are four sites. Replace each:

*Line ~2277* (concealment leak in standard footprint handler):
```python
# Before:
field="apparent",
# After:
field="suspicious",
```

*Line ~3856* (apparent leak in harvest handler):
```python
# Before:
field="apparent",
# After:
field="suspicious",
```

*Line ~3866* (narrative string):
```python
# Before:
f"Apparent leak: {apparent_leak:.2f}. "
# After:
f"Suspicious Essence added: {apparent_leak:.2f}. "
```

*Line ~4611* (eval call argument):
```python
# Before:
apparent_stockpile=state.essence.apparent,
# After:
apparent_stockpile=state.essence.suspicious,
```

*Lines ~6166–6167* (cap enforcement):
```python
# Before:
if state.essence.apparent > state.essence.actual:
    state.essence.apparent = state.essence.actual
# After:
if state.essence.suspicious > state.essence.actual:
    state.essence.suspicious = state.essence.actual
```

- [ ] **Step 2: Update `core/eval_core.py`**

Line ~179, rename the field:
```python
# Before:
apparent_stockpile_reading: float = 0.0
# After:
suspicious_stockpile_reading: float = 0.0
```

Line ~622, rename the parameter:
```python
# Before:
apparent_stockpile: float,
# After:
apparent_stockpile: float,  # keep param name — caller uses keyword arg; update together
```

Actually update both the parameter at line ~622 and all uses within the function body (lines ~638–640, ~680):

```python
# Function signature:
apparent_stockpile: float,  →  suspicious_stockpile: float,

# Line ~638:
if apparent_stockpile > 0.1:  →  if suspicious_stockpile > 0.1:

# Line ~639:
suspicion += apparent_stockpile * 0.3  →  suspicion += suspicious_stockpile * 0.3

# Line ~680:
apparent_stockpile_reading=apparent_stockpile,  →  suspicious_stockpile_reading=suspicious_stockpile,
```

Also update the call site in `tick_logic.py` (already changed above at line ~4611 — make sure the keyword arg name matches: `apparent_stockpile=` → `suspicious_stockpile=`).

- [ ] **Step 3: Update `ui/widgets.py`**

Find the StatusTab display lines (around line 627–638):

```python
# Before:
a(f"  actual [bold]{es.actual:.2f}[/]  apparent [bold]{es.apparent:.2f}[/]")
# ...
a(f"  last harvest [#c09030]+{state.last_harvest_amount:.2f}[/] "
# After:
a(f"  actual [bold]{es.actual:.2f}[/]  suspicious [bold]{es.suspicious:.2f}[/]")
```

- [ ] **Step 4: Update `ui/display.py`**

Find line ~370:
```python
# Before:
f"  Essence   — actual:{es.actual:.2f}  apparent:{es.apparent:.2f}  "
# After:
f"  Essence   — actual:{es.actual:.2f}  suspicious:{es.suspicious:.2f}  "
```

- [ ] **Step 5: Update `autoplay/autoplay.py`**

Find lines ~131 and ~155:
```python
# Before:
print(f"  Ess: actual={state.essence.actual:.2f} apparent={state.essence.apparent:.2f} "
# After:
print(f"  Ess: actual={state.essence.actual:.2f} suspicious={state.essence.suspicious:.2f} "
```

(Apply the same substitution on line ~155.)

- [ ] **Step 6: Run tests**

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add logic/tick_logic.py core/eval_core.py ui/widgets.py ui/display.py autoplay/autoplay.py
git commit -m "refactor: propagate apparent→suspicious rename through engine, eval, and display layers"
```

---

## Task 3: Clean up `EssenceHarvestIntent` — remove dead fields, add stop conditions

**Files:**
- Modify: `core/action_core.py`

- [ ] **Step 1: Replace `EssenceHarvestIntent` definition**

In `core/action_core.py`, replace the current `EssenceHarvestIntent` class (lines ~433–453) with:

```python
class EssenceHarvestIntent(BaseModel):
    """
    For: harvest_essence
    Controls how aggressively you're drawing from the Underreal
    and when to automatically pause the ongoing harvest.
    """
    concealment_priority: float = Field(ge=0.0, le=1.0, default=0.7)
    # 0.0 = maximum yield, maximum suspicious Essence leak
    # 1.0 = minimum yield, minimum suspicious Essence leak

    stop_at_suspicious: Optional[float] = None
    # Pause when essence.suspicious >= this value. None = no limit.

    stop_at_integrity_below: Optional[float] = None
    # Pause when essence.concealment_integrity < this value. None = no limit.

    stop_at_stockpile: Optional[float] = None
    # Pause when essence.actual >= this value. None = harvest indefinitely.
```

- [ ] **Step 2: Run tests**

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add core/action_core.py
git commit -m "refactor: clean up EssenceHarvestIntent — remove dead fields, add auto-stop condition fields"
```

---

## Task 4: Implement the Essence laundering mechanic

**Files:**
- Create: `tests/test_essence_mechanics.py`
- Modify: `logic/tick_logic.py`

The mechanic: when Essence is spent (negative `ESSENCE_CHANGE` on the `actual` field), reduce `suspicious` by a proportional amount with mild random noise.

Formula: `drain = spend * (suspicious / actual) * (1 + noise)`, clamped to `[0, suspicious]`.
Noise: uniform in `[-0.15, +0.15]` — small enough not to flip direction, large enough to feel organic.

Only applies when `actual > 0` and `suspicious > 0` and `delta < 0` (a spend) and `field == "actual"`.

- [ ] **Step 1: Write failing tests in `tests/test_essence_mechanics.py`**

```python
import pytest
import random
from unittest.mock import MagicMock
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


def _apply(state, field, delta, rng=None):
    """Apply a single ESSENCE_CHANGE mutation via TickLoop._apply_mutations."""
    loop = TickLoop.__new__(TickLoop)
    loop._rng = rng or random.Random(42)
    m = StateMutation(
        mutation_type=MutationType.ESSENCE_CHANGE,
        target_id=state.essence.__class__.__name__,  # unused by handler
        field=field,
        delta=delta,
    )
    # _apply_mutations iterates over a list; we need the state it writes to
    loop._apply_mutations(state, [m])
    return state


def test_spending_actual_drains_suspicious_proportionally():
    """Spending 10 from actual=50, suspicious=20 should drain ~4 suspicious."""
    state = _make_state(actual=50.0, suspicious=20.0)
    rng = random.Random(0)  # seed for reproducibility
    _apply(state, "actual", -10.0, rng)
    # actual drops by 10
    assert state.essence.actual == pytest.approx(40.0)
    # suspicious drains: 10 * (20/50) = 4.0, ± noise
    assert 0.0 < state.essence.suspicious < 20.0
    assert state.essence.suspicious == pytest.approx(20.0 - 4.0, abs=1.0)


def test_no_drain_when_suspicious_is_zero():
    """If suspicious is 0, spending should not produce negative suspicious."""
    state = _make_state(actual=30.0, suspicious=0.0)
    _apply(state, "actual", -10.0)
    assert state.essence.suspicious == pytest.approx(0.0)
    assert state.essence.actual == pytest.approx(20.0)


def test_drain_clamped_to_suspicious_balance():
    """Drain can never exceed the current suspicious balance."""
    state = _make_state(actual=10.0, suspicious=1.0)
    _apply(state, "actual", -9.0)  # spend almost everything
    assert state.essence.suspicious >= 0.0


def test_gain_does_not_affect_suspicious():
    """A positive ESSENCE_CHANGE (harvest yield) must not drain suspicious."""
    state = _make_state(actual=20.0, suspicious=10.0)
    _apply(state, "actual", +5.0)
    assert state.essence.suspicious == pytest.approx(10.0)
    assert state.essence.actual == pytest.approx(25.0)


def test_suspicious_field_change_does_not_trigger_drain():
    """Direct suspicious mutations (harvest leak) must not loop back."""
    state = _make_state(actual=20.0, suspicious=5.0)
    _apply(state, "suspicious", +3.0)
    assert state.essence.suspicious == pytest.approx(8.0)
    assert state.essence.actual == pytest.approx(20.0)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_essence_mechanics.py -v
```

Expected: failures because laundering is not yet implemented.

- [ ] **Step 3: Add laundering to `_apply_mutations` in `logic/tick_logic.py`**

In the `ESSENCE_CHANGE` branch (around line 6162), extend it:

```python
elif m.mutation_type == MutationType.ESSENCE_CHANGE:
    current = getattr(state.essence, m.field, 0.0)
    setattr(state.essence, m.field, max(0.0, current + (m.delta or 0)))
    # Enforce suspicious <= actual
    if state.essence.suspicious > state.essence.actual:
        state.essence.suspicious = state.essence.actual
    # Laundering: spending actual Essence passively drains suspicious.
    # Fraction drained ≈ (suspicious/actual) with mild noise.
    if (
        m.field == "actual"
        and (m.delta or 0) < 0
        and state.essence.actual > 0.0
        and state.essence.suspicious > 0.0
    ):
        spend = abs(m.delta)
        ratio = state.essence.suspicious / (state.essence.actual + spend)
        noise = self._rng.uniform(-0.15, 0.15)
        drain = spend * ratio * (1.0 + noise)
        drain = max(0.0, min(drain, state.essence.suspicious))
        state.essence.suspicious = max(0.0, state.essence.suspicious - drain)
```

Note: `actual + spend` in the ratio denominator uses the pre-spend actual to avoid division by near-zero.

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_essence_mechanics.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 5: Run full suite**

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add tests/test_essence_mechanics.py logic/tick_logic.py
git commit -m "feat: add Essence laundering — spending Essence passively drains suspicious Essence proportionally"
```

---

## Task 5: Implement auto-stop conditions in the harvest handler

**Files:**
- Modify: `logic/tick_logic.py`
- Modify: `tests/test_essence_mechanics.py`

Stop conditions are checked at the top of the `EssenceHarvestIntent` branch in `_resolve_intent_mutations`. If any condition is met, we cancel the repeating flag on the `OngoingAction` and return an explanatory narrative without applying yield mutations.

- [ ] **Step 1: Add stop-condition tests to `tests/test_essence_mechanics.py`**

```python
from uuid import uuid4
from core.action_core import (
    EssenceHarvestIntent, ActionInstance, TargetType, OngoingAction,
    ActionCategory, ActionDefinition, ActionReliability,
)
from logic.tick_logic import TickLoop, SimulationState, ActionOutcome


def _harvest_setup(concealment=0.7, stop_suspicious=None,
                   stop_integrity=None, stop_stockpile=None,
                   actual=10.0, suspicious=0.0, integrity=1.0):
    """Return (loop, instance, defn, state, outcome) for harvest handler tests."""
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
    state.pending_actions = {
        ActionCategory.UNDERREAL.value: OngoingAction(
            action_key="harvest_essence",
            repeating=True,
        )
    }
    state.last_harvest_amount = 0.0
    state.last_harvest_tick = 0
    state.tick_number = 5

    return loop, instance, defn, state


def test_stop_at_suspicious_cancels_repeat():
    loop, instance, defn, state = _harvest_setup(
        suspicious=15.0, stop_suspicious=10.0
    )
    mutations, narrative = loop._resolve_intent_mutations(
        instance, defn, state, ActionOutcome.SUCCESS, loop._rng
    )
    assert state.pending_actions[ActionCategory.UNDERREAL.value].repeating is False
    assert not mutations
    assert "paused" in narrative.lower()


def test_stop_at_integrity_cancels_repeat():
    loop, instance, defn, state = _harvest_setup(
        integrity=0.3, stop_integrity=0.5
    )
    mutations, narrative = loop._resolve_intent_mutations(
        instance, defn, state, ActionOutcome.SUCCESS, loop._rng
    )
    assert state.pending_actions[ActionCategory.UNDERREAL.value].repeating is False
    assert not mutations


def test_stop_at_stockpile_cancels_repeat():
    loop, instance, defn, state = _harvest_setup(
        actual=50.0, stop_stockpile=40.0
    )
    mutations, narrative = loop._resolve_intent_mutations(
        instance, defn, state, ActionOutcome.SUCCESS, loop._rng
    )
    assert state.pending_actions[ActionCategory.UNDERREAL.value].repeating is False
    assert not mutations


def test_no_stop_condition_met_proceeds_normally():
    loop, instance, defn, state = _harvest_setup(
        actual=10.0, suspicious=2.0, integrity=0.9,
        stop_suspicious=20.0, stop_integrity=0.2, stop_stockpile=100.0,
    )
    mutations, narrative = loop._resolve_intent_mutations(
        instance, defn, state, ActionOutcome.SUCCESS, loop._rng
    )
    assert state.pending_actions[ActionCategory.UNDERREAL.value].repeating is True
    assert any(m.field == "actual" for m in mutations)
```

- [ ] **Step 2: Run to confirm failures**

```bash
pytest tests/test_essence_mechanics.py::test_stop_at_suspicious_cancels_repeat -v
```

Expected: FAIL.

- [ ] **Step 3: Add stop-condition checks to harvest handler in `logic/tick_logic.py`**

At the top of the `elif isinstance(intent, EssenceHarvestIntent):` block (currently line ~3832), before any yield logic:

```python
elif isinstance(intent, EssenceHarvestIntent):
    # ── Auto-stop checks ──────────────────────────────────────────
    stop_reason = None
    if (intent.stop_at_suspicious is not None
            and state.essence.suspicious >= intent.stop_at_suspicious):
        stop_reason = f"suspicious Essence reached {state.essence.suspicious:.2f}"
    elif (intent.stop_at_integrity_below is not None
            and state.essence.concealment_integrity < intent.stop_at_integrity_below):
        stop_reason = (
            f"concealment integrity at "
            f"{state.essence.concealment_integrity:.0%}"
        )
    elif (intent.stop_at_stockpile is not None
            and state.essence.actual >= intent.stop_at_stockpile):
        stop_reason = f"Essence stockpile reached {state.essence.actual:.2f}"

    if stop_reason:
        cat_key = defn.category.value
        pending = state.pending_actions.get(cat_key)
        if pending:
            pending.repeating = False
        return [], f"Harvest paused: {stop_reason}."

    if outcome == ActionOutcome.FAILURE:
        # ... (existing failure branch continues unchanged)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_essence_mechanics.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Run full suite**

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add logic/tick_logic.py tests/test_essence_mechanics.py
git commit -m "feat: add auto-stop conditions to Harvest Essence — suspicious cap, integrity floor, stockpile target"
```

---

## Task 6: Build `HarvestEssenceConfigModal`

**Files:**
- Modify: `ui/modals.py`

The modal shows:
- A `Slider` (0.0–1.0, step 0.05) for `concealment_priority`, with a live preview label showing the expected yield and suspicious leak per tick at the current slider value.
- Three optional stop conditions, each with a `Checkbox` and an `Input` for the threshold. Inputs are disabled when the checkbox is unchecked.
- A confirm button.

The modal returns a dict `{"concealment": float, "stop_suspicious": float|None, "stop_integrity": float|None, "stop_stockpile": float|None}` on confirm, or `None` on cancel/back.

- [ ] **Step 1: Add imports at the top of `ui/modals.py` if not already present**

Verify `Slider`, `Checkbox`, `Input`, `Button`, `Label` are imported from `textual.widgets`. The existing imports in `modals.py` likely already cover Button, Label, Input — add Slider and Checkbox if missing:

```python
from textual.widgets import Button, Input, Label, Slider, Checkbox
```

- [ ] **Step 2: Add `HarvestEssenceConfigModal` to `ui/modals.py`**

Append after the existing modal classes:

```python
class HarvestEssenceConfigModal(ModalScreen):
    """Config modal for the Harvest Essence from Underreal action."""

    DEFAULT_CSS = """
    HarvestEssenceConfigModal > Vertical {
        width: 60;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: solid $primary;
    }
    HarvestEssenceConfigModal #preview {
        margin: 0 0 1 0;
        color: $text-muted;
    }
    HarvestEssenceConfigModal .stop-row {
        height: 3;
        margin-bottom: 1;
    }
    HarvestEssenceConfigModal .stop-input {
        width: 12;
        margin-left: 2;
    }
    HarvestEssenceConfigModal #buttons {
        margin-top: 1;
        height: 3;
        align: center middle;
    }
    """

    _BASE_YIELD = 3.0

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Harvest Essence from Underreal", id="title")
            yield Label("Concealment priority")
            yield Slider(min=0.0, max=1.0, step=0.05, value=0.7, id="conc_slider")
            yield Label("", id="preview")

            yield Label("Auto-stop conditions (leave unchecked to harvest indefinitely):")
            with Horizontal(classes="stop-row"):
                yield Checkbox("Stop when suspicious Essence ≥", id="chk_suspicious")
                yield Input(placeholder="e.g. 20", id="inp_suspicious",
                            disabled=True, classes="stop-input")
            with Horizontal(classes="stop-row"):
                yield Checkbox("Stop when concealment integrity <", id="chk_integrity")
                yield Input(placeholder="0–100 %", id="inp_integrity",
                            disabled=True, classes="stop-input")
            with Horizontal(classes="stop-row"):
                yield Checkbox("Stop when Essence stockpile ≥", id="chk_stockpile")
                yield Input(placeholder="e.g. 50", id="inp_stockpile",
                            disabled=True, classes="stop-input")

            with Horizontal(id="buttons"):
                yield Button("✕ Cancel", id="cancel", variant="default")
                yield Button("Confirm", id="confirm", variant="primary")

    def on_mount(self) -> None:
        self._update_preview(0.7)

    def _update_preview(self, conc: float) -> None:
        yield_val = self._BASE_YIELD * (0.5 + conc * 0.5)
        leak_val  = self._BASE_YIELD * (1.0 - conc) * 0.5
        self.query_one("#preview", Label).update(
            f"Expected yield: ~{yield_val:.2f}  |  Suspicious leak: ~{leak_val:.2f}  (per tick, on success)"
        )

    def on_slider_changed(self, event: Slider.Changed) -> None:
        self._update_preview(float(event.value))

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        mapping = {
            "chk_suspicious": "inp_suspicious",
            "chk_integrity":  "inp_integrity",
            "chk_stockpile":  "inp_stockpile",
        }
        inp_id = mapping.get(event.checkbox.id)
        if inp_id:
            self.query_one(f"#{inp_id}", Input).disabled = not event.value

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        if event.button.id == "confirm":
            self.dismiss(self._build_result())

    def _parse_optional_float(self, input_id: str, checkbox_id: str) -> Optional[float]:
        if not self.query_one(f"#{checkbox_id}", Checkbox).value:
            return None
        raw = self.query_one(f"#{input_id}", Input).value.strip()
        try:
            return float(raw)
        except ValueError:
            return None

    def _build_result(self) -> dict:
        conc = float(self.query_one("#conc_slider", Slider).value)

        stop_suspicious = self._parse_optional_float("inp_suspicious", "chk_suspicious")
        stop_stockpile  = self._parse_optional_float("inp_stockpile",  "chk_stockpile")

        # Integrity input is in % (0–100); store as fraction
        raw_integrity = self._parse_optional_float("inp_integrity", "chk_integrity")
        stop_integrity = raw_integrity / 100.0 if raw_integrity is not None else None

        return {
            "concealment": conc,
            "stop_suspicious": stop_suspicious,
            "stop_integrity": stop_integrity,
            "stop_stockpile": stop_stockpile,
        }
```

- [ ] **Step 3: Run tests**

```bash
pytest -v
```

Expected: all tests pass (the modal has no unit-testable logic outside the UI layer).

- [ ] **Step 4: Commit**

```bash
git add ui/modals.py
git commit -m "feat: add HarvestEssenceConfigModal with concealment slider and auto-stop conditions"
```

---

## Task 7: Wire `HarvestEssenceConfigModal` into the UI

**Files:**
- Modify: `ui/ui.py`

- [ ] **Step 1: Add `HarvestEssenceConfigModal` to imports in `ui/ui.py`**

Find the existing modal imports (near the top of the file, importing from `ui.modals`) and add:

```python
from ui.modals import (
    ...,
    HarvestEssenceConfigModal,
)
```

- [ ] **Step 2: Replace the `harvest_essence` branch in `_build_intent_params`**

Find the current block starting at line ~1673:

```python
if action_key == "harvest_essence":
    form = await app.push_screen_wait(
        TextFormModal(
            ...
        )
    )
    ...
    return EssenceHarvestIntent(
        target_concept_type=form["concept"].strip() or None,
        concealment_priority=conc,
    )
```

Replace entirely with:

```python
if action_key == "harvest_essence":
    result = await app.push_screen_wait(HarvestEssenceConfigModal())
    if result is None:
        return None
    return EssenceHarvestIntent(
        concealment_priority=result["concealment"],
        stop_at_suspicious=result["stop_suspicious"],
        stop_at_integrity_below=result["stop_integrity"],
        stop_at_stockpile=result["stop_stockpile"],
    )
```

- [ ] **Step 3: Run tests**

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 4: Run the app and exercise the modal manually**

```bash
python main.py
```

Navigate to Actions, select "Harvest Essence from Underreal", and verify:
- The slider renders and the preview label updates as you drag.
- Checking a stop-condition checkbox enables its input.
- Confirm returns to the game screen with the action queued.
- Cancel returns without queuing.
- Advance one tick and confirm the harvest narrative appears in the log.

- [ ] **Step 5: Commit**

```bash
git add ui/ui.py
git commit -m "feat: wire HarvestEssenceConfigModal — replaces TextFormModal for Harvest Essence action"
```
