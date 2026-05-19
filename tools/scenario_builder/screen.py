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
from typing import Optional
from uuid import UUID

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, TabbedContent, TabPane

from core.universe_core import SignificantLocation
from logic.tick_logic import SimulationState
from ui.constants import _SCENARIOS_DIR
from ui.detail_tabs import DetailTabManager
from ui.display import _pop_identity_label, _pop_stratum_label  # _pop_stratum_label kept for future inline use
from ui.constants import BACK
from ui.modals import QuitConfirmModal, ErrorModal, PickerModal, TextFormModal
from ui.widgets import (
    DivineWisdomTab, LocationsTab, LuminariesTab, UniverseTab,
    set_detail_action_provider, set_flag_predicate, set_unseen_predicate,
)
from utilities.scenario_exporter import export_scenario

from .briefing_editor import BriefingEditorTab
from .naming import validate_initialism, validate_scenario_name
from .scenario_tab import ScenarioTab
from . import location_editor as locedit
from . import entity_editor as entedit
from . import mortal_editor as medit
from . import luminary_editor as ledit
from . import field_editors as fedit
from .flag_check import find_broken_refs, render_flag_report


class BuilderScreen(Screen):
    """Builder-mode workspace. Read-only browsing + save/save-as in Phase 1."""

    BINDINGS = [
        ("ctrl+s",       "save",            "Save"),
        ("ctrl+shift+s", "save_as",         "Save As"),
        ("ctrl+o",       "switch_scenario", "Open"),
        ("q",            "quit_confirm",    "Quit"),
        ("ctrl+q",       "quit_force",      "Force quit"),
        # Left-panel tab switching.
        ("1", "left_tab('scenario')",       "Scenario"),
        ("2", "left_tab('locations')",      "Locations"),
        # Right-panel tab switching.
        ("ctrl+1", "right_tab('briefing')",      ""),
        ("ctrl+2", "right_tab('universe')",      ""),
        ("ctrl+3", "right_tab('luminaries')",    ""),
        ("ctrl+4", "right_tab('divine_wisdom')", ""),
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
        # IDs of entities with broken outgoing references (populated each
        # refresh by `_recompute_flags`). Rendered in red wherever they
        # appear; saving is refused while non-empty.
        self._flagged_ids: set[str] = set()
        # Verbose reasons keyed by the same entity id — surfaced in the
        # save / quit guards' diagnostic listings.
        self._flag_reasons: dict[str, list[str]] = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal():
            with TabbedContent(id="left-tabs", initial="scenario"):
                with TabPane("Scenario", id="scenario"):
                    yield ScenarioTab()
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
        flagged = (
            f" · ⚠ {len(self._flagged_ids)} flagged"
            if self._flagged_ids else ""
        )
        self.app.sub_title = (
            f"{s.universe.name}  ·  {self._db_path.name}{dirty}{flagged}"
        )

    # ── Refresh fan-out ────────────────────────────────────────────────────

    def _recompute_flags(self) -> None:
        """Re-scan state for broken references and refresh the flag set."""
        self._flag_reasons = find_broken_refs(self._state)
        self._flagged_ids = set(self._flag_reasons.keys())

    # ── Detail-tab inline action provider ─────────────────────────────────

    # Mapping of renderer kind → (in-state attribute name, ordered).
    _EDITABLE_KIND_TABLES = {
        "world":    "locations",
        "system":   "locations",
        "galaxy":   "locations",
        "poploc":   "locations",
        "civ":      "civilizations",
        "species":  "species",
        "pop":      "pops",
        "mortal":   "mortals",
        "luminary": "luminaries",
    }

    def _detail_actions_for(self, kind: str, eid: str) -> list[tuple[str, str]]:
        """Return the inline button set for a given detail-tab entity.
        Empty list means no buttons render (e.g., for unknown kinds)."""
        if kind not in self._EDITABLE_KIND_TABLES:
            return []
        table = getattr(self._state, self._EDITABLE_KIND_TABLES[kind], None)
        if table is None or eid not in table:
            return []
        return [
            ("Edit",   "edit_entity_by_id"),
            ("Delete", "delete_entity_by_id"),
        ]

    def action_edit_entity_by_id(self, kind: str, eid: str) -> None:
        """Click target from the detail-tab [ Edit ] button. Dispatches to
        the per-kind edit-loop helper, bypassing the picker step."""
        self._edit_entity_by_id_worker(kind, eid)

    def action_delete_entity_by_id(self, kind: str, eid: str) -> None:
        """Click target from the detail-tab [ Delete ] button."""
        self._delete_entity_by_id_worker(kind, eid)

    @work
    async def _edit_entity_by_id_worker(self, kind: str, eid: str) -> None:
        if kind in ("world", "system", "galaxy", "poploc"):
            loc = self._state.locations.get(eid)
            if loc is None:
                await self.app.push_screen_wait(ErrorModal("Location not found.")); return
            await self._location_edit_loop(loc)
        elif kind == "civ":
            civ = self._state.civilizations.get(eid)
            if civ is None:
                await self.app.push_screen_wait(ErrorModal("Civilization not found.")); return
            await self._civ_edit_loop(civ)
        elif kind == "species":
            sp = self._state.species.get(eid)
            if sp is None:
                await self.app.push_screen_wait(ErrorModal("Species not found.")); return
            await self._species_edit_loop(sp)
        elif kind == "pop":
            pop = self._state.pops.get(eid)
            if pop is None:
                await self.app.push_screen_wait(ErrorModal("Pop not found.")); return
            await self._pop_edit_loop(pop)
        elif kind == "mortal":
            m = self._state.mortals.get(eid)
            if m is None:
                await self.app.push_screen_wait(ErrorModal("Mortal not found.")); return
            await self._mortal_edit_loop(m)
        elif kind == "luminary":
            lum = self._state.luminaries.get(eid)
            if lum is None:
                await self.app.push_screen_wait(ErrorModal("Luminary not found.")); return
            await self._luminary_edit_loop(lum)

    @work
    async def _delete_entity_by_id_worker(self, kind: str, eid: str) -> None:
        if kind in ("world", "system", "galaxy", "poploc"):
            await self._location_delete_by_id(eid)
        elif kind == "civ":
            await self._civ_delete_by_id(eid)
        elif kind == "species":
            await self._species_delete_by_id(eid)
        elif kind == "pop":
            await self._pop_delete_by_id(eid)
        elif kind == "mortal":
            await self._mortal_delete_by_id(eid)
        elif kind == "luminary":
            await self._luminary_delete_by_id(eid)

    def _refresh_all(self) -> None:
        # Widgets consult this predicate for "unseen" gold highlighting.
        # The builder has no discovery system, so always return False.
        set_unseen_predicate(lambda *_: False)
        # Recompute broken-ref flags and install the red-link predicate.
        self._recompute_flags()
        set_flag_predicate(lambda eid: eid in self._flagged_ids)
        # Install the per-entity action provider used by DetailTab's header
        # to render inline [ Edit ] / [ Delete ] buttons.
        set_detail_action_provider(self._detail_actions_for)
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

    def action_left_tab(self, pane_id: str) -> None:
        self.query_one("#left-tabs", TabbedContent).active = pane_id

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
        while True:
            choice = await self.app.push_screen_wait(PickerModal(
                title=f"Edit Universe: {u.name}",
                items=[
                    ("basics",     "Basics (name, initialism, current age)"),
                    ("expression", f"Universe-wide domain expression ({len(u.universe_domain_expression)})"),
                    ("done",       "Done"),
                ],
            ))
            if choice in (None, "done"):
                return
            if choice == "basics":
                await self._edit_universe_basics(u)
            elif choice == "expression":
                await fedit.edit_tag_weight_dict(
                    self, u.universe_domain_expression,
                    title_prefix="Universe — Domain expression baseline",
                    tag_namespace="domain",
                )

    async def _edit_universe_basics(self, u) -> None:
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
            show_back=True,
        ))
        if result in (None, BACK):
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
        while True:
            choice = await self.app.push_screen_wait(PickerModal(
                title=f"Edit Demiurge: {d.name}",
                items=[
                    ("basics",     "Basics (name)"),
                    ("affiliated", f"Affiliated domains ({len(d.affiliated_domains)}/4)"),
                    ("imagines",   f"Unlocked Imagines ({len(d.unlocked_imagines)})"),
                    ("done",       "Done"),
                ],
            ))
            if choice in (None, "done"):
                return
            if choice == "basics":
                await self._edit_demiurge_basics(d)
            elif choice == "affiliated":
                await fedit.edit_string_list(
                    self, d.affiliated_domains,
                    title_prefix=f"{d.name} — Affiliated domains",
                    tag_namespace="domain",
                    max_items=4,
                )
            elif choice == "imagines":
                await self._edit_demiurge_imagines(d)

    async def _edit_demiurge_basics(self, d) -> None:
        result = await self.app.push_screen_wait(TextFormModal(
            title=f"Edit Demiurge: {d.name}",
            fields=[("Name", "name", d.name)],
            show_back=True,
        ))
        if result in (None, BACK):
            return
        new_name = result["name"].strip()
        if not new_name:
            await self.app.push_screen_wait(ErrorModal("Demiurge name cannot be empty."))
            return
        d.name = new_name
        self.mark_dirty(); self._refresh_all()

    async def _edit_demiurge_imagines(self, d) -> None:
        """Add/remove loop over `d.unlocked_imagines: list[str]` (Imago
        node_ids). Add path is a two-step picker: tree → node within tree."""
        from utilities.imago_registry import get_registry as get_imago_registry
        reg = get_imago_registry()
        # Group all node_ids by tree for display.
        nodes_by_tree: dict[str, list[str]] = {}
        for node_id in reg.all_node_ids:
            tree = node_id.split(":", 1)[0]
            nodes_by_tree.setdefault(tree, []).append(node_id)

        while True:
            n = len(d.unlocked_imagines)
            choice = await self.app.push_screen_wait(PickerModal(
                title=f"{d.name} — Unlocked Imagines ({n})",
                items=[
                    ("add",    "+ Add an Imago"),
                    ("remove", "Remove an Imago"),
                    ("done",   "Done"),
                ],
            ))
            if choice in (None, "done"):
                return
            if choice == "add":
                # Step 1: pick a tree (16 canonical domains).
                tree_items = [
                    (t, t.title()) for t in sorted(nodes_by_tree.keys())
                ]
                tree = await self.app.push_screen_wait(PickerModal(
                    title="Pick a tree (domain)", items=tree_items, show_back=True,
                ))
                if tree in (None, BACK):
                    continue
                # Step 2: pick a node within that tree, hiding ones already unlocked.
                existing = set(d.unlocked_imagines)
                node_items = []
                for node_id in nodes_by_tree[tree]:
                    if node_id in existing:
                        continue
                    node = reg.get_node(node_id)
                    label = f"T{node.tier}  {node.name}  ({node_id})" if node else node_id
                    node_items.append((node_id, label))
                if not node_items:
                    await self.app.push_screen_wait(ErrorModal(
                        f"Every Imago in the {tree} tree is already unlocked."
                    ))
                    continue
                picked = await self.app.push_screen_wait(PickerModal(
                    title=f"Pick an Imago from {tree.title()}",
                    items=node_items, show_back=True,
                ))
                if picked in (None, BACK):
                    continue
                d.unlocked_imagines.append(picked)
                self.mark_dirty(); self._refresh_all()
            elif choice == "remove":
                if not d.unlocked_imagines:
                    await self.app.push_screen_wait(ErrorModal("Nothing to remove."))
                    continue
                items = []
                for node_id in d.unlocked_imagines:
                    node = reg.get_node(node_id)
                    label = f"T{node.tier}  {node.name}  ({node_id})" if node else node_id
                    items.append((node_id, label))
                picked = await self.app.push_screen_wait(PickerModal(
                    title="Remove which?", items=items, show_back=True,
                ))
                if picked in (None, BACK):
                    continue
                d.unlocked_imagines = [x for x in d.unlocked_imagines if x != picked]
                self.mark_dirty(); self._refresh_all()

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
            return _pop_identity_label(s, s.pops[eid])
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
        # Refresh flags right before saving so the guard sees current state.
        self._recompute_flags()
        if self._flagged_ids:
            report = render_flag_report(self._state, self._flag_reasons)
            self.app.push_screen(ErrorModal(
                f"Cannot save: {len(self._flagged_ids)} entity/entities have "
                "broken references. Fix or delete them first.\n\n" + report
            ))
            return
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

    def action_switch_scenario(self) -> None:
        """Ctrl+O — return to the chooser, optionally saving first."""
        self._switch_scenario_flow()

    @on(Button.Pressed, "#switch-scenario-btn")
    def _switch_scenario_pressed(self, _: Button.Pressed) -> None:
        self._switch_scenario_flow()

    @work
    async def _switch_scenario_flow(self) -> None:
        """If dirty, ask the user how to handle unsaved edits before switching
        back to the scenario chooser. Flagged entities still block save."""
        if self._dirty:
            choice = await self.app.push_screen_wait(PickerModal(
                title="Unsaved edits",
                description=(
                    "You have unsaved edits in this scenario. Saving and "
                    "switching writes them to disk first; discarding drops "
                    "them entirely."
                ),
                items=[
                    ("save",    "Save and switch"),
                    ("discard", "Discard and switch"),
                    ("cancel",  "Cancel — keep editing"),
                ],
            ))
            if choice in (None, "cancel"):
                return
            if choice == "save":
                # Flagged entities still block save; refuse the switch too.
                self._recompute_flags()
                if self._flagged_ids:
                    report = render_flag_report(self._state, self._flag_reasons)
                    await self.app.push_screen_wait(ErrorModal(
                        f"Cannot save — {len(self._flagged_ids)} entity/entities "
                        "have broken references. Fix or discard them first.\n\n"
                        + report
                    ))
                    return
                self._save_to(self._db_path)
        from .chooser import ScenarioChooserScreen
        # set_flag_predicate left a closure pointing at this screen's _flagged_ids;
        # reset to no-op so the chooser doesn't inherit stale state.
        set_flag_predicate(lambda _eid: False)
        # Same for the detail-tab action provider.
        set_detail_action_provider(lambda _k, _e: [])
        self.app.switch_screen(ScenarioChooserScreen())

    # ── Cascade helpers (delete dependents along with the target) ──────────

    def _cascade_delete_location(self, eid: str) -> int:
        """Recursively delete a location subtree. Also clears civ/pop/mortal/
        species references that pointed at any deleted location. Returns the
        number of locations removed."""
        loc = self._state.locations.get(eid)
        if loc is None:
            return 0
        removed = 0
        for cid in list(loc.child_ids):
            removed += self._cascade_delete_location(str(cid))
        locedit.remove_from_parent(self._state, loc)
        self._state.locations.pop(eid, None)
        removed += 1
        return removed

    def _cascade_delete_civ(self, eid: str) -> dict[str, int]:
        """Delete a civilization and every pop/mortal owned by it. Returns a
        small counts dict for the user-facing report."""
        counts = {"civ": 0, "pops": 0, "mortals": 0}
        civ = self._state.civilizations.get(eid)
        if civ is None:
            return counts
        # Delete pops referring to this civ (with their own back-ref cleanup).
        for pid in [pid for pid, p in self._state.pops.items() if p.civilization_id == civ.id]:
            pop = self._state.pops[pid]
            entedit.unlink_pop_back_refs(self._state, pop)
            self._state.pops.pop(pid, None)
            counts["pops"] += 1
        # Delete mortals referring to this civ.
        for mid in [mid for mid, m in self._state.mortals.items() if m.civilization_id == civ.id]:
            mortal = self._state.mortals[mid]
            medit.unlink_back_refs(self._state, mortal)
            self._state.mortals.pop(mid, None)
            counts["mortals"] += 1
        entedit.unlink_civ_back_refs(self._state, civ)
        self._state.civilizations.pop(eid, None)
        counts["civ"] = 1
        return counts

    def _cascade_delete_species(self, eid: str) -> dict[str, int]:
        """Delete a species and every pop/mortal using it."""
        counts = {"species": 0, "pops": 0, "mortals": 0}
        sp = self._state.species.get(eid)
        if sp is None:
            return counts
        for pid in [pid for pid, p in self._state.pops.items() if p.species_id == sp.id]:
            pop = self._state.pops[pid]
            entedit.unlink_pop_back_refs(self._state, pop)
            self._state.pops.pop(pid, None)
            counts["pops"] += 1
        for mid in [mid for mid, m in self._state.mortals.items() if m.species_id == sp.id]:
            mortal = self._state.mortals[mid]
            medit.unlink_back_refs(self._state, mortal)
            self._state.mortals.pop(mid, None)
            counts["mortals"] += 1
        # Clear primary_species_id on any civ still pointing at this species
        # (the ref check won't blow up; the civ just has a dangling pointer).
        for civ in self._state.civilizations.values():
            if civ.primary_species_id == sp.id:
                civ.primary_species_id = None
        entedit.unlink_species_back_refs(self._state, sp)
        self._state.species.pop(eid, None)
        counts["species"] = 1
        return counts

    async def _prompt_delete_with_refs(
        self,
        target_label: str,
        blocking_refs: list[str],
        offer_cascade: bool,
    ) -> Optional[str]:
        """Show the three-way delete prompt when a target has blocking
        references. Returns 'cascade', 'flag', 'cancel', or None."""
        preview = "\n  • ".join(blocking_refs[:8])
        extra = f"\n  …and {len(blocking_refs) - 8} more" if len(blocking_refs) > 8 else ""
        items = []
        if offer_cascade:
            items.append(("cascade", "Delete and cascade through dependent entities"))
        items.extend([
            ("flag",   "Delete only — flag affected entities with broken refs"),
            ("cancel", "Cancel — keep everything"),
        ])
        choice = await self.app.push_screen_wait(PickerModal(
            title=f"Delete {target_label}?",
            description=(
                f"{len(blocking_refs)} reference(s) point at it:\n\n"
                f"  • {preview}{extra}\n\n"
                "Cascade removes dependents along with the target. Flagging "
                "removes only the target; the references become broken and "
                "those entities will be highlighted in red, blocking save."
            ),
            items=items,
        ))
        return choice

    @work
    async def _quit_confirm_flow(self) -> None:
        choice = await self.app.push_screen_wait(QuitConfirmModal())
        if choice is None:
            return  # Keep editing
        # If there are flagged entities, gate the quit on an extra
        # confirmation. Saving with flags is already refused upstream.
        self._recompute_flags()
        if self._flagged_ids:
            if choice == "save":
                report = render_flag_report(self._state, self._flag_reasons)
                await self.app.push_screen_wait(ErrorModal(
                    f"Cannot save while {len(self._flagged_ids)} entity/entities "
                    "have broken references. Fix them or choose 'discard and "
                    "quit'.\n\n" + report
                ))
                return
            # User picked "Quit" but has flagged entities — extra confirm.
            second = await self.app.push_screen_wait(PickerModal(
                title=f"⚠  {len(self._flagged_ids)} flagged entity/entities",
                items=[
                    ("discard", "Discard flagged entities and quit"),
                    ("cancel",  "Cancel — keep editing"),
                ],
                description=(
                    "These entities have broken references and will not be "
                    "saved. Choosing 'discard and quit' drops them entirely.\n\n"
                    + render_flag_report(self._state, self._flag_reasons)
                ),
            ))
            if second != "discard":
                return
            for eid in list(self._flagged_ids):
                self._state.mortals.pop(eid, None)
                self._state.pops.pop(eid, None)
                self._state.civilizations.pop(eid, None)
                self._state.species.pop(eid, None)
                self._state.locations.pop(eid, None)
            self.app.exit()
            return
        if choice == "save":
            self._save_to(self._db_path)
        self.app.exit()

    # ── Location editing toolbar buttons ───────────────────────────────────

    @on(Button.Pressed, "#add-location-btn")
    def _add_location_pressed(self, _: Button.Pressed) -> None:
        self._add_location_flow()

    @on(Button.Pressed, "#edit-location-btn")
    def _edit_location_pressed(self, _: Button.Pressed) -> None:
        self._edit_location_flow()

    @on(Button.Pressed, "#delete-location-btn")
    def _delete_location_pressed(self, _: Button.Pressed) -> None:
        self._delete_location_flow()

    @work
    async def _add_location_flow(self) -> None:
        # Step 1: pick the kind of location to create.
        kind = await self.app.push_screen_wait(PickerModal(
            title="What kind of location?",
            items=locedit.KIND_ITEMS,
            description=(
                "Galaxies live at the top of the spatial tree; Systems sit "
                "inside Galaxies; Worlds (SignificantLocations) sit inside "
                "Systems; Settlements (PopLocations) sit inside Worlds."
            ),
        ))
        if not kind or kind == BACK:
            return

        # Step 2: pick parent (Galaxy is parentless and skips this step).
        parent_uuid = None
        parent_kind = locedit.PARENT_KIND.get(kind)
        if parent_kind is not None:
            cands = locedit.candidates_for_kind(self._state, parent_kind)
            if not cands:
                await self.app.push_screen_wait(ErrorModal(
                    f"Cannot create a {kind}: no {parent_kind} exists to "
                    "contain it. Create the parent first."
                ))
                return
            parent_id_str = await self.app.push_screen_wait(PickerModal(
                title=f"Pick parent {parent_kind}",
                items=cands,
                show_back=True,
            ))
            if parent_id_str in (None, BACK):
                return
            parent_uuid = UUID(parent_id_str)

        # Step 3: enum picker for star_type (system) or condition (world).
        star_type = condition = None
        if kind == "system":
            star_type = await self.app.push_screen_wait(PickerModal(
                title="Star type",
                items=locedit.STAR_TYPE_ITEMS,
                show_back=True,
            ))
            if star_type in (None, BACK):
                return
        elif kind == "world":
            condition = await self.app.push_screen_wait(PickerModal(
                title="World condition",
                items=locedit.CONDITION_ITEMS,
                show_back=True,
            ))
            if condition in (None, BACK):
                return

        # Step 4: text-field form.
        fields = await self.app.push_screen_wait(TextFormModal(
            title=f"New {kind}",
            fields=locedit.text_fields_for(kind, None),
            show_back=True,
        ))
        if fields in (None, BACK):
            return
        err = locedit.validate_text_fields(kind, fields)
        if err:
            await self.app.push_screen_wait(ErrorModal(err))
            return

        # Construct and insert.
        new_loc = locedit.construct_location(
            kind, fields, parent_uuid,
            star_type=star_type, condition=condition,
        )
        self._state.locations[str(new_loc.id)] = new_loc
        if parent_uuid is None:
            self._state.universe.child_ids.append(new_loc.id)
        else:
            parent = self._state.locations.get(str(parent_uuid))
            if parent is not None:
                parent.child_ids.append(new_loc.id)
        self.mark_dirty()
        self._refresh_all()
        self.notify(f"Created {kind}: {new_loc.name}", timeout=3)

    @work
    async def _edit_location_flow(self) -> None:
        items = locedit.all_locations_grouped(self._state)
        if not items:
            await self.app.push_screen_wait(ErrorModal(
                "No locations exist yet. Use + Add Location to create one."
            ))
            return
        target_id = await self.app.push_screen_wait(PickerModal(
            title="Edit which location?",
            items=items,
        ))
        if not target_id:
            return
        loc = self._state.locations.get(target_id)
        if loc is None:
            await self.app.push_screen_wait(ErrorModal("Location not found."))
            return
        await self._location_edit_loop(loc)

    async def _location_edit_loop(self, loc) -> None:
        kind = locedit.location_kind(loc)
        kind_label = {"galaxy": "galaxy", "system": "system",
                      "world": "world", "poploc": "settlement"}.get(kind, kind)
        # All location kinds share Basics + Coordinates; Worlds add the
        # belief/footprint sub-editors on top.
        while True:
            menu = [
                ("basics", "Basics (name, type, kind-specific fields)"),
                ("coords", f"Coordinates (x={loc.coordinates.x:.1f}, y={loc.coordinates.y:.1f}, z={loc.coordinates.z:.1f})"),
            ]
            if kind == "world":
                from core.universe_core import SignificantLocation
                assert isinstance(loc, SignificantLocation)
                menu.extend([
                    ("expression", f"Domain expression ({len(loc.domain_expression)})"),
                    ("geo_tags",   f"Geo tags ({len(loc.geo_tags)})"),
                    ("atmo_tags",  f"Atmo tags ({len(loc.atmo_tags)})"),
                    ("footprint",  "Local footprint (4 floats)"),
                ])
            menu.append(("done", "Done"))
            choice = await self.app.push_screen_wait(PickerModal(
                title=f"Edit {kind_label}: {loc.name}",
                items=menu,
            ))
            if choice in (None, "done"):
                return
            if choice == "basics":
                await self._edit_location_basics(loc, kind)
            elif choice == "coords":
                await fedit.edit_coordinates(self, loc.coordinates)
            elif choice == "expression":
                await fedit.edit_tag_weight_dict(
                    self, loc.domain_expression,
                    title_prefix=f"{loc.name} — Domain expression",
                    tag_namespace="domain",
                )
            elif choice == "geo_tags":
                await fedit.edit_string_list(
                    self, loc.geo_tags,
                    title_prefix=f"{loc.name} — Geo tags",
                    tag_namespace="free",
                )
            elif choice == "atmo_tags":
                await fedit.edit_string_list(
                    self, loc.atmo_tags,
                    title_prefix=f"{loc.name} — Atmo tags",
                    tag_namespace="free",
                )
            elif choice == "footprint":
                await fedit.edit_loc_footprint(self, loc.local_footprint)

    async def _edit_location_basics(self, loc, kind: str) -> None:
        """Edit a location's text-form fields + its kind-specific enum."""
        new_star_type = None
        new_condition = None
        if kind == "system":
            new_star_type = await self.app.push_screen_wait(PickerModal(
                title=f"Star type (current: {loc.star_type.value})",
                items=locedit.STAR_TYPE_ITEMS,
                show_back=True,
            ))
            if new_star_type in (None, BACK):
                return
        elif kind == "world":
            new_condition = await self.app.push_screen_wait(PickerModal(
                title=f"Condition (current: {loc.condition.value})",
                items=locedit.CONDITION_ITEMS,
                show_back=True,
            ))
            if new_condition in (None, BACK):
                return
        fields = await self.app.push_screen_wait(TextFormModal(
            title=f"Edit {kind}: {loc.name}",
            fields=locedit.text_fields_for(kind, loc),
            show_back=True,
        ))
        if fields in (None, BACK):
            return
        err = locedit.validate_text_fields(kind, fields)
        if err:
            await self.app.push_screen_wait(ErrorModal(err))
            return
        locedit.apply_text_fields(loc, kind, fields)
        if new_star_type is not None:
            from core.universe_core import StarType
            loc.star_type = StarType(new_star_type)
        if new_condition is not None:
            from core.universe_core import LocCondition
            loc.condition = LocCondition(new_condition)
        self.mark_dirty()
        self._refresh_all()

    @work
    async def _delete_location_flow(self) -> None:
        items = locedit.all_locations_grouped(self._state)
        if not items:
            await self.app.push_screen_wait(ErrorModal("No locations to delete."))
            return
        target_id = await self.app.push_screen_wait(PickerModal(
            title="Delete which location?",
            items=items,
        ))
        if not target_id:
            return
        await self._location_delete_by_id(target_id)

    async def _location_delete_by_id(self, target_id: str) -> None:
        loc = self._state.locations.get(target_id)
        if loc is None:
            await self.app.push_screen_wait(ErrorModal("Location not found."))
            return

        # Reference check.
        blocks = locedit.find_blocking_references(self._state, target_id)
        if not blocks:
            confirm = await self.app.push_screen_wait(PickerModal(
                title=f"Delete {loc.name}?",
                items=[("yes", "Yes, delete it."), ("no", "No, cancel.")],
                description="This cannot be undone within the current session.",
            ))
            if confirm != "yes":
                return
            locedit.remove_from_parent(self._state, loc)
            self._state.locations.pop(target_id, None)
            self.mark_dirty(); self._refresh_all()
            self.notify(f"Deleted: {loc.name}", timeout=3)
            return

        choice = await self._prompt_delete_with_refs(
            target_label=loc.name,
            blocking_refs=blocks,
            offer_cascade=True,
        )
        if choice in (None, "cancel"):
            return
        if choice == "cascade":
            removed = self._cascade_delete_location(target_id)
            self.mark_dirty(); self._refresh_all()
            self.notify(f"Deleted {removed} location(s) (cascade).", timeout=4)
            return
        if choice == "flag":
            locedit.remove_from_parent(self._state, loc)
            self._state.locations.pop(target_id, None)
            self.mark_dirty(); self._refresh_all()
            self.notify(
                f"Deleted {loc.name}. {len(self._flagged_ids)} entity/entities flagged.",
                severity="warning", timeout=5,
            )

    # ── Civilization / Species / Pop button handlers ───────────────────────

    @on(Button.Pressed, "#add-civ-btn")
    def _add_civ_pressed(self, _: Button.Pressed) -> None:
        self._add_civ_flow()

    @on(Button.Pressed, "#edit-civ-btn")
    def _edit_civ_pressed(self, _: Button.Pressed) -> None:
        self._edit_civ_flow()

    @on(Button.Pressed, "#delete-civ-btn")
    def _delete_civ_pressed(self, _: Button.Pressed) -> None:
        self._delete_civ_flow()

    @on(Button.Pressed, "#add-species-btn")
    def _add_species_pressed(self, _: Button.Pressed) -> None:
        self._add_species_flow()

    @on(Button.Pressed, "#edit-species-btn")
    def _edit_species_pressed(self, _: Button.Pressed) -> None:
        self._edit_species_flow()

    @on(Button.Pressed, "#delete-species-btn")
    def _delete_species_pressed(self, _: Button.Pressed) -> None:
        self._delete_species_flow()

    @on(Button.Pressed, "#add-pop-btn")
    def _add_pop_pressed(self, _: Button.Pressed) -> None:
        self._add_pop_flow()

    @on(Button.Pressed, "#edit-pop-btn")
    def _edit_pop_pressed(self, _: Button.Pressed) -> None:
        self._edit_pop_flow()

    @on(Button.Pressed, "#delete-pop-btn")
    def _delete_pop_pressed(self, _: Button.Pressed) -> None:
        self._delete_pop_flow()

    # ── Species flows ──────────────────────────────────────────────────────

    @work
    async def _add_species_flow(self) -> None:
        # Origin world (optional).
        origin = await self.app.push_screen_wait(PickerModal(
            title="Origin world (optional)",
            items=entedit.world_picker_items(self._state, allow_none=True),
            description="Choose the world this species evolved on, or '(none)'.",
        ))
        if origin is None:
            return
        origin_uuid = None if origin == "__none__" else UUID(origin)
        # Sapience.
        sap = await self.app.push_screen_wait(PickerModal(
            title="Sapient?", items=entedit.YESNO_ITEMS, show_back=True,
        ))
        if sap in (None, BACK):
            return
        # Condition.
        cond = await self.app.push_screen_wait(PickerModal(
            title="Condition", items=entedit.SPECIES_CONDITION_ITEMS, show_back=True,
        ))
        if cond in (None, BACK):
            return
        # Text form.
        fields = await self.app.push_screen_wait(TextFormModal(
            title="New Species",
            fields=entedit.species_text_fields(None),
            show_back=True,
        ))
        if fields in (None, BACK):
            return
        err = entedit.validate_species_fields(fields)
        if err:
            await self.app.push_screen_wait(ErrorModal(err)); return
        from core.universe_core import SpeciesCondition
        sp = entedit.construct_species(
            fields, origin_uuid, sap == "yes", SpeciesCondition(cond),
        )
        self._state.species[str(sp.id)] = sp
        if origin_uuid is not None:
            world = self._state.locations.get(str(origin_uuid))
            if world is not None and sp.id not in world.species_ids:
                world.species_ids.append(sp.id)
        self.mark_dirty()
        self._refresh_all()
        self.notify(f"Created species: {sp.name}", timeout=3)

    @work
    async def _edit_species_flow(self) -> None:
        items = entedit.species_picker_items(self._state)
        if not items:
            await self.app.push_screen_wait(ErrorModal("No species exist yet."))
            return
        sid = await self.app.push_screen_wait(PickerModal(
            title="Edit which species?", items=items,
        ))
        if not sid:
            return
        sp = self._state.species.get(sid)
        if sp is None:
            await self.app.push_screen_wait(ErrorModal("Species not found.")); return
        await self._species_edit_loop(sp)

    async def _species_edit_loop(self, sp) -> None:
        while True:
            choice = await self.app.push_screen_wait(PickerModal(
                title=f"Edit species: {sp.name}",
                items=[
                    ("basics",      "Basics (name, lifespans, condition)"),
                    ("domain_tags", f"Domain affinity tags ({len(sp.domain_tags)})"),
                    ("bio_tags",    f"Bio tags ({len(sp.bio_tags)})"),
                    ("done",        "Done"),
                ],
            ))
            if choice in (None, "done"):
                return
            if choice == "basics":
                await self._edit_species_basics(sp)
            elif choice == "domain_tags":
                await fedit.edit_string_list(
                    self, sp.domain_tags,
                    title_prefix=f"{sp.name} — Domain tags",
                    tag_namespace="domain",
                )
            elif choice == "bio_tags":
                await fedit.edit_string_list(
                    self, sp.bio_tags,
                    title_prefix=f"{sp.name} — Bio tags",
                    tag_namespace="free",
                )

    async def _edit_species_basics(self, sp) -> None:
        # Sapience stays — toggling it would invalidate any Pops using
        # social_class vs wild_stratum without a reconciling pass.
        cond = await self.app.push_screen_wait(PickerModal(
            title=f"Condition (current: {sp.condition.value})",
            items=entedit.SPECIES_CONDITION_ITEMS, show_back=True,
        ))
        if cond in (None, BACK):
            return
        transplanted = await self.app.push_screen_wait(PickerModal(
            title=f"Transplanted? (current: {'yes' if sp.transplanted else 'no'})",
            items=entedit.YESNO_ITEMS, show_back=True,
        ))
        if transplanted in (None, BACK):
            return
        fields = await self.app.push_screen_wait(TextFormModal(
            title=f"Edit species: {sp.name}",
            fields=entedit.species_text_fields(sp), show_back=True,
        ))
        if fields in (None, BACK):
            return
        err = entedit.validate_species_fields(fields)
        if err:
            await self.app.push_screen_wait(ErrorModal(err)); return
        from core.universe_core import SpeciesCondition
        entedit.apply_species_fields(sp, fields)
        sp.condition = SpeciesCondition(cond)
        sp.transplanted = (transplanted == "yes")
        self.mark_dirty(); self._refresh_all()

    @work
    async def _delete_species_flow(self) -> None:
        items = entedit.species_picker_items(self._state)
        if not items:
            await self.app.push_screen_wait(ErrorModal("No species to delete.")); return
        sid = await self.app.push_screen_wait(PickerModal(
            title="Delete which species?", items=items,
        ))
        if not sid:
            return
        await self._species_delete_by_id(sid)

    async def _species_delete_by_id(self, sid: str) -> None:
        sp = self._state.species.get(sid)
        if sp is None:
            await self.app.push_screen_wait(ErrorModal("Species not found.")); return
        blocks = entedit.find_species_references(self._state, sid)
        if not blocks:
            confirm = await self.app.push_screen_wait(PickerModal(
                title=f"Delete species {sp.name}?",
                items=[("yes", "Yes, delete it."), ("no", "No, cancel.")],
            ))
            if confirm != "yes":
                return
            entedit.unlink_species_back_refs(self._state, sp)
            self._state.species.pop(sid, None)
            self.mark_dirty(); self._refresh_all()
            self.notify(f"Deleted species: {sp.name}", timeout=3)
            return
        choice = await self._prompt_delete_with_refs(
            target_label=f"species {sp.name}",
            blocking_refs=blocks,
            offer_cascade=True,
        )
        if choice in (None, "cancel"):
            return
        if choice == "cascade":
            counts = self._cascade_delete_species(sid)
            self.mark_dirty(); self._refresh_all()
            self.notify(
                f"Cascaded: {counts['species']} species, {counts['pops']} pop(s), "
                f"{counts['mortals']} mortal(s).", timeout=5,
            )
            return
        if choice == "flag":
            entedit.unlink_species_back_refs(self._state, sp)
            self._state.species.pop(sid, None)
            self.mark_dirty(); self._refresh_all()
            self.notify(
                f"Deleted {sp.name}. {len(self._flagged_ids)} entity/entities flagged.",
                severity="warning", timeout=5,
            )

    # ── Civilization flows ─────────────────────────────────────────────────

    @work
    async def _add_civ_flow(self) -> None:
        # Origin location (required, must be a SignificantLocation).
        worlds = entedit.world_picker_items(self._state, allow_none=False)
        if not worlds:
            await self.app.push_screen_wait(ErrorModal(
                "No worlds exist yet — create a SignificantLocation first."
            ))
            return
        origin_id = await self.app.push_screen_wait(PickerModal(
            title="Origin world", items=worlds,
        ))
        if not origin_id:
            return
        # Scale.
        scale = await self.app.push_screen_wait(PickerModal(
            title="Civilization scale",
            items=entedit.CIV_SCALE_ITEMS, show_back=True,
        ))
        if scale in (None, BACK):
            return
        # Primary species (optional).
        sp_id = await self.app.push_screen_wait(PickerModal(
            title="Primary species (optional)",
            items=entedit.species_picker_items(self._state, allow_none=True),
            show_back=True,
        ))
        if sp_id in (None, BACK):
            return
        sp_uuid = None if sp_id == "__none__" else UUID(sp_id)
        # Text form.
        fields = await self.app.push_screen_wait(TextFormModal(
            title="New Civilization",
            fields=entedit.civ_text_fields(None), show_back=True,
        ))
        if fields in (None, BACK):
            return
        err = entedit.validate_civ_fields(fields)
        if err:
            await self.app.push_screen_wait(ErrorModal(err)); return
        from core.universe_core import CivilizationScale
        civ = entedit.construct_civilization(
            fields, CivilizationScale(scale), UUID(origin_id), sp_uuid,
        )
        self._state.civilizations[str(civ.id)] = civ
        world = self._state.locations.get(origin_id)
        if world is not None and civ.id not in world.civilization_ids:
            world.civilization_ids.append(civ.id)
        self.mark_dirty(); self._refresh_all()
        self.notify(f"Created civilization: {civ.name}", timeout=3)

    @work
    async def _edit_civ_flow(self) -> None:
        items = entedit.civ_picker_items(self._state)
        if not items:
            await self.app.push_screen_wait(ErrorModal("No civilizations exist yet.")); return
        cid = await self.app.push_screen_wait(PickerModal(
            title="Edit which civilization?", items=items,
        ))
        if not cid:
            return
        civ = self._state.civilizations.get(cid)
        if civ is None:
            await self.app.push_screen_wait(ErrorModal("Civilization not found.")); return
        await self._civ_edit_loop(civ)

    async def _civ_edit_loop(self, civ) -> None:
        """Sub-menu loop on a resolved Civilization. Called both by the
        picker-driven flow and by the inline detail-tab Edit button."""
        while True:
            choice = await self.app.push_screen_wait(PickerModal(
                title=f"Edit civilization: {civ.name}",
                items=[
                    ("basics",         "Basics (name, scale, age, health, theistic, divine awareness)"),
                    ("beliefs",        f"Dominant beliefs ({len(civ.dominant_beliefs)})"),
                    ("est_beliefs",    f"Established beliefs ({len(civ.established_beliefs)})"),
                    ("culture",        f"Culture tags ({len(civ.culture_tags)})"),
                    ("est_culture",    f"Established culture tags ({len(civ.established_culture_tags)})"),
                    ("core_locs",      f"Core locations ({len(civ.core_locs)})"),
                    ("done",           "Done"),
                ],
            ))
            if choice in (None, "done"):
                return
            if choice == "basics":
                await self._edit_civ_basics(civ)
            elif choice == "beliefs":
                await fedit.edit_tag_weight_dict(
                    self, civ.dominant_beliefs,
                    title_prefix=f"{civ.name} — Dominant beliefs",
                    tag_namespace="domain",
                )
            elif choice == "est_beliefs":
                await fedit.edit_tag_weight_dict(
                    self, civ.established_beliefs,
                    title_prefix=f"{civ.name} — Established beliefs",
                    tag_namespace="domain",
                )
            elif choice == "culture":
                await fedit.edit_tag_weight_dict(
                    self, civ.culture_tags,
                    title_prefix=f"{civ.name} — Culture tags",
                    tag_namespace="culture",
                )
            elif choice == "est_culture":
                await fedit.edit_tag_weight_dict(
                    self, civ.established_culture_tags,
                    title_prefix=f"{civ.name} — Established culture tags",
                    tag_namespace="culture",
                )
            elif choice == "core_locs":
                await self._edit_civ_core_locs(civ)

    async def _edit_civ_core_locs(self, civ) -> None:
        """Loop add/remove over `civ.core_locs` (list of SignificantLocation
        UUIDs). The civ's home worlds; pops at locations not in this list
        are weighted down when civ-aggregate beliefs/culture roll up."""
        while True:
            n = len(civ.core_locs)
            choice = await self.app.push_screen_wait(PickerModal(
                title=f"{civ.name} — Core locations ({n})",
                items=[
                    ("add",    "+ Add core location"),
                    ("remove", "Remove a core location"),
                    ("done",   "Done"),
                ],
            ))
            if choice in (None, "done"):
                return
            if choice == "add":
                existing = {str(x) for x in civ.core_locs}
                candidates = [
                    (eid, name) for (eid, name) in entedit.world_picker_items(self._state)
                    if eid not in existing
                ]
                if not candidates:
                    await self.app.push_screen_wait(ErrorModal(
                        "Every existing world is already a core location."
                    )); continue
                picked = await self.app.push_screen_wait(PickerModal(
                    title="Pick a world to add", items=candidates, show_back=True,
                ))
                if picked in (None, BACK):
                    continue
                civ.core_locs.append(UUID(picked))
                self.mark_dirty(); self._refresh_all()
            elif choice == "remove":
                if not civ.core_locs:
                    await self.app.push_screen_wait(ErrorModal(
                        "No core locations to remove."
                    )); continue
                items = []
                for cid in civ.core_locs:
                    loc = self._state.locations.get(str(cid))
                    items.append((str(cid), loc.name if loc else str(cid)[:8]))
                picked = await self.app.push_screen_wait(PickerModal(
                    title="Remove which?", items=items, show_back=True,
                ))
                if picked in (None, BACK):
                    continue
                civ.core_locs = [c for c in civ.core_locs if str(c) != picked]
                self.mark_dirty(); self._refresh_all()

    async def _edit_civ_basics(self, civ) -> None:
        scale = await self.app.push_screen_wait(PickerModal(
            title=f"Scale (current: {civ.scale.value})",
            items=entedit.CIV_SCALE_ITEMS, show_back=True,
        ))
        if scale in (None, BACK):
            return
        theistic = await self.app.push_screen_wait(PickerModal(
            title=f"Theistic? (current: {'yes' if civ.theistic else 'no'})",
            items=entedit.YESNO_ITEMS, show_back=True,
        ))
        if theistic in (None, BACK):
            return
        fields = await self.app.push_screen_wait(TextFormModal(
            title=f"Edit civilization: {civ.name}",
            fields=entedit.civ_text_fields(civ), show_back=True,
        ))
        if fields in (None, BACK):
            return
        err = entedit.validate_civ_fields(fields)
        if err:
            await self.app.push_screen_wait(ErrorModal(err)); return
        from core.universe_core import CivilizationScale
        entedit.apply_civ_fields(civ, fields)
        civ.scale = CivilizationScale(scale)
        civ.theistic = (theistic == "yes")
        self.mark_dirty(); self._refresh_all()

    @work
    async def _delete_civ_flow(self) -> None:
        items = entedit.civ_picker_items(self._state)
        if not items:
            await self.app.push_screen_wait(ErrorModal("No civilizations to delete.")); return
        cid = await self.app.push_screen_wait(PickerModal(
            title="Delete which civilization?", items=items,
        ))
        if not cid:
            return
        await self._civ_delete_by_id(cid)

    async def _civ_delete_by_id(self, cid: str) -> None:
        civ = self._state.civilizations.get(cid)
        if civ is None:
            await self.app.push_screen_wait(ErrorModal("Civilization not found.")); return
        blocks = entedit.find_civ_references(self._state, cid)
        if not blocks:
            confirm = await self.app.push_screen_wait(PickerModal(
                title=f"Delete civilization {civ.name}?",
                items=[("yes", "Yes, delete it."), ("no", "No, cancel.")],
            ))
            if confirm != "yes":
                return
            entedit.unlink_civ_back_refs(self._state, civ)
            self._state.civilizations.pop(cid, None)
            self.mark_dirty(); self._refresh_all()
            self.notify(f"Deleted civilization: {civ.name}", timeout=3)
            return
        choice = await self._prompt_delete_with_refs(
            target_label=f"civilization {civ.name}",
            blocking_refs=blocks,
            offer_cascade=True,
        )
        if choice in (None, "cancel"):
            return
        if choice == "cascade":
            counts = self._cascade_delete_civ(cid)
            self.mark_dirty(); self._refresh_all()
            self.notify(
                f"Cascaded: {counts['civ']} civ, {counts['pops']} pop(s), "
                f"{counts['mortals']} mortal(s).", timeout=5,
            )
            return
        if choice == "flag":
            entedit.unlink_civ_back_refs(self._state, civ)
            self._state.civilizations.pop(cid, None)
            self.mark_dirty(); self._refresh_all()
            self.notify(
                f"Deleted {civ.name}. {len(self._flagged_ids)} entity/entities flagged.",
                severity="warning", timeout=5,
            )

    # ── Pop flows ──────────────────────────────────────────────────────────

    @work
    async def _add_pop_flow(self) -> None:
        # Species (required — determines social_class vs wild_stratum).
        sp_items = entedit.species_picker_items(self._state, allow_none=False)
        if not sp_items:
            await self.app.push_screen_wait(ErrorModal(
                "No species exist yet — create one first."
            ))
            return
        sp_id = await self.app.push_screen_wait(PickerModal(
            title="Pop species", items=sp_items,
        ))
        if not sp_id:
            return
        sp = self._state.species.get(sp_id)
        # Civilization (optional but typical).
        civ_items = entedit.civ_picker_items(self._state)
        civ_items.insert(0, ("__none__", "(no civilization — wild pop)"))
        civ_id = await self.app.push_screen_wait(PickerModal(
            title="Civilization", items=civ_items, show_back=True,
        ))
        if civ_id in (None, BACK):
            return
        civ_uuid = None if civ_id == "__none__" else UUID(civ_id)
        # PopLocation (required).
        loc_items = entedit.poploc_picker_items(self._state)
        if not loc_items:
            await self.app.push_screen_wait(ErrorModal(
                "No PopLocations exist yet — create a Settlement first."
            ))
            return
        loc_id = await self.app.push_screen_wait(PickerModal(
            title="Current location (PopLocation)", items=loc_items, show_back=True,
        ))
        if loc_id in (None, BACK):
            return
        # Stratum: social class for sapient species, wild stratum otherwise.
        from core.universe_core import SocialClass, WildStratum
        social_class = wild_stratum = None
        if sp and sp.sapient:
            chosen = await self.app.push_screen_wait(PickerModal(
                title="Social class", items=entedit.SOCIAL_CLASS_ITEMS, show_back=True,
            ))
            if chosen in (None, BACK):
                return
            social_class = SocialClass(chosen)
        else:
            chosen = await self.app.push_screen_wait(PickerModal(
                title="Wild stratum", items=entedit.WILD_STRATUM_ITEMS, show_back=True,
            ))
            if chosen in (None, BACK):
                return
            wild_stratum = WildStratum(chosen)
        # Text form.
        fields = await self.app.push_screen_wait(TextFormModal(
            title="New Pop", fields=entedit.pop_text_fields(None), show_back=True,
        ))
        if fields in (None, BACK):
            return
        err = entedit.validate_pop_fields(fields)
        if err:
            await self.app.push_screen_wait(ErrorModal(err)); return
        # Auto-seed beliefs/culture from the parent civ's established profile,
        # if a civ is selected. A wild pop (civ=None) starts with empty dicts.
        seed_beliefs = seed_culture = None
        if civ_uuid is not None:
            parent_civ = self._state.civilizations.get(str(civ_uuid))
            if parent_civ is not None:
                seed_beliefs = parent_civ.established_beliefs or None
                seed_culture = parent_civ.established_culture_tags or None
        pop = entedit.construct_pop(
            fields, civ_uuid, UUID(sp_id), UUID(loc_id),
            social_class, wild_stratum,
            seed_beliefs=seed_beliefs, seed_culture=seed_culture,
        )
        self._state.pops[str(pop.id)] = pop
        if civ_uuid is not None:
            civ = self._state.civilizations.get(str(civ_uuid))
            if civ is not None and pop.id not in civ.pop_ids:
                civ.pop_ids.append(pop.id)
        loc = self._state.locations.get(loc_id)
        if loc is not None and pop.id not in loc.pop_ids:
            loc.pop_ids.append(pop.id)
        self.mark_dirty(); self._refresh_all()
        self.notify(f"Created pop ({sp.name if sp else '?'})", timeout=3)

    @work
    async def _edit_pop_flow(self) -> None:
        items = entedit.pop_picker_items(self._state)
        if not items:
            await self.app.push_screen_wait(ErrorModal("No pops exist yet.")); return
        pid = await self.app.push_screen_wait(PickerModal(
            title="Edit which pop?", items=items,
        ))
        if not pid:
            return
        pop = self._state.pops.get(pid)
        if pop is None:
            await self.app.push_screen_wait(ErrorModal("Pop not found.")); return
        await self._pop_edit_loop(pop)

    async def _pop_edit_loop(self, pop) -> None:
        # Reassigning species/civ/location/stratum is deferred (back-ref
        # bookkeeping); the basics form just edits size_fractional.
        while True:
            sp = self._state.species.get(str(pop.species_id)) if pop.species_id else None
            sp_label = sp.name if sp else "?"
            choice = await self.app.push_screen_wait(PickerModal(
                title=f"Edit pop ({sp_label})",
                items=[
                    ("basics",     "Basics (size)"),
                    ("beliefs",    f"Dominant beliefs ({len(pop.dominant_beliefs)})"),
                    ("culture",    f"Culture tags ({len(pop.culture_tags)})"),
                    ("reassign",   "Reassign species / civ / location / stratum"),
                    ("done",       "Done"),
                ],
            ))
            if choice in (None, "done"):
                return
            if choice == "basics":
                fields = await self.app.push_screen_wait(TextFormModal(
                    title="Edit pop size",
                    fields=entedit.pop_text_fields(pop), show_back=True,
                ))
                if fields in (None, BACK):
                    continue
                err = entedit.validate_pop_fields(fields)
                if err:
                    await self.app.push_screen_wait(ErrorModal(err)); continue
                entedit.apply_pop_fields(pop, fields)
                self.mark_dirty(); self._refresh_all()
            elif choice == "beliefs":
                await fedit.edit_tag_weight_dict(
                    self, pop.dominant_beliefs,
                    title_prefix=f"{sp_label} pop — Dominant beliefs",
                    tag_namespace="domain",
                )
            elif choice == "culture":
                await fedit.edit_tag_weight_dict(
                    self, pop.culture_tags,
                    title_prefix=f"{sp_label} pop — Culture tags",
                    tag_namespace="culture",
                )
            elif choice == "reassign":
                await self._pop_reassign_submenu(pop)

    async def _pop_reassign_submenu(self, pop) -> None:
        """Nested picker over the four reassignable fields."""
        while True:
            sp = self._state.species.get(str(pop.species_id)) if pop.species_id else None
            civ = self._state.civilizations.get(str(pop.civilization_id)) if pop.civilization_id else None
            loc = self._state.locations.get(str(pop.current_location)) if pop.current_location else None
            stratum = (
                pop.social_class.value if pop.social_class
                else (pop.wild_stratum.value if pop.wild_stratum else "(none)")
            )
            choice = await self.app.push_screen_wait(PickerModal(
                title="Reassign which field?",
                items=[
                    ("species",  f"Species  (current: {sp.name if sp else '?'})"),
                    ("civ",      f"Civilization  (current: {civ.name if civ else '(none — wild)'})"),
                    ("location", f"Location  (current: {loc.name if loc else '?'})"),
                    ("stratum",  f"Stratum  (current: {stratum})"),
                    ("back",     "← Back"),
                ],
            ))
            if choice in (None, "back"):
                return
            if choice == "species":
                await self._reassign_pop_species(pop)
            elif choice == "civ":
                await self._reassign_pop_civ(pop)
            elif choice == "location":
                await self._reassign_pop_location(pop)
            elif choice == "stratum":
                await self._reassign_pop_stratum(pop)

    async def _reassign_pop_species(self, pop) -> None:
        items = entedit.species_picker_items(self._state)
        if not items:
            await self.app.push_screen_wait(ErrorModal("No species exist."))
            return
        sp_id = await self.app.push_screen_wait(PickerModal(
            title="New species", items=items, show_back=True,
        ))
        if sp_id in (None, BACK):
            return
        new_sp = self._state.species[sp_id]
        old_sp = self._state.species.get(str(pop.species_id)) if pop.species_id else None
        # If sapience flips, the stratum kind has to change too.
        if old_sp is None or old_sp.sapient != new_sp.sapient:
            if new_sp.sapient:
                chosen = await self.app.push_screen_wait(PickerModal(
                    title="Pick a social class for the new species",
                    items=entedit.SOCIAL_CLASS_ITEMS, show_back=True,
                ))
                if chosen in (None, BACK):
                    return
                from core.universe_core import SocialClass
                pop.social_class = SocialClass(chosen)
                pop.wild_stratum = None
            else:
                chosen = await self.app.push_screen_wait(PickerModal(
                    title="Pick a wild stratum for the new species",
                    items=entedit.WILD_STRATUM_ITEMS, show_back=True,
                ))
                if chosen in (None, BACK):
                    return
                from core.universe_core import WildStratum
                pop.wild_stratum = WildStratum(chosen)
                pop.social_class = None
        pop.species_id = UUID(sp_id)
        self.mark_dirty(); self._refresh_all()
        self.notify(f"Pop species → {new_sp.name}", timeout=3)

    async def _reassign_pop_civ(self, pop) -> None:
        items = entedit.civ_picker_items(self._state)
        items.insert(0, ("__none__", "(no civilization — wild pop)"))
        civ_id = await self.app.push_screen_wait(PickerModal(
            title="New civilization", items=items, show_back=True,
        ))
        if civ_id in (None, BACK):
            return
        # Unlink from old civ's pop_ids.
        if pop.civilization_id:
            old_civ = self._state.civilizations.get(str(pop.civilization_id))
            if old_civ is not None:
                old_civ.pop_ids = [p for p in old_civ.pop_ids if p != pop.id]
        if civ_id == "__none__":
            pop.civilization_id = None
            self.mark_dirty(); self._refresh_all()
            self.notify("Pop civilization cleared (wild).", timeout=3)
            return
        new_civ = self._state.civilizations[civ_id]
        pop.civilization_id = UUID(civ_id)
        if pop.id not in new_civ.pop_ids:
            new_civ.pop_ids.append(pop.id)
        self.mark_dirty(); self._refresh_all()
        self.notify(f"Pop civilization → {new_civ.name}", timeout=3)

    async def _reassign_pop_location(self, pop) -> None:
        items = entedit.poploc_picker_items(self._state)
        if not items:
            await self.app.push_screen_wait(ErrorModal(
                "No PopLocations exist — create a Settlement first."
            ))
            return
        loc_id = await self.app.push_screen_wait(PickerModal(
            title="New location (PopLocation)", items=items, show_back=True,
        ))
        if loc_id in (None, BACK):
            return
        # Unlink from old location's pop_ids.
        from core.universe_core import PopLocation
        if pop.current_location:
            old_loc = self._state.locations.get(str(pop.current_location))
            if isinstance(old_loc, PopLocation):
                old_loc.pop_ids = [p for p in old_loc.pop_ids if p != pop.id]
        pop.current_location = UUID(loc_id)
        new_loc = self._state.locations[loc_id]
        if pop.id not in new_loc.pop_ids:
            new_loc.pop_ids.append(pop.id)
        self.mark_dirty(); self._refresh_all()
        self.notify(f"Pop location → {new_loc.name}", timeout=3)

    async def _reassign_pop_stratum(self, pop) -> None:
        sp = self._state.species.get(str(pop.species_id)) if pop.species_id else None
        if sp is None:
            await self.app.push_screen_wait(ErrorModal(
                "Pop has no species — assign a species first."
            ))
            return
        if sp.sapient:
            chosen = await self.app.push_screen_wait(PickerModal(
                title=f"Social class (current: {pop.social_class.value if pop.social_class else '(none)'})",
                items=entedit.SOCIAL_CLASS_ITEMS, show_back=True,
            ))
            if chosen in (None, BACK):
                return
            from core.universe_core import SocialClass
            pop.social_class = SocialClass(chosen)
            pop.wild_stratum = None
        else:
            chosen = await self.app.push_screen_wait(PickerModal(
                title=f"Wild stratum (current: {pop.wild_stratum.value if pop.wild_stratum else '(none)'})",
                items=entedit.WILD_STRATUM_ITEMS, show_back=True,
            ))
            if chosen in (None, BACK):
                return
            from core.universe_core import WildStratum
            pop.wild_stratum = WildStratum(chosen)
            pop.social_class = None
        self.mark_dirty(); self._refresh_all()
        self.notify(f"Pop stratum → {chosen}", timeout=3)

    @work
    async def _delete_pop_flow(self) -> None:
        items = entedit.pop_picker_items(self._state)
        if not items:
            await self.app.push_screen_wait(ErrorModal("No pops to delete.")); return
        pid = await self.app.push_screen_wait(PickerModal(
            title="Delete which pop?", items=items,
        ))
        if not pid:
            return
        await self._pop_delete_by_id(pid)

    async def _pop_delete_by_id(self, pid: str) -> None:
        pop = self._state.pops.get(pid)
        if pop is None:
            await self.app.push_screen_wait(ErrorModal("Pop not found.")); return
        blocks = entedit.find_pop_references(self._state, pid)
        if not blocks:
            confirm = await self.app.push_screen_wait(PickerModal(
                title="Delete this pop?",
                items=[("yes", "Yes, delete it."), ("no", "No, cancel.")],
            ))
            if confirm != "yes":
                return
            entedit.unlink_pop_back_refs(self._state, pop)
            self._state.pops.pop(pid, None)
            self.mark_dirty(); self._refresh_all()
            self.notify("Deleted pop.", timeout=3)
            return
        choice = await self._prompt_delete_with_refs(
            target_label="this pop",
            blocking_refs=blocks,
            offer_cascade=True,
        )
        if choice in (None, "cancel"):
            return
        if choice == "cascade":
            removed_mortals = 0
            for mid in [mid for mid, m in self._state.mortals.items() if m.pop_id == pop.id]:
                mortal = self._state.mortals[mid]
                medit.unlink_back_refs(self._state, mortal)
                self._state.mortals.pop(mid, None)
                removed_mortals += 1
            entedit.unlink_pop_back_refs(self._state, pop)
            self._state.pops.pop(pid, None)
            self.mark_dirty(); self._refresh_all()
            self.notify(
                f"Cascaded: 1 pop, {removed_mortals} mortal(s).", timeout=5,
            )
            return
        if choice == "flag":
            entedit.unlink_pop_back_refs(self._state, pop)
            self._state.pops.pop(pid, None)
            self.mark_dirty(); self._refresh_all()
            self.notify(
                f"Deleted pop. {len(self._flagged_ids)} entity/entities flagged.",
                severity="warning", timeout=5,
            )

    # ── Notable Mortal handlers ────────────────────────────────────────────

    @on(Button.Pressed, "#add-mortal-btn")
    def _add_mortal_pressed(self, _: Button.Pressed) -> None:
        self._add_mortal_flow()

    @on(Button.Pressed, "#edit-mortal-btn")
    def _edit_mortal_pressed(self, _: Button.Pressed) -> None:
        self._edit_mortal_flow()

    @on(Button.Pressed, "#delete-mortal-btn")
    def _delete_mortal_pressed(self, _: Button.Pressed) -> None:
        self._delete_mortal_flow()

    @work
    async def _add_mortal_flow(self) -> None:
        # Species (required).
        sp_items = entedit.species_picker_items(self._state)
        if not sp_items:
            await self.app.push_screen_wait(ErrorModal(
                "No species exist yet — create one first."
            ))
            return
        sp_id = await self.app.push_screen_wait(PickerModal(
            title="Species", items=sp_items,
        ))
        if not sp_id:
            return
        # Home location (required — SignificantLocation).
        worlds = entedit.world_picker_items(self._state, allow_none=False)
        if not worlds:
            await self.app.push_screen_wait(ErrorModal(
                "No worlds exist yet — create a SignificantLocation first."
            ))
            return
        home_id = await self.app.push_screen_wait(PickerModal(
            title="Home location (world)", items=worlds, show_back=True,
        ))
        if home_id in (None, BACK):
            return
        # Current location (defaults to home).
        same = await self.app.push_screen_wait(PickerModal(
            title="Current location same as home?",
            items=[("yes", "Yes — current = home"), ("no", "No — pick a different world")],
            show_back=True,
        ))
        if same in (None, BACK):
            return
        current_id = home_id
        if same == "no":
            current_id = await self.app.push_screen_wait(PickerModal(
                title="Current location (world)", items=worlds, show_back=True,
            ))
            if current_id in (None, BACK):
                return
        # Civilization (optional).
        civ_items = entedit.civ_picker_items(self._state)
        civ_items.insert(0, ("__none__", "(no civilization)"))
        civ_id = await self.app.push_screen_wait(PickerModal(
            title="Civilization (optional)", items=civ_items, show_back=True,
        ))
        if civ_id in (None, BACK):
            return
        civ_uuid = None if civ_id == "__none__" else UUID(civ_id)
        # Pop (optional).
        pop_items = entedit.pop_picker_items(self._state)
        pop_items.insert(0, ("__none__", "(no pop affiliation)"))
        pop_id = await self.app.push_screen_wait(PickerModal(
            title="Pop affiliation (optional)", items=pop_items, show_back=True,
        ))
        if pop_id in (None, BACK):
            return
        pop_uuid = None if pop_id == "__none__" else UUID(pop_id)
        # Role.
        role = await self.app.push_screen_wait(PickerModal(
            title="Role", items=medit.ROLE_ITEMS, show_back=True,
        ))
        if role in (None, BACK):
            return
        # Status.
        status = await self.app.push_screen_wait(PickerModal(
            title="Status", items=medit.STATUS_ITEMS, show_back=True,
        ))
        if status in (None, BACK):
            return
        # Text form.
        fields = await self.app.push_screen_wait(TextFormModal(
            title="New Mortal", fields=medit.text_fields(None), show_back=True,
        ))
        if fields in (None, BACK):
            return
        err = medit.validate_fields(fields)
        if err:
            await self.app.push_screen_wait(ErrorModal(err)); return
        from core.universe_core import MortalRole, MortalStatus
        # Auto-seed belief_tags/culture_tags from the parent civ's established
        # profile, if one is selected. Wild mortals start with empty dicts.
        seed_beliefs = seed_culture = None
        if civ_uuid is not None:
            parent_civ = self._state.civilizations.get(str(civ_uuid))
            if parent_civ is not None:
                seed_beliefs = parent_civ.established_beliefs or None
                seed_culture = parent_civ.established_culture_tags or None
        m = medit.construct_mortal(
            fields,
            species_id=UUID(sp_id),
            home_location=UUID(home_id),
            current_location=UUID(current_id),
            role=MortalRole(role),
            status=MortalStatus(status),
            civilization_id=civ_uuid,
            pop_id=pop_uuid,
            seed_beliefs=seed_beliefs, seed_culture=seed_culture,
        )
        self._state.mortals[str(m.id)] = m
        medit.link_back_refs(self._state, m)
        self.mark_dirty(); self._refresh_all()
        self.notify(f"Created mortal: {m.name}", timeout=3)

    @work
    async def _edit_mortal_flow(self) -> None:
        items = medit.mortal_picker_items(self._state)
        if not items:
            await self.app.push_screen_wait(ErrorModal("No mortals exist yet.")); return
        mid = await self.app.push_screen_wait(PickerModal(
            title="Edit which mortal?", items=items,
        ))
        if not mid:
            return
        m = self._state.mortals.get(mid)
        if m is None:
            await self.app.push_screen_wait(ErrorModal("Mortal not found.")); return
        await self._mortal_edit_loop(m)

    async def _mortal_edit_loop(self, m) -> None:
        while True:
            choice = await self.app.push_screen_wait(PickerModal(
                title=f"Edit mortal: {m.name}",
                items=[
                    ("basics",        "Basics (name, status, prominence, alignment, ages)"),
                    ("beliefs",       f"Belief tags ({len(m.belief_tags)})"),
                    ("culture",       f"Culture tags ({len(m.culture_tags)})"),
                    ("personal",      f"Personal tags ({len(m.personal_tags)})"),
                    ("status_tags",   f"Status tags ({len(m.status_tags)})"),
                    ("prom_roles",    f"Prominence roles ({len(m.prominence_roles)})"),
                    ("reassign",      "Reassign role / species / civ / pop / location"),
                    ("done",          "Done"),
                ],
            ))
            if choice in (None, "done"):
                return
            if choice == "basics":
                await self._edit_mortal_basics(m)
            elif choice == "beliefs":
                await fedit.edit_tag_weight_dict(
                    self, m.belief_tags,
                    title_prefix=f"{m.name} — Belief tags",
                    tag_namespace="domain",
                )
            elif choice == "culture":
                await fedit.edit_tag_weight_dict(
                    self, m.culture_tags,
                    title_prefix=f"{m.name} — Culture tags",
                    tag_namespace="culture",
                )
            elif choice == "personal":
                await fedit.edit_string_list(
                    self, m.personal_tags,
                    title_prefix=f"{m.name} — Personal tags",
                    tag_namespace="free",
                )
            elif choice == "status_tags":
                await fedit.edit_string_list(
                    self, m.status_tags,
                    title_prefix=f"{m.name} — Status tags",
                    tag_namespace="free",
                )
            elif choice == "prom_roles":
                from core.universe_core import MortalProminence
                await fedit.edit_enum_list(
                    self, m.prominence_roles,
                    enum_items=medit.PROMINENCE_ROLE_ITEMS,
                    enum_class=MortalProminence,
                    title_prefix=f"{m.name} — Prominence roles",
                )
            elif choice == "reassign":
                await self._mortal_reassign_submenu(m)

    async def _edit_mortal_basics(self, m) -> None:
        # Role reassignment is deferred (it rebalances appointed_by_* and
        # proxius/herald lists in non-trivial ways); the basics form re-prompts
        # status only.
        status = await self.app.push_screen_wait(PickerModal(
            title=f"Status (current: {m.status.value})",
            items=medit.STATUS_ITEMS, show_back=True,
        ))
        if status in (None, BACK):
            return
        fields = await self.app.push_screen_wait(TextFormModal(
            title=f"Edit mortal: {m.name}",
            fields=medit.text_fields(m), show_back=True,
        ))
        if fields in (None, BACK):
            return
        err = medit.validate_fields(fields)
        if err:
            await self.app.push_screen_wait(ErrorModal(err)); return
        from core.universe_core import MortalStatus
        medit.apply_fields(m, fields)
        m.status = MortalStatus(status)
        self.mark_dirty(); self._refresh_all()

    @work
    async def _delete_mortal_flow(self) -> None:
        items = medit.mortal_picker_items(self._state)
        if not items:
            await self.app.push_screen_wait(ErrorModal("No mortals to delete.")); return
        mid = await self.app.push_screen_wait(PickerModal(
            title="Delete which mortal?", items=items,
        ))
        if not mid:
            return
        await self._mortal_delete_by_id(mid)

    async def _mortal_delete_by_id(self, mid: str) -> None:
        m = self._state.mortals.get(mid)
        if m is None:
            await self.app.push_screen_wait(ErrorModal("Mortal not found.")); return
        choice = await self.app.push_screen_wait(PickerModal(
            title=f"Delete mortal {m.name}?",
            items=[("yes", "Yes, delete it."), ("no", "No, cancel.")],
            description=(
                "Back-references on civilizations, pops, locations, the "
                "Demiurge and Luminaries will be cleaned automatically."
            ),
        ))
        if choice != "yes":
            return
        medit.unlink_back_refs(self._state, m)
        self._state.mortals.pop(mid, None)
        self.mark_dirty(); self._refresh_all()
        self.notify(f"Deleted mortal: {m.name}", timeout=3)

    # ── Luminary handlers ──────────────────────────────────────────────────

    @on(Button.Pressed, "#add-luminary-btn")
    def _add_luminary_pressed(self, _: Button.Pressed) -> None:
        self._add_luminary_flow()

    @on(Button.Pressed, "#edit-luminary-btn")
    def _edit_luminary_pressed(self, _: Button.Pressed) -> None:
        self._edit_luminary_flow()

    @on(Button.Pressed, "#delete-luminary-btn")
    def _delete_luminary_pressed(self, _: Button.Pressed) -> None:
        self._delete_luminary_flow()

    @on(Button.Pressed, "#edit-pantheon-constraints-btn")
    def _edit_pantheon_constraints_pressed(self, _: Button.Pressed) -> None:
        self._edit_pantheon_constraints_flow()

    @work
    async def _add_luminary_flow(self) -> None:
        fields = await self.app.push_screen_wait(TextFormModal(
            title="New Luminary",
            description=(
                "Domain affinities and constraints are added separately via "
                "Edit Luminary after creation."
            ),
            fields=ledit.basics_fields(None, attention=0.0),
        ))
        if not fields:
            return
        err = ledit.validate_basics(fields)
        if err:
            await self.app.push_screen_wait(ErrorModal(err)); return
        lum = ledit.construct_luminary(fields, self._state.pantheon.id)
        self._state.luminaries[str(lum.id)] = lum
        ledit.link_luminary_to_pantheon(self._state, lum)
        # Starting attention is stored on SimulationState, not the Luminary.
        self._state.luminary_attention[str(lum.id)] = float(fields["attention"])
        self.mark_dirty(); self._refresh_all()
        self.notify(f"Created Luminary: {lum.name}  "
                    "(use Edit Luminary to set domains and constraints).",
                    timeout=5)

    @work
    async def _edit_luminary_flow(self) -> None:
        items = ledit.luminary_picker_items(self._state)
        if not items:
            await self.app.push_screen_wait(ErrorModal("No Luminaries exist yet.")); return
        lid = await self.app.push_screen_wait(PickerModal(
            title="Edit which Luminary?", items=items,
        ))
        if not lid:
            return
        lum = self._state.luminaries.get(lid)
        if lum is None:
            await self.app.push_screen_wait(ErrorModal("Luminary not found.")); return
        await self._luminary_edit_loop(lum)

    async def _luminary_edit_loop(self, lum) -> None:
        # Loop sub-menu until the user picks Done.
        while True:
            choice = await self.app.push_screen_wait(PickerModal(
                title=f"Edit Luminary: {lum.name}",
                items=[
                    ("basics",      "Name + disposition + attention"),
                    ("domains",     "Domain affinities"),
                    ("constraints", "Constraints imposed on the Demiurge"),
                    ("status_tags", f"Status tags ({len(lum.status_tags)})"),
                    ("done",        "Done"),
                ],
            ))
            if choice in (None, "done"):
                return
            if choice == "basics":
                await self._edit_luminary_basics(lum)
            elif choice == "domains":
                await self._edit_luminary_domains(lum)
            elif choice == "constraints":
                await self._edit_constraint_list(lum.constraints,
                    title_prefix=f"{lum.name} — Constraints")
            elif choice == "status_tags":
                await fedit.edit_string_list(
                    self, lum.status_tags,
                    title_prefix=f"{lum.name} — Status tags",
                    tag_namespace="free",
                )

    async def _edit_luminary_basics(self, lum) -> None:
        attention = self._state.luminary_attention.get(str(lum.id), 0.0)
        fields = await self.app.push_screen_wait(TextFormModal(
            title=f"Edit basics: {lum.name}",
            fields=ledit.basics_fields(lum, attention=attention),
            show_back=True,
        ))
        if fields in (None, BACK):
            return
        err = ledit.validate_basics(fields)
        if err:
            await self.app.push_screen_wait(ErrorModal(err)); return
        ledit.apply_basics(lum, fields)
        self._state.luminary_attention[str(lum.id)] = float(fields["attention"])
        self.mark_dirty(); self._refresh_all()
        self.notify(f"Updated basics for {lum.name}", timeout=3)

    async def _edit_luminary_domains(self, lum) -> None:
        while True:
            existing_count = len(lum.domains)
            lum_sum = ledit.luminary_total_affinity(lum)
            choice = await self.app.push_screen_wait(PickerModal(
                title=(
                    f"{lum.name} — Domains "
                    f"({existing_count} assigned, sum {lum_sum:.2f}/"
                    f"{ledit.MAX_LUMINARY_AFFINITY:.1f})"
                ),
                items=[
                    ("add",    "+ Add domain"),
                    ("edit",   "Edit an existing affinity"),
                    ("remove", "Remove a domain"),
                    ("done",   "Done"),
                ],
            ))
            if choice in (None, "done"):
                return
            if choice == "add":
                tag = await self.app.push_screen_wait(PickerModal(
                    title="Pick a domain to add",
                    description=(
                        "Pantheon totals show the sum across every other "
                        "Luminary on that domain — your add stacks on top."
                    ),
                    items=ledit.domain_picker_items_with_sums(self._state, lum),
                    show_back=True,
                ))
                if tag in (None, BACK):
                    continue
                fields = await self.app.push_screen_wait(TextFormModal(
                    title=f"Affinity for {tag}",
                    description=ledit.affinity_form_description(
                        self._state, lum, tag, exclude_self=True,
                    ),
                    fields=ledit.affinity_field(tag, None),
                    show_back=True,
                ))
                if fields in (None, BACK):
                    continue
                val, err = ledit.validate_affinity(fields)
                if err:
                    await self.app.push_screen_wait(ErrorModal(err)); continue
                warns = ledit.check_affinity_caps(self._state, lum, tag, val)
                if warns:
                    self.notify(
                        "Soft warning(s): " + "; ".join(warns),
                        severity="warning", timeout=8,
                    )
                lum.domains[tag] = val
                self.mark_dirty(); self._refresh_all()
            elif choice == "edit":
                if not lum.domains:
                    await self.app.push_screen_wait(ErrorModal(
                        "No domains assigned yet — add one first."
                    )); continue
                tag = await self.app.push_screen_wait(PickerModal(
                    title="Edit which domain?",
                    items=ledit.existing_domain_picker_items(lum),
                    show_back=True,
                ))
                if tag in (None, BACK):
                    continue
                current = lum.domains[tag]
                fields = await self.app.push_screen_wait(TextFormModal(
                    title=f"Affinity for {tag} (current: {current:.2f})",
                    description=ledit.affinity_form_description(
                        self._state, lum, tag, exclude_self=True,
                    ),
                    fields=ledit.affinity_field(tag, current),
                    show_back=True,
                ))
                if fields in (None, BACK):
                    continue
                val, err = ledit.validate_affinity(fields)
                if err:
                    await self.app.push_screen_wait(ErrorModal(err)); continue
                warns = ledit.check_affinity_caps(self._state, lum, tag, val)
                if warns:
                    self.notify(
                        "Soft warning(s): " + "; ".join(warns),
                        severity="warning", timeout=8,
                    )
                lum.domains[tag] = val
                self.mark_dirty(); self._refresh_all()
            elif choice == "remove":
                if not lum.domains:
                    await self.app.push_screen_wait(ErrorModal(
                        "No domains assigned yet."
                    )); continue
                tag = await self.app.push_screen_wait(PickerModal(
                    title="Remove which domain?",
                    items=ledit.existing_domain_picker_items(lum),
                    show_back=True,
                ))
                if tag in (None, BACK):
                    continue
                lum.domains.pop(tag, None)
                self.mark_dirty(); self._refresh_all()

    async def _edit_constraint_list(self, constraints, title_prefix: str) -> None:
        """Generic constraint-list editor. Used by both per-Luminary and
        pantheon-wide constraint flows. Mutates `constraints` in place."""
        while True:
            n = len(constraints)
            choice = await self.app.push_screen_wait(PickerModal(
                title=f"{title_prefix} ({n} present)",
                items=[
                    ("add",    "+ Add constraint"),
                    ("edit",   "Edit a constraint"),
                    ("remove", "Remove a constraint"),
                    ("done",   "Done"),
                ],
            ))
            if choice in (None, "done"):
                return
            if choice == "add":
                tag_pick = await self.app.push_screen_wait(PickerModal(
                    title="Domain this constraint flows from",
                    items=ledit.constraint_domain_tag_items(),
                    show_back=True,
                ))
                if tag_pick in (None, BACK):
                    continue
                dtag = None if tag_pick == "__none__" else tag_pick
                fields = await self.app.push_screen_wait(TextFormModal(
                    title="New constraint",
                    fields=ledit.constraint_fields(None),
                    show_back=True,
                ))
                if fields in (None, BACK):
                    continue
                err = ledit.validate_constraint(fields)
                if err:
                    await self.app.push_screen_wait(ErrorModal(err)); continue
                constraints.append(ledit.construct_constraint(fields, domain_tag=dtag))
                self.mark_dirty(); self._refresh_all()
            elif choice == "edit":
                if not constraints:
                    await self.app.push_screen_wait(ErrorModal(
                        "No constraints to edit."
                    )); continue
                cid = await self.app.push_screen_wait(PickerModal(
                    title="Edit which constraint?",
                    items=ledit.constraint_picker_items(constraints),
                    show_back=True,
                ))
                if cid in (None, BACK):
                    continue
                target = next(
                    (c for c in constraints if str(c.id) == cid), None,
                )
                if target is None:
                    continue
                # Default the picker selection to the existing domain_tag
                # so the user sees what's currently set.
                current_tag_label = (
                    target.domain_tag or "(no domain — general expectation)"
                )
                tag_pick = await self.app.push_screen_wait(PickerModal(
                    title=f"Domain (current: {current_tag_label})",
                    items=ledit.constraint_domain_tag_items(),
                    show_back=True,
                ))
                if tag_pick in (None, BACK):
                    continue
                dtag = None if tag_pick == "__none__" else tag_pick
                fields = await self.app.push_screen_wait(TextFormModal(
                    title=f"Edit constraint: {target.name}",
                    fields=ledit.constraint_fields(target),
                    show_back=True,
                ))
                if fields in (None, BACK):
                    continue
                err = ledit.validate_constraint(fields)
                if err:
                    await self.app.push_screen_wait(ErrorModal(err)); continue
                ledit.apply_constraint_fields(target, fields, domain_tag=dtag)
                self.mark_dirty(); self._refresh_all()
            elif choice == "remove":
                if not constraints:
                    await self.app.push_screen_wait(ErrorModal(
                        "No constraints to remove."
                    )); continue
                cid = await self.app.push_screen_wait(PickerModal(
                    title="Remove which constraint?",
                    items=ledit.constraint_picker_items(constraints),
                    show_back=True,
                ))
                if cid in (None, BACK):
                    continue
                target = next(
                    (c for c in constraints if str(c.id) == cid), None,
                )
                if target is not None:
                    constraints.remove(target)
                    self.mark_dirty(); self._refresh_all()

    @work
    async def _delete_luminary_flow(self) -> None:
        items = ledit.luminary_picker_items(self._state)
        if not items:
            await self.app.push_screen_wait(ErrorModal("No Luminaries to delete.")); return
        lid = await self.app.push_screen_wait(PickerModal(
            title="Delete which Luminary?", items=items,
        ))
        if not lid:
            return
        await self._luminary_delete_by_id(lid)

    async def _luminary_delete_by_id(self, lid: str) -> None:
        lum = self._state.luminaries.get(lid)
        if lum is None:
            await self.app.push_screen_wait(ErrorModal("Luminary not found.")); return
        notes = ledit.find_luminary_references(self._state, lid)
        warn_text = ""
        if notes:
            warn_text = (
                "\n\nNote: this Luminary has Heralds appointed. Their "
                "`appointed_by_luminary` pointers will be left dangling — "
                "consider editing those mortals first.\n  • "
                + "\n  • ".join(notes)
            )
        choice = await self.app.push_screen_wait(PickerModal(
            title=f"Delete Luminary {lum.name}?",
            items=[("yes", "Yes, delete it."), ("no", "No, cancel.")],
            description=(
                "Pantheon.luminary_ids and Demiurge.liege_luminary_ids "
                "will be scrubbed automatically." + warn_text
            ),
        ))
        if choice != "yes":
            return
        ledit.unlink_luminary_back_refs(self._state, lum)
        self._state.luminaries.pop(lid, None)
        self.mark_dirty(); self._refresh_all()
        self.notify(f"Deleted Luminary: {lum.name}", timeout=3)

    @work
    async def _edit_pantheon_constraints_flow(self) -> None:
        await self._edit_constraint_list(
            self._state.pantheon.collective_constraints,
            title_prefix=f"{self._state.pantheon.name} — Collective Constraints",
        )

    # ── Mortal reassignment helpers ────────────────────────────────────────

    async def _mortal_reassign_submenu(self, m) -> None:
        """Nested picker over the reassignable fields on a NotableMortal.
        Role gets the appointed_by_* rebalance; the others swap UUIDs with
        the appropriate back-ref scrub. When the mortal is currently a
        Herald, an extra "Reappoint to a different Luminary" option appears."""
        from core.universe_core import MortalRole
        while True:
            sp = self._state.species.get(str(m.species_id)) if m.species_id else None
            civ = self._state.civilizations.get(str(m.civilization_id)) if m.civilization_id else None
            pop = self._state.pops.get(str(m.pop_id)) if m.pop_id else None
            home = self._state.locations.get(str(m.home_location)) if m.home_location else None
            cur = self._state.locations.get(str(m.current_location)) if m.current_location else None
            items = [
                ("role",     f"Role  (current: {m.role.value})"),
            ]
            if m.role == MortalRole.HERALD:
                appointing = (
                    self._state.luminaries.get(str(m.appointed_by_luminary))
                    if m.appointed_by_luminary else None
                )
                items.append(("reappoint", f"Reappoint Herald  (current Luminary: {appointing.name if appointing else '?'})"))
            items.extend([
                ("species",  f"Species  (current: {sp.name if sp else '?'})"),
                ("civ",      f"Civilization  (current: {civ.name if civ else '(none)'})"),
                ("pop",      f"Pop affiliation  (current: {'set' if pop else '(none)'})"),
                ("home",     f"Home location  (current: {home.name if home else '?'})"),
                ("current",  f"Current location  (current: {cur.name if cur else '?'})"),
                ("back",     "← Back"),
            ])
            choice = await self.app.push_screen_wait(PickerModal(
                title=f"Reassign which? — {m.name}",
                items=items,
            ))
            if choice in (None, "back"):
                return
            if choice == "role":
                await self._reassign_mortal_role(m)
            elif choice == "reappoint":
                await self._reappoint_herald_luminary(m)
            elif choice == "species":
                await self._reassign_mortal_species(m)
            elif choice == "civ":
                await self._reassign_mortal_civ(m)
            elif choice == "pop":
                await self._reassign_mortal_pop(m)
            elif choice == "home":
                await self._reassign_mortal_home_location(m)
            elif choice == "current":
                await self._reassign_mortal_current_location(m)

    async def _reappoint_herald_luminary(self, m) -> None:
        """Move a Herald's appointment from one Luminary to another without
        flipping the role. No-op for non-Heralds."""
        from core.universe_core import MortalRole
        if m.role != MortalRole.HERALD:
            return
        items = ledit.luminary_picker_items(self._state)
        if not items:
            await self.app.push_screen_wait(ErrorModal("No Luminaries exist."))
            return
        cur_lum = (
            self._state.luminaries.get(str(m.appointed_by_luminary))
            if m.appointed_by_luminary else None
        )
        picked = await self.app.push_screen_wait(PickerModal(
            title=f"Reappoint to which Luminary? (current: {cur_lum.name if cur_lum else '?'})",
            items=items, show_back=True,
        ))
        if picked in (None, BACK):
            return
        new_lum_id = UUID(picked)
        if m.appointed_by_luminary == new_lum_id:
            return  # no change
        # Scrub old appointing Luminary's herald_ids.
        if m.appointed_by_luminary:
            old_lum = self._state.luminaries.get(str(m.appointed_by_luminary))
            if old_lum is not None:
                old_lum.herald_ids = [x for x in old_lum.herald_ids if x != m.id]
        new_lum = self._state.luminaries[picked]
        if m.id not in new_lum.herald_ids:
            new_lum.herald_ids.append(m.id)
        m.appointed_by_luminary = new_lum_id
        self.mark_dirty(); self._refresh_all()
        self.notify(f"{m.name} reappointed → {new_lum.name}", timeout=3)

    async def _reassign_mortal_role(self, m) -> None:
        """Flip a mortal's role with full back-ref rebalance.

        Leaving PROXIUS  → clear appointed_by_demiurge + scrub demiurge.proxius_ids + world.proxius_ids.
        Leaving HERALD   → clear appointed_by_luminary + scrub that luminary's herald_ids + world.herald_ids.
        Entering PROXIUS → set appointed_by_demiurge, register in demiurge.proxius_ids + world.proxius_ids.
        Entering HERALD  → pick Luminary, set appointed_by_luminary, register in luminary.herald_ids + world.herald_ids.
        """
        from core.universe_core import MortalRole
        new_role_str = await self.app.push_screen_wait(PickerModal(
            title=f"New role (current: {m.role.value})",
            items=medit.ROLE_ITEMS, show_back=True,
        ))
        if new_role_str in (None, BACK):
            return
        new_role = MortalRole(new_role_str)
        if new_role == m.role:
            return
        # If becoming a Herald, pick which Luminary appoints them.
        new_luminary_id = None
        if new_role == MortalRole.HERALD:
            lum_items = ledit.luminary_picker_items(self._state)
            if not lum_items:
                await self.app.push_screen_wait(ErrorModal(
                    "No Luminaries exist — cannot appoint a Herald."
                ))
                return
            picked = await self.app.push_screen_wait(PickerModal(
                title="Which Luminary appoints them?", items=lum_items, show_back=True,
            ))
            if picked in (None, BACK):
                return
            new_luminary_id = UUID(picked)
        # Scrub old role's back-refs.
        cur_loc = self._state.locations.get(str(m.current_location)) if m.current_location else None
        if m.role == MortalRole.PROXIUS:
            self._state.demiurge.proxius_ids = [
                x for x in self._state.demiurge.proxius_ids if x != m.id
            ]
            if isinstance(cur_loc, SignificantLocation):
                cur_loc.proxius_ids = [x for x in cur_loc.proxius_ids if x != m.id]
            m.appointed_by_demiurge = None
        elif m.role == MortalRole.HERALD:
            if m.appointed_by_luminary:
                old_lum = self._state.luminaries.get(str(m.appointed_by_luminary))
                if old_lum is not None:
                    old_lum.herald_ids = [x for x in old_lum.herald_ids if x != m.id]
            if isinstance(cur_loc, SignificantLocation):
                cur_loc.herald_ids = [x for x in cur_loc.herald_ids if x != m.id]
            m.appointed_by_luminary = None
        # Install new role's back-refs.
        m.role = new_role
        if new_role == MortalRole.PROXIUS:
            m.appointed_by_demiurge = self._state.demiurge.id
            if m.id not in self._state.demiurge.proxius_ids:
                self._state.demiurge.proxius_ids.append(m.id)
            if isinstance(cur_loc, SignificantLocation) and m.id not in cur_loc.proxius_ids:
                cur_loc.proxius_ids.append(m.id)
        elif new_role == MortalRole.HERALD:
            m.appointed_by_luminary = new_luminary_id
            new_lum = self._state.luminaries[str(new_luminary_id)]
            if m.id not in new_lum.herald_ids:
                new_lum.herald_ids.append(m.id)
            if isinstance(cur_loc, SignificantLocation) and m.id not in cur_loc.herald_ids:
                cur_loc.herald_ids.append(m.id)
        self.mark_dirty(); self._refresh_all()
        self.notify(f"{m.name} → {new_role.value}", timeout=4)

    async def _reassign_mortal_species(self, m) -> None:
        items = entedit.species_picker_items(self._state)
        if not items:
            await self.app.push_screen_wait(ErrorModal("No species exist.")); return
        sp_id = await self.app.push_screen_wait(PickerModal(
            title="New species", items=items, show_back=True,
        ))
        if sp_id in (None, BACK):
            return
        m.species_id = UUID(sp_id)
        self.mark_dirty(); self._refresh_all()
        self.notify(f"{m.name} species → {self._state.species[sp_id].name}", timeout=3)

    async def _reassign_mortal_civ(self, m) -> None:
        items = entedit.civ_picker_items(self._state)
        items.insert(0, ("__none__", "(no civilization)"))
        civ_id = await self.app.push_screen_wait(PickerModal(
            title="New civilization", items=items, show_back=True,
        ))
        if civ_id in (None, BACK):
            return
        if m.civilization_id:
            old_civ = self._state.civilizations.get(str(m.civilization_id))
            if old_civ is not None:
                old_civ.notable_mortal_ids = [x for x in old_civ.notable_mortal_ids if x != m.id]
        if civ_id == "__none__":
            m.civilization_id = None
            self.mark_dirty(); self._refresh_all()
            self.notify(f"{m.name} civilization cleared.", timeout=3)
            return
        new_civ = self._state.civilizations[civ_id]
        m.civilization_id = UUID(civ_id)
        if m.id not in new_civ.notable_mortal_ids:
            new_civ.notable_mortal_ids.append(m.id)
        self.mark_dirty(); self._refresh_all()
        self.notify(f"{m.name} civilization → {new_civ.name}", timeout=3)

    async def _reassign_mortal_pop(self, m) -> None:
        items = entedit.pop_picker_items(self._state)
        items.insert(0, ("__none__", "(no pop affiliation)"))
        pop_id = await self.app.push_screen_wait(PickerModal(
            title="New pop affiliation", items=items, show_back=True,
        ))
        if pop_id in (None, BACK):
            return
        if m.pop_id:
            old_pop = self._state.pops.get(str(m.pop_id))
            if old_pop is not None:
                old_pop.notable_mortal_ids = [x for x in old_pop.notable_mortal_ids if x != m.id]
        if pop_id == "__none__":
            m.pop_id = None
            self.mark_dirty(); self._refresh_all()
            self.notify(f"{m.name} pop cleared.", timeout=3)
            return
        new_pop = self._state.pops[pop_id]
        m.pop_id = UUID(pop_id)
        if m.id not in new_pop.notable_mortal_ids:
            new_pop.notable_mortal_ids.append(m.id)
        self.mark_dirty(); self._refresh_all()
        self.notify(f"{m.name} pop affiliation updated.", timeout=3)

    async def _reassign_mortal_home_location(self, m) -> None:
        items = entedit.world_picker_items(self._state)
        if not items:
            await self.app.push_screen_wait(ErrorModal("No worlds exist."))
            return
        loc_id = await self.app.push_screen_wait(PickerModal(
            title="New home location (world)", items=items, show_back=True,
        ))
        if loc_id in (None, BACK):
            return
        m.home_location = UUID(loc_id)
        self.mark_dirty(); self._refresh_all()
        self.notify(f"{m.name} home → {self._state.locations[loc_id].name}", timeout=3)

    async def _reassign_mortal_current_location(self, m) -> None:
        """Swap current_location and migrate proxius/herald world back-refs."""
        from core.universe_core import MortalRole
        items = entedit.world_picker_items(self._state)
        if not items:
            await self.app.push_screen_wait(ErrorModal("No worlds exist.")); return
        loc_id = await self.app.push_screen_wait(PickerModal(
            title="New current location (world)", items=items, show_back=True,
        ))
        if loc_id in (None, BACK):
            return
        old_loc = self._state.locations.get(str(m.current_location)) if m.current_location else None
        new_loc = self._state.locations[loc_id]
        # Migrate proxius/herald presence between worlds.
        if m.role == MortalRole.PROXIUS:
            if isinstance(old_loc, SignificantLocation):
                old_loc.proxius_ids = [x for x in old_loc.proxius_ids if x != m.id]
            if isinstance(new_loc, SignificantLocation) and m.id not in new_loc.proxius_ids:
                new_loc.proxius_ids.append(m.id)
        elif m.role == MortalRole.HERALD:
            if isinstance(old_loc, SignificantLocation):
                old_loc.herald_ids = [x for x in old_loc.herald_ids if x != m.id]
            if isinstance(new_loc, SignificantLocation) and m.id not in new_loc.herald_ids:
                new_loc.herald_ids.append(m.id)
        m.current_location = UUID(loc_id)
        self.mark_dirty(); self._refresh_all()
        self.notify(f"{m.name} current location → {new_loc.name}", timeout=3)
