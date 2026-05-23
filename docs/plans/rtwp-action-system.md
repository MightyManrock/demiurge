> **Status:** active
> **TO-DO ref:** Tick and time standardization with RTwP
> **Last updated:** 2026-05-22 (rev 14)

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

**2c — Trigger + puissance reduction** ✓ complete
- Stopping an ongoing action sets that category's cooldown to its base value
- Apply puissance formula on cooldown assignment: `max(base - floor(puissance * 3), ceil(base * 0.75))`

---

### Phase 3: Auto-Pause System

**3a — Pause event framework + hard-pause triggers** ✓ complete
- Define pause event types in `tick_logic.py`
- Implement hard-pause triggers (not configurable): Luminary/Herald/Proxius contact, Luminary ultimatum

**3b — Default-pause triggers** ✓ complete
- evaluation completes, Revelation threshold crossed, queued action completes, pinned mortal dies

**3c — Default-silent triggers + config persistence** ✓ complete
- pop splint, domain threshold, travel complete, minor agent updates
- Persist pause config (enabled/disabled per trigger) to save state

---

### Phase 4: Category Panel UI

**4a — Panel scaffold** ✓ complete
- New vertical panel on the far right of `GameScreen`
- One row per `ActionCategory`: symbol + placeholder `ProgressBar`
- Layout and basic styles in `ui/widgets.py` + `ui/styles.tcss`

**4b — Live cooldown state** ✓ complete
- Wire `CategoryCooldowns.counters` to each row's progress bar
- Ready categories display at full; cooling categories show countdown

**4c — Interaction** ✓ complete
- Click ready category → open action picker at that category's sub-menu; "back" goes to main picker
- Click cooling category → "not ready" toast
- Category symbols: `✦ ✺ ≃ ▻ ⊚ ⚜ ↑ ∇ ⟡`

---

### Phase 5: RTwP Control Modal

**5a — Modal scaffold + layout** ✓ complete
- Triggered by `spacebar` from `GameScreen` (when no other modal is active)
- Covers main content panel area only — tab name row, left panel, category panel remain visible
- Background: standard modal dim; left panel + category panel at full brightness
- Establish the three-section layout (log / auto-pause options / time control bar) with placeholder content
- *Note: scaffold covers the full right panel including tab strip; exact column clipping deferred to later sub-phase when live content is in place*

**5b — Live log feed** ✓ complete
- Top ~2/3 of modal: log section that continues to refresh as ticks advance

**5c — Auto-pause options panel** ✓ complete
- Two-column layout with spanning header toggle: `[ ] Begin advancing when this menu opens`
- Left column (default-on): evaluation completes, Revelation threshold, queued action completes, pinned mortal dies
- Right column (default-off): pop splint, domain threshold, travel complete, minor agent updates
- Wire to the pause config state from Phase 3c

**5d — Time control bar + keybindings** ✓ complete
- Button row (left to right): Exit | Slow | Pause/Play | +1 | Fast
- `spacebar` → Pause/Play; `t` → +1; `numpad +` / `numpad -` → Fast / Slow
- `Esc` → Exit (pauses first if advancing); Exit while advancing always pauses before closing

---

### Phase 6: Tick Scale Recalibration

**6a — Audit all per-tick rates** ✓ complete
- Identify every system with a per-tick rate (Essence, Revelation, cultural drift, belief shifts, travel countdown, etc.)
- Produce a checklist before touching any values

#### 6a checklist (no values changed yet)

**Action cooldowns** (`core/action_core.py:78`)
- [ ] `CATEGORY_BASE_COOLDOWNS`: Direct=20, Overt=25, Influence=10, Proxius=8, Observe=5, Herald=15, Luminary=15, Underreal=12, Refine=6 ticks

**Tick cadence** (`logic/tick_logic.py`)
- [ ] `tick_duration` (~:499): 1.0 universe-time units per tick
- [ ] `evaluation_interval` (~:558): 10.0 ticks between Luminary evaluations
- [ ] Starting pin expiry (~:1602): tick 30

**Visibility decay** (`logic/tick_logic.py`)
- [ ] Mortal decay: 0.03/tick (modulated by prominence) (~:537)
- [ ] Location decay: 0.01/tick (~:540)
- [ ] Civilization decay: 0.01/tick (~:541)
- [ ] Species decay: 0.01/tick (~:542)
- [ ] Pop visibility drift: 0.02/tick (~:608)

**Footprint & concealment** (`logic/tick_logic.py`)
- [ ] Base footprint decay: 0.05/tick; category multipliers overt=1.0, influence=1.8, proxius=0.8, creation=0.4 (~:505–516)
- [ ] Proxius passive footprint: 0.03/tick/Proxius; compliant worlds 0.3× (~:552, :72)
- [ ] Concealment decay: 0.02/tick; stalls at ≥6 quiet ticks (~:519, :1758)

