# Civilian Resource Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat `resources: float` field in `CivilianAgentState` with typed `Resource` objects, add a sell→credits pipeline, split need urgency into two thresholds, and give agents trip-length awareness so they don't start long journeys they can't survive.

**Architecture:** `Resource` objects carry their own action eligibility (`usable_for`), conversion chain (`converts_to`), and satisfaction linkage (`fills_need`). Decision logic in `civilian_agent_logic.py` operates on these objects directly — no magic strings in the tick engine. Priority order: sell sellable resources → spend credits → collect raw resources.

**Tech Stack:** Python 3.11, Pydantic v2 (`model_validate_json` / `model_dump_json`), pytest, SQLite (JSON blob columns — no schema migration needed).

---

## File Map

| File | Change |
|------|--------|
| `core/agent_core.py` | Add `Resource`; update `MortalNeed`, `CollectibleResource`, `LocationQualityFact`, `RouteFact`, `ResourceFact`, `CivilianAgentState`, `KnowledgeBase` |
| `logic/civilian_agent_logic.py` | Full rewrite of `evaluate_civilian_action`; add `SELL_COOLDOWN` and `_trip_too_long_for_urgent_need` |
| `logic/tick_logic.py` | Update `_tick_civilian_agents`: collect→unobtanium, add sell branch, spend→credits only |
| `ui/detail_renderers.py` | Replace `cs.resources` / `cs.spend_threshold` display with inventory breakdown |
| `autoplay/strategies/vail_travel_test.py` | Extend to track inventory and log sell/spend events |
| `tools/migrate_civilian_resources.py` | **New** — migration script to patch Vail's `civilian_state` and `knowledge_base` in `scenarios/wardens_compact.db` |
| `tests/conftest.py` | **New** — sys.path setup for pytest |
| `tests/test_agent_core.py` | **New** — unit tests for data models |
| `tests/test_civilian_logic.py` | **New** — unit tests for `evaluate_civilian_action` |

---

### Task 1: Data models (`core/agent_core.py`)

**Files:**
- Modify: `core/agent_core.py`
- Test: `tests/test_agent_core.py`

- [x] **Step 1.1: Create test scaffold**

```bash
mkdir -p /root/demiurge/tests
touch /root/demiurge/tests/__init__.py
```

Create `tests/conftest.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
```

- [x] **Step 1.2: Write failing tests for new data models**

Create `tests/test_agent_core.py`:

```python
import pytest
from core.agent_core import (
    Resource, MortalNeed, CivilianAgentState,
    CollectibleResource, LocationQualityFact, RouteFact, ResourceFact,
    KnowledgeBase,
)


# Resource

def test_resource_defaults():
    r = Resource(resource_type="credits")
    assert r.quantity == 0.0
    assert r.converts_to is None
    assert r.usable_for == []
    assert r.fills_need is None


def test_resource_below_threshold():
    r = Resource(resource_type="unobtanium", quantity=0.5, threshold=2.0)
    assert r.quantity < r.threshold


# MortalNeed

def test_mortal_need_pressing_threshold_default():
    n = MortalNeed(name="indulgence")
    assert n.pressing_threshold == 0.65


def test_mortal_need_is_pressing():
    n = MortalNeed(name="indulgence", satisfaction=0.5, pressing_threshold=0.65)
    assert n.is_pressing


def test_mortal_need_is_urgent():
    n = MortalNeed(name="indulgence", satisfaction=0.2, urgent_threshold=0.35)
    assert n.is_urgent


def test_mortal_need_not_urgent():
    n = MortalNeed(name="indulgence", satisfaction=0.5, urgent_threshold=0.35)
    assert not n.is_urgent


# CivilianAgentState

def test_civilian_state_inventory_default():
    cs = CivilianAgentState()
    assert cs.inventory == []


def test_civilian_state_get_resource_found():
    r = Resource(resource_type="unobtanium", quantity=5.0)
    cs = CivilianAgentState(inventory=[r])
    found = cs.get_resource("unobtanium")
    assert found is r


def test_civilian_state_get_resource_missing():
    cs = CivilianAgentState()
    assert cs.get_resource("unobtanium") is None


def test_civilian_state_round_trips_json():
    r = Resource(resource_type="unobtanium", quantity=3.0, usable_for=["sell"], converts_to="credits")
    cs = CivilianAgentState(inventory=[r])
    restored = CivilianAgentState.model_validate_json(cs.model_dump_json())
    assert restored.inventory[0].resource_type == "unobtanium"
    assert restored.inventory[0].usable_for == ["sell"]


def test_old_json_with_resources_float_loads_cleanly():
    # Pydantic v2 ignores unknown fields — old DB rows must not crash
    old_json = '{"needs":[],"resources":5.0,"spend_threshold":2.0,"action_cooldowns":{}}'
    cs = CivilianAgentState.model_validate_json(old_json)
    assert cs.inventory == []


# CollectibleResource

def test_collectible_resource_has_resource_type():
    cr = CollectibleResource()
    assert cr.resource_type == "unobtanium"


# LocationQualityFact

def test_location_quality_fact_quality_type_default():
    f = LocationQualityFact(location_id="abc")
    assert f.quality_type == "spend"


# RouteFact

def test_route_fact_ticks_cost_default():
    f = RouteFact(from_id="a", to_id="b")
    assert f.ticks_cost == 0


# ResourceFact

def test_resource_fact_resource_type_default():
    f = ResourceFact(location_id="abc")
    assert f.resource_type == "unobtanium"


# KnowledgeBase helpers

def test_knowledge_base_best_known_spend_location():
    kb = KnowledgeBase(facts=[
        LocationQualityFact(location_id="neran", quality=0.9, quality_type="spend"),
        LocationQualityFact(location_id="sethis", quality=0.2, quality_type="sell"),
    ])
    assert kb.best_known_spend_location() == "neran"


def test_knowledge_base_best_known_sell_location():
    kb = KnowledgeBase(facts=[
        LocationQualityFact(location_id="neran", quality=0.9, quality_type="sell"),
        LocationQualityFact(location_id="sethis", quality=0.2, quality_type="spend"),
    ])
    assert kb.best_known_sell_location() == "neran"


def test_knowledge_base_route_ticks_to():
    kb = KnowledgeBase(facts=[
        RouteFact(from_id="a", to_id="b", ticks_cost=12),
    ])
    assert kb.route_ticks_to("b") == 12
    assert kb.route_ticks_to("c") == 0
```

