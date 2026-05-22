> **Status:** active
> **TO-DO ref:** Tick and time standardization with RTwP
> **Last updated:** 2026-05-22 (rev 7)

## Goal

Replace the current manual tick-per-turn model with a **Real-Time with Pause** (RTwP) loop where time advances continuously, per-category cooldowns gate action availability, and tick scale drops from ~six-month periods to single days. This is a **massive, game-breaking refactor** — all work must be done in a dedicated fork.

Full design is in [`docs/Brainstorming/rtwp_action_system.md`](../Brainstorming/rtwp_action_system.md).

---

## Phases

### Phase 1: Core Loop Refactor

**1a — Spacebar auto-advance toggle** ✓ complete
- Add `auto_advance: bool` state to `GameScreen`
- Bind `spacebar` to toggle it; when active, fire ticks continuously with a short inter-tick delay
- Preserve `t` for single-tick step regardless of auto-advance state

**1b — Stability check** ✓ complete
- Confirm the game loop is stable under continuous advancement with no player input
- Run `--autoplay` regression; no crashes or hangs expected

---

### Phase 2: Per-Category Cooldowns

**2a — Data model + persistence** ✓ complete
- Add `CategoryCooldowns(BaseModel)` to `core/action_core.py` with `counters: dict[ActionCategory, int]`
- Add `category_cooldowns: CategoryCooldowns` to `SimulationState`
- Add column to `core/scenario_schema.sql`; load in `scenario_loader.py`; export in `scenario_exporter.py`

**2b — Cooldown decrement + action gating** ✓ complete
- Decrement all non-zero counters each tick in `tick_logic.py`
- Gate action availability: actions in a cooling category are unavailable
- Assign placeholder base cooldown values per category (to be tuned in playtesting)

**2c — Trigger + puissance reduction**
- Stopping an ongoing action sets that category's cooldown to its base value
- Apply puissance formula on cooldown assignment: `max(base - floor(puissance * 3), ceil(base * 0.75))`

---

### Phase 3: Auto-Pause System

**3a — Pause event framework + hard-pause triggers**
- Define pause event types in `tick_logic.py`
- Implement hard-pause triggers (not configurable): Luminary/Herald/Proxius contact, Luminary ultimatum

**3b — Default-pause triggers**
- evaluation completes, Revelation threshold crossed, queued action completes, pinned mortal dies

**3c — Default-silent triggers + config persistence**
- pop splint, domain threshold, travel complete, minor agent updates
- Persist pause config (enabled/disabled per trigger) to save state

---

### Phase 4: Category Panel UI

**4a — Panel scaffold**
- New vertical panel on the far right of `GameScreen`
- One row per `ActionCategory`: symbol + placeholder `ProgressBar`
- Layout and basic styles in `ui/widgets.py` + `ui/styles.tcss`

**4b — Live cooldown state**
- Wire `CategoryCooldowns.counters` to each row's progress bar
- Ready categories display at full; cooling categories show countdown

**4c — Interaction**
- Click ready category → open action picker at that category's sub-menu; "back" goes to main picker
- Click cooling category → "not ready" toast
- Category symbols: `✦ ✺ ≃ ▻ ⊚ ⚜ ↑ ∇ ⟡`

---

### Phase 5: RTwP Control Modal

**5a — Modal scaffold + layout**
- Triggered by `spacebar` from `GameScreen` (when no other modal is active)
- Covers main content panel area only — tab name row, left panel, category panel remain visible
- Background: standard modal dim; left panel + category panel at full brightness
- Establish the three-section layout (log / auto-pause options / time control bar) with placeholder content

**5b — Live log feed**
- Top ~2/3 of modal: log section that continues to refresh as ticks advance

**5c — Auto-pause options panel**
- Two-column layout with spanning header toggle: `[ ] Begin advancing when this menu opens`
- Left column (default-on): evaluation completes, Revelation threshold, queued action completes, pinned mortal dies
- Right column (default-off): pop splint, domain threshold, travel complete, minor agent updates
- Wire to the pause config state from Phase 3c

**5d — Time control bar + keybindings**
- Button row (left to right): Exit | Slow | Pause/Play | +1 | Fast
- `spacebar` → Pause/Play; `t` → +1; `numpad +` / `numpad -` → Fast / Slow
- `Esc` → Exit (pauses first if advancing); Exit while advancing always pauses before closing

---

### Phase 6: Tick Scale Recalibration

**6a — Audit all per-tick rates**
- Identify every system with a per-tick rate (Essence, Revelation, cultural drift, belief shifts, travel countdown, etc.)
- Produce a checklist before touching any values

**6b — Age representation**
- Change `Universe` age storage to `(billions, millions, thousands, years, months, days)`
- Update top-bar display: `"Day 13 of Month 5, Year 13,675,482,090"`

**6c — Recalibrate Essence + Revelation**
- Adjust per-tick rates to suit tick = 1 day; drop per-tick minimums; rely on fractional accumulation

**6d — Recalibrate cultural drift + belief shifts + remaining systems**
- Work through the audit checklist from 6a

**6e — Full regression**
- `--autoplay` pass; fix any remaining rate anomalies

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
