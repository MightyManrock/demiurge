"""
All modal screens used by the Demiurge TUI. Each modal is a self-contained
ModalScreen subclass; they communicate with callers by being pushed via
push_screen_wait() and returning a value from dismiss().
"""
from __future__ import annotations
from typing import TYPE_CHECKING

from rich.markup import escape as _e
from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, Grid, ScrollableContainer
from textual.screen import ModalScreen
from textual.widgets import (
    Button, Input, Label, ListItem, ListView,
    RadioButton, RadioSet, Static,
)

from core.action_core import ActionCategory, ActionDefinition
from logic.tick_logic import (
    SimulationState, _compute_revelation_cap, _revelation_adjusted_cost,
)
from utilities.culture_registry import is_culture_tag
from utilities.domain_registry import get_registry as get_domain_registry
from utilities.imago_registry import get_registry as get_imago_registry, ImagoNode

from display import _get_lum_domain_context, _wrap_desc

from ui.widgets import DomainSquare, ImagoCell, ImagoRevealCell, LoopingListView
from ui.constants import BACK, _DOMAIN_GRID_ORDER, _LATITUDE_OPTS, _STUB_ACTIONS

if TYPE_CHECKING:
    from core.universe_core import NotableMortal


# ─────────────────────────────────────────
# ERROR MODAL
# Displays a blocking error message; dismissed with Enter or Escape.
# ─────────────────────────────────────────

class ErrorModal(ModalScreen):
    BINDINGS = [("escape", "dismiss", "OK"), ("enter", "dismiss", "OK")]

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(classes="picker-box"):
            yield Label("ERROR", classes="picker-title")
            yield Label(self._message)
            yield Button("OK", variant="error", id="ok-btn")

    @on(Button.Pressed, "#ok-btn")
    def _ok(self) -> None:
        self.dismiss()


# ─────────────────────────────────────────
# TOAST MODAL
# Compact dismissible notice — for non-critical warnings
# like affordability blocks. Dismiss with Enter, Esc, or OK.
# ─────────────────────────────────────────

class ToastModal(ModalScreen):
    BINDINGS = [("escape", "dismiss", "OK"), ("enter", "dismiss", "OK")]

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(classes="toast-box"):
            yield Label(self._message)
            yield Button("OK", id="ok-btn")

    @on(Button.Pressed, "#ok-btn")
    def _ok(self) -> None:
        self.dismiss()


# ─────────────────────────────────────────
# PICKER MODAL
# Generic: pick one item from a list.
# Dismisses with the selected key (str) or None.
# ─────────────────────────────────────────

class PickerModal(ModalScreen):
    BINDINGS = [
        ("escape",     "go_back",       "Back"),
        ("ctrl+escape","force_cancel",  "Cancel"),
    ]

    def __init__(
        self,
        title: str,
        items: list[tuple[str, str]],  # (key, display_text)
        description: str = "",
        show_back: bool = False,
    ):
        super().__init__()
        self._title       = title
        self._items       = items
        self._description = description
        self._show_back   = show_back

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box-tall"):
            yield Label(self._title, classes="modal-title")
            if self._description:
                yield Label(_wrap_desc(self._description), classes="modal-desc")
            with ScrollableContainer():
                with LoopingListView(id="picker-list"):
                    for i, (key, text) in enumerate(self._items):
                        yield ListItem(Label(text), id=f"pick-{i}")
            with Horizontal(classes="btn-row"):
                if self._show_back:
                    yield Button("← Back",  id="back-btn")
                yield Button("Cancel", id="cancel-btn", classes="-danger")

    def on_mount(self) -> None:
        self.query_one("#picker-list", ListView).focus()

    @on(ListView.Selected, "#picker-list")
    def _on_selected(self, event: ListView.Selected) -> None:
        idx = int(event.item.id.split("-", 1)[1])
        self.dismiss(self._items[idx][0])

    @on(Button.Pressed, "#back-btn")
    def _on_back(self, _: Button.Pressed) -> None:
        self.dismiss(BACK)

    @on(Button.Pressed, "#cancel-btn")
    def _on_cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_go_back(self) -> None:
        self.dismiss(BACK if self._show_back else None)

    def action_force_cancel(self) -> None:
        self.dismiss(None)


# ─────────────────────────────────────────
# POP + LATITUDE PICKER MODAL
# Variant of PickerModal with a horizontal latitude radio bar.
# Dismisses with (pop_key, latitude_float), BACK, or None.
# ─────────────────────────────────────────

