# Pop Splinter/Reabsorption Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the deterministic per-tick pop splinter with a probabilistic stride-gated system, add divergence-scaled fraction, post-split belief nudge, mortal redistribution, civ-scale modifier, and passive gradual reabsorption.

**Architecture:** All changes live in `logic/tick_logic.py`. Pure helper functions (`_splinter_probability`, `_splinter_fraction`) are module-level and independently testable. The tick loop gates both splinter and reabsorption checks on `SPLINTER_CHECK_STRIDE`. The POP_SPLINTER mutation handler is extended to redistribute mortals after the parent's belief nudge is applied. A new `_check_pop_reabsorption` method handles gradual drain of converged splinters back into their parent (or best-matching local pop).

**Tech Stack:** Python, Pydantic, `math`, `cosine_similarity` (already imported in tick_logic), pytest/MagicMock.

**Design reference:** `docs/.dev/plans/pop-splinter-redesign.md`

---

## File Map

| File | Change |
|---|---|
| `logic/tick_logic.py` | Replace constants; add helpers; rewrite `_check_pop_splinters`; update `POP_SPLINTER` handler; add `_check_pop_reabsorption`; update tick loop call sites |
| `tests/test_pop_splinter.py` | New — unit tests for helpers, splinter check, mortal redistribution, reabsorption |

---

## Task 1: Replace constants and add pure helper functions

**Files:**
- Modify: `logic/tick_logic.py` (constants block, ~lines 105–134)
- Create: `tests/test_pop_splinter.py`

- [ ] **Step 1: Write failing tests for the two pure helpers**

Create `tests/test_pop_splinter.py`:

```python
import math
import pytest
from unittest.mock import MagicMock


# ── _splinter_probability ──────────────────────────────────────────────────

def test_splinter_probability_near_zero_at_threshold():
    from logic.tick_logic import _splinter_probability, SPLINTER_PROB_MIDPOINT
    # At divergence = 0.50 (threshold), probability should be well below 0.15
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
    # A positive offset (tribal civ) makes the same divergence less likely to split
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
```

- [ ] **Step 2: Run to confirm they fail**

```bash
source venv/bin/activate && pytest tests/test_pop_splinter.py -v 2>&1 | tail -20
```

Expected: ImportError or AttributeError — functions don't exist yet.

- [ ] **Step 3: Replace constants and add helpers in tick_logic.py**

Find and replace the old splinter constants block (currently around lines 105–134). Remove these three lines entirely:
```python
SPLINTER_FRACTION = 0.35
_SPLINTER_SIZE_DELTA    = math.log10(SPLINTER_FRACTION)          # ≈ -0.456
_SPLINTER_PARENT_DELTA  = math.log10(1.0 - SPLINTER_FRACTION)   # ≈ -0.187
```

Add these constants in their place (keep `SPLINTER_DIVERGENCE_THRESHOLD`, `SPLINTER_MIN_SIZE`, `SPLINTER_COOLDOWN_TICKS` unchanged):

```python
SPLINTER_CHECK_STRIDE        = 10     # ticks between splinter/reabsorption checks
SPLINTER_MIN_FRACTION        = 0.10   # smallest possible splinter (at threshold divergence)
SPLINTER_MAX_FRACTION        = 0.45   # largest possible splinter (at max divergence)
SPLINTER_BELIEF_NUDGE_FACTOR = 0.50   # how far parent nudges toward civ per split
SPLINTER_PROB_MIDPOINT       = 0.70   # divergence at which P(split) = 50%
SPLINTER_PROB_STEEPNESS      = 15.0   # sigmoid steepness

REABSORPTION_CONVERGENCE_THRESHOLD = 0.85   # cosine similarity floor to begin drain
REABSORPTION_DRAIN_FRACTION        = 0.20   # fraction of source drained per check

_CIV_SCALE_SPLINTER_OFFSET: dict[str, float] = {
    "nascent":         +0.20,
    "tribal":          +0.15,
    "city_state":      +0.08,
    "regional":        +0.03,
    "continental":      0.00,
    "planetary":       -0.03,
    "interplanetary":  -0.06,
    "interstellar":    -0.10,
    "intergalactic":   -0.15,
}
```

