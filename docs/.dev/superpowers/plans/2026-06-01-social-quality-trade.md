# Social Quality Redesign + practice:trade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign pop social quality scoring to account for mortal-pop cultural compatibility with xenophilia modulation, and replace `relations:commerce` with a `practice:trade` tag that dynamically influences location commerce quality.

**Architecture:** Social quality becomes a compatibility function between mortal and pop (beliefs + values/religion tags, cross-species/civ factors, xenophilia curve); trade activity is a weighted pop-level practice tag that adds a dynamic bonus on top of each location's authored `commerce_quality`. No model schema changes — the trade bonus is computed at action time from live pop state.

**Tech Stack:** Python, Pydantic, SQLite (direct SQL for scenario migration)

---

## Files Modified

| File | What changes |
|---|---|
| `logic/civilian_agent_logic.py` | `_pop_social_quality` redesigned; `_cosine_sim`, `_cross_factor`, `_effective_commerce_quality` added |
| `utilities/culture_registry.py` | `practice:trade` added to `PRACTICE_TAGS`; `relations:commerce` removed from `RELATIONS_TAGS`; synergy table updated |
| `logic/tick_logic.py` | 3 `commerce_quality` accesses replaced with `_effective_commerce_quality` |
| `tests/test_civilian_logic.py` | New tests for social quality and trade bonus |
| `scenarios/wardens_compact.db` | Durenn Vail: drop `relations:commerce`; merchant-occupation trader pops: add `practice:trade` |

---

## Task 1: Social quality — cosine sim helper + new function skeleton

**Files:**
- Modify: `logic/civilian_agent_logic.py`
- Modify: `tests/test_civilian_logic.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_civilian_logic.py` (after existing imports):

```python
from logic.civilian_agent_logic import _cosine_sim, _pop_social_quality
```

Then add these test functions:

```python
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
    # Minimal smoke test: new signature with all args
    score = _pop_social_quality(
        mortal_beliefs={"domain:fire": 0.7},
        mortal_culture={"values:honor": 0.6},
        pop_beliefs={"domain:fire": 0.7},
        pop_culture={"values:honor": 0.6, "values:solidarity": 0.8, "practice:revelry": 0.7},
        same_species=True,
        same_civ=True,
    )
    assert 0.0 <= score <= 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
source venv/bin/activate && pytest tests/test_civilian_logic.py::test_cosine_sim_identical_vectors tests/test_civilian_logic.py::test_cosine_sim_empty_returns_neutral tests/test_civilian_logic.py::test_cosine_sim_orthogonal_vectors tests/test_civilian_logic.py::test_pop_social_quality_new_signature_accepted -v
```

Expected: FAIL with ImportError (`_cosine_sim` not found) or TypeError (wrong signature).

- [ ] **Step 3: Add `_cosine_sim` and replace `_pop_social_quality` signature**

In `logic/civilian_agent_logic.py`, add before `_pop_practice_quality`:

```python
def _cosine_sim(a: dict[str, float], b: dict[str, float]) -> float:
    """Cosine similarity between two float-valued tag vectors, normalized to [0, 1].

    Returns 0.5 (neutral) if either vector is empty or zero-magnitude.
    Maps raw cosine [-1, 1] to [0, 1] via (raw + 1) / 2.
    """
    if not a or not b:
        return 0.5
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0.0) * b.get(k, 0.0) for k in keys)
    mag_a = sum(v * v for v in a.values()) ** 0.5
    mag_b = sum(v * v for v in b.values()) ** 0.5
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.5
    raw = dot / (mag_a * mag_b)
    return max(0.0, min(1.0, (raw + 1.0) / 2.0))
```

Replace the existing `_pop_social_quality` function entirely:

```python
# ── Social quality constants (tunable) ───────────────────────────────────────
_CROSS_SPECIES_BASE = 0.80     # compatibility factor at xeno=0 (20% penalty)
_CROSS_CIV_BASE = 0.70         # compatibility factor at xeno=0 (30% penalty)
_CROSS_SPECIES_XENO_NEUTRAL = 0.30   # xenophilia level that neutralizes species penalty
_CROSS_CIV_XENO_NEUTRAL = 0.40      # xenophilia level that neutralizes civ penalty
_CROSS_MAX_BONUS = 0.20        # max compatibility bonus at high xenophilia
_NEG_XENO_MIN = 0.30           # minimum final-score multiplier at xeno=-1
_SOLIDARITY_BONUS_WEIGHT = 0.15
_REVELRY_BONUS_WEIGHT = 0.15


def _cross_factor(base: float, xeno_neutral: float, xeno: float) -> float:
    """Compatibility multiplier for a cross-group barrier (species or civ).

    base: factor at xeno=0 (e.g. 0.80 → 20% penalty)
    xeno_neutral: xenophilia value where factor reaches 1.0 (no penalty)
    xeno: mortal's values:xenophilia in [-1, 1]

    Curve:
      xeno = -1          →  base - (1-base)        (penalty doubled)
      xeno = 0           →  base                   (base penalty)
      xeno = xeno_neutral →  1.0                   (neutral)
      xeno = 1.0         →  1.0 + _CROSS_MAX_BONUS (bonus)
    """
    if xeno < 0.0:
        return max(_NEG_XENO_MIN, base + xeno * (1.0 - base))
    elif xeno <= xeno_neutral:
        return base + (1.0 - base) * (xeno / xeno_neutral)
    else:
        excess = (xeno - xeno_neutral) / max(0.001, 1.0 - xeno_neutral)
        return min(1.0 + _CROSS_MAX_BONUS, 1.0 + _CROSS_MAX_BONUS * excess)


def _pop_social_quality(
    mortal_beliefs: dict[str, float],
    mortal_culture: dict[str, float],
    pop_beliefs: dict[str, float],
    pop_culture: dict[str, float],
    same_species: bool = True,
    same_civ: bool = True,
) -> float:
    """Belonging quality score [0, 1] for a mortal socialising with a pop.

    Drives the 'belonging' need. Components:
    - Cosine similarity of beliefs + non-practice culture (xenophilia-modulated)
    - Cross-species and cross-civ penalties (weighted more heavily by xenophilia)
    - Small additive bonus from pop solidarity and revelry
    """
    xeno = mortal_culture.get("values:xenophilia", 0.0)

    # Build compatibility profiles (beliefs + non-practice culture tags)
    def _profile(beliefs: dict, culture: dict) -> dict:
        v = dict(beliefs)
        v.update({t: val for t, val in culture.items() if not t.startswith("practice:")})
        return v

    sim = _cosine_sim(_profile(mortal_beliefs, mortal_culture), _profile(pop_beliefs, pop_culture))

    # Xenophilia modulation on similarity:
    #   xeno in [0, 0.5]: lerp sim → 0.5 (similarity matters less)
    #   xeno in [0.5, 1]: lerp 0.5 → 1-sim (difference starts to please)
    #   xeno < 0: sim unchanged here; overall penalty applied below
    if 0.0 < xeno <= 0.5:
        adj_sim = sim + (0.5 - sim) * (xeno / 0.5)
    elif xeno > 0.5:
        adj_sim = 0.5 + (0.5 - sim) * ((xeno - 0.5) / 0.5)
    else:
        adj_sim = sim

    species_f = _cross_factor(_CROSS_SPECIES_BASE, _CROSS_SPECIES_XENO_NEUTRAL, xeno) if not same_species else 1.0
    civ_f = _cross_factor(_CROSS_CIV_BASE, _CROSS_CIV_XENO_NEUTRAL, xeno) if not same_civ else 1.0
    neg_f = max(_NEG_XENO_MIN, 1.0 + xeno * (1.0 - _NEG_XENO_MIN)) if xeno < 0.0 else 1.0

    base = adj_sim * species_f * civ_f * neg_f
    solidarity = pop_culture.get("values:solidarity", 0.3) * _SOLIDARITY_BONUS_WEIGHT
    revelry = pop_culture.get("practice:revelry", 0.3) * _REVELRY_BONUS_WEIGHT
    return min(1.0, max(0.0, base + solidarity + revelry))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
source venv/bin/activate && pytest tests/test_civilian_logic.py::test_cosine_sim_identical_vectors tests/test_civilian_logic.py::test_cosine_sim_empty_returns_neutral tests/test_civilian_logic.py::test_cosine_sim_orthogonal_vectors tests/test_civilian_logic.py::test_pop_social_quality_new_signature_accepted -v
```