- [x] **Step 1.3: Run tests, confirm they fail**

```bash
cd /root/demiurge && source bin/activate && python -m pytest tests/test_agent_core.py -v 2>&1 | head -40
```

Expected: multiple `ImportError` or `AttributeError` failures.

- [x] **Step 1.4: Implement the data model changes**

In `core/agent_core.py`, make these changes in order:

**A. Add `Resource` class** — insert before `CivilianAgentState`:

```python
class Resource(BaseModel):
    resource_type: str
    quantity: float = 0.0
    base_value: float = 1.0
    converts_to: Optional[str] = None
    threshold: float = 1.0
    usable_for: list[str] = Field(default_factory=list)
    fills_need: Optional[str] = None
```

**B. Update `MortalNeed`** — change `pressing_threshold` default from `0.3` to `0.65`, add `urgent_threshold` field and `is_urgent` property:

```python
class MortalNeed(BaseModel):
    name: str
    satisfaction: float = Field(ge=0.0, le=1.0, default=1.0)
    decay_rate: float = 0.05
    pressing_threshold: float = 0.65
    urgent_threshold: float = 0.35
    satiation_hold: int = 0

    @property
    def is_pressing(self) -> bool:
        return self.satisfaction < self.pressing_threshold

    @property
    def is_urgent(self) -> bool:
        return self.satisfaction < self.urgent_threshold
```

**C. Update `CollectibleResource`** — add `resource_type` field:

```python
class CollectibleResource(BaseModel):
    resource_yield: float = 1.0
    cooldown_ticks: int = 3
    resource_type: str = "unobtanium"
```

**D. Update `LocationQualityFact`** — add `quality_type` field:

```python
class LocationQualityFact(BaseModel):
    fact_type: Literal["location_quality"] = "location_quality"
    location_id: str
    quality: float = 0.5
    quality_type: Literal["sell", "spend"] = "spend"
    confidence: float = 1.0
    learned_at_tick: int = 0
```

**E. Update `RouteFact`** — add `ticks_cost` field:

```python
class RouteFact(BaseModel):
    fact_type: Literal["route"] = "route"
    from_id: str
    to_id: str
    vehicle_type: Optional[str] = None
    ticks_cost: int = 0
    confidence: float = 1.0
    learned_at_tick: int = 0
```

**F. Update `ResourceFact`** — add `resource_type` field:

```python
class ResourceFact(BaseModel):
    fact_type: Literal["resource"] = "resource"
    location_id: str
    resource_type: str = "unobtanium"
    resource_yield: float = 1.0
    confidence: float = 1.0
    learned_at_tick: int = 0
```

**G. Update `CivilianAgentState`** — replace `resources: float` and `spend_threshold` with `inventory: list[Resource]`, add `get_resource` helper:

```python
class CivilianAgentState(BaseModel):
    needs: list[MortalNeed] = Field(default_factory=list)
    inventory: list[Resource] = Field(default_factory=list)
    action_cooldowns: dict[str, int] = Field(default_factory=dict)

    def pressing_needs(self) -> list[MortalNeed]:
        return [n for n in self.needs if n.is_pressing]

    def cooldown_expired(self, action_type: str, current_tick: int) -> bool:
        return self.action_cooldowns.get(action_type, 0) <= current_tick

    def get_resource(self, resource_type: str) -> Optional["Resource"]:
        return next((r for r in self.inventory if r.resource_type == resource_type), None)
```

**H. Update `KnowledgeBase`** — filter `best_known_spend_location` by `quality_type`, add `best_known_sell_location` and `route_ticks_to`:

```python
class KnowledgeBase(BaseModel):
    facts: list[KnowledgeFact] = Field(default_factory=list)

    def best_known_spend_location(self) -> Optional[str]:
        quality_facts = [
            f for f in self.facts
            if f.fact_type == "location_quality" and f.quality_type == "spend"
        ]
        if not quality_facts:
            return None
        return max(quality_facts, key=lambda f: f.quality * f.confidence).location_id

    def best_known_sell_location(self) -> Optional[str]:
        quality_facts = [
            f for f in self.facts
            if f.fact_type == "location_quality" and f.quality_type == "sell"
        ]
        if not quality_facts:
            return None
        return max(quality_facts, key=lambda f: f.quality * f.confidence).location_id

    def known_resource_locations(self) -> list[str]:
        return [f.location_id for f in self.facts if f.fact_type == "resource"]

    def route_to(self, to_id: str) -> Optional[RouteFact]:
        for f in self.facts:
            if f.fact_type == "route" and f.to_id == to_id:
                return f
        return None

    def route_ticks_to(self, to_id: str) -> int:
        fact = self.route_to(to_id)
        return fact.ticks_cost if fact else 0
```

- [x] **Step 1.5: Run tests, confirm they pass**

```bash
cd /root/demiurge && source bin/activate && python -m pytest tests/test_agent_core.py -v
```

Expected: all tests PASS.

- [x] **Step 1.6: Smoke-check the app still loads**

```bash
cd /root/demiurge && source bin/activate && python -c "from core.agent_core import CivilianAgentState, Resource, KnowledgeBase; print('ok')"
```

Expected: `ok`

- [x] **Step 1.7: Commit**