class PopLatitudePickerModal(ModalScreen):
    BINDINGS = [
        ("escape",      "go_back",      "Back"),
        ("ctrl+escape", "force_cancel", "Cancel"),
    ]
    DEFAULT_CSS = """
    PopLatitudePickerModal .latitude-section {
        height: auto;
        align: center middle;
        padding: 1 0 0 0;
    }
    PopLatitudePickerModal RadioSet {
        layout: horizontal;
        border: none;
        background: transparent;
        height: 1;
    }
    """

    def __init__(
        self,
        title: str,
        items: list[tuple[str, str]],
        show_back: bool = False,
    ):
        super().__init__()
        self._title     = title
        self._items     = items
        self._show_back = show_back

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box-tall"):
            yield Label(self._title, classes="modal-title")
            with ScrollableContainer():
                with LoopingListView(id="picker-list"):
                    for i, (key, text) in enumerate(self._items):
                        yield ListItem(Label(text), id=f"pick-{i}")
            with Horizontal(classes="latitude-section"):
                with RadioSet(id="latitude-radio"):
                    yield RadioButton("Strict", id="strict")
                    yield RadioButton("Guided", id="guided", value=True)
                    yield RadioButton("Lax",    id="lax")
            with Horizontal(classes="btn-row"):
                if self._show_back:
                    yield Button("← Back",  id="back-btn")
                yield Button("Cancel", id="cancel-btn", classes="-danger")

    def on_mount(self) -> None:
        self.query_one("#picker-list", ListView).focus()

    def _latitude(self) -> float:
        rs = self.query_one("#latitude-radio", RadioSet)
        bid = rs.pressed_button.id if rs.pressed_button else "guided"
        return next((v for k, _, v in _LATITUDE_OPTS if k == bid), 0.5)

    @on(ListView.Selected, "#picker-list")
    def _on_selected(self, event: ListView.Selected) -> None:
        idx = int(event.item.id.split("-", 1)[1])
        self.dismiss((self._items[idx][0], self._latitude()))

    @on(Button.Pressed, "#back-btn")
    def _on_back(self, _: Button.Pressed) -> None:
        self.dismiss(BACK)

    @on(Button.Pressed, "#cancel-btn")
    def _on_cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_go_back(self) -> None:
        self.dismiss(BACK if self._show_back else None)

    def action_force_cancel(self) -> None:
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
        ("escape",      "go_back",      "Back"),
        ("ctrl+escape", "force_cancel", "Cancel"),
        ("ctrl+enter",  "confirm",      "Confirm"),
    ]

    def __init__(
        self,
        title: str,
        fields: list[tuple[str, str, str]],  # (label, id, default)
        description: str = "",
        show_back: bool = False,
    ):
        super().__init__()
        self._title       = title
        self._fields      = fields
        self._description = description
        self._show_back   = show_back

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box"):
            yield Label(self._title, classes="modal-title")
            if self._description:
                yield Label(_wrap_desc(self._description), classes="modal-desc")
            for label, fid, default in self._fields:
                yield Label(label, classes="field-label")
                yield Input(value=default, id=f"field-{fid}")
            with Horizontal(classes="btn-row"):
                if self._show_back:
                    yield Button("← Back",  id="back-btn")
                yield Button("Cancel",  id="cancel-btn", classes="-danger")
                yield Button("Confirm", id="confirm-btn", classes="-primary")

    @on(Button.Pressed, "#back-btn")
    def _back(self, _: Button.Pressed) -> None:
        self.dismiss(BACK)

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

    def action_go_back(self) -> None:
        self.dismiss(BACK if self._show_back else None)

    def action_force_cancel(self) -> None:
        self.dismiss(None)


# ─────────────────────────────────────────
# DOMAIN PICKER MODAL
# A 4×4 grid of domain squares with color-coded approval borders
# and a per-Luminary focus panel.
# Dismisses with a domain tag (str), "" for skip, or None to cancel.
# ─────────────────────────────────────────

