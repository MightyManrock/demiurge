> **Status:** active
> **TO-DO ref:** Soft queue / pending slot system
> **Last updated:** 2026-05-23 (rev 1)

## Goal

Unify `action_queue` (transient list) and `ongoing_actions` (persistent dict) into a single `pending_actions: dict[str, OngoingAction]` — one slot per `ActionCategory`. A `repeating: bool` flag on `OngoingAction` distinguishes one-shot queued actions (fire once, then clear) from standing orders (fire each tick while ready). This makes the programmatic reality match the conceptual model: all actions are "queued"; ongoing actions are just actions that re-queue themselves.

---

## Design summary

- **One pending slot per category.** `state.pending_actions: dict[str, OngoingAction]` replaces both `state.action_queue` and `state.ongoing_actions`.
- **`repeating: bool = False`** on `OngoingAction`. `False` = fire once and clear the slot. `True` = keep the slot after firing (current "ongoing" behaviour).
- **Tick fires in category priority order.** Each tick, pending actions are attempted in `ActionCategory` display order (Direct → Overt → Subtle → Proxius → Observe → Herald → Luminary → Underreal → Refine). Cooldown still gates firing; queuing into a cooling slot is now always allowed.
- **Target validation every tick.** Before firing, check that the pending action's target still exists and is valid. Cancel invalid slots with a narrative note.
- **UI: no essence hard-block at queue time.** Essence is checked at fire time (same as ongoing actions today). The "make persistent?" flow is replaced with "make repeating?"
- **Cooling category click → smart modal.** Empty slot: open browser. Occupied slot (regardless of cooldown state): `CategoryPendingModal` with four options.
- **Phase 5 — override-once-then-resume.** A `pending_resume` slot lets the player fire a one-off action and automatically restore the standing order afterward.

**Must be done on a feature branch.** This refactor changes every path that writes to the action queue mid-implementation; the game is non-functional between phases.

---

## Phases

### Phase 1: Data model + persistence

**1a — Add `repeating` to `OngoingAction`; rename field in `SimulationState`** ✓ _not started_

Files:
- `core/action_core.py` — add `repeating: bool = False` to `OngoingAction`; update docstring
- `logic/tick_logic.py` — rename `ongoing_actions` → `pending_actions` in `SimulationState`; rename the comment block; remove `action_queue` from `SimulationState`
- `core/scenario_schema.sql` — add `repeating INTEGER NOT NULL DEFAULT 0` column to `ongoing_actions` table
- `utilities/scenario_loader.py` — load `repeating` in `_load_ongoing_actions()`; assign to `state.pending_actions`
- `utilities/scenario_exporter.py` — write `repeating` in `_write_ongoing_actions()`; read from `state.pending_actions`
- `autoplay/strategies/_helpers.py` — update `queue()` to write `OngoingAction` into `state.pending_actions[cat_key]` instead of appending to `state.action_queue`

**`core/action_core.py` change — `OngoingAction`:**
```python
class OngoingAction(BaseModel):
    """
    A pending action occupying one category slot.
    repeating=False: fires once, then the slot is cleared.
    repeating=True: slot is kept after firing (standing order).
    Keyed by ActionCategory.value in SimulationState.pending_actions.
    """
    action_key: str
    action_definition_id: UUID
    target_type: TargetType
    target_id: Optional[UUID] = None
    proxius_id: Optional[UUID] = None
    intent: Optional[ActionIntent] = None
    ticks_active: int = 0
    executed_ticks: int = 0
    successful_ticks: int = 0
    started_at_tick: int = 0
    repeating: bool = False
```

**`logic/tick_logic.py` — `SimulationState` field changes:**

Remove:
```python
# Queued actions waiting to be processed this tick
action_queue: list["ActionInstance"] = Field(default_factory=list)
```