**Belief & culture drift** (`logic/tick_logic.py`)
- [ ] Pop conformity toward civ: 0.005/tick base × cohesion × scale_mult (~:604)
- [ ] Civ established→dominant drift: 0.01/tick × cohesion (~:611)
- [ ] Pop cross-contact base: 0.005/tick; cross-civ 0.15×, cross-species 0.50×, cross-stratum 0.70×/rank (~:616–620)
- [ ] Rider trait attrition: 0.003/tick (~:188)
- [ ] Values stubbornness: 0.1× normal rate (~:630)
- [ ] `BELIEF_FLOOR` 0.02, `CULTURE_FLOOR` 0.01, `BELIEF_CAP` 0.9 (~:78–90) — may not need scaling

**Mortal & civ aging** (`logic/tick_logic.py`)
- [ ] Mortal alignment drift: 0.01/tick (Proxii 0.5×) (~:533)
- [ ] Mortal bio-age: 1.0×tick_duration active, 0.2× dormant (~:1516)
- [ ] Natural death probability: progress × 0.3 peak/tick (~:1537)
- [ ] Pop affiliation age-out threshold: lifespan_min (~:1564)
- [ ] Civ momentum drift: 0.02/tick; noise 0.01/tick (~:525)

**Attention** (`logic/tick_logic.py`)
- [ ] Luminary attention decay: 0.03/tick (~:546)

**Essence generation** (`logic/tick_logic.py`)
- [ ] Location weight: 3.0, Pop weight: 10.0, Mortal weight: 0.5 (~:561–570)
- [ ] Luminary essence baseline: 10.0/affinity/tick (~:579)
- [ ] Essence recall fraction: 0.20 of prior excess (~:591)
- [ ] Passive expectation rise: 5.0/tick × (ticks_since / tick_number) (~:597)

**Revelation & puissance** (`logic/tick_logic.py`)
- [ ] Revelation base costs per tier: {1:60, 2:100, 3:200, 4:400} (~:295)
- [ ] Revelation inflation: +0.3%/previously-revealed Imago (~:336)
- [ ] Puissance saturation: `REV_SCALE`=500, `IMAGO_SCALE`=40, `TICK_SCALE`=200 (~:305)

**6b — Age representation** ✓ complete
- `UniverseAge(year, month, day)` model replaces `float`; `advance_days(n)` + `display()` helpers
- Top-bar/status/briefing display: `"Day D of Month M, Year Y"` (year formatted with commas)
- `birthday: (month, day)` on `NotableMortal`; `founding_date: (year, month, day)` on `Civilization`; both derived from existing age data during migration
- Birthday interval check (`_birthday_fires`) gates chrono/bio age increments for mortals; dormant Proxii bio_age increments 0.2 on birthday only
- Civ age increments by 1 on founding anniversary (`_birthday_fires` over founding month/day)
- Schema: `age_year/age_month/age_day` columns (legacy `current_age` float preserved); `birthday_month/birthday_day` on mortals; `founding_year/month/day` on civs
- Existing scenarios migrated via `--rebuild --scenario`

**6b2 — Founding date + birthday curation** ✓ complete
- All 9 civs in wardens_compact.db and 9 in ledger_and_ash.db assigned distinct founding month/day via deterministic MD5 hash of name
- All mortals in both scenarios assigned distinct birthdays by same method
- Applied directly to scenario DBs; autoplay regression passes

**6c — Recalibrate Essence + Revelation** ✓ complete
- `evaluation_interval` → 360 ticks (annual); gate essence generation to `day == 1` (monthly)
- `luminary_essence_baseline_rate` 10.0 → 0.05; `luminary_essence_passive_rise` 5.0 → 0.1
- Fixed early-return bug in `_process_essence_generation` (`return []` → `return [], {}`)
- `core/scenario_schema.sql` default updated; both scenario DBs migrated

**6d1 — Recalibrate decay rates** ✓ complete
- Footprint, concealment, visibility (mortal/location/civ/species), attention, proxius passive footprint
- All scaled from ~180-day-tick magnitudes down to 1-day-tick magnitudes
- Targets: footprint lingers ~2.7 yr, concealment degrades ~2.7 yr, attention 1.0→0.1 in ~1 yr, mortal vis fades over years, location/civ/species slower, proxius trace minimal daily

**6d2 — Recalibrate belief/culture drift** ✓ complete
- `pop_conformity_base` 0.005 → 0.0003; `established_drift_base` 0.01 → 0.0005; `pop_contact_base_rate` 0.005 → 0.00003; `RIDER_ATTRITION_BASE` 0.003 → 0.00002
- `alignment_drift_rate` 0.01 → 0.001; `pop_visibility_drift_rate` 0.02 → 0.002
- `civ_momentum_rate` 0.02 → 0.003; `civ_noise_factor` 0.01 → 0.004
- Civ momentum/stability gated to monthly (day==1), same pattern as essence; `stability_delta` initialized to 0.0 before gate to preserve threshold-crossing narrative events

**6d3 — TICK_SCALE / puissance recalibration** ✓ complete
- `TICK_SCALE` 200 → 3650 (10-year saturation at 1-day/tick; preserves "minor long-run contribution" character)
- Starting pin expiry: tick 29 → tick 359 (30 days → 1 year; old 30-tick expiry was ~15yr at 180-day ticks)

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
