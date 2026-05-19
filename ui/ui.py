"""
Textual UI for the Demiurge simulation: LoadScreen, GameScreen, DemiurgeApp.

This is the primary UI file — the home for the three screens that drive the
session. Modals and custom widgets live in sibling modules (ui.modals,
ui.widgets). Display helpers (formatters, snapshot renderers) live in
display.py at the project root.
"""
from __future__ import annotations
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import UUID

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import (
    Button, Footer, Header, Input, Label, ListItem, ListView, Static,
    TabbedContent, TabPane,
)
from textual.containers import Horizontal, Vertical, ScrollableContainer

from core.action_core import (
    ActionCategory, ActionDefinition, ActionInstance, OngoingAction, TargetType,
    WhisperIntent, OmenIntent, ProbabilityNudgeIntent, DevelopmentIntent,
    ProxiusDirectiveIntent, LuminaryPetitionIntent, EssenceHarvestIntent,
    SalvageIntent, SeedWorldIntent, UpliftSpeciesIntent, ExploreBeliefIntent,
    RevealImagoIntent, CommissionInquiryIntent, ChangeAffiliatedDomainsIntent,
    ScryIntent, ScryScope, DomainVector, Framing,
)
from core.universe_core import (
    MortalRole, MortalStatus, MortalProminence, PopLocation,
)
from logic.tick_logic import (
    SimulationState, TickLoop, is_in_window, ENTITY_VISIBILITY_FLOOR,
    _compute_revelation_cap, _revelation_adjusted_cost,
)
from utilities.domain_registry import get_registry as get_domain_registry
from utilities.imago_registry import get_registry as get_imago_registry
from utilities.scenario_loader import load_scenario, validate_luminary_affinities
from utilities.scenario_exporter import export_scenario

from ui import display
from ui.display import (
    display_state, display_briefing, display_tick_result,
    display_tick_result_categorized,
    _strip_oow, _name_for_id, _personality_label, _wrap_desc, _short_tag,
    _pop_stratum_label,
)

from ui.constants import BACK, _SAVES_DIR, _SCENARIOS_DIR, _LOGS_DIR
from ui.widgets import (
    StatusPanel, LoopingListView,
    LocationsTab, EntitiesTab, ActionsTab,
    BriefingTab, UniverseTab, LuminariesTab, LogTab,
    DivineWisdomTab,
    set_unseen_predicate,
)
from ui.detail_tabs import DetailTabManager
from ui.session_log import SessionLog
from ui.modals import (
    ErrorModal, ToastModal, PickerModal, PopLatitudePickerModal, YesNoModal,
    QuitConfirmModal,
    TextFormModal, DomainPickerModal, ImagoTreeModal, ImagoDetailModal,
    ImagoRevealModal, ImagoRevealDetailModal, MortalDetailModal,
    ActionBrowserModal,
)


# ─────────────────────────────────────────
# Local helper: peek scenario/save DB metadata
# (Used only by LoadScreen; not worth its own module.)
# ─────────────────────────────────────────

def _peek_db_meta(path: Path) -> dict:
    try:
        with sqlite3.connect(path) as c:
            row = c.execute(
                "SELECT name, description, tick_number FROM scenario_meta LIMIT 1"
            ).fetchone()
        if row:
            return {
                "name":        row[0] or path.stem,
                "description": row[1] or "",
                "tick_number": row[2] if row[2] is not None else 0,
            }
    except Exception:
        pass
    return {"name": path.stem, "description": "", "tick_number": 0}


# ─────────────────────────────────────────
# LOAD SCREEN
# ─────────────────────────────────────────

class LoadScreen(Screen):
    """Startup screen: lists saves and scenarios."""

    BINDINGS = [("q", "quit_app", "Quit")]

    def compose(self) -> ComposeResult:
        saves     = sorted(_SAVES_DIR.glob("*.db"))     if _SAVES_DIR.exists()     else []
        scenarios = sorted(_SCENARIOS_DIR.glob("*.db")) if _SCENARIOS_DIR.exists() else []

        with Vertical(classes="load-box"):
            yield Label("DEMIURGE", classes="load-title")
            with ScrollableContainer():
                with LoopingListView(id="load-list"):
                    if saves:
                        yield ListItem(Label("── SAVES ──", classes="load-section"), disabled=True)
                        for path in saves:
                            meta = _peek_db_meta(path)
                            desc_wrapped = _wrap_desc(meta["description"])
                            label_text   = f"{meta['name']}\n{desc_wrapped}" if desc_wrapped else meta["name"]
                            yield ListItem(
                                Label(label_text),
                                id=f"file-{path.stem}",
                                name=str(path),
                            )
                    if scenarios:
                        yield ListItem(Label("── SCENARIOS ──", classes="load-section"), disabled=True)
                        for path in scenarios:
                            meta = _peek_db_meta(path)
                            desc_wrapped = _wrap_desc(meta["description"])
                            label_text   = f"{meta['name']}\n{desc_wrapped}" if desc_wrapped else meta["name"]
                            yield ListItem(
                                Label(label_text),
                                id=f"file-{path.stem}",
                                name=str(path),
                            )
                    if not saves and not scenarios:
                        yield ListItem(Label("(no saves or scenarios found)"), disabled=True)

    def on_mount(self) -> None:
        self.query_one("#load-list", ListView).focus()

    @on(ListView.Selected)
    def _on_selected(self, event: ListView.Selected) -> None:
        path_str = event.item.name
        if not path_str:
            return
        path = Path(path_str)
        state = load_scenario(path)
        violations = validate_luminary_affinities(state)
        if violations:
            msg = "Scenario rejected — Luminary affinity constraints violated:\n\n"
            msg += "\n".join(f"  • {v}" for v in violations)
            self.app.push_screen(ErrorModal(msg))
            return
        self.app.push_screen(GameScreen(state))

    def action_quit_app(self) -> None:
        self.app.exit()


# ─────────────────────────────────────────
# GAME SCREEN
# ─────────────────────────────────────────