```bash
cd /root/demiurge && git add core/agent_core.py tests/conftest.py tests/__init__.py tests/test_agent_core.py && git commit -m "feat: typed Resource model, dual need thresholds, quality_type/ticks_cost on KB facts"
```

---

### Task 2: Rewrite civilian decision logic (`logic/civilian_agent_logic.py`)

**Files:**
- Modify: `logic/civilian_agent_logic.py`
- Test: `tests/test_civilian_logic.py`

- [x] **Step 2.1: Write failing tests**

Create `tests/test_civilian_logic.py`:

```python
import pytest
from unittest.mock import MagicMock
from core.agent_core import (
    CivilianAgentState, Resource, MortalNeed, KnowledgeBase,
    RouteFact, LocationQualityFact, ResourceFact,
)
from logic.civilian_agent_logic import evaluate_civilian_action


def _mortal(cs, kb=None, fatigue=0.0, assets=None, travel_intent=None, loc_id="loc-A"):
    m = MagicMock()
    m.civilian_state = cs
    m.knowledge_base = kb or KnowledgeBase()
    m.fatigue = fatigue
    m.assets = assets or []
    m.travel_intent = travel_intent
    m.current_location = loc_id
    return m


def _state(locations=None):
    s = MagicMock()
    s.locations = locations or {}
    return s


def _pressing_need():
    return MortalNeed(name="indulgence", satisfaction=0.3, pressing_threshold=0.65)


# No pressing needs → idle

def test_no_pressing_needs_returns_idle():
    cs = CivilianAgentState(
        needs=[MortalNeed(name="indulgence", satisfaction=1.0)],
    )
    result = evaluate_civilian_action(_mortal(cs), _state(), 0)
    assert result == "idle"


# Fatigue gate

def test_fatigue_blocks_action():
    cs = CivilianAgentState(needs=[_pressing_need()])
    result = evaluate_civilian_action(_mortal(cs, fatigue=0.9), _state(), 0)
    assert result == "idle"


# Sell priority: already at sell location

def test_sell_at_sell_location():
    sell_loc_id = "neran-surface"
    cs = CivilianAgentState(
        needs=[_pressing_need()],
        inventory=[Resource(resource_type="unobtanium", quantity=5.0, threshold=2.0, usable_for=["sell"])],
    )
    kb = KnowledgeBase(facts=[
        LocationQualityFact(location_id=sell_loc_id, quality=0.9, quality_type="sell"),
    ])
    result = evaluate_civilian_action(_mortal(cs, kb, loc_id=sell_loc_id), _state(), 0)
    assert result == "sell"


# Sell priority: needs to travel to sell location

def test_sell_triggers_travel_to_sell_location():
    sell_loc_id = "neran-surface"
    cs = CivilianAgentState(
        needs=[_pressing_need()],
        inventory=[Resource(resource_type="unobtanium", quantity=5.0, threshold=2.0, usable_for=["sell"])],
    )
    kb = KnowledgeBase(facts=[
        LocationQualityFact(location_id=sell_loc_id, quality=0.9, quality_type="sell"),
        RouteFact(from_id="sethis", to_id=sell_loc_id, ticks_cost=12),
    ])
    result = evaluate_civilian_action(_mortal(cs, kb, loc_id="sethis"), _state(), 0)
    assert result == f"travel:{sell_loc_id}"


# Sell skipped when unobtanium below threshold

def test_sell_skipped_below_threshold():
    sell_loc_id = "neran-surface"
    cs = CivilianAgentState(
        needs=[_pressing_need()],
        inventory=[Resource(resource_type="unobtanium", quantity=1.0, threshold=2.0, usable_for=["sell"])],
    )
    kb = KnowledgeBase(facts=[
        LocationQualityFact(location_id=sell_loc_id, quality=0.9, quality_type="sell"),
        RouteFact(from_id="sethis", to_id=sell_loc_id, ticks_cost=12),
    ])
    result = evaluate_civilian_action(_mortal(cs, kb, loc_id="sethis"), _state(), 0)
    assert result != f"travel:{sell_loc_id}"


# Spend priority: already at spend location

def test_spend_at_spend_location():
    spend_loc_id = "neran-surface"
    cs = CivilianAgentState(
        needs=[_pressing_need()],
        inventory=[Resource(resource_type="credits", quantity=3.0, threshold=1.0, usable_for=["spend"])],
    )
    kb = KnowledgeBase(facts=[
        LocationQualityFact(location_id=spend_loc_id, quality=0.9, quality_type="spend"),
    ])
    result = evaluate_civilian_action(_mortal(cs, kb, loc_id=spend_loc_id), _state(), 0)
    assert result == "spend"


# Collect priority: at resource location

def test_collect_at_resource_location():
    loc_id = "sethis-surface"
    loc = MagicMock()
    loc.collectible_resource = MagicMock()
    loc.location_type = "pop_location"
    cs = CivilianAgentState(needs=[_pressing_need()])
    kb = KnowledgeBase(facts=[ResourceFact(location_id=loc_id)])
    result = evaluate_civilian_action(_mortal(cs, kb, loc_id=loc_id), _state({loc_id: loc}), 0)
    assert result == "collect"


# Trip-length awareness: urgent need blocks long travel

def test_urgent_need_blocks_long_travel():
    sell_loc_id = "neran-surface"
    # satisfaction=0.2, decay_rate=0.05 → ticks_until_desperate = 4
    urgent_need = MortalNeed(name="indulgence", satisfaction=0.2, decay_rate=0.05,
                             pressing_threshold=0.65, urgent_threshold=0.35)
    cs = CivilianAgentState(
        needs=[urgent_need],
        inventory=[Resource(resource_type="unobtanium", quantity=5.0, threshold=2.0, usable_for=["sell"])],
    )
    kb = KnowledgeBase(facts=[
        LocationQualityFact(location_id=sell_loc_id, quality=0.9, quality_type="sell"),
        RouteFact(from_id="sethis", to_id=sell_loc_id, ticks_cost=12),
    ])
    result = evaluate_civilian_action(_mortal(cs, kb, loc_id="sethis"), _state(), 0)
    # Trip takes 12 ticks, need hits 0 in 4 → should NOT travel
    assert result != f"travel:{sell_loc_id}"
```

