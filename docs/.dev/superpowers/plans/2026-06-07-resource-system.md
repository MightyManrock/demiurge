# Resource System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign `CollectibleResource` from a single optional into a depleting, renewing list; split the monolithic `sustenance` need into `nourishment` and `hydration`; add passive sustenance fulfillment for both Pops and mortals; add mortal-autonomous `forage` and `hunt` actions.

**Architecture:** `CollectibleResource` gains `max_yield`/`yield_renew_rate`/`current_yield` fields and an `action_types` discriminator; `PopLocation.collectible_resource` becomes `collectible_resources: list[CollectibleResource]`. A new tick phase renews yields before agents act. `sustenance` is replaced by `nourishment` (filled by `basis:*`-tagged resources) and `hydration` (filled by `solvent:*`-tagged resources, decaying ~1.5× faster). Mortals passively consume from their KB inventory to fill these needs rather than using an explicit eat/drink action; a new `forage` / `hunt` priority in `evaluate_mortal_action` lets mortals acquire food autonomously when nourishment is pressing.

**Tech Stack:** Python 3.11, Pydantic v2, SQLite; `pytest` test suite.

**Out of scope:** `ResourceStockpile` shared-ownership system (separate plan); Pop "leak" migration; tech-bonus modifiers on yield; mortal hydration action (collect with `solvent:*` resource covers it).

---

## Files created or modified

| File | Change |
|---|---|
| `core/agent_core.py` | Extend `CollectibleResource`: rename `resource_yield`→`max_yield`, add `yield_renew_rate`, `current_yield`, `action_types`; add `model_validator` |
| `core/universe_core.py` | Replace `PopLocation.collectible_resource: Optional` with `collectible_resources: list` |
| `core/scenario_schema.sql` | Rename column `collectible_resource` → `collectible_resources TEXT NOT NULL DEFAULT '[]'` |
| `utilities/scenario_loader.py` | Replace `_load_collectible_resource` with `_load_collectible_resources`; backward-compat for old single-object column; state need migration (`sustenance`→`nourishment`+`hydration`) |
| `utilities/scenario_exporter.py` | Serialize `collectible_resources` list |
| `logic/needs_config.py` | Add `NEED_NOURISHMENT`, `NEED_HYDRATION`; remove `NEED_SUSTENANCE`; add pop equivalents; update mortal and pop defaults |
| `logic/pop_agent_logic.py` | Update `ACTION_NEED_MAP`; gate forage/hunt/collect on `action_types` and `current_yield`; split consumption pass into nourishment + hydration |
| `logic/tick_logic.py` | Add Phase 2.54 yield renewal; update mortal collect to use `collectible_resources` list; replace passive `sustenance` restore with `nourishment`+`hydration` inventory draws; add `forage`/`hunt` resolution for mortals |
| `logic/mortal_agent_logic.py` | Add `"forage"` and `"hunt"` as possible return values from `evaluate_mortal_action` |
| `tests/test_resource_system.py` | New test file covering all tasks |
| `tests/test_pop_agent.py` | Update tests that reference `"sustenance"` need name |
| `docs/.dev/Mechanics/needs-and-directives.md` | Update `CollectibleResource` section; update sustenance→nourishment+hydration |
| `docs/.dev/Mechanics/agent-system.md` | Update Pop needs table |

---

## Task 1: CollectibleResource model + PopLocation list field

**Files:**
- Modify: `core/agent_core.py`
- Modify: `core/universe_core.py`
- Test: `tests/test_resource_system.py`

**Context:** `CollectibleResource` lives in `core/agent_core.py` around line 198. `PopLocation` lives in `core/universe_core.py` around line 337. Pydantic v2 — use `model_validator(mode="after")`. The `Optional` import is already present in `agent_core.py`.

- [ ] **Step 1: Write failing tests**

Create `tests/test_resource_system.py`:

```python
import pytest
from uuid import uuid4
from core.agent_core import CollectibleResource
from core.universe_core import PopLocation


# ── CollectibleResource ───────────────────────────────────────────────────────

def test_cr_max_yield_field():
    cr = CollectibleResource(resource_type="food_flora", max_yield=5.0)
    assert cr.max_yield == 5.0

def test_cr_current_yield_defaults_to_max_yield():
    cr = CollectibleResource(resource_type="food_flora", max_yield=3.0)
    assert cr.current_yield == 3.0

def test_cr_current_yield_can_be_set_explicitly():
    cr = CollectibleResource(resource_type="food_flora", max_yield=10.0, current_yield=4.0)
    assert cr.current_yield == 4.0

def test_cr_yield_renew_rate_field():
    cr = CollectibleResource(resource_type="food_flora", max_yield=10.0, yield_renew_rate=0.1)
    assert cr.yield_renew_rate == 0.1

def test_cr_yield_renew_rate_default():
    cr = CollectibleResource(resource_type="food_flora", max_yield=10.0)
    assert cr.yield_renew_rate == 0.2

def test_cr_action_types_empty_by_default():
    cr = CollectibleResource(resource_type="food_flora", max_yield=5.0)
    assert cr.action_types == []

def test_cr_action_types_can_be_set():
    cr = CollectibleResource(resource_type="food_flora", max_yield=5.0,
                              action_types=["forage", "collect"])
    assert "forage" in cr.action_types
    assert "collect" in cr.action_types

def test_cr_no_resource_yield_field():
    with pytest.raises(Exception):
        # resource_yield is gone; this should raise a validation error
        CollectibleResource(resource_type="food_flora", resource_yield=5.0)


# ── PopLocation.collectible_resources ─────────────────────────────────────────

def _make_pop_loc(**kwargs):
    defaults = {"id": uuid4(), "name": "Plains", "parent_id": uuid4()}
    defaults.update(kwargs)
    return PopLocation(**defaults)

def test_pop_location_has_collectible_resources_list():
    loc = _make_pop_loc()
    assert loc.collectible_resources == []

def test_pop_location_accepts_multiple_collectible_resources():
    cr1 = CollectibleResource(resource_type="food_flora", max_yield=5.0,
                               action_types=["forage"])
    cr2 = CollectibleResource(resource_type="potable_water", max_yield=8.0,
                               action_types=["collect"],
                               biochem_tags=["solvent:water"])
    loc = _make_pop_loc(collectible_resources=[cr1, cr2])
    assert len(loc.collectible_resources) == 2
    assert loc.collectible_resources[0].resource_type == "food_flora"
    assert loc.collectible_resources[1].resource_type == "potable_water"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
source venv/bin/activate && pytest tests/test_resource_system.py -v
```

Expected: failures referencing missing `max_yield`, `current_yield`, `action_types`, or `collectible_resources`.

- [ ] **Step 3: Update CollectibleResource in `core/agent_core.py`**

Add `model_validator` to the imports at the top of the file:
```python
from pydantic import BaseModel, Field, model_validator
```

Replace the `CollectibleResource` class (around line 198):
```python
class CollectibleResource(BaseModel):
    resource_type: str = "unobtanium"
    max_yield: float = 1.0
    yield_renew_rate: float = 0.2      # fraction of max_yield restored per tick
    current_yield: Optional[float] = None
    cooldown_ticks: int = 3
    action_types: list[str] = Field(default_factory=list)  # [] = any action can use
    biochem_tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _init_current_yield(self) -> "CollectibleResource":
        if self.current_yield is None:
            self.current_yield = self.max_yield
        return self
```

- [ ] **Step 4: Update `PopLocation` in `core/universe_core.py`**

Find the line with `collectible_resource: Optional[CollectibleResource] = None` (around line 337) and replace it:
```python
collectible_resources: list["CollectibleResource"] = Field(default_factory=list)
```

