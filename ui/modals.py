"""
All modal screens used by the Demiurge TUI. Each modal is a self-contained
ModalScreen subclass; they communicate with callers by being pushed via
push_screen_wait() and returning a value from dismiss().
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Iterable

from rich.markup import escape as _e
from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, Grid, ScrollableContainer
from textual.screen import ModalScreen
from textual.widgets import (
    Button, Checkbox, Input, Label, ListItem, ListView,
    RadioButton, RadioSet, RichLog, Static,
    TabbedContent, Tab, TabPane,
)

from core.action_core import ActionCategory, ActionDefinition, OngoingAction, compute_cooldown
from logic.tick_logic import (
    SimulationState,
    _compute_revelation_cap, _revelation_adjusted_cost,
    ENTITY_VISIBILITY_FLOOR,
)
from utilities.culture_registry import is_culture_tag
from utilities.domain_registry import get_registry as get_domain_registry
from utilities.imago_registry import get_registry as get_imago_registry, ImagoNode

from ui.display import _get_lum_domain_context, _wrap_desc, _short_tag, _pop_stratum_label

from ui.widgets import DomainSquare, ImagoCell, ImagoRevealCell, ImagoTreeGrid, LoopingListView
from ui.constants import BACK, _DOMAIN_GRID_ORDER, _LATITUDE_OPTS, _STUB_ACTIONS

from core.universe_core import MortalRole, MortalStatus

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
        ("escape",    "force_cancel", "Cancel"),
        ("backspace", "go_back",      "Back"),
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
        ("escape",    "force_cancel", "Cancel"),
        ("backspace", "go_back",      "Back"),
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

    def __init__(self, question: str, detail: str = "",
                 yes_label: str = "Yes", no_label: str = "No"):
        super().__init__()
        self._question  = question
        self._detail    = detail
        self._yes_label = yes_label
        self._no_label  = no_label

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box"):
            yield Label(self._question, classes="modal-title")
            if self._detail:
                yield Label(self._detail, classes="modal-desc")
            with Horizontal(classes="btn-row"):
                yield Button(self._yes_label, id="yes-btn", classes="-primary")
                yield Button(self._no_label,  id="no-btn",  classes="-danger")

    @on(Button.Pressed, "#yes-btn")
    def _yes(self, _: Button.Pressed) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#no-btn")
    def _no(self, _: Button.Pressed) -> None:
        self.dismiss(False)

    def action_no(self) -> None:
        self.dismiss(False)


# ─────────────────────────────────────────
# QUIT CONFIRM MODAL
# Returns "quit" | "save" | None (cancel/Esc)
# ─────────────────────────────────────────

class QuitConfirmModal(ModalScreen):
    BINDINGS = [("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box"):
            yield Label("Quit?", classes="modal-title")
            yield Label(
                "Unsaved progress will be lost.",
                classes="modal-desc",
            )
            with Horizontal(classes="btn-row"):
                yield Button("Save and quit",   id="save-btn", classes="-primary")
                yield Button("Quit",            id="quit-btn", classes="-danger")
                yield Button("Keep playing",    id="cancel-btn")

    @on(Button.Pressed, "#save-btn")
    def _save(self, _: Button.Pressed) -> None:
        self.dismiss("save")

    @on(Button.Pressed, "#quit-btn")
    def _quit(self, _: Button.Pressed) -> None:
        self.dismiss("quit")

    @on(Button.Pressed, "#cancel-btn")
    def _cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


# ─────────────────────────────────────────
# TEXT FORM MODAL
# fields: list of (label, field_id, default)
# Dismisses with dict[str, str] or None.
# ─────────────────────────────────────────

class TextFormModal(ModalScreen):
    BINDINGS = [
        ("escape",    "force_cancel", "Cancel"),
        ("backspace", "go_back",      "Back"),
        ("ctrl+enter","confirm",      "Confirm"),
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
        ("escape",    "force_cancel", "Cancel"),
        ("backspace", "go_back",      "Back"),
        ("up",        "nav('up')",    ""),
        ("down",      "nav('down')",  ""),
        ("left",      "nav('left')",  ""),
        ("right",     "nav('right')", ""),
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
                yield from _domain_grid_squares(
                    self._state, self._dreg, self._accessible_set,
                    show_names=True,
                    eligible_reveal_tags=self._eligible_reveal_set or None,
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
                parts.append(f"[{col}]{_e(lum.name[:10])}: {v:+.0%}[/]")
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
# EXPLORE BELIEFS MODAL
# Dedicated domain picker for Explore Beliefs. Selection does not immediately
# dismiss — the player also configures auto-stop settings before confirming.
# Returns (tag, t1_one, t1_both, t2_one, t2_both, t3_one, t3_both) on confirm,
# BACK or None otherwise.
# ─────────────────────────────────────────

class ExploreBeliefsModal(ModalScreen):
    """Domain grid + auto-stop settings for Explore Beliefs.

    Returns (tag, stop_t1_one, stop_t1_both, stop_t2_one, stop_t2_both,
             stop_t3_one, stop_t3_both), BACK, or None.
    """

    BINDINGS = [
        ("escape",    "force_cancel", "Cancel"),
        ("backspace", "go_back",      "Back"),
        ("up",        "nav('up')",    ""),
        ("down",      "nav('down')",  ""),
        ("left",      "nav('left')",  ""),
        ("right",     "nav('right')", ""),
    ]

    def __init__(
        self,
        state: SimulationState,
        capped_domains: set | None = None,
    ) -> None:
        super().__init__()
        self._state         = state
        self._selected_tag: str | None = None

        dreg = get_domain_registry()
        lum_info, fellow_tags, _ = _get_lum_domain_context(state)

        accessible_set = set(dreg.all_tags)
        if capped_domains:
            accessible_set -= capped_domains

        self._dreg           = dreg
        self._lum_info       = lum_info
        self._fellow_tags    = fellow_tags
        self._accessible_set = accessible_set

        first_tag = next(iter(sorted(accessible_set)), None)
        self._initial_tree = first_tag.split(":", 1)[1] if first_tag and ":" in first_tag else "fire"

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box-wide"):
            yield Label("Explore Beliefs", classes="modal-title")
            with Horizontal(id="explore-panels"):
                with Vertical(id="explore-left"):
                    yield Static("Domain: -", id="domain-label")
                    with Grid(id="domain-grid"):
                        yield from _domain_grid_squares(
                            self._state, self._dreg, self._accessible_set,
                            show_names=True,
                        )
                    yield Static("", id="lum-panel")
                    with Vertical(id="auto-stop-panel"):
                        yield Label("Auto-stop when…", classes="auto-stop-title")
                        with Grid(id="auto-stop-grid"):
                            yield Checkbox("One T1 unlockable",   id="stop-t1-one",  value=False, disabled=True)
                            yield Checkbox("Both T1s unlockable", id="stop-t1-both", value=False, disabled=True)
                            yield Checkbox("One T2 unlockable",   id="stop-t2-one",  value=False, disabled=True)
                            yield Checkbox("Both T2s unlockable", id="stop-t2-both", value=False, disabled=True)
                            yield Checkbox("One T3 unlockable",   id="stop-t3-one",  value=False, disabled=True)
                            yield Checkbox("Both T3s unlockable", id="stop-t3-both", value=False, disabled=True)
                        yield Checkbox("Revelation cap reached", id="stop-cap", value=True, disabled=True)
                    with Horizontal(classes="btn-row"):
                        yield Button("← Back",  id="back-btn")
                        yield Button("Cancel",  id="cancel-btn", classes="-danger")
                        yield Button("Confirm", id="confirm-btn", disabled=True)
                with Vertical(id="explore-right"):
                    yield Label("— Imāgō reference —", classes="explore-ref-title")
                    yield Static("", id="imago-ref-pool")
                    yield ImagoTreeGrid(self._state, self._initial_tree, readonly=True)
                    yield Static("", id="imago-ref-tooltip")

    def on_mount(self) -> None:
        for sq in self.query(DomainSquare):
            if not sq.disabled:
                sq.focus()
                break

    _CB_GRID = [
        ("stop-t1-one",  0, 0), ("stop-t1-both", 0, 1),
        ("stop-t2-one",  1, 0), ("stop-t2-both", 1, 1),
        ("stop-t3-one",  2, 0), ("stop-t3-both", 2, 1),
    ]

    def action_nav(self, direction: str) -> None:
        focused_cb = next((cb for cb in self.query(Checkbox) if cb.has_focus), None)
        if focused_cb is not None:
            entry = next((e for e in self._CB_GRID if e[0] == focused_cb.id), None)
            if entry:
                _, row, col = entry
                dr, dc = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}[direction]
                r, c = row + dr, col + dc
                while 0 <= r < 3 and 0 <= c < 2:
                    target_id = next((e[0] for e in self._CB_GRID if e[1] == r and e[2] == c), None)
                    if target_id:
                        cb = self.query_one(f"#{target_id}", Checkbox)
                        if not cb.disabled:
                            cb.focus()
                            return
                    r, c = r + dr, c + dc
            return

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

    def on_key(self, event) -> None:
        if event.key == "tab":
            focused_sq = next((sq for sq in self.query(DomainSquare) if sq.has_focus), None)
            if focused_sq is not None:
                event.prevent_default(); event.stop()
                self._focus_first_checkbox()
                return
            focused_cb = next((cb for cb in self.query(Checkbox) if cb.has_focus), None)
            if focused_cb is not None:
                event.prevent_default(); event.stop()
                self.query_one("#back-btn", Button).focus()
                return
        elif event.key == "shift+tab":
            focused_sq = next((sq for sq in self.query(DomainSquare) if sq.has_focus), None)
            if focused_sq is not None:
                event.prevent_default(); event.stop()
                return
            focused_cb = next((cb for cb in self.query(Checkbox) if cb.has_focus), None)
            if focused_cb is not None:
                event.prevent_default(); event.stop()
                self._focus_selected_square()
                return
            back_btn = self.query_one("#back-btn", Button)
            if back_btn.has_focus:
                event.prevent_default(); event.stop()
                self._focus_first_checkbox()
                return

    def _focus_first_checkbox(self) -> None:
        for cb_id, _, _ in self._CB_GRID:
            cb = self.query_one(f"#{cb_id}", Checkbox)
            if not cb.disabled:
                cb.focus()
                return

    def _focus_selected_square(self) -> None:
        if self._selected_tag:
            for sq in self.query(DomainSquare):
                if sq._tag == self._selected_tag and not sq.disabled:
                    sq.focus()
                    return
        for sq in self.query(DomainSquare):
            if not sq.disabled:
                sq.focus()
                return

    def on_domain_square_focused(self, event: DomainSquare.Focused) -> None:
        tag = event.tag
        self._selected_tag = tag
        btn = self.query_one("#confirm-btn", Button)
        btn.disabled = False
        btn.add_class("continue-ready")
        name  = _domain_display_name(tag)
        pool  = self._state.demiurge.revelation_pools.get(tag, 0.0)
        cap   = _compute_revelation_cap(self._state, tag)
        cap_s = f"{cap:.0f}" if cap > 0.0 else "∞"
        self.query_one("#domain-label", Static).update(
            f"Domain: {name}  {pool:.0f} / {cap_s} Revelation"
        )
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
                parts.append(f"[{col}]{_e(lum.name[:10])}: {v:+.0%}[/]")
        self.query_one("#lum-panel", Static).update("  ".join(parts))
        self._update_checkbox_states(tag)
        tree = tag.split(":", 1)[1] if ":" in tag else tag
        pool  = self._state.demiurge.revelation_pools.get(tag, 0.0)
        rcap  = _compute_revelation_cap(self._state, tag)
        cap_s = f"{rcap:.0f}" if rcap > 0.0 else "∞"
        self.query_one("#imago-ref-pool", Static).update(
            f"Revelation: {pool:.0f} / {cap_s}"
        )
        self.query_one(ImagoTreeGrid).load_tree(tree)
        self.query_one("#imago-ref-tooltip", Static).update("")

    def _update_checkbox_states(self, tag: str) -> None:
        ireg = get_imago_registry()
        tree = tag.split(":", 1)[1] if ":" in tag else tag
        unlocked = set(self._state.demiurge.unlocked_imagines)
        nodes = ireg.nodes_for_tree(tree)
        for tier in (1, 2, 3):
            remaining = sum(1 for n in nodes if n.tier == tier and n.node_id not in unlocked)
            cb_one  = self.query_one(f"#stop-t{tier}-one",  Checkbox)
            cb_both = self.query_one(f"#stop-t{tier}-both", Checkbox)
            cb_one.disabled  = remaining < 1
            cb_both.disabled = remaining < 2
            if remaining < 1:
                cb_one.value = False
            if remaining < 2:
                cb_both.value = False

    def on_imago_cell_focused(self, event: ImagoCell.Focused) -> None:
        ireg = get_imago_registry()
        node = ireg.get_node(event.node_id)
        tip  = (node.tooltip_blurb or f"Tier {node.tier} apex.") if node else ""
        self.query_one("#imago-ref-tooltip", Static).update(tip)

    def on_imago_reveal_cell_focused(self, event: ImagoRevealCell.Focused) -> None:
        ireg = get_imago_registry()
        node = ireg.get_node(event.node_id)
        tip  = (node.tooltip_blurb or f"Tier {node.tier} apex.") if node else ""
        self.query_one("#imago-ref-tooltip", Static).update(tip)

    _updating_checkboxes: bool = False

    @on(Checkbox.Changed)
    def _autostop_changed(self, event: Checkbox.Changed) -> None:
        cb_ids = {e[0] for e in self._CB_GRID}
        if event.checkbox.id not in cb_ids or self._updating_checkboxes or not event.value:
            return
        self._updating_checkboxes = True
        try:
            for cb_id, _, _ in self._CB_GRID:
                if cb_id != event.checkbox.id:
                    self.query_one(f"#{cb_id}", Checkbox).value = False
        finally:
            self._updating_checkboxes = False

    def on_domain_square_selected(self, event: DomainSquare.Selected) -> None:
        self._selected_tag = event.tag
        self.query_one("#confirm-btn", Button).focus()

    def _do_confirm(self) -> None:
        if self._selected_tag:
            self.dismiss((
                self._selected_tag,
                self.query_one("#stop-t1-one",  Checkbox).value,
                self.query_one("#stop-t1-both", Checkbox).value,
                self.query_one("#stop-t2-one",  Checkbox).value,
                self.query_one("#stop-t2-both", Checkbox).value,
                self.query_one("#stop-t3-one",  Checkbox).value,
                self.query_one("#stop-t3-both", Checkbox).value,
            ))

    @on(Button.Pressed, "#confirm-btn")
    def _confirm(self, _: Button.Pressed) -> None:
        self._do_confirm()

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
    Tree-layout Imago picker. Dismisses with a node_id, BACK, or None.
    Rendering and keyboard nav are handled by the embedded ImagoTreeGrid widget.
    """

    BINDINGS = [
        ("escape",    "force_cancel", "Cancel"),
        ("backspace", "cancel",       "Back"),
    ]

    def __init__(self, state: SimulationState, tree: str) -> None:
        super().__init__()
        self._state = state
        self._tree  = tree

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box"):
            yield Label(f"{self._tree.title()} — Imāginēs", classes="modal-title")
            yield ImagoTreeGrid(self._state, self._tree)
            yield Static("", id="imago-tooltip")
            with Horizontal(classes="btn-row"):
                yield Button("← Domain",  id="back-btn")
                yield Button("Cancel",    id="cancel-btn",  classes="-danger")

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