- [x] **Step 2.2: Run tests, confirm they fail**

```bash
cd /root/demiurge && source bin/activate && python -m pytest tests/test_civilian_logic.py -v 2>&1 | head -50
```

Expected: failures due to missing `SELL_COOLDOWN`, wrong return values from old logic.

- [x] **Step 2.3: Rewrite `logic/civilian_agent_logic.py`**

Replace the entire file content:

```python
from __future__ import annotations
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.universe_core import NotableMortal
    from core.agent_core import CivilianAgentState, KnowledgeBase
    from logic.tick_logic import SimulationState

FATIGUE_BLOCK_THRESHOLD = 0.85
COLLECT_COOLDOWN = "collect"
SELL_COOLDOWN = "sell"
SPEND_COOLDOWN = "spend"
TRAVEL_COOLDOWN = "travel"


def _mortal_is_travelling(mortal: NotableMortal, state: SimulationState) -> bool:
    if mortal.travel_intent is not None:
        return True
    loc = state.locations.get(str(mortal.current_location))
    return loc is not None and getattr(loc, "location_type", None) == "travel_location"


def _trip_too_long_for_urgent_need(
    cs: CivilianAgentState,
    kb: KnowledgeBase,
    dest_id: str,
) -> bool:
    """Return True if any urgent need will reach 0 before the trip completes."""
    ticks_cost = kb.route_ticks_to(dest_id)
    if ticks_cost == 0:
        return False
    for need in cs.needs:
        if need.is_urgent and need.decay_rate > 0:
            ticks_until_desperate = need.satisfaction / need.decay_rate
            if ticks_cost > ticks_until_desperate:
                return True
    return False


def evaluate_civilian_action(
    mortal: NotableMortal,
    state: SimulationState,
    current_tick: int,
) -> Optional[str]:
    """
    Returns one of: "collect", "sell", "spend", "travel:<location_id>", "idle", None.
    None means the mortal has no civilian_state and should be skipped.

    Priority: sell sellable resources → spend credits → collect raw resources.
    Long-trip guard: if any urgent need would hit 0 before arrival, skip that travel.
    """
    cs = mortal.civilian_state
    kb = mortal.knowledge_base
    if cs is None or kb is None:
        return None

    if _mortal_is_travelling(mortal, state):
        return "idle"

    if mortal.fatigue >= FATIGUE_BLOCK_THRESHOLD:
        return "idle"

    if not cs.pressing_needs():
        return "idle"

    current_loc_id = str(mortal.current_location)

    # ── Priority 1: sell ─────────────────────────────────────────────────────
    sellable = next(
        (r for r in cs.inventory if "sell" in r.usable_for and r.quantity >= r.threshold),
        None,
    )
    if sellable:
        best_sell_loc = kb.best_known_sell_location()
        if best_sell_loc:
            if current_loc_id == best_sell_loc:
                if cs.cooldown_expired(SELL_COOLDOWN, current_tick):
                    return "sell"
                return "idle"
            if cs.cooldown_expired(TRAVEL_COOLDOWN, current_tick):
                if not _trip_too_long_for_urgent_need(cs, kb, best_sell_loc):
                    route = kb.route_to(best_sell_loc)
                    if route and route.vehicle_type:
                        if not any(a.asset_type == route.vehicle_type for a in mortal.assets):
                            return "idle"
                    return f"travel:{best_sell_loc}"
            return "idle"

    # ── Priority 2: spend ────────────────────────────────────────────────────
    spendable = next(
        (r for r in cs.inventory if "spend" in r.usable_for and r.quantity >= r.threshold),
        None,
    )
    if spendable:
        best_spend_loc = kb.best_known_spend_location()
        if best_spend_loc:
            if current_loc_id == best_spend_loc:
                if cs.cooldown_expired(SPEND_COOLDOWN, current_tick):
                    return "spend"
                return "idle"
            if cs.cooldown_expired(TRAVEL_COOLDOWN, current_tick):
                if not _trip_too_long_for_urgent_need(cs, kb, best_spend_loc):
                    route = kb.route_to(best_spend_loc)
                    if route and route.vehicle_type:
                        if not any(a.asset_type == route.vehicle_type for a in mortal.assets):
                            return "idle"
                    return f"travel:{best_spend_loc}"
            return "idle"

    # ── Priority 3: collect ──────────────────────────────────────────────────
    resource_locs = kb.known_resource_locations()
    if not resource_locs:
        return "idle"

    loc = state.locations.get(current_loc_id)
    at_resource = (
        loc is not None
        and getattr(loc, "collectible_resource", None) is not None
        and current_loc_id in resource_locs
    )

    if at_resource:
        if cs.cooldown_expired(COLLECT_COOLDOWN, current_tick):
            return "collect"
        return "idle"

    if cs.cooldown_expired(TRAVEL_COOLDOWN, current_tick):
        dest = resource_locs[0]
        if not _trip_too_long_for_urgent_need(cs, kb, dest):
            route = kb.route_to(dest)
            if route and route.vehicle_type:
                if not any(a.asset_type == route.vehicle_type for a in mortal.assets):
                    return "idle"
            return f"travel:{dest}"

    return "idle"
```

- [x] **Step 2.4: Run tests, confirm they pass**

```bash
cd /root/demiurge && source bin/activate && python -m pytest tests/test_civilian_logic.py -v
```

Expected: all tests PASS.

- [x] **Step 2.5: Commit**