`CollectibleResource` is already imported from `core.agent_core` at the top of this file.

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_resource_system.py -v
```

Expected: all new tests pass. Also run:
```bash
pytest -v
```
Expected: full suite passes (forward-ref errors or field-not-found errors would indicate the field rename broke something — fix before committing).

- [ ] **Step 6: Commit**

```bash
git add core/agent_core.py core/universe_core.py tests/test_resource_system.py
git commit -m "feat(resources): CollectibleResource depletion model + PopLocation list field"
```

---

## Task 2: DB schema, persistence, and migration

**Files:**
- Modify: `core/scenario_schema.sql`
- Modify: `utilities/scenario_loader.py`
- Modify: `utilities/scenario_exporter.py`
- Modify: `logic/tick_logic.py` (mortal collect action — update `collectible_resource` → `collectible_resources` references)

**Context:** The loader uses `_load_collectible_resource(raw: Optional[str]) -> Optional[CollectibleResource]` (around line 948). The exporter writes `collectible_resource_val` (around line 308). The `collectible_resource TEXT DEFAULT NULL` column is in the `pop_locations` table. The mortal `collect` action branch is around line 5623 in `tick_logic.py` and references `loc.collectible_resource`. Background loading at line 5556 also uses `collectible_resource`. The old format JSON was a single object `{"resource_yield": ..., "cooldown_ticks": ...}`.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_resource_system.py`:

```python
import json
from utilities.scenario_loader import _load_collectible_resources


# ── Persistence ───────────────────────────────────────────────────────────────

def test_load_collectible_resources_empty_list():
    assert _load_collectible_resources("[]", None) == []

def test_load_collectible_resources_from_none():
    assert _load_collectible_resources(None, None) == []

def test_load_collectible_resources_from_new_format():
    raw = json.dumps([{
        "resource_type": "food_flora", "max_yield": 5.0, "yield_renew_rate": 0.2,
        "action_types": ["forage"], "biochem_tags": ["basis:carbon"]
    }])
    result = _load_collectible_resources(raw, None)
    assert len(result) == 1
    assert result[0].resource_type == "food_flora"
    assert result[0].max_yield == 5.0
    assert result[0].current_yield == 5.0   # initialized from max_yield

def test_load_collectible_resources_preserves_depleted_current_yield():
    raw = json.dumps([{
        "resource_type": "food_flora", "max_yield": 10.0, "current_yield": 3.0,
        "yield_renew_rate": 0.1, "action_types": []
    }])
    result = _load_collectible_resources(raw, None)
    assert result[0].current_yield == 3.0  # not reset to max

def test_load_collectible_resources_old_format_fallback():
    # Old single-object with resource_yield (not max_yield)
    old_raw = json.dumps({"resource_yield": 3.0, "cooldown_ticks": 3,
                           "resource_type": "food_flora"})
    result = _load_collectible_resources(None, old_raw)
    assert len(result) == 1
    assert result[0].max_yield == 3.0
    assert result[0].current_yield == 3.0

def test_load_collectible_resources_old_format_already_max_yield():
    # Old format that somehow already has max_yield
    old_raw = json.dumps({"max_yield": 4.0, "cooldown_ticks": 3,
                           "resource_type": "potable_water"})
    result = _load_collectible_resources(None, old_raw)
    assert result[0].max_yield == 4.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_resource_system.py::test_load_collectible_resources_empty_list -v
```

Expected: ImportError or AttributeError — function doesn't exist yet.

- [ ] **Step 3: Update `core/scenario_schema.sql`**

Find the `pop_locations` table definition and replace:
```sql
collectible_resource  TEXT    DEFAULT NULL,
```
with:
```sql
collectible_resources TEXT NOT NULL DEFAULT '[]',
```

- [ ] **Step 4: Update `utilities/scenario_loader.py`**

Add the import at the top of the file (alongside existing CollectibleResource import):
```python
from core.agent_core import CollectibleResource  # already imported; keep as-is
```

Replace the `_load_collectible_resource` function (around line 948) with:

```python
def _load_collectible_resources(
    raw: Optional[str],
    old_raw: Optional[str],
) -> list[CollectibleResource]:
    """Load list-format collectible_resources; falls back to old single-object format."""
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [CollectibleResource.model_validate(item) for item in data]
        except Exception:
            pass
    if old_raw:
        try:
            data = json.loads(old_raw)
            if isinstance(data, dict):
                if "resource_yield" in data and "max_yield" not in data:
                    data["max_yield"] = data.pop("resource_yield")
                return [CollectibleResource.model_validate(data)]
        except Exception:
            pass
    return []
```

In the `_load_locations` function (around line 586), replace:
```python
collectible_resource=_load_collectible_resource(row.get("collectible_resource")),
```
with:
```python
collectible_resources=_load_collectible_resources(
    row.get("collectible_resources"),
    row.get("collectible_resource"),
),
```

- [ ] **Step 5: Update `utilities/scenario_exporter.py`**

In `_write_locations` (around line 308), replace the `collectible_resource_val` block:

Find and replace the two relevant lines. Change the initialization from:
```python
collectible_resource_val = None
```
to:
```python
collectible_resources_val = "[]"
```

And the PopLocation branch that sets it from:
```python
collectible_resource_val = loc.collectible_resource.model_dump_json() if loc.collectible_resource else None
```
to:
```python
collectible_resources_val = json.dumps(
    [cr.model_dump(mode="json") for cr in loc.collectible_resources]
)
```

Update the INSERT column list and VALUES accordingly (rename `collectible_resource` → `collectible_resources` in both the column name and the value variable).

- [ ] **Step 6: Update mortal collect in `logic/tick_logic.py`**

Find the mortal `collect` action branch (around line 5623). Replace `collectible_resource` references:

```python
if action == "collect":
    loc = state.locations.get(str(mortal.current_location))
    crs = getattr(loc, "collectible_resources", []) if loc else []
    for cr in crs:
        if cr.action_types and "collect" not in cr.action_types:
            continue
        if cr.current_yield <= 0:
            continue
        res = cs.get_resource(cr.resource_type)
        if res is None:
            from core.agent_core import Resource as _Resource
            res = _Resource(resource_type=cr.resource_type,
                            biochem_tags=list(cr.biochem_tags))
            cs.inventory.append(res)
        gained = min(cr.max_yield * 0.15, cr.current_yield)  # mortal yield: 15% of max
        cr.current_yield = max(0.0, cr.current_yield - gained)
        res.quantity += gained
        mortal.fatigue = min(1.0, mortal.fatigue + 0.15)
        if mortal.pinned:
            narratives.append(
                f"{mortal.name} collects {gained:.2f} {cr.resource_type} "
                f"(total: {res.quantity:.1f})."
            )
        break  # collect one resource per tick
```

Also find the background loading branch (around line 5556) and replace:
```python
_bg_cr = getattr(_bg_loc, "collectible_resource", None)
```
with:
```python
_bg_crs = getattr(_bg_loc, "collectible_resources", [])
_bg_cr = next(
    (c for c in _bg_crs
     if (not c.action_types or "collect" in c.action_types) and c.current_yield > 0),
    None,
)
```

Then wherever the old `_bg_cr.resource_yield` is referenced, replace it with `_bg_cr.max_yield * 0.15` (matching the mortal yield rate above). Read the background loading block carefully before editing — don't change logic beyond the field names.

- [ ] **Step 7: Run migrator on all scenario DBs**

```bash
python main.py --rebuild --scenario
```

This runs `utilities/scenario_migrator.py` over every `scenarios/*.db`, doing a load→re-export round trip that will migrate the `collectible_resource` column data into `collectible_resources`.

- [ ] **Step 8: Run full test suite**

```bash
pytest -v
```

Expected: all tests pass. If any test references `pop_loc.collectible_resource` (the old field), update it to `pop_loc.collectible_resources`.

- [ ] **Step 9: Commit**

```bash
git add core/scenario_schema.sql utilities/scenario_loader.py utilities/scenario_exporter.py logic/tick_logic.py tests/test_resource_system.py
git commit -m "feat(resources): persist collectible_resources list; migrate old single-resource format"
```