class DomainPickerModal(ModalScreen):
    """4×4 domain grid picker with affiliated domain coloring."""

    BINDINGS = [
        ("escape",      "go_back",      "Back"),
        ("ctrl+escape", "force_cancel", "Cancel"),
        ("up",          "nav('up')",    ""),
        ("down",        "nav('down')",  ""),
        ("left",        "nav('left')",  ""),
        ("right",       "nav('right')", ""),
    ]

    def __init__(
        self,
        state: SimulationState,
        explore_mode: bool = False,
        exclude_tags: set | None = None,
        capped_domains: set | None = None,
        eligible_reveal_domains: set | None = None,
    ) -> None:
        super().__init__()
        self._state        = state
        self._explore_mode = explore_mode

        dreg = get_domain_registry()
        lum_info, fellow_tags, _ = _get_lum_domain_context(state)

        accessible_set = set(dreg.all_tags)
        # Domain-tag unlocking removed; all 16 domains are accessible by default.
        if exclude_tags:
            accessible_set -= exclude_tags
        if capped_domains:
            accessible_set -= capped_domains

        self._dreg                  = dreg
        self._lum_info              = lum_info
        self._fellow_tags           = fellow_tags
        self._accessible_set        = accessible_set
        self._affiliated_set        = set(state.demiurge.affiliated_domains)
        self._eligible_reveal_set   = eligible_reveal_domains or set()

    def compose(self) -> ComposeResult:
        title = "Explore Domain" if self._explore_mode else "Choose Domain"
        with Vertical(classes="modal-box"):
            yield Label(title, classes="modal-title")
            with Grid(id="domain-grid"):
                for tag in _DOMAIN_GRID_ORDER:
                    accessible = tag in self._accessible_set
                    affiliated = tag in self._affiliated_set
                    eligible_reveal = tag in self._eligible_reveal_set
                    _dname = tag.split(":", 1)[1].title()
                    if len(_dname) % 2 == 0:
                        _dname = " " + _dname
                    yield DomainSquare(
                        tag=tag,
                        icon=self._dreg.icon(tag),
                        name=_dname,
                        affiliated=affiliated,
                        accessible=accessible,
                        eligible_reveal=eligible_reveal,
                    )
            yield Static("", id="lum-panel")
            with Horizontal(classes="btn-row"):
                yield Button("Skip Domain", id="skip-btn")
                yield Button("← Back",      id="back-btn")
                yield Button("Cancel",      id="cancel-btn", classes="-danger")

    def on_mount(self) -> None:
        for sq in self.query(DomainSquare):
            if not sq.disabled:
                sq.focus()
                break

    def action_nav(self, direction: str) -> None:
        squares = list(self.query(DomainSquare))
        focused_idx = next((i for i, sq in enumerate(squares) if sq.has_focus), -1)
        if focused_idx == -1:
            self.on_mount()
            return
        row, col = divmod(focused_idx, 4)
        dr, dc = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}[direction]
        r, c = row + dr, col + dc
        while 0 <= r < 4 and 0 <= c < 4:
            candidate = squares[r * 4 + c]
            if not candidate.disabled:
                candidate.focus()
                return
            r, c = r + dr, c + dc

    def on_domain_square_focused(self, event: DomainSquare.Focused) -> None:
        tag   = event.tag
        parts = []
        for lum, lum_tags in self._lum_info:
            if lum_tags:
                lid = str(lum.id)
                v   = self._dreg.luminary_approval(
                    tag, lum_tags,
                    fellow_lum_tags=self._fellow_tags[lid],
                    personality=self._dreg.compute_personality(lum.domains),
                )
                col = "#50b870" if v > 0.15 else ("#b04050" if v < -0.15 else "#5a7090")
                parts.append(f"[{col}]{_e(lum.name[:10])}: {v:+.2f}[/]")
        self.query_one("#lum-panel", Static).update("  ".join(parts))

    def on_domain_square_selected(self, event: DomainSquare.Selected) -> None:
        self.dismiss(event.tag)

    @on(Button.Pressed, "#skip-btn")
    def _skip(self, _: Button.Pressed) -> None:
        self.dismiss("")

    @on(Button.Pressed, "#back-btn")
    def _back(self, _: Button.Pressed) -> None:
        self.dismiss(BACK)

    @on(Button.Pressed, "#cancel-btn")
    def _cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_go_back(self) -> None:
        self.dismiss(BACK)

    def action_force_cancel(self) -> None:
        self.dismiss(None)


# ─────────────────────────────────────────
# IMAGO TREE PICKER
# Shows all 7 nodes of one tree in a 3-column pyramid layout.
# Dismisses with a node_id (str), BACK to return to domain picker,
# or None to cancel.
# ─────────────────────────────────────────

