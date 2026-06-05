# Scry Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the per-tick scry action with a proper ongoing action that sweeps its scope to completion, auto-terminates when all primary-scope entities are visible, and uses action-local momentum instead of a global dict on Demiurge.

**Architecture:** Add `momentum: float` to `OngoingAction`; remove `Demiurge.scry_momentum`; rewrite the scry resolution block in Phase 2 to use a flat-rate + momentum primary sweep (no depth/delta for in-scope entities) plus a separate incidental pass using the old harsh delta math; emit `CLEAR_PENDING_SLOT` when the termination condition is met. Tag scry `always_persist` so it always queues as repeating.

**Tech Stack:** Python 3.11 / Pydantic v2, SQLite, `logic/tick_logic.py` Phase 2 action resolution

---

## File map

| File | Change |
|---|---|
| `core/action_core.py` | Add `momentum` to `OngoingAction`; add `CLEAR_PENDING_SLOT` to `MutationType`; remove `DEMIURGE_SCRY_MOMENTUM_UPDATE` |
| `core/onto_core.py` | Remove `scry_momentum` from `Demiurge` |
| `core/scenario_schema.sql` | Add `momentum` to `ongoing_actions`; remove `scry_momentum` from `demiurge` |
| `utilities/scenario_loader.py` | Load `momentum` on `OngoingAction`; remove `scry_momentum` from `_load_demiurge()` |
| `utilities/scenario_exporter.py` | Export `momentum` on `OngoingAction`; remove `scry_momentum` from `_write_demiurge()` |
| `utilities/action_registry.py` | Change scry tag `can_persist` → `always_persist` |
| `logic/tick_logic.py` | Remove Phase 1 decay; remove Phase 2 scry block (lines 2544–2965); remove `DEMIURGE_SCRY_MOMENTUM_UPDATE` handler; add `CLEAR_PENDING_SLOT` handler; insert new scry block |
| `docs/.dev/Mechanics/scry-action.md` | Rewrite to match new mechanics |

---

## Task 1: Add `momentum` to `OngoingAction` — model, schema, loader, exporter

**Files:**
- Modify: `core/action_core.py:693`
- Modify: `core/scenario_schema.sql` (ongoing_actions table)
- Modify: `utilities/scenario_loader.py:1007` (`_load_ongoing_actions`)
- Modify: `utilities/scenario_exporter.py:750` (`_write_ongoing_actions`)

- [ ] **Step 1: Add field to model**

In `core/action_core.py`, after `repeating: bool = False` (line 692), add:

```python
    momentum: float = 0.0
```

- [ ] **Step 2: Add column to schema**

In `core/scenario_schema.sql`, in the `ongoing_actions` CREATE TABLE, change the last line before `);`:

```sql
    repeating              INTEGER NOT NULL DEFAULT 0,
    momentum               REAL NOT NULL DEFAULT 0.0
);
```

- [ ] **Step 3: Load from DB**

In `utilities/scenario_loader.py`, inside `_load_ongoing_actions()`, in the `OngoingAction(...)` constructor (around line 1023), add after `repeating=bool(row.get("repeating", 0)),`:

```python
            momentum=float(row.get("momentum", 0.0)),
```

- [ ] **Step 4: Export to DB**

In `utilities/scenario_exporter.py`, in `_write_ongoing_actions()` (around line 751), change the INSERT to include `momentum`:

```python
        conn.execute(
            """INSERT INTO ongoing_actions
               (category_key, action_key, action_definition_id, target_type,
                target_id, proxius_id, intent_type, intent_data,
                ticks_active, executed_ticks, successful_ticks, started_at_tick,
                repeating, momentum)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                cat_val,
                oa.action_key,
                str(oa.action_definition_id),
                oa.target_type.value,
                str(oa.target_id) if oa.target_id else None,
                str(oa.proxius_id) if oa.proxius_id else None,
                intent_type,
                intent_data,
                oa.ticks_active,
                oa.executed_ticks,
                oa.successful_ticks,
                oa.started_at_tick,
                int(oa.repeating),
                oa.momentum,
            ),
        )
```

- [ ] **Step 5: Run tests**

```bash
cd /root/demiurge && source venv/bin/activate && pytest -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add core/action_core.py core/scenario_schema.sql utilities/scenario_loader.py utilities/scenario_exporter.py
git commit -m "feat: add momentum field to OngoingAction for scry redesign"
```

---

## Task 2: Add `CLEAR_PENDING_SLOT` mutation type and handler