---

## Task 3: Sustenance need split — constants and state migration

**Files:**
- Modify: `logic/needs_config.py`
- Modify: `utilities/scenario_loader.py` (state migration helpers)

**Context:** `logic/needs_config.py` defines `NEED_SUSTENANCE = "sustenance"` (line 14), `CANONICAL_MORTAL_NEED_NAMES` (line 22), `MORTAL_NEED_DEFAULTS` (line 43), and the parallel pop constants starting around line 231. `tick_logic.py` imports `NEED_SUSTENANCE` from this file (line 63 area). The loader's `_load_mortal_agent_state` and `_load_pop_agent_state` functions need migration logic to convert existing "sustenance" needs to "nourishment" + "hydration".

- [ ] **Step 1: Write failing tests**

Add to `tests/test_resource_system.py`:

```python
from logic.needs_config import (
    NEED_NOURISHMENT, NEED_HYDRATION,
    CANONICAL_MORTAL_NEED_NAMES, MORTAL_NEED_DEFAULTS,
    POP_NEED_NOURISHMENT, POP_NEED_HYDRATION,
    POP_NEED_DEFAULTS, compute_pop_need_profile, initialize_pop_state,
    compute_need_profile,
)
from unittest.mock import MagicMock


def test_need_nourishment_constant():
    assert NEED_NOURISHMENT == "nourishment"

def test_need_hydration_constant():
    assert NEED_HYDRATION == "hydration"

def test_sustenance_not_in_canonical_mortal_needs():
    assert "sustenance" not in CANONICAL_MORTAL_NEED_NAMES

def test_nourishment_in_canonical_mortal_needs():
    assert "nourishment" in CANONICAL_MORTAL_NEED_NAMES

def test_hydration_in_canonical_mortal_needs():
    assert "hydration" in CANONICAL_MORTAL_NEED_NAMES

def test_hydration_decays_faster_than_nourishment():
    nour_decay = MORTAL_NEED_DEFAULTS["nourishment"]["decay_rate"]
    hydr_decay = MORTAL_NEED_DEFAULTS["hydration"]["decay_rate"]
    assert hydr_decay > nour_decay

def test_compute_need_profile_has_nourishment_and_hydration():
    needs = compute_need_profile({})
    names = [n.name for n in needs]
    assert "nourishment" in names
    assert "hydration" in names
    assert "sustenance" not in names

def test_pop_nourishment_and_hydration_constants():
    assert POP_NEED_NOURISHMENT == "nourishment"
    assert POP_NEED_HYDRATION == "hydration"

def test_pop_hydration_decays_faster():
    nour_decay = POP_NEED_DEFAULTS["nourishment"]["decay_rate"]
    hydr_decay = POP_NEED_DEFAULTS["hydration"]["decay_rate"]
    assert hydr_decay > nour_decay

def test_initialize_pop_state_has_nourishment_and_hydration():
    pop = MagicMock()
    pop.culture_tags = {}
    state = initialize_pop_state(pop)
    names = [n.name for n in state.needs]
    assert "nourishment" in names
    assert "hydration" in names
    assert "sustenance" not in names
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_resource_system.py -k "nourishment or hydration or sustenance" -v
```

Expected: ImportError or AssertionError — these constants don't exist yet.

- [ ] **Step 3: Update `logic/needs_config.py` — mortal constants**

Replace `NEED_SUSTENANCE = "sustenance"` with:
```python
NEED_NOURISHMENT = "nourishment"
NEED_HYDRATION   = "hydration"
```

In `CANONICAL_MORTAL_NEED_NAMES`, replace `NEED_SUSTENANCE` with `NEED_NOURISHMENT, NEED_HYDRATION`:
```python
CANONICAL_MORTAL_NEED_NAMES = [
    NEED_NOURISHMENT,
    NEED_HYDRATION,
    NEED_SAFETY,
    NEED_BELONGING,
    NEED_STATUS,
    NEED_PURPOSE,
    NEED_LEISURE,
]
```

In `MORTAL_NEED_DEFAULTS`, replace the `NEED_SUSTENANCE` entry with two entries:
```python
NEED_NOURISHMENT: {"decay_rate": 0.02,  "pressing_threshold": 0.55, "urgent_threshold": 0.20},
NEED_HYDRATION:   {"decay_rate": 0.03,  "pressing_threshold": 0.55, "urgent_threshold": 0.20},
```

If `MORTAL_NEED_TRAIT_MODIFIERS` has any `NEED_SUSTENANCE` entries, split them into separate `NEED_NOURISHMENT` and `NEED_HYDRATION` entries with the same values.

- [ ] **Step 4: Update `logic/needs_config.py` — pop constants**

Replace `POP_NEED_SUSTENANCE = "sustenance"` with:
```python
POP_NEED_NOURISHMENT = "nourishment"
POP_NEED_HYDRATION   = "hydration"
```

In `CANONICAL_POP_NEED_NAMES`, replace `POP_NEED_SUSTENANCE` with both:
```python
CANONICAL_POP_NEED_NAMES = [
    POP_NEED_NOURISHMENT,
    POP_NEED_HYDRATION,
    POP_NEED_SAFETY,
    POP_NEED_COHESION,
    POP_NEED_PURPOSE,
    POP_NEED_SHELTER,
    POP_NEED_WANDERLUST,
]
```

In `POP_NEED_DEFAULTS`, replace `POP_NEED_SUSTENANCE` entry with:
```python
POP_NEED_NOURISHMENT: {"decay_rate": 0.02,  "pressing_threshold": 0.55, "urgent_threshold": 0.20},
POP_NEED_HYDRATION:   {"decay_rate": 0.03,  "pressing_threshold": 0.55, "urgent_threshold": 0.20},
```

- [ ] **Step 5: Update `tick_logic.py` import**

Find `NEED_SUSTENANCE` in the imports from `needs_config` (around line 63) and replace:
```python
NEED_NOURISHMENT, NEED_HYDRATION,
```

Find every usage of `NEED_SUSTENANCE` in `tick_logic.py` (the passive restore at line 5488) and update — this will be replaced entirely in Task 6, so just comment it out for now or update the variable name to `NEED_NOURISHMENT`.

- [ ] **Step 6: Add state migration in `utilities/scenario_loader.py`**

Add a migration helper after `_load_pop_agent_state`:

```python
def _migrate_needs_sustenance_split(needs: list) -> list:
    """Convert old 'sustenance' need into 'nourishment' + 'hydration'."""
    names = {n.name for n in needs}
    if "sustenance" not in names:
        return needs
    result = []
    for n in needs:
        if n.name == "sustenance":
            n.name = "nourishment"
        result.append(n)
    if "hydration" not in names:
        from core.agent_core import MortalNeed
        result.append(MortalNeed(
            name="hydration",
            satisfaction=1.0,
            decay_rate=0.03,
            pressing_threshold=0.55,
            urgent_threshold=0.20,
        ))
    return result
```

In `_load_mortal_agent_state`, after the state is deserialized, add:
```python
state.needs = _migrate_needs_sustenance_split(state.needs)
```

In `_load_pop_agent_state`, after deserialization, add the equivalent call using `PopNeed`:

```python
def _migrate_pop_needs_sustenance_split(needs: list) -> list:
    """Convert old 'sustenance' Pop need into 'nourishment' + 'hydration'."""
    names = {n.name for n in needs}
    if "sustenance" not in names:
        return needs
    result = []
    for n in needs:
        if n.name == "sustenance":
            n.name = "nourishment"
        result.append(n)
    if "hydration" not in names:
        from core.agent_core import PopNeed
        result.append(PopNeed(
            name="hydration",
            satisfaction=1.0,
            decay_rate=0.03,
            pressing_threshold=0.55,
            urgent_threshold=0.20,
        ))
    return result
```

