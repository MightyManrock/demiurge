> status: active | last updated: 2026-05-29

# Belief Propagation: Extraction + Tuning

## Goal

Extract all belief/culture influence mechanics from `logic/tick_logic.py` into a dedicated `logic/belief_propagation.py` module, then implement the tuning changes discussed 2026-05-29 (strides, stratum weighting). This is a two-phase plan: Phase 1 is a pure mechanical extraction with no behavioral changes; Phase 2 adds the tuning on top of the clean module.

Reference: [belief-culture-influence.md](../Mechanics/belief-culture-influence.md)

---

## Phase 1: Extract to `logic/belief_propagation.py`

**Goal:** Move all belief propagation code out of `tick_logic.py`. No behavioral changes; tick_logic call sites become thin imports.

### What moves

**Module-level constants** (currently in tick_logic.py):
- `_SOCIAL_CLASS_RANK` (dict — stratum rank table)
- `_STRATUM_SUSCEPTIBILITY` (dict — flat susceptibility modifiers)
- `_CIV_SCALE_CONTACT_RANK` (dict — civ scale rank table)
- `_SCALE_CONFORMITY` (dict — civ scale → conformity multiplier) — currently defined inline inside `_tick_civilization_momentum`; extract to module level

**Pure functions** (currently module-level in tick_logic.py):
- `_location_distance_from_core(state, loc_id) -> int`
- `_pop_distance_factor(state, src_loc_id, tgt_loc_id) -> float`

**`_belief_inertia`** — currently a `@staticmethod` on `TickLoop`; move to module-level function.

**`TickLoop` methods** — convert to module-level functions taking `(state, cfg)`:
- `_pop_contact_resistance(target_pop, src_civ_id, src_species_id, src_class, state, cfg, src_size)` → `pop_contact_resistance(...)`
- `_process_pop_contact(state, cfg)` → `process_pop_contact(state, cfg)`
- `_recompute_civ_beliefs(state, cfg)` → `recompute_civ_beliefs(state, cfg)` — also handles culture
- `_recompute_civ_culture_tags(state, cfg)` → fold into `recompute_civ_beliefs` or keep separate
- `_civ_conformity_pressure(state, cfg, result)` → `civ_conformity_pressure(state, cfg)` returning list of `StateMutation`

### What stays in tick_logic.py

- The tick phase orchestration that calls the above (thin import + call)
- `_check_pop_splinter` — tightly coupled to tick phase ordering and mutation result; leave for now
- Lineage bleed logic (embedded in belief-shift apply handlers; leave for now)

### New file structure

```python
# logic/belief_propagation.py

from core.universe_core import Pop, Civilization
from core.action_core import StateMutation, MutationType
from logic.tick_logic import SimulationState, TickConfig  # avoid circular: import types only

_SOCIAL_CLASS_RANK: dict[str, int] = { ... }
_STRATUM_SUSCEPTIBILITY: dict[str, float] = { ... }
_CIV_SCALE_CONTACT_RANK: dict[str, int] = { ... }
_SCALE_CONFORMITY: dict[str, float] = { ... }

def belief_inertia(current: float, delta: float) -> float: ...
def location_distance_from_core(state, loc_id) -> int: ...
def pop_distance_factor(state, src_loc_id, tgt_loc_id) -> float: ...
def pop_contact_resistance(target_pop, src_civ_id, src_species_id, src_class, state, cfg, src_size) -> float: ...
def process_pop_contact(state, cfg) -> list[StateMutation]: ...
def recompute_civ_beliefs(state, cfg) -> None: ...  # mutates state in place (same as current)
def recompute_civ_culture_tags(state, cfg) -> None: ...
def civ_conformity_pressure(state, cfg) -> list[StateMutation]: ...
```

### Import strategy (avoid circular)

`belief_propagation.py` will need `SimulationState` and `TickConfig`. Since `tick_logic.py` defines these, import them from there: `from logic.tick_logic import SimulationState, TickConfig`. This is not circular as long as `tick_logic.py` does not import from `belief_propagation.py` at module level before the class definitions. Use a `TYPE_CHECKING` guard if needed.

Alternative: move `TickConfig` and `SimulationState` to `core/` — but that's a larger refactor; defer.

### Commit strategy

Single commit: "Extract belief propagation code to logic/belief_propagation.py". Tests + autoplay must pass before pushing.

---

## Phase 2: Tuning changes

**Goal:** Implement the four tuning adjustments on the extracted module. Three behavioral changes + one new TickConfig field.

### Change A: Stride civ conformity pressure (every 10 ticks)

In `tick_logic.py` tick phase orchestration:
```python
if state.tick_number % cfg.civ_conformity_stride == 0:
    mutations += civ_conformity_pressure(state, cfg)
```

New `TickConfig` field:
```python
civ_conformity_stride: int = 10
```

### Change B: Stride pop contact (every 7 ticks)

```python
if state.tick_number % cfg.pop_contact_stride == 0:
    mutations += process_pop_contact(state, cfg)
```

New `TickConfig` field:
```python
pop_contact_stride: int = 7
```

The two strides are intentionally co-prime (7 and 10) so they rarely fire on the same tick.

### Change C: Stratum influence weighting in civ aggregate

In `recompute_civ_beliefs` and `recompute_civ_culture_tags`, apply a multiplier to each pop's `size_fractional` when computing the weighted average:

```python
_STRATUM_INFLUENCE_WEIGHT: dict[str, float] = {
    "elite":      2.0,
    "scholar":    1.8,
    "warrior":    1.5,
    "trader":     1.2,
    "artisan":    1.1,
    "common":     1.0,
    "underclass": 0.8,
    "feral":      0.4,
    "wild":       0.1
}
```

```python
influence_w = _STRATUM_INFLUENCE_WEIGHT.get(pop_class, 1.0)
w = base_w * influence_w * (1.0 if is_core else cfg.peripheral_pop_belief_weight)
```

This gives politically prominent strata outsized representation in `dominant_beliefs`, which then feeds into `established_beliefs` and back to conformity pressure.

### Change D: Update mechanics doc

Update `docs/.dev/Mechanics/belief-culture-influence.md`:
- Move the "pending changes" section entries to the main body as implemented mechanics
- Record new TickConfig defaults

### Commit strategy

One commit per change (A, B, C each separate). Change D can be folded into the last behavioral commit or done as a cleanup commit.

---

## Files affected

| File | Change |
|---|---|
| `logic/belief_propagation.py` | New file (Phase 1) |
| `logic/tick_logic.py` | Remove extracted code, import from belief_propagation, add stride guards (Phase 1 + 2A/2B) |
| `core/action_core.py` or `logic/tick_logic.py` | Add `civ_conformity_stride` and `pop_contact_stride` to `TickConfig` |
| `docs/.dev/Mechanics/belief-culture-influence.md` | Update to reflect implemented changes |

---

## Notes

- Phase 1 must not change any numbers. If tests fail after extraction, the extraction has a bug.
- The `_pops_on_world` helper used by `_process_pop_contact` also lives in `TickLoop`; extract alongside or pass as argument.
- The pop anchor ("drift baseline") mechanic is explicitly deferred — it requires additional model plumbing and is logged in TO-PLAN.md.