Replace:
```python
# Persistent actions that auto-execute each tick.
# Keyed by ActionCategory.value; appended to action_queue before Phase 2.
# Manually queued actions in the same category take priority and block the ongoing one.
ongoing_actions: dict[str, OngoingAction] = Field(default_factory=dict)
```
With:
```python
# One pending slot per ActionCategory.
# repeating=False: fire once, then clear. repeating=True: keep after firing.
# Keyed by ActionCategory.value.
pending_actions: dict[str, OngoingAction] = Field(default_factory=dict)
```

**`core/scenario_schema.sql` change:**
```sql
CREATE TABLE IF NOT EXISTS ongoing_actions (
    category_key           TEXT PRIMARY KEY,
    action_key             TEXT NOT NULL,
    action_definition_id   TEXT NOT NULL,
    target_type            TEXT NOT NULL,
    target_id              TEXT,
    proxius_id             TEXT,
    intent_type            TEXT,
    intent_data            TEXT,
    ticks_active           INTEGER NOT NULL DEFAULT 0,
    executed_ticks         INTEGER NOT NULL DEFAULT 0,
    successful_ticks       INTEGER NOT NULL DEFAULT 0,
    started_at_tick        INTEGER NOT NULL DEFAULT 0,
    repeating              INTEGER NOT NULL DEFAULT 0
);
```

**`utilities/scenario_loader.py` — `_load_ongoing_actions()` change:**
```python
out[row["category_key"]] = OngoingAction(
    action_key=row["action_key"],
    action_definition_id=UUID(row["action_definition_id"]),
    target_type=TargetType(row["target_type"]),
    target_id=_uuid(row.get("target_id")),
    proxius_id=_uuid(row.get("proxius_id")),
    intent=intent,
    ticks_active=row["ticks_active"],
    executed_ticks=row["executed_ticks"],
    successful_ticks=row.get("successful_ticks", 0),
    started_at_tick=row["started_at_tick"],
    repeating=bool(row.get("repeating", 0)),
)
```

