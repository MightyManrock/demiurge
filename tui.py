#!/usr/bin/env python3
"""
tui.py
Textual TUI for the Demiurge simulation.
Run with: python tui.py
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import UUID

from rich.markup import escape as _e
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.screen import Screen, ModalScreen
from textual.widgets import (
    Button, Footer, Header, Label, ListItem, ListView,
    Input, RichLog, Static,
)
from textual.containers import Horizontal, Vertical, ScrollableContainer

from core.action_core import (
    ActionCategory, TargetType, ActionDefinition, ActionInstance, OngoingAction,
    WhisperIntent, OmenIntent, ProbabilityNudgeIntent, DevelopmentIntent,
    ProxiusDirectiveIntent, LuminaryPetitionIntent, EssenceHarvestIntent,
    SalvageIntent, SeedWorldIntent, UpliftSpeciesIntent, ExploreBeliefIntent,
    DomainVector, Framing,
)
from core.universe_core import MortalRole, MortalStatus, SignificantLocation
from logic.tick_logic import (
    SimulationState, TickLoop, TickResult,
    is_mortal_visible, ALWAYS_VISIBLE_THRESHOLD,
)
from utilities.scenario_loader import load_scenario
from utilities.scenario_exporter import export_scenario
from utilities.domain_registry import get_registry as get_domain_registry
from utilities.imago_registry import get_registry as get_imago_registry

# Reuse pure formatting functions from main.py
from main import (
    display_state, display_tick_result, display_briefing,
    _format_beliefs, _name_for_id, _get_lum_domain_context,
    SessionLog,
)

_SAVES_DIR    = Path(__file__).parent / "saves"
_SCENARIOS_DIR = Path(__file__).parent / "scenarios"
_LOGS_DIR     = Path(__file__).parent / "logs"

_STUB_ACTIONS: frozenset[str] = frozenset({
    "read_divine_traces",
    "negotiate_herald",
    "obstruct_herald",
    "petition_luminary_herald",
    "investigate_underreal",
})


# ─────────────────────────────────────────
# CSS  (dark mode)
# ─────────────────────────────────────────

_CSS = """
$bg:        #0c0c1e;
$bg-panel:  #0f1028;
$bg-feed:   #080812;
$bg-modal:  #101026;
$border:    #1e2d50;
$text:      #c0ccdc;
$muted:     #5a7090;
$accent:    #4a80b0;
$good:      #50b870;
$warn:      #b8902a;
$danger:    #b04050;
$highlight: #1a2a50;

Screen {
    background: $bg;
    color: $text;
}

Header {
    background: #0a0a1e;
    color: $muted;
    height: 1;
}

Footer {
    background: #0a0a1e;
    color: $muted;
}

/* ── Layout ─────────────────────────── */

#status-panel {
    width: 36;
    background: $bg-panel;
    border-right: solid $border;
    padding: 0 1 1 1;
    overflow-y: auto;
}

#main-feed {
    background: $bg-feed;
}

/* ── Buttons ─────────────────────────── */

Button {
    background: $highlight;
    color: $accent;
    border: none;
    margin: 0 1;
}

Button:focus {
    background: #24407a;
    color: #c0d8f0;
    border: none;
}

Button:hover {
    background: #24407a;
    color: #c0d8f0;
}

Button.-primary {
    background: #14382a;
    color: $good;
}

Button.-primary:hover {
    background: #1e5040;
    color: #70d890;
}

Button.-danger {
    background: #38101e;
    color: $danger;
}

Button.-danger:hover {
    background: #501828;
    color: #d07080;
}

/* ── Lists ─────────────────────────────── */

ListView {
    background: $bg-panel;
    border: solid $border;
}

ListItem {
    color: $text;
    padding: 0 1;
}

ListItem.--highlight {
    background: $highlight;
    color: #e0eaf8;
}

ListItem > Label {
    color: $text;
    padding: 0 0;
}

/* ── Inputs ──────────────────────────── */

Input {
    background: #07071a;
    color: #e0e8f8;
    border: solid $border;
}

Input:focus {
    border: solid #3a5a9a;
}

/* ── Labels ──────────────────────────── */

Label {
    color: $muted;
}

.field-label {
    color: $muted;
    padding: 1 0 0 0;
}

/* ── Modals ──────────────────────────── */

ModalScreen {
    align: center middle;
    background: rgba(0,0,0,0.6);
}

.modal-box {
    background: $bg-modal;
    border: solid $border;
    width: 74;
    height: auto;
    max-height: 90%;
    padding: 1 2;
}

.modal-box-tall {
    background: $bg-modal;
    border: solid $border;
    width: 74;
    height: 80%;
    padding: 1 2;
}

.modal-title {
    color: $accent;
    text-style: bold;
    padding: 0 0 1 0;
}

.modal-desc {
    color: $muted;
    padding: 0 0 1 0;
}

.btn-row {
    height: 3;
    align: right middle;
    padding: 1 0 0 0;
}

/* ── LoadScreen ───────────────────────── */

LoadScreen {
    align: center middle;
}

.load-box {
    background: $bg-panel;
    border: solid $border;
    width: 68;
    height: 70%;
    padding: 1 2;
}

.load-title {
    color: $accent;
    text-style: bold;
    text-align: center;
    padding: 1 0;
}