Call it inside `_load_pop_agent_state` after deserialization.

- [ ] **Step 7: Update existing tests that reference "sustenance"**

In `tests/test_pop_agent.py`, find all assertions on `need.name == "sustenance"` or `get_need("sustenance")` and update them to `"nourishment"`. Run:
```bash
grep -n '"sustenance"' tests/test_pop_agent.py
```
for a list of lines to fix.

- [ ] **Step 8: Run full test suite**

```bash
pytest -v
```

Expected: all tests pass. Fix any remaining `NEED_SUSTENANCE` references.

- [ ] **Step 9: Commit**

```bash
git add logic/needs_config.py utilities/scenario_loader.py tests/test_resource_system.py tests/test_pop_agent.py logic/tick_logic.py
git commit -m "feat(needs): split sustenance into nourishment + hydration; migrate existing states"
```

---

## Task 4: Pop agent logic — action_types gating, yield deduction, consumption pass split

**Files:**
- Modify: `logic/pop_agent_logic.py`
- Test: `tests/test_resource_system.py`

**Context:** `logic/pop_agent_logic.py` has `ACTION_NEED_MAP` (line 18), `resolve_pop_actions` (around line 163), and the consumption pass at the end of `resolve_pop_actions` (around line 234). The function takes `(pop, pop_loc, pops_directives, current_tick, state)`. `pop_loc.collectible_resources` is now a list. The priority vector computation uses `ACTION_NEED_MAP` to map actions to needs — `forage` and `hunt` should map to `nourishment`, `collect` to either (use `nourishment` for priority purposes, hydration fulfillment is handled by the consumption pass).

- [ ] **Step 1: Write failing tests**

Add to `tests/test_resource_system.py`:

```python
from logic.pop_agent_logic import (
    resolve_pop_actions, compute_pop_priorities, ACTION_NEED_MAP,
)
from core.agent_core import PopAgentState, PopNeed, CollectibleResource
from core.universe_core import PopLocation, Pop
from unittest.mock import MagicMock


def _make_pop_state_with_needs(**need_satisfactions):
    needs = []
    defaults = {
        "nourishment": 1.0, "hydration": 1.0, "safety": 1.0,
        "cohesion": 1.0, "purpose": 1.0, "shelter": 1.0, "wanderlust": 0.0,
    }
    defaults.update(need_satisfactions)
    for name, sat in defaults.items():
        needs.append(PopNeed(name=name, satisfaction=sat,
                              decay_rate=0.02, pressing_threshold=0.55, urgent_threshold=0.20))
    return PopAgentState(needs=needs)

def _make_loc_with_resource(resource_type, max_yield, action_types, biochem_tags=None):
    cr = CollectibleResource(
        resource_type=resource_type, max_yield=max_yield,
        current_yield=max_yield, action_types=action_types,
        biochem_tags=biochem_tags or []
    )
    loc = PopLocation(id=uuid4(), name="Plains", parent_id=uuid4(),
                      collectible_resources=[cr])
    return loc


def test_action_need_map_forage_maps_to_nourishment():
    assert ACTION_NEED_MAP["forage"] == "nourishment"

def test_action_need_map_hunt_maps_to_nourishment():
    assert ACTION_NEED_MAP["hunt"] == "nourishment"

def test_action_need_map_no_sustenance_key():
    assert "sustenance" not in ACTION_NEED_MAP.values()

def test_forage_uses_resource_with_forage_action_type():
    pop = MagicMock()
    pop.id = uuid4()
    pop.pop_state = _make_pop_state_with_needs(nourishment=0.1)
    pop.size_fractional = 1.0
    pop.social_class = MagicMock()
    pop.social_class.value = "common"
    pop.occupation = "farmer"
    pop.active_directives = []
    pop.faction_ids = []

    loc = _make_loc_with_resource("food_flora", 10.0, ["forage"],
                                   biochem_tags=["basis:carbon"])
    state = MagicMock()
    state.factions = {}

    resolve_pop_actions(pop, loc, [], 1, state)

    assert loc.resource_stockpile.get("food_flora", 0.0) > 0
    assert loc.collectible_resources[0].current_yield < 10.0  # depleted

def test_collect_does_not_use_forage_only_resource():
    pop = MagicMock()
    pop.id = uuid4()
    pop.pop_state = _make_pop_state_with_needs(nourishment=0.1)
    pop.size_fractional = 1.0
    pop.social_class = MagicMock()
    pop.social_class.value = "common"
    pop.occupation = "farmer"
    pop.active_directives = []
    pop.faction_ids = []

    loc = _make_loc_with_resource("food_flora", 10.0, ["forage"])  # forage only
    state = MagicMock()
    state.factions = {}

    # Force "collect" to be the top action by using a Directive that boosts collect
    # Instead, just test that forage-only resource stays untouched when collect fires
    # We verify via: if only collect is in active slots and resource is forage-only → no depletion
    initial_yield = loc.collectible_resources[0].current_yield
    # Swap ACTION_NEED_MAP temporarily to force collect (not forage) to top
    # Better: test the filter function directly
    from logic.pop_agent_logic import _find_matching_resources
    matches = _find_matching_resources(loc.collectible_resources, "collect")
    assert all(cr.resource_type != "food_flora" for cr in matches)

def test_forage_bounded_by_current_yield():
    pop = MagicMock()
    pop.id = uuid4()
    pop.pop_state = _make_pop_state_with_needs(nourishment=0.1)
    pop.size_fractional = 5.0  # large pop → high output
    pop.social_class = MagicMock()
    pop.social_class.value = "common"
    pop.occupation = "farmer"
    pop.active_directives = []
    pop.faction_ids = []

    loc = _make_loc_with_resource("food_flora", 2.0, ["forage"])
    loc.collectible_resources[0].current_yield = 0.5  # nearly depleted
    state = MagicMock()
    state.factions = {}

    resolve_pop_actions(pop, loc, [], 1, state)

    # Stockpile cannot exceed what current_yield held
    assert loc.resource_stockpile.get("food_flora", 0.0) <= 0.5
    assert loc.collectible_resources[0].current_yield >= 0.0

def test_consumption_pass_basis_resource_fills_nourishment():
    pop = MagicMock()
    pop.id = uuid4()
    pop.pop_state = _make_pop_state_with_needs(nourishment=0.3)
    pop.size_fractional = 1.0
    pop.social_class = MagicMock()
    pop.social_class.value = "common"
    pop.occupation = "farmer"
    pop.active_directives = []
    pop.faction_ids = []

    loc = PopLocation(id=uuid4(), name="Plains", parent_id=uuid4(),
                      resource_stockpile={"food_flora": 10.0},
                      collectible_resources=[])
    state = MagicMock()
    state.factions = {}

    before = pop.pop_state.get_need("nourishment").satisfaction
    resolve_pop_actions(pop, loc, [], 1, state)
    after = pop.pop_state.get_need("nourishment").satisfaction
    assert after >= before  # passive consumption filled nourishment

def test_consumption_pass_solvent_resource_fills_hydration():
    pop = MagicMock()
    pop.id = uuid4()
    pop.pop_state = _make_pop_state_with_needs(hydration=0.3)
    pop.size_fractional = 1.0
    pop.social_class = MagicMock()
    pop.social_class.value = "common"
    pop.occupation = "farmer"
    pop.active_directives = []
    pop.faction_ids = []

    # potable_water is a known solvent:water resource type
    loc = PopLocation(id=uuid4(), name="Plains", parent_id=uuid4(),
                      resource_stockpile={"potable_water": 10.0},
                      collectible_resources=[])
    state = MagicMock()
    state.factions = {}

    before = pop.pop_state.get_need("hydration").satisfaction
    resolve_pop_actions(pop, loc, [], 1, state)
    after = pop.pop_state.get_need("hydration").satisfaction
    assert after >= before
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_resource_system.py -k "action_need_map or forage_uses or collect_does or consumption_pass" -v
```

