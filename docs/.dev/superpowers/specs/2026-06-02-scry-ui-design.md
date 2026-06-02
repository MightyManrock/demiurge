# Scry UI Design — ScryConfigModal + ScryConfirmModal

**Status:** Approved
**Date:** 2026-06-02
**Companion mechanic plan:** `docs/.dev/superpowers/plans/2026-05-30-scry-redesign.md` (implemented)

---

## Context

Scry mechanics are implemented. The existing UI is a sequential wizard (PickerModal for scope → PickerModal for target) that violates the action-queue design philosophy of one config modal + one confirm modal. This spec replaces it.

---

## Design philosophy

One config modal, one confirm modal. No more, no less.

---

## 1. ScryConfigModal

### Layout

Five regions stacked vertically:

```
┌────────────────────────────────────────────────────────┐
│  Scry                                  (modal title)   │
│  ┌──────────────────────────────────────────────────┐  │
│  │              [  Universe  ]                      │  │
│  │  [  Galaxy  ]   [  System  ]   [  World  ]       │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌─────────────┬──────────────┬───────────────────┐    │
│  │  Galaxy     │  System      │  World            │    │
│  │  ─────────  │  ─────────   │  ─────────        │    │
│  │  Andromeda  │  (blank)     │  (blank)          │    │
│  │  Cygnus Arm │              │                   │    │
│  └─────────────┴──────────────┴───────────────────┘    │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Stop when                                       │  │
│  │  (●) Entities within scope become visible        │  │
│  │  (○) Entities within scope are fully revealed    │  │
│  │                                                  │  │
│  │  [← Back]    [✕ Cancel]    [Continue →]          │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

### Scope chips

Four chips arranged in two rows:
- Row 1 (centered): `Universe`
- Row 2 (left-to-right, aligned above their respective picker columns): `Galaxy` · `System` · `World`

All four chips are **mutually exclusive** — selecting any one deselects the others. Universe is visually separated to signal that it is not tied to any picker, but it participates in the same exclusive group. No chip is selected on open.

Selected chip gets CSS class `scope-chip--active`. Unselected chips get `scope-chip--inactive`.

### Picker columns

Three `LoopingListView` columns side by side: Galaxy, System, World.

**Active vs. dull:**

| Scope selected | Galaxy | System | World |
|---|---|---|---|
| Universe | dull | dull | dull |
| Galaxy | active | dull | dull |
| System | active | active | dull |
| World | active | active | active |

Dull columns receive CSS class `picker-col--dull` (dimmed, pointer-events none). Active columns get `picker-col--active`.

**Population rules (strict left-to-right cascade):**

- Galaxy column: populates on scope selection with all visible galaxies. Only shows entities that pass `is_in_window`.
- System column: **blank** until a galaxy is selected. Populates with visible systems whose parent is the selected galaxy.
- World column: **blank** until a system is selected. Populates with visible worlds whose parent is the selected system.

Right-side pickers never show a "see everything" fallback — they are empty until their parent is chosen.

**"None in scope!":** When a parent IS selected and no visible children exist under it, the picker column displays the static label `None in scope!` instead of a list. Continue stays disabled in this state.

**On galaxy selection change (System/World scope):**
- Repopulate system column from the new galaxy. Clear system selection. Clear world selection.
**On system selection change (World scope):**
- Repopulate world column from the new system. Clear world selection.

**Scope-switch carry-over:**
When the scope chip changes, any selection that remains valid (i.e., its picker column stays active) is preserved. Selections for pickers that become dull are cleared. Example: World → System clears the world selection; galaxy and system selections survive.

### Auto-stop options

A `RadioSet` with two mutually exclusive options. "Entities within scope become visible" is selected by default; it is not possible to deselect both.

- **Entities within scope become visible** — stop when all primary-scope entities have visibility above `ENTITY_VISIBILITY_FLOOR`. This is the existing behavior.
- **Entities within scope are fully revealed** — stop when all primary-scope entities have `visibility >= 1.0`.

### Continue button

Disabled (greyed) until all required selections are made:

| Scope | Required |
|---|---|
| Universe | chip selected (always satisfied) |
| Galaxy | galaxy chosen |
| System | galaxy chosen AND system chosen |
| World | galaxy → system → world all chosen |

Once enabled, styled green (CSS class `continue-ready`).

### Dismissal

- **Back** → dismisses with `BACK`
- **Cancel** → dismisses with `None`
- **Continue** → dismisses with `(scope, target_id_or_None, target_type, stop_when)`
  - `stop_when`: `"visible"` or `"full"`

### Prefill

`ScryConfigModal` accepts an optional `prefill` tuple `(scope, target_id, stop_when)`. When provided, all prior selections are restored so the player can edit them. Used when backing out of the confirm modal.

---

## 2. ScryConfirmModal

Minimal. Displays a plain-language summary and three buttons.

**Text:**
> You have chosen to scry **[target name]** and stop when **[condition]**.

Where:
- Target name: location name for Galaxy/System/World; `"the universe"` for Universe scope.
- Condition: `"entities within scope become visible"` or `"entities within scope are fully revealed"`.

**Buttons:** Back · Cancel · Confirm

- **Back** → dismisses with `False` (caller re-opens config modal with prefill)
- **Cancel** → dismisses with `None`
- **Confirm** → dismisses with `True`

---

## 3. Mechanic change — ScryIntent.stop_when

Add a `stop_when` field to `ScryIntent`:

```python
class ScryIntent(BaseModel):
    scope: ScryScope = ScryScope.WORLD
    stop_when: Literal["visible", "full"] = "visible"
