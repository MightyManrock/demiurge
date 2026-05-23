> **Status:** pending
> **Last updated:** 2026-05-23 (rev 1)

## Goal

Four quality-of-life improvements to the Status tab, Log tab, and entity pinning system:

1. **Affinities persistence** — show the last Essence capture snapshot at all times, not just on the tick it fires.
2. **Harvest Essence line** — surface the last Underreal harvest amount in the Status tab; hide it after 30 ticks of disuse.
3. **Log verbosity** — suppress travel notifications for un-pinned mortals; suppress empty-tick log entries entirely.
4. **Remove starting-pinned** — replace with explicit 1.00 starting visibility; show visibility as a percentage in the UI.

Execution order: Phase 1 → Phase 2 (batch schema changes together) → Phase 3 → Phase 4.

---

## Phase 1 — Persist last Essence capture snapshot

**Problem:** `last_tick_essence_by_domain` is cleared and repopulated monthly (Phase 1 of the tick loop). On all other ticks it is empty, so the affinities section of the Status tab goes blank between capture events.

**1a — New `SimulationState` fields** (`logic/tick_logic.py` ~line 940) ✓ complete

- `last_essence_capture_by_domain: dict[str, float] = Field(default_factory=dict)` — most recent non-empty monthly snapshot
- `last_essence_capture_tick: int = 0` — tick number when the snapshot was taken

**1b — Populate in tick_logic** ✓ complete

In `_process_essence_generation`, after writing to `last_tick_essence_by_domain`, copy the result into `last_essence_capture_by_domain` and set `last_essence_capture_tick = state.tick_number`.

**1c — Persistence** ✓ complete

- `core/scenario_schema.sql`: add `last_essence_capture_by_domain TEXT` (JSON) and `last_essence_capture_tick INTEGER DEFAULT 0` to the saves metadata table
- `scenario_loader.py`: load with `.get()` defaults (empty dict / 0)
- `scenario_exporter.py`: serialize dict as JSON; export int normally

**1d — Wire Status tab** (`ui/widgets.py` ~line 413) ✓ complete

Replace the read of `state.last_tick_essence_by_domain` with `state.last_essence_capture_by_domain`. When `last_essence_capture_tick > 0`, append a dim annotation such as `[dim](tick {state.last_essence_capture_tick})[/]` to the section header so the player knows how fresh the data is.

---

## Phase 2 — Harvest Essence last-result line

**2a — New `SimulationState` fields** (`logic/tick_logic.py` ~line 940) ✓ complete

- `last_harvest_amount: float = 0.0`
- `last_harvest_tick: int = 0`

**2b — Populate in tick_logic**

In the `EssenceHarvestIntent` handler (~line 3708), on a successful harvest: set `state.last_harvest_amount = actual_yield` and `state.last_harvest_tick = state.tick_number`. (Leave unchanged on failure so the last successful value persists.)

**2c — Persistence**

Same pattern: `last_harvest_amount REAL DEFAULT 0.0` and `last_harvest_tick INTEGER DEFAULT 0` in the schema; load with `.get()` defaults; export normally.

**2d — Status tab line + CSS visibility** (`ui/widgets.py`, `ui/styles.tcss`)

Add a dedicated `Static` widget in the Essence section showing `Last underreal harvest: +{state.last_harvest_amount:.2f}`. In `refresh_state`, compute `stale = state.last_harvest_tick == 0 or (state.tick_number - state.last_harvest_tick) > 30` and toggle a CSS class (e.g. `harvest-stale`) on that widget. In `styles.tcss`: `.harvest-stale { display: none; }`.

---

## Phase 3 — Log verbosity

**3a — Travel notifications: pinned mortals only**

In `_resolve_mortal_travel_decisions` and `_process_mortal_travel` (`logic/tick_logic.py` ~lines 4994–5105), gate travel narrative appends on `mortal.pinned`. Currently only Karath Omn and Durenn Vail have travel logic — once their `pinned` flags are cleared in Phase 4, their notifications will disappear automatically. The explicit gate ensures future mortals with travel logic respect the same rule.

**3b — Suppress empty-tick log entries**

In `display_tick_result_categorized` (`ui/display.py`), after assembling all sections, check whether anything substantive was added (i.e., any category other than `"other"` has at least one non-empty line, or the `"other"` section contains more than just the tick header/separator). If nothing substantive was produced, return `[]`.

In `ui/ui.py`'s tick-result processing, skip all `_feed_markup` calls when the returned list is empty (no header, no separator, nothing).

---

## Phase 4 — Remove starting-pinned; visibility as percentage

**4a — Remove the concept**

- Drop `starting_pinned_ids: list[str]` from `SimulationState` (`logic/tick_logic.py` ~line 944)
- Remove the tick-360 unpin loop (`logic/tick_logic.py` ~lines 1691–1701)
- Remove `starting_pinned_ids` loading/saving from `scenario_loader.py` and `scenario_exporter.py`
- Drop the column from `core/scenario_schema.sql`
- Remove the `starting_pinned_ids` field from `tools/scenario_builder/skeleton.py` (~line 127)

**4b — Set affected entities to 1.00 visibility**

Run `--rebuild --scenario` (the migrator round-trip) after removing the schema column. Any entity previously in `starting_pinned_ids` must have `visibility = 1.0` already set in its scenario row — verify this is the case by inspecting the wardens_compact scenario, and patch manually via `--inject` if any entity's visibility was left at a lower value.

**4c — Visibility as percentage in UI**

Audit every place entity visibility is displayed:
- `ui/widgets.py` — Entities tab rows
- `ui/detail_renderers.py` — per-entity detail tabs
- Any other surfaces (Status panel, Briefing tab if applicable)

Format as `f"{v:.0%}"` (e.g. `100%`, `74%`) to match how domain affinities and disposition scores are shown.