Then add these two module-level functions directly after the constants block:

```python
def _splinter_probability(divergence: float, effective_midpoint: float) -> float:
    """Sigmoid P(split): near-zero at threshold, near-certain above ~0.88."""
    x = SPLINTER_PROB_STEEPNESS * (divergence - effective_midpoint)
    return 1.0 / (1.0 + math.exp(-x))


def _splinter_fraction(divergence: float) -> float:
    """Fraction of parent that breaks away, scaled linearly with divergence magnitude."""
    span  = divergence - SPLINTER_DIVERGENCE_THRESHOLD
    scale = span / (1.0 - SPLINTER_DIVERGENCE_THRESHOLD)
    return SPLINTER_MIN_FRACTION + scale * (SPLINTER_MAX_FRACTION - SPLINTER_MIN_FRACTION)
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/test_pop_splinter.py -v 2>&1 | tail -15
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Run full suite — expect no regressions**

```bash
pytest -q 2>&1 | tail -5
```

Expected: 86 passed (existing count).

- [ ] **Step 6: Commit**

```bash
git add logic/tick_logic.py tests/test_pop_splinter.py
git commit -m "feat: add splinter probability/fraction helpers and redesign constants"
```

---

## Task 2: Rewrite `_check_pop_splinters` and stride-gate the call site

**Files:**
- Modify: `logic/tick_logic.py` — `_check_pop_splinters` method (~line 1685) and call site (~line 1670)

- [ ] **Step 1: Write a failing test for the stride gate**

Add to `tests/test_pop_splinter.py`:

```python
# ── _check_pop_splinters stride gate ──────────────────────────────────────

def _make_loop():
    import random
    from logic.tick_logic import TickLoop
    loop = TickLoop(rng_seed=42)
    return loop

def _make_minimal_state(tick_number=0):
    """State with no pops — splinter check should find nothing to do."""
    from logic.tick_logic import SimulationState, SPLINTER_CHECK_STRIDE
    s = MagicMock()
    s.tick_number = tick_number
    s.pops = {}
    s.civilizations = {}
    return s

def test_splinter_check_returns_empty_off_stride():
    from logic.tick_logic import SPLINTER_CHECK_STRIDE
    loop = _make_loop()
    state = _make_minimal_state(tick_number=1)   # not on stride
    mutations, events = loop._check_pop_splinters(state)
    assert mutations == []
    assert events == []