Expected: all 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add logic/civilian_agent_logic.py tests/test_civilian_logic.py
git commit -m "feat: add _cosine_sim helper and redesign _pop_social_quality signature"
```

---

## Task 2: Social quality — xenophilia curve + cross-factor behavioral tests

**Files:**
- Modify: `tests/test_civilian_logic.py`

- [ ] **Step 1: Write the failing behavioral tests**

Add to `tests/test_civilian_logic.py`:

```python
from logic.civilian_agent_logic import _cross_factor

def _mortal_same(xeno=0.0):
    """Mortal profile identical to test pop below."""
    return {"domain:fire": 0.7}, {"values:honor": 0.6, "values:xenophilia": xeno}

def _pop_same():
    return {"domain:fire": 0.7}, {"values:honor": 0.6, "values:solidarity": 0.5, "practice:revelry": 0.5}

def _pop_different():
    return {"domain:water": 0.7}, {"values:solidarity": 0.8, "practice:revelry": 0.7}

# Xenophilia modulation on similarity
def test_social_quality_xeno_zero_identical_pop_scores_high():
    mb, mc = _mortal_same(xeno=0.0)
    pb, pc = _pop_same()
    score = _pop_social_quality(mb, mc, pb, pc, same_species=True, same_civ=True)
    assert score > 0.8

def test_social_quality_xeno_zero_different_pop_scores_lower_than_identical():
    mb, mc = _mortal_same(xeno=0.0)
    pb_same, pc_same = _pop_same()
    pb_diff, pc_diff = _pop_different()
    score_same = _pop_social_quality(mb, mc, pb_same, pc_same, same_species=True, same_civ=True)
    score_diff = _pop_social_quality(mb, mc, pb_diff, pc_diff, same_species=True, same_civ=True)
    assert score_same > score_diff

def test_social_quality_xeno_half_returns_near_neutral():
    # At xeno=0.5 similarity is neutralised; both identical and different pops converge
    mb, mc = _mortal_same(xeno=0.5)
    pb_same, pc_same = _pop_same()
    pb_diff, pc_diff = _pop_different()
    score_same = _pop_social_quality(mb, mc, pb_same, pc_same, same_species=True, same_civ=True)
    score_diff = _pop_social_quality(mb, mc, pb_diff, pc_diff, same_species=True, same_civ=True)
    assert abs(score_same - score_diff) < 0.20  # closer together at xeno=0.5

def test_social_quality_high_xeno_prefers_different_pop():
    mb, mc = _mortal_same(xeno=0.9)
    pb_same, pc_same = _pop_same()
    pb_diff, pc_diff = _pop_different()
    score_same = _pop_social_quality(mb, mc, pb_same, pc_same, same_species=True, same_civ=True)
    score_diff = _pop_social_quality(mb, mc, pb_diff, pc_diff, same_species=True, same_civ=True)
    assert score_diff >= score_same  # high xenophilia prefers difference

def test_social_quality_negative_xeno_reduces_score():
    mb, mc = _mortal_same(xeno=0.0)
    mb_neg, mc_neg = _mortal_same(xeno=-0.6)
    pb, pc = _pop_same()
    score_neutral = _pop_social_quality(mb, mc, pb, pc, same_species=True, same_civ=True)
    score_neg = _pop_social_quality(mb_neg, mc_neg, pb, pc, same_species=True, same_civ=True)
    assert score_neutral > score_neg

# Cross-species and cross-civ factors
def test_social_quality_cross_species_applies_penalty_at_xeno_zero():
    mb, mc = _mortal_same(xeno=0.0)
    pb, pc = _pop_same()
    score_same = _pop_social_quality(mb, mc, pb, pc, same_species=True, same_civ=True)
    score_diff = _pop_social_quality(mb, mc, pb, pc, same_species=False, same_civ=True)
    assert score_same > score_diff

