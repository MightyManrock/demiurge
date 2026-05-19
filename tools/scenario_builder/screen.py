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
from uuid import UUID

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, TabbedContent, TabPane

from logic.tick_logic import SimulationState
from ui.constants import _SCENARIOS_DIR
from ui.detail_tabs import DetailTabManager
from ui.display import _pop_stratum_label
from ui.constants import BACK
from ui.modals import QuitConfirmModal, ErrorModal, PickerModal, TextFormModal
from ui.widgets import (
    DivineWisdomTab, LocationsTab, LuminariesTab, UniverseTab,
    set_unseen_predicate,
)
from utilities.scenario_exporter import export_scenario

from .briefing_editor import BriefingEditorTab
from .naming import validate_initialism, validate_scenario_name
from .scenario_tab import ScenarioTab
from . import location_editor as locedit
from . import entity_editor as entedit
from . import mortal_editor as medit
from . import luminary_editor as ledit


class BuilderScreen(Screen):
    """Builder-mode workspace. Read-only browsing + save/save-as in Phase 1."""

    BINDINGS = [
        ("ctrl+s",       "save",         "Save"),
        ("ctrl+shift+s", "save_as",      "Save As"),
        ("q",            "quit_confirm", "Quit"),
        ("ctrl+q",       "quit_force",   "Force quit"),
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
        kind = locedit.location_kind(loc)

        # System star_type / world condition pickers go first when present,
        # so users can hit Cancel without committing other edits.
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
        self.notify(f"Updated {kind}: {loc.name}", timeout=3)

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
        loc = self._state.locations.get(target_id)
        if loc is None:
            await self.app.push_screen_wait(ErrorModal("Location not found."))
            return

        # Reference check — refuse if anything points at this location.
        blocks = locedit.find_blocking_references(self._state, target_id)
        if blocks:
            preview = "\n  • ".join(blocks[:8])
            extra = f"\n  …and {len(blocks) - 8} more" if len(blocks) > 8 else ""
            await self.app.push_screen_wait(ErrorModal(
                f"Cannot delete {loc.name}: {len(blocks)} reference(s) "
                f"point at it. Clear them first.\n\n  • {preview}{extra}"
            ))
            return

        # Confirm deletion.
        choice = await self.app.push_screen_wait(PickerModal(
            title=f"Delete {loc.name}?",
            items=[("yes", "Yes, delete it."), ("no", "No, cancel.")],
            description="This cannot be undone within the current session.",
        ))
        if choice != "yes":
            return

        locedit.remove_from_parent(self._state, loc)
        self._state.locations.pop(target_id, None)
        self.mark_dirty()
        self._refresh_all()
        self.notify(f"Deleted: {loc.name}", timeout=3)

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
        # Re-prompt for condition (sapience stays — toggling it would invalidate
        # any Pops using social_class vs wild_stratum).
        cond = await self.app.push_screen_wait(PickerModal(
            title=f"Condition (current: {sp.condition.value})",
            items=entedit.SPECIES_CONDITION_ITEMS, show_back=True,
        ))
        if cond in (None, BACK):
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
        self.mark_dirty(); self._refresh_all()
        self.notify(f"Updated species: {sp.name}", timeout=3)

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
        sp = self._state.species.get(sid)
        if sp is None:
            await self.app.push_screen_wait(ErrorModal("Species not found.")); return
        blocks = entedit.find_species_references(self._state, sid)
        if blocks:
            preview = "\n  • ".join(blocks[:8])
            extra = f"\n  …and {len(blocks) - 8} more" if len(blocks) > 8 else ""
            await self.app.push_screen_wait(ErrorModal(
                f"Cannot delete {sp.name}: {len(blocks)} reference(s) point at it.\n\n  • {preview}{extra}"
            ))
            return
        choice = await self.app.push_screen_wait(PickerModal(
            title=f"Delete species {sp.name}?",
            items=[("yes", "Yes, delete it."), ("no", "No, cancel.")],
        ))
        if choice != "yes":
            return
        entedit.unlink_species_back_refs(self._state, sp)
        self._state.species.pop(sid, None)
        self.mark_dirty(); self._refresh_all()
        self.notify(f"Deleted species: {sp.name}", timeout=3)

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
        # Re-prompt for scale.
        scale = await self.app.push_screen_wait(PickerModal(
            title=f"Scale (current: {civ.scale.value})",
            items=entedit.CIV_SCALE_ITEMS, show_back=True,
        ))
        if scale in (None, BACK):
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
        self.mark_dirty(); self._refresh_all()
        self.notify(f"Updated civilization: {civ.name}", timeout=3)

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
        civ = self._state.civilizations.get(cid)
        if civ is None:
            await self.app.push_screen_wait(ErrorModal("Civilization not found.")); return
        blocks = entedit.find_civ_references(self._state, cid)
        if blocks:
            preview = "\n  • ".join(blocks[:8])
            extra = f"\n  …and {len(blocks) - 8} more" if len(blocks) > 8 else ""
            await self.app.push_screen_wait(ErrorModal(
                f"Cannot delete {civ.name}: {len(blocks)} reference(s) point at it.\n\n  • {preview}{extra}"
            ))
            return
        choice = await self.app.push_screen_wait(PickerModal(
            title=f"Delete civilization {civ.name}?",
            items=[("yes", "Yes, delete it."), ("no", "No, cancel.")],
        ))
        if choice != "yes":
            return
        entedit.unlink_civ_back_refs(self._state, civ)
        self._state.civilizations.pop(cid, None)
        self.mark_dirty(); self._refresh_all()
        self.notify(f"Deleted civilization: {civ.name}", timeout=3)

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
        pop = entedit.construct_pop(
            fields, civ_uuid, UUID(sp_id), UUID(loc_id),
            social_class, wild_stratum,
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
        # Phase 4 keeps pop edits narrow: just size_fractional. Reassigning
        # species / civ / location is more invasive (back-ref bookkeeping)
        # and is deferred. Stratum reassignment is similarly deferred.
        fields = await self.app.push_screen_wait(TextFormModal(
            title="Edit pop size",
            fields=entedit.pop_text_fields(pop), show_back=True,
        ))
        if fields in (None, BACK):
            return
        err = entedit.validate_pop_fields(fields)
        if err:
            await self.app.push_screen_wait(ErrorModal(err)); return
        entedit.apply_pop_fields(pop, fields)
        self.mark_dirty(); self._refresh_all()
        self.notify("Updated pop.", timeout=3)

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
        pop = self._state.pops.get(pid)
        if pop is None:
            await self.app.push_screen_wait(ErrorModal("Pop not found.")); return
        blocks = entedit.find_pop_references(self._state, pid)
        if blocks:
            preview = "\n  • ".join(blocks[:8])
            extra = f"\n  …and {len(blocks) - 8} more" if len(blocks) > 8 else ""
            await self.app.push_screen_wait(ErrorModal(
                f"Cannot delete pop: {len(blocks)} reference(s) point at it.\n\n  • {preview}{extra}"
            ))
            return
        choice = await self.app.push_screen_wait(PickerModal(
            title="Delete this pop?",
            items=[("yes", "Yes, delete it."), ("no", "No, cancel.")],
        ))
        if choice != "yes":
            return
        entedit.unlink_pop_back_refs(self._state, pop)
        self._state.pops.pop(pid, None)
        self.mark_dirty(); self._refresh_all()
        self.notify("Deleted pop.", timeout=3)

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
        m = medit.construct_mortal(
            fields,
            species_id=UUID(sp_id),
            home_location=UUID(home_id),
            current_location=UUID(current_id),
            role=MortalRole(role),
            status=MortalStatus(status),
            civilization_id=civ_uuid,
            pop_id=pop_uuid,
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
        # Re-prompt status (role changes are too tangled for Phase 5 — they
        # need to clean up appointed_by_* refs and the proxius/herald lists).
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
        self.notify(f"Updated mortal: {m.name}", timeout=3)

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
        # Loop sub-menu until the user picks Done.
        while True:
            choice = await self.app.push_screen_wait(PickerModal(
                title=f"Edit Luminary: {lum.name}",
                items=[
                    ("basics",      "Name + disposition + attention"),
                    ("domains",     "Domain affinities"),
                    ("constraints", "Constraints imposed on the Demiurge"),
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
            choice = await self.app.push_screen_wait(PickerModal(
                title=f"{lum.name} — Domains ({existing_count} assigned)",
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
                    items=ledit.domain_tag_picker_items(exclude=set(lum.domains.keys())),
                    show_back=True,
                ))
                if tag in (None, BACK):
                    continue
                fields = await self.app.push_screen_wait(TextFormModal(
                    title=f"Affinity for {tag}",
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
                constraints.append(ledit.construct_constraint(fields))
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
                ledit.apply_constraint_fields(target, fields)
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