def test_splinter_check_runs_on_stride():
    from logic.tick_logic import SPLINTER_CHECK_STRIDE
    loop = _make_loop()
    state = _make_minimal_state(tick_number=SPLINTER_CHECK_STRIDE)
    # No pops → still empty, but the method ran without error
    mutations, events = loop._check_pop_splinters(state)
    assert mutations == []
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_pop_splinter.py::test_splinter_check_returns_empty_off_stride tests/test_pop_splinter.py::test_splinter_check_runs_on_stride -v 2>&1 | tail -15
```

Expected: FAIL — `_check_pop_splinters` currently runs every tick regardless.

- [ ] **Step 3: Rewrite `_check_pop_splinters`**

Replace the entire `_check_pop_splinters` method body with:

```python
    def _check_pop_splinters(
        self,
        state: SimulationState,
    ) -> tuple[list[StateMutation], list[NarrativeEvent]]:
        """Check every eligible Pop for belief divergence and emit splinter mutations.
        Only runs on SPLINTER_CHECK_STRIDE ticks; probabilistic gate per pop."""
        mutations: list[StateMutation] = []
        events: list[NarrativeEvent] = []
        if state.tick_number % SPLINTER_CHECK_STRIDE != 0:
            return mutations, events
        for pid, pop in list(state.pops.items()):
            if pop.asset_crew_for is not None:
                continue
            if pop.splinter_cooldown > 0:
                pop.splinter_cooldown -= 1
                continue
            if pop.size_fractional < SPLINTER_MIN_SIZE:
                continue
            if not pop.civilization_id:
                continue
            civ = state.civilizations.get(str(pop.civilization_id))
            if civ is None or not civ.established_beliefs:
                continue
            divergence = 1.0 - cosine_similarity(pop.dominant_beliefs, civ.established_beliefs)
            if divergence < SPLINTER_DIVERGENCE_THRESHOLD:
                continue

            scale_offset = _CIV_SCALE_SPLINTER_OFFSET.get(civ.scale.value, 0.0)
            effective_midpoint = SPLINTER_PROB_MIDPOINT + scale_offset
            if self._rng.random() >= _splinter_probability(divergence, effective_midpoint):
                continue

            top_div_tag = max(
                (t for t in pop.dominant_beliefs),
                key=lambda t: abs(
                    pop.dominant_beliefs.get(t, 0.0)
                    - civ.established_beliefs.get(t, 0.0)
                ),
                default=None,
            )
            short_label = top_div_tag.split(":", 1)[-1].title() if top_div_tag else "Unknown"
            domain_sentinel = f"§domain§{top_div_tag}§{short_label}§" if top_div_tag else short_label
            label = pop_label(pop)

            fraction = _splinter_fraction(divergence)
            original_size = pop.size_fractional

            # Shrink parent immediately (before mutation handler runs)
            pop.size_fractional = max(0.0, original_size + math.log10(1.0 - fraction))

            # Nudge parent beliefs toward civ established beliefs
            nudge = fraction * SPLINTER_BELIEF_NUDGE_FACTOR
            for tag, val in list(pop.dominant_beliefs.items()):
                civ_val = civ.established_beliefs.get(tag, 0.0)
                pop.dominant_beliefs[tag] = val + (civ_val - val) * nudge

            splinter_size = max(0.0, original_size + math.log10(fraction))
            splinter = Pop(
                id=uuid4(),
                civilization_id=pop.civilization_id,
                species_id=pop.species_id,
                social_class=pop.social_class,
                wild_stratum=pop.wild_stratum,
                occupation=pop.occupation,
                current_location=pop.current_location,
                size_fractional=splinter_size,
                dominant_beliefs=dict(pop.dominant_beliefs),  # pre-nudge snapshot via original; see note
                culture_tags=dict(pop.culture_tags),
                rider_traits=dict(pop.rider_traits),
                parent_pop_id=pop.id,
                visibility=max(0.0, pop.visibility * 0.75),
                pinned=False,
                splinter_cooldown=SPLINTER_COOLDOWN_TICKS,
            )
            # NOTE: splinter inherits the original divergent beliefs. The parent's
            # dominant_beliefs dict was mutated in place by the nudge above, so
            # dict(pop.dominant_beliefs) now gives the nudged values. We need the
            # PRE-nudge beliefs for the splinter. Capture them before nudging:
            # (see corrected order in step 3 note below)

            _parent_sentinel  = f"§pop§{pop.id}§{label}§"
            _splinter_sentinel = f"§pop§{splinter.id}§{label}§"
            note = (
                f"[Pop splinter] Part of {_parent_sentinel} ({civ.name}) "
                f"broke away as {_splinter_sentinel} over {domain_sentinel} "
                f"(divergence {divergence:.2f})."
            )
            pop.splinter_cooldown = SPLINTER_COOLDOWN_TICKS
            mutations.append(StateMutation(
                mutation_type=MutationType.POP_SPLINTER,
                target_id=pop.id,
                field="pops",
                new_value=splinter,
                note=note,
            ))
            events.append(NarrativeEvent(
                text=note,
                in_window=is_in_window(pop),
            ))
        return mutations, events
```

**Important:** The splinter must capture the PRE-nudge beliefs. Fix the ordering — capture original beliefs before nudging, then create splinter with those:

```python
            # Capture original (deviant) beliefs before nudging parent
            original_beliefs = dict(pop.dominant_beliefs)

            # Nudge parent beliefs toward civ
            nudge = fraction * SPLINTER_BELIEF_NUDGE_FACTOR
            for tag, val in list(pop.dominant_beliefs.items()):
                civ_val = civ.established_beliefs.get(tag, 0.0)
                pop.dominant_beliefs[tag] = val + (civ_val - val) * nudge

            splinter = Pop(
                ...
                dominant_beliefs=original_beliefs,   # splinter keeps the deviant beliefs
                ...
            )