- [ ] **Step 3: Add `_find_matching_resources` helper to `logic/pop_agent_logic.py`**

After the imports and constants block, add:

```python
def _find_matching_resources(
    collectible_resources: list, action: str
) -> list:
    """Return CollectibleResources usable by this action (action_types=[] means any)."""
    return [
        cr for cr in collectible_resources
        if (not cr.action_types or action in cr.action_types)
        and cr.current_yield > 0
    ]
```

- [ ] **Step 4: Update `ACTION_NEED_MAP` in `logic/pop_agent_logic.py`**

Replace `"sustenance"` references:
```python
ACTION_NEED_MAP: dict[str, str] = {
    "forage":        "nourishment",
    "hunt":          "nourishment",
    "collect":       "nourishment",
    "commune":       "cohesion",
    "revel":         "cohesion",
    "enact_rituals": "purpose",
    "build":         "shelter",
    "fortify":       "safety",
    "migrate":       "wanderlust",
    "raid":          "safety",
    "fight":         "safety",
    "rout":          "safety",
}
```

Also remove or update `POP_FOOD_RESOURCE_TYPES` and `SUSTENANCE_CONSUME_RATE` — these will be replaced by the consumption pass rewrite below. Add:

```python
NOURISHMENT_CONSUME_RATE = 0.05
HYDRATION_CONSUME_RATE   = 0.05
NOURISHMENT_FILL_RATE    = 0.08
HYDRATION_FILL_RATE      = 0.08
BASE_FORAGE_YIELD        = 0.1   # fallback when no matching collectible_resource

# Well-known resource types → biochem categories for stockpile consumption pass
_RESOURCE_BIOCHEM: dict[str, str] = {
    "food_flora":            "basis",
    "food_fauna":            "basis",
    "silicate_flora":        "basis",
    "silicate_fauna":        "basis",
    "methane_flora":         "basis",
    "methane_fauna":         "basis",
    "potable_water":         "solvent",
    "potable_sulfuric_acid": "solvent",
    "potable_ammonia":       "solvent",
    "potable_methane_liq":   "solvent",
}
```

- [ ] **Step 5: Update `resolve_pop_actions` — resource-producing actions**

Find the `forage`, `hunt`, and `collect` branches in `resolve_pop_actions` and replace them:

```python
if action in ("forage", "hunt", "collect"):
    matching = _find_matching_resources(pop_loc.collectible_resources, action)
    if matching:
        per_resource_output = output / len(matching)
        for cr in matching:
            actual = min(per_resource_output, cr.current_yield)
            cr.current_yield = max(0.0, cr.current_yield - actual)
            pop_loc.resource_stockpile[cr.resource_type] = (
                pop_loc.resource_stockpile.get(cr.resource_type, 0.0) + actual
            )
    else:
        # Environment fallback: sparse foraging without a defined resource
        if action == "forage":
            pop_loc.resource_stockpile["food_flora"] = (
                pop_loc.resource_stockpile.get("food_flora", 0.0)
                + output * BASE_FORAGE_YIELD
            )
        elif action == "hunt":
            pop_loc.resource_stockpile["food_fauna"] = (
                pop_loc.resource_stockpile.get("food_fauna", 0.0)
                + output * BASE_FORAGE_YIELD
            )
        # collect with no matching resource → no output
```

- [ ] **Step 6: Update the consumption pass in `resolve_pop_actions`**

Build a biochem-category map from the location's collectible_resources, then split the pass:

```python
# Build resource_type → "basis" | "solvent" map from location resources + well-known types
_biochem_map: dict[str, str] = dict(_RESOURCE_BIOCHEM)
for _cr in pop_loc.collectible_resources:
    if _cr.biochem_tags:
        if any(t.startswith("basis:") for t in _cr.biochem_tags):
            _biochem_map[_cr.resource_type] = "basis"
        elif any(t.startswith("solvent:") for t in _cr.biochem_tags):
            _biochem_map[_cr.resource_type] = "solvent"

nourishment = needs_by_name.get("nourishment")
hydration    = needs_by_name.get("hydration")

for resource_type, quantity in list(pop_loc.resource_stockpile.items()):
    if quantity <= 0:
        continue
    category = _biochem_map.get(resource_type)
    if category == "basis" and nourishment and nourishment.satisfaction < 1.0:
        consumed = min(quantity, NOURISHMENT_CONSUME_RATE)
        pop_loc.resource_stockpile[resource_type] -= consumed
        nourishment.satisfaction = min(1.0, nourishment.satisfaction + NOURISHMENT_FILL_RATE)
    elif category == "solvent" and hydration and hydration.satisfaction < 1.0:
        consumed = min(quantity, HYDRATION_CONSUME_RATE)
        pop_loc.resource_stockpile[resource_type] -= consumed
        hydration.satisfaction = min(1.0, hydration.satisfaction + HYDRATION_FILL_RATE)

# Narrative: unmet nourishment or hydration
if nourishment and nourishment.is_pressing and not any(
    _biochem_map.get(rt) == "basis" and q > 0
    for rt, q in pop_loc.resource_stockpile.items()
):
    from core.universe_core import pop_label as _pop_label
    narratives.append(
        f"§pop§{pop.id}§{_pop_label(pop)}§ has no food — nourishment unmet."
    )
if hydration and hydration.is_pressing and not any(
    _biochem_map.get(rt) == "solvent" and q > 0
    for rt, q in pop_loc.resource_stockpile.items()
):
    from core.universe_core import pop_label as _pop_label
    narratives.append(
        f"§pop§{pop.id}§{_pop_label(pop)}§ has no water — hydration unmet."
    )
```

Remove the old `sustenance`-based consumption block that this replaces.

- [ ] **Step 7: Run tests**

```bash
pytest -v
```

Expected: all pass. Fix any remaining `sustenance` references in `pop_agent_logic.py`.

- [ ] **Step 8: Commit**

```bash
git add logic/pop_agent_logic.py tests/test_resource_system.py
git commit -m "feat(pop-agent): action_types gating, current_yield deduction, nourishment+hydration consumption"
```

---

## Task 5: Yield renewal tick phase

**Files:**
- Modify: `logic/tick_logic.py`
- Test: `tests/test_resource_system.py`

**Context:** Yield renewal should run once per tick before Pop agents act, so resources have been partially renewed before Pops forage/hunt. Insert as Phase 2.54, after Phase 2.55 comment search in `tick_logic.py`. The `_tick_pop_agents` method is the Phase 2.57 method added during PopAgent implementation — yield renewal is a separate helper.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_resource_system.py`:

```python
from unittest.mock import MagicMock, patch
from core.agent_core import CollectibleResource
from core.universe_core import PopLocation


def _make_state_with_location(cr: CollectibleResource):
    loc = PopLocation(id=uuid4(), name="Plains", parent_id=uuid4(),
                      collectible_resources=[cr])
    state = MagicMock()
    state.locations = {str(loc.id): loc}
    return state, loc


def test_yield_renewal_increases_current_yield():
    cr = CollectibleResource(resource_type="food_flora", max_yield=10.0,
                              yield_renew_rate=0.1, current_yield=5.0)
    state, loc = _make_state_with_location(cr)

    from logic.tick_logic import _tick_yield_renewal
    _tick_yield_renewal(state)

    # 5.0 + 0.1 * 10.0 = 6.0
    assert loc.collectible_resources[0].current_yield == pytest.approx(6.0)

def test_yield_renewal_capped_at_max_yield():
    cr = CollectibleResource(resource_type="food_flora", max_yield=10.0,
                              yield_renew_rate=0.5, current_yield=9.0)
    state, loc = _make_state_with_location(cr)

    from logic.tick_logic import _tick_yield_renewal
    _tick_yield_renewal(state)

    # 9.0 + 0.5 * 10.0 = 14.0 → capped at 10.0
    assert loc.collectible_resources[0].current_yield == pytest.approx(10.0)