**Files:**
- Modify: `core/action_core.py:746` (MutationType enum)
- Modify: `logic/tick_logic.py` (`_apply_mutations`)

- [ ] **Step 1: Add to MutationType**

In `core/action_core.py`, after line 746 (`DEMIURGE_SCRY_MOMENTUM_UPDATE`), add:

```python
    CLEAR_PENDING_SLOT     = "clear_pending_slot"    # field=category_key; removes slot from pending_actions
```

- [ ] **Step 2: Add handler in `_apply_mutations`**

In `logic/tick_logic.py`, find the `DEMIURGE_SCRY_MOMENTUM_UPDATE` handler (around line 5950):

```python
            elif m.mutation_type == MutationType.DEMIURGE_SCRY_MOMENTUM_UPDATE:
                    state.demiurge.scry_momentum[m.field] = float(m.new_value)
```

Add after it:

```python
            elif m.mutation_type == MutationType.CLEAR_PENDING_SLOT:
                state.pending_actions.pop(m.field, None)
```

- [ ] **Step 3: Run tests**

```bash
pytest -q
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add core/action_core.py logic/tick_logic.py
git commit -m "feat: add CLEAR_PENDING_SLOT mutation type and handler"
```

---

## Task 3: Tag scry as `always_persist`

**Files:**
- Modify: `utilities/action_registry.py:342`

- [ ] **Step 1: Change tag**

In `utilities/action_registry.py`, in the scry action definition (around line 342), change `"can_persist"` to `"always_persist"`:

```python
        "tags": ["observation", "low_footprint", "intelligence", "always_persist"],
```

This causes the UI to skip the "once or repeat?" prompt and always queue scry as `repeating=True`.

- [ ] **Step 2: Run tests**

```bash
pytest -q
```

- [ ] **Step 3: Commit**

```bash
git add utilities/action_registry.py
git commit -m "feat: scry always queues as repeating (always_persist tag)"
```

---

## Task 4: Remove old scry code from `tick_logic.py`

**Files:**
- Modify: `logic/tick_logic.py`

- [ ] **Step 1: Remove Phase 1 decay block**

Find and delete lines 1055–1061 (the scry_momentum decay loop):

```python
        # ── Scry momentum decay ──────────────────────────────────────────────
        # Runs before Phase 2 so growth in _process_scry reads the decayed value.
        _scry_m = state.demiurge.scry_momentum
        for _mk in list(_scry_m):
            _scry_m[_mk] *= 0.95
            if _scry_m[_mk] < 0.001:
                del _scry_m[_mk]
```

- [ ] **Step 2: Remove Phase 2 scry block**

Find the `if isinstance(intent, ScryIntent):` block starting around line 2544 and delete everything through the final `return mutations, " ".join(parts)` at line 2965. The block to delete starts at:

```python
        # ── Scry ─────────────────────────────────────────
        if isinstance(intent, ScryIntent):
```

and ends at:

```python
            return mutations, " ".join(parts)
```

- [ ] **Step 3: Run autoplay to confirm no crash**

```bash
python main.py --autoplay 2>&1 | tail -20
```

Expected: 50 ticks complete. Scry action queued in autoplay strategy will fire but produce no effect (no intent handler for ScryIntent yet). If autoplay strategy queues scry, ensure it doesn't crash — it should silently produce `mutations=[], narrative=""`.

- [ ] **Step 4: Commit**

```bash
git add logic/tick_logic.py
git commit -m "refactor: remove old scry resolution code (Phase 1 decay + Phase 2 block)"
```

---

## Task 5: Remove `scry_momentum` from Demiurge and clean up mutation type

**Files:**
- Modify: `core/onto_core.py`
- Modify: `core/scenario_schema.sql`
- Modify: `utilities/scenario_loader.py`
- Modify: `utilities/scenario_exporter.py`
- Modify: `core/action_core.py`
- Modify: `logic/tick_logic.py`

- [ ] **Step 1: Remove field from Demiurge model**

In `core/onto_core.py`, remove these two lines from the `Demiurge` class:

```python
    scry_momentum: dict[str, float] = Field(default_factory=dict)
    # "{scope}:{target_id_or_None}" → [0, 1] accumulation; decays when scry not active.
```

- [ ] **Step 2: Remove column from schema**

In `core/scenario_schema.sql`, in the `demiurge` CREATE TABLE, remove:

```sql
    scry_momentum             TEXT NOT NULL DEFAULT '{}'   -- JSON {"scope:target": float}
```

- [ ] **Step 3: Remove from loader**