class ImagoTreeModal(ModalScreen):
    """
    Tree-layout Imago picker. Grid is 3 columns × 4 rows (T4 top, T1 bottom).
    T4 is centred; each other tier puts its lower-sort node in col 0, higher in col 2.
    Dismisses with a node_id, BACK, or None.
    """

    BINDINGS = [
        ("escape",      "cancel",       "Back"),
        ("ctrl+escape", "force_cancel", "Cancel"),
        ("up",          "nav('up')",    ""),
        ("down",        "nav('down')",  ""),
        ("left",        "nav('left')",  ""),
        ("right",       "nav('right')", ""),
    ]

    # Cell positions in DOM order → (grid_row, grid_col)
    # Row 0=T4, 1=T3, 2=T2, 3=T1 ; Col 0=left, 1=center, 2=right
    _POSITIONS = [(0, 1), (1, 0), (1, 2), (2, 0), (2, 2), (3, 0), (3, 2)]

    def __init__(self, state: SimulationState, tree: str) -> None:
        super().__init__()
        self._state = state
        self._tree  = tree

        ireg         = get_imago_registry()
        unlocked_set = set(state.demiurge.unlocked_imagines)
        nodes        = ireg.nodes_for_tree(tree)  # sorted by (tier, sort_order)

        by_tier: dict[int, list[ImagoNode]] = {1: [], 2: [], 3: [], 4: []}
        for n in nodes:
            by_tier[n.tier].append(n)

        self._by_tier    = by_tier
        self._unlocked   = unlocked_set
        dreg             = get_domain_registry()
        lum_info, fellow_tags, _ = _get_lum_domain_context(state)
        self._dreg        = dreg
        self._lum_info    = lum_info
        self._fellow_tags = fellow_tags

    def _imago_score(self, node: ImagoNode) -> float:
        """Weighted sum of (luminary_approval × mechanic_direction) across all Luminaries."""
        total, count = 0.0, 0
        for lum, lum_tags in self._lum_info:
            if not lum_tags:
                continue
            lid   = str(lum.id)
            score = sum(
                self._dreg.luminary_approval(
                    tag, lum_tags,
                    fellow_lum_tags=self._fellow_tags[lid],
                    personality=self._dreg.compute_personality(lum.domains),
                ) * direction
                for tag, direction in node.mechanics.items()
                if tag.startswith("domain:")
            )
            total += score
            count += 1
        return total / count if count else 0.0

    def _approval_class(self, node: ImagoNode) -> str:
        s = self._imago_score(node)
        if s > 0.15:
            return "good"
        if s < -0.15:
            return "danger"
        return ""

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box"):
            yield Label(f"{self._tree.title()} — Imāginēs", classes="modal-title")
            with Grid(id="imago-grid"):
                for tier in (4, 3, 2, 1):
                    nodes = self._by_tier[tier]
                    if tier == 4:
                        yield Static("", classes="imago-spacer")
                        node     = nodes[0]
                        unlocked = node.node_id in self._unlocked
                        yield ImagoCell(node, unlocked, self._approval_class(node) if unlocked else "")
                        yield Static("", classes="imago-spacer")
                    else:
                        left, right = nodes[0], nodes[1]
                        for node in (left, right):
                            unlocked = node.node_id in self._unlocked
                            cell = ImagoCell(node, unlocked, self._approval_class(node) if unlocked else "")
                            if node is left:
                                yield cell
                                yield Static("", classes="imago-spacer")
                            else:
                                yield cell
            yield Static("", id="imago-tooltip")
            with Horizontal(classes="btn-row"):
                yield Button("← Domain",  id="back-btn")
                yield Button("Cancel",    id="cancel-btn",  classes="-danger")

    def on_mount(self) -> None:
        cells = list(self.query(ImagoCell))
        target = next((c for c in cells if c._unlocked), cells[0] if cells else None)
        if target:
            target.focus()

    def action_nav(self, direction: str) -> None:
        cells   = list(self.query(ImagoCell))
        pos_map = {p: i for i, p in enumerate(self._POSITIONS)}
        focused = next((i for i, c in enumerate(cells) if c.has_focus), -1)
        if focused == -1:
            self.on_mount()
            return
        row, col = self._POSITIONS[focused]
        new_pos  = None
        if direction == "up" and row > 0:
            new_pos = (row - 1, 1 if row - 1 == 0 else col)
        elif direction == "down" and row < 3:
            new_pos = (row + 1, 0 if col == 1 else col)
        elif direction == "left" and col == 2:
            new_pos = (row, 0)
        elif direction == "right" and col == 0:
            new_pos = (row, 2)
        if new_pos and new_pos in pos_map:
            cells[pos_map[new_pos]].focus()

    def on_imago_cell_focused(self, event: ImagoCell.Focused) -> None:
        ireg = get_imago_registry()
        node = ireg.get_node(event.node_id)
        tip  = (node.tooltip_blurb or f"Tier {node.tier} apex — cannot be drawn from the Underreal.") if node else ""
        self.query_one("#imago-tooltip", Static).update(tip)

    def on_imago_cell_selected(self, event: ImagoCell.Selected) -> None:
        self.dismiss(event.node_id)

    @on(Button.Pressed, "#back-btn")
    def _back_btn(self, _: Button.Pressed) -> None:
        self.dismiss(BACK)

    @on(Button.Pressed, "#cancel-btn")
    def _cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(BACK)

    def action_force_cancel(self) -> None:
        self.dismiss(None)


# ─────────────────────────────────────────
# IMAGO DETAIL MODAL
# Confirmation screen for a chosen Imago node.
# ─────────────────────────────────────────