Assign result to `state.pending_actions` in the main load call (find the assignment in the loader's `load()` function and rename `ongoing_actions=` → `pending_actions=`).

**`utilities/scenario_exporter.py` — `_write_ongoing_actions()` change:**
```python
def _write_ongoing_actions(conn, state: SimulationState):
    for cat_val, oa in state.pending_actions.items():
        intent_type = type(oa.intent).__name__ if oa.intent is not None else None
        intent_data = oa.intent.model_dump_json() if oa.intent is not None else None
        conn.execute(
            """INSERT INTO ongoing_actions
               (category_key, action_key, action_definition_id, target_type,
                target_id, proxius_id, intent_type, intent_data,
                ticks_active, executed_ticks, successful_ticks, started_at_tick,
                repeating)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            ),
        )
```

**`autoplay/strategies/_helpers.py` — `queue()` change:**
```python
def queue(loop: TickLoop, state: SimulationState, key: str,
          target_type: TargetType, target_id, intent=None, proxius_id=None,
          repeating: bool = False):
    defn = loop._action_library[key]
    state.pending_actions[defn.category.value] = OngoingAction(
        action_key=key,
        action_definition_id=defn.id,
        target_type=target_type,
        target_id=UUID(str(target_id)) if target_id else None,
        proxius_id=UUID(str(proxius_id)) if proxius_id else None,
        intent=intent,
        repeating=repeating,
        ticks_active=0,
        executed_ticks=0,
        successful_ticks=0,
        started_at_tick=state.tick_number,
    )
```

Also update the import at the top of `_helpers.py` to import `OngoingAction` from `core.action_core` (currently it doesn't need it; after this change it does).

Run autoplay regression after 1a:
```bash
cd /root/demiurge && source bin/activate
python main.py --autoplay wardens_compact
python main.py --autoplay ledger_and_ash
```
Expected: both complete 50 ticks without errors. (Actions will not fire yet if tick logic still references old names — fix any `AttributeError` on `state.action_queue` / `state.ongoing_actions` in this pass.)

---

### Phase 2: Tick logic refactor

**2a — Replace inject-ongoing block with pending-fire-in-priority-order loop** ✓ complete

Files: `logic/tick_logic.py`

The current inject block (lines ~1036–1110) does two jobs: (1) converts `ongoing_actions` entries into `ActionInstance` objects and appends them to `action_queue`; (2) tracks which instances came from ongoing slots and credits `executed_ticks`/`successful_ticks` after processing. The new approach fires directly from `pending_actions` in priority order, inline.

Add this constant near the top of `tick_logic.py` (after the `ActionCategory` import):
```python
_CATEGORY_PRIORITY: list["ActionCategory"] = [
    ActionCategory.DIRECT_CREATION,
    ActionCategory.OVERT_MIRACLE,
    ActionCategory.SUBTLE_INFLUENCE,
    ActionCategory.PROXIUS_DIRECTION,
    ActionCategory.OBSERVATION,
    ActionCategory.HERALD_INTERACTION,
    ActionCategory.LUMINARY_RELATIONS,
    ActionCategory.UNDERREAL,
    ActionCategory.SELF_REFINEMENT,
]
```

Replace the entire inject block (from `# ── Inject ongoing actions` through the manual cooldown assignment block ending at line ~1110) with:

```python
        # ── Phase 2: Pending action fire (priority order) ────────────
        # Build a temporary action_queue from pending slots, in category priority order.
        # Cooldown and Essence checks happen here; the queue fed to _process_action_queue
        # contains only the instances that will actually run this tick.
        committed_essence = 0.0
        fire_queue: list[ActionInstance] = []
        fired_cat_vals: list[str] = []  # parallel to fire_queue entries

        for category in _CATEGORY_PRIORITY:
            cat_val = category.value
            pending = state.pending_actions.get(cat_val)
            if pending is None:
                continue
            pending.ticks_active += 1

            defn = self._action_library.get(pending.action_key)
            if defn is None:
                continue

            if state.category_cooldowns.counters.get(category, 0) > 0:
                continue

            if defn.essence_cost > 0:
                available = state.essence.actual - committed_essence
                if defn.essence_cost > available:
                    continue
                committed_essence += defn.essence_cost

            instance = ActionInstance(
                action_definition_id=defn.id,
                target_type=pending.target_type,
                target_id=pending.target_id,
                timestamp=state.universe.current_age.to_float_years(),
                demiurge_id=state.demiurge.id,
                proxius_id=pending.proxius_id,
                intent=pending.intent,
            )
            fire_queue.append(instance)
            fired_cat_vals.append(cat_val)

        # Temporarily assign fire_queue as the action_queue for _process_action_queue.
        # (action_queue field removed from SimulationState; pass directly.)
        _essence_before = state.essence.actual
        action_result = self._process_action_queue_list(state, cfg, phase_rng, fire_queue)
        result.action_result = action_result
        state = self._apply_action_mutations(state, action_result)

        # Credit stats and assign cooldowns; clear non-repeating slots.
        executed_ids = {str(e.action_instance_id) for e in action_result.entries}
        outcome_by_id = {str(e.action_instance_id): e.outcome for e in action_result.entries}
        for instance, cat_val in zip(fire_queue, fired_cat_vals):
            if str(instance.id) not in executed_ids:
                continue
            pending = state.pending_actions.get(cat_val)
            if pending is None:
                continue
            pending.executed_ticks += 1
            if outcome_by_id.get(str(instance.id)) != ActionOutcome.FAILURE:
                pending.successful_ticks += 1
            defn = self._action_library.get(pending.action_key)
            if defn:
                _assign_category_cooldown(state, defn.category)
            if not pending.repeating:
                del state.pending_actions[cat_val]
```

Note: `_process_action_queue` currently reads `state.action_queue`. Rename it to `_process_action_queue_list` and change its signature to accept an explicit `queue` parameter instead of reading from state:

```python
def _process_action_queue_list(
    self,
    state: SimulationState,
    cfg: TickConfig,
    rng: random.Random,
    queue: list[ActionInstance],
) -> ActionProcessingResult:
    result = ActionProcessingResult()
    validated_queue, rejections = self._validate_and_filter_queue(queue, state.category_cooldowns)
    ...  # rest unchanged
```

The `state.action_queue = []` clear line (currently ~line 1089) is also removed since `action_queue` no longer exists on state.

Autoplay regression after 2a:
```bash
python main.py --autoplay wardens_compact
python main.py --autoplay ledger_and_ash
```

**2b — Target validation pass + remove cooldown gate from `_validate_and_filter_queue`** ✓ complete

Files: `logic/tick_logic.py`

Add a target validation helper and call it at the top of the tick's Phase 2 block, before building `fire_queue`:

```python
def _is_pending_target_valid(state: SimulationState, pending: OngoingAction) -> bool:
    """Return False if the pending action's target no longer exists in state."""
    if pending.target_id is None:
        return True
    tid = str(pending.target_id)
    tt = pending.target_type
    if tt == TargetType.MORTAL:
        m = state.mortals.get(tid)
        return m is not None and m.status != MortalStatus.DECEASED
    if tt == TargetType.WORLD:
        return tid in state.locations
    if tt == TargetType.CIVILIZATION:
        return tid in state.civilizations
    if tt == TargetType.LUMINARY:
        return tid in state.luminaries
    if tt in (TargetType.SYSTEM, TargetType.GALAXY):
        return tid in state.locations
    if tt == TargetType.SPECIES:
        return tid in state.species
    return True
```

Call at the start of Phase 2 (before `committed_essence = 0.0`):

```python
        # Validate pending targets; cancel stale slots.
        stale = [
            cat_val for cat_val, pending in state.pending_actions.items()
            if not _is_pending_target_valid(state, pending)
        ]
        for cat_val in stale:
            pa = state.pending_actions.pop(cat_val)
            result.passive_result.narrative_events.append(
                f"[Queue] Pending {pa.action_key.replace('_', ' ')} cancelled: target no longer valid."
            )
```

Also remove the cooldown gate from `_validate_and_filter_queue` (lines ~2120–2126). The cooldown check now happens at fire time in Phase 2; the validator no longer needs to enforce it. Keep only the duplicate-category check:

```python
    def _validate_and_filter_queue(
        self,
        queue: list["ActionInstance"],
        cooldowns: "CategoryCooldowns",
    ) -> tuple[list["ActionInstance"], list[str]]:
        """
        Enforce per-tick uniqueness: at most one action per ActionCategory.
        Cooldown gating is handled upstream (Phase 2 fire loop).
        """
        accepted: list[ActionInstance] = []
        rejected: list[str] = []
        seen_categories: dict[str, str] = {}

        for instance in queue:
            key = self._action_key_by_id.get(str(instance.action_definition_id))
            defn = self._action_library.get(key) if key else None
            if defn is None:
                continue
            cat = defn.category.value
            if cat in seen_categories:
                rejected.append(
                    f"{defn.name} blocked: a {cat.replace('_', ' ')} action "
                    f"({seen_categories[cat]}) is already queued this tick."
                )
                continue
            seen_categories[cat] = defn.name
            accepted.append(instance)

        return accepted, rejected
```

Update the `explore_beliefs` auto-stop block (~line 1132): change `state.ongoing_actions` → `state.pending_actions`.

Autoplay regression after 2b:
```bash
python main.py --autoplay wardens_compact
python main.py --autoplay ledger_and_ash
```

---

### Phase 3: UI action queuing flow

**3a — Remove essence hard-block; replace "make persistent?" with "make repeating?"; all actions write to `pending_actions`** ✓ complete

Files: `ui/ui.py`

Remove the essence affordability check block (lines ~821–844). Essence is now checked at fire time.

Remove the `can_persist` persistence offer block (lines ~855–878).

Replace the final `state.action_queue.append(instance)` line (~880) and the logging that follows with a write to `pending_actions`. Since all actions now use `OngoingAction`, construct one from the `ActionInstance`:

```python
        # Ask if they want this action to repeat
        make_repeating = False
        repeat_answer = await app.push_screen_wait(
            YesNoModal(
                f"Queue '{defn.name}'?",
                "Fire once and clear, or repeat each tick until stopped?",
                yes_label="Repeat",
                no_label="Once",
            )
        )
        make_repeating = bool(repeat_answer)

        state.pending_actions[defn.category.value] = OngoingAction(
            action_key=action_key,
            action_definition_id=defn.id,
            target_type=instance.target_type,
            target_id=instance.target_id,
            proxius_id=instance.proxius_id,
            intent=instance.intent,
            repeating=make_repeating,
            ticks_active=0,
            started_at_tick=state.tick_number,
        )
        label = "[REPEATING]" if make_repeating else "[QUEUED]"
        plain_target = f" → {_name_for_id(instance.target_id, state)}" if instance.target_id else ""
        link_target  = f" → {_name_link_for_id(instance.target_id, state)}" if instance.target_id else ""
        self._log.write_action(f"{label} {defn.name}{plain_target}")
        self._feed_markup(f"[#a0d080]{label}[/] {_e(defn.name)}{link_target}", "actions")
        self._refresh_status()
        self._focus_actions_tab()
```

Note: `YesNoModal` may not support custom button labels today. Check `ui/modals.py`; if it doesn't, either add `yes_label`/`no_label` params or use a dedicated `RepeatOrOnceModal`. Either way, the modal must offer two clear options: "Once" and "Repeat".

Also update the committed-essence calculation in any remaining UI surfaces (e.g., status display) that reference `state.action_queue` or `state.ongoing_actions` — change to `state.pending_actions`.

Autoplay regression after 3a:
```bash
python main.py --autoplay wardens_compact
python main.py --autoplay ledger_and_ash
```

---

### Phase 4: Cooling category modal

**4a — `CategoryPendingModal` scaffold** ✓ complete

Files: `ui/modals.py`

Add a new modal class. When the player clicks a category with an occupied slot (regardless of cooldown state), show this instead of the "not ready" toast:

```python
class CategoryPendingModal(ModalScreen):
    """
    Shown when the player clicks a category that already has a pending action.
    Offers four options: keep, override-once-resume (Phase 5), replace, cancel.
    """
    BINDINGS = [("escape", "dismiss(None)", "Cancel")]

    def __init__(self, category: "ActionCategory", pending: "OngoingAction",
                 action_name: str, cooldown_remaining: int):
        super().__init__()
        self._category = category
        self._pending = pending
        self._action_name = action_name
        self._cooldown_remaining = cooldown_remaining

    def compose(self) -> ComposeResult:
        repeat_label = "Repeating" if self._pending.repeating else "One-shot"
        cooldown_str = (
            f"  Cooling: {self._cooldown_remaining} tick{'s' if self._cooldown_remaining != 1 else ''} remaining\n"
            if self._cooldown_remaining > 0 else ""
        )
        with ModalContainer():
            yield Label(
                f"[b]{self._category.value.replace('_', ' ').title()}[/b] — pending action\n\n"
                f"  {self._action_name}  [{repeat_label}]\n"
                f"{cooldown_str}",
                markup=True,
            )
            yield Button("1  Keep current", id="keep", variant="default")
            yield Button("2  Override once, then resume  (Phase 5 — not yet impl.)", id="override_resume", variant="default", disabled=True)
            yield Button("3  Replace with new action", id="replace", variant="warning")
            yield Button("4  Cancel pending action", id="cancel_pending", variant="error")

    @on(Button.Pressed, "#keep")
    def _keep(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#replace")
    def _replace(self) -> None:
        self.dismiss("replace")

    @on(Button.Pressed, "#cancel_pending")
    def _cancel(self) -> None:
        self.dismiss("cancel")
```

**4b — Wire `_on_category_clicked` to `CategoryPendingModal`** ✓ complete

Files: `ui/ui.py`

Replace the current `_on_category_clicked` handler:

```python
@on(CategoryPanel.CategoryClicked)
def _on_category_clicked(self, event: CategoryPanel.CategoryClicked) -> None:
    if event.is_cooling:
        self.app.push_screen(ToastModal("Category on cooldown — not ready yet."))
    else:
        self._queue_action_flow(initial_category=event.category)
```

With:

```python
@on(CategoryPanel.CategoryClicked)
@work
async def _on_category_clicked(self, event: CategoryPanel.CategoryClicked) -> None:
    cat_val = event.category.value
    pending = self._state.pending_actions.get(cat_val)
    if pending is None:
        # Slot empty — open browser directly (cooldown doesn't block queuing)
        await self._queue_action_flow(initial_category=event.category)
        return

    # Slot occupied — show pending modal regardless of cooldown state
    cooldown_remaining = self._state.category_cooldowns.counters.get(event.category, 0)
    defn = self.app.loop._action_library.get(pending.action_key)
    action_name = defn.name if defn else pending.action_key
    result = await self.app.push_screen_wait(
        CategoryPendingModal(event.category, pending, action_name, cooldown_remaining)
    )
    if result == "replace":
        await self._queue_action_flow(initial_category=event.category)
    elif result == "cancel":
        del self._state.pending_actions[cat_val]
        self._feed_markup(f"[#c08070]Cancelled pending {_e(action_name)}.[/]", "actions")
        self._refresh_status()
    # None (keep) → do nothing
```

Note: `_queue_action_flow` is currently decorated with `@work` and is not `async`. For the `await` above to work, either make `_queue_action_flow` return a result (currently it doesn't), or split the flow. The simplest approach: remove `@work` from `_queue_action_flow` and make it a plain `async` method, then call it with `await`. Check that this doesn't break the other callers (`_build_intent` etc.) — they're all `await`-based already.

Autoplay regression after 4b:
```bash
python main.py --autoplay wardens_compact
python main.py --autoplay ledger_and_ash
```

---

### Phase 5: Override-once-then-resume

**5a — `pending_resume` state + tick restore logic**

Files: `logic/tick_logic.py`, `core/scenario_schema.sql`, `utilities/scenario_loader.py`, `utilities/scenario_exporter.py`

Add to `SimulationState`:
```python
# When a one-shot override is queued over a repeating action, the repeating
# action is stored here. After the one-shot fires, it is restored.
pending_resume: dict[str, OngoingAction] = Field(default_factory=dict)
```

In the Phase 2 fire loop, after clearing a non-repeating slot, check for a resume action:
```python
            if not pending.repeating:
                del state.pending_actions[cat_val]
                # Restore resume action if one was saved for this category
                resume = state.pending_resume.pop(cat_val, None)
                if resume is not None:
                    state.pending_actions[cat_val] = resume
```

Add `pending_resume` table to `core/scenario_schema.sql` (same columns as `ongoing_actions`):
```sql
CREATE TABLE IF NOT EXISTS pending_resume (
    category_key           TEXT PRIMARY KEY,
    action_key             TEXT NOT NULL,
    action_definition_id   TEXT NOT NULL,
    target_type            TEXT NOT NULL,
    target_id              TEXT,
    proxius_id             TEXT,
    intent_type            TEXT,
    intent_data            TEXT,
    ticks_active           INTEGER NOT NULL DEFAULT 0,
    executed_ticks         INTEGER NOT NULL DEFAULT 0,
    successful_ticks       INTEGER NOT NULL DEFAULT 0,
    started_at_tick        INTEGER NOT NULL DEFAULT 0,
    repeating              INTEGER NOT NULL DEFAULT 0
);
```

Add `_load_pending_resume(conn)` and `_write_pending_resume(conn, state)` in loader/exporter — structurally identical to their `ongoing_actions` counterparts, but reading/writing the `pending_resume` table and `state.pending_resume`.

**5b — Wire "Override once, then resume" in `CategoryPendingModal`**

Files: `ui/modals.py`, `ui/ui.py`

In `CategoryPendingModal`, enable the "Override once, then resume" button (remove `disabled=True`):
```python
yield Button("2  Override once, then resume", id="override_resume", variant="primary")
```

Add handler:
```python
@on(Button.Pressed, "#override_resume")
def _override_resume(self) -> None:
    self.dismiss("override_resume")
```

In `_on_category_clicked` in `ui.py`, handle the new result:
```python
    elif result == "override_resume":
        # Store current repeating action as resume target, then open browser for one-shot
        self._state.pending_resume[cat_val] = pending
        await self._queue_action_flow(initial_category=event.category)
        # After flow completes, ensure the new action is one-shot
        new_pending = self._state.pending_actions.get(cat_val)
        if new_pending and new_pending is not pending:
            new_pending.repeating = False
```

Autoplay regression after 5b:
```bash
python main.py --autoplay wardens_compact
python main.py --autoplay ledger_and_ash
```

---

## Files affected

- `core/action_core.py` — `repeating: bool = False` on `OngoingAction`
- `core/scenario_schema.sql` — `repeating` column on `ongoing_actions`; new `pending_resume` table (Phase 5)
- `logic/tick_logic.py` — `SimulationState` field rename; `_CATEGORY_PRIORITY` constant; inject block → priority fire loop; target validation; `_validate_and_filter_queue` simplified; `_process_action_queue` → `_process_action_queue_list`
- `utilities/scenario_loader.py` — load `repeating`; assign `pending_actions`; `_load_pending_resume` (Phase 5)
- `utilities/scenario_exporter.py` — write `repeating`; write `pending_actions`; `_write_pending_resume` (Phase 5)
- `autoplay/strategies/_helpers.py` — `queue()` writes `OngoingAction` to `pending_actions`
- `ui/ui.py` — remove essence hard-block; remove `can_persist` flow; "once vs repeating" modal; `_on_category_clicked` smart dispatch
- `ui/modals.py` — `CategoryPendingModal` (Phase 4); "Override once, then resume" wired (Phase 5)

---

## Notes

- **Must be on a feature branch.** The game is non-functional between Phase 1 and Phase 2 (action_queue removed but fire logic not yet replaced). Never let a partial state land on main.
- The `cooldowns` parameter on `_validate_and_filter_queue` becomes unused after Phase 2b. Remove it from the signature once 2b is stable; update the call site in `_process_action_queue_list`.
- The "Once" / "Repeat" modal in Phase 3 may feel like too much friction for every action queue. Consider making the default behavior configurable per `ActionDefinition` (most actions default one-shot; `essence_harvest` and `scry` default repeating) and only asking when the player might want to override. This is a playtesting question — implement the ask-always version first.
- The `can_persist` tag on `ActionDefinition` becomes unused after Phase 3. Remove it from all action definitions in `build_action_library()` as cleanup.
- Phase 5 "override-once-then-resume" is the most complex piece. If it feels over-engineered after playtesting Phases 1–4, it can be cut — the modal simply leaves option 2 disabled permanently.
- The autoplay strategies currently call `queue()` with no `repeating` argument; they will default to `repeating=False` (one-shot). Strategies that previously used `state.ongoing_actions[cat] = OngoingAction(...)` directly (if any) need to be found and updated to use `_helpers.queue()` with `repeating=True`.