In `utilities/scenario_loader.py`, in `_load_demiurge()` (around line 933), remove:

```python
        scry_momentum=_j(row.get("scry_momentum", "{}")),
```

- [ ] **Step 4: Remove from exporter**

In `utilities/scenario_exporter.py`, in `_write_demiurge()` (around lines 583–615):

Remove `scry_momentum` from the column list in the INSERT string.

Remove `_j(d.scry_momentum),` from the values tuple.

Decrement the `VALUES (?, ..., ?)` placeholder count by one to match.

- [ ] **Step 5: Remove `DEMIURGE_SCRY_MOMENTUM_UPDATE` from MutationType**

In `core/action_core.py`, remove:

```python
    DEMIURGE_SCRY_MOMENTUM_UPDATE = "demiurge_scry_momentum_update"  # field=key, new_value=float
```

- [ ] **Step 6: Remove old handler from `_apply_mutations`**

In `logic/tick_logic.py`, remove the handler block at around line 5950:

```python
            elif m.mutation_type == MutationType.DEMIURGE_SCRY_MOMENTUM_UPDATE:
                    state.demiurge.scry_momentum[m.field] = float(m.new_value)
```

- [ ] **Step 7: Run tests and autoplay**

```bash
pytest -q && python main.py --autoplay 2>&1 | tail -5
```

Expected: tests pass, autoplay completes 50 ticks.

- [ ] **Step 8: Commit**

```bash
git add core/onto_core.py core/scenario_schema.sql utilities/scenario_loader.py utilities/scenario_exporter.py core/action_core.py logic/tick_logic.py
git commit -m "refactor: remove scry_momentum from Demiurge and DEMIURGE_SCRY_MOMENTUM_UPDATE mutation"
```

---

## Task 6: Implement new primary sweep and termination check

**Files:**
- Modify: `logic/tick_logic.py` — insert new scry block where the old one was removed

- [ ] **Step 1: Insert new scry block**

In `logic/tick_logic.py`, in `_resolve_intent_mutations()`, after the action blocks that come before `# ── Scry` (restore the comment as a landmark), insert:

```python
        # ── Scry ─────────────────────────────────────────────────────────
        if isinstance(intent, ScryIntent):
            scope = intent.scope
            target_id_str = str(instance.target_id) if instance.target_id else None

            # Momentum: read and update directly on the OngoingAction instance.
            _own_oa: Optional[OngoingAction] = next(
                (oa for oa in state.pending_actions.values()
                 if isinstance(oa.intent, ScryIntent)
                 and oa.intent.scope == scope
                 and oa.target_id == instance.target_id),
                None,
            )
            _old_momentum = _own_oa.momentum if _own_oa is not None else 0.0
            _new_momentum = _old_momentum + (1.0 - _old_momentum) * 0.15
            if _own_oa is not None:
                _own_oa.momentum = _new_momentum

            # Footprint cost
            scope_fp: dict[ScryScope, float] = {
                ScryScope.WORLD:    0.01 + _new_momentum * 0.09,
                ScryScope.SYSTEM:   0.10,
                ScryScope.GALAXY:   0.20,
                ScryScope.UNIVERSE: 0.35,
            }
            mutations.append(StateMutation(
                mutation_type=MutationType.FOOTPRINT_CHANGE,
                target_id=state.demiurge.id,
                field="subtle_influence",
                delta=scope_fp[scope],
                note=f"Scry ({scope.value}) footprint",
            ))

            # Essence cost (galaxy/universe only)
            scope_essence: dict[ScryScope, float] = {
                ScryScope.WORLD: 0.0, ScryScope.SYSTEM: 0.0,
                ScryScope.GALAXY: 3.0, ScryScope.UNIVERSE: 5.0,
            }
            if scope_essence[scope] > 0.0:
                mutations.append(StateMutation(
                    mutation_type=MutationType.ESSENCE_CHANGE,
                    target_id=state.demiurge.id,
                    field="actual",
                    delta=-scope_essence[scope],
                    note=f"Scry ({scope.value}) essence cost",
                ))

            # Spatial infrastructure (kept for incidental pass in Task 7)
            _GALAXY_SCALE = 1000.0
            _SPATIAL_SCALE = 8.0

            def _effective_pos(loc_id: str) -> tuple[float, float, float]:
                loc = state.locations.get(loc_id)
                if loc is None:
                    return (0.0, 0.0, 0.0)
                cx, cy, cz = loc.coordinates.x, loc.coordinates.y, loc.coordinates.z
                if loc.parent_id is not None:
                    px, py, pz = _effective_pos(str(loc.parent_id))
                    return (px * _GALAXY_SCALE + cx, py * _GALAXY_SCALE + cy, pz * _GALAXY_SCALE + cz)
                return (cx, cy, cz)

            _focus_pos: Optional[tuple[float, float, float]] = None
            if scope in (ScryScope.WORLD, ScryScope.SYSTEM, ScryScope.GALAXY) and instance.target_id:
                target_loc = state.locations.get(str(instance.target_id))
                if target_loc is not None:
                    if scope == ScryScope.WORLD and target_loc.parent_id is not None:
                        _focus_pos = _effective_pos(str(target_loc.parent_id))
                    else:
                        _focus_pos = _effective_pos(str(instance.target_id))

            def _spatial_factor(candidate_loc_id: str) -> float:
                if _focus_pos is None:
                    return 1.0
                loc = state.locations.get(candidate_loc_id)
                if loc is None:
                    return 1.0
                if loc.location_type not in ("galaxy", "system"):
                    ref_id = str(loc.parent_id) if loc.parent_id else candidate_loc_id
                else:
                    ref_id = candidate_loc_id
                rx, ry, rz = _effective_pos(ref_id)
                fx, fy, fz = _focus_pos
                dist = math.sqrt((rx - fx) ** 2 + (ry - fy) ** 2 + (rz - fz) ** 2)
                return 1.0 / (1.0 + dist / _SPATIAL_SCALE)

            dreg = self._domain_registry
            affiliated = state.demiurge.affiliated_domains

            def _domain_bonus(entity_tags: list[str], base: float) -> float:
                if not dreg or not affiliated or not entity_tags:
                    return 0.0
                total = 0.0
                for etag in entity_tags:
                    for atag in affiliated:
                        try:
                            total += max(0.0, dreg.similarity(etag, atag)) * 0.05
                        except Exception:
                            pass
                bonus_scale = min(1.0, base / 0.55)
                return min(0.20, total) * bonus_scale

            # Primary sweep helpers
            _BASE = 0.45
            _MOM  = 0.35

            def _scry_p(tags: list[str]) -> float:
                return min(0.95, _BASE + _new_momentum * _MOM + _domain_bonus(tags, _BASE))

            def _scry_new_vis(cur_vis: float) -> float:
                return max(cur_vis, _BASE + _new_momentum * _MOM)

            # Narrative accumulators
            discovered_locs: list[str] = []
            discovered_civs: list[str] = []
            discovered_sp:   list[str] = []
            discovered_mort: list[str] = []
            discovered_pops: list[tuple] = []
            parts: list[str] = []

            # ── Build primary location set ────────────────────────────────
            if scope == ScryScope.UNIVERSE:
                primary_locs = [
                    (lid, loc) for lid, loc in state.locations.items()
                    if loc.location_type == "galaxy" and not getattr(loc, "pinned", False)
                ]
            elif scope == ScryScope.GALAXY and target_id_str:
                primary_locs = [
                    (lid, loc) for lid, loc in state.locations.items()
                    if loc.location_type == "system"
                    and str(loc.parent_id) == target_id_str
                    and not getattr(loc, "pinned", False)
                ]
            elif scope == ScryScope.SYSTEM and target_id_str:
                primary_locs = [
                    (lid, loc) for lid, loc in state.locations.items()
                    if loc.location_type not in ("galaxy", "system")
                    and str(loc.parent_id) == target_id_str
                    and not getattr(loc, "pinned", False)
                ]
            else:
                primary_locs = []

            _primary_loc_ids: set[str] = {lid for lid, _ in primary_locs}

            # ── Primary location sweep (UNIVERSE / GALAXY / SYSTEM) ───────
            for lid, loc in primary_locs:
                tags = (
                    list(getattr(loc, "domain_expression", {}).keys())
                    + list(getattr(loc, "traits", []))
                )
                p = _scry_p(tags)
                if is_in_window(loc):
                    mutations.append(StateMutation(
                        mutation_type=MutationType.ENTITY_VISIBILITY,
                        target_id=UUID(lid), field="visibility",
                        new_value=min(1.0, loc.visibility + p * 0.3),
                        note=f"Scry ({scope.value}): {loc.name} refreshed",
                    ))
                elif rng.random() < p:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.ENTITY_VISIBILITY,
                        target_id=UUID(lid), field="visibility",
                        new_value=_scry_new_vis(loc.visibility),
                        note=f"Scry ({scope.value}): {loc.name} sighted",
                    ))
                    discovered_locs.append(loc.name)

            # ── WORLD scope: sweep pops, mortals, civs, species ───────────
            _world_pop_loc_ids: set[str] = set()
            _civs_at_world: set[str] = set()
            if scope == ScryScope.WORLD and target_id_str:
                _world_pop_loc_ids = {
                    lid for lid, loc in state.locations.items()
                    if isinstance(loc, PopLocation)
                    and str(loc.parent_id) == target_id_str
                    and not getattr(loc, "pinned", False)
                }
                _primary_loc_ids |= _world_pop_loc_ids

                # PopLocations
                for lid in _world_pop_loc_ids:
                    loc = state.locations[lid]
                    p = _scry_p([])
                    if is_in_window(loc):
                        mutations.append(StateMutation(
                            mutation_type=MutationType.ENTITY_VISIBILITY,
                            target_id=UUID(lid), field="visibility",
                            new_value=min(1.0, loc.visibility + p * 0.3),
                            note="Scry (world): PopLocation refreshed",
                        ))
                    elif rng.random() < p:
                        mutations.append(StateMutation(
                            mutation_type=MutationType.ENTITY_VISIBILITY,
                            target_id=UUID(lid), field="visibility",
                            new_value=_scry_new_vis(loc.visibility),
                            note="Scry (world): PopLocation sighted",
                        ))

                # Pops
                _PROMINENT = {"elite", "scholar", "warrior"}
                for pid, pop in state.pops.items():
                    if pop.pinned or str(pop.current_location) not in _world_pop_loc_ids:
                        continue
                    tags = list(pop.dominant_beliefs.keys()) if hasattr(pop, "dominant_beliefs") else []
                    p = _scry_p(tags)
                    if pop.social_class and pop.social_class.value in _PROMINENT:
                        p = min(0.95, p * 1.3)
                    if is_in_window(pop):
                        mutations.append(StateMutation(
                            mutation_type=MutationType.POP_VISIBILITY,
                            target_id=UUID(pid), field="visibility",
                            new_value=min(1.0, pop.visibility + p * 0.3),
                            note="Scry (world): Pop refreshed",
                        ))
                    elif rng.random() < p:
                        mutations.append(StateMutation(
                            mutation_type=MutationType.POP_VISIBILITY,
                            target_id=UUID(pid), field="visibility",
                            new_value=_scry_new_vis(pop.visibility),
                            note="Scry (world): Pop sighted",
                        ))
                        civ = state.civilizations.get(str(pop.civilization_id)) if pop.civilization_id else None
                        discovered_pops.append((pid, pop, civ))

                # Mortals
                for mid, mortal in state.mortals.items():
                    if mortal.status == MortalStatus.DECEASED or mortal.pinned:
                        continue
                    if str(mortal.current_location) not in _world_pop_loc_ids:
                        continue
                    tags = list(mortal.belief_tags.keys()) + mortal.personal_tags
                    p = _scry_p(tags)
                    if is_in_window(mortal):
                        mutations.append(StateMutation(
                            mutation_type=MutationType.MORTAL_VISIBILITY,
                            target_id=UUID(mid), field="visibility",
                            new_value=min(1.0, mortal.visibility + p * 0.3),
                            note=f"Scry (world): {mortal.name} refreshed",
                        ))
                    elif rng.random() < p:
                        mutations.append(StateMutation(
                            mutation_type=MutationType.MORTAL_VISIBILITY,
                            target_id=UUID(mid), field="visibility",
                            new_value=_scry_new_vis(mortal.visibility),
                            note=f"Scry (world): {mortal.name} sighted",
                        ))
                        discovered_mort.append(mortal.name)

                # Civs with pops at this world
                _civs_at_world = {
                    str(pop.civilization_id) for pop in state.pops.values()
                    if pop.civilization_id
                    and str(pop.current_location) in _world_pop_loc_ids
                }
                for cid in _civs_at_world:
                    civ = state.civilizations.get(cid)
                    if civ is None or civ.pinned or is_wild_civ(civ):
                        continue
                    tags = list(civ.dominant_beliefs.keys())
                    p = _scry_p(tags)
                    if is_in_window(civ):
                        mutations.append(StateMutation(
                            mutation_type=MutationType.ENTITY_VISIBILITY,
                            target_id=UUID(cid), field="visibility",
                            new_value=min(1.0, civ.visibility + p * 0.3),
                            note=f"Scry (world): {civ.name} refreshed",
                        ))
                    elif rng.random() < p:
                        mutations.append(StateMutation(
                            mutation_type=MutationType.ENTITY_VISIBILITY,
                            target_id=UUID(cid), field="visibility",
                            new_value=_scry_new_vis(civ.visibility),
                            note=f"Scry (world): {civ.name} sighted",
                        ))
                        discovered_civs.append(civ.name)

                # Species originating at this world
                for sid, sp in state.species.items():
                    if sp.pinned or str(sp.origin_world_id) != target_id_str:
                        continue
                    p = _scry_p(sp.domain_tags)
                    if is_in_window(sp):
                        mutations.append(StateMutation(
                            mutation_type=MutationType.ENTITY_VISIBILITY,
                            target_id=UUID(sid), field="visibility",
                            new_value=min(1.0, sp.visibility + p * 0.3),
                            note=f"Scry (world): {sp.name} refreshed",
                        ))
                    elif rng.random() < p:
                        mutations.append(StateMutation(
                            mutation_type=MutationType.ENTITY_VISIBILITY,
                            target_id=UUID(sid), field="visibility",
                            new_value=_scry_new_vis(sp.visibility),
                            note=f"Scry (world): {sp.name} sighted",
                        ))
                        discovered_sp.append(sp.name)

            # ── Termination check ─────────────────────────────────────────
            # Map entity IDs → new_value from visibility mutations emitted this tick.
            _vis_muts: dict[str, float] = {
                str(m.target_id): float(m.new_value)
                for m in mutations
                if m.mutation_type in (
                    MutationType.ENTITY_VISIBILITY,
                    MutationType.POP_VISIBILITY,
                    MutationType.MORTAL_VISIBILITY,
                )
                and m.new_value is not None
            }

            def _will_be_visible(eid: str, cur_vis: float) -> bool:
                return (
                    cur_vis > ENTITY_VISIBILITY_FLOOR
                    or _vis_muts.get(eid, 0.0) > ENTITY_VISIBILITY_FLOOR
                )

            _has_primary = bool(primary_locs) or bool(_world_pop_loc_ids)
            _all_visible = _has_primary and all(
                _will_be_visible(lid, loc.visibility) for lid, loc in primary_locs
            )

            if _all_visible and scope == ScryScope.WORLD and target_id_str:
                _all_visible = (
                    all(
                        _will_be_visible(lid, state.locations[lid].visibility)
                        for lid in _world_pop_loc_ids
                    )
                    and all(
                        _will_be_visible(pid, pop.visibility)
                        for pid, pop in state.pops.items()
                        if not pop.pinned
                        and str(pop.current_location) in _world_pop_loc_ids
                    )
                    and all(
                        _will_be_visible(mid, mortal.visibility)
                        for mid, mortal in state.mortals.items()
                        if mortal.status != MortalStatus.DECEASED
                        and not mortal.pinned
                        and str(mortal.current_location) in _world_pop_loc_ids
                    )
                    and all(
                        _will_be_visible(cid, civ.visibility)
                        for cid in _civs_at_world
                        for civ in [state.civilizations.get(cid)]
                        if civ and not civ.pinned and not is_wild_civ(civ)
                    )
                    and all(
                        _will_be_visible(sid, sp.visibility)
                        for sid, sp in state.species.items()
                        if not sp.pinned and str(sp.origin_world_id) == target_id_str
                    )
                )

            if _all_visible and _own_oa is not None:
                _own_cat = next(
                    (k for k, oa in state.pending_actions.items() if oa is _own_oa),
                    None,
                )
                if _own_cat is not None:
                    _tgt_loc = state.locations.get(target_id_str or "")
                    tgt_name = _tgt_loc.name if _tgt_loc is not None else scope.value
                    mutations.append(StateMutation(
                        mutation_type=MutationType.CLEAR_PENDING_SLOT,
                        target_id=state.demiurge.id,
                        field=_own_cat,
                        note=f"Scry of {tgt_name} complete",
                    ))
                    parts.append(
                        f"Scry of {tgt_name} complete — all entities within scope have been revealed."
                    )

            # ── Narrative ─────────────────────────────────────────────────
            if discovered_locs:
                parts.append(f"Locations sighted: {', '.join(discovered_locs)}.")
            if discovered_civs:
                parts.append(f"Civilizations sighted: {', '.join(discovered_civs)}.")
            if discovered_sp:
                parts.append(f"Species sighted: {', '.join(discovered_sp)}.")
            if discovered_mort:
                parts.append(f"Mortals sighted: {', '.join(discovered_mort)}.")
            if discovered_pops:
                formatted = self._format_pop_entries_with_links(discovered_pops)
                parts.append(f"Pops sighted: {', '.join(formatted)}.")

            return mutations, " ".join(parts)
```