def _imago_panel_body(node: "ImagoNode", state: "SimulationState") -> Text:
    """Shared body renderer for single-imago confirmation panels."""
    dreg = get_domain_registry()
    lum_info, fellow_tags, _ = _get_lum_domain_context(state)

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
            lines.append(f"  [{col}]{short:<16}  {v:+.0%}[/]")
        lines.append("")

    if culture_fx:
        lines.append("[bold #5a7090]CULTURE EFFECTS[/]")
        for tag, v in sorted(culture_fx, key=lambda x: -abs(x[1])):
            short = tag.split(":", 1)[1]
            col   = "#50b870" if v > 0 else "#b04050"
            lines.append(f"  [{col}]{short:<16}  {v:+.0%}[/]")
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
        lines.append(f"  [{col}]{_e(lum.name):<16}  {score:+.0%}[/]")

    return Text.from_markup("\n".join(lines))


class ImagoDetailModal(ModalScreen):
    """
    Confirmation screen for a chosen Imago node.
    Shows full description, domain/culture effects, and per-Luminary affinity scores.
    Dismisses with True (confirm), False (back one step), or None (cancel entirely).
    """

    BINDINGS = [
        ("escape",    "force_cancel", "Cancel"),
        ("backspace", "back",         "Back"),
    ]

    def __init__(self, node: ImagoNode, state: SimulationState) -> None:
        super().__init__()
        self._node  = node
        self._state = state

    def _body(self) -> Text:
        return _imago_panel_body(self._node, self._state)

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
# SHAPE DREAM CONFIRM MODAL
# Double-wide confirmation screen for a chosen pair of Imago nodes.
# ─────────────────────────────────────────

