> **Status:** active
> **TO-DO ref:** RTwP → Log Tab migration
> **Last updated:** 2026-05-23 (rev 2)

## Goal

Replace the `RTwPModal` overlay (Phases 5a–5d) with a bottom section bolted onto the existing `LogTab`. Spacebar is a pure play/pause toggle from anywhere on the main game screen — no navigation. The Log tab shows a gold indicator when it has unseen tick output. Auto-pause options and time controls live permanently at the bottom of the Log tab in a fixed-height section that doesn't interfere with the scrollable log above.

---

## Design decisions

- **Spacebar = play/pause only.** No tab switch. Works identically from every tab on the main game screen.
- **Footer label is contextual.** When advancing: `space` label reads "Pause". When paused: reads "Unpause". Signals that RTwP is the default state.
- **Gold Log tab indicator.** When a new tick entry arrives and the Log tab is not active, the Log tab label turns gold (same `discovered` CSS class used by entity tabs). Cleared when the user opens the Log tab.
- **Auto-pause on Log open.** Opt-in checkbox (default **off**) in the pause options. One-shot per visit: if RTwP is running when you open the Log tab and this option is enabled, auto-advance pauses.
- **No "Begin advancing when this menu opens" checkbox.** That intent is covered by spacebar from anywhere.
- **No "Exit" button.** The RTwP section is always visible at the bottom of the Log tab; spacebar pauses from anywhere.

---

## Phases

### Phase R1: LogTab bottom section — scaffold, checkboxes, gold indicator ✓ complete

- Move `_SPEED_SLOW`, `_SPEED_NORMAL`, `_SPEED_FAST` constants from `modals.py` to `widgets.py`
- Move `_PAUSE_CHECKBOX_MAP` (id → `PauseEventType`) from `modals.py` to `widgets.py`; add "pause-on-log-open" as a sentinel key (maps to `None` — handled separately)
- Add `PauseConfig`, `PauseEventType` to the `logic.tick_logic` import in `widgets.py`
- `LogTab.__init__` gains a `pause_config: PauseConfig` parameter; store as `self._pause_config`
- Add `self._has_unseen: bool = False` to `LogTab.__init__`
- `LogTab.compose()` gains a fixed bottom section after the `RichLog`:
  - `#log-rtwp` (`Vertical`, fixed height): two-column checkbox layout + time bar
  - Left column (`#log-pause-left`): Evaluation completes, Revelation threshold, Queued action completes, Pinned mortal dies — initial values from `pause_config.overrides` (default-on)
  - Right column (`#log-pause-right`): Pop splints, Domain threshold, Travel completes, Minor agent update — initial values from `pause_config.overrides` (default-off)
  - Pause-on-open row: `Checkbox("Pause when Log opens", id="pause-on-log-open", value=False)`
  - Time bar (`#log-time-bar`): `Slow | ▶ Play | +1 | Fast` — buttons present, no wiring yet
- `@on(Checkbox.Changed)` in `LogTab`: update `self._pause_config.overrides[event_type] = event.value` for the 8 trigger checkboxes; ignore `pause-on-log-open` (wired in R2)
- Add `refresh_play_button(is_playing: bool)` method: updates `#log-play` button label
- **Gold indicator:** define `LogTab.NewContent` message (no fields); `LogTab.append()` fires it once when `_has_unseen` transitions False → True; add `mark_seen()` method that clears `_has_unseen`
- **In `GameScreen`:** handle `on_log_tab_new_content` → add `discovered` to the Log tab button in `right-tabs`; in `_on_tab_activated`, if `pane_id == "log"` → call `log_tab.mark_seen()` and remove `discovered`
- Pass `self._state.pause_config` to `LogTab()` in `GameScreen.compose()`
- CSS in `styles.tcss` for `#log-rtwp`, `#log-pause-left`, `#log-pause-right`, `#log-time-bar`; `RichLog` (`#main-feed`) gets `height: 1fr` so it fills remaining space above the bottom section
- Autoplay regression; commit + push + Telegram

**Files:** `ui/widgets.py`, `ui/styles.tcss`, `ui/ui.py`

---

### Phase R2: Wire time bar + spacebar + auto-pause on Log open ✓ complete