- [ ] **Step 2: Run autoplay**

```bash
python main.py --autoplay 2>&1 | tail -20
```

Expected: 50 ticks complete without errors. If a scry action is in the default strategy, you should see discovery narrative in the output.

- [ ] **Step 3: Run tests**

```bash
pytest -q
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add logic/tick_logic.py
git commit -m "feat: implement new scry primary sweep and termination check"
```

---

## Task 7: Implement incidental discovery pass

The incidental pass runs after the primary sweep (before the narrative block) and discovers entities outside the primary scope using the existing harsh delta math plus `_spatial_factor`. This is appended inside the `if isinstance(intent, ScryIntent):` block, after the termination check and before the narrative block.

**Files:**
- Modify: `logic/tick_logic.py` — insert incidental pass between termination and narrative

- [ ] **Step 1: Insert incidental pass**

Inside the scry block, find the `# ── Narrative` comment and insert before it:

```python
            # ── Incidental discovery pass ─────────────────────────────────
            # Candidates: entities outside the primary set that are related
            # to already-visible entities or near the target by coordinates.
            # Uses the existing harsh depth/delta math — no momentum bonus.
            _eligible_locs: set[str] = {
                lid for lid, loc in state.locations.items() if is_in_window(loc)
            }
            # Include locations just discovered this tick
            for _m in mutations:
                if (
                    _m.mutation_type == MutationType.ENTITY_VISIBILITY
                    and _m.new_value is not None
                    and float(_m.new_value) > ENTITY_VISIBILITY_FLOOR
                ):
                    _eligible_locs.add(str(_m.target_id))

            scope_anchor: dict[ScryScope, int] = {
                ScryScope.WORLD: 3, ScryScope.SYSTEM: 2,
                ScryScope.GALAXY: 1, ScryScope.UNIVERSE: 0,
            }
            _anchor = scope_anchor[scope]

            def _depth_chance(delta: int) -> float:
                if delta == 0: return 0.85
                if delta == 1: return 0.55
                if delta == 2: return 0.30
                if delta == 3: return 0.06
                if delta == 4: return 0.02
                return 0.005

            # Incidental location pass (entities not in primary set)
            for lid, loc in state.locations.items():
                if lid in _primary_loc_ids or getattr(loc, "pinned", False) or is_in_window(loc):
                    continue
                depth = (
                    1 if loc.location_type == "galaxy"
                    else 2 if loc.location_type == "system"
                    else 3
                )
                if depth > 1 and (loc.parent_id is None or str(loc.parent_id) not in _eligible_locs):
                    continue
                delta = abs(depth - _anchor)
                base = _depth_chance(delta)
                sf = _spatial_factor(lid)
                expr_tags = (
                    list(getattr(loc, "domain_expression", {}).keys())
                    + list(getattr(loc, "traits", []))
                )
                p = max(0.0, min(1.0, (base + _domain_bonus(expr_tags, base)) * sf))
                if rng.random() < p:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.ENTITY_VISIBILITY,
                        target_id=UUID(lid), field="visibility",
                        new_value=max(loc.visibility, base),
                        note=f"Scry ({scope.value}) incidental: {loc.name} sighted",
                    ))
                    discovered_locs.append(f"{loc.name} [incidental]")

            # Incidental mortal pass via pop_milieu (the pop_milieu fix)
            # Mortals outside the primary world scope whose milieu Pop is visible.
            for mid, mortal in state.mortals.items():
                if mortal.status == MortalStatus.DECEASED or mortal.pinned:
                    continue
                if str(mortal.current_location) in _world_pop_loc_ids:
                    continue  # already handled in primary sweep
                if is_in_window(mortal):
                    continue
                _milieu_pop = (
                    state.pops.get(str(mortal.pop_milieu)) if mortal.pop_milieu else None
                )
                if _milieu_pop is None or not is_in_window(_milieu_pop):
                    continue
                # Milieu pop is visible: soft delta-1 if clearly visible, else normal delta
                if _milieu_pop.visibility > 0.5:
                    _m_delta = 1
                else:
                    _m_loc = state.locations.get(str(mortal.current_location))
                    _m_dist = _m_loc.distance_from_core if isinstance(_m_loc, PopLocation) else 0
                    _m_delta = abs(5 - _anchor) + min(_m_dist, 2)
                base = _depth_chance(_m_delta)
                tags = list(mortal.belief_tags.keys()) + mortal.personal_tags
                p = max(0.0, min(1.0, base + _domain_bonus(tags, base)))
                if rng.random() < p:
                    mutations.append(StateMutation(
                        mutation_type=MutationType.MORTAL_VISIBILITY,
                        target_id=UUID(mid), field="visibility",
                        new_value=max(mortal.visibility, base),
                        note=f"Scry ({scope.value}) incidental: {mortal.name} sighted via milieu",
                    ))
                    discovered_mort.append(f"{mortal.name} [incidental]")
```

