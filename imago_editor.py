#!/usr/bin/env python3
"""
imago_editor.py
Standalone Textual TUI for editing Imago node mechanics and text fields.
Run with: python imago_editor.py
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.markup import escape as _e
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import (
    Button, DataTable, Footer, Header, Input, Label,
    ListItem, ListView, Static, TabbedContent, TabPane, TextArea,
)
from textual.containers import Grid, Horizontal, ScrollableContainer, Vertical, VerticalScroll

from utilities.imago_registry import ImagoNode, get_registry as get_imago_registry
from utilities.domain_registry import DOMAIN_TAGS
from utilities.culture_registry import (
    ALL_CULTURE_TAGS,
    RELIGION_TAGS, TECHNO_TAGS, STRUCTURE_TAGS,
    PRACTICE_TAGS, RELATIONS_TAGS, VALUES_TAGS,
)

_DB_PATH = Path(__file__).parent / "core" / "core.db"

# (cat_id, label, tag_list) — drives the Status tab culture sections
_STAT_CATEGORIES: list[tuple[str, str, list[str]]] = [
    ("religion",   "Religion",           RELIGION_TAGS),
    ("techno",     "Technology",         TECHNO_TAGS),
    ("structure",  "Structure",          STRUCTURE_TAGS),
    ("practices",  "Societal Practices", PRACTICE_TAGS),
    ("relations",  "Relations",          RELATIONS_TAGS),
    ("values",     "Values & Virtues",   VALUES_TAGS),
]

# Groups shown under the "Other" section in AddMechanicModal
_OTHER_GROUPS: list[tuple[str, list[str]]] = [
    ("Technology", TECHNO_TAGS),
    ("Structure",  STRUCTURE_TAGS),
    ("Relations",  RELATIONS_TAGS),
]

# rows: 1 = single Input, >1 = TextArea that height, -1 = TextArea in full tall modal
_TEXT_FIELDS: list[tuple[str, str, int]] = [
    ("name",          "Name",        1),
    ("tooltip_blurb", "Tooltip",     5),
    ("description",   "Description", -1),
]

# ─────────────────────────────────────────
# CSS
# ─────────────────────────────────────────

_CSS = """
$bg:       #0c0c1e;
$bg-panel: #0f1028;
$bg-modal: #101026;
$border:   #1e2d50;
$text:     #c0ccdc;
$muted:    #5a7090;
$accent:   #4a80b0;
$good:     #50b870;
$danger:   #b04050;
$highlight:#1a2a50;

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

/* ── Layout ──────────────────────────── */

#app-body {
    height: 1fr;
}

#domain-sidebar {
    width: 22;
    background: $bg-panel;
    border-right: solid $border;
    padding: 0 1;
}

#sidebar-title {
    color: $accent;
    text-style: bold;
    padding: 1 0;
}

#tree-list {
    height: 1fr;
}

#main-panel {
    width: 1fr;
}

/* ── Status tab ──────────────────────── */

#status-scroll {
    height: 1fr;
    padding: 0 1;
}

.section-header {
    color: $accent;
    text-style: bold;
    padding: 1 0 0 0;
}

.missing-label {
    color: $muted;
    padding: 0 0 1 0;
}

/* ── Node editor ─────────────────────── */

#node-content-area {
    height: 1fr;
    padding: 0 1 1 1;
}

#no-node-msg {
    color: $muted;
    padding: 2 0;
}

#node-header {
    color: $accent;
    text-style: bold;
    padding: 1 0;
}

.field-row {
    height: 3;
    margin: 0 0 1 0;
}

.field-row-tall {
    height: 4;
    margin: 0 0 1 0;
}

.field-label-left {
    width: 14;
    color: $muted;
    content-align: left middle;
}

.field-display {
    width: 1fr;
    color: $text;
    border: solid $border;
    padding: 0 1;
    content-align: left middle;
    overflow-x: hidden;
}

.edit-btn {
    width: 8;
    margin: 0 0 0 1;
}

.mechanic-section-label {
    color: $accent;
    text-style: bold;
    padding: 1 0 0 0;
}

