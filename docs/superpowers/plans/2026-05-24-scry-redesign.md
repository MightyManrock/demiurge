# Scry Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add asymptotic momentum accumulation, dynamic footprint scaling, parent-visibility cascade, and a PopLocation distance cap to scry — making repeated scrys build toward discovery without flat probability inflation.

**Architecture:** Momentum is stored on `Demiurge.scry_momentum` (dict keyed by `"{scope}:{target_id_or_None}"`), decayed every tick in `TickLoop.advance()`, and grown whenever scry fires via a new `DEMIURGE_SCRY_MOMENTUM_UPDATE` mutation. Discovery bonuses from momentum and parent-entity visibility are applied additively to `base` inside `_process_scry`. The uncharted-galaxy exception is preserved unchanged.

**Tech Stack:** Python 3, Pydantic v2, SQLite (via `core/scenario_schema.sql`), `logic/tick_logic.py` simulation engine.

---

## File Map

| File | Change |
|---|---|
| `core/onto_core.py` | Add `scry_momentum` field to `Demiurge` |
| `core/scenario_schema.sql` | Add `scry_momentum` column to `demiurge` table |
| `utilities/scenario_loader.py` | Load `scry_momentum` in `_load_demiurge` |
| `utilities/scenario_exporter.py` | Export `scry_momentum` in `_write_demiurge` |
| `core/action_core.py` | Add `DEMIURGE_SCRY_MOMENTUM_UPDATE` to `MutationType` |
| `logic/tick_logic.py` | (a) handler in `_apply_mutations`; (b) per-tick decay in `advance()`; (c) momentum growth + fp + discovery bonuses in `_process_scry`; (d) distance cap + parent cascade in mortal/pop sections |
| `utilities/action_registry.py` | Change `fp_subtle_influence` for scry from `0.05` → `0.01` |
| `docs/Mechanics/scry-action.md` | Update to reflect new mechanics |

---

## Task 1: Demiurge model + persistence

**Files:**
- Modify: `core/onto_core.py:196`
- Modify: `core/scenario_schema.sql:296`
- Modify: `utilities/scenario_loader.py:744-765`
- Modify: `utilities/scenario_exporter.py:548-578`

- [x] **Step 1: Add field to Demiurge model**

In `core/onto_core.py`, after line 196 (`puissance: float = 0.0`), add:

```python
    scry_momentum: dict[str, float] = Field(default_factory=dict)
    # "{scope}:{target_id_or_None}" → [0, 1] accumulation; decays when scry not active.
```

- [x] **Step 2: Add column to schema**

In `core/scenario_schema.sql`, in the `demiurge` table definition (after `lifetime_revelation REAL NOT NULL DEFAULT 0.0`), add:

```sql
    scry_momentum         TEXT NOT NULL DEFAULT '{}'   -- JSON {"scope:target": float}
```

- [x] **Step 3: Load in scenario_loader.py**

In `utilities/scenario_loader.py`, in `_load_demiurge` (line ~765), add `scry_momentum=` to the `Demiurge(...)` constructor, after `lifetime_revelation=`:

```python
        scry_momentum=_j(row.get("scry_momentum", "{}")),
```

- [x] **Step 4: Export in scenario_exporter.py**

In `utilities/scenario_exporter.py`, in `_write_demiurge` (lines 548-578), add `scry_momentum` to both the column list and values tuple.

Column list (add after `lifetime_revelation`):
```python
            scry_momentum, revealed_imagines, lifetime_revelation)
```

Wait — full replacement of the INSERT statement:

```python
    conn.execute(
        """INSERT INTO demiurge
           (id, name, liege_luminary_ids,
            fp_overt_miracles, fp_subtle_influence,
            fp_proxius_activity, fp_direct_creation,
            proxius_ids, unlocked_domain_tags, unlocked_imagines,
            affiliated_domains, max_affiliated_domains, tracked_essence_domains,
            revelation_pools, revealed_imagines, lifetime_revelation,
            scry_momentum)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            str(d.id),
            d.name,
            _j(d.liege_luminary_ids),
            fp.overt_miracles,
            fp.subtle_influence,
            fp.proxius_activity,
            fp.direct_creation,
            _j(d.proxius_ids),
            _j(d.unlocked_domain_tags),
            _j(d.unlocked_imagines),
            _j(d.affiliated_domains),
            d.max_affiliated_domains,
            _j(d.tracked_essence_domains),
            _j(d.revelation_pools),
            d.revealed_imagines,
            d.lifetime_revelation,
            _j(d.scry_momentum),
        ),
    )
```

- [x] **Step 5: Regression — migration**

```bash
cd /root/demiurge && python3 main.py --rebuild --scenario
```

Expected: no errors, all `.db` files migrate cleanly (new column gets `'{}'` default).

- [x] **Step 6: Regression — autoplay**