- [ ] **Step 2: Run autoplay**

```bash
python main.py --autoplay 2>&1 | tail -20
```

Expected: 50 ticks complete. Incidental discoveries may appear alongside primary ones.

- [ ] **Step 3: Run tests**

```bash
pytest -q
```

- [ ] **Step 4: Commit**

```bash
git add logic/tick_logic.py
git commit -m "feat: add incidental discovery pass to scry (pop_milieu fix + proximity)"
```

---

## Task 8: Migrate saves, update docs, final verification

**Files:**
- Modify: `docs/.dev/Mechanics/scry-action.md`

- [ ] **Step 1: Migrate existing scenario DBs**

```bash
python main.py --rebuild --scenario
```

Expected: migrator runs a load→re-export round-trip on all `scenarios/*.db`, bringing them to the new schema (no `scry_momentum` column, `momentum` column on `ongoing_actions`).

- [ ] **Step 2: Rewrite scry-action.md**

Replace the full contents of `docs/.dev/Mechanics/scry-action.md` with:

```markdown
# Scry Action

Scry is an ongoing action that sweeps its target scope to completion and auto-terminates once every entity within the primary scope is visible.

## Queuing

Scry always queues as a repeating ongoing action (`always_persist` tag). The "once or repeat?" prompt is skipped. Cancel explicitly to stop.

## Scopes and primary entities

| Scope | Target | Primary entities (guaranteed sweep) |
|---|---|---|
| UNIVERSE | (none) | All Galaxy locations |
| GALAXY | A galaxy | All System locations in that galaxy |
| SYSTEM | A system | All non-system child locations in that system |
| WORLD | A world/SignificantLocation | All PopLocations, Pops, NotableMortals, Civs, and Species at target |

## Momentum

Each tick the action fires, momentum increases: `new = old + (1 − old) × 0.15`. Momentum resets to 0 if the action is cancelled. Momentum is stored directly on the `OngoingAction` instance.

## Discovery probability (primary entities)

```
p = 0.45 + (momentum × 0.35) + domain_bonus
```

- `domain_bonus`: up to +0.20 from similarity between entity tags and Demiurge's affiliated domains; scaled down when base is already high.
- No depth/delta penalties for entities within primary scope.
- Already-visible entities receive a boost: `visibility += p × 0.3` (capped at 1.0).
- On discovery: `visibility = max(current, 0.45 + momentum × 0.35)`.

## Termination

After each tick's sweep, the action checks whether all primary-scope entities are above `ENTITY_VISIBILITY_FLOOR` (including entities just discovered this tick). If all are visible, the action auto-resolves and a log entry fires: "Scry of [Target] complete".

Newly-spawned entities at the target join the primary set immediately; scry will not complete until they are found.

## Incidental discovery

A separate pass runs after the primary sweep, finding entities outside the primary scope. Two candidate pools:

1. **Relationship-adjacent**: locations whose parent is in-window, and NotableMortals whose `pop_milieu` Pop is visible.
2. **Coordinate-adjacent**: locations near the target by effective position.

Incidentals use the old harsh delta math (depth anchor + distance penalty + spatial falloff) with no momentum bonus. A mortal whose `pop_milieu` Pop has visibility > 0.5 is treated as depth-delta 1 (visible crowd).

## Footprint costs

| Scope | Subtle influence footprint |
|---|---|
| WORLD | 0.01 + momentum × 0.09 |
| SYSTEM | 0.10 |
| GALAXY | 0.20 |
| UNIVERSE | 0.35 |

GALAXY and UNIVERSE also cost 3 and 5 Essence respectively per tick.
```

- [ ] **Step 3: Final autoplay + tests**

```bash
pytest -q && python main.py --autoplay 2>&1 | tail -10
```

Expected: tests pass, 50 ticks complete.

- [ ] **Step 4: Commit all**

```bash
git add docs/.dev/Mechanics/scry-action.md
git commit -m "docs: rewrite scry-action.md for redesigned sweep mechanics"
```
