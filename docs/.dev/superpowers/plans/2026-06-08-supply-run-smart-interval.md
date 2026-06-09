# supply_run Smart Delivery Interval Implementation Plan

> **Status: complete (2026-06-09).** All three tasks implemented and playtested.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent `supply_run` carriers from making redundant delivery trips when the destination stockpile is already adequately stocked, by checking demand vs. stockpile immediately after depositing and delaying the next run if supply is sufficient.

**Architecture:** `StockpileFact` is a new `KnowledgeFact` subtype (one per location, whole-stockpile snapshot). All Pops sync a `StockpileFact` for their current location each tick. After a successful `deposit_cargo`, the carrier checks the post-deposit stockpile against a log-sum demand estimate of entitled co-located Pops; if stocked above demand, it sets `PopAgentState.supply_run_skip_until` to delay the next outbound leg.

**Tech Stack:** Python/Pydantic, `core/agent_core.py`, `logic/pop_agent_logic.py`, `tests/test_resource_system.py`, `tests/test_phase2_directives.py`

---

## Files

- **Modify:** `core/agent_core.py` — add `StockpileFact`, add to `KnowledgeFact` union, add `KnowledgeBase` helpers, add `PopAgentState.supply_run_skip_until`
- **Modify:** `logic/pop_agent_logic.py` — extend co-location KB sync block, add skip enforcement to supply_run loop, add at-deposit demand check
- **Modify:** `tests/test_resource_system.py` — `StockpileFact` model + KB helper tests + KB sync behaviour test
- **Modify:** `tests/test_phase2_directives.py` — skip enforcement test + at-deposit check tests

---

## Task 1: StockpileFact model, KB helpers, PopAgentState field

**Files:**
- Modify: `core/agent_core.py`
- Modify: `tests/test_resource_system.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_resource_system.py` (after the existing KB/PopAgentState imports at the top, add `StockpileFact`):

```python
# ── StockpileFact ─────────────────────────────────────────────────────────────

from core.agent_core import StockpileFact  # add to top-of-file import

def test_stockpile_fact_fact_type():
    sf = StockpileFact(location_id="loc-1", quantities={"food_flora": 5.0})
    assert sf.fact_type == "stockpile"

def test_stockpile_fact_stores_quantities():
    sf = StockpileFact(location_id="loc-1", quantities={"food_flora": 5.0, "potable_water": 3.0})
    assert sf.quantities["food_flora"] == 5.0
    assert sf.quantities["potable_water"] == 3.0

def test_stockpile_fact_defaults():
    sf = StockpileFact(location_id="loc-1", quantities={})
    assert sf.confidence == 1.0
    assert sf.learned_at_tick == 0

def test_kb_get_stockpile_fact_found():
    from core.agent_core import KnowledgeBase, StockpileFact
    kb = KnowledgeBase()
    sf = StockpileFact(location_id="loc-1", quantities={"food_flora": 5.0})
    kb.facts.append(sf)
    assert kb.get_stockpile_fact("loc-1") is sf

def test_kb_get_stockpile_fact_absent():
    from core.agent_core import KnowledgeBase
    kb = KnowledgeBase()
    assert kb.get_stockpile_fact("loc-1") is None

def test_kb_stockpile_facts_returns_all():
    from core.agent_core import KnowledgeBase, StockpileFact
    kb = KnowledgeBase()
    sf1 = StockpileFact(location_id="loc-1", quantities={})
    sf2 = StockpileFact(location_id="loc-2", quantities={})
    kb.facts.extend([sf1, sf2])
    assert set(id(f) for f in kb.stockpile_facts()) == {id(sf1), id(sf2)}

def test_pop_agent_state_has_supply_run_skip_until():
    from core.agent_core import PopAgentState
    ps = PopAgentState()
    assert ps.supply_run_skip_until == {}

def test_supply_run_skip_until_is_mutable_per_instance():
    from core.agent_core import PopAgentState
    ps1 = PopAgentState()
    ps2 = PopAgentState()
    ps1.supply_run_skip_until["dir-1"] = 10
    assert ps2.supply_run_skip_until == {}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
source venv/bin/activate
pytest tests/test_resource_system.py -k "stockpile_fact or supply_run_skip" -v
```