class ShapeDreamConfirmModal(ModalScreen):
    """
    Confirmation screen for a Shape Dream — shows both Imāginēs side by side.
    Dismisses with True (confirm), False (back to config), or None (cancel).
    """

    BINDINGS = [
        ("escape",    "force_cancel", "Cancel"),
        ("backspace", "back",         "Back"),
    ]

    def __init__(self, node_a: "ImagoNode", node_b: "ImagoNode", state: "SimulationState") -> None:
        super().__init__()
        self._node_a = node_a
        self._node_b = node_b
        self._state  = state

    def compose(self) -> ComposeResult:
        with Vertical(classes="sd-confirm-modal"):
            yield Label("Shape Dream — Confirm", classes="modal-title")
            with Horizontal(classes="sd-confirm-panels"):
                with ScrollableContainer(classes="sd-confirm-left"):
                    yield Static(_imago_panel_body(self._node_a, self._state))
                with ScrollableContainer(classes="sd-confirm-right"):
                    yield Static(_imago_panel_body(self._node_b, self._state))
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
        ("escape",    "force_cancel", "Cancel"),
        ("backspace", "go_back",      "Back"),
        ("up",        "nav('up')",    ""),
        ("down",      "nav('down')",  ""),
        ("left",      "nav('left')",  ""),
        ("right",     "nav('right')", ""),
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
        ("escape",    "force_cancel", "Cancel"),
        ("backspace", "go_back",      "Back"),
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
                lines.append(f"  [{col}]{short:<16}  {v:+.0%}[/]")
            lines.append("")

        if culture_fx:
            lines.append("[bold #5a7090]CULTURE EFFECTS[/]")
            for tag, v in sorted(culture_fx, key=lambda x: -abs(x[1])):
                short = tag.split(":", 1)[1]
                col   = "#50b870" if v > 0 else "#b04050"
                lines.append(f"  [{col}]{short:<16}  {v:+.0%}[/]")
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
            lines.append(f"  [{col}]{_e(lum.name):<16}  {score:+.0%}[/]")

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
        ("escape",    "force_cancel", "Cancel"),
        ("backspace", "go_back",      "Back"),
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

        age_str = f"{m.chrono_age:,.0f}"
        if m.bio_age != m.chrono_age:
            age_str += f"  (bio {m.bio_age:,.0f})"
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
                bstr = "  ".join(f"{_short_tag(t)}:{v:.0%}" for t, v in top)
                lines.append(f"  beliefs: {bstr}")
            lines.append("")

        if m.belief_tags:
            lines.append(f"[bold #5a7090]PERSONAL BELIEFS[/]")
            for tag, v in sorted(m.belief_tags.items(), key=lambda x: -x[1]):
                short = _short_tag(tag)
                col   = "#50b870" if v >= 0.5 else "#5a7090"
                lines.append(f"  [{col}]{short:<16}  {v:.0%}[/]")
            lines.append("")

        if m.culture_tags:
            lines.append(f"[bold #5a7090]CULTURAL TRAITS[/]")
            for tag, v in sorted(m.culture_tags.items(), key=lambda x: -x[1]):
                short = tag.split(":", 1)[-1]
                lines.append(f"  [#5a7090]{short:<16}  {v:.0%}[/]")
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
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, state: SimulationState, library: dict,
                 initial_category: "ActionCategory | None" = None):
        super().__init__()
        self._state            = state
        self._library          = library
        self._initial_category = initial_category

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
            with ScrollableContainer(id="cat-list-container"):
                with LoopingListView(id="cat-list"):
                    for i, (cat, _) in enumerate(self._cat_actions.items()):
                        is_cooling = self._state.category_cooldowns.counters.get(cat, 0) > 0
                        used    = self._queued_cats.get(cat.value)
                        ongoing = self._state.pending_actions.get(cat.value)
                        if used:
                            note = f"  [used: {used}]"
                        elif ongoing:
                            note = f"  [ongoing: {ongoing.action_key.replace('_',' ')} ({ongoing.executed_ticks}x)]"
                        else:
                            note = ""
                        label_text = f"{cat.value.replace('_',' ').title()}{note}"
                        if is_cooling:
                            label_text = f"[#3a5070]{label_text}[/#3a5070]"
                        yield ListItem(
                            Label(label_text),
                            id=f"cat-{i}",
                        )
            with Horizontal(classes="btn-row"):
                yield Button("Cancel", id="cancel-btn", classes="-danger")

    def on_mount(self) -> None:
        self.query_one("#cat-list", ListView).focus()
        if self._initial_category is not None:
            cat = self._initial_category
            actions = self._cat_actions.get(cat, [])
            if actions:
                self.query_one("#cat-list-container").display = False
                self.call_after_refresh(lambda: self._open_cat(cat, actions))

    @on(ListView.Selected, "#cat-list")
    def _on_cat_selected(self, event: ListView.Selected) -> None:
        idx = int(event.item.id.split("-", 1)[1])
        cat, actions = list(self._cat_actions.items())[idx]
        self._open_cat(cat, actions)

    def _reveal_cat_list(self) -> None:
        try:
            self.query_one("#cat-list-container").display = True
            self.query_one("#cat-list", ListView).focus()
        except Exception:
            pass

    @work
    async def _open_cat(self, cat: "ActionCategory", actions: list) -> None:
        # If an action is already pending in this category, offer management
        ongoing = self._state.pending_actions.get(cat.value)
        if ongoing:
            od    = self._library.get(ongoing.action_key)
            oname = od.name if od else ongoing.action_key
            if ongoing.repeating:
                choice = await self.app.push_screen_wait(
                    PickerModal(
                        f"[ONGOING] {oname}",
                        [
                            ("stop",     "Stop ongoing action"),
                            ("override", "Override this tick only"),
                            ("leave",    "Leave it running"),
                        ],
                        description=f"{ongoing.successful_ticks}/{ongoing.executed_ticks} successes, {ongoing.ticks_active} ticks old",
                    )
                )
                if choice is None:
                    self.dismiss(None)
                    return
                if choice == "leave":
                    self._reveal_cat_list()
                    return
                if choice == "stop":
                    del self._state.pending_actions[cat.value]
                    self._state.category_cooldowns.counters[cat] = compute_cooldown(
                        cat, self._state.demiurge.puissance
                    )
                # "override" falls through to the action picker below
            else:
                choice = await self.app.push_screen_wait(
                    PickerModal(
                        f"[QUEUED] {oname}",
                        [
                            ("replace", "Cancel and pick another action"),
                            ("cancel",  "Cancel this action"),
                            ("keep",    "Keep it queued"),
                        ],
                    )
                )
                if choice is None:
                    self.dismiss(None)
                    return
                if choice == "keep":
                    self._reveal_cat_list()
                    return
                del self._state.pending_actions[cat.value]
                if choice == "cancel":
                    self._reveal_cat_list()
                    return
                # "replace" falls through to the action picker below

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
                self._reveal_cat_list()
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
        _has_directed_proxii = any(
            m.active_goal is not None
            for pid in self._state.demiurge.proxius_ids
            if (m := self._state.mortals.get(str(pid)))
        )
        items = []
        for key, defn in actions:
            fp_total    = defn.footprint_cost.total()
            essence_str = ""
            if defn.essence_cost != 0:
                verb        = "↑" if defn.essence_cost < 0 else "↓"
                essence_str = f"  Ess{verb}{abs(defn.essence_cost):g}"
            persist = "  [persist]" if "can_persist" in defn.tags else ""
            stub    = "  [stub]"    if key in _STUB_ACTIONS else ""
            unavail = "  [unavailable]" if (key == "rescind_directive" and not _has_directed_proxii) else ""
            items.append(
                (key, f"{defn.name:<34}  FP:{fp_total:.2f}{essence_str}{persist}{stub}{unavail}")
            )
        chosen_key = await self.app.push_screen_wait(
            PickerModal(cat.value.replace("_", " ").title(), items, show_back=True)
        )
        if chosen_key == BACK:
            self._reveal_cat_list()
            return
        if chosen_key is None:
            self.dismiss(None)
            return

        if chosen_key in _STUB_ACTIONS:
            defn = self._library[chosen_key]
            await self.app.push_screen_wait(
                YesNoModal(
                    f"{defn.name} — not yet implemented",
                    "This action requires systems that are planned but not yet built.",
                )
            )
            self._reveal_cat_list()
            return

        if chosen_key == "rescind_directive" and not _has_directed_proxii:
            await self.app.push_screen_wait(
                ToastModal("None of your Proxiī have active directives.")
            )
            self._reveal_cat_list()
            return

        if chosen_key in self._library:
            self.dismiss((chosen_key, self._library[chosen_key]))

    @on(Button.Pressed, "#cancel-btn")
    def _cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