#mechanics-scroll {
    height: auto;
    max-height: 20;
    border: solid $border;
    margin: 0 0 1 0;
}

/* ── Mechanic rows ───────────────────── */

MechanicRow {
    height: 3;
}

.mechanic-tag {
    width: 24;
    color: $text;
    content-align: left middle;
    padding: 0 1;
}

.mechanic-input {
    width: 12;
}

.delete-btn {
    width: 5;
    margin: 0 0 0 1;
}

/* ── Buttons ─────────────────────────── */

Button {
    background: $highlight;
    color: $accent;
    border: none;
    margin: 0 1;
}
Button:focus { background: #24407a; color: #c0d8f0; border: none; }
Button:hover { background: #24407a; color: #c0d8f0; }
Button.-primary { background: #14382a; color: $good; }
Button.-primary:hover { background: #1e5040; color: #70d890; }
Button.-danger { background: #38101e; color: $danger; }
Button.-danger:hover { background: #501828; color: #d07080; }

/* ── Lists ───────────────────────────── */

ListView {
    background: $bg-panel;
    border: solid $border;
}
ListItem { color: $text; padding: 0 1; }
ListItem.--highlight { background: $highlight; color: #e0eaf8; }
ListItem > Label { color: $text; }

/* ── Inputs ──────────────────────────── */

Input {
    background: #07071a;
    color: #e0e8f8;
    border: solid $border;
}
Input:focus { border: solid #3a5a9a; }

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
.modal-title { color: $accent; text-style: bold; padding: 0 0 1 0; }
.modal-desc  { color: $muted; padding: 0 0 1 0; }
.btn-row { height: 3; align: right middle; padding: 1 0 0 0; }
.field-label { color: $muted; padding: 1 0 0 0; }

/* ── Add mechanic modal ──────────────── */

#type-btn-row {
    height: 3;
    margin: 0 0 1 0;
}
#type-btn-row-2 {
    height: 3;
    margin: 0 0 1 0;
}
#add-tag-list { height: 12; }
#add-value-label { padding: 0 0 0 0; }
.sep-item { color: $muted; }

/* ── Imago pyramid picker ────────────── */

#imago-grid {
    grid-size: 3;
    height: auto;
    margin: 1 0;
}
ImagoEditorCell {
    border: round $border;
    height: 4;
    content-align: center middle;
    text-align: center;
    padding: 0 1;
    color: $text;
}
ImagoEditorCell:focus { border: round $accent; }
.imago-spacer { height: 4; }
#imago-tooltip {
    height: 5;
    background: $bg-panel;
    border: solid $border;
    padding: 0 1;
    margin: 0 0 1 0;
    content-align: left middle;
}
"""


# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────

def _node_to_dict(node: ImagoNode) -> dict:
    return {
        "node_id":      node.node_id,
        "tree":         node.tree,
        "tier":         node.tier,
        "name":         node.name,
        "tooltip_blurb": node.tooltip_blurb,
        "description":  node.description,
        "mechanics":    dict(node.mechanics),
        "min_prereqs":  node.min_prereqs,
        "sort_order":   node.sort_order,
    }


def _compute_category_stats(nodes: dict[str, dict], tag_list: list[str]) -> tuple[list[tuple], list[str]]:
    """Returns (rows, missing_tags) for the given tag list. Rows sorted by total descending."""
    tag_set = set(tag_list)
    counts: dict[str, int]   = defaultdict(int)
    totals: dict[str, float] = defaultdict(float)

    for node in nodes.values():
        for tag, val in node["mechanics"].items():
            if tag in tag_set:
                counts[tag] += 1
                totals[tag] += val

    rows = []
    for tag in sorted(counts, key=lambda t: -totals[t]):
        short = tag.split(":", 1)[1]
        rows.append((short, str(counts[tag]), f"{totals[tag]:+.2f}", f"{totals[tag] / 16:+.2f}"))

    present = set(counts.keys())
    missing = sorted(t.split(":", 1)[1] for t in tag_list if t not in present)
    return rows, missing


def _compute_domain_rider_stats(nodes: dict[str, dict]) -> list[tuple]:
    """Domain tag appearances in mechanics, sorted by (pos+neg) total descending."""
    counts:    dict[str, int]   = defaultdict(int)
    pos_tots:  dict[str, float] = defaultdict(float)
    neg_tots:  dict[str, float] = defaultdict(float)

    for node in nodes.values():
        for tag, val in node["mechanics"].items():
            if tag.startswith("domain:"):
                counts[tag] += 1
                if val >= 0:
                    pos_tots[tag] += val
                else:
                    neg_tots[tag] += val

    rows = []
    for tag in sorted(counts, key=lambda t: -(pos_tots[t] + abs(neg_tots[t]))):
        short = tag.split(":", 1)[1]
        net   = pos_tots[tag] + neg_tots[tag]
        rows.append((
            short, str(counts[tag]),
            f"{pos_tots[tag]:+.2f}", f"{neg_tots[tag]:+.2f}", f"{net / 16:+.2f}",
        ))
    return rows


# ─────────────────────────────────────────
# IMAGO TREE PICKER (editor-only, no game state)
# ─────────────────────────────────────────

class ImagoEditorCell(Widget):
    """One cell in the editor's Imago tree pyramid."""

    can_focus = True

    class Focused(Message):
        def __init__(self, node_id: str) -> None:
            super().__init__()
            self.node_id = node_id

    class Selected(Message):
        def __init__(self, node_id: str) -> None:
            super().__init__()
            self.node_id = node_id

    def __init__(self, node: dict) -> None:
        super().__init__()
        self._node = node

    def render(self) -> Text:
        return Text(self._node["name"], justify="center")

    def on_focus(self)  -> None: self.post_message(self.Focused(self._node["node_id"]))
    def on_enter(self)  -> None: self.post_message(self.Focused(self._node["node_id"]))
    def on_click(self)  -> None: self.post_message(self.Selected(self._node["node_id"]))
    def key_enter(self) -> None: self.post_message(self.Selected(self._node["node_id"]))


class ImagoPickerModal(ModalScreen):
    """
    Tree-layout Imago picker for the editor (no game state).
    All 7 nodes are selectable. Dismisses with node_id or None.
    """

    BINDINGS = [
        ("escape", "cancel",       "Cancel"),
        ("up",     "nav('up')",    ""),
        ("down",   "nav('down')",  ""),
        ("left",   "nav('left')",  ""),
        ("right",  "nav('right')", ""),
    ]

    # (grid_row, grid_col) for each of the 7 cells in DOM order
    _POSITIONS = [(0, 1), (1, 0), (1, 2), (2, 0), (2, 2), (3, 0), (3, 2)]

    def __init__(self, tree: str, nodes: list[dict]) -> None:
        super().__init__()
        self._tree = tree
        self._node_by_id: dict[str, dict] = {n["node_id"]: n for n in nodes}
        by_tier: dict[int, list[dict]] = {1: [], 2: [], 3: [], 4: []}
        for n in nodes:
            by_tier[n["tier"]].append(n)
        self._by_tier = by_tier

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box"):
            yield Label(f"{self._tree.title()} — Imāginēs", classes="modal-title")
            with Grid(id="imago-grid"):
                for tier in (4, 3, 2, 1):
                    tier_nodes = self._by_tier.get(tier, [])
                    if tier == 4:
                        yield Static("", classes="imago-spacer")
                        if tier_nodes:
                            yield ImagoEditorCell(tier_nodes[0])
                        else:
                            yield Static("", classes="imago-spacer")
                        yield Static("", classes="imago-spacer")
                    else:
                        left  = tier_nodes[0] if len(tier_nodes) > 0 else None
                        right = tier_nodes[1] if len(tier_nodes) > 1 else None
                        for node in (left, right):
                            if node:
                                cell = ImagoEditorCell(node)
                                yield cell
                            else:
                                yield Static("", classes="imago-spacer")
                            if node is left:
                                yield Static("", classes="imago-spacer")
            yield Static("", id="imago-tooltip")
            with Horizontal(classes="btn-row"):
                yield Button("Cancel", id="cancel-btn", classes="-danger")

    def on_mount(self) -> None:
        cells = list(self.query(ImagoEditorCell))
        if cells:
            cells[0].focus()

    def action_nav(self, direction: str) -> None:
        cells   = list(self.query(ImagoEditorCell))
        pos_map = {p: i for i, p in enumerate(self._POSITIONS)}
        focused = next((i for i, c in enumerate(cells) if c.has_focus), -1)
        if focused == -1:
            if cells:
                cells[0].focus()
            return
        row, col = self._POSITIONS[focused]
        new_pos: Optional[tuple[int, int]] = None
        if direction == "up"    and row > 0: new_pos = (row - 1, 1 if row - 1 == 0 else col)
        elif direction == "down" and row < 3: new_pos = (row + 1, 0 if col == 1 else col)
        elif direction == "left" and col == 2: new_pos = (row, 0)
        elif direction == "right" and col == 0: new_pos = (row, 2)
        if new_pos and new_pos in pos_map:
            cells[pos_map[new_pos]].focus()

    def on_imago_editor_cell_focused(self, event: ImagoEditorCell.Focused) -> None:
        node = self._node_by_id.get(event.node_id)
        tip  = node["tooltip_blurb"] if node else ""
        if node and node["tier"] == 4:
            tip = "Tier 4 apex."
        self.query_one("#imago-tooltip", Static).update(tip)

    def on_imago_editor_cell_selected(self, event: ImagoEditorCell.Selected) -> None:
        self.dismiss(event.node_id)

    @on(Button.Pressed, "#cancel-btn")
    def _cancel_btn(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


# ─────────────────────────────────────────
# EDIT TEXT MODAL
# ─────────────────────────────────────────

class EditTextModal(ModalScreen):
    """Pre-populated single-field editor. Dismisses with new str or None."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, field_label: str, current_value: str, rows: int = 1) -> None:
        super().__init__()
        self._label = field_label
        self._value = current_value
        self._rows  = rows  # 1=Input, >1=TextArea that height, -1=TextArea+tall modal

    def compose(self) -> ComposeResult:
        box_class = "modal-box-tall" if self._rows == -1 else "modal-box"
        with Vertical(classes=box_class):
            yield Label(f"Edit: {self._label}", classes="modal-title")
            if self._rows == 1:
                yield Input(self._value, id="edit-input")
            else:
                yield TextArea(self._value, id="edit-area")
            with Horizontal(classes="btn-row"):
                yield Button("Cancel",  id="cancel-btn",  classes="-danger")
                yield Button("Confirm", id="confirm-btn", classes="-primary")

    def on_mount(self) -> None:
        if self._rows == 1:
            inp = self.query_one("#edit-input", Input)
            inp.focus()
            inp.cursor_position = len(inp.value)
        else:
            area = self.query_one("#edit-area", TextArea)
            if self._rows > 1:
                area.styles.height = self._rows
            area.focus()

    @on(Button.Pressed, "#confirm-btn")
    def _confirm(self, _: Button.Pressed) -> None:
        if self._rows == 1:
            value = self.query_one("#edit-input", Input).value
        else:
            value = self.query_one("#edit-area", TextArea).text
        self.dismiss(value)

    @on(Button.Pressed, "#cancel-btn")
    def _cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


# ─────────────────────────────────────────
# ADD MECHANIC MODAL
# ─────────────────────────────────────────

class AddMechanicModal(ModalScreen):
    """Pick a tag and a float value. Dismisses with (tag, float) or None.

    Sections: Domain Expression | Religion | Societal Practices | Values & Virtues | Other
    "Other" covers Technology, Structure, and Relations tags grouped with dim separators.
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    _SECTION_IDS = ("domain", "religion", "practices", "values", "other")

    def __init__(self, existing_tags: set[str]) -> None:
        super().__init__()
        self._existing  = existing_tags
        self._tag_type  = "domain"
        self._cur_tags: list[str] = []
        self._sel_tag: Optional[str] = None

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box-tall"):
            yield Label("Add Mechanic", classes="modal-title")
            with Horizontal(id="type-btn-row"):
                yield Button("Domain",   id="type-domain-btn",    classes="-primary")
                yield Button("Religion", id="type-religion-btn")
            with Horizontal(id="type-btn-row-2"):
                yield Button("Practices", id="type-practices-btn")
                yield Button("Values",    id="type-values-btn")
                yield Button("Other",     id="type-other-btn")
            with ScrollableContainer():
                yield ListView(id="add-tag-list")
            yield Label("Value:", id="add-value-label", classes="field-label")
            yield Input("0.10", id="add-value-input")
            with Horizontal(classes="btn-row"):
                yield Button("Cancel", id="cancel-btn", classes="-danger")
                yield Button("Add",    id="add-btn",    classes="-primary")

    async def on_mount(self) -> None:
        await self._reload_list()

    async def _set_section(self, section: str) -> None:
        self._tag_type = section
        for sid in self._SECTION_IDS:
            btn = self.query_one(f"#type-{sid}-btn", Button)
            if sid == section:
                btn.add_class("-primary")
            else:
                btn.remove_class("-primary")
        await self._reload_list()

    async def _reload_list(self) -> None:
        lv = self.query_one("#add-tag-list", ListView)
        await lv.clear()
        self._cur_tags = []
        self._sel_tag = None

        if self._tag_type == "domain":
            tags = [t for t in DOMAIN_TAGS if t not in self._existing]
            self._cur_tags = tags
            for i, tag in enumerate(tags):
                await lv.append(ListItem(Label(tag), id=f"addtag-{i}"))
        elif self._tag_type == "religion":
            tags = [t for t in RELIGION_TAGS if t not in self._existing]
            self._cur_tags = tags
            for i, tag in enumerate(tags):
                await lv.append(ListItem(Label(tag), id=f"addtag-{i}"))
        elif self._tag_type == "practices":
            tags = [t for t in PRACTICE_TAGS if t not in self._existing]
            self._cur_tags = tags
            for i, tag in enumerate(tags):
                await lv.append(ListItem(Label(tag), id=f"addtag-{i}"))
        elif self._tag_type == "values":
            tags = [t for t in VALUES_TAGS if t not in self._existing]
            self._cur_tags = tags
            for i, tag in enumerate(tags):
                await lv.append(ListItem(Label(tag), id=f"addtag-{i}"))
        elif self._tag_type == "other":
            for group_label, group_tags in _OTHER_GROUPS:
                sep = f"__sep__{group_label}"
                self._cur_tags.append(sep)
                idx = len(self._cur_tags) - 1
                await lv.append(ListItem(
                    Label(f"[dim]── {group_label} ──[/]"),
                    id=f"addtag-{idx}",
                    classes="sep-item",
                ))
                for tag in group_tags:
                    if tag not in self._existing:
                        self._cur_tags.append(tag)
                        idx = len(self._cur_tags) - 1
                        await lv.append(ListItem(Label(tag), id=f"addtag-{idx}"))

        if self._cur_tags:
            first_real = next((t for t in self._cur_tags if not t.startswith("__sep__")), None)
            self._sel_tag = first_real

    @on(Button.Pressed, "#type-domain-btn")
    async def _set_domain(self, _: Button.Pressed) -> None:
        await self._set_section("domain")

    @on(Button.Pressed, "#type-religion-btn")
    async def _set_religion(self, _: Button.Pressed) -> None:
        await self._set_section("religion")

    @on(Button.Pressed, "#type-practices-btn")
    async def _set_practices(self, _: Button.Pressed) -> None:
        await self._set_section("practices")

    @on(Button.Pressed, "#type-values-btn")
    async def _set_values(self, _: Button.Pressed) -> None:
        await self._set_section("values")

    @on(Button.Pressed, "#type-other-btn")
    async def _set_other(self, _: Button.Pressed) -> None:
        await self._set_section("other")

    @on(ListView.Highlighted, "#add-tag-list")
    def _tag_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item and event.item.id:
            try:
                idx = int(event.item.id.split("-", 1)[1])
                tag = self._cur_tags[idx]
                self._sel_tag = None if tag.startswith("__sep__") else tag
            except (ValueError, IndexError):
                pass

    @on(Button.Pressed, "#add-btn")
    def _add(self, _: Button.Pressed) -> None:
        if not self._sel_tag:
            return
        try:
            value = float(self.query_one("#add-value-input", Input).value)
        except ValueError:
            self.notify("Enter a valid float value.", severity="warning")
            return
        self.dismiss((self._sel_tag, value))

    @on(Button.Pressed, "#cancel-btn")
    def _cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


# ─────────────────────────────────────────
# MECHANIC ROW
# ─────────────────────────────────────────

class MechanicRow(Widget):
    """Displays one mechanic entry: [tag label] [value Input] [× button]."""

    class ValueChanged(Message):
        def __init__(self, node_id: str, tag: str, value: float) -> None:
            super().__init__()
            self.node_id = node_id
            self.tag     = tag
            self.value   = value

    class DeleteRequested(Message):
        def __init__(self, node_id: str, tag: str) -> None:
            super().__init__()
            self.node_id = node_id
            self.tag     = tag

    def __init__(self, node_id: str, tag: str, value: float) -> None:
        super().__init__()
        self._node_id  = node_id
        self._tag      = tag
        self._value    = value
        self._mounted  = False
        safe = tag.replace(":", "-")
        self._input_id  = f"mval-{safe}"
        self._delete_id = f"mdel-{safe}"

    def compose(self) -> ComposeResult:
        prefix, _, short = self._tag.partition(":")
        display = f"[dim]{prefix}:[/]{short}" if prefix else self._tag
        with Horizontal():
            yield Static(Text.from_markup(display), classes="mechanic-tag")
            yield Input(f"{self._value}", id=self._input_id, classes="mechanic-input")
            yield Button("×", id=self._delete_id, classes="delete-btn -danger")

    def on_mount(self) -> None:
        self.call_after_refresh(self._activate)

    def _activate(self) -> None:
        self._mounted = True

    @on(Input.Changed)
    def _val_changed(self, event: Input.Changed) -> None:
        event.stop()
        if not self._mounted:
            return
        try:
            self.post_message(self.ValueChanged(self._node_id, self._tag, float(event.value)))
        except ValueError:
            pass

    @on(Button.Pressed)
    def _del_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == self._delete_id:
            self.post_message(self.DeleteRequested(self._node_id, self._tag))


# ─────────────────────────────────────────
# MAIN APP
# ─────────────────────────────────────────

class ImagoEditorApp(App):
    CSS = _CSS
    BINDINGS = [
        Binding("ctrl+s", "save", "Save"),
        Binding("q",      "quit_app", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        ireg = get_imago_registry()
        self._ndata: dict[str, dict] = {
            nid: _node_to_dict(ireg.get_node(nid))
            for nid in ireg.all_node_ids
        }
        self._trees: list[str] = sorted({n["tree"] for n in self._ndata.values()})
        self._dirty: set[str]  = set()
        self._selected_node_id: Optional[str] = None
        self._backup_done: bool = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="app-body"):
            with VerticalScroll(id="domain-sidebar"):
                yield Label("Domains", id="sidebar-title")
                with ListView(id="tree-list"):
                    for tree in self._trees:
                        yield ListItem(Label(tree.title()), id=f"tree-{tree}")
            with TabbedContent(id="main-panel", initial="tab-status"):
                with TabPane("Status", id="tab-status"):
                    with VerticalScroll(id="status-scroll"):
                        for cat_id, cat_label, _ in _STAT_CATEGORIES:
                            yield Label(cat_label, classes="section-header")
                            yield Static("", id=f"missing-{cat_id}", classes="missing-label")
                            yield DataTable(id=f"table-{cat_id}", cursor_type="row")
                        yield Label("Domain Riders", classes="section-header")
                        yield DataTable(id="domain-table", cursor_type="row")
                with TabPane("Node", id="tab-node"):
                    with VerticalScroll(id="node-content-area"):
                        yield Static(
                            "Select a domain from the sidebar, then pick an Imāgō node.",
                            id="no-node-msg",
                        )
        yield Footer()

    def on_mount(self) -> None:
        for cat_id, _, _ in _STAT_CATEGORIES:
            self.query_one(f"#table-{cat_id}", DataTable).add_columns(
                "Tag", "Count", "Total", "Avg/Tree"
            )
        self.query_one("#domain-table", DataTable).add_columns(
            "Tag", "Count", "Pos Total", "Neg Total", "Net/Tree"
        )
        self._refresh_status_tables()
        self.query_one("#tree-list", ListView).focus()

    # ── Status tables ────────────────────────────────────────────────────

    def _refresh_status_tables(self) -> None:
        for cat_id, _, tag_list in _STAT_CATEGORIES:
            rows, missing = _compute_category_stats(self._ndata, tag_list)
            tbl = self.query_one(f"#table-{cat_id}", DataTable)
            tbl.clear()
            for row in rows:
                tbl.add_row(*row)
            miss_text = "Missing: " + ", ".join(missing) if missing else "All tags represented."
            self.query_one(f"#missing-{cat_id}", Static).update(miss_text)

        rider_rows = _compute_domain_rider_stats(self._ndata)
        dt = self.query_one("#domain-table", DataTable)
        dt.clear()
        for row in rider_rows:
            dt.add_row(*row)

    # ── Sidebar selection ────────────────────────────────────────────────

    @on(ListView.Selected, "#tree-list")
    def _on_tree_selected(self, event: ListView.Selected) -> None:
        if not event.item.id:
            return
        tree  = event.item.id.split("-", 1)[1]
        nodes = sorted(
            (n for n in self._ndata.values() if n["tree"] == tree),
            key=lambda n: (n["tier"], n["sort_order"]),
        )
        self.push_screen(
            ImagoPickerModal(tree, nodes),
            lambda nid: self._on_node_picked(nid),
        )

    def _on_node_picked(self, node_id: Optional[str]) -> None:
        if not node_id:
            return
        self._selected_node_id = node_id
        self._rebuild_node_editor(node_id)
        self.query_one(TabbedContent).active = "tab-node"

    # ── Node editor ──────────────────────────────────────────────────────

    @work
    async def _rebuild_node_editor(self, node_id: str) -> None:
        node      = self._ndata[node_id]
        container = self.query_one("#node-content-area")
        await container.remove_children()

        header_text = (
            f"[bold]{_e(node['name'])}[/]"
            f"  ·  {node['tree'].title()} T{node['tier']}"
            f"  [dim]{node['node_id']}[/]"
        )
        await container.mount(Static(Text.from_markup(header_text), id="node-header"))

        for field, label_text, rows in _TEXT_FIELDS:
            val_display = (node[field] or "").replace("\n", " ")
            row = Horizontal(classes="field-row-tall" if rows != 1 else "field-row")
            await container.mount(row)
            await row.mount(
                Label(label_text + ":", classes="field-label-left"),
                Static(val_display, id=f"display-{field}", classes="field-display"),
                Button("Edit", id=f"edit-{field}", classes="edit-btn"),
            )

        await container.mount(Label("Mechanics", classes="mechanic-section-label"))
        scroll = VerticalScroll(id="mechanics-scroll")
        await container.mount(scroll)
        await self._populate_mechanics(scroll, node_id)
        await container.mount(Button("+ Add mechanic", id="add-mechanic-btn", classes="-primary"))

    async def _populate_mechanics(self, scroll: Widget, node_id: str) -> None:
        """Clear scroll and mount a MechanicRow for each mechanic."""
        await scroll.remove_children()
        node = self._ndata[node_id]
        rows = [MechanicRow(node_id, tag, val) for tag, val in sorted(node["mechanics"].items())]
        if rows:
            await scroll.mount(*rows)

    @work
    async def _refresh_mechanics(self) -> None:
        if not self._selected_node_id:
            return
        try:
            scroll = self.query_one("#mechanics-scroll")
        except Exception:
            return
        await self._populate_mechanics(scroll, self._selected_node_id)

    # ── Edit text field buttons ──────────────────────────────────────────

    @on(Button.Pressed)
    def _on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""

        if btn_id.startswith("edit-"):
            field = btn_id[len("edit-"):]
            if field not in ("name", "tooltip_blurb", "description"):
                return
            if not self._selected_node_id:
                return
            node = self._ndata[self._selected_node_id]
            rows = next(r for f, _, r in _TEXT_FIELDS if f == field)
            self.push_screen(
                EditTextModal(field.replace("_", " ").title(), node[field], rows),
                lambda val, f=field: self._on_field_edited(f, val),
            )
            return

        if btn_id == "add-mechanic-btn":
            if not self._selected_node_id:
                return
            existing = set(self._ndata[self._selected_node_id]["mechanics"].keys())
            self.push_screen(
                AddMechanicModal(existing),
                self._on_mechanic_added,
            )
            return

    def _on_field_edited(self, field: str, new_value: Optional[str]) -> None:
        if new_value is None or not self._selected_node_id:
            return
        self._ndata[self._selected_node_id][field] = new_value
        self._dirty.add(self._selected_node_id)
        try:
            display = self.query_one(f"#display-{field}", Static)
            display.update(new_value.replace("\n", " "))
        except Exception:
            pass
        if field == "name":
            try:
                node = self._ndata[self._selected_node_id]
                header_text = (
                    f"[bold]{_e(node['name'])}[/]"
                    f"  ·  {node['tree'].title()} T{node['tier']}"
                    f"  [dim]{node['node_id']}[/]"
                )
                self.query_one("#node-header", Static).update(Text.from_markup(header_text))
            except Exception:
                pass

    def _on_mechanic_added(self, result: Optional[tuple]) -> None:
        if not result or not self._selected_node_id:
            return
        tag, value = result
        self._ndata[self._selected_node_id]["mechanics"][tag] = value
        self._dirty.add(self._selected_node_id)
        self._refresh_mechanics()
        self._refresh_status_tables()

    # ── Mechanic row messages ────────────────────────────────────────────

    @on(MechanicRow.ValueChanged)
    def _on_mechanic_value_changed(self, event: MechanicRow.ValueChanged) -> None:
        self._ndata[event.node_id]["mechanics"][event.tag] = event.value
        self._dirty.add(event.node_id)
        self._refresh_status_tables()

    @on(MechanicRow.DeleteRequested)
    def _on_mechanic_delete_requested(self, event: MechanicRow.DeleteRequested) -> None:
        self._ndata[event.node_id]["mechanics"].pop(event.tag, None)
        self._dirty.add(event.node_id)
        self._refresh_mechanics()
        self._refresh_status_tables()

    # ── Save ─────────────────────────────────────────────────────────────

    def action_save(self) -> None:
        if not self._dirty:
            self.notify("No unsaved changes.")
            return
        if not self._backup_done:
            ts  = datetime.now().strftime("%Y%m%d-%H%M%S")
            bak = _DB_PATH.parent / f"core.db.{ts}.bak"
            shutil.copy2(_DB_PATH, bak)
            self._backup_done = True
            self.notify(f"Backup → {bak.name}")

        conn = sqlite3.connect(_DB_PATH)
        try:
            for node_id in self._dirty:
                n = self._ndata[node_id]
                conn.execute(
                    "UPDATE imago_node "
                    "SET name=?, tooltip_blurb=?, description=?, mechanics_json=? "
                    "WHERE node_id=?",
                    (n["name"], n["tooltip_blurb"], n["description"],
                     json.dumps(n["mechanics"]), node_id),
                )
            conn.commit()
        finally:
            conn.close()

        count = len(self._dirty)
        self._dirty.clear()
        self.notify(f"Saved {count} node(s).")

    def action_quit_app(self) -> None:
        if self._dirty:
            self.notify(f"{len(self._dirty)} unsaved change(s). Press Ctrl+S to save first. Press Ctrl+Q to discard changes and quit anyway.", severity="warning")
            return
        self.exit()


if __name__ == "__main__":
    ImagoEditorApp().run()