Expected: `ImportError` or `AttributeError` — `StockpileFact` does not exist yet.

- [ ] **Step 3: Add `StockpileFact` to `core/agent_core.py`**

After `MortalFact` (around line 80), add:

```python
class StockpileFact(BaseModel):
    fact_type: Literal["stockpile"] = "stockpile"
    location_id: str
    quantities: dict[str, float] = Field(default_factory=dict)
    confidence: float = 1.0
    learned_at_tick: int = 0
```

Update the `KnowledgeFact` union (around line 82):

```python
KnowledgeFact = Annotated[
    LocationFact | ResourceFact | RouteFact | LocationQualityFact | DirectiveFact | PopFact | MortalFact | StockpileFact,
    Field(discriminator="fact_type"),
]
```

- [ ] **Step 4: Add KB helpers to `KnowledgeBase`**

After `get_mortal_fact` (around line 155), add:

```python
def stockpile_facts(self) -> list[StockpileFact]:
    return [f for f in self.facts if f.fact_type == "stockpile"]

def get_stockpile_fact(self, location_id: str) -> Optional[StockpileFact]:
    return next(
        (f for f in self.facts if f.fact_type == "stockpile" and f.location_id == location_id),
        None,
    )
```

- [ ] **Step 5: Add `supply_run_skip_until` to `PopAgentState`**

In `PopAgentState` (around line 227, after `knowledge_base`):

```python
supply_run_skip_until: dict[str, int] = Field(default_factory=dict)
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/test_resource_system.py -k "stockpile_fact or supply_run_skip" -v
```

Expected: all new tests PASS.

- [ ] **Step 7: Run full suite**

```bash
pytest
```

Expected: all tests PASS (no regressions — new fields have defaults, union is additive).

- [ ] **Step 8: Commit**

```bash
git add core/agent_core.py tests/test_resource_system.py
git commit -m "feat(agent_core): StockpileFact type, KB helpers, PopAgentState.supply_run_skip_until"
```

---

## Task 2: KB stockpile sync in `resolve_pop_actions`

All Pops upsert a `StockpileFact` for their current location each tick as part of the existing co-location sync block.

**Files:**
- Modify: `logic/pop_agent_logic.py`
- Modify: `tests/test_resource_system.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_resource_system.py`:

```python
def test_resolve_pop_actions_syncs_stockpile_fact_to_kb():
    from uuid import uuid4
    from unittest.mock import MagicMock
    from core.agent_core import PopAgentState, ResourceStockpile
    from core.universe_core import PopLocation
    from logic.pop_agent_logic import resolve_pop_actions

    loc_id = uuid4()
    pop_loc = PopLocation(id=loc_id)
    stockpile = ResourceStockpile(quantities={"food_flora": 7.5})
    pop_loc.resource_stockpiles = [stockpile]

    pop = MagicMock()
    pop.id = uuid4()
    pop.faction_ids = []
    pop.active_directives = []
    pop.band_id = None
    pop.size_fractional = 1.0
    pop.occupation = "producer"
    pop.stratum = "common"
    pop.current_location = loc_id
    pop.migration_travel_location_id = None
    ps = PopAgentState()
    pop.pop_state = ps

    resolve_pop_actions(pop, pop_loc=pop_loc, factions={}, current_tick=5, colocated_pops=[pop])

    sf = ps.knowledge_base.get_stockpile_fact(str(loc_id))
    assert sf is not None
    assert sf.quantities.get("food_flora", 0.0) == pytest.approx(7.5)
    assert sf.learned_at_tick == 5

def test_resolve_pop_actions_updates_existing_stockpile_fact():
    from uuid import uuid4
    from unittest.mock import MagicMock
    from core.agent_core import PopAgentState, ResourceStockpile, StockpileFact
    from core.universe_core import PopLocation
    from logic.pop_agent_logic import resolve_pop_actions

    loc_id = uuid4()
    pop_loc = PopLocation(id=loc_id)
    stockpile = ResourceStockpile(quantities={"food_flora": 3.0})
    pop_loc.resource_stockpiles = [stockpile]

    pop = MagicMock()
    pop.id = uuid4()
    pop.faction_ids = []
    pop.active_directives = []
    pop.band_id = None
    pop.size_fractional = 1.0
    pop.occupation = "producer"
    pop.stratum = "common"
    pop.current_location = loc_id
    pop.migration_travel_location_id = None
    ps = PopAgentState()
    # Pre-populate a stale fact
    ps.knowledge_base.facts.append(StockpileFact(location_id=str(loc_id), quantities={"food_flora": 99.0}, learned_at_tick=0))
    pop.pop_state = ps

    resolve_pop_actions(pop, pop_loc=pop_loc, factions={}, current_tick=10, colocated_pops=[pop])

    sf = ps.knowledge_base.get_stockpile_fact(str(loc_id))
    assert sf is not None
    assert sf.quantities.get("food_flora", 0.0) == pytest.approx(3.0)
    assert sf.learned_at_tick == 10
    # Should be one fact, not two
    assert len(ps.knowledge_base.stockpile_facts()) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_resource_system.py -k "syncs_stockpile_fact or updates_existing_stockpile_fact" -v
```