class ImagoDetailModal(ModalScreen):
    """
    Confirmation screen for a chosen Imago node.
    Shows full description, domain/culture effects, and per-Luminary affinity scores.
    Dismisses with True (confirm), False (back one step), or None (cancel entirely).
    """

    BINDINGS = [
        ("escape",      "back",         "Back"),
        ("ctrl+escape", "force_cancel", "Cancel"),
    ]

    def __init__(self, node: ImagoNode, state: SimulationState) -> None:
        super().__init__()
        self._node  = node
        self._state = state

    def _body(self) -> Text:
        node = self._node
        dreg = get_domain_registry()
        lum_info, fellow_tags, _ = _get_lum_domain_context(self._state)

        lines: list[str] = []
        lines.append(f"[bold #c0ccdc]{_e(node.name)}[/]")
        lines.append(f"[#3a5a7a]Tier {node.tier}  ·  {node.tree.title()} tree[/]")
        lines.append("")
        lines.append(f"[#9090a8]{_e(node.description)}[/]")
        lines.append("")

        domain_fx  = [(t, v) for t, v in node.mechanics.items() if t.startswith("domain:")]
        culture_fx = [(t, v) for t, v in node.mechanics.items() if is_culture_tag(t)]

        if domain_fx:
            lines.append("[bold #5a7090]DOMAIN EFFECTS[/]")
            for tag, v in sorted(domain_fx, key=lambda x: -abs(x[1])):
                short = tag.split(":", 1)[1]
                col   = "#50b870" if v > 0 else "#b04050"
                lines.append(f"  [{col}]{short:<16}  {v:+.2f}[/]")
            lines.append("")

        if culture_fx:
            lines.append("[bold #5a7090]CULTURE EFFECTS[/]")
            for tag, v in sorted(culture_fx, key=lambda x: -abs(x[1])):
                short = tag.split(":", 1)[1]
                col   = "#50b870" if v > 0 else "#b04050"
                lines.append(f"  [{col}]{short:<16}  {v:+.2f}[/]")
            lines.append("")

        lines.append("[bold #5a7090]LUMINARY AFFINITIES[/]")
        for lum, lum_tags in lum_info:
            if not lum_tags:
                continue
            lid   = str(lum.id)
            score = sum(
                dreg.luminary_approval(
                    tag, lum_tags,
                    fellow_lum_tags=fellow_tags[lid],
                    personality=dreg.compute_personality(lum.domains),
                ) * direction
                for tag, direction in node.mechanics.items()
                if tag.startswith("domain:")
            )
            col = "#50b870" if score > 0.1 else ("#b04050" if score < -0.1 else "#5a7090")
            lines.append(f"  [{col}]{_e(lum.name):<16}  {score:+.2f}[/]")

        return Text.from_markup("\n".join(lines))

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box-tall"):
            yield Label("Imāgō — Confirm", classes="modal-title")
            with ScrollableContainer():
                yield Static(self._body(), id="imago-detail-body")
            with Horizontal(classes="btn-row"):
                yield Button("← Back",  id="back-btn")
                yield Button("Cancel",  id="cancel-btn",  classes="-danger")
                yield Button("Confirm", id="confirm-btn", classes="-primary")

    def on_mount(self) -> None:
        self.query_one("#confirm-btn", Button).focus()

    @on(Button.Pressed, "#confirm-btn")
    def _confirm(self, _: Button.Pressed) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#back-btn")
    def _back(self, _: Button.Pressed) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#cancel-btn")
    def _cancel_btn(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_back(self) -> None:
        self.dismiss(False)

    def action_force_cancel(self) -> None:
        self.dismiss(None)


# ─────────────────────────────────────────
# IMAGO REVEAL MODALS
# ─────────────────────────────────────────

class ImagoRevealModal(ModalScreen):
    """
    Imago tree view for the Reveal Imago flow.
    Shows Revelation costs, pool/cap header, and eligibility highlights.
    Dismisses with a node_id string (eligible node selected), BACK, or None (cancel).
    """

    BINDINGS = [
        ("escape",      "go_back",      "Back"),
        ("ctrl+escape", "force_cancel", "Cancel"),
        ("up",          "nav('up')",    ""),
        ("down",        "nav('down')",  ""),
        ("left",        "nav('left')",  ""),
        ("right",       "nav('right')", ""),
    ]

    _POSITIONS = [(0, 1), (1, 0), (1, 2), (2, 0), (2, 2), (3, 0), (3, 2)]

    def __init__(self, state: "SimulationState", domain_tag: str) -> None:
        super().__init__()
        self._state      = state
        self._domain_tag = domain_tag
        tree = domain_tag.split(":", 1)[1] if ":" in domain_tag else domain_tag
        self._tree = tree

        ireg  = get_imago_registry()
        nodes = ireg.nodes_for_tree(tree)
        by_tier: dict[int, list] = {1: [], 2: [], 3: [], 4: []}
        for n in nodes:
            by_tier[n.tier].append(n)
        self._by_tier = by_tier

        rev_count = state.demiurge.revealed_imagines
        self._costs = {
            n.node_id: _revelation_adjusted_cost(n.tier, rev_count)
            for n in nodes
        }
        self._pool = state.demiurge.revelation_pools.get(domain_tag, 0.0)
        self._cap  = _compute_revelation_cap(state, domain_tag)

    def compose(self) -> "ComposeResult":
        pool_str = f"Revelation: {self._pool:.2f} / {self._cap:.2f}"
        with Vertical(classes="modal-box"):
            yield Label(f"{self._tree.title()} — Reveal Imāgō", classes="modal-title")
            yield Label(pool_str, id="reveal-pool-label")
            with Grid(id="imago-grid"):
                for tier in (4, 3, 2, 1):
                    nodes = self._by_tier[tier]
                    if tier == 4:
                        yield Static("", classes="imago-spacer")
                        node = nodes[0]
                        yield ImagoRevealCell(node, self._state, self._costs[node.node_id])
                        yield Static("", classes="imago-spacer")
                    else:
                        left, right = nodes[0], nodes[1]
                        for node in (left, right):
                            cell = ImagoRevealCell(node, self._state, self._costs[node.node_id])
                            if node is left:
                                yield cell
                                yield Static("", classes="imago-spacer")
                            else:
                                yield cell
            with Horizontal(classes="btn-row"):
                yield Button("← Back",  id="back-btn")
                yield Button("Cancel",  id="cancel-btn", classes="-danger")

    def on_mount(self) -> None:
        for cell in self.query(ImagoRevealCell):
            if not cell.disabled:
                cell.focus()
                break

    def action_nav(self, direction: str) -> None:
        cells = list(self.query(ImagoRevealCell))
        focused_idx = next((i for i, c in enumerate(cells) if c.has_focus), -1)
        if focused_idx == -1:
            self.on_mount()
            return
        pos_map = {i: p for i, p in enumerate(self._POSITIONS)}
        cur_pos = pos_map.get(focused_idx, (0, 1))
        dr, dc = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}[direction]
        r, c = cur_pos[0] + dr, cur_pos[1] + dc
        while 0 <= r <= 3 and 0 <= c <= 2:
            for i, p in pos_map.items():
                if p == (r, c) and not cells[i].disabled:
                    cells[i].focus()
                    return
            r, c = r + dr, c + dc

    def on_imago_reveal_cell_selected(self, event: ImagoRevealCell.Selected) -> None:
        self.dismiss(event.node_id)

    @on(Button.Pressed, "#back-btn")
    def _back(self, _: Button.Pressed) -> None:
        self.dismiss(BACK)

    @on(Button.Pressed, "#cancel-btn")
    def _cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_go_back(self) -> None:
        self.dismiss(BACK)

    def action_force_cancel(self) -> None:
        self.dismiss(None)