```

- [ ] **Step 4: Remove the `child_pop_ids` guard**

The old method had `if pop.child_pop_ids: continue`. This line is gone in the rewrite above — confirm it is not present in the new method.

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_pop_splinter.py -v 2>&1 | tail -20
```

Expected: all tests PASS.

- [ ] **Step 6: Run full suite**

```bash
pytest -q 2>&1 | tail -5
```

Expected: 86+ passed, 0 failed.

- [ ] **Step 7: Commit**

```bash
git add logic/tick_logic.py tests/test_pop_splinter.py
git commit -m "feat: rewrite _check_pop_splinters with probabilistic stride-gated splits"
```

---

## Task 3: Update POP_SPLINTER mutation handler — mortal redistribution

**Files:**
- Modify: `logic/tick_logic.py` — `_apply_mutations` POP_SPLINTER branch (~line 6222)

- [ ] **Step 1: Write failing tests for mortal redistribution**

Add to `tests/test_pop_splinter.py`:

```python
# ── mortal redistribution ─────────────────────────────────────────────────

from uuid import uuid4 as _uuid4

def _make_pop(beliefs, size=6.0, location_id="loc-1", occupation="Artist"):
    from core.universe_core import Pop, SocialClass
    return Pop(
        social_class=SocialClass.COMMON,
        occupation=occupation,
        current_location=_uuid4(),
        size_fractional=size,
        dominant_beliefs=beliefs,
        civilization_id=_uuid4(),
    )

def _make_mortal(beliefs, pop_id):
    from core.universe_core import NotableMortal
    m = NotableMortal(name="Test Mortal", pop_id=pop_id, belief_tags=beliefs)
    return m

def test_mortal_stays_with_parent_when_more_similar():
    """Mortal whose beliefs match parent more than splinter stays in parent."""
    parent   = _make_pop({"domain:order": 0.6, "domain:change": 0.2})
    splinter = _make_pop({"domain:order": 0.1, "domain:change": 0.8})
    mortal   = _make_mortal({"domain:order": 0.55, "domain:change": 0.25}, pop_id=parent.id)

    parent.notable_mortal_ids = [mortal.id]
    splinter.notable_mortal_ids = []

    from logic.tick_logic import _redistribute_mortals_on_splinter
    moved = _redistribute_mortals_on_splinter(parent, splinter, {str(mortal.id): mortal})

    assert mortal.id not in moved   # stayed with parent
    assert mortal.pop_id == parent.id

def test_mortal_moves_to_splinter_when_more_similar():
    """Mortal whose beliefs match splinter more moves to it."""
    parent   = _make_pop({"domain:order": 0.6, "domain:change": 0.2})
    splinter = _make_pop({"domain:order": 0.1, "domain:change": 0.8})
    mortal   = _make_mortal({"domain:order": 0.15, "domain:change": 0.75}, pop_id=parent.id)

    parent.notable_mortal_ids = [mortal.id]
    splinter.notable_mortal_ids = []

    from logic.tick_logic import _redistribute_mortals_on_splinter
    moved = _redistribute_mortals_on_splinter(parent, splinter, {str(mortal.id): mortal})

    assert mortal.id in moved
    assert mortal.pop_id == splinter.id
    assert mortal.id in splinter.notable_mortal_ids
    assert mortal.id not in parent.notable_mortal_ids
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_pop_splinter.py::test_mortal_stays_with_parent_when_more_similar tests/test_pop_splinter.py::test_mortal_moves_to_splinter_when_more_similar -v 2>&1 | tail -10
```

Expected: ImportError — `_redistribute_mortals_on_splinter` does not exist yet.

- [ ] **Step 3: Add `_redistribute_mortals_on_splinter` as a module-level function**

Add near the other module-level helpers in `tick_logic.py` (after `_splinter_fraction`):