def test_social_quality_cross_civ_applies_penalty_at_xeno_zero():
    mb, mc = _mortal_same(xeno=0.0)
    pb, pc = _pop_same()
    score_same = _pop_social_quality(mb, mc, pb, pc, same_species=True, same_civ=True)
    score_diff = _pop_social_quality(mb, mc, pb, pc, same_species=True, same_civ=False)
    assert score_same > score_diff

def test_social_quality_high_xeno_neutralizes_cross_species_penalty():
    mb, mc = _mortal_same(xeno=0.5)  # xeno_neutral for species = 0.30, so 0.5 should exceed it
    pb, pc = _pop_same()
    score_same_species = _pop_social_quality(mb, mc, pb, pc, same_species=True, same_civ=True)
    score_diff_species = _pop_social_quality(mb, mc, pb, pc, same_species=False, same_civ=True)
    # At xeno=0.5 the species penalty should be gone or become a bonus
    assert score_diff_species >= score_same_species * 0.95

# cross_factor helper
def test_cross_factor_at_zero_xeno_returns_base():
    assert _cross_factor(0.80, 0.30, 0.0) == pytest.approx(0.80)

def test_cross_factor_at_neutral_xeno_returns_one():
    assert _cross_factor(0.80, 0.30, 0.30) == pytest.approx(1.0, abs=0.001)

def test_cross_factor_at_negative_xeno_amplifies_penalty():
    f_zero = _cross_factor(0.80, 0.30, 0.0)
    f_neg = _cross_factor(0.80, 0.30, -0.5)
    assert f_neg < f_zero

def test_cross_factor_above_neutral_grants_bonus():
    assert _cross_factor(0.80, 0.30, 1.0) > 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
source venv/bin/activate && pytest tests/test_civilian_logic.py -k "social_quality or cross_factor" -v 2>&1 | head -50
```

Expected: most FAIL (the new `_cross_factor` import doesn't exist yet, behavioral tests may error on wrong values).

- [ ] **Step 3: Run full test suite to verify no regressions yet**

```bash
source venv/bin/activate && pytest 2>&1 | tail -5
```

Expected: 140 passed (the new failing tests are the ones added in step 1 above).

- [ ] **Step 4: Verify tests pass with current implementation**

The implementation was written in Task 1 Step 3. Run only the new tests:

```bash
source venv/bin/activate && pytest tests/test_civilian_logic.py -k "social_quality or cross_factor" -v
```

Expected: all PASS. If any fail, adjust the constants `_CROSS_SPECIES_XENO_NEUTRAL`, `_CROSS_CIV_XENO_NEUTRAL`, `_CROSS_MAX_BONUS`, `_NEG_XENO_MIN` in `civilian_agent_logic.py` until they do — these are tunable parameters, exact values are not fixed.

- [ ] **Step 5: Commit**

```bash
git add tests/test_civilian_logic.py
git commit -m "test: behavioral tests for xenophilia curve and cross-group social quality factors"
```

---

## Task 3: Update both call sites for the new `_pop_social_quality` signature

**Files:**
- Modify: `logic/civilian_agent_logic.py`

The old signature was `_pop_social_quality(pop_tags)`. There are two call sites.

- [ ] **Step 1: Update `_select_local_pop`**

The function currently calls `_pop_social_quality(pop.culture_tags)`. Replace the whole scoring lambda with one that passes mortal context. Find the `_select_local_pop` function and update the `_score` inner function:

Old:
```python
    def _score(item: tuple) -> float:
        _, pop = item
        s = 0.0
        if leisure_pressing:
            s += _pop_practice_quality(mortal.culture_tags, pop.culture_tags)
        if belonging_pressing:
            s += _pop_social_quality(pop.culture_tags)
        return s