```bash
cd /root/demiurge && python3 main.py --autoplay
```

Expected: completes 50 ticks without error.

- [x] **Step 7: Commit**

```bash
git add core/onto_core.py core/scenario_schema.sql utilities/scenario_loader.py utilities/scenario_exporter.py
git commit -m "feat: add scry_momentum field to Demiurge model with full persistence"
```

---

## Task 2: MutationType + _apply_mutations handler

**Files:**
- Modify: `core/action_core.py:748`
- Modify: `logic/tick_logic.py` (`_apply_mutations`, ~line 6679)

- [x] **Step 1: Add MutationType enum value**

In `core/action_core.py`, after `MORTAL_POP_AGED_OUT` (line 748), add:

```python
    DEMIURGE_SCRY_MOMENTUM_UPDATE = "demiurge_scry_momentum_update"  # field=key, new_value=float
```

- [x] **Step 2: Add handler in _apply_mutations**

In `logic/tick_logic.py`, find the `DEMIURGE_UNLOCK` handler (around line 6679):

```python
            elif m.mutation_type == MutationType.DEMIURGE_UNLOCK:
                tag = str(m.new_value) if m.new_value else None
                if tag and tag not in state.demiurge.unlocked_domain_tags:
                    state.demiurge.unlocked_domain_tags.append(tag)
```

Add immediately after:

```python
            elif m.mutation_type == MutationType.DEMIURGE_SCRY_MOMENTUM_UPDATE:
                if m.field and m.new_value is not None:
                    state.demiurge.scry_momentum[m.field] = float(m.new_value)
```

- [x] **Step 3: Regression**

```bash
cd /root/demiurge && python3 main.py --autoplay
```

Expected: completes without error (no scry momentum emitted yet, but enum and handler exist).

- [x] **Step 4: Commit**

```bash
git add core/action_core.py logic/tick_logic.py
git commit -m "feat: add DEMIURGE_SCRY_MOMENTUM_UPDATE mutation type and handler"
```

---

## Task 3: Action registry base footprint change

**Files:**
- Modify: `utilities/action_registry.py:321`

- [ ] **Step 1: Lower scry base footprint**

In `utilities/action_registry.py`, find the scry entry (around line 321):

```python
        "fp_overt_miracles": 0.0, "fp_subtle_influence": 0.05,
```

Change to:

```python
        "fp_overt_miracles": 0.0, "fp_subtle_influence": 0.01,
```

- [ ] **Step 2: Regression**

```bash
cd /root/demiurge && python3 main.py --autoplay
```

Expected: completes without error; world-scope scry now only charges 0.01 base fp (lower than before).

- [ ] **Step 3: Commit**

```bash
git add utilities/action_registry.py
git commit -m "feat: lower scry world-scope base footprint from 0.05 to 0.01"
```

---

## Task 4: Momentum growth, dynamic footprint, and per-tick decay

**Files:**
- Modify: `logic/tick_logic.py` (`_process_scry` and `advance()`)

This task wires in all momentum mechanics: growth when scry fires, dynamic footprint based on momentum, and per-tick decay.

- [ ] **Step 1: Add momentum computation at top of _process_scry**

In `logic/tick_logic.py`, inside the `if isinstance(intent, ScryIntent):` block, right after `scope = intent.scope` (line 2917), insert:

```python
            # Momentum key: unique per scope + target.
            _momentum_key = (
                f"{scope.value}:{str(instance.target_id) if instance.target_id else 'None'}"
            )
            _old_momentum = state.demiurge.scry_momentum.get(_momentum_key, 0.0)
            _new_momentum = _old_momentum + (1.0 - _old_momentum) * 0.15
            mutations.append(StateMutation(
                mutation_type=MutationType.DEMIURGE_SCRY_MOMENTUM_UPDATE,
                target_id=state.demiurge.id,
                field=_momentum_key,
                new_value=_new_momentum,
                note=f"Scry momentum: {_old_momentum:.3f} → {_new_momentum:.3f}",
            ))
```

- [ ] **Step 2: Update scope_fp dict and fp_delta to use momentum**

Replace the existing `scope_fp` dict and `fp_delta` block (lines 2919-2933) with:

```python
            scope_fp: dict[ScryScope, float] = {
                ScryScope.WORLD:    0.01,   # base; momentum adds up to 0.09 on top
                ScryScope.SYSTEM:   0.10,
                ScryScope.GALAXY:   0.20,
                ScryScope.UNIVERSE: 0.35,
            }
            fp_delta = scope_fp[scope] - 0.01  # registry base is now 0.01
            if scope == ScryScope.WORLD:
                fp_delta += _new_momentum * 0.09
            if fp_delta > 0.0:
                mutations.append(StateMutation(
                    mutation_type=MutationType.FOOTPRINT_CHANGE,
                    target_id=state.demiurge.id,
                    field="subtle_influence",
                    delta=fp_delta,
                    note=f"Scry ({scope.value}) extra footprint",
                ))
```