Expected: FAIL — no stockpile sync in `resolve_pop_actions` yet.

- [ ] **Step 3: Add stockpile sync to the KB co-location block**

In `logic/pop_agent_logic.py`, the co-location sync block starts around line 410 (`if pop_loc is not None:`). Add the stockpile upsert **after** the ResourceFact sync loop and **before** the demand calculation, importing `StockpileFact` at the top of the function or via the module-level import:

First, add `StockpileFact` to the import in `pop_agent_logic.py` (around line 9):

```python
from core.agent_core import (
    PopAgentState, PopNeed, ResourceFact, StockpileFact, ResourceStockpile, can_access_stockpile,
    load_cargo as _load_cargo_fn, unload_cargo as _unload_cargo_fn,
)
```

Then, inside the `if pop_loc is not None:` block, after the ResourceFact sync loop (after line ~436), add:

```python
        # Sync StockpileFact: snapshot the public stockpile for this location
        _pub_kb = _public_stockpile(pop_loc)
        _sf = ps.knowledge_base.get_stockpile_fact(_loc_id_str)
        if _sf is not None:
            _sf.quantities = dict(_pub_kb.quantities)
            _sf.learned_at_tick = current_tick
        else:
            ps.knowledge_base.facts.append(StockpileFact(
                location_id=_loc_id_str,
                quantities=dict(_pub_kb.quantities),
                learned_at_tick=current_tick,
            ))
```

Note: `_loc_id_str` and `_pub_d` (the public stockpile used for demand) are already computed just below this point. Rename `_pub_d` usage accordingly — the stockpile sync uses `_public_stockpile(pop_loc)` directly, same call as `_pub_d` below. You can reuse `_pub_d` as the variable name if you move the `_pub_d =` line before the stockpile sync block.

Concretely, restructure the block opening (currently ~line 438) so that `_pub_d` is assigned once before both the StockpileFact sync and the demand calc:

```python
        _pub_d = _public_stockpile(pop_loc)

        # Sync StockpileFact
        _sf = ps.knowledge_base.get_stockpile_fact(_loc_id_str)
        if _sf is not None:
            _sf.quantities = dict(_pub_d.quantities)
            _sf.learned_at_tick = current_tick
        else:
            ps.knowledge_base.facts.append(StockpileFact(
                location_id=_loc_id_str,
                quantities=dict(_pub_d.quantities),
                learned_at_tick=current_tick,
            ))

        # Demand = log-sum of sizes of entitled co-located Pops, with noise
        _demand = sum(
            math.log(p.size_fractional + 1)
            for p in (colocated_pops or [])
            if can_access_stockpile(p, _pub_d)
        ) * random.uniform(0.6, 1.4)
        _demand = max(_demand, 1e-6)
```