```python
def _redistribute_mortals_on_splinter(
    parent: "Pop",
    splinter: "Pop",
    mortals: "dict[str, NotableMortal]",
) -> list["UUID"]:
    """Re-assign notable mortals between parent and splinter based on belief similarity.

    Returns list of mortal UUIDs that moved to the splinter.
    Called after parent belief nudge so the two pops have meaningfully different beliefs.
    """
    moved: list["UUID"] = []
    for mid in list(parent.notable_mortal_ids):
        mortal = mortals.get(str(mid))
        if mortal is None:
            continue
        sim_parent   = cosine_similarity(mortal.belief_tags, parent.dominant_beliefs)
        sim_splinter = cosine_similarity(mortal.belief_tags, splinter.dominant_beliefs)
        if sim_splinter > sim_parent:
            parent.notable_mortal_ids.remove(mid)
            splinter.notable_mortal_ids.append(mid)
            mortal.pop_id = splinter.id
            moved.append(mid)
    return moved
```

- [ ] **Step 4: Call `_redistribute_mortals_on_splinter` from the POP_SPLINTER mutation handler**

Find the `elif m.mutation_type == MutationType.POP_SPLINTER:` block (~line 6222). After wiring the splinter into the civ and PopLocation (the existing code), add:

```python
                    # Redistribute mortals: those more similar to splinter move over
                    moved_ids = _redistribute_mortals_on_splinter(
                        parent_pop, splinter, state.mortals
                    )
                    # Emit narrative for each moved mortal (if in window)
                    for mid in moved_ids:
                        mortal = state.mortals.get(str(mid))
                        if mortal is None:
                            continue
                        if is_in_window(mortal) and is_in_window(parent_pop):
                            _mortal_s = f"§mortal§{mortal.id}§{mortal.name}§" if hasattr(mortal, 'id') else mortal.name
                            result_narrative = (
                                f"[Pop splinter] {_mortal_s} sided with the splinter faction."
                            )
                            # NOTE: result is not directly available here; append to a
                            # local list and extend result.narrative_events at the call site.
```

**NOTE:** The mutation handler does not have direct access to `result`. The cleanest approach is to collect moved-mortal narratives inside the `POP_SPLINTER` mutation handler and return them via a separate list, or simply append to `result.passive_result.narrative_events` if `result` is in scope. Check the handler signature — if `result` is not available, emit mortal narratives as part of the splinter event list in `_check_pop_splinters` by passing moved mortal info through the `StateMutation.note` field, or do a second pass after mutations are applied.