```bash
cd /root/demiurge && git add logic/civilian_agent_logic.py tests/test_civilian_logic.py && git commit -m "feat: sell→spend→collect priority, urgency trip-cost guard in civilian_agent_logic"
```

---

### Task 3: Update tick engine (`logic/tick_logic.py`)

**Files:**
- Modify: `logic/tick_logic.py` lines ~5342–5392 (`_tick_civilian_agents`)

- [x] **Step 3.1: Update the `collect` branch**

Find and replace the `collect` branch (around line 5342):

Old:
```python
            if action == "collect":
                loc = state.locations.get(str(mortal.current_location))
                resource = getattr(loc, "collectible_resource", None)
                if resource:
                    cs.resources += resource.resource_yield
                    mortal.fatigue = min(1.0, mortal.fatigue + 0.15)
                    cs.action_cooldowns["collect"] = current_tick + resource.cooldown_ticks
```

New:
```python
            if action == "collect":
                loc = state.locations.get(str(mortal.current_location))
                cr = getattr(loc, "collectible_resource", None)
                if cr:
                    res = cs.get_resource(cr.resource_type)
                    if res is None:
                        from core.agent_core import Resource as _Resource
                        res = _Resource(resource_type=cr.resource_type)
                        cs.inventory.append(res)
                    res.quantity += cr.resource_yield
                    mortal.fatigue = min(1.0, mortal.fatigue + 0.15)
                    cs.action_cooldowns["collect"] = current_tick + cr.cooldown_ticks
```

- [x] **Step 3.2: Replace the `spend` branch and add `sell` branch**

Find and replace the `spend` branch (around line 5350):

Old:
```python
            elif action == "spend":
                loc = state.locations.get(str(mortal.current_location))
                quality = getattr(loc, "commerce_quality", 0.5)
                # Spend minimum integer units to cover the largest need deficit.
                base_per_unit = 0.12
                bulk_bonus = 0.04
                max_deficit = max((1.0 - n.satisfaction for n in cs.needs), default=0.0)
                available = int(cs.resources)
                if max_deficit > 0 and base_per_unit * quality > 0:
                    n_units = max(1, min(
                        int(max_deficit / (base_per_unit * quality) + 0.5),
                        available,
                    ))
                else:
                    n_units = min(1, available)
                gain_per_need = n_units * base_per_unit * quality * (1 + bulk_bonus * (n_units - 1))
                cs.resources -= n_units
                hold_ticks = round(8 * quality)
                for need in cs.needs:
                    need.satisfaction = min(1.0, need.satisfaction + gain_per_need)
                    if need.satisfaction >= 1.0:
                        need.satiation_hold = hold_ticks
                cs.action_cooldowns["spend"] = current_tick + 2
```

New (sell + spend):
```python
            elif action == "sell":
                loc = state.locations.get(str(mortal.current_location))
                quality = getattr(loc, "commerce_quality", 0.5)
                for res in cs.inventory:
                    if "sell" not in res.usable_for or res.quantity < res.threshold:
                        continue
                    if res.converts_to is None:
                        continue
                    units = int(res.quantity)
                    if units == 0:
                        continue
                    credits_gained = units * res.base_value * quality
                    res.quantity -= units
                    target = cs.get_resource(res.converts_to)
                    if target is None:
                        from core.agent_core import Resource as _Resource
                        target = _Resource(resource_type=res.converts_to)
                        cs.inventory.append(target)
                    target.quantity += credits_gained
                    if res.fills_need:
                        need = next((n for n in cs.needs if n.name == res.fills_need), None)
                        if need:
                            need.satisfaction = min(1.0, need.satisfaction + min(0.4, credits_gained * 0.05))
                    mortal.fatigue = min(1.0, mortal.fatigue + 0.1)
                    cs.action_cooldowns["sell"] = current_tick + 2
                    break

            elif action == "spend":
                loc = state.locations.get(str(mortal.current_location))
                quality = getattr(loc, "commerce_quality", 0.5)
                for res in cs.inventory:
                    if "spend" not in res.usable_for or res.quantity < res.threshold:
                        continue
                    base_per_unit = 0.12
                    bulk_bonus = 0.04
                    target_need = (
                        next((n for n in cs.needs if n.name == res.fills_need), None)
                        if res.fills_need else None
                    )
                    needs_to_fill = [target_need] if target_need else cs.needs
                    max_deficit = max((1.0 - n.satisfaction for n in needs_to_fill), default=0.0)
                    available = int(res.quantity)
                    if max_deficit > 0 and base_per_unit * quality > 0:
                        n_units = max(1, min(
                            int(max_deficit / (base_per_unit * quality) + 0.5),
                            available,
                        ))
                    else:
                        n_units = min(1, available)
                    gain_per_need = n_units * base_per_unit * quality * (1 + bulk_bonus * (n_units - 1))
                    res.quantity -= n_units
                    hold_ticks = round(8 * quality)
                    for need in needs_to_fill:
                        need.satisfaction = min(1.0, need.satisfaction + gain_per_need)
                        if need.satisfaction >= 1.0:
                            need.satiation_hold = hold_ticks
                    cs.action_cooldowns["spend"] = current_tick + 2
                    break
```

- [x] **Step 3.3: Smoke-check tick_logic imports and syntax**

```bash
cd /root/demiurge && source bin/activate && python -c "from logic.tick_logic import TickLoop; print('ok')"
```

Expected: `ok`

- [x] **Step 3.4: Commit**

```bash
cd /root/demiurge && git add logic/tick_logic.py && git commit -m "feat: tick engine uses typed Resource inventory for collect/sell/spend"
```

---

### Task 4: Migrate scenario data (`tools/migrate_civilian_resources.py`)

**Files:**
- Create: `tools/migrate_civilian_resources.py`

This script loads `wardens_compact.db`, patches Vail's `civilian_state` and `knowledge_base` to use the new model, then re-exports.

