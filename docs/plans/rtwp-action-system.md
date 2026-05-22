> **Status:** active
> **TO-DO ref:** Tick and time standardization with RTwP
> **Last updated:** 2026-05-22 (rev 2)

## Goal

Replace the current manual tick-per-turn model with a **Real-Time with Pause** (RTwP) loop where time advances continuously, per-category cooldowns gate action availability, and tick scale drops from ~six-month periods to single days. This is a **massive, game-breaking refactor** — all work must be done in a dedicated fork.

Full design is in [`docs/Brainstorming/rtwp_action_system.md`](../Brainstorming/rtwp_action_system.md).

---

## Phases

### Phase 1: Core Loop Refactor
- Add `spacebar` toggle for continuous auto-advance in `GameScreen`
- Preserve `t` for single-tick step
- Confirm the game loop is stable under continuous advancement with no player input

### Phase 2: Per-Category Cooldowns
- Add a `CategoryCooldowns(BaseModel)` to `core/action_core.py` with a single field `counters: dict[ActionCategory, int]`; add `category_cooldowns: CategoryCooldowns` to `SimulationState` — **not** flat fields on `SimulationState`
- Define base cooldown values per category (placeholder values, to be tuned)
- Gate action availability on cooldown state rather than tick boundary
- Stopping an ongoing action triggers a cooldown on that category
- Puissance reduces cooldowns: `max(base - floor(puissance * 3), ceil(base * 0.75))` — max −3 ticks, never below 75% of base; at typical cooldowns of 5–30+ ticks this is intentionally minor

### Phase 3: Auto-Pause System
- Implement an event-type pause framework in the tick loop
- Hard-pause triggers (not configurable): Luminary/Herald/Proxius contact, Luminary ultimatum
- Default-pause triggers (player can disable): evaluation completes, Revelation threshold, queued action completes, pinned mortal dies
- Default-silent triggers (player can enable): pop splint, domain threshold, travel complete, minor agent updates
- Expose pause config in a settings modal or dedicated tab

### Phase 4: Category Panel UI
- New vertical panel on the far right of `GameScreen`
- One row per action category: symbol + short progress bar (Textual `ProgressBar`)
- Click on a ready category → open the action picker directly at that category's sub-menu (bypasses top-level picker); pressing "back" from there goes to the main action picker, not close
- Click on a cooling category → "not ready" toast
- Category symbols per brainstorm doc:
  `✦ ✺ ≃ ▻ ⊚ ⚜ ↑ ∇ ⟡`

### Phase 5: RTwP Control Modal
- Triggered by `spacebar` from `GameScreen` (when no other modal is active)
- Covers the main content panel area only — tab name row, left panel, and category cooldown panel remain visible and fully interactive
- Background dims to standard modal level; left panel and cooldown panel stay at full brightness
- **Log section** (top ~2/3): live feed that continues to refresh as ticks advance
- **Auto-pause options** (middle, two columns):
  - Spanning header row: `[ ] Begin advancing when this menu opens`
  - Left column (default-on, can disable): evaluation completes, Revelation threshold, queued action completes, pinned mortal dies
  - Right column (default-off, can enable): pop splint, domain threshold, travel complete, minor agent updates
- **Time control bar** (bottom, left to right): Exit | Slow | Pause/Play | +1 | Fast
  - `spacebar`: same as Pause/Play
  - `t`: same as +1 (advance one tick)
  - `numpad +` / `numpad -`: same as Fast / Slow
  - `Esc`: same as Exit; pauses advancement first if ticks are running
  - Exit while advancing: always pauses before closing

### Phase 6: Tick Scale Recalibration
- Tick = 1 day (scenario parameter, stored on `SimulationState`)
- Universe/civilization ages stored as `(billions, millions, thousands, years, months, days)` — display as `"Day 13 of Month 5, Year 13,675,482,090"` in the top bar
- Recalibrate all per-tick rates: Essence, Revelation, cultural drift, belief shifts
- Drop per-tick minimums; rely on fractional accumulation
- Audit checklist: every system with a per-tick rate must be identified and recalibrated in a single coordinated pass

*Phase 6 should not be started until Phases 1–5 are stable and playtested.*

---

## Files affected

- `core/action_core.py` — add `CategoryCooldowns` model; cooldown metadata per `ActionDefinition`; per-action cooldown modifier field
- `core/universe_core.py` — age representation changes (Phase 5)
- `logic/tick_logic.py` — cooldown decrement, auto-advance loop, auto-pause event dispatch
- `ui/ui.py` — spacebar binding, auto-advance state, pause event handling, category panel wiring
- `ui/widgets.py` — category panel widget; cooldown progress bars
- `ui/styles.tcss` — category panel layout
- `ui/modals.py` — RTwP control modal: log feed, auto-pause config, time controls (Phase 5)
- `utilities/scenario_loader.py` / `scenario_exporter.py` — cooldown state persistence (Phase 2)
- `core/scenario_schema.sql` — new columns for cooldown state (Phase 2)
- Possibly all of `autoplay/` — auto-advance may require updates to headless playtest strategies

---

## Notes

- **Must be done in a fork.** This refactor fundamentally breaks the game mid-implementation. No partial state should land on `main` until the whole system is stable and playtested.
- Base cooldown values per category need significant playtesting to feel right. Starting heuristic: direct/overt actions (Manifest Omen, Appoint Proxius) cool longer than subtle/delegated (Whisper, Proxius directives) or internal (Reveal Imāgō) actions.
- The category panel is the third queue-action path, alongside the `a` keybind and the "Queue Action" button in the Actions tab — all three must stay in sync.
- Phase 5 tick recalibration scope: a full audit list of all per-tick rates should be assembled before that pass begins.
- Open question: should a category with a running ongoing action display its cooldown bar differently? (e.g., mid-gray-blue tint)
- Open question: do ongoing actions in a category reduce cooldown for related categories? (TBD per category)