.load-section {
    color: $muted;
    text-style: bold;
    padding: 1 0 0 0;
}
"""


# ─────────────────────────────────────────
# HELPERS
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


def _render_status(state: SimulationState) -> Text:
    """Build a Rich Text object for the status panel."""
    lines: list[str] = []
    a = lines.append

    a(f"[bold #4a80b0]━━ STATUS ━━[/]")
    a(f"[#3a6090]{_e(state.universe.name)}[/]")
    a(f"[#2a4a6a]Age {state.universe.current_age:.1f}  ·  Tick {state.tick_number}[/]")
    a("")

    # Essence
    es = state.essence
    fp = state.demiurge.footprint
    ci = es.concealment_integrity
    ci_col = "#50b870" if ci > 0.6 else ("#c09030" if ci > 0.3 else "#b04050")
    a("[bold #4a80b0]ESSENCE[/]")
    a(f"  actual [bold]{es.actual:.2f}[/]  apparent [bold]{es.apparent:.2f}[/]")
    a(f"  concealment [{ci_col}]{ci:.2f}[/]")
    a("")

    # Footprint
    a("[bold #4a80b0]FOOTPRINT[/]")
    a(f"  overt  [#b06050]{fp.overt_miracles:.2f}[/]  "
      f"subtle [#9060a0]{fp.subtle_influence:.2f}[/]")
    a(f"  proxii [#60a070]{fp.proxius_activity:.2f}[/]  "
      f"create [#6080c0]{fp.direct_creation:.2f}[/]")
    a("")

    # Luminaries
    a("[bold #4a80b0]LUMINARIES[/]")
    for lid, lum in state.luminaries.items():
        att = state.luminary_attention.get(lid, 0.0)
        d   = lum.disposition
        rc  = "#50b870" if d.results >= 0 else "#b04050"
        mc  = "#50b870" if d.methods  >= 0 else "#b04050"
        ac  = "#c09030" if att > 0.5       else "#2a4a6a"
        a(f"  [bold #c0ccdc]{_e(lum.name)}[/] [#3a5a7a]({_e(lum.temperament.value)})[/]")
        a(f"    R[{rc}]{d.results:+.2f}[/] "
          f"M[{mc}]{d.methods:+.2f}[/] "
          f"att[{ac}]{att:.2f}[/]")
    a("")

    # Worlds
    a("[bold #4a80b0]WORLDS[/]")
    cond_colors = {
        "thriving": "#50b870",
        "stable":   "#3a6a8a",
        "stressed": "#c09030",
        "dying":    "#b04050",
        "barren":   "#604040",
    }
    for wid, world in state.worlds.items():
        cc = cond_colors.get(world.condition.value, "#707070")
        a(f"  [{cc}]●[/] [bold]{_e(world.name)}[/] [{cc}]{_e(world.condition.value)}[/]")
        for cid in world.civilization_ids:
            civ = state.civilizations.get(str(cid))
            if civ:
                h = civ.health
                a(f"    [#2a4060]└[/] [#8090a0]{_e(civ.name)}[/]")
                a(f"      [#2a4060]S{h.stability:.1f} P{h.prosperity:.1f} C{h.cohesion:.1f}[/]")
    a("")

    # Queue / ongoing
    q_count = len(state.action_queue)
    o_count = len(state.ongoing_actions)
    if q_count or o_count:
        a("[bold #4a80b0]QUEUE[/]")
        if q_count:
            a(f"  [#c09030]{q_count}[/] queued this tick")
        for cat_val, oa in state.ongoing_actions.items():
            label = cat_val.replace("_", " ").title()
            a(f"  [#2a4060]({_e(label)})[/]")
            a(f"  [#3a6a50]{_e(oa.action_key.replace('_',' '))}[/] "
              f"[#2a4060]{oa.executed_ticks}x[/]")

    return Text.from_markup("\n".join(lines))


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
                with ListView(id="load-list"):
                    if saves:
                        yield ListItem(Label("── SAVES ──", classes="load-section"), disabled=True)
                        for path in saves:
                            meta = _peek_db_meta(path)
                            tick_str = f"  [tick {meta['tick_number']}]" if meta["tick_number"] else ""
                            desc = f"  {meta['description']}" if meta["description"] else ""
                            yield ListItem(
                                Label(f"{meta['name']}{tick_str}{desc}"),
                                id=f"file-{path.stem}",
                                name=str(path),
                            )
                    if scenarios:
                        yield ListItem(Label("── SCENARIOS ──", classes="load-section"), disabled=True)
                        for path in scenarios:
                            meta = _peek_db_meta(path)
                            desc = f"  {meta['description']}" if meta["description"] else ""
                            yield ListItem(
                                Label(f"{meta['name']}{desc}"),
                                id=f"file-{path.stem}",
                                name=str(path),
                            )
                    if not saves and not scenarios:
                        yield ListItem(Label("(no saves or scenarios found)"), disabled=True)

    @on(ListView.Selected)
    def _on_selected(self, event: ListView.Selected) -> None:
        path_str = event.item.name
        if not path_str:
            return
        path = Path(path_str)
        state = load_scenario(path)
        self.app.push_screen(GameScreen(state))

    def action_quit_app(self) -> None:
        self.app.exit()


# ─────────────────────────────────────────
# PICKER MODAL
# Generic: pick one item from a list.
# Dismisses with the selected key (str) or None.
# ─────────────────────────────────────────

class PickerModal(ModalScreen):
    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(
        self,
        title: str,
        items: list[tuple[str, str]],  # (key, display_text)
        description: str = "",
    ):
        super().__init__()
        self._title       = title
        self._items       = items
        self._description = description

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box-tall"):
            yield Label(self._title, classes="modal-title")
            if self._description:
                yield Label(self._description, classes="modal-desc")
            with ScrollableContainer():
                with ListView(id="picker-list"):
                    for i, (key, text) in enumerate(self._items):
                        yield ListItem(Label(text), id=f"pick-{i}")
            with Horizontal(classes="btn-row"):
                yield Button("Cancel", id="cancel-btn", classes="-danger")

    @on(ListView.Selected, "#picker-list")
    def _on_selected(self, event: ListView.Selected) -> None:
        idx = int(event.item.id.split("-", 1)[1])
        self.dismiss(self._items[idx][0])

    @on(Button.Pressed, "#cancel-btn")
    def _on_cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


# ─────────────────────────────────────────
# YES / NO MODAL
# ─────────────────────────────────────────

class YesNoModal(ModalScreen):
    BINDINGS = [("escape", "no", "No")]

    def __init__(self, question: str, detail: str = ""):
        super().__init__()
        self._question = question
        self._detail   = detail

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box"):
            yield Label(self._question, classes="modal-title")
            if self._detail:
                yield Label(self._detail, classes="modal-desc")
            with Horizontal(classes="btn-row"):
                yield Button("Yes", id="yes-btn", classes="-primary")
                yield Button("No",  id="no-btn",  classes="-danger")

    @on(Button.Pressed, "#yes-btn")
    def _yes(self, _: Button.Pressed) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#no-btn")
    def _no(self, _: Button.Pressed) -> None:
        self.dismiss(False)

    def action_no(self) -> None:
        self.dismiss(False)


# ─────────────────────────────────────────
# TEXT FORM MODAL
# fields: list of (label, field_id, default)
# Dismisses with dict[str, str] or None.
# ─────────────────────────────────────────

class TextFormModal(ModalScreen):
    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("ctrl+enter", "confirm", "Confirm"),
    ]

    def __init__(
        self,
        title: str,
        fields: list[tuple[str, str, str]],  # (label, id, default)
        description: str = "",
    ):
        super().__init__()
        self._title       = title
        self._fields      = fields
        self._description = description

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box"):
            yield Label(self._title, classes="modal-title")
            if self._description:
                yield Label(self._description, classes="modal-desc")
            for label, fid, default in self._fields:
                yield Label(label, classes="field-label")
                yield Input(value=default, id=f"field-{fid}")
            with Horizontal(classes="btn-row"):
                yield Button("Cancel",  id="cancel-btn", classes="-danger")
                yield Button("Confirm", id="confirm-btn", classes="-primary")

    @on(Button.Pressed, "#confirm-btn")
    def _confirm(self, _: Button.Pressed) -> None:
        self.action_confirm()

    @on(Button.Pressed, "#cancel-btn")
    def _cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_confirm(self) -> None:
        result = {}
        for _label, fid, _default in self._fields:
            widget = self.query_one(f"#field-{fid}", Input)
            result[fid] = widget.value
        self.dismiss(result)

    def action_cancel(self) -> None:
        self.dismiss(None)


# ─────────────────────────────────────────
# DOMAIN / IMAGO MODAL
# Step 1: pick a domain tag (with approval ratings).
# Step 2: if imagines available for that tree, pick one (or go manual).
# Dismisses with (dvs, imago_node_id) or None to cancel.
# ─────────────────────────────────────────

class DomainImagoModal(ModalScreen):
    """Domain selection + optional Imago framing."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, state: SimulationState, explore_mode: bool = False):
        super().__init__()
        self._state        = state
        self._explore_mode = explore_mode  # True → only show unexplored domains

    def compose(self) -> ComposeResult:
        dreg = get_domain_registry()
        lum_info, fellow_tags, all_lum_canonical = _get_lum_domain_context(self._state)

        accessible = dreg.demiurge_accessible(
            all_lum_canonical,
            self._state.demiurge.unlocked_domain_tags,
        )

        if self._explore_mode:
            already_unlocked = set(self._state.demiurge.unlocked_domain_tags)
            accessible = [t for t in accessible if t not in already_unlocked]

        unlocked_set = set(self._state.demiurge.unlocked_domain_tags)
        self._accessible = accessible
        self._lum_info   = lum_info
        self._fellow_tags = fellow_tags

        title = "Explore Domain" if self._explore_mode else "Domain Selection"
        lum_header = "  ".join(f"{l.name[:8]:>8}" for l, _ in lum_info)

        with Vertical(classes="modal-box-tall"):
            yield Label(title, classes="modal-title")
            yield Label(
                f"  {'Domain':<18}  {lum_header}",
                classes="modal-desc",
            )
            with ScrollableContainer():
                with ListView(id="domain-list"):
                    for i, tag in enumerate(accessible):
                        short   = tag.split(":", 1)[1]
                        marker  = "*" if tag in unlocked_set else " "
                        approvals = []
                        for lum, lum_tags in lum_info:
                            lid = str(lum.id)
                            if not lum_tags:
                                approvals.append("       ·")
                            else:
                                v = dreg.luminary_approval(
                                    tag, lum_tags,
                                    fellow_lum_tags=fellow_tags[lid],
                                    temperament=lum.temperament.value,
                                )
                                approvals.append(f"  {v:>+7.2f}" if abs(v) >= 0.01 else "       ·")
                        row = f"{marker}{short:<18}  {''.join(approvals)}"
                        yield ListItem(Label(row), id=f"dom-{i}")
            with Horizontal(classes="btn-row"):
                yield Button("Skip Domain", id="skip-btn")
                yield Button("Cancel",      id="cancel-btn", classes="-danger")

    @on(ListView.Selected, "#domain-list")
    def _on_domain_selected(self, event: ListView.Selected) -> None:
        self._handle_domain_selected(event)

    @work
    async def _handle_domain_selected(self, event: ListView.Selected) -> None:
        idx = int(event.item.id.split("-", 1)[1])
        tag = self._accessible[idx]

        if self._explore_mode:
            from core.action_core import ExploreBeliefIntent
            self.dismiss(([DomainVector(domain_tag=tag, direction=1.0)], None))
            return

        # Check for available imagines in this tree
        tree = tag.split(":", 1)[1]
        ireg = get_imago_registry()
        available_nodes = [
            ireg.get_node(nid)
            for nid in self._state.demiurge.unlocked_imagines
            if ireg.get_node(nid) and ireg.get_node(nid).tree == tree
        ]

        if available_nodes:
            items = [(n.node_id, f"{n.name}  —  {n.tooltip_blurb}") for n in available_nodes]
            items.append(("__manual__", "No Imago — set direction manually"))
            chosen_id = await self.app.push_screen_wait(
                PickerModal("Frame with Imago?", items)
            )
            if chosen_id and chosen_id != "__manual__":
                node = ireg.get_node(chosen_id)
                dvs  = [
                    DomainVector(domain_tag=t, direction=v)
                    for t, v in node.mechanics.items()
                    if t.startswith("domain:")
                ]
                self.dismiss((dvs, chosen_id))
                return
            # fall through to manual direction

        # Manual direction via form
        form = await self.app.push_screen_wait(
            TextFormModal(
                "Domain Direction",
                [("Direction  -1.0 suppress  →  +1.0 promote", "dir", "0.5")],
            )
        )
        if form is None:
            self.dismiss(None)
            return
        try:
            direction = max(-1.0, min(1.0, float(form["dir"])))
        except ValueError:
            direction = 0.5
        self.dismiss(([DomainVector(domain_tag=tag, direction=direction)], None))

    @on(Button.Pressed, "#skip-btn")
    def _skip(self, _: Button.Pressed) -> None:
        self.dismiss(([], None))

    @on(Button.Pressed, "#cancel-btn")
    def _cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