(The existing `_pub_d =` line at ~438 is removed and replaced by the version above.)

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_resource_system.py -k "syncs_stockpile_fact or updates_existing_stockpile_fact" -v
```

Expected: PASS.

- [ ] **Step 5: Run full suite**

```bash
pytest
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add core/agent_core.py logic/pop_agent_logic.py tests/test_resource_system.py
git commit -m "feat(pop_agent): sync StockpileFact to Pop KB each tick at co-location"
```

---

## Task 3: Skip enforcement + at-deposit demand check

After a successful `deposit_cargo`, the carrier checks whether the destination stockpile is already stocked above demand. If so, it delays the next run. The supply_run loop checks `supply_run_skip_until` each tick and skips the directive while the delay is active.

**Files:**
- Modify: `logic/pop_agent_logic.py`
- Modify: `tests/test_phase2_directives.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_phase2_directives.py` (add `from unittest.mock import patch` if not already imported at the top):

```python
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


def test_supply_run_skip_prevents_travel_home_dest():
    """Carrier mid-journey home with active skip does not get pending_migration_dest set.

    Without skip: travel_home phase sets pending_migration_dest = src_id.
    With skip active: supply_run loop is bypassed, so pending_migration_dest stays None.
    """
    from logic.pop_agent_logic import resolve_pop_actions
    from core.agent_core import PopAgentState, ResourceStockpile
    from core.universe_core import PopLocation

    src_id = uuid4()
    dst_pop_id = uuid4()
    d = _make_supply_run_directive_with_interval(src_id, dst_pop_id)

    # Carrier is at some arbitrary location (not source, not dest) with no cargo
    # → would normally be "travel_home" phase, which sets pending_migration_dest
    arbitrary_loc_id = uuid4()
    pop_loc = PopLocation(id=arbitrary_loc_id)
    pop_loc.resource_stockpiles = [ResourceStockpile(quantities={})]

    dest_pop = MagicMock()
    dest_pop.current_location = uuid4()  # somewhere different from carrier

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
    # No cargo — travel_home phase
    ps.supply_run_skip_until[str(d.id)] = 999  # active skip
    pop.pop_state = ps

    state = MagicMock()
    state.pops = {str(dst_pop_id): dest_pop}

    resolve_pop_actions(
        pop, pop_loc=pop_loc, factions={}, current_tick=5,
        colocated_pops=[pop], state=state,
    )
    # Skip was active: pending_migration_dest must NOT have been set by supply_run
    assert ps.pending_migration_dest is None


def test_supply_run_deposit_sets_skip_when_stockpile_adequate():
    """After depositing into a well-stocked destination, carrier sets skip_until.

    random.uniform is patched to 1.0 for determinism.
    Setup: 1 small entitled Pop (demand ≈ log(2) ≈ 0.69).
    Post-deposit stockpile: 50 + 5 = 55 units → ratio ≈ 79 >> 1.0 → skip set.
    """
    from unittest.mock import patch
    from logic.pop_agent_logic import resolve_pop_actions
    from core.agent_core import PopAgentState, ResourceStockpile
    from core.universe_core import PopLocation

    src_id = uuid4()
    dst_pop_id = uuid4()
    dst_loc_id = uuid4()
    d = _make_supply_run_directive_with_interval(src_id, dst_pop_id, interval_ticks=8)

    pop_loc = PopLocation(id=dst_loc_id)
    pop_loc.resource_stockpiles = [ResourceStockpile(quantities={"food_flora": 50.0})]

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
            pop, pop_loc=pop_loc, factions={}, current_tick=10,
            colocated_pops=[pop, colocated], state=state,
        )
    # skip_until = current_tick + interval_ticks = 10 + 8 = 18
    assert ps.supply_run_skip_until.get(str(d.id), 0) == 18