Vail's planned state after migration:
- **inventory:** unobtanium (quantity=0, threshold=2, usable_for=["sell"], converts_to="credits", fills_need="trader"), credits (quantity=0, threshold=1, usable_for=["spend"], fills_need="indulgence")
- **needs:** pressing_threshold=0.65, urgent_threshold=0.35 for both
- **KB:** add `quality_type="sell"` facts for Neran Surface (0.9) and Sethis Surface (0.2); add `quality_type="spend"` to existing quality facts; add `ticks_cost=12` to both route facts; add `resource_type="unobtanium"` to existing resource fact

Vail's known location IDs (from current DB):
- Neran Surface: `2ac3f5fc-...` (check exact ID by running the script below first)
- Sethis Surface: `ef5b9dc6-...`
- Route from→to uses these IDs

- [x] **Step 4.1: Identify exact location IDs**

```bash
cd /root/demiurge && source bin/activate && python -c "
import sys; sys.path.insert(0, '.')
from utilities.scenario_loader import load_scenario
state = load_scenario('scenarios/wardens_compact.db')
vail = next(m for m in state.mortals.values() if m.name == 'Durenn Vail')
kb = vail.knowledge_base
for f in kb.facts:
    print(f.fact_type, f.__dict__)
"
```

Note the exact UUID strings for Neran Surface and Sethis Surface from the output.

- [x] **Step 4.2: Create migration script**

Create `tools/migrate_civilian_resources.py` — replace `NERAN_SURFACE_ID` and `SETHIS_SURFACE_ID` with the exact UUIDs from Step 4.1:

```python
#!/usr/bin/env python3
"""
Migrate Durenn Vail's civilian_state and knowledge_base in wardens_compact.db
to the typed Resource model.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utilities.scenario_loader import load_scenario
from utilities.scenario_exporter import export_scenario
from core.agent_core import (
    CivilianAgentState, Resource, MortalNeed,
    KnowledgeBase, LocationQualityFact, RouteFact, ResourceFact,
)

DB_PATH = "scenarios/wardens_compact.db"
VAIL_NAME = "Durenn Vail"

# Fill these in from Step 4.1 output:
NERAN_SURFACE_ID = "2ac3f5fc-FILL-IN"
SETHIS_SURFACE_ID = "ef5b9dc6-FILL-IN"


def migrate():
    state = load_scenario(DB_PATH)
    vail = next((m for m in state.mortals.values() if m.name == VAIL_NAME), None)
    if vail is None:
        print(f"ERROR: {VAIL_NAME} not found in {DB_PATH}")
        sys.exit(1)

    # ── civilian_state ──────────────────────────────────────────────────────
    vail.civilian_state = CivilianAgentState(
        needs=[
            MortalNeed(
                name="indulgence",
                satisfaction=0.1,
                decay_rate=0.02,
                pressing_threshold=0.65,
                urgent_threshold=0.35,
            ),
            MortalNeed(
                name="trader",
                satisfaction=0.1,
                decay_rate=0.015,
                pressing_threshold=0.65,
                urgent_threshold=0.35,
            ),
        ],
        inventory=[
            Resource(
                resource_type="unobtanium",
                quantity=0.0,
                base_value=1.0,
                converts_to="credits",
                threshold=2.0,
                usable_for=["sell"],
                fills_need="trader",
            ),
            Resource(
                resource_type="credits",
                quantity=0.0,
                base_value=1.0,
                converts_to=None,
                threshold=1.0,
                usable_for=["spend"],
                fills_need="indulgence",
            ),
        ],
        action_cooldowns={},
    )

    # ── knowledge_base ──────────────────────────────────────────────────────
    vail.knowledge_base = KnowledgeBase(facts=[
        # Location pointers (unchanged)
        *[f for f in (vail.knowledge_base.facts if vail.knowledge_base else [])
          if f.fact_type == "location"],

        # Resource fact — tag resource_type
        ResourceFact(
            location_id=SETHIS_SURFACE_ID,
            resource_type="unobtanium",
            resource_yield=10.0,
        ),

        # Spend quality facts
        LocationQualityFact(location_id=NERAN_SURFACE_ID, quality=0.9, quality_type="spend"),
        LocationQualityFact(location_id="b6e77481-FILL-IN", quality=0.5, quality_type="spend"),

        # Sell quality facts (Neran is best for selling)
        LocationQualityFact(location_id=NERAN_SURFACE_ID, quality=0.9, quality_type="sell"),
        LocationQualityFact(location_id=SETHIS_SURFACE_ID, quality=0.2, quality_type="sell"),

        # Routes with ticks_cost
        RouteFact(
            from_id=NERAN_SURFACE_ID,
            to_id=SETHIS_SURFACE_ID,
            vehicle_type="merchant_vessel",
            ticks_cost=12,
        ),
        RouteFact(
            from_id=SETHIS_SURFACE_ID,
            to_id=NERAN_SURFACE_ID,
            vehicle_type="merchant_vessel",
            ticks_cost=12,
        ),
    ])

    export_scenario(state, DB_PATH)
    print(f"Migration complete. Patched {VAIL_NAME} in {DB_PATH}.")


if __name__ == "__main__":
    migrate()
```

- [x] **Step 4.3: Fill in exact UUIDs**

Edit `tools/migrate_civilian_resources.py` and replace all `FILL-IN` placeholders with the actual UUID strings from Step 4.1. There are four IDs to fill in: Neran Surface, Sethis Surface, and Neran Orbital Ring (the third spend quality fact).

- [x] **Step 4.4: Run the migration**

```bash
cd /root/demiurge && source bin/activate && python tools/migrate_civilian_resources.py
```

Expected: `Migration complete. Patched Durenn Vail in scenarios/wardens_compact.db.`

- [x] **Step 4.5: Verify the migration round-tripped correctly**