- Define Textual message classes inside `LogTab`:
  - `LogTab.PlayPause` (no data)
  - `LogTab.Step` (no data)
  - `LogTab.SetSpeed` (field: `delay_s: float`)
- Wire button handlers in `LogTab` via `@on(Button.Pressed)`:
  - `#log-slow` → post `SetSpeed(_SPEED_SLOW)`
  - `#log-play` → post `PlayPause()`
  - `#log-step` → post `Step()`
  - `#log-fast` → post `SetSpeed(_SPEED_FAST)`
- Handle messages in `GameScreen`:
  - `on_log_tab_play_pause` → `self.action_toggle_auto_advance()`
  - `on_log_tab_step` → `self.action_advance_tick()` only if not auto-advancing
  - `on_log_tab_set_speed` → `self._auto_advance_delay_s = event.delay_s`
- Update `action_toggle_auto_advance` to call `self.query_one(LogTab).refresh_play_button(self._auto_advance)` after toggling
- Also call `refresh_play_button` in `_advance_tick_work` at both `self._auto_advance = False` sites (pause-event stop and terminal-condition stop), via `call_from_thread`
- **Spacebar binding:** change `GameScreen` binding description from `"RTwP"` to `"Unpause"` initially; after each toggle, call `self.app.bind("space", "rtwp", description="Pause" if self._auto_advance else "Unpause")` + `self.refresh_bindings()`; rename `action_open_rtwp_modal` → `action_rtwp` (just calls `action_toggle_auto_advance`)
- **Auto-pause on Log open:** in `_on_tab_activated`, if `pane_id == "log"` and `self._auto_advance` and `pause_on_log_open` checkbox is checked → call `action_toggle_auto_advance()`; read checkbox value via `self.query_one("#pause-on-log-open", Checkbox).value`
- Autoplay regression; commit + push + Telegram

**Files:** `ui/widgets.py`, `ui/ui.py`

---

### Phase R3: Remove RTwPModal + cleanup

- Delete `RTwPModal` class from `modals.py` (from `_SPEED_*` constants to end of file)
- Remove the `_feed_markup` forwarding block from `GameScreen._feed_markup` (`isinstance(self.app.screen, RTwPModal)` check)
- Remove `action_open_rtwp_modal` from `ui.py` (replaced by `action_rtwp` in R2)
- Remove `RTwPModal` from `modals.py` import in `ui.py`
- Remove from `modals.py` imports: `Checkbox`, `PauseConfig`, `PauseEventType` (no longer used there)
- Remove `from ui.ui import GameScreen` from `modals.py` TYPE_CHECKING block
- Remove all RTwP modal CSS from `styles.tcss`:
  - `RTwPModal`, `#rtwp-layout`, `#rtwp-left-spacer`, `#rtwp-right-spacer`
  - `#rtwp-body`, `#rtwp-log`, `#rtwp-pauses`
  - `#rtwp-pause-columns`, `#rtwp-pause-left`, `#rtwp-pause-right`
  - `#rtwp-time-bar` (old modal rule), `#pause-autostart`
- Autoplay regression; commit + push + Telegram

**Files:** `ui/modals.py`, `ui/ui.py`, `ui/styles.tcss`

---

## Files affected

- `ui/widgets.py` — `LogTab` gains pause_config param, bottom section, message classes, button wiring, `refresh_play_button`, gold indicator machinery
- `ui/ui.py` — `GameScreen.compose()` passes `pause_config`; `action_rtwp` replaces `action_open_rtwp_modal`; message handlers; `refresh_play_button` callsites; footer label updates; gold Log tab handling
- `ui/modals.py` — `RTwPModal` and associated constants removed; imports cleaned
- `ui/styles.tcss` — modal CSS removed; Log tab RTwP section CSS added

## Notes

- No changes to `logic/`, `core/`, or persistence — pure UI refactor.
- `action_toggle_auto_advance` on `GameScreen` is kept as-is; `action_rtwp` calls it.
- Phase 5 (modal) work on `rtwp` branch is superseded by this plan; overwriting on the same branch.
- `pause-on-log-open` checkbox default is **off** — opt-in behavior.