def test_supply_run_deposit_no_skip_when_demand_exceeds_stockpile():
    """After depositing a small amount into a high-demand destination, no skip is set.

    random.uniform is patched to 1.0 for determinism.
    Setup: 5 large entitled Pops (demand ≈ 5 * log(6) ≈ 8.97).
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

    pop_loc = PopLocation(id=dst_loc_id)
    pop_loc.resource_stockpiles = [ResourceStockpile(quantities={})]

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

    # 5 large entitled co-located Pops (size=5.0 each), all different from carrier
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
            pop, pop_loc=pop_loc, factions={}, current_tick=10,
            colocated_pops=colocated_pops, state=state,
        )
    assert ps.supply_run_skip_until.get(str(d.id), 0) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_phase2_directives.py -k "skip_blocks or sets_skip or no_skip" -v
```

Expected: FAIL — skip logic not implemented yet.

- [ ] **Step 3: Add skip enforcement to the supply_run loop**

In `logic/pop_agent_logic.py`, find the supply_run loop (around line 483):

```python
    for _sd in _sr_directives:
        _sr_phase = _supply_run_phase(pop, _sd, _pops_dict)
```

Add the skip guard as the **first thing** inside the loop body:

```python
    for _sd in _sr_directives:
        if current_tick < ps.supply_run_skip_until.get(str(_sd.id), 0):
            continue  # skip active: carrier acts on normal need priorities this tick
        _sr_phase = _supply_run_phase(pop, _sd, _pops_dict)
```

- [ ] **Step 4: Add at-deposit demand check**

Inside the `elif action == "deposit_cargo":` block (around line 587), after the `_unload_cargo_fn` calls and before the `break`, add:

```python
                    # At-deposit check: if destination is well-stocked relative to demand,
                    # delay the next run by interval_ticks (default 5).
                    _post_qtys = _pub.quantities
                    _total_stocked = sum(_post_qtys.get(_rt, 0.0) for _rt in _manifest)
                    _dest_demand = sum(
                        math.log(p.size_fractional + 1)
                        for p in (colocated_pops or [])
                        if can_access_stockpile(p, _pub) and p.id != pop.id
                    ) * random.uniform(0.6, 1.4)
                    _dest_demand = max(_dest_demand, 1e-6)
                    if _total_stocked / _dest_demand >= 1.0:
                        _delay = _sd.interval_ticks if _sd.interval_ticks > 0 else 5
                        ps.supply_run_skip_until[str(_sd.id)] = current_tick + _delay
```

The full updated `deposit_cargo` block looks like:

```python
        elif action == "deposit_cargo":
            for _sd in _sr_directives:
                if _supply_run_phase(pop, _sd, _pops_dict) == "deposit":
                    _pub = _public_stockpile(pop_loc)
                    _manifest = _sd.cargo_manifest or {}
                    if not _manifest and _sd.cargo_resource_type:
                        _manifest = {_sd.cargo_resource_type: float(_sd.cargo_quantity)}
                    for _rt, _qty in _manifest.items():
                        _unload_cargo_fn(ps.cargo, _pub, _rt, _qty)
                    # At-deposit check: delay next run if destination is well-stocked
                    _post_qtys = _pub.quantities
                    _total_stocked = sum(_post_qtys.get(_rt, 0.0) for _rt in _manifest)
                    _dest_demand = sum(
                        math.log(p.size_fractional + 1)
                        for p in (colocated_pops or [])
                        if can_access_stockpile(p, _pub) and p.id != pop.id
                    ) * random.uniform(0.6, 1.4)
                    _dest_demand = max(_dest_demand, 1e-6)
                    if _total_stocked / _dest_demand >= 1.0:
                        _delay = _sd.interval_ticks if _sd.interval_ticks > 0 else 5
                        ps.supply_run_skip_until[str(_sd.id)] = current_tick + _delay
                    break
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_phase2_directives.py -k "skip_blocks or sets_skip or no_skip" -v
```

Expected: PASS. Note: `test_supply_run_deposit_sets_skip_when_stockpile_adequate` exercises a random noise factor — the 50-unit stockpile vs a tiny demand should reliably clear the threshold regardless of the `random.uniform(0.6, 1.4)` draw. If the test is flaky, increase stockpile to 200.0.

- [ ] **Step 6: Run full suite**

```bash
pytest
```

Expected: all tests PASS.

- [ ] **Step 7: Run 100-tick Oros playtest**

```bash
python tools/oros_observe.py
```

Spot-check: the Stonecaller or Hiparunite supply_run carrier should show gaps between delivery runs when the destination stockpile stays stocked. Carriers should not make consecutive runs when the destination is at capacity.

- [ ] **Step 8: Commit**

```bash
git add logic/pop_agent_logic.py tests/test_phase2_directives.py
git commit -m "feat(pop_agent): supply_run smart interval — skip when destination stocked"
```
