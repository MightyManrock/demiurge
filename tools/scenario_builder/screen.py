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

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, TabbedContent, TabPane

from logic.tick_logic import SimulationState
from ui.constants import _SCENARIOS_DIR
from ui.detail_tabs import DetailTabManager
from ui.display import _pop_stratum_label
from ui.modals import QuitConfirmModal, ErrorModal, TextFormModal
from ui.widgets import (
    DivineWisdomTab, LocationsTab, LuminariesTab, UniverseTab,
    set_unseen_predicate,
)
from utilities.scenario_exporter import export_scenario

from .briefing_editor import BriefingEditorTab
from .naming import validate_initialism, validate_scenario_name


class BuilderScreen(Screen):
    """Builder-mode workspace. Read-only browsing + save/save-as in Phase 1."""

    DEFAULT_CSS = """
    BuilderScreen #builder-toolbar {
        height: 3;
        padding: 0 1;
        background: #0a0a1e;
    }
    BuilderScreen #builder-toolbar Button {
        margin: 0 1 0 0;
        min-width: 18;
    }
    """

    BINDINGS = [
        ("ctrl+s",       "save",         "Save"),
        ("ctrl+shift+s", "save_as",      "Save As"),
        ("q",            "quit_confirm", "Quit"),
        ("ctrl+q",       "quit_force",   "Force quit"),
        # Tab switching: digit jumps to right-panel tab.
        ("1", "right_tab('briefing')",      "Briefing"),
        ("2", "right_tab('universe')",      "Universe"),
        ("3", "right_tab('luminaries')",    "Luminaries"),
        ("4", "right_tab('divine_wisdom')", "Wisdom"),
        # Detail-tab controls.
        ("escape",   "close_detail", "Close"),
        ("ctrl+p",   "pin_detail",   "Pin"),
        ("alt+left", "back_detail",  "Back"),
    ]

    def __init__(
        self,
        state: SimulationState,
        db_path: Path,
        scenario_description: str = "",
    ):
        super().__init__()
        self._state: SimulationState = state
        self._db_path: Path = db_path
        self._dirty: bool = False
        self._detail_mgr: DetailTabManager | None = None
        # Authored prose: scenario_meta.description is not stored on
        # SimulationState by the loader; we track it here and persist it via
        # export_scenario(..., description=...). Universe.description is read
        # from state.universe.description.
        self._scenario_description: str = scenario_description

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="builder-toolbar"):
            yield Button("Edit Universe",  id="edit-universe-btn")
            yield Button("Edit Demiurge",  id="edit-demiurge-btn")
            yield Button("Edit Pantheon",  id="edit-pantheon-btn")
        with Horizontal():
            with TabbedContent(id="left-tabs", initial="locations"):
                with TabPane("Locations", id="locations"):
                    yield LocationsTab()
            with TabbedContent(id="right-tabs", initial="briefing"):
                with TabPane("Briefing", id="briefing"):
                    yield BriefingEditorTab(
                        scenario_description=self._scenario_description,
                        universe_description=self._state.universe.description,
                        on_scenario_description_changed=self._on_scenario_desc_edited,
                        on_universe_description_changed=self._on_universe_desc_edited,
                    )
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

    # ── Briefing-editor callbacks ──────────────────────────────────────────

    def _on_scenario_desc_edited(self, new_text: str) -> None:
        if new_text == self._scenario_description:
            return
        self._scenario_description = new_text
        self.mark_dirty()

    def _on_universe_desc_edited(self, new_text: str) -> None:
        if new_text == self._state.universe.description:
            return
        self._state.universe.description = new_text
        self.mark_dirty()

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
        # Briefing editor needs state for preview rendering and may need its
        # textareas resynced if a meta-edit modal changed universe.description.
        try:
            briefing = self.query_one(BriefingEditorTab)
        except Exception:
            briefing = None
        if briefing is not None:
            briefing.sync_descriptions(
                self._scenario_description,
                self._state.universe.description,
            )
            briefing.refresh_state(state)
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

    # ── Meta-edit toolbar buttons ──────────────────────────────────────────

    @on(Button.Pressed, "#edit-universe-btn")
    def _edit_universe_pressed(self, _: Button.Pressed) -> None:
        self._edit_universe_flow()

    @on(Button.Pressed, "#edit-demiurge-btn")
    def _edit_demiurge_pressed(self, _: Button.Pressed) -> None:
        self._edit_demiurge_flow()

    @on(Button.Pressed, "#edit-pantheon-btn")
    def _edit_pantheon_pressed(self, _: Button.Pressed) -> None:
        self._edit_pantheon_flow()

    @work
    async def _edit_universe_flow(self) -> None:
        u = self._state.universe
        result = await self.app.push_screen_wait(TextFormModal(
            title="Edit Universe",
            description=(
                "Scenario name appears in the chooser and at the top of the "
                "briefing. Initialism is the save-file prefix (1–6 uppercase "
                "letters/digits). Current age is the in-universe clock at "
                "scenario start."
            ),
            fields=[
                ("Scenario name", "name",        u.name),
                ("Initialism",    "save_name",   u.save_name),
                ("Current age",   "current_age", f"{u.current_age}"),
            ],
        ))
        if not result:
            return
        name, err = validate_scenario_name(result["name"])
        if err:
            await self.app.push_screen_wait(ErrorModal(err)); return
        initialism, err = validate_initialism(result["save_name"])
        if err:
            await self.app.push_screen_wait(ErrorModal(err)); return
        try:
            age = float(result["current_age"])
        except (TypeError, ValueError):
            await self.app.push_screen_wait(ErrorModal(
                "Current age must be a number (e.g. 0, 600, 1500.5)."
            ))
            return
        if age < 0:
            await self.app.push_screen_wait(ErrorModal(
                "Current age cannot be negative."
            ))
            return
        u.name        = name
        u.save_name   = initialism
        u.current_age = age
        self.mark_dirty()
        self._refresh_all()

    @work
    async def _edit_demiurge_flow(self) -> None:
        d = self._state.demiurge
        result = await self.app.push_screen_wait(TextFormModal(
            title="Edit Demiurge",
            description=(
                "Domain affiliations and unlocked Imagines are not yet "
                "editable here — that's coming in a follow-up. For now this "
                "form edits the Demiurge's name only."
            ),
            fields=[
                ("Name", "name", d.name),
            ],
        ))
        if not result:
            return
        new_name = result["name"].strip()
        if not new_name:
            await self.app.push_screen_wait(ErrorModal(
                "Demiurge name cannot be empty."
            ))
            return
        d.name = new_name
        self.mark_dirty()
        self._refresh_all()

    @work
    async def _edit_pantheon_flow(self) -> None:
        p = self._state.pantheon
        result = await self.app.push_screen_wait(TextFormModal(
            title="Edit Pantheon",
            description=(
                "Pantheon-level constraints will be editable in Phase 6. "
                "For now this form edits the Pantheon's name only."
            ),
            fields=[
                ("Name", "name", p.name),
            ],
        ))
        if not result:
            return
        new_name = result["name"].strip()
        if not new_name:
            await self.app.push_screen_wait(ErrorModal(
                "Pantheon name cannot be empty."
            ))
            return
        p.name = new_name
        self.mark_dirty()
        self._refresh_all()

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
        export_scenario(
            self._state, path,
            scenario_name=self._state.universe.name,
            description=self._scenario_description,
        )
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
        """Q — open the same confirmation modal the core game uses."""
        self._quit_confirm_flow()

    def action_quit_force(self) -> None:
        """Ctrl+Q — skip the modal and exit immediately."""
        self.app.exit()

    @work
    async def _quit_confirm_flow(self) -> None:
        choice = await self.app.push_screen_wait(QuitConfirmModal())
        if choice is None:
            return  # Keep editing
        if choice == "save":
            self._save_to(self._db_path)
        self.app.exit()
