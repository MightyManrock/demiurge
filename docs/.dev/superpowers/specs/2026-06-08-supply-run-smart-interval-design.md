# Design: supply_run Smart Delivery Interval

**Date:** 2026-06-08
**Status:** Approved
**Scope:** `logic/pop_agent_logic.py`, `core/agent_core.py`

---

## Problem

`supply_run` carriers currently run a continuous tight loop: load → travel → deposit → travel home → repeat, every tick they're at home. They never check whether the destination stockpile actually needs a refill. A carrier will make redundant trips even when the destination is fully stocked, crowding out the normal need-driven behaviour they'd otherwise perform at home.

---

## Solution

Two-layer stockpile awareness, enabled by `StockpileFact` (new KB fact type):

1. **At-deposit (direct observation):** immediately after depositing, the carrier observes the destination stockpile and decides whether to delay the next run.
2. **Pre-travel (stale KB):** before starting the outbound leg, the carrier checks their last-remembered stockpile snapshot; if it still looks adequate they delay without making the trip.

Both layers use the same demand proxy and noise model already used for yield/stockpile priority dampening.

---

## Data Model

### `StockpileFact` (new, `core/agent_core.py`)

```python
class StockpileFact(BaseModel):
    fact_type: Literal["stockpile"] = "stockpile"
    location_id: str
    quantities: dict[str, float]   # public stockpile snapshot at last observation
    confidence: float = 1.0
    learned_at_tick: int = 0
```

One fact per location — a whole-stockpile snapshot, not per-resource. Added to the `KnowledgeFact` discriminated union.

**Scope:** applies to both `PopAgentState.knowledge_base` and mortal `KnowledgeBase` — mortals will benefit from the same discovery logic, and `StockpileFact` will be useful for raid decision-making later.

### `KnowledgeBase` helpers (new)

```python
def get_stockpile_fact(self, location_id: str) -> Optional[StockpileFact]: ...
def stockpile_facts(self) -> list[StockpileFact]: ...
```

### `PopAgentState` (new field)

```python
supply_run_skip_until: dict[str, int] = {}
```

Maps directive ID (string) → tick number to resume. When `current_tick < supply_run_skip_until[directive_id]`, the carrier skips the directive this tick and acts on normal need priorities instead.

---

## KB Sync

Extend the existing co-location sync block in `resolve_pop_actions` (already runs each tick when `pop_loc is not None`):

- Upsert a `StockpileFact` for `pop_loc.id` with the public stockpile's current `quantities` and `learned_at_tick = current_tick`.
- If a fact for this location already exists, update it in place.

This is universal — all Pops update their stockpile knowledge whenever co-located, not just supply_run carriers.

---

## Demand Calculation

Same pattern as yield/stockpile priority dampening:

```python
demand = sum(
    math.log(p.size_fractional + 1)
    for p in colocated_pops
    if can_access_stockpile(p, pub_stockpile) and p.id != pop.id
) * random.uniform(0.6, 1.4)
demand = max(demand, 1e-6)
```

The carrier excludes itself (`p.id != pop.id`) — it is the supplier, not a consumer at the destination.

---

## Skip Logic

### Delay duration

Use `directive.interval_ticks` if non-zero; otherwise default to **5 ticks**.

### Threshold

`total_manifest_qty / demand >= 1.0` — meaning the stockpile holds at least one full demand-unit of each manifest resource. Noise is already baked into the demand calculation, so no separate threshold noise is needed.

`total_manifest_qty` is the sum of `quantities.get(resource_type, 0.0)` across all resources in `cargo_manifest`.

### At-deposit check (A)

After `deposit_cargo` executes:

1. Read the `StockpileFact` for the current location (just updated this tick — fresh).
2. Compute demand (entitled co-located Pops excluding self, with noise).
3. If `total_manifest_qty / demand >= 1.0`: set `ps.supply_run_skip_until[str(directive.id)] = current_tick + delay`.

### Pre-travel check (B)

When `_supply_run_phase` would return `"load"` (carrier is at home, about to start the outbound leg):

1. Resolve destination location from `directive.target_pop_id`.
2. Look up `ps.knowledge_base.get_stockpile_fact(str(dest_loc_id))`.
3. If **absent**: carrier has never visited — proceed unconditionally.
4. If **present**: compare stale `quantities` against `cargo_manifest`. If the stockpile holds at least one full manifest-worth of every resource (`quantities.get(rt, 0.0) >= manifest_qty * noise` for all `rt` in manifest, where `noise = random.uniform(0.6, 1.4)`) → set skip.

The threshold here is deliberately simpler than the at-deposit check: "they still have at least as much as I was planning to bring, so the trip isn't needed yet." No demand calculation is attempted pre-travel because the carrier is at home and does not have current knowledge of who is co-located at the destination.

Staleness is intentional and realistic. If the skip proves wrong (destination ran dry), the carrier will re-assess on the next deposit and shorten or clear the skip.

### Skip enforcement

At the top of the supply_run loop in `resolve_pop_actions`, before calling `_supply_run_phase`:

```python
if current_tick < ps.supply_run_skip_until.get(str(_sd.id), 0):
    continue  # skip this directive; carrier acts on normal need priorities
```

---

## Behaviour Summary

| Situation | Result |
|---|---|
| First outbound leg ever | Always proceeds (no KB fact for destination) |
| Destination well-stocked at deposit | Carrier delays next run by `interval_ticks` |
| Pre-travel: stale KB shows destination well-stocked | Carrier skips outbound leg, re-checks each tick |
| Skip expires; destination still stocked | New skip set after next deposit |
| Skip expires; destination now depleted | Run proceeds normally |

---

## Future

- Mortal agents will use `StockpileFact` for trade, appeal, and raid target evaluation once those systems exist.
- Raid logic can read `get_stockpile_fact(target_location)` to estimate the value of a raid before committing to travel.
- `learned_at_tick` enables staleness-aware confidence decay if desired later.