class ImagoRevealDetailModal(ModalScreen):
    """
    Confirmation screen for Reveal Imago.
    Shows node description, costs, and pool balance. Confirm button labeled 'Reveal'.
    Dismisses with True (confirm), False (back to tree), or None (cancel).
    """

    BINDINGS = [
        ("escape",      "go_back",      "Back"),
        ("ctrl+escape", "force_cancel", "Cancel"),
    ]

    def __init__(
        self,
        node: "ImagoNode",
        state: "SimulationState",
        domain_tag: str,
        cost: int,
        pool: float,
    ) -> None:
        super().__init__()
        self._node       = node
        self._state      = state
        self._domain_tag = domain_tag
        self._cost       = cost
        self._pool       = pool

    def _body(self) -> "Text":
        node = self._node
        dreg = get_domain_registry()
        lum_info, fellow_tags, _ = _get_lum_domain_context(self._state)

        lines: list[str] = []
        lines.append(f"[bold #c0ccdc]{_e(node.name)}[/]")
        lines.append(f"[#3a5a7a]Tier {node.tier}  ·  {node.tree.title()} tree[/]")
        lines.append("")
        lines.append(f"[#9090a8]{_e(node.description)}[/]")
        lines.append("")

        remaining = round(self._pool - self._cost, 2)
        cost_col = "#50b870" if self._pool >= self._cost else "#b04050"
        lines.append(f"[bold {cost_col}]Cost: {self._cost} Revelation[/]")
        lines.append(f"[#5a7090]Pool: {self._pool:.2f}  →  Remaining after reveal: {remaining:.2f}[/]")
        lines.append("")

        domain_fx  = [(t, v) for t, v in node.mechanics.items() if t.startswith("domain:")]
        culture_fx = [(t, v) for t, v in node.mechanics.items() if is_culture_tag(t)]

        if domain_fx:
            lines.append("[bold #5a7090]DOMAIN EFFECTS[/]")
            for tag, v in sorted(domain_fx, key=lambda x: -abs(x[1])):
                short = tag.split(":", 1)[1]
                col   = "#50b870" if v > 0 else "#b04050"
                lines.append(f"  [{col}]{short:<16}  {v:+.2f}[/]")
            lines.append("")

        if culture_fx:
            lines.append("[bold #5a7090]CULTURE EFFECTS[/]")
            for tag, v in sorted(culture_fx, key=lambda x: -abs(x[1])):
                short = tag.split(":", 1)[1]
                col   = "#50b870" if v > 0 else "#b04050"
                lines.append(f"  [{col}]{short:<16}  {v:+.2f}[/]")
            lines.append("")

        lines.append("[bold #5a7090]LUMINARY AFFINITIES[/]")
        for lum, lum_tags in lum_info:
            if not lum_tags:
                continue
            lid   = str(lum.id)
            score = sum(
                dreg.luminary_approval(
                    tag, lum_tags,
                    fellow_lum_tags=fellow_tags[lid],
                    personality=dreg.compute_personality(lum.domains),
                ) * direction
                for tag, direction in node.mechanics.items()
                if tag.startswith("domain:")
            )
            col = "#50b870" if score > 0.1 else ("#b04050" if score < -0.1 else "#5a7090")
            lines.append(f"  [{col}]{_e(lum.name):<16}  {score:+.2f}[/]")

        return Text.from_markup("\n".join(lines))

    def compose(self) -> "ComposeResult":
        can_reveal = self._pool >= self._cost
        with Vertical(classes="modal-box-tall"):
            yield Label("Reveal Imāgō — Confirm", classes="modal-title")
            with ScrollableContainer():
                yield Static(self._body(), id="imago-detail-body")
            with Horizontal(classes="btn-row"):
                yield Button("← Back",  id="back-btn")
                yield Button("Cancel",  id="cancel-btn", classes="-danger")
                yield Button(
                    "Reveal",
                    id="reveal-btn",
                    classes="-primary",
                    disabled=not can_reveal,
                )

    def on_mount(self) -> None:
        self.query_one("#reveal-btn", Button).focus()

    @on(Button.Pressed, "#reveal-btn")
    def _reveal(self, _: Button.Pressed) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#back-btn")
    def _back(self, _: Button.Pressed) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#cancel-btn")
    def _cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_go_back(self) -> None:
        self.dismiss(False)

    def action_force_cancel(self) -> None:
        self.dismiss(None)