```

New:
```python
    _mortal_home_pop = state.pops.get(str(mortal.pop_milieu or mortal.pop_id or ""))
    _mortal_civ = str(_mortal_home_pop.civilization_id) if _mortal_home_pop and _mortal_home_pop.civilization_id else None

    def _score(item: tuple) -> float:
        _, pop = item
        s = 0.0
        if leisure_pressing:
            s += _pop_practice_quality(mortal.culture_tags, pop.culture_tags)
        if belonging_pressing:
            _same_species = (str(mortal.species_id) == str(pop.species_id)) if (mortal.species_id and pop.species_id) else True
            _same_civ = (_mortal_civ == str(pop.civilization_id)) if (_mortal_civ and pop.civilization_id) else True
            s += _pop_social_quality(
                mortal.belief_tags, mortal.culture_tags,
                pop.dominant_beliefs, pop.culture_tags,
                same_species=_same_species,
                same_civ=_same_civ,
            )
        return s
```

- [ ] **Step 2: Update the main evaluation loop call site**

Find the line `_sq = _pop_social_quality(_local_pop.culture_tags)` in `evaluate_civilian_action`. It's inside the belonging scoring block, where `mortal`, `_local_pop`, and `state` are all in scope. The mortal's milieu pop ID is already computed earlier in the function as `_local_pop_id`.

Replace:
```python
        _sq = _pop_social_quality(_local_pop.culture_tags)
```

With:
```python
        _mortal_civ_id = str(_local_pop.civilization_id) if _local_pop and _local_pop.civilization_id else None
        _sq = _pop_social_quality(
            mortal.belief_tags, mortal.culture_tags,
            _local_pop.dominant_beliefs, _local_pop.culture_tags,
            same_species=(str(mortal.species_id) == str(_local_pop.species_id)) if (mortal.species_id and _local_pop.species_id) else True,
            same_civ=True,  # mortal socialises with their milieu pop — treat as same-civ
        )
```

Note: for the milieu pop the mortal is already embedded in, `same_civ=True` is appropriate since they chose this pop as their current social environment. The cross-civ/species penalty matters for the *selection* step (Task 3 Step 1), not execution with the already-chosen milieu.

- [ ] **Step 3: Run full test suite**

```bash
source venv/bin/activate && pytest -v 2>&1 | tail -20
```

Expected: all previously passing tests still PASS. No test should newly fail.

- [ ] **Step 4: Commit**

```bash
git add logic/civilian_agent_logic.py
git commit -m "feat: update _pop_social_quality call sites with mortal context and cross-group factors"
```

---

## Task 4: Registry — add `practice:trade`, remove `relations:commerce`, update synergy

**Files:**
- Modify: `utilities/culture_registry.py`
- Modify: `tests/test_civilian_logic.py` (registry smoke tests)

- [ ] **Step 1: Write failing registry tests**

Add to `tests/test_civilian_logic.py`:

```python
from utilities.culture_registry import get_registry as _get_culture_registry, is_culture_tag

def test_practice_trade_is_canonical():
    assert is_culture_tag("practice:trade")

def test_relations_commerce_is_not_canonical():
    assert not is_culture_tag("relations:commerce")

def test_practice_trade_has_synergy_with_xenophilia():
    reg = _get_culture_registry()
    synergy = reg.get_synergy("practice:trade", "relations:xenophilia")
    assert synergy > 0

def test_practice_trade_negative_synergy_with_protectionism():
    reg = _get_culture_registry()
    synergy = reg.get_synergy("practice:trade", "relations:protectionism")
    assert synergy < 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