```

Default `"visible"` ensures backward compatibility with any in-progress saves.

In `tick_logic.py`, the `_will_be_visible` predicate used in `_all_visible` currently checks `visibility > ENTITY_VISIBILITY_FLOOR`. When `intent.stop_when == "full"`, replace that check with `visibility >= 1.0` (no mutation bonus — the entity must actually be at full visibility, not just on its way there).

---

## 4. Queuing behavior

Scry is tagged `always_persist` in the action registry. The "once or repeat?" `YesNoModal` is automatically bypassed — it always queues as a repeating ongoing action. No code change needed; this is noted here to make the intent explicit. The `YesNoModal` is retained for other actions (e.g. `harvest_essence`) that still use it.

---

## 5. ui.py change

Replace the existing scry block in `_build_intent` (sequential PickerModal chain) with:

```python
if action_key == "scry":
    prefill = None
    while True:
        result = await app.push_screen_wait(ScryConfigModal(state, prefill=prefill))
        if result is None: return None
        if result == BACK: return BACK
        scope, target_id, target_type, stop_when = result
        confirmed = await app.push_screen_wait(
            ScryConfirmModal(scope, target_id, target_type, stop_when, state)
        )
        if confirmed is None: return None
        if not confirmed:
            prefill = (scope, target_id, stop_when)
            continue
        return ActionInstance(
            action_definition_id=defn.id,
            target_type=target_type,
            target_id=target_id,
            timestamp=state.universe.age.to_float_years(),
            demiurge_id=state.demiurge.id,
            proxius_id=None,
            intent=ScryIntent(scope=scope, stop_when=stop_when),
        )
```

---

## 6. Files affected

| File | Change |
|---|---|
| `ui/modals.py` | Add `ScryConfigModal`, `ScryConfirmModal` |
| `ui/styles.tcss` | Add `.scope-chip--active`, `.scope-chip--inactive`, `.picker-col--active`, `.picker-col--dull` |
| `ui/ui.py` | Replace scry block in `_build_intent` |
| `core/action_core.py` | Add `stop_when` field to `ScryIntent` |
| `logic/tick_logic.py` | Respect `stop_when == "full"` in `_will_be_visible` termination check |