def test_yield_renewal_already_full_stays_full():
    cr = CollectibleResource(resource_type="food_flora", max_yield=10.0,
                              yield_renew_rate=0.2, current_yield=10.0)
    state, loc = _make_state_with_location(cr)

    from logic.tick_logic import _tick_yield_renewal
    _tick_yield_renewal(state)

    assert loc.collectible_resources[0].current_yield == pytest.approx(10.0)

def test_yield_renewal_skips_non_pop_locations():
    from core.universe_core import SignificantLocation
    sig_loc = SignificantLocation(id=uuid4(), name="Region", parent_id=uuid4())
    state = MagicMock()
    state.locations = {str(sig_loc.id): sig_loc}

    from logic.tick_logic import _tick_yield_renewal
    _tick_yield_renewal(state)  # should not raise
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_resource_system.py -k "yield_renewal" -v
```

Expected: ImportError — `_tick_yield_renewal` does not exist yet.

- [ ] **Step 3: Implement `_tick_yield_renewal` in `logic/tick_logic.py`**

Add this method to the `TickLoop` class (or as a module-level function if the existing `_tick_pop_agents` is a method — match the pattern). If implemented as a method, add it near `_tick_pop_agents`:

```python
def _tick_yield_renewal(self, state) -> None:
    """Phase 2.54 — renew collectible_resource yields at all PopLocations."""
    for loc in state.locations.values():
        if not isinstance(loc, PopLocation):
            continue
        for cr in loc.collectible_resources:
            recovered = cr.yield_renew_rate * cr.max_yield
            cr.current_yield = min(cr.max_yield, cr.current_yield + recovered)
```

If tick_logic uses a module-level function pattern instead, define it at module level:
```python
def _tick_yield_renewal(state) -> None:
    for loc in state.locations.values():
        if not isinstance(loc, PopLocation):
            continue
        for cr in loc.collectible_resources:
            recovered = cr.yield_renew_rate * cr.max_yield
            cr.current_yield = min(cr.max_yield, cr.current_yield + recovered)
```

Wire it into the tick loop as Phase 2.54, before the Phase 2.55 mortal agents call. Find the Phase 2.55 comment and add the call just above it:
```python
# Phase 2.54 — resource yield renewal
self._tick_yield_renewal(state)  # or _tick_yield_renewal(state) if module-level

# Phase 2.55 — mortal agents
...
```

The test imports `_tick_yield_renewal` from `logic.tick_logic` — if it's a method on `TickLoop`, expose it as a module-level alias at the bottom of the file or adjust the test to call it via a mock loop instance. Whichever is simpler given the existing patterns.

- [ ] **Step 4: Run tests**

```bash
pytest -v
```

Expected: all pass. Run `--autoplay` smoke test:
```bash
python main.py --autoplay
```
Expected: completes 50 ticks without errors.

- [ ] **Step 5: Commit**

```bash
git add logic/tick_logic.py tests/test_resource_system.py
git commit -m "feat(resources): Phase 2.54 collectible_resource yield renewal"
```

---

## Task 6: Mortal passive sustenance from inventory

**Files:**
- Modify: `logic/tick_logic.py`
- Test: `tests/test_resource_system.py`

**Context:** The current passive restore is at lines 5487–5490 in `tick_logic.py`:
```python
if loc and _effective_commerce_quality(loc, state) > 0:
    sust = cs.get_need(NEED_SUSTENANCE)
    if sust and sust.satisfaction < 1.0:
        sust.satisfaction = min(1.0, sust.satisfaction + 0.03)
```

This needs to be replaced with: (1) passive draw from KB inventory for basis:* resources → nourishment; (2) passive draw from inventory for solvent:* resources → hydration; (3) retain commerce-quality fallback for mortals without resources but in a market location.

The mortal's KB inventory is `mortal.mortal_state.inventory: list[Resource]`. `Resource` has `biochem_tags: list[str]`.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_resource_system.py`:

```python
from core.agent_core import MortalAgentState, MortalNeed, Resource


def _make_mortal_with_needs(**sats):
    needs = []
    defaults = {"nourishment": 1.0, "hydration": 1.0, "safety": 1.0,
                "belonging": 1.0, "status": 1.0, "purpose": 1.0, "leisure": 1.0}
    defaults.update(sats)
    for name, sat in defaults.items():
        needs.append(MortalNeed(name=name, satisfaction=sat,
                                 decay_rate=0.02, pressing_threshold=0.55,
                                 urgent_threshold=0.20))
    return MortalAgentState(needs=needs, inventory=[])


def test_mortal_with_food_in_inventory_gains_nourishment():
    cs = _make_mortal_with_needs(nourishment=0.3)
    food = Resource(resource_type="food_flora", biochem_tags=["basis:carbon"],
                    quantity=10.0)
    cs.inventory.append(food)

    mortal = MagicMock()
    mortal.mortal_state = cs
    mortal.current_location = uuid4()
    loc = MagicMock()
    loc.collectible_resources = []

    from logic.tick_logic import _tick_mortal_passive_sustenance
    _tick_mortal_passive_sustenance(mortal, loc)

    nour = cs.get_need("nourishment")
    assert nour.satisfaction > 0.3

def test_mortal_with_water_in_inventory_gains_hydration():
    cs = _make_mortal_with_needs(hydration=0.2)
    water = Resource(resource_type="potable_water", biochem_tags=["solvent:water"],
                     quantity=10.0)
    cs.inventory.append(water)

    mortal = MagicMock()
    mortal.mortal_state = cs
    loc = MagicMock()
    loc.collectible_resources = []

    from logic.tick_logic import _tick_mortal_passive_sustenance
    _tick_mortal_passive_sustenance(mortal, loc)

    hydr = cs.get_need("hydration")
    assert hydr.satisfaction > 0.2

def test_mortal_food_consumed_from_inventory():
    cs = _make_mortal_with_needs(nourishment=0.3)
    food = Resource(resource_type="food_flora", biochem_tags=["basis:carbon"],
                    quantity=1.0)
    cs.inventory.append(food)

    mortal = MagicMock()
    mortal.mortal_state = cs
    loc = MagicMock()
    loc.collectible_resources = []

    from logic.tick_logic import _tick_mortal_passive_sustenance
    _tick_mortal_passive_sustenance(mortal, loc)

    assert food.quantity < 1.0  # some consumed

def test_mortal_commerce_fallback_fills_nourishment():
    cs = _make_mortal_with_needs(nourishment=0.3)
    # No food in inventory
    mortal = MagicMock()
    mortal.mortal_state = cs
    loc = MagicMock()
    loc.collectible_resources = []

    from logic.tick_logic import _tick_mortal_passive_sustenance
    # commerce_quality > 0 triggers fallback
    _tick_mortal_passive_sustenance(mortal, loc, commerce_quality=0.8)

    nour = cs.get_need("nourishment")
    assert nour.satisfaction > 0.3
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_resource_system.py -k "mortal_with_food or mortal_with_water or mortal_food_consumed or mortal_commerce" -v
```

Expected: ImportError — `_tick_mortal_passive_sustenance` doesn't exist.

- [ ] **Step 3: Extract `_tick_mortal_passive_sustenance` in `logic/tick_logic.py`**

Add this module-level helper function:

```python
_MORTAL_FOOD_CONSUME_RATE  = 0.05
_MORTAL_DRINK_CONSUME_RATE = 0.05
_MORTAL_NOURISHMENT_FILL   = 0.03
_MORTAL_HYDRATION_FILL     = 0.025

def _tick_mortal_passive_sustenance(mortal, loc, commerce_quality: float = 0.0) -> None:
    """Passive nourishment + hydration restore from inventory; falls back to commerce."""
    cs = mortal.mortal_state
    nour = cs.get_need("nourishment")
    hydr = cs.get_need("hydration")

    food_consumed = False
    drink_consumed = False

    for res in cs.inventory:
        if not food_consumed and nour and nour.satisfaction < 1.0:
            if any(t.startswith("basis:") for t in res.biochem_tags) and res.quantity > 0:
                consumed = min(res.quantity, _MORTAL_FOOD_CONSUME_RATE)
                res.quantity = max(0.0, res.quantity - consumed)
                nour.satisfaction = min(1.0, nour.satisfaction + _MORTAL_NOURISHMENT_FILL)
                food_consumed = True
        if not drink_consumed and hydr and hydr.satisfaction < 1.0:
            if any(t.startswith("solvent:") for t in res.biochem_tags) and res.quantity > 0:
                consumed = min(res.quantity, _MORTAL_DRINK_CONSUME_RATE)
                res.quantity = max(0.0, res.quantity - consumed)
                hydr.satisfaction = min(1.0, hydr.satisfaction + _MORTAL_HYDRATION_FILL)
                drink_consumed = True
        if food_consumed and drink_consumed:
            break

    if commerce_quality > 0:
        if not food_consumed and nour and nour.satisfaction < 1.0:
            nour.satisfaction = min(1.0, nour.satisfaction + 0.02)
        if not drink_consumed and hydr and hydr.satisfaction < 1.0:
            hydr.satisfaction = min(1.0, hydr.satisfaction + 0.015)
```

- [ ] **Step 4: Replace the old passive restore block in `logic/tick_logic.py`**

Find lines 5487–5490:
```python
if loc and _effective_commerce_quality(loc, state) > 0:
    sust = cs.get_need(NEED_SUSTENANCE)
    if sust and sust.satisfaction < 1.0:
        sust.satisfaction = min(1.0, sust.satisfaction + 0.03)
```

Replace with:
```python
_cq = _effective_commerce_quality(loc, state) if loc else 0.0
_tick_mortal_passive_sustenance(mortal, loc, commerce_quality=_cq)
```

Remove the now-unused `NEED_SUSTENANCE` import from `needs_config` (or just leave the import cleanup to Task 3 if not already done).

- [ ] **Step 5: Run tests**

```bash
pytest -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add logic/tick_logic.py tests/test_resource_system.py
git commit -m "feat(mortal): passive nourishment+hydration from inventory; commerce fallback"
```

---

## Task 7: Mortal forage + hunt autonomous actions

**Files:**
- Modify: `logic/mortal_agent_logic.py`
- Modify: `logic/tick_logic.py`
- Test: `tests/test_resource_system.py`

**Context:** `evaluate_mortal_action` in `logic/mortal_agent_logic.py` returns a string action. It currently returns one of: `"collect"`, `"sell"`, `"spend"`, `"leisure"`, `"socialize"`, `"travel:<id>"`, `"idle"`, or `None`. We add `"forage"` and `"hunt"` as new return values. Forage/hunt fire at Priority 2.75 (before leisure at 3, after the sell/collect chain at 2.5) when nourishment is pressing and a matching resource exists at the mortal's current location. The tick_logic `collect` branch (around line 5623) needs sibling `forage` and `hunt` branches. Mortal forage/hunt yield is lower than Pop yield: `min(cr.max_yield * 0.15, cr.current_yield)`.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_resource_system.py`:

```python
from logic.mortal_agent_logic import evaluate_mortal_action


def _make_mortal_for_forage(nourishment_sat=0.3, has_forage_resource=True):
    cs = _make_mortal_with_needs(nourishment=nourishment_sat)
    mortal = MagicMock()
    mortal.mortal_state = cs
    mortal.knowledge_base = MagicMock()
    mortal.knowledge_base.facts = []
    mortal.knowledge_base.directive_facts = MagicMock(return_value=[])
    mortal.fatigue = 0.0
    mortal.pinned = False
    mortal.assets = []
    mortal.pop_milieu = None
    mortal.pop_id = uuid4()
    mortal.current_location = uuid4()

    if has_forage_resource:
        cr = CollectibleResource(resource_type="food_flora", max_yield=10.0,
                                  action_types=["forage"],
                                  biochem_tags=["basis:carbon"])
        loc = PopLocation(id=mortal.current_location, name="Plains",
                          parent_id=uuid4(), collectible_resources=[cr])
    else:
        loc = PopLocation(id=mortal.current_location, name="Plains",
                          parent_id=uuid4(), collectible_resources=[])

    state = MagicMock()
    state.locations = {str(mortal.current_location): loc}
    state.pops = {}
    return mortal, state


def test_mortal_forage_fires_when_nourishment_pressing():
    mortal, state = _make_mortal_for_forage(nourishment_sat=0.1, has_forage_resource=True)
    action = evaluate_mortal_action(mortal, state, 1)
    assert action == "forage"

def test_mortal_forage_does_not_fire_without_matching_resource():
    mortal, state = _make_mortal_for_forage(nourishment_sat=0.1, has_forage_resource=False)
    action = evaluate_mortal_action(mortal, state, 1)
    assert action != "forage"

def test_mortal_forage_does_not_fire_when_nourishment_ok():
    mortal, state = _make_mortal_for_forage(nourishment_sat=0.9, has_forage_resource=True)
    action = evaluate_mortal_action(mortal, state, 1)
    assert action != "forage"

def test_mortal_forage_produces_resource_in_inventory():
    mortal, state = _make_mortal_for_forage(nourishment_sat=0.1, has_forage_resource=True)

    loc = list(state.locations.values())[0]
    initial_yield = loc.collectible_resources[0].current_yield

    # Simulate tick_logic forage resolution (call the helper directly)
    from logic.tick_logic import _resolve_mortal_forage
    narratives = []
    _resolve_mortal_forage(mortal, loc, state, narratives)

    assert any(r.resource_type == "food_flora" for r in mortal.mortal_state.inventory)
    assert loc.collectible_resources[0].current_yield < initial_yield

def test_mortal_hunt_fires_when_nourishment_pressing_and_hunt_resource():
    cs = _make_mortal_with_needs(nourishment=0.1)
    mortal = MagicMock()
    mortal.mortal_state = cs
    mortal.knowledge_base = MagicMock()
    mortal.knowledge_base.facts = []
    mortal.knowledge_base.directive_facts = MagicMock(return_value=[])
    mortal.fatigue = 0.0
    mortal.pinned = False
    mortal.assets = []
    mortal.pop_milieu = None
    mortal.pop_id = uuid4()
    mortal.current_location = uuid4()

    cr = CollectibleResource(resource_type="food_fauna", max_yield=10.0,
                              action_types=["hunt"], biochem_tags=["basis:carbon"])
    loc = PopLocation(id=mortal.current_location, name="Plains",
                      parent_id=uuid4(), collectible_resources=[cr])
    state = MagicMock()
    state.locations = {str(mortal.current_location): loc}
    state.pops = {}

    action = evaluate_mortal_action(mortal, state, 1)
    assert action == "hunt"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_resource_system.py -k "mortal_forage or mortal_hunt" -v
```

Expected: ImportError or AssertionError.

- [ ] **Step 3: Add forage/hunt priority to `evaluate_mortal_action` in `logic/mortal_agent_logic.py`**

Find where the action priorities are evaluated (around line 400+, after the cargo state block). Add a check at Priority 2.75 (before the leisure/socialize check):

```python
# Priority 2.75 — forage/hunt when nourishment is pressing and a resource is available
if not _docked:
    _nour = cs.get_need("nourishment")
    if _nour and _nour.is_pressing:
        _forage_loc = state.locations.get(str(mortal.current_location))
        if _forage_loc:
            _forage_crs = getattr(_forage_loc, "collectible_resources", [])
            _forage_match = next(
                (cr for cr in _forage_crs
                 if "forage" in cr.action_types and cr.current_yield > 0),
                None
            )
            if _forage_match:
                return "forage"
            _hunt_match = next(
                (cr for cr in _forage_crs
                 if "hunt" in cr.action_types and cr.current_yield > 0),
                None
            )
            if _hunt_match:
                return "hunt"
```