- [ ] **Step 3: Add per-tick momentum decay to advance()**

In `logic/tick_logic.py`, in `TickLoop.advance()`, directly before the `# ── Phase 2: Pending action fire` comment (around line 1091), insert:

```python
        # ── Scry momentum decay ──────────────────────────────────────────────
        # Decay runs before Phase 2 so scry's growth reads the already-decayed value.
        _scry_m = state.demiurge.scry_momentum
        for _mk in list(_scry_m):
            _scry_m[_mk] *= 0.95
            if _scry_m[_mk] < 0.001:
                del _scry_m[_mk]

```

- [ ] **Step 4: Regression**

```bash
cd /root/demiurge && python3 main.py --autoplay
```

Expected: completes without error. World-scope scry now emits a momentum mutation each tick it fires, and footprint scales with momentum (starting at 0.01, growing toward 0.10).

- [ ] **Step 5: Commit**

```bash
git add logic/tick_logic.py
git commit -m "feat: asymptotic scry momentum accumulation with decay and dynamic world-scope footprint"
```

---

## Task 5: Momentum discovery bonus

**Files:**
- Modify: `logic/tick_logic.py` (location, civ, species, mortal, and pop discovery sections inside `_process_scry`)

Apply `_new_momentum * 0.25` as an additive bonus to `base` for all entity types (except pops, which use a multiplicative adjustment to `world_scry_base`).

- [ ] **Step 1: Location discovery momentum bonus**

In the location discovery loop (around line 3131), change:

```python
                    base = _depth_chance(delta)
```

to:

```python
                    base = min(0.95, _depth_chance(delta) + _new_momentum * 0.25)
```