# ─────────────────────────────────────────
# ACTION BROWSER MODAL
# Two-level: category → action.
# Dismisses with (action_key, ActionDefinition) or None.
# ─────────────────────────────────────────

class ActionBrowserModal(ModalScreen):
    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, state: SimulationState, library: dict):
        super().__init__()
        self._state   = state
        self._library = library

        # Group by category
        self._cat_actions: dict[ActionCategory, list[tuple[str, ActionDefinition]]] = {}
        for key, defn in library.items():
            self._cat_actions.setdefault(defn.category, []).append((key, defn))

        # Currently-queued categories
        key_by_id = {str(v.id): k for k, v in library.items()}
        self._queued_cats: dict[str, str] = {}
        for ai in state.action_queue:
            k = key_by_id.get(str(ai.action_definition_id))
            if k and k in library:
                d = library[k]
                self._queued_cats[d.category.value] = d.name

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box-tall"):
            yield Label("Queue Action", classes="modal-title")
            with ScrollableContainer():
                with ListView(id="cat-list"):
                    for i, (cat, _) in enumerate(self._cat_actions.items()):
                        used    = self._queued_cats.get(cat.value)
                        ongoing = self._state.ongoing_actions.get(cat.value)
                        if used:
                            note = f"  [used: {used}]"
                        elif ongoing:
                            note = f"  [ongoing: {ongoing.action_key.replace('_',' ')} ({ongoing.executed_ticks}x)]"
                        else:
                            note = ""
                        yield ListItem(
                            Label(f"{cat.value.replace('_',' ').title()}{note}"),
                            id=f"cat-{i}",
                        )
            with Horizontal(classes="btn-row"):
                yield Button("Cancel", id="cancel-btn", classes="-danger")

    @on(ListView.Selected, "#cat-list")
    def _on_cat_selected(self, event: ListView.Selected) -> None:
        self._handle_cat_selected(event)

    @work
    async def _handle_cat_selected(self, event: ListView.Selected) -> None:
        idx = int(event.item.id.split("-", 1)[1])
        cat, actions = list(self._cat_actions.items())[idx]

        # If ongoing action in this category, offer management
        ongoing = self._state.ongoing_actions.get(cat.value)
        if ongoing:
            od    = self._library.get(ongoing.action_key)
            oname = od.name if od else ongoing.action_key
            choice = await self.app.push_screen_wait(
                PickerModal(
                    f"[ONGOING] {oname}",
                    [
                        ("stop",     "Stop ongoing action"),
                        ("override", "Override this tick only"),
                        ("leave",    "Leave it running"),
                    ],
                    description=f"{ongoing.executed_ticks}x executed, {ongoing.ticks_active} ticks old",
                )
            )
            if choice == "leave" or choice is None:
                return
            if choice == "stop":
                del self._state.ongoing_actions[cat.value]

        # Show action list
        items = []
        for key, defn in actions:
            fp_total    = defn.footprint_cost.total()
            essence_str = ""
            if defn.essence_cost != 0:
                verb        = "↑" if defn.essence_cost < 0 else "↓"
                essence_str = f"  Ess{verb}{abs(defn.essence_cost):.1f}"
            persist = "  [persist]" if "can_persist" in defn.tags else ""
            stub    = "  [stub]"    if key in _STUB_ACTIONS else ""
            items.append(
                (key, f"{defn.name:<34}  FP:{fp_total:.2f}{essence_str}{persist}{stub}")
            )
        items.append(("__back__", "← Back"))

        chosen_key = await self.app.push_screen_wait(
            PickerModal(cat.value.replace("_", " ").title(), items)
        )
        if chosen_key is None or chosen_key == "__back__":
            return

        if chosen_key in _STUB_ACTIONS:
            defn = self._library[chosen_key]
            await self.app.push_screen_wait(
                YesNoModal(
                    f"{defn.name} — not yet implemented",
                    "This action requires systems that are planned but not yet built.",
                )
            )
            return

        if chosen_key in self._library:
            defn = self._library[chosen_key]
            if defn.category.value in self._queued_cats:
                existing = self._queued_cats[defn.category.value]
                await self.app.push_screen_wait(
                    YesNoModal(
                        "Category already used",
                        f"'{existing}' is already queued in this category this tick.",
                    )
                )
                return
            self.dismiss((chosen_key, defn))

    @on(Button.Pressed, "#cancel-btn")
    def _cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