```bash
cd /root/demiurge && source bin/activate && python -c "
import sys; sys.path.insert(0, '.')
from utilities.scenario_loader import load_scenario
state = load_scenario('scenarios/wardens_compact.db')
vail = next(m for m in state.mortals.values() if m.name == 'Durenn Vail')
cs = vail.civilian_state
print('inventory:', [(r.resource_type, r.quantity, r.usable_for) for r in cs.inventory])
print('needs:', [(n.name, n.pressing_threshold, n.urgent_threshold) for n in cs.needs])
kb = vail.knowledge_base
print('sell locs:', kb.best_known_sell_location())
print('spend locs:', kb.best_known_spend_location())
print('ticks to Sethis:', kb.route_ticks_to(kb.known_resource_locations()[0]))
"
```

Expected output includes:
- `inventory` showing unobtanium (usable_for=['sell']) and credits (usable_for=['spend'])
- `needs` with pressing_threshold=0.65 and urgent_threshold=0.35
- `sell locs` resolving to Neran Surface ID
- `ticks to Sethis` = 12

- [x] **Step 4.6: Commit**

```bash
cd /root/demiurge && git add tools/migrate_civilian_resources.py scenarios/wardens_compact.db && git commit -m "feat: migrate Vail to typed Resource inventory and dual-threshold needs"
```

---

### Task 5: Update UI renderer (`ui/detail_renderers.py`)

**Files:**
- Modify: `ui/detail_renderers.py` lines ~807–827

- [x] **Step 5.1: Replace the resources/spend_threshold display with inventory breakdown**

Find and replace this block (around line 811):

Old:
```python
        a(f"  resources: {cs.resources:.2f}  (spend threshold: {cs.spend_threshold:.2f})")
        a(f"  fatigue:   {m.fatigue:.2f}")
        if m.assets:
            a(f"  assets:    {_e(', '.join(a_.label or a_.asset_type for a_ in m.assets))}")
        if cs.needs:
            a("  needs:")
            for need in cs.needs:
                bar = "█" * int(need.satisfaction * 10) + "░" * (10 - int(need.satisfaction * 10))
                if need.is_pressing:
                    suffix = "  [#c09030][PRESSING][/]"
                elif need.satiation_hold > 0:
                    suffix = f"  [#60a860][held:{need.satiation_hold}][/]"
                else:
                    suffix = ""
                a(f"    {_e(need.name):12s} [{bar}] {need.satisfaction:.2f}{suffix}")
```

New:
```python
        a(f"  fatigue:   {m.fatigue:.2f}")
        if m.assets:
            a(f"  assets:    {_e(', '.join(a_.label or a_.asset_type for a_ in m.assets))}")
        if cs.inventory:
            a("  inventory:")
            for res in cs.inventory:
                thresh_tag = (
                    f"  [#888888](need {res.threshold:.0f})[/]"
                    if res.quantity < res.threshold else ""
                )
                a(f"    {_e(res.resource_type):15s} {res.quantity:6.2f}{thresh_tag}")
        else:
            a("  inventory: (empty)")
        if cs.needs:
            a("  needs:")
            for need in cs.needs:
                bar = "█" * int(need.satisfaction * 10) + "░" * (10 - int(need.satisfaction * 10))
                if need.is_urgent:
                    suffix = "  [#c04040][URGENT][/]"
                elif need.is_pressing:
                    suffix = "  [#c09030][PRESSING][/]"
                elif need.satiation_hold > 0:
                    suffix = f"  [#60a860][held:{need.satiation_hold}][/]"
                else:
                    suffix = ""
                a(f"    {_e(need.name):12s} [{bar}] {need.satisfaction:.2f}{suffix}")
```

- [x] **Step 5.2: Smoke-check the TUI renders without crashing**

```bash
cd /root/demiurge && source bin/activate && python -c "from ui.detail_renderers import render_mortal_detail; print('ok')"
```

Expected: `ok`

- [x] **Step 5.3: Commit**

```bash
cd /root/demiurge && git add ui/detail_renderers.py && git commit -m "feat: show typed inventory and URGENT need label in mortal detail renderer"
```

---

### Task 6: Update vail travel test + run autoplay validation

**Files:**
- Modify: `autoplay/strategies/vail_travel_test.py`

- [x] **Step 6.1: Extend the test to track inventory and sell/spend events**

Replace the file content:

```python
"""
autoplay/strategies/vail_travel_test.py

Validates Durenn Vail's full trade loop: collect unobtanium on Sethis,
sell on Neran, spend credits on Neran.

Expected behavior:
  Tick  1: Vail departs Neran → Sethis (12-tick journey)
  Tick 13: Arrives Sethis Surface; begins collecting unobtanium
  Tick ~16+: Unobtanium threshold reached; departs Sethis → Neran
  Tick ~28+: Arrives Neran Surface; sells unobtanium for credits
  Tick ~30+: Spends credits; indulgence need partially fulfilled
"""
from __future__ import annotations
from core.universe_core import TravelLocation, PopLocation
from core.agent_core import TravelIntent
from autoplay.strategies._helpers import queue, world_id
from logic.tick_logic import TickLoop, SimulationState

VAIL_NAME = "Durenn Vail"
MAX_TICKS = 50

_arrived_sethis: bool = False
_returned_neran: bool = False
_sold_unobtanium: bool = False
_spent_credits: bool = False
_prev_unobtanium: float = 0.0
_prev_credits: float = 0.0


def _vail(state: SimulationState):
    return next((m for m in state.mortals.values() if m.name == VAIL_NAME), None)


def _loc_name(state: SimulationState, loc_id) -> str:
    if loc_id is None:
        return "?"
    loc = state.locations.get(str(loc_id))
    return loc.name if loc else str(loc_id)


def _print_status(state: SimulationState, tick: int) -> None:
    global _prev_unobtanium, _prev_credits
    vail = _vail(state)
    if vail is None:
        print(f"  tick {tick:3d} | Vail NOT FOUND")
        return

    loc_name = _loc_name(state, vail.current_location)
    cs = vail.civilian_state

    inv_str = ""
    if cs and cs.inventory:
        parts = []
        for r in cs.inventory:
            parts.append(f"{r.resource_type}={r.quantity:.1f}")
        inv_str = "  inv:[" + ", ".join(parts) + "]"

    ti = vail.travel_intent
    if ti is not None:
        tl = state.locations.get(str(ti.travel_location_id))
        if isinstance(tl, TravelLocation):
            wp_name = _loc_name(state, tl.current_waypoint)
            dest_key = next(k for k, v in tl.legs.items() if v == 0)
            dest_name = _loc_name(state, dest_key)
            print(f"  tick {tick:3d} | IN TRANSIT → {dest_name}"
                  f"  (leg: {wp_name}, {tl.ticks_remaining} tick(s) left){inv_str}")
        else:
            print(f"  tick {tick:3d} | travel_intent → missing TravelLocation{inv_str}")
    else:
        print(f"  tick {tick:3d} | AT {loc_name}{inv_str}")


def decide(loop: TickLoop, state: SimulationState, tick: int) -> str:
    global _arrived_sethis, _returned_neran, _sold_unobtanium, _spent_credits
    global _prev_unobtanium, _prev_credits

    _print_status(state, tick)

    vail = _vail(state)
    if vail and vail.travel_intent is None and vail.civilian_state:
        cs = vail.civilian_state
        loc = _loc_name(state, vail.current_location)

        if loc == "Sethis Surface":
            _arrived_sethis = True

        elif loc == "Neran Surface" and _arrived_sethis:
            _returned_neran = True

        unobtanium = next((r.quantity for r in cs.inventory if r.resource_type == "unobtanium"), 0.0)
        credits = next((r.quantity for r in cs.inventory if r.resource_type == "credits"), 0.0)

        if unobtanium < _prev_unobtanium and credits > _prev_credits:
            _sold_unobtanium = True
            print(f"  tick {tick:3d} | *** SOLD unobtanium → credits ({credits:.2f})")

        if credits < _prev_credits:
            _spent_credits = True
            print(f"  tick {tick:3d} | *** SPENT credits")

        _prev_unobtanium = unobtanium
        _prev_credits = credits

    if tick >= MAX_TICKS:
        print(f"\n=== RESULT at tick {tick} ===")
        print(f"  arrived Sethis:   {_arrived_sethis}")
        print(f"  returned Neran:   {_returned_neran}")
        print(f"  sold unobtanium:  {_sold_unobtanium}")
        print(f"  spent credits:    {_spent_credits}")
        if _arrived_sethis and _returned_neran and _sold_unobtanium and _spent_credits:
            print("PASS: Vail completed full trade loop.")
        elif _arrived_sethis and _returned_neran:
            print("PASS (partial): round trip done but sell/spend not observed.")
        elif _arrived_sethis:
            print("PASS (partial): reached Sethis, did not return.")
        else:
            print("FAIL: Vail did not reach Sethis within 50 ticks.")

    from core.action_core import EssenceHarvestIntent, TargetType
    queue(loop, state, "harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(concealment_priority=0.9))
    return "Idle harvest (watching Vail)."
```

- [x] **Step 6.2: Run the autoplay validation**

```bash
cd /root/demiurge && source bin/activate && python main.py --autoplay vail_travel_test 2>&1 | tail -30
```

Expected: output shows Vail traveling to Sethis, collecting unobtanium, returning to Neran, selling, spending. Final line should be `PASS: Vail completed full trade loop.`

If you see `PASS (partial): round trip done but sell/spend not observed`, check that the migration ran correctly (Task 4.5 verification).

If Vail is blocked at tick 1 (never starts travel), check the `pressing_needs()` condition — needs start at `satisfaction=0.1` which is below both thresholds, so they should be pressing.

- [x] **Step 6.3: Run unit tests one final time**

```bash
cd /root/demiurge && source bin/activate && python -m pytest tests/ -v
```

Expected: all tests PASS.

- [x] **Step 6.4: Commit**

```bash
cd /root/demiurge && git add autoplay/strategies/vail_travel_test.py && git commit -m "feat: extend vail_travel_test to validate full sell/spend trade loop"
```

---

### Task 7: Push

- [x] **Step 7.1: Push to origin**

```bash
cd /root/demiurge && git push origin agent-mvp
```

---

## Self-Review

**Spec coverage:**
- [x] `resources` → typed `Resource` list — Task 1 + Task 3
- [x] unobtanium / credits split — Task 1 (Resource model), Task 4 (migration)
- [x] Two urgency thresholds (`pressing` at 0.65, `urgent` at 0.35) — Task 1 (MortalNeed)
- [x] sell pipeline (unobtanium → credits) — Task 3 (collect→credits formula), Task 3 tick
- [x] Trip-length awareness — Task 2 (`_trip_too_long_for_urgent_need`)
- [x] KB knows sell vs spend locations — Task 1 (`quality_type` + `best_known_sell_location`)
- [x] KB knows route cost — Task 1 (`ticks_cost` + `route_ticks_to`)
- [x] Scenario data patched — Task 4
- [x] UI shows inventory breakdown + URGENT label — Task 5
- [x] Autoplay test validates full loop — Task 6

**Placeholder scan:** No TBD/TODO/implement-later text present.

**Type consistency:**
- `Resource.resource_type` used consistently in tick_logic, agent_logic, migration, and tests
- `cs.inventory` replaces `cs.resources` everywhere
- `cs.get_resource()` used in tick_logic for upsert pattern
- `quality_type` field name consistent across `LocationQualityFact`, `best_known_spend_location`, `best_known_sell_location`
- `ticks_cost` field name consistent across `RouteFact`, `route_ticks_to`, `_trip_too_long_for_urgent_need`