# ─────────────────────────────────────────
# MORTAL DETAIL MODAL
# Read-only profile shown before appointing a Proxius.
# Dismisses with True (confirm appoint), BACK sentinel (re-pick), or None (cancel).
# ─────────────────────────────────────────

class MortalDetailModal(ModalScreen):
    BINDINGS = [
        ("escape",      "go_back",      "Back"),
        ("ctrl+escape", "force_cancel", "Cancel"),
    ]

    def __init__(self, mortal: "NotableMortal", state: "SimulationState") -> None:
        super().__init__()
        self._mortal = mortal
        self._state  = state

    def _body(self) -> "Text":
        m     = self._mortal
        state = self._state

        sp_obj  = state.species.get(str(m.species_id)) if m.species_id else None
        sp_name = sp_obj.name if sp_obj else "Unknown"

        pop_obj  = state.pops.get(str(m.pop_id)) if m.pop_id else None
        civ_obj  = (state.civilizations.get(str(pop_obj.civilization_id))
                    if pop_obj and pop_obj.civilization_id else None)
        civ_name = civ_obj.name if civ_obj else (
            state.civilizations.get(str(m.civilization_id)).name
            if m.civilization_id and str(m.civilization_id) in state.civilizations else "Unknown"
        )

        loc_obj  = state.locations.get(str(m.current_location))
        loc_name = loc_obj.name if loc_obj else "Unknown"

        lines: list[str] = []
        lines.append(f"[bold #c0ccdc]{_e(m.name)}[/]")
        lines.append(f"[#3a5a7a]{sp_name}  ·  {civ_name}  ·  {loc_name}[/]")
        if m.description:
            lines.append("")
            lines.append(f"[#9090a8]{_e(m.description)}[/]")
        lines.append("")

        age_str = f"{m.chrono_age:.0f}"
        if m.bio_age != m.chrono_age:
            age_str += f"  (bio {m.bio_age:.0f})"
        prom_str = "  ".join(r.value for r in m.prominence_roles if r.value != "none") or "none"
        lines.append(f"[bold #5a7090]OVERVIEW[/]")
        lines.append(f"  Age         {age_str}")
        lines.append(f"  Alignment   {m.alignment:.2f}")
        lines.append(f"  Prominence  {prom_str}")
        if m.origin_pop_subsumed:
            lines.append(f"  [#b08020](Origin community has been subsumed)[/]")
        lines.append("")

        if pop_obj:
            pop_loc_obj  = state.locations.get(str(pop_obj.current_location))
            pop_loc_name = pop_loc_obj.name if pop_loc_obj else "?"
            lines.append(f"[bold #5a7090]ORIGIN COMMUNITY[/]")
            lines.append(f"  {civ_name}  [{pop_obj.stratum.upper()}]  ·  {pop_loc_name}  sz:{pop_obj.size_magnitude}")
            if pop_obj.dominant_beliefs:
                top = sorted(pop_obj.dominant_beliefs.items(), key=lambda x: -x[1])[:4]
                bstr = "  ".join(f"{t.split(':',1)[-1]}:{v:.2f}" for t, v in top)
                lines.append(f"  beliefs: {bstr}")
            lines.append("")

        if m.belief_tags:
            lines.append(f"[bold #5a7090]PERSONAL BELIEFS[/]")
            for tag, v in sorted(m.belief_tags.items(), key=lambda x: -x[1]):
                short = tag.split(":", 1)[-1]
                col   = "#50b870" if v >= 0.5 else "#5a7090"
                lines.append(f"  [{col}]{short:<16}  {v:.2f}[/]")
            lines.append("")

        if m.culture_tags:
            lines.append(f"[bold #5a7090]CULTURAL TRAITS[/]")
            for tag, v in sorted(m.culture_tags.items(), key=lambda x: -x[1]):
                short = tag.split(":", 1)[-1]
                lines.append(f"  [#5a7090]{short:<16}  {v:.2f}[/]")
            lines.append("")

        if m.personal_tags:
            lines.append(f"[bold #5a7090]PERSONAL TRAITS[/]")
            for tag in m.personal_tags:
                lines.append(f"  [#7a6090]{_e(tag)}[/]")
            lines.append("")

        return Text.from_markup("\n".join(lines))

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box-tall"):
            yield Label("Mortal Profile", classes="modal-title")
            with ScrollableContainer():
                yield Static(self._body(), id="mortal-detail-body")
            with Horizontal(classes="btn-row"):
                yield Button("← Back",            id="back-btn")
                yield Button("Cancel",             id="cancel-btn",  classes="-danger")
                yield Button("Appoint as Proxius", id="confirm-btn", classes="-primary")

    def on_mount(self) -> None:
        self.query_one("#confirm-btn", Button).focus()

    @on(Button.Pressed, "#back-btn")
    def _back(self, _: Button.Pressed) -> None:
        self.dismiss(BACK)

    @on(Button.Pressed, "#cancel-btn")
    def _cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#confirm-btn")
    def _confirm(self, _: Button.Pressed) -> None:
        self.dismiss(True)

    def action_go_back(self) -> None:
        self.dismiss(BACK)

    def action_force_cancel(self) -> None:
        self.dismiss(None)