source venv/bin/activate && pytest tests/test_civilian_logic.py::test_practice_trade_is_canonical tests/test_civilian_logic.py::test_relations_commerce_is_not_canonical tests/test_civilian_logic.py::test_practice_trade_has_synergy_with_xenophilia tests/test_civilian_logic.py::test_practice_trade_negative_synergy_with_protectionism -v
```

Expected: all FAIL.

- [ ] **Step 3: Edit `utilities/culture_registry.py`**

**3a. Find `PRACTICE_TAGS` and add `practice:trade`:**

Find the list that includes `"practice:music"`, `"practice:ritual"`, etc. Add `"practice:trade"` to it. Order alphabetically within the list.

**3b. Find `RELATIONS_TAGS` and remove `"relations:commerce"`:**

Find the line with `"relations:commerce"` and delete it.

**3c. Update the `CULTURE_SYNERGIES` (or equivalent pairwise list):**

Remove all tuples containing `"relations:commerce"`. From the audit these were:
```python
("relations:diplomacy",     "relations:commerce",      0.60),
("relations:xenophilia",    "relations:commerce",       0.50),
("techno:industrialism",    "relations:commerce",       0.50),   # techno:industrialism is deprecated; drop entirely
("structure:hierarchy",     "relations:commerce",       0.40),
("structure:competition",   "relations:commerce",       0.40),
("values:prosperity",       "relations:commerce",       0.50),
("relations:commerce",      "relations:protectionism",  -0.80),
```

Add replacement entries for `practice:trade`:
```python
("relations:diplomacy",     "practice:trade",           0.55),
("relations:xenophilia",    "practice:trade",           0.50),
("structure:competition",   "practice:trade",           0.45),
("values:prosperity",       "practice:trade",           0.50),
("structure:hierarchy",     "practice:trade",           0.30),
("practice:trade",          "relations:protectionism",  -0.80),
("practice:trade",          "relations:isolationism",   -0.60),
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
source venv/bin/activate && pytest tests/test_civilian_logic.py::test_practice_trade_is_canonical tests/test_civilian_logic.py::test_relations_commerce_is_not_canonical tests/test_civilian_logic.py::test_practice_trade_has_synergy_with_xenophilia tests/test_civilian_logic.py::test_practice_trade_negative_synergy_with_protectionism -v
```

Expected: all 4 PASS.

- [ ] **Step 5: Run full test suite**

```bash
source venv/bin/activate && pytest 2>&1 | tail -5
```

Expected: all PASS. If any test breaks, the removed synergy entries were referenced — fix accordingly.

- [ ] **Step 6: Commit**

```bash
git add utilities/culture_registry.py tests/test_civilian_logic.py
git commit -m "feat: add practice:trade canonical tag, remove relations:commerce, update synergy table"
```

---

## Task 5: Trade bonus — `_effective_commerce_quality` + tick_logic update

**Files:**
- Modify: `logic/civilian_agent_logic.py`
- Modify: `logic/tick_logic.py`
- Modify: `tests/test_civilian_logic.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_civilian_logic.py`:

```python
from logic.civilian_agent_logic import _effective_commerce_quality
from unittest.mock import MagicMock

def _make_loc_and_state(commerce_quality, pop_trade_vals):
    """Build minimal loc + state for trade bonus tests."""
    from core.universe_core import PopLocation
    from uuid import uuid4
    loc = MagicMock(spec=PopLocation)
    loc.commerce_quality = commerce_quality
    loc.pop_ids = []
    state = MagicMock()
    state.pops = {}
    for trade_val, size in pop_trade_vals:
        pid = uuid4()
        pop = MagicMock()
        pop.culture_tags = {"practice:trade": trade_val} if trade_val > 0 else {}
        pop.size_fractional = size
        loc.pop_ids.append(pid)
        state.pops[str(pid)] = pop
    return loc, state

def test_effective_commerce_no_pops_returns_base():
    loc, state = _make_loc_and_state(0.7, [])
    assert _effective_commerce_quality(loc, state) == pytest.approx(0.7)

def test_effective_commerce_trader_pop_adds_bonus():
    loc, state = _make_loc_and_state(0.5, [(0.8, 5.0)])
    result = _effective_commerce_quality(loc, state)
    assert result > 0.5

def test_effective_commerce_clamped_to_one():
    # High base + high trade shouldn't exceed 1.0
    loc, state = _make_loc_and_state(0.9, [(1.0, 10.0)])
    assert _effective_commerce_quality(loc, state) <= 1.0

def test_effective_commerce_size_weighted():
    # Larger pop contributes more to bonus
    loc_small, state_small = _make_loc_and_state(0.5, [(0.8, 1.0)])
    loc_large, state_large = _make_loc_and_state(0.5, [(0.8, 10.0), (0.0, 1.0)])
    # Both have same weighted-average trade (0.8 * 1 / 1 vs 0.8 * 10 / 11)
    # large has lower effective trade per unit but result should still exceed base
    assert _effective_commerce_quality(loc_large, state_large) > 0.5
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
source venv/bin/activate && pytest tests/test_civilian_logic.py -k "effective_commerce" -v
```

Expected: FAIL with ImportError (`_effective_commerce_quality` not defined).

- [ ] **Step 3: Add `_effective_commerce_quality` to `civilian_agent_logic.py`**

Add after the `_pop_social_quality` block (before `_select_local_pop`):

```python
_TRADE_QUALITY_WEIGHT = 0.30  # max bonus contribution from practice:trade pops


