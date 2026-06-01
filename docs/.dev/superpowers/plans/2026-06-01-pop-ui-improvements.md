# Pop UI Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Three targeted UI improvements: show fractional pop size in dev mode, seed splinter pops with a name, and auto-close pop detail tabs when the pop disappears.

**Architecture:** Each task is independent. Task 1 changes one line in a renderer. Task 2 adds one field to the splinter Pop constructor and one test. Task 3 adds a guard in `refresh_all` with no new abstractions.

**Tech Stack:** Python 3, Pydantic, Textual TUI. Tests use pytest + MagicMock.

---

### Task 1: Fractional size in dev mode

**Files:**
- Modify: `ui/detail_renderers.py:1105`

> No unit test: `detail_renderers` is a UI layer intentionally outside the unit test suite (per project conventions). Verify visually with `--dev --autoplay`.

- [ ] **Step 1: Edit the size line in `render_pop_detail`**

In `ui/detail_renderers.py`, find line 1105:

```python
    a(f"  size: {pop.size_magnitude} ({_size_magnitude_word(pop.size_magnitude)})")
```

Replace with:

```python
    if dev:
        a(f"  size: {pop.size_magnitude}  [#606060]{pop.size_fractional:.2f}[/]")
    else:
        a(f"  size: {pop.size_magnitude} ({_size_magnitude_word(pop.size_magnitude)})")
```

- [ ] **Step 2: Verify with dev autoplay**

```bash
python main.py --dev --autoplay
```

Expected: no errors, run completes. Then open the TUI in dev mode (`python main.py --dev`) and inspect a pop detail page — the size line should read e.g. `size: 5  5.73` with the fractional value dimmed. Normal mode (`python main.py`) should show `size: 5 (100,000)` unchanged.

- [ ] **Step 3: Run full test suite**

```bash
pytest -v
```

Expected: all tests pass (no renderer tests exist, so no new failures possible here).

- [ ] **Step 4: Commit**

```bash
git add ui/detail_renderers.py
git commit -m "feat: show size_fractional in dev mode on pop detail page"
```

---

### Task 2: Splinter pop default name

**Files:**
- Modify: `logic/tick_logic.py` (splinter `Pop` constructor, around line 1850)
- Test: `tests/test_pop_splinter.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_pop_splinter.py`:

```python
def test_splinter_pop_gets_name_from_parent_label():
    """Splinter Pop should have name = '<parent label> Splinter'."""
    from logic.tick_logic import SPLINTER_CHECK_STRIDE, SPLINTER_DIVERGENCE_THRESHOLD
    from core.universe_core import Pop, SocialClass, Civilization, CivilizationScale
    from uuid import uuid4
    loop = _make_loop()

    civ_id = uuid4()
    loc_id = uuid4()
    civ = Civilization(
        id=civ_id,
        name="Test Civ",
        scale=CivilizationScale.CITY,
        established_beliefs={"domain:change": 0.9},
    )
    parent = Pop(
        social_class=SocialClass.COMMON,
        occupation="Merchant",
        current_location=loc_id,
        size_fractional=6.0,
        dominant_beliefs={"domain:order": 0.9},
        civilization_id=civ_id,
        visibility=1.0,
    )

    state = MagicMock()
    state.tick_number = SPLINTER_CHECK_STRIDE
    state.pops = {str(parent.id): parent}
    state.civilizations = {str(civ_id): civ}
    state.mortals = {}

    # Force divergence above threshold and rng to always trigger
    import unittest.mock as mock
    with mock.patch.object(loop, '_rng') as rng_mock:
        rng_mock.random.return_value = 0.0  # always splinter
        mutations, _ = loop._check_pop_splinters(state)

    assert len(mutations) == 1
    splinter_pop = mutations[0].new_value
    assert splinter_pop.name == "Merchant Splinter"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_pop_splinter.py::test_splinter_pop_gets_name_from_parent_label -v
```

Expected: FAIL — the splinter pop's `name` is `""` (empty), not `"Merchant Splinter"`.

- [ ] **Step 3: Add `name` to the splinter Pop constructor**

In `logic/tick_logic.py`, find the `splinter = Pop(` constructor (around line 1850). Add the `name` field:

```python
            splinter = Pop(
                id=uuid4(),
                name=f"{pop_label(pop)} Splinter",
                civilization_id=pop.civilization_id,
                species_id=pop.species_id,
                social_class=pop.social_class,
                wild_stratum=pop.wild_stratum,
                occupation=pop.occupation,
                current_location=pop.current_location,
                size_fractional=max(0.0, original_size + math.log10(fraction)),
                dominant_beliefs=original_beliefs,
                culture_tags=original_culture,
                rider_traits=dict(pop.rider_traits),
                parent_pop_id=pop.id,
                visibility=max(0.0, pop.visibility * 0.75),
                pinned=False,
                splinter_cooldown=SPLINTER_COOLDOWN_TICKS,
            )
```

(`pop_label` is already imported at line 49 of `tick_logic.py`.)

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_pop_splinter.py::test_splinter_pop_gets_name_from_parent_label -v
```

Expected: PASS.

- [ ] **Step 5: Run full test suite**

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add logic/tick_logic.py tests/test_pop_splinter.py
git commit -m "feat: seed splinter Pop name from parent label"
```

---

### Task 3: Auto-close pop detail tab when pop disappears

**Files:**
- Modify: `ui/detail_tabs.py:208` (`refresh_all` method)

> No unit test: `DetailTabManager` depends on a live Textual `TabbedContent` widget and cannot be instantiated in isolation. Verify via `--autoplay`.

- [ ] **Step 1: Update `refresh_all` in `DetailTabManager`**

In `ui/detail_tabs.py`, replace the `refresh_all` method (lines 208–219):

```python
    def refresh_all(self, state: "SimulationState") -> None:
        """Re-render every open detail tab against the current state."""
        to_close: list[str] = []
        for pane_id, dt in list(self._panes.items()):
            if dt.kind == "pop" and state.pops.get(dt.entity_id) is None:
                to_close.append(pane_id)
                continue
            try:
                dt.refresh_state(state)
            except Exception:
                pass
        for pane_id in to_close:
            self._close_pane(pane_id)
```

- [ ] **Step 2: Verify with autoplay**

```bash
python main.py --autoplay
```

Expected: completes 50 ticks with no errors. (Pop reabsorption happens mid-run; this verifies the close path doesn't crash.)

- [ ] **Step 3: Run full test suite**

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add ui/detail_tabs.py
git commit -m "feat: auto-close pop detail tab when pop is removed from simulation"
```