# ─────────────────────────────────────────
# ACTION BROWSER MODAL
# Two-level: category → action.
# Dismisses with (action_key, ActionDefinition) or None.
# ─────────────────────────────────────────

class ActionBrowserModal(ModalScreen):
    BINDINGS = [
        ("escape",      "cancel",       "Cancel"),
        ("ctrl+escape", "cancel",       ""),
    ]

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
                with LoopingListView(id="cat-list"):
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

    def on_mount(self) -> None:
        self.query_one("#cat-list", ListView).focus()

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

        # If a manually queued action already occupies this category, ask to cancel it
        if cat.value in self._queued_cats:
            existing = self._queued_cats[cat.value]
            cancel_it = await self.app.push_screen_wait(
                YesNoModal(
                    f"'{existing}' already queued",
                    "Cancel it and choose a different action for this category?",
                )
            )
            if not cancel_it:
                return
            # Remove that action instance from the queue
            cat_def_ids = {
                str(defn.id)
                for key, defn in self._library.items()
                if defn.category == cat
            }
            self._state.action_queue = [
                ai for ai in self._state.action_queue
                if str(ai.action_definition_id) not in cat_def_ids
            ]
            del self._queued_cats[cat.value]

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
        chosen_key = await self.app.push_screen_wait(
            PickerModal(cat.value.replace("_", " ").title(), items, show_back=True)
        )
        if chosen_key is None or chosen_key == BACK:
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
            self.dismiss((chosen_key, self._library[chosen_key]))

    @on(Button.Pressed, "#cancel-btn")
    def _cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)