(The `in_uncharted` branch already overrides `base` further, so momentum will be overwritten there — that's correct; uncharted bonus dominates.)

Actually: the uncharted check sets `base = min(0.95, base + 0.25)` *after* the `sf = ...` line, not after our new `base` line. So the order is fine — uncharted overrides whatever base we computed.

- [ ] **Step 2: Civilization discovery momentum bonus**

In the civ discovery loop (around line 3172), change:

```python
                base = _depth_chance(delta)
```

to:

```python
                base = min(0.95, _depth_chance(delta) + _new_momentum * 0.25)
```

- [ ] **Step 3: Species discovery momentum bonus**

In the species loop (around line 3205), change:

```python
                base = _depth_chance(delta)
```

to:

```python
                base = min(0.95, _depth_chance(delta) + _new_momentum * 0.25)
```

- [ ] **Step 4: Mortal discovery momentum bonus**

In the mortal loop (around line 3233), change:

```python
                base = _depth_chance(delta)
```

to:

```python
                base = min(0.95, _depth_chance(delta) + _new_momentum * 0.25)
```

- [ ] **Step 5: Pop discovery momentum bonus**

In the pop discovery loop (around line 3276), change:

```python
                world_scry_base = start_vis * 0.5  # Pops revealed at half start_vis
```

to:

```python
                world_scry_base = start_vis * 0.5 * (1.0 + _new_momentum * 0.35)
```

- [ ] **Step 6: Regression**

```bash
cd /root/demiurge && python3 main.py --autoplay
```

Expected: completes without error.

- [ ] **Step 7: Commit**

```bash
git add logic/tick_logic.py
git commit -m "feat: momentum discovery bonus for all entity types in scry"
```

---

## Task 6: PopLocation distance cap at world scope

**Files:**
- Modify: `logic/tick_logic.py` (mortal discovery section, ~line 3232)

- [ ] **Step 1: Cap m_dist at +2 for WORLD scope**

In the mortal discovery loop (around line 3232), change:

```python
                delta = abs(5 - anchor) + m_dist
```

to:

```python
                m_dist_eff = min(m_dist, 2) if scope == ScryScope.WORLD else m_dist
                delta = abs(5 - anchor) + m_dist_eff
```

- [ ] **Step 2: Regression**

```bash
cd /root/demiurge && python3 main.py --autoplay
```

Expected: completes without error. Mortals at PopLocation dist≥3 in a WORLD-scope scry are no longer penalized beyond delta+2 (base ≥ 0.06 before momentum/cascade).

- [ ] **Step 3: Commit**

```bash
git add logic/tick_logic.py
git commit -m "feat: cap PopLocation distance penalty at +2 for WORLD-scope mortal discovery"
```

---

## Task 7: Parent-visibility cascade

**Files:**
- Modify: `logic/tick_logic.py` (mortal section and pop section inside `_process_scry`)

When a mortal's parent pop is visible, discovery is easier. When a pop's parent civ is visible, pop discovery is easier.

- [ ] **Step 1: Mortal → parent pop cascade**

In the mortal discovery section (around line 3233, after computing `base`), insert a parent-pop visibility bonus before the `p = ...` computation:

Replace:
```python
                base = min(0.95, _depth_chance(delta) + _new_momentum * 0.25)
                sf = _spatial_factor(str(mortal.current_location))
                p = max(0.0, min(1.0,
                    (base + _domain_bonus(list(mortal.belief_tags.keys()) + mortal.personal_tags, base)) * sf
                ))
```

With:
```python
                base = min(0.95, _depth_chance(delta) + _new_momentum * 0.25)
                if mortal.pop_id:
                    _parent_pop = state.pops.get(str(mortal.pop_id))
                    if _parent_pop is not None:
                        base = min(0.95, base + _parent_pop.visibility * 0.25)
                sf = _spatial_factor(str(mortal.current_location))
                p = max(0.0, min(1.0,
                    (base + _domain_bonus(list(mortal.belief_tags.keys()) + mortal.personal_tags, base)) * sf
                ))
```

- [ ] **Step 2: Pop → parent civ cascade**

In the pop discovery section (around line 3276, near `world_scry_base`), after the momentum-adjusted `world_scry_base` line, insert a civ-visibility multiplier:

Replace:
```python
                world_scry_base = start_vis * 0.5 * (1.0 + _new_momentum * 0.35)
```

With:
```python
                world_scry_base = start_vis * 0.5 * (1.0 + _new_momentum * 0.35)
                if pop.civilization_id:
                    _parent_civ = state.civilizations.get(str(pop.civilization_id))
                    if _parent_civ is not None:
                        world_scry_base = min(start_vis, world_scry_base * (1.0 + _parent_civ.visibility * 0.30))
```

(Capped at `start_vis` so pops can't be auto-discovered; full civ visibility adds a 30% multiplier to world_scry_base.)

- [ ] **Step 3: Regression**

```bash
cd /root/demiurge && python3 main.py --autoplay
```

Expected: completes without error.

- [ ] **Step 4: Commit**

```bash
git add logic/tick_logic.py
git commit -m "feat: parent-visibility cascade in scry — pop boosts mortal, civ boosts pop"
```

---

## Task 8: Regression + docs update

**Files:**
- Run: regression tests
- Modify: `docs/Mechanics/scry-action.md`

- [ ] **Step 1: Full regression**

```bash
cd /root/demiurge && python3 main.py --autoplay && python3 main.py --autoplay whisper_demo
```

Expected: both strategies complete 50 ticks without error or exception.

- [ ] **Step 2: Update scry-action.md**

Rewrite `docs/Mechanics/scry-action.md` to reflect:

1. **Costs** — world-scope base fp is now 0.01 (not 0.05); actual fp scales with momentum up to ~0.10. Other scopes unchanged.
2. **Momentum** — key format `"{scope}:{target_id_or_None}"`, growth formula `new = old + (1-old)*0.15` per firing, decay `*= 0.95` per tick before action phase, pruned below 0.001. Discovery bonus: `+momentum*0.25` additive to `base` for locations/civs/species/mortals; `*(1+momentum*0.35)` multiplier on `world_scry_base` for pops.
3. **Parent-visibility cascade** — mortal: `+pop.visibility*0.25` additive to base; pop: `*(1+civ.visibility*0.30)` on world_scry_base.
4. **Distance cap** — PopLocation `distance_from_core` capped at +2 delta for WORLD scope only.
5. **Uncharted-galaxy exception** — unchanged.
6. **Probability tables** — update the mortal row at best scope (WORLD, dist=0) from 0.30 to "0.30 + momentum bonus + parent cascade" notation.

- [ ] **Step 3: Commit**

```bash
git add docs/Mechanics/scry-action.md
git commit -m "docs: update scry-action.md for redesign — momentum, dynamic fp, parent cascade, distance cap"
```

---

## Tunable Constants Summary

These can be adjusted after playtesting without structural changes:

| Constant | Location | Default | Effect |
|---|---|---|---|
| Momentum growth rate | `_process_scry` | `0.15` | How fast momentum builds per firing |
| Momentum decay rate | `advance()` | `0.95` | How fast momentum fades per tick when not active |
| Momentum fp multiplier | `_process_scry` | `0.09` | Max extra fp at world scope (total: 0.01 + 0.09 = 0.10) |
| Momentum discovery bonus | all entity sections | `0.25` | Additive to base at full momentum |
| Momentum pop multiplier | pop section | `0.35` | Multiplier on world_scry_base at full momentum |
| Parent pop cascade | mortal section | `0.25` | Additive bonus at full parent pop visibility |
| Parent civ cascade | pop section | `0.30` | Multiplier on world_scry_base at full parent civ visibility |
| Distance cap (world) | mortal section | `2` | Max m_dist penalty at world scope |