**Simplest approach that avoids the scope problem:** move mortal redistribution directly into `_check_pop_splinters` after the `Pop` object is created (the parent is already nudged; compare against the nudged parent and the new splinter object before it's registered in state):

In `_check_pop_splinters`, after creating `splinter` and before building `note`:

```python
            # Redistribute mortals before emitting mutation
            moved_mortal_ids = _redistribute_mortals_on_splinter(
                pop, splinter, state.mortals
            )
            for mid in moved_mortal_ids:
                mortal = state.mortals.get(str(mid))
                if mortal and is_in_window(mortal) and is_in_window(pop):
                    _m_sentinel = f"§mortal§{mortal.id}§{mortal.name}§"
                    events.append(NarrativeEvent(
                        text=f"[Pop splinter] {_m_sentinel} sided with the splinter faction.",
                        in_window=True,
                    ))
```

Then the mutation handler only needs to register the splinter (as it already does). The mortal fields (`pop_id`, `notable_mortal_ids`) are mutated in place by `_redistribute_mortals_on_splinter`.

**Note on `§mortal§` sentinel:** Verify `_ENTITY_SENTINEL_RE` in `display.py` includes `mortal`. If not, add it (same pattern as the `species` addition). Check `_LOG_LINK_COLORS` for a `mortal` entry — it is already there (`"mortal": "#a080c0"`), so only the regex needs updating if missing.

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_pop_splinter.py -v 2>&1 | tail -20
```

Expected: all tests PASS.

- [ ] **Step 6: Run full suite**

```bash
pytest -q 2>&1 | tail -5
```

Expected: 86+ passed, 0 failed.

- [ ] **Step 7: Commit**

```bash
git add logic/tick_logic.py tests/test_pop_splinter.py
git commit -m "feat: redistribute mortals between parent and splinter on pop split"
```

---

## Task 4: Add `_check_pop_reabsorption`

**Files:**
- Modify: `logic/tick_logic.py` — add new method on `TickLoop`, after `_check_pop_splinters`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_pop_splinter.py`:

```python
# ── _check_pop_reabsorption ───────────────────────────────────────────────

def _make_state_with_pops(pops_dict, civs_dict=None, tick=10):
    s = MagicMock()
    s.tick_number = tick
    s.pops = pops_dict
    s.civilizations = civs_dict or {}
    s.locations = {}
    s.mortals = {}
    return s

def test_reabsorption_skips_vessel_crew():
    from logic.tick_logic import TickLoop, SPLINTER_CHECK_STRIDE
    from core.universe_core import Pop, SocialClass
    import uuid

    loc_id = uuid.uuid4()
    civ_id = uuid.uuid4()

    crew = Pop(
        social_class=SocialClass.COMMON,
        occupation="Crew",
        current_location=loc_id,
        size_fractional=4.5,
        dominant_beliefs={"domain:order": 0.6},
        civilization_id=civ_id,
        asset_crew_for="ship",
    )
    state = _make_state_with_pops({str(crew.id): crew}, tick=SPLINTER_CHECK_STRIDE)
    loop = _make_loop()
    mutations, events = loop._check_pop_reabsorption(state)
    assert mutations == []

def test_reabsorption_skips_off_stride():
    from logic.tick_logic import TickLoop, SPLINTER_CHECK_STRIDE
    from core.universe_core import Pop, SocialClass
    import uuid

    loc_id = uuid.uuid4()
    source = Pop(
        social_class=SocialClass.COMMON,
        occupation="Artist",
        current_location=loc_id,
        size_fractional=4.5,
        dominant_beliefs={"domain:order": 0.1},
        civilization_id=uuid.uuid4(),
    )
    state = _make_state_with_pops({str(source.id): source}, tick=1)  # off-stride
    loop = _make_loop()
    mutations, events = loop._check_pop_reabsorption(state)
    assert mutations == []

def test_reabsorption_drains_source_into_parent():
    from logic.tick_logic import TickLoop, SPLINTER_CHECK_STRIDE, REABSORPTION_DRAIN_FRACTION, MutationType
    from core.universe_core import Pop, SocialClass
    import uuid, math

    loc_id = uuid.uuid4()
    civ_id = uuid.uuid4()
    beliefs = {"domain:order": 0.6, "domain:change": 0.3}

    parent = Pop(
        social_class=SocialClass.COMMON,
        occupation="Artist",
        current_location=loc_id,
        size_fractional=6.0,
        dominant_beliefs=dict(beliefs),
        civilization_id=civ_id,
    )
    source = Pop(
        social_class=SocialClass.COMMON,
        occupation="Artist",
        current_location=loc_id,
        size_fractional=4.5,
        dominant_beliefs=dict(beliefs),   # identical → cosine sim = 1.0
        civilization_id=civ_id,
        parent_pop_id=parent.id,
    )

    state = _make_state_with_pops(
        {str(parent.id): parent, str(source.id): source},
        tick=SPLINTER_CHECK_STRIDE,
    )
    loop = _make_loop()
    mutations, events = loop._check_pop_reabsorption(state)

    types = [m.mutation_type for m in mutations]
    assert MutationType.POP_SIZE_CHANGE in types   # source shrank
    # Two POP_SIZE_CHANGE mutations: one for source (negative delta), one for parent (positive)
    size_changes = [m for m in mutations if m.mutation_type == MutationType.POP_SIZE_CHANGE]
    assert len(size_changes) == 2
    source_mut = next(m for m in size_changes if str(m.target_id) == str(source.id))
    parent_mut = next(m for m in size_changes if str(m.target_id) == str(parent.id))
    assert source_mut.delta < 0
    assert parent_mut.delta > 0
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_pop_splinter.py::test_reabsorption_skips_vessel_crew tests/test_pop_splinter.py::test_reabsorption_skips_off_stride tests/test_pop_splinter.py::test_reabsorption_drains_source_into_parent -v 2>&1 | tail -15
```

Expected: AttributeError — `_check_pop_reabsorption` does not exist.

- [ ] **Step 3: Implement `_check_pop_reabsorption`**

Add as a new method on `TickLoop`, directly after `_check_pop_splinters`:

```python
    def _check_pop_reabsorption(
        self,
        state: SimulationState,
    ) -> tuple[list[StateMutation], list[NarrativeEvent]]:
        """Gradually drain small converged splinter pops back into their parent (or best local match).
        Runs on the same stride as _check_pop_splinters."""
        mutations: list[StateMutation] = []
        events: list[NarrativeEvent] = []
        if state.tick_number % SPLINTER_CHECK_STRIDE != 0:
            return mutations, events

        for pid, pop in list(state.pops.items()):
            if pop.asset_crew_for is not None:
                continue
            if pop.preaching_imago_id is not None:
                continue
            if pop.size_fractional >= SPLINTER_MIN_SIZE + 1.0:
                # Only drain pops that are small (near or below min + buffer)
                # Larger pops are not candidates for passive reabsorption
                continue

            # Find target: parent first, then best local match
            target = self._find_reabsorption_target(pop, state)
            if target is None:
                continue

            sim = cosine_similarity(pop.dominant_beliefs, target.dominant_beliefs)
            if sim < REABSORPTION_CONVERGENCE_THRESHOLD:
                continue

            # Drain fraction of source into target (log-space, population-conserving)
            transferred = (10 ** pop.size_fractional) * REABSORPTION_DRAIN_FRACTION
            new_target_size = math.log10(10 ** target.size_fractional + transferred)
            new_source_size = pop.size_fractional + math.log10(1.0 - REABSORPTION_DRAIN_FRACTION)

            delta_source = new_source_size - pop.size_fractional   # negative
            delta_target = new_target_size - target.size_fractional  # positive

            mutations.append(StateMutation(
                mutation_type=MutationType.POP_SIZE_CHANGE,
                target_id=pop.id,
                field="size_fractional",
                delta=delta_source,
            ))
            mutations.append(StateMutation(
                mutation_type=MutationType.POP_SIZE_CHANGE,
                target_id=target.id,
                field="size_fractional",
                delta=delta_target,
            ))

            # If source will drop below minimum, schedule full absorption
            if new_source_size < SPLINTER_MIN_SIZE:
                mutations.append(StateMutation(
                    mutation_type=MutationType.POP_ABSORBED,
                    target_id=pop.id,
                    field="pops",
                    new_value=str(target.id),
                    note=f"[Pop reabsorption] {pop_label(pop)} fully reintegrated into {pop_label(target)}.",
                ))
                if is_in_window(pop) or is_in_window(target):
                    events.append(NarrativeEvent(
                        text=(
                            f"[Pop reabsorption] §pop§{pop.id}§{pop_label(pop)}§ "
                            f"fully reintegrated into §pop§{target.id}§{pop_label(target)}§."
                        ),
                        in_window=is_in_window(pop) or is_in_window(target),
                    ))
            else:
                if is_in_window(pop) or is_in_window(target):
                    events.append(NarrativeEvent(
                        text=(
                            f"[Pop reabsorption] §pop§{pop.id}§{pop_label(pop)}§ "
                            f"is drifting back into §pop§{target.id}§{pop_label(target)}§."
                        ),
                        in_window=is_in_window(pop) or is_in_window(target),
                    ))

        return mutations, events

    def _find_reabsorption_target(
        self,
        pop: "Pop",
        state: SimulationState,
    ) -> "Optional[Pop]":
        """Return the best reabsorption target for pop: parent first, then best local match."""
        # Guard: target must not be a Preach Imago goal
        def _eligible_target(p: "Pop") -> bool:
            return (
                p.id != pop.id
                and p.asset_crew_for is None
                and p.preaching_imago_id is None
                and p.stratum == pop.stratum
                and p.occupation == pop.occupation
                and p.current_location == pop.current_location
                and p.size_fractional >= pop.size_fractional  # target must be larger
            )

        # Try parent first
        if pop.parent_pop_id is not None:
            parent = state.pops.get(str(pop.parent_pop_id))
            if parent is not None and _eligible_target(parent):
                return parent

        # Fall back to best-matching local pop by cosine similarity
        best: "Optional[Pop]" = None
        best_sim: float = -1.0
        for other in state.pops.values():
            if not _eligible_target(other):
                continue
            sim = cosine_similarity(pop.dominant_beliefs, other.dominant_beliefs)
            if sim > best_sim:
                best_sim = sim
                best = other
        return best
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_pop_splinter.py -v 2>&1 | tail -20
```

Expected: all tests PASS.

- [ ] **Step 5: Run full suite**

```bash
pytest -q 2>&1 | tail -5
```

Expected: 86+ passed, 0 failed.

- [ ] **Step 6: Commit**

```bash
git add logic/tick_logic.py tests/test_pop_splinter.py
git commit -m "feat: add passive pop reabsorption with gradual drain into parent"
```

---

## Task 5: Wire stride gate and reabsorption into tick loop, then push

**Files:**
- Modify: `logic/tick_logic.py` — tick loop Phase 2 (~line 1670)

- [ ] **Step 1: Update the call site**

Find this block (~line 1670):

```python
        # ── Pop splinter check ─────────────────────────
        # A Pop splits when its beliefs diverge too far from civ.established_beliefs.
        # Runs after conformity pressure so we react to this tick's final belief state.
        splinter_mutations, splinter_events = self._check_pop_splinters(state)
        result.entity_mutations.extend(splinter_mutations)
        result.narrative_events.extend(splinter_events)
```

Replace with:

```python
        # ── Pop splinter and reabsorption checks ────────
        # Both stride-gated; _check_pop_splinters gates internally on tick_number.
        # Runs after conformity pressure so we react to this tick's final belief state.
        splinter_mutations, splinter_events = self._check_pop_splinters(state)
        result.entity_mutations.extend(splinter_mutations)
        result.narrative_events.extend(splinter_events)
        reabsorb_mutations, reabsorb_events = self._check_pop_reabsorption(state)
        result.entity_mutations.extend(reabsorb_mutations)
        result.narrative_events.extend(reabsorb_events)
```

- [ ] **Step 2: Check `_ENTITY_SENTINEL_RE` includes `mortal`**

In `ui/display.py`, verify the regex:

```python
_ENTITY_SENTINEL_RE = re.compile(r"§(pop|civ|imago|species|domain)§([^§]+)§([^§]+)§")
```

If `mortal` is missing, add it:

```python
_ENTITY_SENTINEL_RE = re.compile(r"§(pop|civ|imago|species|domain|mortal)§([^§]+)§([^§]+)§")
```

- [ ] **Step 3: Run full suite**

```bash
pytest -q 2>&1 | tail -5
```

Expected: 86+ passed, 0 failed.

- [ ] **Step 4: Run a short autoplay to verify no crashes**

```bash
source venv/bin/activate && python main.py --autoplay 2>&1 | tail -20
```

Expected: completes without exception; some splinter events visible in output after tick 10.

- [ ] **Step 5: Final commit and push**

```bash
git add logic/tick_logic.py ui/display.py tests/test_pop_splinter.py
git commit -m "feat: wire pop reabsorption into tick loop; add mortal sentinel to regex"
git push
```

---

## Post-implementation tuning notes

- Watch for: frequency of splinter events (should be occasional, not every stride)
- Watch for: accumulation of micro-pops (reabsorption should drain these over time)
- Watch for: parent belief nudge too strong (pop immediately falls below threshold, no repeat events)
- Parameters to adjust if needed: `SPLINTER_PROB_MIDPOINT`, `SPLINTER_PROB_STEEPNESS`, `SPLINTER_BELIEF_NUDGE_FACTOR`, `REABSORPTION_CONVERGENCE_THRESHOLD`
- The `child_pop_ids` list on Pop is now unused for splinter gating — it still tracks lineage for display purposes, leave it in place