# ─────────────────────────────────────────
# STATUS PANEL  (left sidebar)
# ─────────────────────────────────────────

class StatusPanel(Static):
    def refresh_state(self, state: SimulationState) -> None:
        self.update(_render_status(state))


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
        ("q",      "quit_game",       "Quit"),
    ]

    def __init__(self, state: SimulationState):
        super().__init__()
        self._state = state

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal():
            yield StatusPanel(id="status-panel")
            yield RichLog(id="main-feed", markup=True, highlight=False, wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        self._last_result = None
        _LOGS_DIR.mkdir(exist_ok=True)
        log_path = _LOGS_DIR / f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        self._log = SessionLog(log_path)
        self._refresh_status()
        self._feed_markup(f"[#2a4a6a]Logging to: {log_path}[/]")
        briefing = display_briefing(state)
        self._feed(briefing)
        self._log.write(briefing)
        state_str = display_state(state)
        self._feed(state_str)
        self._log.write(state_str)

    # ── Display helpers ───────────────────────

    def _feed(self, text: str) -> None:
        self.query_one("#main-feed", RichLog).write(text)

    def _feed_markup(self, markup: str) -> None:
        self.query_one("#main-feed", RichLog).write(Text.from_markup(markup))

    def _refresh_status(self) -> None:
        state = self._state
        self.query_one(StatusPanel).refresh_state(state)
        self.app.sub_title = (
            f"{state.universe.name}  ·  Age {state.universe.current_age:.1f}  ·  Tick {state.tick_number}"
        )

    # ── Actions (keyboard bindings) ───────────

    def action_briefing(self) -> None:
        self._feed(display_briefing(self._state))

    def action_show_state(self) -> None:
        self._feed(display_state(self._state))

    def action_queue_action(self) -> None:
        self._queue_action_flow()

    def action_manage_ongoing(self) -> None:
        self._manage_ongoing_flow()

    @work
    async def _manage_ongoing_flow(self) -> None:
        state   = self._state
        library = self.app.loop._action_library  # type: ignore[attr-defined]
        if not state.ongoing_actions:
            self._feed_markup("[#5a7090]No ongoing actions.[/]")
            return
        items = []
        for cat_val, oa in state.ongoing_actions.items():
            defn  = library.get(oa.action_key)
            name  = defn.name if defn else oa.action_key
            label = cat_val.replace("_", " ").title()
            items.append((cat_val, f"[{label}] {name}  ({oa.executed_ticks}/{oa.ticks_active})"))
        items.append(("__back__", "← Back"))
        chosen = await self.app.push_screen_wait(PickerModal("Ongoing Actions", items))
        if chosen and chosen != "__back__" and chosen in state.ongoing_actions:
            confirmed = await self.app.push_screen_wait(
                YesNoModal(f"Stop this ongoing action?")
            )
            if confirmed:
                oa   = state.ongoing_actions.pop(chosen)
                defn = library.get(oa.action_key)
                name = defn.name if defn else oa.action_key
                self._feed_markup(f"[#c09030]Stopped ongoing:[/] {name}")
                self._refresh_status()

    def action_advance_tick(self) -> None:
        self._advance_tick_work()

    @work(thread=True)
    def _advance_tick_work(self) -> None:
        state = self._state
        loop  = self.app.loop   # type: ignore[attr-defined]
        self.app.call_from_thread(self._feed_markup, "[#3a6090]Advancing time...[/]")
        new_state, result = loop.advance(state)
        self._state = new_state
        self._last_result = result
        tick_str = display_tick_result(result)
        self._log.write_tick(result)
        self.app.call_from_thread(self._feed, tick_str)
        self.app.call_from_thread(self._refresh_status)
        if result.terminal.triggered:
            self._log.finalize(new_state, result)
            self.app.call_from_thread(
                self._feed_markup,
                f"[bold #b04050]SCENARIO END: {result.terminal.condition.value.upper()}[/]\n"
                f"{result.terminal.note}",
            )

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

    def action_quit_game(self) -> None:
        self._log.finalize(self._state, self._last_result)
        self.app.exit()

    # ── Action queue flow ─────────────────────

    @work
    async def _queue_action_flow(self) -> None:
        app     = self.app
        state   = self._state
        library = app.loop._action_library  # type: ignore[attr-defined]

        # Browse and pick action
        picked = await app.push_screen_wait(ActionBrowserModal(state, library))
        if picked is None:
            return
        action_key, defn = picked

        # Build intent
        instance = await self._build_intent(action_key, defn)
        if instance is None:
            self._feed_markup("[#5a7090]Cancelled.[/]")
            return

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
                self._feed_markup(f"[#60a870][ONGOING SET][/] {defn.name}")
                self._refresh_status()
                return

        state.action_queue.append(instance)
        summary = defn.name
        if instance.target_id:
            summary += f" → {_name_for_id(instance.target_id, state)}"
        self._log.write_action(summary)
        self._feed_markup(f"[#a0d080]Queued:[/] {summary}")
        self._refresh_status()

    # ── Intent construction ───────────────────

    async def _build_intent(
        self,
        action_key: str,
        defn: ActionDefinition,
    ) -> ActionInstance | None:
        app   = self.app
        state = self._state

        target_id   = None
        target_type = defn.valid_targets[0] if defn.valid_targets else TargetType.WORLD
        proxius_id  = None
        intent      = None

        # ── issue_directive: proxius IS the target ──────
        if action_key == "issue_directive":
            already_directed = {
                str(ai.proxius_id)
                for ai in state.action_queue
                if isinstance(ai.intent, ProxiusDirectiveIntent)
                and ai.proxius_id is not None
            }
            pid = await self._pick_proxius(
                state,
                include_dormant=True,
                already_directed=already_directed,
            )
            if pid is None:
                return None
            target_id  = UUID(pid)
            proxius_id = target_id

            form = await app.push_screen_wait(
                TextFormModal(
                    "Directive",
                    [
                        ("Goal statement", "goal", "Strengthen the reformist faction"),
                        ("Latitude  0.0 strict → 1.0 open", "lat", "0.5"),
                    ],
                    description=defn.description,
                )
            )
            if form is None:
                return None
            goal = form["goal"].strip() or "Strengthen the reformist faction"
            try:
                latitude = max(0.0, min(1.0, float(form["lat"])))
            except ValueError:
                latitude = 0.5

            domain_result = await app.push_screen_wait(DomainImagoModal(state))
            dvs, imago_id = domain_result if domain_result is not None else ([], None)

            target_civ_id = None
            if dvs:
                proxius_obj = state.mortals.get(pid)
                loc_id      = str(proxius_obj.current_location) if proxius_obj else None
                civs_here   = [
                    (cid, c) for cid, c in state.civilizations.items()
                    if str(c.origin_location_id) == loc_id
                ] if loc_id else []
                if not civs_here:
                    self._feed_markup("[#5a7090](No civilizations at Proxius's location — domain vectors discarded.)[/]")
                    dvs = []
                elif len(civs_here) == 1:
                    target_civ_id = UUID(civs_here[0][0])
                else:
                    civ_items = [(cid, f"{c.name}  [{c.scale.value}]") for cid, c in civs_here]
                    civ_items.append(("__discard__", "Discard domain vectors"))
                    chosen_civ = await app.push_screen_wait(
                        PickerModal("Promote belief in which civilization?", civ_items)
                    )
                    if chosen_civ and chosen_civ != "__discard__":
                        target_civ_id = UUID(chosen_civ)
                    else:
                        dvs = []

            intent      = ProxiusDirectiveIntent(
                goal_statement=goal,
                domain_vectors=dvs,
                latitude=latitude,
                target_civilization_id=target_civ_id,
                imago_node_id=imago_id,
            )
            target_type = TargetType.MORTAL

        # ── Other proxius-targeted actions ──────────────
        elif defn.requires_proxius:
            pid = await self._pick_proxius(
                state,
                include_dormant="include_dormant_proxius" in defn.tags,
            )
            if pid is None:
                return None
            proxius_id  = UUID(pid)
            target_id   = proxius_id
            target_type = TargetType.MORTAL

        # ── Target selection by type ────────────────────
        elif TargetType.MORTAL in defn.valid_targets:
            mortals = [(mid, m) for mid, m in state.mortals.items() if is_mortal_visible(m)]
            if not mortals:
                self._feed_markup("[#5a7090]No mortals currently within perception.[/]")
                return None
            items = []
            for mid, m in mortals:
                w_obj    = state.locations.get(str(m.current_location))
                loc      = w_obj.name if w_obj else "?"
                role_str = m.role.value if m.role != MortalRole.OTHER else "mortal"
                items.append((mid, f"{m.name:<18} [{role_str}]  align:{m.alignment:.2f}  {loc}"))
            picked_id = await app.push_screen_wait(PickerModal("Select Mortal", items))
            if picked_id is None:
                return None
            target_id   = UUID(picked_id)
            target_type = TargetType.MORTAL

        elif TargetType.CIVILIZATION in defn.valid_targets:
            civs  = list(state.civilizations.items())
            items = []
            for cid, c in civs:
                w_obj = state.locations.get(str(c.origin_location_id)) if c.origin_location_id else None
                loc   = w_obj.name if w_obj else "?"
                items.append((cid, f"{c.name:<30} [{c.scale.value}]  {loc}"))
            picked_id = await app.push_screen_wait(PickerModal("Select Civilization", items))
            if picked_id is None:
                return None
            target_id   = UUID(picked_id)
            target_type = TargetType.CIVILIZATION

        elif TargetType.LUMINARY in defn.valid_targets:
            lums  = list(state.luminaries.items())
            items = [(lid, f"{l.name}  [{l.temperament.value}]") for lid, l in lums]
            picked_id = await app.push_screen_wait(PickerModal("Select Luminary", items))
            if picked_id is None:
                return None
            target_id   = UUID(picked_id)
            target_type = TargetType.LUMINARY

        elif TargetType.SPECIES in defn.valid_targets:
            species_list = list(state.species.items())
            items        = []
            for sid, sp in species_list:
                w_obj  = state.locations.get(str(sp.origin_world_id)) if sp.origin_world_id else None
                origin = w_obj.name if w_obj else "unknown"
                sap    = "sapient" if sp.sapient else "non-sapient"
                items.append((sid, f"{sp.name:<18} [{sap}]  origin: {origin}"))
            picked_id = await app.push_screen_wait(PickerModal("Select Species", items))
            if picked_id is None:
                return None
            target_id   = UUID(picked_id)
            target_type = TargetType.SPECIES

        elif TargetType.WORLD in defn.valid_targets and state.worlds:
            target_id, target_type = await self._pick_world(state)
            if target_id is None:
                return None

        elif TargetType.UNDERREAL in defn.valid_targets:
            target_type = TargetType.UNDERREAL

        # ── Intent params by action ─────────────────────
        if intent is None:
            intent = await self._build_intent_params(action_key, defn, target_id, state)
            if intent is None and action_key not in (
                "scry", "appoint_proxius", "empower_proxius",
                "dismiss_proxius", "go_quiet_proxius", "audit_proxius",
                "maintain_concealment",
            ):
                return None  # Cancelled during intent building

        return ActionInstance(
            action_definition_id=defn.id,
            target_type=target_type,
            target_id=target_id,
            timestamp=state.universe.current_age,
            demiurge_id=state.demiurge.id,
            proxius_id=proxius_id,
            intent=intent,
        )

    async def _build_intent_params(
        self,
        action_key: str,
        defn: "ActionDefinition",
        target_id,
        state: SimulationState,
    ):
        """Return the typed intent object (or None to cancel), or the sentinel None for no-intent actions."""
        app = self.app

        cat = defn.category

        # ── DIRECT CREATION ──────────────────────────────
        if cat == ActionCategory.DIRECT_CREATION:
            if action_key == "seed_world":
                form = await app.push_screen_wait(
                    TextFormModal(
                        "Seed World — New Species",
                        [
                            ("Species name",          "name",        "Life-Form Alpha"),
                            ("Lifespan min",          "lmin",        "100.0"),
                            ("Lifespan max",          "lmax",        "200.0"),
                            ("Sapient from start? y/n","sapient",    "n"),
                            ("Bio tags (comma-separated, e.g. bio:bipedal)", "tags", ""),
                        ],
                        description=defn.description,
                    )
                )
                if form is None:
                    return None
                bio_tags = [t.strip() for t in form["tags"].split(",") if t.strip()]
                return SeedWorldIntent(
                    species_name=form["name"].strip() or "Life-Form Alpha",
                    lifespan_min=float(form["lmin"] or 100.0),
                    lifespan_max=float(form["lmax"] or 200.0),
                    sapient=form["sapient"].strip().lower() == "y",
                    bio_tags=bio_tags,
                )
            elif action_key == "uplift_species":
                domain_result = await app.push_screen_wait(DomainImagoModal(state))
                if domain_result is None:
                    return None
                dvs, imago_id = domain_result
                return UpliftSpeciesIntent(
                    species_id=target_id,
                    domain_vectors=dvs,
                    imago_node_id=imago_id,
                )

        # ── SUBTLE INFLUENCE ─────────────────────────────
        elif cat == ActionCategory.SUBTLE_INFLUENCE:
            if action_key in ("whisper", "shape_dream"):
                domain_result = await app.push_screen_wait(DomainImagoModal(state))
                if domain_result is None:
                    return None
                dvs, imago_id = domain_result
                ireg = get_imago_registry()
                if imago_id:
                    concept = ireg.get_node(imago_id).name
                else:
                    form = await app.push_screen_wait(
                        TextFormModal(
                            "Whisper",
                            [("Concept to plant", "concept", "You could shape the future.")],
                        )
                    )
                    if form is None:
                        return None
                    concept = form["concept"].strip() or "You could shape the future."
                framing = await self._pick_framing()
                return WhisperIntent(
                    concept=concept,
                    domain_vectors=dvs,
                    framing=framing,
                    imago_node_id=imago_id,
                )
            elif action_key == "nudge_probability":
                form = await app.push_screen_wait(
                    TextFormModal(
                        "Nudge Probability",
                        [
                            ("Event to nudge",    "event",   "Upcoming succession conflict"),
                            ("Desired outcome",   "outcome", "The reformist faction prevails"),
                        ],
                    )
                )
                if form is None:
                    return None
                domain_result = await app.push_screen_wait(DomainImagoModal(state))
                dvs, imago_id = domain_result if domain_result is not None else ([], None)
                return ProbabilityNudgeIntent(
                    event_description=form["event"].strip() or "Upcoming succession conflict",
                    desired_outcome=form["outcome"].strip() or "The reformist faction prevails",
                    domain_vectors=dvs,
                    imago_node_id=imago_id,
                )
            elif action_key == "accelerate_development":
                form = await app.push_screen_wait(
                    TextFormModal(
                        "Accelerate Development",
                        [("Aspect to develop", "aspect", "military doctrine")],
                    )
                )
                if form is None:
                    return None
                domain_result = await app.push_screen_wait(DomainImagoModal(state))
                dvs, imago_id = domain_result if domain_result is not None else ([], None)
                return DevelopmentIntent(
                    domain_vectors=dvs,
                    target_aspect=form["aspect"].strip() or "military doctrine",
                    imago_node_id=imago_id,
                )

        # ── OVERT MIRACLE ────────────────────────────────
        elif cat == ActionCategory.OVERT_MIRACLE:
            if action_key in ("manifest_omen", "divine_manifestation"):
                form = await app.push_screen_wait(
                    TextFormModal(
                        "Manifest Omen",
                        [
                            ("Sign description",      "sign",   "A celestial anomaly appears"),
                            ("Intended interpretation","interp", "The gods demand action"),
                        ],
                    )
                )
                if form is None:
                    return None
                domain_result = await app.push_screen_wait(DomainImagoModal(state))
                dvs, imago_id = domain_result if domain_result is not None else ([], None)
                framing       = await self._pick_framing()
                civ_scope = None
                if target_id:
                    tid_str = str(target_id)
                    if tid_str in state.civilizations:
                        civ_scope = target_id
                    elif tid_str in state.mortals:
                        civ_scope = state.mortals[tid_str].civilization_id
                return OmenIntent(
                    sign_description=form["sign"].strip() or "A celestial anomaly appears",
                    intended_interpretation=form["interp"].strip() or "The gods demand action",
                    domain_vectors=dvs,
                    framing=framing,
                    civilization_scope=civ_scope,
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
                    )
                )
                if form is None:
                    return None
                try:
                    conc = max(0.0, min(1.0, float(form["conc"] or 0.7)))
                except ValueError:
                    conc = 0.7
                return EssenceHarvestIntent(
                    target_concept_type=form["concept"].strip() or None,
                    concealment_priority=conc,
                )
            elif action_key == "salvage_concept":
                form = await app.push_screen_wait(
                    TextFormModal(
                        "Salvage Concept",
                        [("What are you hoping to find?", "desired", "")],
                    )
                )
                if form is None:
                    return None
                world_id, _ = await self._pick_world(state)
                if world_id is None:
                    return None
                domain_result = await app.push_screen_wait(DomainImagoModal(state))
                dvs, imago_id = domain_result if domain_result is not None else ([], None)
                return SalvageIntent(
                    desired_concept=form["desired"].strip(),
                    target_world_id=world_id,
                    domain_vectors=dvs,
                    imago_node_id=imago_id,
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
                )
            )
            if form is None:
                return None
            return LuminaryPetitionIntent(
                subject=form["subject"].strip()   or "Current universe state",
                your_position=form["position"].strip() or "Continued patience",
                tone=form["tone"].strip() or "deferential",
            )

        # ── SELF REFINEMENT ──────────────────────────────
        elif cat == ActionCategory.SELF_REFINEMENT:
            if action_key == "explore_beliefs":
                domain_result = await app.push_screen_wait(
                    DomainImagoModal(state, explore_mode=True)
                )
                if domain_result is None:
                    return None
                dvs, _ = domain_result
                if not dvs:
                    return None
                tag = dvs[0].domain_tag
                return ExploreBeliefIntent(domain_tag=tag)

        # No intent needed (scry, appoint_proxius, audit_proxius,
        # maintain_concealment, empower_proxius, etc.)
        return None

    # ── Sub-pickers ───────────────────────────

    async def _pick_proxius(
        self,
        state: SimulationState,
        include_dormant: bool = False,
        already_directed: set | None = None,
    ) -> str | None:
        already_directed = already_directed or set()
        proxii = [
            (mid, m) for mid, m in state.mortals.items()
            if m.role == MortalRole.PROXIUS
            and mid not in already_directed
            and (m.status == MortalStatus.ACTIVE
                 or (include_dormant and m.status == MortalStatus.DORMANT))
        ]
        if not proxii:
            self._feed_markup("[#5a7090]No Proxii available.[/]")
            return None
        items = []
        for mid, m in proxii:
            w_obj    = state.locations.get(str(m.current_location))
            loc      = w_obj.name if w_obj else "?"
            dorm_note = "  [DORMANT]" if m.status == MortalStatus.DORMANT else ""
            items.append((mid, f"{m.name:<18}  align:{m.alignment:.2f}  {loc}{dorm_note}"))
        return await self.app.push_screen_wait(PickerModal("Select Proxius", items))

    async def _pick_world(
        self,
        state: SimulationState,
    ) -> tuple[UUID | None, TargetType]:
        worlds = list(state.worlds.items())
        if not worlds:
            self._feed_markup("[#5a7090]No worlds available.[/]")
            return None, TargetType.WORLD
        items = []
        for wid, w in worlds:
            sys_obj  = state.locations.get(str(w.parent_id)) if w.parent_id else None
            sys_name = sys_obj.name if sys_obj else "?"
            n_civs   = len(w.civilization_ids)
            life_str = f"{n_civs} civilization(s)" if n_civs else "no life"
            items.append((wid, f"{w.name:<16} [{w.condition.value}]  {sys_name:<20}  {life_str}"))
        picked = await self.app.push_screen_wait(PickerModal("Select World", items))
        if picked is None:
            return None, TargetType.WORLD
        return UUID(picked), TargetType.WORLD

    async def _pick_framing(self) -> Framing:
        items = [(f.value, f.value.title()) for f in Framing]
        picked = await self.app.push_screen_wait(PickerModal("Framing", items))
        if picked is None or picked not in {f.value for f in Framing}:
            return Framing.INSPIRATIONAL
        return Framing(picked)


# ─────────────────────────────────────────
# APP
# ─────────────────────────────────────────

class DemiurgeApp(App):
    CSS   = _CSS
    TITLE = "DEMIURGE"

    loop: TickLoop

    def __init__(self):
        super().__init__()
        self.loop = TickLoop()

    def on_mount(self) -> None:
        self.push_screen(LoadScreen())


if __name__ == "__main__":
    DemiurgeApp().run()