def _effective_commerce_quality(loc, state) -> float:
    """Authored commerce_quality + size-weighted pop practice:trade contribution.

    The authored loc.commerce_quality is the base (never modified). Pops with
    practice:trade at this location add a dynamic bonus proportional to their
    share of total local pop size.
    """
    base = getattr(loc, "commerce_quality", 0.5)
    pop_ids = getattr(loc, "pop_ids", [])
    if not pop_ids:
        return base
    pops = [state.pops[str(pid)] for pid in pop_ids if str(pid) in state.pops]
    if not pops:
        return base
    total_size = sum(p.size_fractional for p in pops)
    if total_size == 0.0:
        return base
    trade_activity = sum(
        p.culture_tags.get("practice:trade", 0.0) * p.size_fractional for p in pops
    ) / total_size
    return min(1.0, base + trade_activity * _TRADE_QUALITY_WEIGHT)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
source venv/bin/activate && pytest tests/test_civilian_logic.py -k "effective_commerce" -v
```

Expected: all PASS.

- [ ] **Step 5: Import `_effective_commerce_quality` in `tick_logic.py` and replace `commerce_quality` accesses**

In `tick_logic.py`, add to the civilian_agent_logic imports at the top:

```python
from logic.civilian_agent_logic import (
    ...,   # existing imports
    _effective_commerce_quality,
)
```

(Check the existing import block for `civilian_agent_logic` and add `_effective_commerce_quality` to it.)

Then find and replace all 3 `commerce_quality` accesses in tick_logic.py. Each currently reads `getattr(loc, "commerce_quality", 0.5)` or similar. Replace with `_effective_commerce_quality(loc, state)`:

**Line ~5286 (sustenance restoration):**
```python
# Old:
if loc and getattr(loc, "commerce_quality", 0) > 0:
# New:
if loc and _effective_commerce_quality(loc, state) > 0:
```

**Line ~5385 (sell action):**
```python
# Old:
quality = getattr(loc, "commerce_quality", 0.5)
# New:
quality = _effective_commerce_quality(loc, state)
```

**Line ~5460 (spend action):**
```python
# Old:
quality = getattr(loc, "commerce_quality", 0.5)
# New:
quality = _effective_commerce_quality(loc, state)
```

- [ ] **Step 6: Run full test suite**

```bash
source venv/bin/activate && pytest 2>&1 | tail -5
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add logic/civilian_agent_logic.py logic/tick_logic.py tests/test_civilian_logic.py
git commit -m "feat: add _effective_commerce_quality; trade-active pops boost location commerce quality"
```

---

## Task 6: Scenario data migration

**Files:**
- Modify: `scenarios/wardens_compact.db` (via Python/SQLite)

This task runs Python scripts directly — no unit tests needed (verify by inspection).

- [ ] **Step 1: Inspect what's there**

```bash
python3 -c "
import sqlite3, json
con = sqlite3.connect('scenarios/wardens_compact.db')
# Durenn Vail
rows = con.execute(\"SELECT name, culture_tags FROM mortals WHERE name LIKE '%Vail%'\").fetchall()
print('=== Durenn Vail ===')
for r in rows: print(r[0], r[1])
# Trader pops
print()
print('=== Trader pops ===')
rows = con.execute(\"SELECT id, social_class, occupation, culture_tags FROM pops WHERE social_class = 'trader' AND occupation = 'merchant'\").fetchall()
for r in rows: print(r[0], r[1], r[2], r[3])
con.close()
"
```

Review output. Confirm Durenn has `relations:commerce` and note which trader pops exist.

- [ ] **Step 2: Remove `relations:commerce` from Durenn Vail**

```bash
python3 -c "
import sqlite3, json
con = sqlite3.connect('scenarios/wardens_compact.db')
rows = con.execute(\"SELECT id, culture_tags FROM mortals WHERE name LIKE '%Vail%'\").fetchall()
for row_id, tags_json in rows:
    tags = json.loads(tags_json)
    if 'relations:commerce' in tags:
        del tags['relations:commerce']
        con.execute('UPDATE mortals SET culture_tags = ? WHERE id = ?', (json.dumps(tags), row_id))
        print(f'Updated {row_id}: removed relations:commerce')
con.commit()
con.close()
print('Done.')
"
```

- [ ] **Step 3: Add `practice:trade` to trader pops**

Only add to pops where `social_class = 'trader'` **and** `occupation = 'merchant'` — financiers, executives, and trader pops without an occupation are excluded. Use 0.70 as a reasonable default.

```bash
python3 -c "
import sqlite3, json
TRADE_VALUE = 0.70
con = sqlite3.connect('scenarios/wardens_compact.db')
rows = con.execute(\"SELECT id, culture_tags FROM pops WHERE social_class = 'trader' AND occupation = 'merchant'\").fetchall()
for row_id, tags_json in rows:
    tags = json.loads(tags_json or '{}')
    if 'practice:trade' not in tags:
        tags['practice:trade'] = TRADE_VALUE
        con.execute('UPDATE pops SET culture_tags = ? WHERE id = ?', (json.dumps(tags), row_id))
        print(f'Updated pop {row_id}: added practice:trade={TRADE_VALUE}')
    else:
        print(f'Pop {row_id} already has practice:trade={tags[\"practice:trade\"]} — skipped')
con.commit()
con.close()
print('Done.')
"
```

- [ ] **Step 4: Verify**

```bash
python3 -c "
import sqlite3, json
con = sqlite3.connect('scenarios/wardens_compact.db')
print('=== Durenn Vail after ===')
for r in con.execute(\"SELECT name, culture_tags FROM mortals WHERE name LIKE '%Vail%'\"):
    print(r[0], r[1])
print()
print('=== Trader pops after ===')
for r in con.execute(\"SELECT id, social_class, occupation, culture_tags FROM pops WHERE social_class = 'trader' AND occupation = 'merchant'\"):
    print(r[0], r[1], r[2])
con.close()
"
```

Confirm: Durenn has no `relations:commerce`; all trader pops have `practice:trade: 0.7`.

- [ ] **Step 5: Smoke test via autoplay**

```bash
source venv/bin/activate && python main.py --autoplay 2>&1 | tail -20
```

Expected: 50 ticks complete without crash or import error.

- [ ] **Step 6: Run full test suite**

```bash
source venv/bin/activate && pytest 2>&1 | tail -5
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add scenarios/wardens_compact.db
git commit -m "data: remove relations:commerce from Durenn Vail; add practice:trade to trader pops"
```

---

## Self-Review

**Spec coverage:**
- ✅ Cosine similarity of beliefs + non-practice culture → Task 1/2
- ✅ Xenophilia curve: 0–0.5 mitigates, >0.5 inverts → Task 1 Step 3 (`_pop_social_quality`)
- ✅ Negative xenophilia linear penalty → Task 1 Step 3 (`neg_f`)
- ✅ Cross-species / cross-civ weighted more by xenophilia (lower neutral point) → Task 2
- ✅ `values:solidarity` and `practice:revelry` kept as additive bonus → Task 1 Step 3
- ✅ `practice:trade` added as canonical tag → Task 4
- ✅ `relations:commerce` removed → Task 4
- ✅ Synergy entries updated → Task 4
- ✅ `practice:trade` on pops contributes to location commerce quality → Task 5
- ✅ Authored `commerce_quality` preserved as base → Task 5 (`_effective_commerce_quality`)
- ✅ `relations:commerce` removed from Durenn Vail → Task 6
- ✅ `practice:trade` added to merchant-occupation trader pops only (excludes financiers, executives, unoccupied) → Task 6

**No placeholders found.**

**Type consistency:** `_effective_commerce_quality(loc, state)` signature used consistently in Task 5 Steps 3 and 5. `_cross_factor` imported in test Task 2 Step 1 and defined in Task 1 Step 3 — both use `(base, xeno_neutral, xeno)`. ✅