class GameScreen(Screen):
    BINDINGS = [
        ("b",      "briefing",        "Briefing"),
        ("s",      "show_state",      "State"),
        ("a",      "queue_action",    "Queue"),
        ("o",      "manage_ongoing",  "Ongoing"),
        ("t",      "advance_tick",    "Advance"),
        ("ctrl+s", "save_game",       "Save"),
        ("q",      "quit_confirm",    "Quit"),
        ("ctrl+q", "quit_immediate",  "Force quit"),
        # Tab switching: digits for left, ctrl+digits for right.
        ("1", "left_tab('status')",      "Status"),
        ("2", "left_tab('locations')",   "Locs"),
        ("3", "left_tab('entities')",    "Ents"),
        ("4", "left_tab('actions')",     "Acts"),
        ("ctrl+1", "right_tab('briefing')",   ""),
        ("ctrl+2", "right_tab('universe')",   ""),
        ("ctrl+3", "right_tab('luminaries')", ""),
        ("ctrl+4", "right_tab('divine_wisdom')", ""),
        ("ctrl+5", "right_tab('log')",        ""),
        # Detail-tab controls (Phase 2).
        ("escape",     "close_detail",   "Close"),
        ("ctrl+p",     "pin_detail",     "Pin"),
        ("alt+left",   "back_detail",    "Back"),
    ]

    # Map from a left/right tab pane id to the entity kinds whose discoveries
    # should highlight that tab's title and entries.
    _TAB_DISCOVERY_KINDS = {
        "locations": ("world", "system", "galaxy"),
        "entities":  ("civ",),
        "universe":  ("world", "civ", "mortal", "pop", "species"),
    }

    def __init__(self, state: SimulationState):
        super().__init__()
        self._state = state
        self._briefing_open: bool = True
        self._detail_mgr: DetailTabManager | None = None
        # Newly-discovered entity IDs since the last time their tab was accessed.
        self._unseen_by_kind: dict[str, set[str]] = {
            "world": set(), "system": set(), "galaxy": set(),
            "civ": set(), "mortal": set(), "pop": set(), "species": set(),
        }
        # Tab pane IDs whose unseen sets should be cleared on the next refresh
        # (set when the user activates the tab; the active render still shows gold).
        self._pending_clear: set[str] = set()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal():
            with TabbedContent(id="left-tabs", initial="status"):
                with TabPane("Status", id="status"):
                    yield StatusPanel(id="status-panel")
                with TabPane("Locations", id="locations"):
                    yield LocationsTab()
                with TabPane("Entities", id="entities"):
                    yield EntitiesTab()
                with TabPane("Actions", id="actions"):
                    yield ActionsTab()
            with TabbedContent(id="right-tabs", initial="briefing"):
                with TabPane("Briefing", id="briefing"):
                    yield BriefingTab()
                with TabPane("Universe", id="universe"):
                    yield UniverseTab()
                with TabPane("Luminaries", id="luminaries"):
                    yield LuminariesTab()
                with TabPane("Divine Wisdom", id="divine_wisdom"):
                    yield DivineWisdomTab()
                with TabPane("Log", id="log"):
                    yield LogTab()
        yield Footer()

    def on_mount(self) -> None:
        self._last_result = None
        _LOGS_DIR.mkdir(exist_ok=True)
        log_path = _LOGS_DIR / f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        self._log = SessionLog(log_path)
        # Initialise the detail-tab manager once the right TabbedContent exists.
        self._detail_mgr = DetailTabManager(
            self, self.query_one("#right-tabs", TabbedContent),
        )
        # Render all tabs from the initial state.
        self._refresh_all()
        # Plain-text session log still receives the full briefing + state snapshot.
        briefing_lines = display_briefing(self._state, dev_mode=display.DEV_MODE)
        self._log.write(_strip_oow(briefing_lines))
        state_lines = display_state(self._state, dev_mode=display.DEV_MODE)
        self._log.write(_strip_oow(state_lines))
        # Quiet header message in the Log tab.
        self._feed_markup(f"[#2a4a6a]Logging to: {log_path}[/]")

    # ── Display helpers ───────────────────────

    def _feed_markup(self, markup: str, category: str = "other") -> None:
        """Append a line to the Log tab, tagged with a chip-filter category."""
        try:
            self.query_one(LogTab).append(category, markup)
        except Exception:
            # Log tab not yet mounted (e.g. very early in startup).
            pass

    def _refresh_status(self) -> None:
        """Compat alias — refreshes every tab and the subtitle."""
        self._refresh_all()

    def _refresh_all(self) -> None:
        """Re-render every mounted tab body from the current state."""
        state = self._state
        # Install the predicate widgets._click_link consults for gold highlighting.
        set_unseen_predicate(
            lambda kind, eid: eid in self._unseen_by_kind.get(kind, ())
        )
        self.app.sub_title = (
            f"{state.universe.name}  ·  Age {state.universe.current_age:.1f}  ·  Tick {state.tick_number}"
        )
        self.query_one(StatusPanel).refresh_state(state, self.app.loop)
        self.query_one(LocationsTab).refresh_state(state)
        self.query_one(EntitiesTab).refresh_state(state)
        self.query_one(ActionsTab).refresh_state(state, self.app.loop)
        if self._briefing_open:
            briefing = self.query(BriefingTab)
            if briefing:
                briefing.first().refresh_state(state)
        self.query_one(UniverseTab).refresh_state(state)
        self.query_one(LuminariesTab).refresh_state(state)
        self.query_one(DivineWisdomTab).refresh_state(state)
        if self._detail_mgr is not None:
            self._detail_mgr.refresh_all(state)
        self._refresh_tab_discovery_styles()

    def _refresh_tab_discovery_styles(self) -> None:
        """Toggle the `discovered` class on tabs whose unseen sets are non-empty."""
        left  = self.query_one("#left-tabs", TabbedContent)
        right = self.query_one("#right-tabs", TabbedContent)
        for pane_id, kinds in self._TAB_DISCOVERY_KINDS.items():
            has = any(self._unseen_by_kind.get(k) for k in kinds)
            tabbed = right if pane_id == "universe" else left
            try:
                tab = tabbed.get_tab(pane_id)
            except Exception:
                continue
            if has:
                tab.add_class("discovered")
            else:
                tab.remove_class("discovered")

    @on(TabbedContent.TabActivated)
    def _on_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        # Schedule discovery clear on next refresh; this render still shows gold.
        pane_id = event.pane.id if event.pane else None
        if pane_id in self._TAB_DISCOVERY_KINDS:
            self._pending_clear.add(pane_id)
            try:
                event.tab.remove_class("discovered")
            except Exception:
                pass

    def _record_discoveries(self, before_ids: dict[str, set[str]]) -> None:
        """Diff in-Window IDs before/after a tick to populate unseen sets."""
        # Apply deferred clears from tab activations *before* recording this
        # tick's discoveries, so newly revealed IDs aren't wiped by a pending
        # clear scheduled before the tick.
        for pane_id in self._pending_clear:
            for kind in self._TAB_DISCOVERY_KINDS.get(pane_id, ()):
                self._unseen_by_kind[kind].clear()
        self._pending_clear.clear()
        after = self._current_window_ids()
        for kind, ids_after in after.items():
            new_ids = ids_after - before_ids.get(kind, set())
            if new_ids:
                self._unseen_by_kind[kind] |= new_ids

    def _current_window_ids(self) -> dict[str, set[str]]:
        s = self._state
        return {
            "world":  {eid for eid, w in s.worlds.items() if is_in_window(w)},
            "system": {eid for eid, sy in s.systems.items() if is_in_window(sy)},
            "galaxy": {eid for eid, g in s.galaxies.items() if is_in_window(g)},
            "civ":    {eid for eid, c in s.civilizations.items() if is_in_window(c)},
            "mortal": {eid for eid, m in s.mortals.items()
                       if m.status != MortalStatus.DECEASED
                       and (m.pinned or m.visibility > ENTITY_VISIBILITY_FLOOR)},
            "pop":     {eid for eid, p in s.pops.items() if is_in_window(p)},
            "species": {eid for eid, sp in s.species.items() if is_in_window(sp)},
        }

    # ── Detail-tab integration ────────────────

    def open_detail(self, kind: str, entity_id, name: str) -> None:
        """Open (or re-focus) a detail tab. Public API used by click handlers."""
        if self._detail_mgr is None:
            return
        self._detail_mgr.open(kind, str(entity_id), name, self._state)

    def open_detail_by_id(self, kind: str, entity_id: str) -> None:
        """Resolve the entity name from current state and open its detail tab."""
        name = self._lookup_entity_name(kind, str(entity_id))
        self.open_detail(kind, entity_id, name)

    def action_open_detail_by_id(self, kind: str, entity_id: str) -> None:
        """Click-action target — fires from `[@click=...]` markup in tab bodies."""
        self.open_detail_by_id(kind, entity_id)

    def action_navigate_detail_by_id(self, kind: str, entity_id: str) -> None:
        """Click target emitted by links rendered inside a detail tab — push
        onto the active tab's history. Falls back to opening a new tab when
        no detail pane is active (e.g. clicked via keyboard during focus change)."""
        if self._detail_mgr is None or not self._detail_mgr.is_detail_pane_active():
            self.open_detail_by_id(kind, entity_id)
            return
        name = self._lookup_entity_name(kind, str(entity_id))
        self._detail_mgr.navigate_active(kind, str(entity_id), name, self._state)

    def action_detail_back_to_index(self, idx: str) -> None:
        """Breadcrumb-click target: jump active detail tab's history to index `idx`."""
        if self._detail_mgr is None:
            return
        try:
            i = int(idx)
        except (TypeError, ValueError):
            return
        self._detail_mgr.jump_active_to_index(i, self._state)

    def action_open_luminary(self, lum_id: str) -> None:
        """Switch to the Luminaries tab and show the detail view for one Luminary."""
        right = self.query_one("#right-tabs", TabbedContent)
        right.active = "luminaries"
        self.query_one(LuminariesTab).show_luminary(str(lum_id))

    def action_open_luminaries_list(self) -> None:
        """Breadcrumb target — return the Luminaries tab to list view."""
        right = self.query_one("#right-tabs", TabbedContent)
        right.active = "luminaries"
        self.query_one(LuminariesTab).show_list()

    def action_open_divine_wisdom(self, domain_tag: str = "") -> None:
        """Switch to the Divine Wisdom tab and (optionally) jump to a Domain tree."""
        right = self.query_one("#right-tabs", TabbedContent)
        right.active = "divine_wisdom"
        tab = self.query_one(DivineWisdomTab)
        if domain_tag:
            tab.show_domain(domain_tag)
        else:
            tab.show_list()

    def action_open_imago_node(self, node_id: str) -> None:
        """Switch to the Divine Wisdom tab and show a specific Imago node."""
        right = self.query_one("#right-tabs", TabbedContent)
        right.active = "divine_wisdom"
        self.query_one(DivineWisdomTab).show_node(node_id)

    def _lookup_entity_name(self, kind: str, entity_id: str) -> str:
        s = self._state
        eid = str(entity_id)
        if kind == "world"    and eid in s.worlds:        return s.worlds[eid].name
        if kind == "system"   and eid in s.systems:       return s.systems[eid].name
        if kind == "galaxy"   and eid in s.galaxies:      return s.galaxies[eid].name
        if kind == "poploc"   and eid in s.locations:     return s.locations[eid].name
        if kind == "civ"      and eid in s.civilizations: return s.civilizations[eid].name
        if kind == "mortal"   and eid in s.mortals:       return s.mortals[eid].name
        if kind == "luminary" and eid in s.luminaries:    return s.luminaries[eid].name
        if kind == "species"  and eid in s.species:       return s.species[eid].name
        if kind == "pop"      and eid in s.pops:
            pop = s.pops[eid]
            stratum = _pop_stratum_label(pop)
            sp = s.species.get(str(pop.species_id)) if pop.species_id else None
            return f"{stratum} ({sp.name})" if sp else f"{stratum} Pop"
        return eid[:8]

    def action_close_detail(self) -> None:
        # Close a focused detail tab, or the Briefing tab if it's the one active.
        right = self.query_one("#right-tabs", TabbedContent)
        if right.active == "briefing" and self._briefing_open:
            self._close_briefing()
            return
        if self._detail_mgr is not None:
            self._detail_mgr.close_focused()

    def action_pin_detail(self) -> None:
        if self._detail_mgr is None:
            return
        ok, msg = self._detail_mgr.toggle_pin_focused(self._state)
        if not ok:
            self._feed_markup(f"[#c09030]{msg}[/]")

    def action_back_detail(self) -> None:
        if self._detail_mgr is None:
            return
        self._detail_mgr.back_focused(self._state)

    # ── Tab actions ───────────────────────────

    def action_left_tab(self, pane_id: str) -> None:
        self.query_one("#left-tabs", TabbedContent).active = pane_id

    def action_right_tab(self, pane_id: str) -> None:
        if pane_id == "briefing" and not self._briefing_open:
            self._open_briefing()
            return
        self.query_one("#right-tabs", TabbedContent).active = pane_id

    def _open_briefing(self) -> None:
        """Re-add the Briefing pane (it had been closed) and activate it."""
        right = self.query_one("#right-tabs", TabbedContent)
        pane = TabPane("Briefing", BriefingTab(), id="briefing")
        right.add_pane(pane, before="universe")
        self._briefing_open = True
        # The new pane mounts on the next event-loop turn; defer the render.
        self.call_after_refresh(self._post_open_briefing)

    def _post_open_briefing(self) -> None:
        try:
            self.query_one(BriefingTab).refresh_state(self._state)
        except Exception:
            pass
        self.query_one("#right-tabs", TabbedContent).active = "briefing"

    def _close_briefing(self) -> None:
        right = self.query_one("#right-tabs", TabbedContent)
        right.remove_pane("briefing")
        self._briefing_open = False
        right.active = "universe"

    # ── Actions (keyboard bindings) ───────────

    def action_briefing(self) -> None:
        """Toggle the Briefing tab — closed becomes opened, open becomes closed."""
        if self._briefing_open:
            self._close_briefing()
        else:
            self._open_briefing()

    def action_show_state(self) -> None:
        """Switch focus to the Universe tab (was: dump snapshot to the log)."""
        self.query_one("#right-tabs", TabbedContent).active = "universe"

    def action_queue_action(self) -> None:
        self._queue_action_flow()

    def action_manage_ongoing(self) -> None:
        self._manage_ongoing_flow()

    @work
    async def _manage_ongoing_flow(self) -> None:
        state   = self._state
        library = self.app.loop._action_library  # type: ignore[attr-defined]
        if not state.ongoing_actions:
            self._feed_markup("[#5a7090]No ongoing actions.[/]", "actions")
            return
        items = []
        for cat_val, oa in state.ongoing_actions.items():
            defn  = library.get(oa.action_key)
            name  = defn.name if defn else oa.action_key
            label = cat_val.replace("_", " ").title()
            items.append((cat_val, f"[{label}] {name}  ({oa.executed_ticks}/{oa.ticks_active})"))
        chosen = await self.app.push_screen_wait(PickerModal("Ongoing Actions", items))
        if chosen and chosen in state.ongoing_actions:
            confirmed = await self.app.push_screen_wait(
                YesNoModal(f"Stop this ongoing action?")
            )
            if confirmed:
                oa   = state.ongoing_actions.pop(chosen)
                defn = library.get(oa.action_key)
                name = defn.name if defn else oa.action_key
                # Clear the Proxius's active goal when a preach_imago is stopped,
                # and clean up any goal Pop (Pop B) that was being grown.
                if oa.action_key == "preach_imago" and oa.proxius_id:
                    proxius = state.mortals.get(str(oa.proxius_id))
                    if proxius and proxius.active_goal:
                        old_goal = proxius.active_goal
                        proxius.active_goal = None
                        if old_goal.goal_pop_id:
                            goal_pop = state.pops.get(str(old_goal.goal_pop_id))
                            if goal_pop:
                                goal_pop.preaching_imago_id = None
                                goal_pop.pinned = False
                                goal_pop.preaching_goal_cooldown_until = state.tick_number
                    elif proxius:
                        proxius.active_goal = None
                self._feed_markup(f"[#c09030]Stopped ongoing:[/] {name}", "actions")
                self._refresh_status()

    def action_advance_tick(self) -> None:
        self._advance_tick_work()

    @work(thread=True)
    def _advance_tick_work(self) -> None:
        state = self._state
        loop  = self.app.loop   # type: ignore[attr-defined]
        before_ids = self._current_window_ids()
        self.app.call_from_thread(self._feed_markup, "[#3a6090]Advancing time...[/]", "other")
        new_state, result = loop.advance(state)
        self._state = new_state
        self._last_result = result
        self.app.call_from_thread(self._record_discoveries, before_ids)
        categorized = display_tick_result_categorized(result, dev_mode=display.DEV_MODE)
        self._log.write_tick(result)
        self.app.call_from_thread(self._feed_categorized, categorized)
        self.app.call_from_thread(self._refresh_status)
        # After each tick, surface the freshly-written log so the player sees
        # the tick result without having to switch tabs manually, and snap the
        # left panel to Status for an at-a-glance numbers check.
        self.app.call_from_thread(self._activate_post_tick_tabs)
        if result.terminal.triggered:
            self._log.finalize(new_state, result)
            self.app.call_from_thread(
                self._feed_markup,
                f"[bold #b04050]SCENARIO END: {result.terminal.condition.value.upper()}[/]\n"
                f"{result.terminal.note}",
                "other",
            )

    def _feed_categorized(self, categorized: list[tuple[str, str]]) -> None:
        for cat, line in categorized:
            self._feed_markup(line, cat)

    def _activate_post_tick_tabs(self) -> None:
        try:
            self.query_one("#right-tabs", TabbedContent).active = "log"
        except Exception:
            pass
        try:
            self.query_one("#left-tabs", TabbedContent).active = "status"
        except Exception:
            pass

    def action_save_game(self) -> None:
        self._save_game_flow()

    @work
    async def _save_game_flow(self) -> None:
        state = self._state
        _SAVES_DIR.mkdir(exist_ok=True)
        dt      = datetime.now().strftime("%Y%m%d%H%M%S")
        default = f"{state.universe.save_name}_{dt}"
        form = await self.app.push_screen_wait(
            TextFormModal("Save Game", [("Save name", "name", default)])
        )
        if form is None:
            return
        name = form["name"].strip() or default
        db_path = _SAVES_DIR / f"{name}.db"
        if db_path.exists():
            overwrite = await self.app.push_screen_wait(
                YesNoModal(f"'{name}.db' already exists", "Overwrite?")
            )
            if not overwrite:
                self._feed_markup("[#5a7090]Save cancelled.[/]")
                return
        description = f"Tick {state.tick_number}  |  Age {state.universe.current_age:.1f}"
        export_scenario(state, db_path, scenario_name=name, description=description)
        self._feed_markup(f"[#50b870]Saved to saves/{name}.db[/]")

    def action_quit_confirm(self) -> None:
        self._quit_confirm_flow()

    def action_quit_immediate(self) -> None:
        """Ctrl+Q — skip the modal, finalise the session log, exit."""
        self._log.finalize(self._state, self._last_result)
        self.app.exit()

    @work
    async def _quit_confirm_flow(self) -> None:
        choice = await self.app.push_screen_wait(QuitConfirmModal())
        if choice is None:
            return  # Keep playing
        if choice == "save":
            state = self._state
            _SAVES_DIR.mkdir(exist_ok=True)
            dt = datetime.now().strftime("%Y%m%d%H%M%S")
            name = f"{state.universe.save_name}_{dt}"
            db_path = _SAVES_DIR / f"{name}.db"
            description = (
                f"Tick {state.tick_number}  |  Age {state.universe.current_age:.1f}"
            )
            export_scenario(state, db_path, scenario_name=name, description=description)
            self._feed_markup(f"[#50b870]Saved to saves/{name}.db[/]")
        self._log.finalize(self._state, self._last_result)
        self.app.exit()

    # ── Action queue flow ─────────────────────

    @work
    async def _queue_action_flow(self) -> None:
        app     = self.app
        state   = self._state
        library = app.loop._action_library  # type: ignore[attr-defined]

        while True:
            # Browse and pick action
            picked = await app.push_screen_wait(ActionBrowserModal(state, library))
            if picked is None:
                return
            action_key, defn = picked

            # Essence affordability check — before submenus
            if defn.essence_cost > 0:
                key_by_id = app.loop._action_key_by_id  # type: ignore[attr-defined]
                committed = sum(
                    library[key].essence_cost
                    for ai in state.action_queue
                    if (key := key_by_id.get(str(ai.action_definition_id)))
                    and library.get(key) is not None
                    and library[key].essence_cost > 0
                ) + sum(
                    library[oa.action_key].essence_cost
                    for oa in state.ongoing_actions.values()
                    if library.get(oa.action_key) is not None
                    and library[oa.action_key].essence_cost > 0
                )
                available = state.essence.actual - committed
                if defn.essence_cost > available:
                    committed_str = f" − {committed:.2f} committed" if committed > 0 else ""
                    await app.push_screen_wait(ToastModal(
                        f"Insufficient Essence.\n\n"
                        f"  Cost:      {defn.essence_cost:.1f}\n"
                        f"  Available: {available:.2f}\n"
                        f"  (stockpile {state.essence.actual:.2f}{committed_str})"
                    ))
                    continue

            # Build intent; BACK means "re-show action browser"
            instance = await self._build_intent(action_key, defn)
            if instance is None:
                self._feed_markup("[#5a7090]Cancelled.[/]", "actions")
                return
            if instance == BACK:
                continue
            break

        # Offer persistence for eligible actions
        if "can_persist" in defn.tags:
            make_persistent = await app.push_screen_wait(
                YesNoModal(
                    f"Make '{defn.name}' persistent?",
                    "It will auto-execute each tick until you stop it.",
                )
            )
            if make_persistent:
                state.ongoing_actions[defn.category.value] = OngoingAction(
                    action_key=action_key,
                    action_definition_id=defn.id,
                    target_type=instance.target_type,
                    target_id=instance.target_id,
                    proxius_id=instance.proxius_id,
                    intent=instance.intent,
                    ticks_active=0,
                    started_at_tick=state.tick_number,
                )
                self._log.write_action(f"[ONGOING SET] {defn.name}")
                self._feed_markup(f"[#60a870][ONGOING SET][/] {defn.name}", "actions")
                self._refresh_status()
                self._focus_actions_tab()
                return

        state.action_queue.append(instance)
        summary = defn.name
        if instance.target_id:
            summary += f" → {_name_for_id(instance.target_id, state)}"
        self._log.write_action(summary)
        self._feed_markup(f"[#a0d080]Queued:[/] {summary}", "actions")
        self._refresh_status()
        self._focus_actions_tab()

    def _focus_actions_tab(self) -> None:
        try:
            self.query_one("#left-tabs", TabbedContent).active = "actions"
        except Exception:
            pass

    # ── Intent construction ───────────────────

    async def _build_intent(
        self,
        action_key: str,
        defn: ActionDefinition,
    ) -> "ActionInstance | str | None":
        """
        Returns ActionInstance on success, BACK to re-show action browser, or None to cancel.
        """
        app   = self.app
        state = self._state

        target_type = defn.valid_targets[0] if defn.valid_targets else TargetType.WORLD

        # ── commission_inquiry: proxius picker → domain picker ──
        if action_key == "commission_inquiry":
            result = await self._pick_proxius(state, include_dormant=False)
            if result is None: return None
            if result == BACK: return BACK
            proxius_id = UUID(result)
            proxius = state.mortals.get(result)
            dreg = get_domain_registry()
            capped = {
                tag for tag in dreg.all_tags
                if _compute_revelation_cap(state, tag) == 0.0
                or state.demiurge.revelation_pools.get(tag, 0.0) >= _compute_revelation_cap(state, tag)
            }
            tag = await self.app.push_screen_wait(
                DomainPickerModal(state, capped_domains=capped)
            )
            if tag is None: return None
            if tag == BACK: return None
            if not tag: return None
            intent = CommissionInquiryIntent(proxius_id=proxius_id, domain_tag=tag)
            return ActionInstance(
                action_definition_id=defn.id,
                target_type=TargetType.MORTAL,
                target_id=proxius_id,
                timestamp=state.universe.current_age,
                demiurge_id=state.demiurge.id,
                proxius_id=proxius_id,
                intent=intent,
            )

        # ── preach_imago: multi-step (proxius → domain/imago → pop) ──
        if action_key == "preach_imago":
            already_directed = {
                str(ai.proxius_id)
                for ai in state.action_queue
                if isinstance(ai.intent, ProxiusDirectiveIntent)
                and ai.proxius_id is not None
            }
            step = 0
            pid = None
            dvs: list = []; imago_id = None
            target_civ_id = None
            target_pop_id = None
            while True:
                if step == 0:
                    result = await self._pick_proxius(
                        state, include_dormant=True, already_directed=already_directed,
                    )
                    if result is None: return None
                    if result == BACK: return BACK
                    pid = result; step = 1
                if step == 1:
                    domain_result = await self._pick_domain_and_imago(state)
                    if domain_result is None: return None
                    if domain_result == BACK: step = 0; continue
                    dvs, imago_id = domain_result; step = 2
                if step == 2:
                    target_civ_id = None
                    target_pop_id = None
                    proxius_obj   = state.mortals.get(pid)
                    # proxius.current_location is a PopLocation now — resolve
                    # to its parent world so child_ids iteration finds sibling PopLocs.
                    from logic.tick_logic import _resolve_world_id_for
                    world_id      = _resolve_world_id_for(state, proxius_obj.current_location) if proxius_obj else None
                    origin_pop_id = str(proxius_obj.pop_id) if (proxius_obj and proxius_obj.pop_id) else None

                    world_obj = state.locations.get(world_id) if world_id else None
                    all_world_pops: list = []
                    for child_id in getattr(world_obj, "child_ids", []):
                        child = state.locations.get(str(child_id))
                        if isinstance(child, PopLocation):
                            for pop_id_val in getattr(child, "pop_ids", []):
                                p = state.pops.get(str(pop_id_val))
                                if p is not None:
                                    all_world_pops.append(p)

                    eligible_pops = [
                        p for p in all_world_pops
                        if (is_in_window(p) or str(p.id) == origin_pop_id)
                        and p.preaching_imago_id is None
                        and p.preaching_goal_cooldown_until <= state.tick_number
                    ]

                    if not eligible_pops:
                        self._feed_markup(
                            "[#5a7090]No visible, targetable Pops at this location. "
                            "Scry the world to reveal Pops first.[/]",
                            "actions",
                        )
                        step = 1; continue

                    proxius_civ_id = (
                        str(state.pops[origin_pop_id].civilization_id)
                        if origin_pop_id and origin_pop_id in state.pops
                        and state.pops[origin_pop_id].civilization_id is not None
                        else None
                    )

                    def _pop_label(p) -> str:
                        civ = state.civilizations.get(str(p.civilization_id)) if p.civilization_id else None
                        civ_name = civ.name if civ else "Unknown"
                        cross = " [foreign]" if proxius_civ_id and str(p.civilization_id) != proxius_civ_id else ""
                        origin_marker = " *" if str(p.id) == origin_pop_id else ""
                        top_beliefs = sorted(
                            p.dominant_beliefs.items(), key=lambda x: -x[1]
                        )[:2]
                        belief_str = "  ".join(
                            f"{_short_tag(tag)}:{val:.2f}" for tag, val in top_beliefs
                        ) if top_beliefs else "no beliefs"
                        return (
                            f"{civ_name} [{p.stratum.upper()}]{cross}{origin_marker}"
                            f"  size {p.size_magnitude}  {belief_str}"
                        )

                    pop_items = [(str(p.id), _pop_label(p)) for p in eligible_pops]
                    pop_result = await app.push_screen_wait(
                        PopLatitudePickerModal("Preach to which community?", pop_items, show_back=True)
                    )
                    if pop_result == BACK: step = 1; continue
                    if pop_result is None: return None
                    chosen_pop, chosen_latitude = pop_result
                    chosen_obj = next((p for p in eligible_pops if str(p.id) == chosen_pop), None)
                    if chosen_obj:
                        target_pop_id = chosen_obj.id
                        target_civ_id = chosen_obj.civilization_id
                    break
            intent = ProxiusDirectiveIntent(
                domain_vectors=dvs,
                latitude=chosen_latitude,
                target_civilization_id=target_civ_id,
                target_pop_id=target_pop_id,
                imago_node_id=imago_id,
            )
            return ActionInstance(
                action_definition_id=defn.id,
                target_type=TargetType.MORTAL,
                target_id=UUID(pid),
                timestamp=state.universe.current_age,
                demiurge_id=state.demiurge.id,
                proxius_id=UUID(pid),
                intent=intent,
            )

        # ── Other proxius-targeted actions (no intent params) ──
        if defn.requires_proxius:
            result = await self._pick_proxius(
                state,
                include_dormant="include_dormant_proxius" in defn.tags,
            )
            if result is None: return None
            if result == BACK: return BACK
            proxius_id = UUID(result)
            return ActionInstance(
                action_definition_id=defn.id,
                target_type=TargetType.MORTAL,
                target_id=proxius_id,
                timestamp=state.universe.current_age,
                demiurge_id=state.demiurge.id,
                proxius_id=proxius_id,
                intent=None,
            )

        # ── Scry: scope → target picker loop ──
        if action_key == "scry":
            scope_items = [
                (ScryScope.WORLD.value,    "World       — deep mortal/civ detail  (0.05 subtle)"),
                (ScryScope.SYSTEM.value,   "System      — reveals worlds & civs   (0.10 subtle)"),
                (ScryScope.GALAXY.value,   "Galaxy      — broad survey            (0.20 subtle  0.3 Ess)"),
                (ScryScope.UNIVERSE.value, "Universe    — cosmos-wide sweep       (0.35 subtle  0.5 Ess)"),
            ]
            target_id = None
            while True:
                picked_scope = await app.push_screen_wait(
                    PickerModal("Scry Scope", scope_items, show_back=True)
                )
                if picked_scope is None: return None
                if picked_scope == BACK: return BACK
                chosen_scope = ScryScope(picked_scope)
                if chosen_scope == ScryScope.WORLD:
                    target_id, target_type = await self._pick_world(state)
                    if target_id is None: return None
                    if target_id == BACK: continue
                elif chosen_scope == ScryScope.SYSTEM:
                    target_id, target_type = await self._pick_system(state)
                    if target_id is None: return None
                    if target_id == BACK: continue
                elif chosen_scope == ScryScope.GALAXY:
                    target_id, target_type = await self._pick_galaxy(state)
                    if target_id is None: return None
                    if target_id == BACK: continue
                else:
                    target_id = None
                    target_type = TargetType.UNIVERSE
                break
            return ActionInstance(
                action_definition_id=defn.id,
                target_type=target_type,
                target_id=target_id,
                timestamp=state.universe.current_age,
                demiurge_id=state.demiurge.id,
                proxius_id=None,
                intent=ScryIntent(scope=chosen_scope),
            )

        # ── Target selection by type, with back-from-params loop ──
        _NO_PARAMS = (
            "appoint_proxius", "empower_proxius", "dismiss_proxius",
            "go_quiet_proxius", "audit_proxius", "maintain_concealment",
            "ask_for_orders",
        )

        if TargetType.MORTAL in defn.valid_targets:
            _proxius_ids = {str(pid) for pid in state.demiurge.proxius_ids}
            mortals = [
                (mid, m) for mid, m in state.mortals.items()
                if (m.status != MortalStatus.DECEASED and (m.pinned or m.visibility > ENTITY_VISIBILITY_FLOOR))
                and m.role not in (MortalRole.PROXIUS, MortalRole.HERALD)
                and mid not in _proxius_ids
            ]
            if not mortals:
                self._feed_markup("[#5a7090]No mortals currently within perception.[/]", "actions")
                return None
            mortal_items = []
            for mid, m in mortals:
                w_obj    = state.locations.get(str(m.current_location))
                loc      = w_obj.name if w_obj else "?"
                role_str = m.role.value if m.role != MortalRole.OTHER else "mortal"
                sp_obj   = state.species.get(str(m.species_id)) if m.species_id else None
                sp_name  = sp_obj.name if sp_obj else "?"
                pop_obj  = state.pops.get(str(m.pop_id)) if m.pop_id else None
                pop_str  = f"  {_pop_stratum_label(pop_obj)}" if pop_obj else ""
                mortal_items.append((mid, f"{m.name:<18} [{role_str}]  {sp_name:<14}  align:{m.alignment:.2f}  {loc}{pop_str}"))
            intent = None
            while True:
                picked_id = await app.push_screen_wait(PickerModal("Select Mortal", mortal_items, show_back=True))
                if picked_id is None: return None
                if picked_id == BACK: return BACK
                target_id = UUID(picked_id)
                if action_key in _NO_PARAMS:
                    if action_key == "appoint_proxius":
                        mortal_obj = state.mortals.get(picked_id)
                        if mortal_obj:
                            result = await app.push_screen_wait(MortalDetailModal(mortal_obj, state))
                            if result is None: return None
                            if result == BACK or not result: continue
                    break
                intent = await self._build_intent_params(action_key, defn, target_id, state)
                if intent is None: return None
                if intent == BACK: continue
                break
            return ActionInstance(
                action_definition_id=defn.id, target_type=TargetType.MORTAL,
                target_id=target_id, timestamp=state.universe.current_age,
                demiurge_id=state.demiurge.id, proxius_id=None,
                intent=None if action_key in _NO_PARAMS else intent,
            )

        if TargetType.CIVILIZATION in defn.valid_targets:
            civ_items = []
            for cid, c in state.civilizations.items():
                if not is_in_window(c):
                    continue
                w_obj = state.locations.get(str(c.origin_location_id)) if c.origin_location_id else None
                loc   = w_obj.name if w_obj else "?"
                civ_items.append((cid, f"{c.name:<30} [{c.scale.value}]  {loc}"))
            intent = None
            while True:
                picked_id = await app.push_screen_wait(PickerModal("Select Civilization", civ_items, show_back=True))
                if picked_id is None: return None
                if picked_id == BACK: return BACK
                target_id = UUID(picked_id)
                if action_key in _NO_PARAMS:
                    break
                intent = await self._build_intent_params(action_key, defn, target_id, state)
                if intent is None: return None
                if intent == BACK: continue
                break
            return ActionInstance(
                action_definition_id=defn.id, target_type=TargetType.CIVILIZATION,
                target_id=target_id, timestamp=state.universe.current_age,
                demiurge_id=state.demiurge.id, proxius_id=None,
                intent=None if action_key in _NO_PARAMS else intent,
            )

        if TargetType.LUMINARY in defn.valid_targets:
            lum_items = [
                (lid, f"{l.name}  [{_personality_label(l)}]")
                for lid, l in state.luminaries.items()
            ]
            intent = None
            while True:
                picked_id = await app.push_screen_wait(PickerModal("Select Luminary", lum_items, show_back=True))
                if picked_id is None: return None
                if picked_id == BACK: return BACK
                target_id = UUID(picked_id)
                if action_key in _NO_PARAMS:
                    break
                intent = await self._build_intent_params(action_key, defn, target_id, state)
                if intent is None: return None
                if intent == BACK: continue
                break
            return ActionInstance(
                action_definition_id=defn.id, target_type=TargetType.LUMINARY,
                target_id=target_id, timestamp=state.universe.current_age,
                demiurge_id=state.demiurge.id, proxius_id=None,
                intent=None if action_key in _NO_PARAMS else intent,
            )

        if TargetType.SPECIES in defn.valid_targets:
            species_items = []
            for sid, sp in state.species.items():
                w_obj  = state.locations.get(str(sp.origin_world_id)) if sp.origin_world_id else None
                origin = w_obj.name if w_obj else "unknown"
                sap    = "sapient" if sp.sapient else "non-sapient"
                species_items.append((sid, f"{sp.name:<18} [{sap}]  origin: {origin}"))
            intent = None
            while True:
                picked_id = await app.push_screen_wait(PickerModal("Select Species", species_items, show_back=True))
                if picked_id is None: return None
                if picked_id == BACK: return BACK
                target_id = UUID(picked_id)
                if action_key in _NO_PARAMS:
                    break
                intent = await self._build_intent_params(action_key, defn, target_id, state)
                if intent is None: return None
                if intent == BACK: continue
                break
            return ActionInstance(
                action_definition_id=defn.id, target_type=TargetType.SPECIES,
                target_id=target_id, timestamp=state.universe.current_age,
                demiurge_id=state.demiurge.id, proxius_id=None,
                intent=None if action_key in _NO_PARAMS else intent,
            )

        if TargetType.WORLD in defn.valid_targets and state.worlds:
            intent = None
            while True:
                target_id, target_type = await self._pick_world(state)
                if target_id is None: return None
                if target_id == BACK: return BACK
                if action_key in _NO_PARAMS:
                    break
                intent = await self._build_intent_params(action_key, defn, target_id, state)
                if intent is None: return None
                if intent == BACK: continue
                break
            return ActionInstance(
                action_definition_id=defn.id, target_type=target_type,
                target_id=target_id, timestamp=state.universe.current_age,
                demiurge_id=state.demiurge.id, proxius_id=None,
                intent=None if action_key in _NO_PARAMS else intent,
            )

        if TargetType.UNDERREAL in defn.valid_targets:
            target_type = TargetType.UNDERREAL
            if action_key in _NO_PARAMS:
                return ActionInstance(
                    action_definition_id=defn.id, target_type=target_type,
                    target_id=None, timestamp=state.universe.current_age,
                    demiurge_id=state.demiurge.id, proxius_id=None, intent=None,
                )
            intent = await self._build_intent_params(action_key, defn, None, state)
            if intent is None: return None
            if intent == BACK: return BACK
            return ActionInstance(
                action_definition_id=defn.id, target_type=target_type,
                target_id=None, timestamp=state.universe.current_age,
                demiurge_id=state.demiurge.id, proxius_id=None, intent=intent,
            )

        # ── No target / self-actions (SELF_REFINEMENT etc.) ──
        if action_key in _NO_PARAMS:
            return ActionInstance(
                action_definition_id=defn.id, target_type=target_type,
                target_id=None, timestamp=state.universe.current_age,
                demiurge_id=state.demiurge.id, proxius_id=None, intent=None,
            )
        intent = await self._build_intent_params(action_key, defn, None, state)
        if intent is None: return None
        if intent == BACK: return BACK
        return ActionInstance(
            action_definition_id=defn.id, target_type=target_type,
            target_id=None, timestamp=state.universe.current_age,
            demiurge_id=state.demiurge.id, proxius_id=None, intent=intent,
        )

    async def _build_intent_params(
        self,
        action_key: str,
        defn: "ActionDefinition",
        target_id,
        state: SimulationState,
    ):
        """
        Return the typed intent, BACK (go to previous step), or None (cancel).
        For no-param actions returns None without meaning cancel.
        """
        app = self.app
        cat = defn.category

        # ── DIRECT CREATION ──────────────────────────────
        if cat == ActionCategory.DIRECT_CREATION:
            if action_key == "seed_world":
                form = await app.push_screen_wait(
                    TextFormModal(
                        "Seed World — New Species",
                        [
                            ("Species name",          "name",    "Life-Form Alpha"),
                            ("Lifespan min",          "lmin",    "100.0"),
                            ("Lifespan max",          "lmax",    "200.0"),
                            ("Sapient from start? y/n","sapient","n"),
                            ("Bio tags (comma-separated, e.g. bio:bipedal)", "tags", ""),
                        ],
                        description=defn.description,
                        show_back=True,
                    )
                )
                if form is None: return None
                if form == BACK: return BACK
                bio_tags = [t.strip() for t in form["tags"].split(",") if t.strip()]
                return SeedWorldIntent(
                    species_name=form["name"].strip() or "Life-Form Alpha",
                    lifespan_min=float(form["lmin"] or 100.0),
                    lifespan_max=float(form["lmax"] or 200.0),
                    sapient=form["sapient"].strip().lower() == "y",
                    bio_tags=bio_tags,
                )
            if action_key == "uplift_species":
                domain_result = await self._pick_domain_and_imago(state)
                if domain_result is None: return None
                if domain_result == BACK: return BACK
                dvs, imago_id = domain_result
                return UpliftSpeciesIntent(species_id=target_id, domain_vectors=dvs, imago_node_id=imago_id)

        # ── SUBTLE INFLUENCE ─────────────────────────────
        elif cat == ActionCategory.SUBTLE_INFLUENCE:
            if action_key in ("whisper", "shape_dream"):
                ireg = get_imago_registry()
                step = 0
                dvs: list = []; imago_id = None; concept = None
                while True:
                    if step == 0:
                        domain_result = await self._pick_domain_and_imago(state)
                        if domain_result is None: return None
                        if domain_result == BACK: return BACK
                        dvs, imago_id = domain_result
                        concept = ireg.get_node(imago_id).name if imago_id else None
                        step = 1
                    if step == 1:
                        if not imago_id:
                            form = await app.push_screen_wait(
                                TextFormModal(
                                    "Whisper",
                                    [("Concept to plant", "concept", "You could shape the future.")],
                                    show_back=True,
                                )
                            )
                            if form is None: return None
                            if form == BACK: step = 0; continue
                            concept = form["concept"].strip() or "You could shape the future."
                        step = 2
                    if step == 2:
                        framing = await self._pick_framing()
                        if framing is None: return None
                        if framing == BACK:
                            step = 1 if not imago_id else 0
                            continue
                        break
                return WhisperIntent(
                    concept=concept, domain_vectors=dvs, framing=framing, imago_node_id=imago_id,
                )

            if action_key == "nudge_probability":
                step = 0; form_data = None
                dvs = []; imago_id = None
                while True:
                    if step == 0:
                        form = await app.push_screen_wait(
                            TextFormModal(
                                "Nudge Probability",
                                [
                                    ("Event to nudge",  "event",   "Upcoming succession conflict"),
                                    ("Desired outcome", "outcome", "The reformist faction prevails"),
                                ],
                                show_back=True,
                            )
                        )
                        if form is None: return None
                        if form == BACK: return BACK
                        form_data = form; step = 1
                    if step == 1:
                        domain_result = await self._pick_domain_and_imago(state)
                        if domain_result is None: return None
                        if domain_result == BACK: step = 0; continue
                        dvs, imago_id = domain_result; break
                return ProbabilityNudgeIntent(
                    event_description=form_data["event"].strip() or "Upcoming succession conflict",
                    desired_outcome=form_data["outcome"].strip() or "The reformist faction prevails",
                    domain_vectors=dvs, imago_node_id=imago_id,
                )

            if action_key == "accelerate_development":
                step = 0; form_data = None
                dvs = []; imago_id = None
                while True:
                    if step == 0:
                        form = await app.push_screen_wait(
                            TextFormModal(
                                "Accelerate Development",
                                [("Aspect to develop", "aspect", "military doctrine")],
                                show_back=True,
                            )
                        )
                        if form is None: return None
                        if form == BACK: return BACK
                        form_data = form; step = 1
                    if step == 1:
                        domain_result = await self._pick_domain_and_imago(state)
                        if domain_result is None: return None
                        if domain_result == BACK: step = 0; continue
                        dvs, imago_id = domain_result; break
                return DevelopmentIntent(
                    domain_vectors=dvs,
                    target_aspect=form_data["aspect"].strip() or "military doctrine",
                    imago_node_id=imago_id,
                )

        # ── OVERT MIRACLE ────────────────────────────────
        elif cat == ActionCategory.OVERT_MIRACLE:
            if action_key in ("manifest_omen", "divine_manifestation"):
                step = 0; form_data = None
                dvs = []; imago_id = None
                while True:
                    if step == 0:
                        form = await app.push_screen_wait(
                            TextFormModal(
                                "Manifest Omen",
                                [
                                    ("Sign description",       "sign",   "A celestial anomaly appears"),
                                    ("Intended interpretation","interp", "The gods demand action"),
                                ],
                                show_back=True,
                            )
                        )
                        if form is None: return None
                        if form == BACK: return BACK
                        form_data = form; step = 1
                    if step == 1:
                        domain_result = await self._pick_domain_and_imago(state)
                        if domain_result is None: return None
                        if domain_result == BACK: step = 0; continue
                        dvs, imago_id = domain_result; step = 2
                    if step == 2:
                        framing = await self._pick_framing()
                        if framing is None: return None
                        if framing == BACK: step = 1; continue
                        break
                civ_scope = None
                if target_id:
                    tid_str = str(target_id)
                    if tid_str in state.civilizations:
                        civ_scope = target_id
                    elif tid_str in state.mortals:
                        civ_scope = state.mortals[tid_str].civilization_id
                return OmenIntent(
                    sign_description=form_data["sign"].strip() or "A celestial anomaly appears",
                    intended_interpretation=form_data["interp"].strip() or "The gods demand action",
                    domain_vectors=dvs, framing=framing, civilization_scope=civ_scope,
                    imago_node_id=imago_id,
                )

        # ── UNDERREAL ────────────────────────────────────
        elif cat == ActionCategory.UNDERREAL:
            if action_key == "harvest_essence":
                form = await app.push_screen_wait(
                    TextFormModal(
                        "Harvest Essence",
                        [
                            ("Target concept type (optional)", "concept", ""),
                            ("Concealment priority  0.0 risky → 1.0 safe", "conc", "0.7"),
                        ],
                        show_back=True,
                    )
                )
                if form is None: return None
                if form == BACK: return BACK
                try:
                    conc = max(0.0, min(1.0, float(form["conc"] or 0.7)))
                except ValueError:
                    conc = 0.7
                return EssenceHarvestIntent(
                    target_concept_type=form["concept"].strip() or None,
                    concealment_priority=conc,
                )
            if action_key == "salvage_concept":
                step = 0; form_data = None; world_id = None
                dvs = []; imago_id = None
                while True:
                    if step == 0:
                        form = await app.push_screen_wait(
                            TextFormModal(
                                "Salvage Concept",
                                [("What are you hoping to find?", "desired", "")],
                                show_back=True,
                            )
                        )
                        if form is None: return None
                        if form == BACK: return BACK
                        form_data = form; step = 1
                    if step == 1:
                        world_id, _ = await self._pick_world(state)
                        if world_id is None: return None
                        if world_id == BACK: step = 0; continue
                        step = 2
                    if step == 2:
                        domain_result = await self._pick_domain_and_imago(state)
                        if domain_result is None: return None
                        if domain_result == BACK: step = 1; continue
                        dvs, imago_id = domain_result; break
                return SalvageIntent(
                    desired_concept=form_data["desired"].strip(),
                    target_world_id=world_id,
                    domain_vectors=dvs, imago_node_id=imago_id,
                )

        # ── LUMINARY RELATIONS ───────────────────────────
        elif cat == ActionCategory.LUMINARY_RELATIONS:
            form = await app.push_screen_wait(
                TextFormModal(
                    "Petition Luminary",
                    [
                        ("Subject",           "subject",  "Current universe state"),
                        ("Your position",     "position", "Continued patience"),
                        ("Tone (deferential/confident/urgent/firm)", "tone", "deferential"),
                    ],
                    show_back=True,
                )
            )
            if form is None: return None
            if form == BACK: return BACK
            return LuminaryPetitionIntent(
                subject=form["subject"].strip() or "Current universe state",
                your_position=form["position"].strip() or "Continued patience",
                tone=form["tone"].strip() or "deferential",
            )

        # ── SELF REFINEMENT ──────────────────────────────
        elif cat == ActionCategory.SELF_REFINEMENT:
            if action_key == "explore_beliefs":
                dreg = get_domain_registry()
                capped = {
                    tag for tag in dreg.all_tags
                    if _compute_revelation_cap(state, tag) == 0.0
                    or state.demiurge.revelation_pools.get(tag, 0.0) >= _compute_revelation_cap(state, tag)
                }
                tag = await self.app.push_screen_wait(
                    DomainPickerModal(state, explore_mode=True, capped_domains=capped)
                )
                if tag is None: return None
                if tag == BACK: return BACK
                if not tag: return None
                return ExploreBeliefIntent(domain_tag=tag)

            if action_key == "reveal_imago":
                return await self._build_reveal_imago_intent(state)

            if action_key == "change_affiliated_domains":
                if not state.demiurge.affiliated_domains:
                    self.app.notify("No affiliated domains to swap.", severity="warning")
                    return None
                step = 0; old_tag = None
                while True:
                    if step == 0:
                        result = await self.app.push_screen_wait(
                            PickerModal(
                                title="Drop which affiliated domain?",
                                items=[(t, t.split(":", 1)[1].title()) for t in state.demiurge.affiliated_domains],
                                show_back=True,
                            )
                        )
                        if result is None: return None
                        if result == BACK: return BACK
                        old_tag = result; step = 1
                    if step == 1:
                        exclude = set(state.demiurge.affiliated_domains)
                        new_tag = await self.app.push_screen_wait(
                            DomainPickerModal(state, exclude_tags=exclude)
                        )
                        if new_tag is None: return None
                        if new_tag == BACK: step = 0; continue
                        if not new_tag: step = 0; continue
                        break
                return ChangeAffiliatedDomainsIntent(old_domain=old_tag, new_domain=new_tag)

        # No intent needed
        return None

    # ── Sub-pickers ───────────────────────────

    async def _pick_domain_and_imago(
        self,
        state: SimulationState,
        explore_mode: bool = False,
    ) -> "tuple[list[DomainVector], str | None] | str | None":
        """
        Show the domain grid picker, then (if applicable) the Imago tree picker.
        Returns (dvs, imago_id), ([], None) for skip, BACK to go one level back, or None to cancel.
        """
        while True:
            tag = await self.app.push_screen_wait(DomainPickerModal(state, explore_mode=explore_mode))

            if tag is None: return None
            if tag == BACK: return BACK
            if tag == "":   return ([], None)

            if explore_mode:
                return ([DomainVector(domain_tag=tag, direction=1.0)], None)

            tree = tag.split(":", 1)[1]
            ireg = get_imago_registry()

            if ireg.nodes_for_tree(tree):
                while True:
                    chosen_id = await self.app.push_screen_wait(ImagoTreeModal(state, tree))
                    if chosen_id == BACK:
                        break
                    if chosen_id is None:
                        return None
                    node      = ireg.get_node(chosen_id)
                    confirmed = await self.app.push_screen_wait(ImagoDetailModal(node, state))
                    if confirmed is None: return None
                    if confirmed:
                        dvs = [
                            DomainVector(domain_tag=t, direction=v)
                            for t, v in node.mechanics.items()
                            if t.startswith("domain:")
                        ]
                        return (dvs, chosen_id)
                continue

    async def _build_reveal_imago_intent(
        self,
        state: SimulationState,
    ) -> "RevealImagoIntent | str | None":
        """
        Multi-step flow for Reveal Imago:
          domain picker → Imago reveal tree → detail/confirm modal → RevealImagoIntent
        """
        dreg = get_domain_registry()
        ireg = get_imago_registry()

        def _min_cost(tag: str) -> int:
            tree = tag.split(":", 1)[1] if ":" in tag else tag
            unlocked = set(state.demiurge.unlocked_imagines)
            rev = state.demiurge.revealed_imagines
            return min(
                (_revelation_adjusted_cost(n.tier, rev) for n in ireg.nodes_for_tree(tree)
                 if n.node_id not in unlocked and ireg.is_unlockable(n.node_id, unlocked)),
                default=9999,
            )

        eligible_reveal_domains = {
            tag for tag in dreg.all_tags
            if state.demiurge.revelation_pools.get(tag, 0.0) >= _min_cost(tag)
        }
        capped = {
            tag for tag in dreg.all_tags
            if _compute_revelation_cap(state, tag) == 0.0
        }

        step = 0
        chosen_tag: str = ""
        chosen_node_id: str = ""
        while True:
            if step == 0:
                tag = await self.app.push_screen_wait(
                    DomainPickerModal(
                        state,
                        capped_domains=capped,
                        eligible_reveal_domains=eligible_reveal_domains,
                    )
                )
                if tag is None: return None
                if tag == BACK: return BACK
                if not tag: return None
                chosen_tag = tag
                step = 1

            if step == 1:
                result = await self.app.push_screen_wait(
                    ImagoRevealModal(state, chosen_tag)
                )
                if result is None: return None
                if result == BACK: step = 0; continue
                chosen_node_id = result
                step = 2

            if step == 2:
                node = ireg.get_node(chosen_node_id)
                if node is None:
                    step = 1; continue
                cost = _revelation_adjusted_cost(node.tier, state.demiurge.revealed_imagines)
                pool = state.demiurge.revelation_pools.get(chosen_tag, 0.0)
                confirmed = await self.app.push_screen_wait(
                    ImagoRevealDetailModal(node, state, chosen_tag, cost, pool)
                )
                if confirmed is None: return None
                if confirmed is False: step = 1; continue
                return RevealImagoIntent(domain_tag=chosen_tag, node_id=chosen_node_id)

    async def _pick_proxius(
        self,
        state: SimulationState,
        include_dormant: bool = False,
        already_directed: set | None = None,
    ) -> "str | None":
        already_directed = already_directed or set()
        proxii = [
            (mid, m) for mid, m in state.mortals.items()
            if m.role == MortalRole.PROXIUS
            and mid not in already_directed
            and (m.status == MortalStatus.ACTIVE
                 or (include_dormant and m.status == MortalStatus.DORMANT))
        ]
        if not proxii:
            self._feed_markup("[#5a7090]No Proxiī available.[/]", "actions")
            return None
        items = []
        for mid, m in proxii:
            w_obj     = state.locations.get(str(m.current_location))
            loc       = w_obj.name if w_obj else "?"
            sp_obj    = state.species.get(str(m.species_id)) if m.species_id else None
            sp_name   = sp_obj.name if sp_obj else "?"
            pop_obj   = state.pops.get(str(m.pop_id)) if m.pop_id else None
            pop_str   = f"  {_pop_stratum_label(pop_obj)}" if pop_obj else ""
            dorm_note = "  [DORMANT]" if m.status == MortalStatus.DORMANT else ""
            items.append((mid, f"{m.name:<18}  {sp_name:<14}  align:{m.alignment:.2f}  {loc}{pop_str}{dorm_note}"))
        return await self.app.push_screen_wait(PickerModal("Select Proxius", items, show_back=True))

    async def _pick_world(
        self,
        state: SimulationState,
    ) -> "tuple[UUID | str | None, TargetType]":
        worlds = [(wid, w) for wid, w in state.worlds.items() if is_in_window(w)]
        if not worlds:
            self._feed_markup("[#5a7090]No worlds available.[/]", "actions")
            return None, TargetType.WORLD
        items = []
        for wid, w in worlds:
            sys_obj  = state.locations.get(str(w.parent_id)) if w.parent_id else None
            sys_name = sys_obj.name if sys_obj else "?"
            n_civs   = sum(1 for cid in w.civilization_ids if str(cid) in state.civilizations and is_in_window(state.civilizations[str(cid)]))
            life_str = f"{n_civs} civilization(s) known" if n_civs else "no life known"
            items.append((wid, f"{w.name:<16} [{w.condition.value}]  {sys_name:<20}  {life_str}"))
        picked = await self.app.push_screen_wait(PickerModal("Select World", items, show_back=True))
        if picked is None:  return None, TargetType.WORLD
        if picked == BACK:  return BACK, TargetType.WORLD
        return UUID(picked), TargetType.WORLD

    async def _pick_system(
        self,
        state: SimulationState,
    ) -> "tuple[UUID | str | None, TargetType]":
        systems = [(sid, s) for sid, s in state.systems.items() if is_in_window(s)]
        if not systems:
            self._feed_markup("[#5a7090]No systems available.[/]", "actions")
            return None, TargetType.SYSTEM
        items = []
        for sid, s in systems:
            gal_obj  = state.locations.get(str(s.parent_id)) if s.parent_id else None
            gal_name = gal_obj.name if gal_obj else "?"
            n_worlds = sum(1 for cid in s.child_ids if str(cid) in state.locations and is_in_window(state.locations[str(cid)]))
            items.append((sid, f"{s.name:<22} [{s.star_type.value}]  {gal_name:<20}  {n_worlds} world(s) known"))
        picked = await self.app.push_screen_wait(PickerModal("Select System", items, show_back=True))
        if picked is None:  return None, TargetType.SYSTEM
        if picked == BACK:  return BACK, TargetType.SYSTEM
        return UUID(picked), TargetType.SYSTEM

    async def _pick_galaxy(
        self,
        state: SimulationState,
    ) -> "tuple[UUID | str | None, TargetType]":
        galaxies = [(gid, g) for gid, g in state.galaxies.items() if is_in_window(g)]
        if not galaxies:
            self._feed_markup("[#5a7090]No galaxies available.[/]", "actions")
            return None, TargetType.GALAXY
        items = []
        for gid, g in galaxies:
            n_systems = sum(1 for cid in g.child_ids if str(cid) in state.locations and is_in_window(state.locations[str(cid)]))
            items.append((gid, f"{g.name:<26}  {n_systems} system(s) known"))
        picked = await self.app.push_screen_wait(PickerModal("Select Galaxy", items, show_back=True))
        if picked is None:  return None, TargetType.GALAXY
        if picked == BACK:  return BACK, TargetType.GALAXY
        return UUID(picked), TargetType.GALAXY

    async def _pick_framing(self) -> "Framing | str | None":
        """Returns a Framing value, BACK sentinel, or None to cancel."""
        items  = [(f.value, f.value.title()) for f in Framing]
        picked = await self.app.push_screen_wait(PickerModal("Framing", items, show_back=True))
        if picked is None:                          return None
        if picked == BACK:                          return BACK
        if picked not in {f.value for f in Framing}: return Framing.INSPIRATIONAL
        return Framing(picked)


# ─────────────────────────────────────────
# APP
# ─────────────────────────────────────────

class DemiurgeApp(App):
    CSS_PATH = Path(__file__).parent / "styles.tcss"
    TITLE    = "DEMIURGE"

    loop: TickLoop

    def __init__(self):
        super().__init__()
        self.loop = TickLoop()

    def on_mount(self) -> None:
        self.push_screen(LoadScreen())
