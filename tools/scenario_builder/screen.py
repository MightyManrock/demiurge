"""
BuilderScreen — the main scenario-builder editing surface.

Composes a stripped-down workspace (Locations on the left; Universe,
Luminaries, Divine Wisdom on the right) from the existing game widgets,
plus the existing DetailTabManager for entity detail tabs. All click-link
actions emitted by those widgets are wired here so the read-only browse
behaves identically to the core game.

Editing modals are intentionally out of scope for Phase 1 — they will be
added in Phases 2–6.
"""
from __future__ import annotations
import shutil
from datetime import datetime
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Footer, Header, TabbedContent, TabPane

from logic.tick_logic import SimulationState
from ui.constants import _SCENARIOS_DIR
from ui.detail_tabs import DetailTabManager
from ui.display import _pop_stratum_label
from ui.widgets import (
    DivineWisdomTab, LocationsTab, LuminariesTab, UniverseTab,
    set_unseen_predicate,
)
from utilities.scenario_exporter import export_scenario


class BuilderScreen(Screen):
    """Builder-mode workspace. Read-only browsing + save/save-as in Phase 1."""

    BINDINGS = [
        ("ctrl+s",       "save",         "Save"),
        ("ctrl+shift+s", "save_as",      "Save As"),
        ("q",            "quit_confirm", "Quit"),
        ("ctrl+q",       "quit_force",   "Force quit"),
        # Tab switching: digit jumps to right-panel tab.
        ("1", "right_tab('universe')",      "Universe"),
        ("2", "right_tab('luminaries')",    "Luminaries"),
        ("3", "right_tab('divine_wisdom')", "Wisdom"),
        # Detail-tab controls.
        ("escape",   "close_detail", "Close"),
        ("ctrl+p",   "pin_detail",   "Pin"),
        ("alt+left", "back_detail",  "Back"),
    ]

    def __init__(self, state: SimulationState, db_path: Path):
        super().__init__()
        self._state: SimulationState = state
        self._db_path: Path = db_path
        self._dirty: bool = False
        self._detail_mgr: DetailTabManager | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal():
            with TabbedContent(id="left-tabs", initial="locations"):
                with TabPane("Locations", id="locations"):
                    yield LocationsTab()
            with TabbedContent(id="right-tabs", initial="universe"):
                with TabPane("Universe", id="universe"):
                    yield UniverseTab()
                with TabPane("Luminaries", id="luminaries"):
                    yield LuminariesTab()
                with TabPane("Divine Wisdom", id="divine_wisdom"):
                    yield DivineWisdomTab()
        yield Footer()

    def on_mount(self) -> None:
        self._detail_mgr = DetailTabManager(
            self, self.query_one("#right-tabs", TabbedContent),
            anchor_before_id=None,  # no Log tab in the builder; append to the end
        )
        self._refresh_all()

    # ── Public API used by external code paths (e.g. future editor modals) ─

    def mark_dirty(self) -> None:
        self._dirty = True
        self._update_subtitle()

    def _update_subtitle(self) -> None:
        s = self._state
        dirty = " · [modified]" if self._dirty else ""
        self.app.sub_title = (
            f"{s.universe.name}  ·  {self._db_path.name}{dirty}"
        )

    # ── Refresh fan-out ────────────────────────────────────────────────────

    def _refresh_all(self) -> None:
        # Widgets consult this predicate for "unseen" gold highlighting.
        # The builder has no discovery system, so always return False.
        set_unseen_predicate(lambda *_: False)
        state = self._state
        self._update_subtitle()
        self.query_one(LocationsTab).refresh_state(state)
        self.query_one(UniverseTab).refresh_state(state)
        self.query_one(LuminariesTab).refresh_state(state)
        self.query_one(DivineWisdomTab).refresh_state(state)
        if self._detail_mgr is not None:
            self._detail_mgr.refresh_all(state)

    # ── Detail-tab integration ─────────────────────────────────────────────

    def open_detail(self, kind: str, entity_id, name: str) -> None:
        if self._detail_mgr is None:
            return
        self._detail_mgr.open(kind, str(entity_id), name, self._state)

    def open_detail_by_id(self, kind: str, entity_id: str) -> None:
        name = self._lookup_entity_name(kind, str(entity_id))
        self.open_detail(kind, entity_id, name)

    def action_open_detail_by_id(self, kind: str, entity_id: str) -> None:
        self.open_detail_by_id(kind, entity_id)

    def action_navigate_detail_by_id(self, kind: str, entity_id: str) -> None:
        if self._detail_mgr is None or not self._detail_mgr.is_detail_pane_active():
            self.open_detail_by_id(kind, entity_id)
            return
        name = self._lookup_entity_name(kind, str(entity_id))
        self._detail_mgr.navigate_active(kind, str(entity_id), name, self._state)

    def action_detail_back_to_index(self, idx: str) -> None:
        if self._detail_mgr is None:
            return
        try:
            i = int(idx)
        except (TypeError, ValueError):
            return
        self._detail_mgr.jump_active_to_index(i, self._state)

    def action_open_luminary(self, lum_id: str) -> None:
        right = self.query_one("#right-tabs", TabbedContent)
        right.active = "luminaries"
        self.query_one(LuminariesTab).show_luminary(str(lum_id))

    def action_open_luminaries_list(self) -> None:
        right = self.query_one("#right-tabs", TabbedContent)
        right.active = "luminaries"
        self.query_one(LuminariesTab).show_list()

    def action_open_divine_wisdom(self, domain_tag: str = "") -> None:
        right = self.query_one("#right-tabs", TabbedContent)
        right.active = "divine_wisdom"
        tab = self.query_one(DivineWisdomTab)
        if domain_tag:
            tab.show_domain(domain_tag)
        else:
            tab.show_list()

    def action_open_imago_node(self, node_id: str) -> None:
        right = self.query_one("#right-tabs", TabbedContent)
        right.active = "divine_wisdom"
        self.query_one(DivineWisdomTab).show_node(node_id)

    def action_close_detail(self) -> None:
        if self._detail_mgr is not None:
            self._detail_mgr.close_focused()

    def action_pin_detail(self) -> None:
        if self._detail_mgr is None:
            return
        self._detail_mgr.toggle_pin_focused(self._state)

    def action_back_detail(self) -> None:
        if self._detail_mgr is None:
            return
        self._detail_mgr.back_focused(self._state)

    def action_right_tab(self, pane_id: str) -> None:
        self.query_one("#right-tabs", TabbedContent).active = pane_id

    def _lookup_entity_name(self, kind: str, entity_id: str) -> str:
        """Mirror of GameScreen._lookup_entity_name."""
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

    # ── Save / Save-As ─────────────────────────────────────────────────────

    def _backup(self, path: Path) -> Path | None:
        if not path.exists():
            return None
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = path.with_suffix(path.suffix + f".bak.{stamp}")
        shutil.copy2(path, bak)
        return bak

    def _save_to(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        bak = self._backup(path)
        export_scenario(self._state, path, scenario_name=self._state.universe.name)
        self._db_path = path
        self._dirty = False
        self._update_subtitle()
        msg = f"Saved → {path.name}"
        if bak is not None:
            msg += f"  (backup: {bak.name})"
        self.notify(msg, timeout=4)

    def action_save(self) -> None:
        self._save_to(self._db_path)

    def action_save_as(self) -> None:
        # Phase 1 keeps Save-As minimal: prompt for a new filename stem and
        # write to scenarios/<stem>.db. A full file-picker can come later.
        from .save_as import SaveAsModal
        self.app.push_screen(SaveAsModal(self._db_path.stem), self._save_as_callback)

    def _save_as_callback(self, stem: str | None) -> None:
        if not stem:
            return
        self._save_to(_SCENARIOS_DIR / f"{stem}.db")

    # ── Quit handling ──────────────────────────────────────────────────────

    def action_quit_confirm(self) -> None:
        if self._dirty:
            self.notify(
                "Unsaved changes. Press Ctrl+S to save, or Ctrl+Q to quit anyway.",
                severity="warning", timeout=5,
            )
            return
        self.app.exit()

    def action_quit_force(self) -> None:
        self.app.exit()