Insert this block before the leisure check. Read the surrounding code to find the exact right insertion point — it must come after the sell/collect chain (`_docked` guard) and before `"leisure"` return.

- [ ] **Step 4: Add `_resolve_mortal_forage` in `logic/tick_logic.py`**

Add a module-level helper (alongside `_tick_mortal_passive_sustenance`):

```python
_MORTAL_FORAGE_YIELD_FRACTION = 0.15  # fraction of max_yield per forage action

def _resolve_mortal_forage(mortal, loc, state, narratives: list) -> None:
    """Resolve a mortal 'forage' or 'hunt' action — low-yield resource acquisition."""
    cs = mortal.mortal_state
    crs = getattr(loc, "collectible_resources", [])
    action = cs.last_action  # "forage" or "hunt"
    for cr in crs:
        if cr.action_types and action not in cr.action_types:
            continue
        if cr.current_yield <= 0:
            continue
        gained = min(cr.max_yield * _MORTAL_FORAGE_YIELD_FRACTION, cr.current_yield)
        cr.current_yield = max(0.0, cr.current_yield - gained)
        res = cs.get_resource(cr.resource_type)
        if res is None:
            from core.agent_core import Resource as _Resource
            res = _Resource(resource_type=cr.resource_type,
                            biochem_tags=list(cr.biochem_tags))
            cs.inventory.append(res)
        res.quantity += gained
        mortal.fatigue = min(1.0, mortal.fatigue + 0.10)
        if mortal.pinned:
            narratives.append(
                f"{mortal.name} forages {gained:.2f} {cr.resource_type}."
            )
        break  # one resource per tick
```

- [ ] **Step 5: Wire into tick_logic Phase 2.55 resolution**

In the block that dispatches based on `action == "collect"` (around line 5623), add `elif` branches for forage and hunt immediately after the `collect` block:

```python
elif action in ("forage", "hunt"):
    loc = state.locations.get(str(mortal.current_location))
    if loc:
        cs.last_action = action  # ensure _resolve_mortal_forage can read it
        _resolve_mortal_forage(mortal, loc, state, narratives)
```

- [ ] **Step 6: Run tests**

```bash
pytest -v
```

Expected: all pass. Also run autoplay smoke check:
```bash
python main.py --autoplay
```

- [ ] **Step 7: Commit**

```bash
git add logic/mortal_agent_logic.py logic/tick_logic.py tests/test_resource_system.py
git commit -m "feat(mortal): forage + hunt autonomous actions for pressing nourishment"
```

---

## Task 8: Documentation

**Files:**
- Modify: `docs/.dev/Mechanics/needs-and-directives.md`
- Modify: `docs/.dev/Mechanics/agent-system.md`

**Context:** `needs-and-directives.md` has a `CollectibleResource` section (around line 180) that references `resource_yield` and `collectible_resource: Optional[CollectibleResource]`. The mortal need table at the top references `sustenance`. `agent-system.md` has a Pop needs table that also references `sustenance`.

- [ ] **Step 1: Update `needs-and-directives.md`**

Replace the mortal need table entry for `sustenance` with two rows:

```markdown
| `NEED_NOURISHMENT` | `nourishment` | 0.02/tick | < 0.55 | < 0.20 |
| `NEED_HYDRATION`   | `hydration`   | 0.03/tick | < 0.55 | < 0.20 |
```

Replace the `CollectibleResource` section with:

```markdown
## CollectibleResource

`PopLocation.collectible_resources: list[CollectibleResource]` declares what a location produces when agents collect/forage/hunt there. A location can have multiple resources (e.g., food flora AND potable water).

```python
class CollectibleResource(BaseModel):
    resource_type: str                  # freeform string; drives stockpile/inventory key
    max_yield: float = 1.0              # maximum quantity available per full renewal
    yield_renew_rate: float = 0.2       # fraction of max_yield restored each tick
    current_yield: Optional[float] = None  # tracks depletion; initializes to max_yield
    cooldown_ticks: int = 3             # per-mortal cooldown (mortal collect only)
    action_types: list[str] = []        # ["forage"], ["hunt"], ["collect"], etc.; [] = any
    biochem_tags: list[str] = []        # species compatibility (see species-biology.md)
```

**Yield renewal (Phase 2.54):** Each tick, `current_yield += yield_renew_rate * max_yield`, capped at `max_yield`. Pops and mortals deduct from `current_yield` when they gather; output is bounded by what's available.

**Action types:** `action_types` controls which actions can use the resource. `["forage"]` means only Pop forage or mortal forage can draw from it. `[]` means any action. Use this to distinguish flora (forage-only), fauna (hunt-only), and labeled mineral/water sources (collect-only).

**Passive sustenance:** Resources are not consumed by explicit "eat" or "drink" actions. Instead:
- Pops: a consumption pass each tick draws `basis:*`-tagged resources from `resource_stockpile` → fills `nourishment`; draws `solvent:*`-tagged resources → fills `hydration`.
- Mortals: `_tick_mortal_passive_sustenance` draws from KB inventory each tick before other action evaluation.
```

- [ ] **Step 2: Update `agent-system.md` Pop needs table**

Find the Pop needs table in the `## Pop Agents (Implemented)` section and replace the `sustenance` row with:

```markdown
| `nourishment` | forage, hunt, collect (two-step: → stockpile → passive consume) | Filled from `basis:*`-tagged resources |
| `hydration`   | collect (two-step: → stockpile → passive consume)               | Filled from `solvent:*`-tagged resources; decays ~1.5× faster |
```

Update any other references to `sustenance` in that doc.

- [ ] **Step 3: Run full test suite one final time**

```bash
pytest -v
python main.py --autoplay
```

Expected: all 300+ tests pass; autoplay completes 50 ticks cleanly.

- [ ] **Step 4: Commit**

```bash
git add docs/.dev/Mechanics/needs-and-directives.md docs/.dev/Mechanics/agent-system.md
git commit -m "docs: update needs + CollectibleResource docs for resource system redesign"
```

---

## Self-Review

**Spec coverage check:**
- ✅ CollectibleResource list field, max_yield/yield_renew_rate/current_yield, action_types — Task 1
- ✅ DB schema + backward compat migration — Task 2
- ✅ Sustenance → nourishment + hydration, hydration faster decay — Task 3
- ✅ Pop action_types gating + current_yield depletion — Task 4
- ✅ Yield renewal tick phase — Task 5
- ✅ Mortal passive sustenance from inventory — Task 6
- ✅ Mortal forage + hunt autonomous actions — Task 7
- ✅ Documentation — Task 8

**Out of scope (do not implement):**
- ResourceStockpile shared-ownership system — separate plan
- Dedicated mortal hydration action — covered by collect + passive consume
- Pop "leak" migration — future

**Type consistency check:**
- `CollectibleResource.current_yield: Optional[float]` initialized via `model_validator` — consistent across Tasks 1, 2, 3, 4, 5, 7
- `PopLocation.collectible_resources: list[CollectibleResource]` — consistent across Tasks 1, 2, 4, 5, 7
- `_find_matching_resources(collectible_resources, action)` defined in Task 4 and tested in Task 4 — consistent
- `NEED_NOURISHMENT`, `NEED_HYDRATION` defined in Task 3 and used in Tasks 4, 6, 7 — consistent
- `_tick_mortal_passive_sustenance(mortal, loc, commerce_quality)` — consistent across Tasks 6 and 7
- `_resolve_mortal_forage(mortal, loc, state, narratives)` — defined in Task 7, called in Task 7