# ─────────────────────────────────────────
# CATEGORY PENDING MODAL
# Shown when the player clicks an occupied action category slot.
# Returns: None (keep), "override_resume", "replace", or "cancel".
# ─────────────────────────────────────────

class CategoryPendingModal(ModalScreen):
    BINDINGS = [
        ("escape", "keep", "Keep"),
        ("1", "keep", "Keep"),
        ("2", "override_resume", "Override once"),
        ("3", "replace", "Replace"),
        ("4", "cancel_pending", "Cancel pending"),
    ]

    def __init__(
        self,
        category: ActionCategory,
        pending: OngoingAction,
        action_name: str,
        cooldown_remaining: int = 0,
    ) -> None:
        super().__init__()
        self._category = category
        self._pending = pending
        self._action_name = action_name
        self._cooldown_remaining = cooldown_remaining

    def compose(self) -> ComposeResult:
        mode_label = "[REPEATING]" if self._pending.repeating else "[ONE-SHOT]"
        stats = (
            f"{self._action_name}  {mode_label}"
            f"\nQueued at tick {self._pending.started_at_tick}"
            f"  ·  Active {self._pending.ticks_active} tick(s)"
        )
        if self._cooldown_remaining > 0:
            stats += f"\nCooldown: {self._cooldown_remaining} tick(s) remaining"

        with Vertical(classes="modal-box"):
            yield Label(
                f"[bold]{self._category.value}[/bold] slot occupied",
                classes="modal-title",
            )
            yield Static(stats, classes="modal-desc")
            yield Button("1  Keep current", id="keep-btn", variant="default")
            yield Button(
                "2  Override once, then resume",
                id="override-btn",
                variant="primary",
                disabled=not self._pending.repeating,
            )
            yield Button("3  Replace with new action", id="replace-btn", variant="warning")
            yield Button("4  Cancel pending action", id="cancel-pending-btn", variant="error")

    @on(Button.Pressed, "#keep-btn")
    def _keep(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#replace-btn")
    def _replace(self, _: Button.Pressed) -> None:
        self.dismiss("replace")

    @on(Button.Pressed, "#override-btn")
    def _override_resume(self, _: Button.Pressed) -> None:
        self.dismiss("override_resume")

    @on(Button.Pressed, "#cancel-pending-btn")
    def _cancel_pending(self, _: Button.Pressed) -> None:
        self.dismiss("cancel")

    def action_keep(self) -> None:
        self.dismiss(None)

    def action_override_resume(self) -> None:
        self.dismiss("override_resume")

    def action_replace(self) -> None:
        self.dismiss("replace")

    def action_cancel_pending(self) -> None:
        self.dismiss("cancel")


# ─────────────────────────────────────────
# SHARED HELPERS FOR CONFIG MODALS
# ─────────────────────────────────────────

def _eligible_domain_tags(state: SimulationState) -> set[str]:
    """Return the set of domain tags that have at least one unlocked Imago node."""
    ireg = get_imago_registry()
    unlocked = set(state.demiurge.unlocked_imagines)
    return {
        tag for tag in _DOMAIN_GRID_ORDER
        if any(n.node_id in unlocked for n in ireg.nodes_for_tree(tag.split(":", 1)[1]))
    }


def _has_any_unlockable(state: SimulationState) -> bool:
    """Return True if any Imago node has prereqs met and is not yet unlocked."""
    ireg     = get_imago_registry()
    dreg     = get_domain_registry()
    unlocked = set(state.demiurge.unlocked_imagines)
    return any(
        ireg.is_unlockable(n.node_id, unlocked)
        for tag in dreg.all_tags
        for n in ireg.nodes_for_tree(tag.split(":", 1)[1])
    )


def _eligible_reveal_domain_tags(state: SimulationState) -> set[str]:
    """
    Return domain tags where the revelation pool can afford at least one
    unlockable node — used for 'eligible-reveal' styling in the domain grid.
    """
    ireg     = get_imago_registry()
    dreg     = get_domain_registry()
    unlocked = set(state.demiurge.unlocked_imagines)
    rev      = state.demiurge.revealed_imagines

    def _min_cost(tag: str) -> int:
        tree = tag.split(":", 1)[1]
        return min(
            (
                _revelation_adjusted_cost(n.tier, rev)
                for n in ireg.nodes_for_tree(tree)
                if n.node_id not in unlocked and ireg.is_unlockable(n.node_id, unlocked)
            ),
            default=9999,
        )

    return {
        tag for tag in dreg.all_tags
        if state.demiurge.revelation_pools.get(tag, 0.0) >= _min_cost(tag)
    }


def _compose_entity_list(
    state: SimulationState,
    entity_type: str,
    id_prefix: str,
    anchor_location: "str | None" = None,
) -> "list[tuple[str, ListItem]]":
    """
    Build a list of (entity_id, ListItem) pairs for a ListView.

    entity_type:
      "mortal"  — visible, non-deceased, non-proxius/herald mortals
      "proxius" — mortals that are active Proxii
      "pop"     — visible Pops
      "world"   — visible SignificantLocations

    anchor_location (str UUID or None): when set, limits mortals/pops to those
    whose current_location matches this PopLocation id.
    """
    items: list[tuple[str, ListItem]] = []

    if entity_type in ("mortal", "proxius"):
        proxius_ids = {str(pid) for pid in state.demiurge.proxius_ids}
        for mid, m in state.mortals.items():
            if m.status == MortalStatus.DECEASED:
                continue
            if not (m.pinned or m.visibility > ENTITY_VISIBILITY_FLOOR):
                continue
            if entity_type == "mortal":
                if m.role in (MortalRole.PROXIUS, MortalRole.HERALD):
                    continue
                if mid in proxius_ids:
                    continue
            else:
                if m.role != MortalRole.PROXIUS or mid not in proxius_ids:
                    continue
            if anchor_location is not None and str(m.current_location) != str(anchor_location):
                continue
            pop_obj  = state.pops.get(str(m.pop_id)) if m.pop_id else None
            pop_name = _pop_stratum_label(pop_obj) if pop_obj else "?"
            loc_obj  = state.locations.get(str(m.current_location))
            loc      = (loc_obj.name or "?") if loc_obj else "?"
            name     = m.name or "?"
            align    = m.alignment if m.alignment is not None else 0.0
            i = len(items)
            items.append((mid, ListItem(
                Label(f"{name:<18}  {align*100:>4.0f}%  {pop_name:<14}  {loc}"),
                id=f"{id_prefix}-{i}",
            )))

    elif entity_type == "pop":
        for pid, pop in state.pops.items():
            if not (pop.pinned or pop.visibility > ENTITY_VISIBILITY_FLOOR):
                continue
            if anchor_location is not None and str(pop.current_location) != str(anchor_location):
                continue
            pop_label = _pop_stratum_label(pop)
            loc_obj   = state.locations.get(str(pop.current_location))
            loc       = (loc_obj.name or "?") if loc_obj else "?"
            name      = pop.name or pop_label
            i = len(items)
            items.append((pid, ListItem(
                Label(f"{name:<22}  {pop_label:<14}  {loc}"),
                id=f"{id_prefix}-{i}",
            )))

    elif entity_type == "world":
        for wid, world in state.worlds.items():
            if not (world.pinned or world.visibility > ENTITY_VISIBILITY_FLOOR):
                continue
            name = world.name or "?"
            i = len(items)
            items.append((wid, ListItem(Label(name), id=f"{id_prefix}-{i}")))

    return items


def _domain_grid_squares(
    state: SimulationState,
    dreg: "object",
    eligible_tags: "set[str]",
    show_names: bool = False,
    eligible_reveal_tags: "set[str] | None" = None,
) -> "Iterable[DomainSquare]":
    """Yield the 16 DomainSquare widgets for a domain picker grid."""
    for tag in _DOMAIN_GRID_ORDER:
        if show_names:
            name = _domain_display_name(tag)
            if len(name) % 2 == 0:
                name = " " + name
        else:
            name = ""
        yield DomainSquare(
            tag=tag,
            icon=dreg.icon(tag),
            name=name,
            affiliated=tag in state.demiurge.affiliated_domains,
            accessible=tag in eligible_tags,
            eligible_reveal=eligible_reveal_tags is not None and tag in eligible_reveal_tags,
        )


def _nav_domain_grid(squares: list, direction: str, cols: int = 8) -> None:
    """Move keyboard focus within a flat list of DomainSquares laid out in `cols` columns."""
    focused_idx = next((i for i, sq in enumerate(squares) if sq.has_focus), -1)
    if focused_idx == -1:
        return
    num_rows = (len(squares) + cols - 1) // cols
    row, col  = divmod(focused_idx, cols)
    if direction in ("left", "right"):
        dc = 1 if direction == "right" else -1
        c  = col + dc
        while 0 <= c < cols:
            idx = row * cols + c
            if idx < len(squares) and not squares[idx].disabled:
                squares[idx].focus(); return
            c += dc
        row_range = range(row + 1, num_rows) if direction == "right" else range(row - 1, -1, -1)
        for nr in row_range:
            for sc in (range(cols) if direction == "right" else range(cols - 1, -1, -1)):
                idx = nr * cols + sc
                if idx < len(squares) and not squares[idx].disabled:
                    squares[idx].focus(); return
        enabled = [sq for sq in squares if not sq.disabled]
        if enabled:
            (enabled[0] if direction == "right" else enabled[-1]).focus()
    else:
        dr = 1 if direction == "down" else -1
        r  = row + dr
        while 0 <= r < num_rows:
            idx = r * cols + col
            if idx < len(squares) and not squares[idx].disabled:
                squares[idx].focus(); return
            r += dr


def _domain_display_name(tag: str) -> str:
    """Return the title-cased name portion of a domain tag (e.g. 'domain:fire' → 'Fire')."""
    return tag.split(":", 1)[1].title() if ":" in tag else tag.title()


class _ImagoSwapMixin:
    """Provides `_swap_imago_tree(container_id, tag)` as a @work method."""

    @work
    async def _swap_imago_tree(
        self, container_id: str, tag: str, *, focus_first: bool = False
    ) -> None:
        tree      = tag.split(":", 1)[1]
        container = self.query_one(f"#{container_id}", ScrollableContainer)
        await container.remove_children()
        await container.mount(ImagoTreeGrid(self._state, tree))
        if focus_first:
            cells = [c for c in container.query(ImagoCell) if c._unlocked]
            if cells:
                cells[0].focus()


# ─────────────────────────────────────────
# WHISPER CONFIG MODAL
# Unified mortal + domain + imago picker for the Whisper action.
# Replaces the 3-step wizard. Dismisses with (mortal_id_str, domain_tag,
# imago_node_id) on Continue, BACK, or None on cancel.
# ─────────────────────────────────────────

class WhisperConfigModal(_ImagoSwapMixin, ModalScreen):
    """
    Single-screen Whisper configuration. Left panel: mortal list.
    Right panel: 2×8 domain grid + dynamic imago tree.
    Continue is gated until mortal, domain, and imago are all selected.
    """

    BINDINGS = [
        ("escape",    "cancel",           "Cancel"),
        ("backspace", "back",             "Back"),
        ("up",        "nav_domain('up')",    ""),
        ("down",      "nav_domain('down')",  ""),
        ("left",      "nav_domain('left')",  ""),
        ("right",     "nav_domain('right')", ""),
    ]

    def __init__(
        self,
        state: SimulationState,
        prefill: "tuple[str, str, str] | None" = None,
    ) -> None:
        super().__init__()
        self._state          = state
        self._prefill        = prefill
        self._mortal_id:     str | None = prefill[0] if prefill else None
        self._domain_tag:    str | None = prefill[1] if prefill else None
        self._imago_node_id: str | None = prefill[2] if prefill else None
        self._dreg           = get_domain_registry()
        self._eligible_tags  = _eligible_domain_tags(state)
        self._mortals        = _compose_entity_list(state, "mortal", "mortal")
        self._mortal_ids     = [mid for mid, _ in self._mortals]

    def compose(self) -> ComposeResult:
        with Vertical(classes="whisper-config-modal"):
            yield Label("Whisper to Mortal", classes="modal-title")
            with Horizontal(classes="whisper-panels"):
                with Vertical(classes="whisper-left"):
                    yield Label("Mortal: —", id="mortal-label")
                    with LoopingListView(id="mortal-list"):
                        for _, item in self._mortals:
                            yield item
                with Vertical(classes="whisper-right"):
                    yield Label("Domain: —", id="domain-label")
                    with Grid(id="whisper-domain-grid"):
                        yield from _domain_grid_squares(self._state, self._dreg, self._eligible_tags)
                    yield Label("Imāgō: —", id="imago-label")
                    with ScrollableContainer(id="whisper-tree-container"):
                        pass
                    with Horizontal(classes="btn-row"):
                        yield Button("← Back",     id="back-btn")
                        yield Button("Cancel",     id="cancel-btn",   classes="-danger")
                        yield Button("Continue →", id="continue-btn", disabled=True)

    def on_mount(self) -> None:
        if self._prefill:
            mortal_id, domain_tag, imago_node_id = self._prefill
            if mortal_id in self._mortal_ids:
                self.query_one("#mortal-list", ListView).index = self._mortal_ids.index(mortal_id)
            m = self._state.mortals.get(mortal_id)
            if m:
                self.query_one("#mortal-label", Label).update(f"Mortal: {m.name}")
            self.query_one("#domain-label", Label).update(
                f"Domain: {_domain_display_name(domain_tag)}"
            )
            ireg = get_imago_registry()
            node = ireg.get_node(imago_node_id)
            self.query_one("#imago-label", Label).update(
                f"Imāgō: {node.name if node else imago_node_id}"
            )
            self._swap_imago_tree("whisper-tree-container", domain_tag)
        elif self._mortal_ids:
            self._mortal_id = self._mortal_ids[0]
            m = self._state.mortals.get(self._mortal_id)
            if m:
                self.query_one("#mortal-label", Label).update(f"Mortal: {m.name}")
        self._check_continue()

    def _check_continue(self) -> None:
        ready = bool(self._mortal_id and self._domain_tag and self._imago_node_id)
        btn   = self.query_one("#continue-btn", Button)
        btn.disabled = not ready
        if ready:
            btn.add_class("continue-ready")
        else:
            btn.remove_class("continue-ready")

    def action_nav_domain(self, direction: str) -> None:
        squares = list(self.query(DomainSquare))
        if any(sq.has_focus for sq in squares):
            _nav_domain_grid(squares, direction)

    @work
    async def _clear_domain_tree(self) -> None:
        container = self.query_one("#whisper-tree-container", ScrollableContainer)
        await container.remove_children()

    def on_key(self, event) -> None:
        focused = self.focused
        if event.key == "tab":
            if isinstance(focused, ListView):
                squares = list(self.query(DomainSquare))
                target  = next((sq for sq in squares if not sq.disabled), None)
                if target:
                    target.focus()
                event.prevent_default(); event.stop()
            elif isinstance(focused, DomainSquare):
                tag = focused._tag
                self._domain_tag    = tag
                self._imago_node_id = None
                self.query_one("#domain-label", Label).update(f"Domain: {_domain_display_name(tag)}")
                self.query_one("#imago-label",  Label).update("Imāgō: —")
                self._check_continue()
                self._swap_imago_tree("whisper-tree-container", tag, focus_first=True)
                event.prevent_default(); event.stop()
            elif isinstance(focused, ImagoCell):
                self.query_one("#back-btn", Button).focus()
                event.prevent_default(); event.stop()
            elif isinstance(focused, Button) and focused.id == "continue-btn":
                self.query_one("#mortal-list", ListView).focus()
                event.prevent_default(); event.stop()
        elif event.key == "shift+tab":
            if isinstance(focused, ListView):
                self.query_one("#continue-btn", Button).focus()
                event.prevent_default(); event.stop()
            elif isinstance(focused, Button) and focused.id == "back-btn":
                cells = [c for c in self.query(ImagoCell) if c._unlocked]
                if cells:
                    cells[0].focus()
                event.prevent_default(); event.stop()
            elif isinstance(focused, ImagoCell):
                self._domain_tag    = None
                self._imago_node_id = None
                self.query_one("#domain-label", Label).update("Domain: —")
                self.query_one("#imago-label",  Label).update("Imāgō: —")
                self._check_continue()
                self._clear_domain_tree()
                squares = list(self.query(DomainSquare))
                target  = next((sq for sq in squares if not sq.disabled), None)
                if target:
                    target.focus()
                event.prevent_default(); event.stop()

    @on(ListView.Highlighted, "#mortal-list")
    def _on_mortal_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item is None:
            return
        idx = int(event.item.id.rsplit("-", 1)[1])
        self._mortal_id = self._mortal_ids[idx]
        m = self._state.mortals.get(self._mortal_id)
        if m:
            self.query_one("#mortal-label", Label).update(f"Mortal: {m.name}")
        self._check_continue()

    def on_domain_square_focused(self, event: DomainSquare.Focused) -> None:
        self.query_one("#domain-label", Label).update(f"Domain: {_domain_display_name(event.tag)}")

    def on_domain_square_selected(self, event: DomainSquare.Selected) -> None:
        tag = event.tag
        self._domain_tag    = tag
        self._imago_node_id = None
        self.query_one("#domain-label", Label).update(f"Domain: {_domain_display_name(tag)}")
        self.query_one("#imago-label",  Label).update("Imāgō: —")
        self._check_continue()
        self._swap_imago_tree("whisper-tree-container", tag)

    def on_imago_cell_focused(self, event: ImagoCell.Focused) -> None:
        self._imago_node_id = event.node_id
        ireg = get_imago_registry()
        node = ireg.get_node(event.node_id)
        name = node.name if node else event.node_id
        self.query_one("#imago-label", Label).update(f"Imāgō: {name}")
        self._check_continue()

    def on_imago_cell_selected(self, event: ImagoCell.Selected) -> None:
        self._imago_node_id = event.node_id
        ireg = get_imago_registry()
        node = ireg.get_node(event.node_id)
        name = node.name if node else event.node_id
        self.query_one("#imago-label", Label).update(f"Imāgō: {name}")
        self._check_continue()
        if self._mortal_id and self._domain_tag and self._imago_node_id:
            self.dismiss((self._mortal_id, self._domain_tag, self._imago_node_id))

    @on(Button.Pressed, "#continue-btn")
    def _on_continue(self, _: Button.Pressed) -> None:
        if self._mortal_id and self._domain_tag and self._imago_node_id:
            self.dismiss((self._mortal_id, self._domain_tag, self._imago_node_id))

    @on(Button.Pressed, "#back-btn")
    def _on_back(self, _: Button.Pressed) -> None:
        self.dismiss(BACK)

    @on(Button.Pressed, "#cancel-btn")
    def _on_cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_back(self) -> None:
        self.dismiss(BACK)


class ShapeDreamConfigModal(_ImagoSwapMixin, ModalScreen):
    """
    Single-screen Shape Dream configuration. Left panel: mortal list.
    Right panel: two tabs (one per Imāgō slot) each with a domain grid +
    imago tree. Buttons live below the tabs. Dismisses with
    (mortal_id, imago_node_id_a, imago_node_id_b).
    """

    BINDINGS = [
        ("escape",    "cancel",              "Cancel"),
        ("backspace", "back",                "Back"),
        ("up",        "nav_domain('up')",    ""),
        ("down",      "nav_domain('down')",  ""),
        ("left",      "nav_domain('left')",  ""),
        ("right",     "nav_domain('right')", ""),
    ]

    def __init__(
        self,
        state: SimulationState,
        prefill: "tuple[str, str, str] | None" = None,
    ) -> None:
        super().__init__()
        self._state   = state
        self._prefill = prefill
        self._dreg          = get_domain_registry()
        self._eligible_tags = _eligible_domain_tags(state)
        self._mortals       = _compose_entity_list(state, "mortal", "sd-mortal")
        self._mortal_ids    = [mid for mid, _ in self._mortals]

        if prefill:
            mortal_id, imago_a, imago_b = prefill
            self._mortal_id: str | None = mortal_id
            self._imago_a:   str | None = imago_a
            self._imago_b:   str | None = imago_b
            self._domain_a:  str | None = "domain:" + imago_a.split(":")[0]
            self._domain_b:  str | None = "domain:" + imago_b.split(":")[0]
        else:
            self._mortal_id = None
            self._imago_a   = None
            self._imago_b   = None
            self._domain_a  = None
            self._domain_b  = None

    def compose(self) -> ComposeResult:
        with Vertical(classes="shape-dream-modal"):
            yield Label("Shape Dream", classes="modal-title")
            with Horizontal(classes="shape-dream-panels"):
                with Vertical(classes="shape-dream-left"):
                    yield Label("Mortal: —", id="sd-mortal-label")
                    with LoopingListView(id="sd-mortal-list"):
                        for _, item in self._mortals:
                            yield item
                with Vertical(classes="shape-dream-right"):
                    with TabbedContent(
                        id="sd-tabs",
                        classes="shape-dream-tabs",
                        initial="sd-tab-a",
                    ):
                        with TabPane("Domain 1: Imāgō 1", id="sd-tab-a"):
                            yield Label("Domain: —", id="sd-domain-label-a")
                            with Grid(id="shape-dream-domain-grid-a"):
                                yield from _domain_grid_squares(self._state, self._dreg, self._eligible_tags)
                            yield Label("Imāgō: —", id="sd-imago-label-a")
                            with ScrollableContainer(id="shape-dream-tree-container-a"):
                                pass
                        with TabPane("Domain 2: Imāgō 2", id="sd-tab-b"):
                            yield Label("Domain: —", id="sd-domain-label-b")
                            with Grid(id="shape-dream-domain-grid-b"):
                                yield from _domain_grid_squares(self._state, self._dreg, self._eligible_tags)
                            yield Label("Imāgō: —", id="sd-imago-label-b")
                            with ScrollableContainer(id="shape-dream-tree-container-b"):
                                pass
                    with Horizontal(classes="btn-row"):
                        yield Button("← Back",     id="sd-back-btn")
                        yield Button("Cancel",     id="sd-cancel-btn",   classes="-danger")
                        yield Button("Continue →", id="sd-continue-btn", disabled=True)

    def on_mount(self) -> None:
        if self._prefill:
            mortal_id, _, _ = self._prefill
            if mortal_id in self._mortal_ids:
                self.query_one("#sd-mortal-list", ListView).index = self._mortal_ids.index(mortal_id)
            m = self._state.mortals.get(mortal_id)
            if m:
                self.query_one("#sd-mortal-label", Label).update(f"Mortal: {m.name}")
            ireg = get_imago_registry()
            if self._domain_a:
                self.query_one("#sd-domain-label-a", Label).update(
                    f"Domain: {_domain_display_name(self._domain_a)}"
                )
                if self._imago_a:
                    node = ireg.get_node(self._imago_a)
                    self.query_one("#sd-imago-label-a", Label).update(
                        f"Imāgō: {node.name if node else self._imago_a}"
                    )
                    self.query_one("#sd-tabs", TabbedContent).get_tab("sd-tab-a").label = \
                        self._tab_label("1", self._domain_a, self._imago_a)
            if self._domain_b:
                self.query_one("#sd-domain-label-b", Label).update(
                    f"Domain: {_domain_display_name(self._domain_b)}"
                )
                if self._imago_b:
                    node = ireg.get_node(self._imago_b)
                    self.query_one("#sd-imago-label-b", Label).update(
                        f"Imāgō: {node.name if node else self._imago_b}"
                    )
                    self.query_one("#sd-tabs", TabbedContent).get_tab("sd-tab-b").label = \
                        self._tab_label("2", self._domain_b, self._imago_b)
            self._restore_prefill_trees()
        elif self._mortal_ids:
            self._mortal_id = self._mortal_ids[0]
            m = self._state.mortals.get(self._mortal_id)
            if m:
                self.query_one("#sd-mortal-label", Label).update(f"Mortal: {m.name}")
        self._check_continue()

    def _check_continue(self) -> None:
        ready = bool(self._mortal_id and self._imago_a and self._imago_b)
        btn   = self.query_one("#sd-continue-btn", Button)
        btn.disabled = not ready
        if ready:
            btn.add_class("continue-ready")
        else:
            btn.remove_class("continue-ready")

    def _tab_label(self, slot: str, domain_tag: str | None, imago_node_id: str | None) -> str:
        if domain_tag is None:
            return f"Domain {slot}: Imāgō {slot}"
        domain_name = _domain_display_name(domain_tag)
        if imago_node_id is None:
            return f"{domain_name}: Imāgō {slot}"
        ireg = get_imago_registry()
        node = ireg.get_node(imago_node_id)
        raw_name = node.name if node else imago_node_id
        imago_name = raw_name.removeprefix("The ")
        return f"{domain_name}: {imago_name}"

    def _set_domain_excluded(self, grid_id: str, excluded_tag: str | None, prev_excluded_tag: str | None) -> None:
        grid = self.query_one(f"#{grid_id}", Grid)
        for sq in grid.query(DomainSquare):
            if sq._tag == excluded_tag:
                sq.disabled = True
                sq.add_class("inactive")
            elif sq._tag == prev_excluded_tag and sq._tag in self._eligible_tags:
                sq.disabled = False
                sq.remove_class("inactive")

    def action_nav_domain(self, direction: str) -> None:
        for grid_id in ("shape-dream-domain-grid-a", "shape-dream-domain-grid-b"):
            squares = list(self.query_one(f"#{grid_id}", Grid).query(DomainSquare))
            if any(sq.has_focus for sq in squares):
                _nav_domain_grid(squares, direction)
                return

    @work
    async def _select_slot_domain(self, slot: str, tag: str) -> None:
        """slot is 'a' or 'b'."""
        other    = "b" if slot == "a" else "a"
        slot_num = "1" if slot == "a" else "2"
        prev = getattr(self, f"_domain_{slot}")
        setattr(self, f"_domain_{slot}", tag)
        setattr(self, f"_imago_{slot}", None)
        self.query_one(f"#sd-domain-label-{slot}", Label).update(f"Domain: {_domain_display_name(tag)}")
        self.query_one(f"#sd-imago-label-{slot}",  Label).update("Imāgō: —")
        self.query_one("#sd-tabs", TabbedContent).get_tab(f"sd-tab-{slot}").label = \
            self._tab_label(slot_num, tag, None)
        self._set_domain_excluded(f"shape-dream-domain-grid-{other}", tag, prev)
        self._check_continue()
        container_id = f"shape-dream-tree-container-{slot}"
        tree      = tag.split(":", 1)[1]
        container = self.query_one(f"#{container_id}", ScrollableContainer)
        await container.remove_children()
        await container.mount(ImagoTreeGrid(self._state, tree))
        cells = [c for c in container.query(ImagoCell) if c._unlocked]
        if cells:
            cells[0].focus()

    @work
    async def _restore_prefill_trees(self) -> None:
        if self._domain_a:
            tree = self._domain_a.split(":", 1)[1]
            container = self.query_one("#shape-dream-tree-container-a", ScrollableContainer)
            await container.remove_children()
            await container.mount(ImagoTreeGrid(self._state, tree))
        if self._domain_b:
            tree = self._domain_b.split(":", 1)[1]
            container = self.query_one("#shape-dream-tree-container-b", ScrollableContainer)
            await container.remove_children()
            await container.mount(ImagoTreeGrid(self._state, tree))
        if self._domain_a and self._domain_b:
            self._set_domain_excluded("shape-dream-domain-grid-b", self._domain_a, None)
            self._set_domain_excluded("shape-dream-domain-grid-a", self._domain_b, None)

    def on_key(self, event) -> None:
        focused = self.focused
        if event.key == "tab":
            if isinstance(focused, ListView):
                squares_a = [sq for sq in self.query_one("#shape-dream-domain-grid-a", Grid).query(DomainSquare) if not sq.disabled]
                if squares_a:
                    squares_a[0].focus()
                event.prevent_default(); event.stop()
            elif isinstance(focused, DomainSquare):
                grid_a = self.query_one("#shape-dream-domain-grid-a", Grid)
                slot   = "a" if grid_a in focused.ancestors_with_self else "b"
                self._select_slot_domain(slot, focused._tag)
                event.prevent_default(); event.stop()
            elif isinstance(focused, ImagoCell):
                container_a = self.query_one("#shape-dream-tree-container-a", ScrollableContainer)
                if container_a in focused.ancestors_with_self:
                    self.query_one("#sd-tabs", TabbedContent).active = "sd-tab-b"
                    squares_b = [sq for sq in self.query_one("#shape-dream-domain-grid-b", Grid).query(DomainSquare) if not sq.disabled]
                    if squares_b:
                        squares_b[0].focus()
                else:
                    self.query_one("#sd-back-btn", Button).focus()
                event.prevent_default(); event.stop()
            elif isinstance(focused, Button) and focused.id == "sd-continue-btn":
                self.query_one("#sd-mortal-list", ListView).focus()
                event.prevent_default(); event.stop()
        elif event.key == "shift+tab":
            if isinstance(focused, ListView):
                self.query_one("#sd-continue-btn", Button).focus()
                event.prevent_default(); event.stop()
            elif isinstance(focused, DomainSquare):
                grid_a = self.query_one("#shape-dream-domain-grid-a", Grid)
                if grid_a in focused.ancestors_with_self:
                    self.query_one("#sd-mortal-list", ListView).focus()
                else:
                    self.query_one("#sd-tabs", TabbedContent).active = "sd-tab-a"
                    cells_a = [c for c in self.query_one("#shape-dream-tree-container-a", ScrollableContainer).query(ImagoCell) if c._unlocked]
                    if cells_a:
                        cells_a[0].focus()
                    else:
                        squares_a = [sq for sq in self.query_one("#shape-dream-domain-grid-a", Grid).query(DomainSquare) if not sq.disabled]
                        if squares_a:
                            squares_a[0].focus()
                event.prevent_default(); event.stop()
            elif isinstance(focused, ImagoCell):
                container_a = self.query_one("#shape-dream-tree-container-a", ScrollableContainer)
                if container_a in focused.ancestors_with_self:
                    prev_a = self._domain_a
                    self._domain_a = None
                    self._imago_a  = None
                    self.query_one("#sd-domain-label-a", Label).update("Domain: —")
                    self.query_one("#sd-imago-label-a",  Label).update("Imāgō: —")
                    self.query_one("#sd-tabs", TabbedContent).get_tab("sd-tab-a").label = \
                        self._tab_label("1", None, None)
                    self._set_domain_excluded("shape-dream-domain-grid-b", None, prev_a)
                    self._check_continue()
                    squares_a = [sq for sq in self.query_one("#shape-dream-domain-grid-a", Grid).query(DomainSquare) if not sq.disabled]
                    if squares_a:
                        squares_a[0].focus()
                else:
                    prev_b = self._domain_b
                    self._domain_b = None
                    self._imago_b  = None
                    self.query_one("#sd-domain-label-b", Label).update("Domain: —")
                    self.query_one("#sd-imago-label-b",  Label).update("Imāgō: —")
                    self.query_one("#sd-tabs", TabbedContent).get_tab("sd-tab-b").label = \
                        self._tab_label("2", None, None)
                    self._set_domain_excluded("shape-dream-domain-grid-a", None, prev_b)
                    self._check_continue()
                    squares_b = [sq for sq in self.query_one("#shape-dream-domain-grid-b", Grid).query(DomainSquare) if not sq.disabled]
                    if squares_b:
                        squares_b[0].focus()
                event.prevent_default(); event.stop()
            elif isinstance(focused, Button) and focused.id == "sd-back-btn":
                cells_b = [c for c in self.query_one("#shape-dream-tree-container-b", ScrollableContainer).query(ImagoCell) if c._unlocked]
                if cells_b:
                    self.query_one("#sd-tabs", TabbedContent).active = "sd-tab-b"
                    cells_b[0].focus()
                event.prevent_default(); event.stop()

    @on(ListView.Highlighted, "#sd-mortal-list")
    def _on_mortal_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item is None:
            return
        idx = int(event.item.id.split("-", 2)[2])
        self._mortal_id = self._mortal_ids[idx]
        m = self._state.mortals.get(self._mortal_id)
        if m:
            self.query_one("#sd-mortal-label", Label).update(f"Mortal: {m.name}")
        self._check_continue()

    def on_domain_square_focused(self, event: DomainSquare.Focused) -> None:
        grid_a = self.query_one("#shape-dream-domain-grid-a", Grid)
        slot   = "a" if grid_a in event._sender.ancestors_with_self else "b"
        self.query_one(f"#sd-domain-label-{slot}", Label).update(
            f"Domain: {_domain_display_name(event.tag)}"
        )

    def on_domain_square_selected(self, event: DomainSquare.Selected) -> None:
        grid_a   = self.query_one("#shape-dream-domain-grid-a", Grid)
        slot     = "a" if grid_a in event._sender.ancestors_with_self else "b"
        other    = "b" if slot == "a" else "a"
        slot_num = "1" if slot == "a" else "2"
        prev = getattr(self, f"_domain_{slot}")
        setattr(self, f"_domain_{slot}", event.tag)
        setattr(self, f"_imago_{slot}", None)
        self.query_one(f"#sd-domain-label-{slot}", Label).update(
            f"Domain: {_domain_display_name(event.tag)}"
        )
        self.query_one(f"#sd-imago-label-{slot}", Label).update("Imāgō: —")
        self.query_one("#sd-tabs", TabbedContent).get_tab(f"sd-tab-{slot}").label = \
            self._tab_label(slot_num, event.tag, None)
        self._set_domain_excluded(f"shape-dream-domain-grid-{other}", event.tag, prev)
        self._swap_imago_tree(f"shape-dream-tree-container-{slot}", event.tag)
        self._check_continue()

    def on_imago_cell_focused(self, event: ImagoCell.Focused) -> None:
        container_a = self.query_one("#shape-dream-tree-container-a", ScrollableContainer)
        in_tab_a = container_a in event._sender.ancestors_with_self
        ireg = get_imago_registry()
        node = ireg.get_node(event.node_id)
        name = node.name if node else event.node_id
        if in_tab_a:
            self._imago_a = event.node_id
            self.query_one("#sd-imago-label-a", Label).update(f"Imāgō: {name}")
            self.query_one("#sd-tabs", TabbedContent).get_tab("sd-tab-a").label = \
                self._tab_label("1", self._domain_a, self._imago_a)
        else:
            self._imago_b = event.node_id
            self.query_one("#sd-imago-label-b", Label).update(f"Imāgō: {name}")
            self.query_one("#sd-tabs", TabbedContent).get_tab("sd-tab-b").label = \
                self._tab_label("2", self._domain_b, self._imago_b)
        self._check_continue()

    def on_imago_cell_selected(self, event: ImagoCell.Selected) -> None:
        container_a = self.query_one("#shape-dream-tree-container-a", ScrollableContainer)
        in_tab_a = container_a in event._sender.ancestors_with_self

        ireg = get_imago_registry()
        node = ireg.get_node(event.node_id)
        name = node.name if node else event.node_id

        if in_tab_a:
            self._imago_a = event.node_id
            self.query_one("#sd-imago-label-a", Label).update(f"Imāgō: {name}")
            self.query_one("#sd-tabs", TabbedContent).get_tab("sd-tab-a").label = \
                self._tab_label("1", self._domain_a, self._imago_a)
        else:
            self._imago_b = event.node_id
            self.query_one("#sd-imago-label-b", Label).update(f"Imāgō: {name}")
            self.query_one("#sd-tabs", TabbedContent).get_tab("sd-tab-b").label = \
                self._tab_label("2", self._domain_b, self._imago_b)

        self._check_continue()
        if self._mortal_id and self._imago_a and self._imago_b:
            self.dismiss((self._mortal_id, self._imago_a, self._imago_b))

    @on(Button.Pressed, "#sd-continue-btn")
    def _on_continue(self, _: Button.Pressed) -> None:
        if self._mortal_id and self._imago_a and self._imago_b:
            self.dismiss((self._mortal_id, self._imago_a, self._imago_b))

    @on(Button.Pressed, "#sd-back-btn")
    def _on_back(self, _: Button.Pressed) -> None:
        self.dismiss(BACK)

    @on(Button.Pressed, "#sd-cancel-btn")
    def _on_cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_back(self) -> None:
        self.dismiss(BACK)

