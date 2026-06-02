"""
All modal screens used by the Demiurge TUI. Each modal is a self-contained
ModalScreen subclass; they communicate with callers by being pushed via
push_screen_wait() and returning a value from dismiss().
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Iterable, Optional

from rich.markup import escape as _e
from rich.text import Text
from textual import on, work
from textual.binding import Binding
from textual.message import Message
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, Grid, ScrollableContainer
from textual.screen import ModalScreen
from textual.widgets import (
    Button, Checkbox, Input, Label, ListItem, ListView,
    RadioButton, RadioSet, RichLog, Static,
    TabbedContent, Tab, TabPane,
)
from textual_slider import Slider as _Slider

from core.action_core import (
    ActionCategory, ActionDefinition, OngoingAction, compute_cooldown,
    RevealImagoIntent, ChangeAffiliatedDomainsIntent,
    ScryScope, TargetType, CATEGORY_BASE_COOLDOWNS,
)
from logic.tick_logic import (
    SimulationState,
    _compute_revelation_cap, _revelation_adjusted_cost,
    ENTITY_VISIBILITY_FLOOR, is_in_window,
    SCRY_FP_BASE, SCRY_FP_WORLD_MOM, SCRY_ESSENCE,
)
from utilities.culture_registry import is_culture_tag
from utilities.domain_registry import get_registry as get_domain_registry
from utilities.imago_registry import get_registry as get_imago_registry, ImagoNode

from ui.display import _get_lum_domain_context, _wrap_desc, _short_tag, _pop_stratum_label

from ui.widgets import DomainSquare, ImagoCell, ImagoRevealCell, ImagoTreeGrid, LoopingListView, ScopeChip
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
                yield Button("✕ Cancel", id="cancel-btn", classes="-danger")

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
                yield Button("✕ Cancel", id="cancel-btn", classes="-danger")

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
                yield Button("✕ Cancel",  id="cancel-btn", classes="-danger")
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
                yield Button("✕ Cancel",      id="cancel-btn", classes="-danger")

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
        initial: tuple | None = None,
    ) -> None:
        super().__init__()
        self._state             = state
        self._initial_selection = initial          # (tag, t1_one, t1_both, t2_one, t2_both, t3_one, t3_both)
        self._selected_tag: str | None = initial[0] if initial else None

        dreg = get_domain_registry()
        lum_info, fellow_tags, _ = _get_lum_domain_context(state)

        accessible_set = set(dreg.all_tags)
        if capped_domains:
            accessible_set -= capped_domains

        self._dreg           = dreg
        self._lum_info       = lum_info
        self._fellow_tags    = fellow_tags
        self._accessible_set = accessible_set
        self._selected_domain_widget: "DomainSquare | None" = None

        first_tag = initial[0] if initial else next(iter(sorted(accessible_set)), None)
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
                            yield RadioButton("One T1 unlockable",   id="stop-t1-one",  value=False, disabled=True)
                            yield RadioButton("Both T1s unlockable", id="stop-t1-both", value=False, disabled=True)
                            yield RadioButton("One T2 unlockable",   id="stop-t2-one",  value=False, disabled=True)
                            yield RadioButton("Both T2s unlockable", id="stop-t2-both", value=False, disabled=True)
                            yield RadioButton("One T3 unlockable",   id="stop-t3-one",  value=False, disabled=True)
                            yield RadioButton("Both T3s unlockable", id="stop-t3-both", value=False, disabled=True)
                        yield RadioButton("Revelation cap reached", id="stop-cap", value=True, disabled=True)
                    with Horizontal(classes="btn-row"):
                        yield Button("← Back",  id="back-btn")
                        yield Button("✕ Cancel",  id="cancel-btn", classes="-danger")
                        yield Button("Continue →", id="confirm-btn", disabled=True)
                with Vertical(id="explore-right"):
                    yield Label("— Imāgō reference —", classes="explore-ref-title")
                    yield Static("", id="imago-ref-pool")
                    yield ImagoTreeGrid(self._state, self._initial_tree, readonly=True)
                    yield Static("", id="imago-ref-tooltip")

    def on_mount(self) -> None:
        if self._initial_selection:
            tag, t1_one, t1_both, t2_one, t2_both, t3_one, t3_both = self._initial_selection
            for sq in self.query(DomainSquare):
                if sq._tag == tag and not sq.disabled:
                    sq.focus()
                    self._mark_domain_selected(sq)
                    break
            for cb_id, val in [
                ("#stop-t1-one",  t1_one),
                ("#stop-t1-both", t1_both),
                ("#stop-t2-one",  t2_one),
                ("#stop-t2-both", t2_both),
                ("#stop-t3-one",  t3_one),
                ("#stop-t3-both", t3_both),
            ]:
                self.query_one(cb_id, RadioButton).value = val
        else:
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
        focused_cb = next((cb for cb in self.query(RadioButton) if cb.has_focus), None)
        if focused_cb is not None:
            entry = next((e for e in self._CB_GRID if e[0] == focused_cb.id), None)
            if entry:
                _, row, col = entry
                dr, dc = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}[direction]
                r, c = row + dr, col + dc
                while 0 <= r < 3 and 0 <= c < 2:
                    target_id = next((e[0] for e in self._CB_GRID if e[1] == r and e[2] == c), None)
                    if target_id:
                        cb = self.query_one(f"#{target_id}", RadioButton)
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
                self._selected_tag = focused_sq._tag
                self._mark_domain_selected(focused_sq)
                self._check_confirm()
                self._focus_first_checkbox()
                return
            focused_cb = next((cb for cb in self.query(RadioButton) if cb.has_focus), None)
            if focused_cb is not None:
                event.prevent_default(); event.stop()
                self.query_one("#back-btn", Button).focus()
                return
        elif event.key == "shift+tab":
            focused_sq = next((sq for sq in self.query(DomainSquare) if sq.has_focus), None)
            if focused_sq is not None:
                event.prevent_default(); event.stop()
                return
            focused_cb = next((cb for cb in self.query(RadioButton) if cb.has_focus), None)
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
            cb = self.query_one(f"#{cb_id}", RadioButton)
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

    def _render_domain_preview(self, tag: str | None) -> None:
        if tag is None:
            self.query_one("#domain-label", Static).update("Domain: —")
            self.query_one("#lum-panel", Static).update("")
            self.query_one("#imago-ref-pool", Static).update("")
            return
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
        tree  = tag.split(":", 1)[1] if ":" in tag else tag
        rcap  = _compute_revelation_cap(self._state, tag)
        cap_s = f"{rcap:.0f}" if rcap > 0.0 else "∞"
        self.query_one("#imago-ref-pool", Static).update(
            f"Revelation: {pool:.0f} / {cap_s}"
        )
        self.query_one(ImagoTreeGrid).load_tree(tree)
        self.query_one("#imago-ref-tooltip", Static).update("")

    def _mark_domain_selected(self, sq: "DomainSquare") -> None:
        if self._selected_domain_widget is not None:
            self._selected_domain_widget.remove_class("selected-active")
        self._selected_domain_widget = sq
        sq.add_class("selected-active")

    def _check_confirm(self) -> None:
        btn = self.query_one("#confirm-btn", Button)
        if self._selected_tag:
            btn.disabled = False
            btn.add_class("continue-ready")
        else:
            btn.disabled = True
            btn.remove_class("continue-ready")

    def on_domain_square_focused(self, event: DomainSquare.Focused) -> None:
        self._render_domain_preview(event.tag)

    def on_domain_square_blurred(self, event: DomainSquare.Blurred) -> None:
        self._render_domain_preview(self._selected_tag)

    def _update_checkbox_states(self, tag: str) -> None:
        ireg = get_imago_registry()
        tree = tag.split(":", 1)[1] if ":" in tag else tag
        unlocked = set(self._state.demiurge.unlocked_imagines)
        nodes = ireg.nodes_for_tree(tree)
        for tier in (1, 2, 3):
            remaining = sum(1 for n in nodes if n.tier == tier and n.node_id not in unlocked)
            cb_one  = self.query_one(f"#stop-t{tier}-one",  RadioButton)
            cb_both = self.query_one(f"#stop-t{tier}-both", RadioButton)
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

    @on(RadioButton.Changed)
    def _autostop_changed(self, event: RadioButton.Changed) -> None:
        cb_ids = {e[0] for e in self._CB_GRID}
        if event.radio_button.id not in cb_ids or self._updating_checkboxes or not event.value:
            return
        self._updating_checkboxes = True
        try:
            for cb_id, _, _ in self._CB_GRID:
                if cb_id != event.radio_button.id:
                    self.query_one(f"#{cb_id}", RadioButton).value = False
        finally:
            self._updating_checkboxes = False

    def on_domain_square_selected(self, event: DomainSquare.Selected) -> None:
        self._selected_tag = event.tag
        sq = next((s for s in self.query(DomainSquare) if s._tag == event.tag), None)
        if sq:
            self._mark_domain_selected(sq)
        self._check_confirm()
        self.query_one("#confirm-btn", Button).focus()

    def _do_confirm(self) -> None:
        if self._selected_tag:
            self.dismiss((
                self._selected_tag,
                self.query_one("#stop-t1-one",  RadioButton).value,
                self.query_one("#stop-t1-both", RadioButton).value,
                self.query_one("#stop-t2-one",  RadioButton).value,
                self.query_one("#stop-t2-both", RadioButton).value,
                self.query_one("#stop-t3-one",  RadioButton).value,
                self.query_one("#stop-t3-both", RadioButton).value,
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
# EXPLORE BELIEFS CONFIRM MODAL
# ─────────────────────────────────────────

class ExploreBeliefConfirmModal(ModalScreen):
    """
    Confirmation screen for Explore Beliefs.
    Shows domain name, revelation pool/cap, and the active auto-stop condition.
    Dismisses with True (confirm), False (back to config), or None (cancel).
    """

    BINDINGS = [
        ("escape",    "force_cancel", "Cancel"),
        ("backspace", "back",         "Back"),
    ]

    def __init__(
        self,
        state: SimulationState,
        tag: str,
        t1_one: bool, t1_both: bool,
        t2_one: bool, t2_both: bool,
        t3_one: bool, t3_both: bool,
    ) -> None:
        super().__init__()
        self._state = state
        self._tag   = tag
        self._stops = (t1_one, t1_both, t2_one, t2_both, t3_one, t3_both)

    def _body(self) -> Text:
        tag   = self._tag
        pool  = self._state.demiurge.revelation_pools.get(tag, 0.0)
        cap   = _compute_revelation_cap(self._state, tag)
        cap_s = f"{cap:.0f}" if cap > 0.0 else "∞"
        name  = _domain_display_name(tag)

        t1_one, t1_both, t2_one, t2_both, t3_one, t3_both = self._stops
        stop_map = [
            (t1_one,  "one Tier 1 node becomes unlockable"),
            (t1_both, "both Tier 1 nodes become unlockable"),
            (t2_one,  "one Tier 2 node becomes unlockable"),
            (t2_both, "both Tier 2 nodes become unlockable"),
            (t3_one,  "one Tier 3 node becomes unlockable"),
            (t3_both, "both Tier 3 nodes become unlockable"),
        ]
        active = [label for val, label in stop_map if val]

        lines: list[str] = [
            f"[bold #c0ccdc]{_e(name)}[/]",
            f"[#5a7090]Revelation: {pool:.0f} / {cap_s}[/]",
            "",
        ]
        if active:
            lines.append("[bold #5a7090]WILL AUTO-STOP WHEN[/]")
            for label in active:
                lines.append(f"  [#c0ccdc]· {label}[/]")
        else:
            lines.append(
                "[#5a7090]No auto-stop condition — will run until the Revelation cap.[/]"
            )
        return Text.from_markup("\n".join(lines))

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box"):
            yield Label("Explore Beliefs — Confirm", classes="modal-title")
            yield Static(self._body())
            with Horizontal(classes="btn-row"):
                yield Button("← Back",  id="back-btn")
                yield Button("✕ Cancel",  id="cancel-btn",  classes="-danger")
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
    def _cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_back(self) -> None:
        self.dismiss(False)

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
                yield Button("✕ Cancel",    id="cancel-btn",  classes="-danger")

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
                yield Button("✕ Cancel",  id="cancel-btn",  classes="-danger")
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
                yield Button("✕ Cancel",  id="cancel-btn",  classes="-danger")
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

class NoUnlockableModal(ModalScreen):
    """
    Shown when the player selects Reveal Imāgō but no nodes are currently unlockable.
    Dismisses with "explore_beliefs" (route to Explore Beliefs), BACK, or None (cancel).
    """

    BINDINGS = [
        ("escape",    "force_cancel", "Cancel"),
        ("backspace", "go_back",      "Back"),
    ]

    def compose(self) -> "ComposeResult":
        with Vertical(classes="modal-box"):
            yield Label("No Unlockable Imāgō", classes="modal-title")
            yield Static(
                "There are no Imāgō nodes available to reveal right now.\n"
                "You may not have met the prerequisites, or your Revelation pools\n"
                "may be empty. Explore Beliefs to build up Revelation.",
                id="no-unlock-body",
            )
            with Horizontal(classes="btn-row"):
                yield Button("← Back",         id="back-btn")
                yield Button("✕ Cancel",          id="cancel-btn",   classes="-danger")
                yield Button("Explore Beliefs", id="explore-btn",  classes="-primary")

    def on_mount(self) -> None:
        self.query_one("#explore-btn", Button).focus()

    @on(Button.Pressed, "#explore-btn")
    def _explore(self, _: Button.Pressed) -> None:
        self.dismiss("explore_beliefs")

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


class RevealImagoConfigModal(ModalScreen):
    """
    Single-screen Reveal Imāgō configuration.
    Domain grid (2×8, symbol-only) → ImagoRevealCell tree → confirm.
    Dismisses with RevealImagoIntent, BACK, or None.
    """

    BINDINGS = [
        ("escape",    "force_cancel", "Cancel"),
        ("backspace", "go_back",      "Back"),
    ]

    _POSITIONS = [(0, 1), (1, 0), (1, 2), (2, 0), (2, 2), (3, 0), (3, 2)]

    def __init__(self, state: "SimulationState", initial: "tuple[str, str] | None" = None) -> None:
        super().__init__()
        self._state       = state
        self._dreg        = get_domain_registry()
        self._initial     = initial                  # (domain_tag, node_id)
        self._domain_tag: "str | None" = initial[0] if initial else None
        self._node_id:    "str | None" = initial[1] if initial else None

        self._accessible_tags: "set[str]" = {
            tag for tag in self._dreg.all_tags
            if _compute_revelation_cap(state, tag) > 0.0
        }
        self._eligible_reveal_tags = _eligible_reveal_domain_tags(state)
        self._selected_domain_widget: "DomainSquare | None"      = None
        self._selected_imago_widget:  "ImagoRevealCell | None"   = None

        first_accessible = next(iter(sorted(self._accessible_tags)), None)
        self._initial_tree = (
            first_accessible.split(":", 1)[1]
            if first_accessible and ":" in first_accessible
            else "fire"
        )

    def compose(self) -> "ComposeResult":
        with Vertical(classes="reveal-imago-modal"):
            yield Label("Reveal Imāgō", classes="modal-title")
            yield Label("Domain: —", id="domain-label")
            with Grid(id="reveal-domain-grid"):
                yield from _domain_grid_squares(
                    self._state, self._dreg, self._accessible_tags,
                    eligible_reveal_tags=self._eligible_reveal_tags,
                )
            yield Label("Imāgō: —", id="imago-label")
            yield ImagoTreeGrid(self._state, self._initial_tree, readonly=True)
            with ScrollableContainer(id="reveal-tree-container"):
                pass
            with Horizontal(classes="btn-row"):
                yield Button("← Back",    id="back-btn")
                yield Button("✕ Cancel",    id="cancel-btn",  classes="-danger")
                yield Button("Continue →", id="confirm-btn", classes="-primary", disabled=True)

    def on_mount(self) -> None:
        if self._initial:
            domain_tag, node_id = self._initial
            self.query_one(ImagoTreeGrid).display = False
            self.query_one("#domain-label", Label).update(
                f"Domain: {_domain_display_name(domain_tag)}"
            )
            for sq in self.query(DomainSquare):
                if sq._tag == domain_tag and not sq.disabled:
                    sq.focus()
                    break
            self._load_reveal_tree(domain_tag, initial_node_id=node_id)
        else:
            self.query_one("#reveal-tree-container", ScrollableContainer).display = False
            for sq in self.query(DomainSquare):
                if not sq.disabled:
                    sq.focus()
                    break

    def _nav_imago_tree(self, direction: str) -> None:
        cells = list(self.query(ImagoRevealCell))
        if not cells:
            return
        focused_idx = next((i for i, c in enumerate(cells) if c.has_focus), -1)
        if focused_idx == -1:
            return
        pos_map = {i: p for i, p in enumerate(self._POSITIONS)}
        cur_pos = pos_map.get(focused_idx, (0, 1))
        dr, dc  = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}[direction]
        r, c    = cur_pos[0] + dr, cur_pos[1] + dc
        while 0 <= r <= 3 and 0 <= c <= 2:
            for i, p in pos_map.items():
                if p == (r, c) and not cells[i].disabled:
                    cells[i].focus()
                    return
            r, c = r + dr, c + dc

    def on_key(self, event) -> None:
        focused = self.focused
        if event.key in ("up", "down", "left", "right"):
            if isinstance(focused, DomainSquare):
                squares = list(self.query(DomainSquare))
                _nav_domain_grid(squares, event.key)
                event.prevent_default(); event.stop()
            elif isinstance(focused, ImagoRevealCell):
                self._nav_imago_tree(event.key)
                event.prevent_default(); event.stop()
            return
        if event.key == "tab":
            if isinstance(focused, DomainSquare):
                tag = focused._tag
                self._domain_tag = tag
                self._node_id    = None
                self.query_one("#domain-label", Label).update(
                    f"Domain: {_domain_display_name(tag)}"
                )
                self.query_one("#imago-label", Label).update("Imāgō: —")
                if self._selected_imago_widget is not None:
                    if self._selected_imago_widget.parent is not None:
                        self._selected_imago_widget.remove_class("selected-active")
                    self._selected_imago_widget = None
                self._mark_domain_selected(focused)
                self._check_confirm()
                self._switch_to_interactive()
                self._load_reveal_tree(tag, focus_first=True)
                event.prevent_default(); event.stop()
            elif isinstance(focused, ImagoRevealCell) and not focused.disabled:
                node_id = focused._node.node_id
                self._node_id = node_id
                ireg = get_imago_registry()
                node = ireg.get_node(node_id)
                name = node.name if node else node_id
                self.query_one("#imago-label", Label).update(f"Imāgō: {name}")
                self._mark_imago_selected(focused)
                self._check_confirm()
                self.query_one("#back-btn", Button).focus()
                event.prevent_default(); event.stop()
            elif isinstance(focused, Button) and focused.id == "cancel-btn":
                confirm = self.query_one("#confirm-btn", Button)
                if not confirm.disabled:
                    confirm.focus()
                event.prevent_default(); event.stop()
            elif isinstance(focused, Button) and focused.id == "confirm-btn":
                squares = list(self.query(DomainSquare))
                target  = next((sq for sq in squares if not sq.disabled), None)
                if target:
                    target.focus()
                event.prevent_default(); event.stop()
        elif event.key == "enter":
            if isinstance(focused, ImagoRevealCell) and not focused.disabled:
                node_id = focused._node.node_id
                if self._domain_tag:
                    self.dismiss((self._domain_tag, node_id))
                event.prevent_default(); event.stop()
        elif event.key == "shift+tab":
            if isinstance(focused, DomainSquare):
                self.query_one("#confirm-btn", Button).focus()
                event.prevent_default(); event.stop()
            elif isinstance(focused, Button) and focused.id == "back-btn":
                cells  = [c for c in self.query(ImagoRevealCell) if not c.disabled]
                if cells:
                    cells[0].focus()
                event.prevent_default(); event.stop()
            elif isinstance(focused, ImagoRevealCell):
                squares = list(self.query(DomainSquare))
                target  = next((sq for sq in squares if not sq.disabled), None)
                if target:
                    target.focus()
                event.prevent_default(); event.stop()

    def _switch_to_interactive(self) -> None:
        preview = self.query_one(ImagoTreeGrid)
        if preview.display:
            preview.display = False
            self.query_one("#reveal-tree-container", ScrollableContainer).display = True

    def _mark_domain_selected(self, sq: "DomainSquare") -> None:
        if self._selected_domain_widget is not None:
            self._selected_domain_widget.remove_class("selected-active")
        self._selected_domain_widget = sq
        sq.add_class("selected-active")

    def _mark_imago_selected(self, cell: "ImagoRevealCell") -> None:
        if self._selected_imago_widget is not None:
            self._selected_imago_widget.remove_class("selected-active")
        self._selected_imago_widget = cell
        cell.add_class("selected-active")

    def on_domain_square_focused(self, event: "DomainSquare.Focused") -> None:
        self.query_one("#domain-label", Label).update(
            f"Domain: {_domain_display_name(event.tag)}"
        )
        if self._domain_tag is None:
            tree = event.tag.split(":", 1)[1] if ":" in event.tag else event.tag
            self.query_one(ImagoTreeGrid).load_tree(tree)

    def on_domain_square_blurred(self, event: "DomainSquare.Blurred") -> None:
        if self._domain_tag:
            self.query_one("#domain-label", Label).update(
                f"Domain: {_domain_display_name(self._domain_tag)}"
            )
        else:
            self.query_one("#domain-label", Label).update("Domain: —")
            self.query_one(ImagoTreeGrid).load_tree(self._initial_tree)

    def on_domain_square_selected(self, event: "DomainSquare.Selected") -> None:
        tag              = event.tag
        self._domain_tag = tag
        self._node_id    = None
        self.query_one("#domain-label", Label).update(
            f"Domain: {_domain_display_name(tag)}"
        )
        self.query_one("#imago-label", Label).update("Imāgō: —")
        if self._selected_imago_widget is not None:
            if self._selected_imago_widget.parent is not None:
                self._selected_imago_widget.remove_class("selected-active")
            self._selected_imago_widget = None
        self._mark_domain_selected(event._sender)
        self._check_confirm()
        self._switch_to_interactive()
        self._load_reveal_tree(tag)

    def on_imago_reveal_cell_focused(self, event: "ImagoRevealCell.Focused") -> None:
        ireg = get_imago_registry()
        node = ireg.get_node(event.node_id)
        name = node.name if node else event.node_id
        self.query_one("#imago-label", Label).update(f"Imāgō: {name}")

    def on_imago_reveal_cell_blurred(self, event: "ImagoRevealCell.Blurred") -> None:
        if self._node_id:
            ireg = get_imago_registry()
            node = ireg.get_node(self._node_id)
            name = node.name if node else self._node_id
            self.query_one("#imago-label", Label).update(f"Imāgō: {name}")
        else:
            self.query_one("#imago-label", Label).update("Imāgō: —")

    def on_imago_reveal_cell_selected(self, event: "ImagoRevealCell.Selected") -> None:
        self._node_id = event.node_id
        ireg = get_imago_registry()
        node = ireg.get_node(event.node_id)
        name = node.name if node else event.node_id
        self.query_one("#imago-label", Label).update(f"Imāgō: {name}")
        self._mark_imago_selected(event._sender)
        self._check_confirm()

    def _check_confirm(self) -> None:
        ready = bool(self._domain_tag and self._node_id)
        btn   = self.query_one("#confirm-btn", Button)
        btn.disabled = not ready
        if ready:
            btn.add_class("continue-ready")
        else:
            btn.remove_class("continue-ready")

    @work(exclusive=True)
    async def _load_reveal_tree(self, tag: str, *, focus_first: bool = False, initial_node_id: "str | None" = None) -> None:
        tree      = tag.split(":", 1)[1]
        ireg      = get_imago_registry()
        nodes     = ireg.nodes_for_tree(tree)
        rev_count = self._state.demiurge.revealed_imagines

        by_tier: "dict[int, list]" = {1: [], 2: [], 3: [], 4: []}
        for n in nodes:
            by_tier[n.tier].append(n)

        container = self.query_one("#reveal-tree-container", ScrollableContainer)
        self._selected_imago_widget = None
        await container.remove_children()

        cells_and_spacers: list = []
        for tier in (4, 3, 2, 1):
            tnodes = by_tier[tier]
            if tier == 4:
                cells_and_spacers.append(Static("", classes="imago-spacer"))
                node = tnodes[0]
                cells_and_spacers.append(
                    ImagoRevealCell(node, self._state, _revelation_adjusted_cost(node.tier, rev_count))
                )
                cells_and_spacers.append(Static("", classes="imago-spacer"))
            else:
                left, right = tnodes[0], tnodes[1]
                cells_and_spacers.append(
                    ImagoRevealCell(left, self._state, _revelation_adjusted_cost(left.tier, rev_count))
                )
                cells_and_spacers.append(Static("", classes="imago-spacer"))
                cells_and_spacers.append(
                    ImagoRevealCell(right, self._state, _revelation_adjusted_cost(right.tier, rev_count))
                )

        grid = Grid(classes="imago-tree-inner-grid")
        await container.mount(grid)
        await grid.mount(*cells_and_spacers)

        if tag == self._domain_tag and self._node_id:
            matched = [c for c in container.query(ImagoRevealCell) if c._node.node_id == self._node_id]
            if matched:
                self._mark_imago_selected(matched[0])

        if initial_node_id:
            matched = [c for c in container.query(ImagoRevealCell) if c._node.node_id == initial_node_id]
            if matched:
                self._node_id = initial_node_id
                ireg = get_imago_registry()
                node = ireg.get_node(initial_node_id)
                name = node.name if node else initial_node_id
                self.query_one("#imago-label", Label).update(f"Imāgō: {name}")
                self._check_confirm()
                matched[0].focus()
        elif focus_first:
            cells = [c for c in container.query(ImagoRevealCell) if not c.disabled]
            if cells:
                cells[0].focus()

    @on(Button.Pressed, "#confirm-btn")
    def _confirm(self, _: Button.Pressed) -> None:
        if self._domain_tag and self._node_id:
            self.dismiss((self._domain_tag, self._node_id))

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
# REVEAL IMĀGŌ CONFIRM MODAL
# ─────────────────────────────────────────

class RevealImagoConfirmModal(ModalScreen):
    """
    Confirmation screen for Reveal Imāgō.
    Shows full node details plus revelation cost vs pool.
    The Reveal button is disabled if the pool is no longer sufficient.
    Dismisses with True (confirm), False (back to config), or None (cancel).
    """

    BINDINGS = [
        ("escape",    "force_cancel", "Cancel"),
        ("backspace", "back",         "Back"),
    ]

    def __init__(
        self,
        state: "SimulationState",
        node: "ImagoNode",
        domain_tag: str,
    ) -> None:
        super().__init__()
        self._state      = state
        self._node       = node
        self._domain_tag = domain_tag

        rev_count        = state.demiurge.revealed_imagines
        self._cost       = _revelation_adjusted_cost(node.tier, rev_count)
        self._pool       = state.demiurge.revelation_pools.get(f"domain:{node.tree}", 0.0)
        self._affordable = self._pool >= self._cost

    def _body(self) -> "Text":
        base  = _imago_panel_body(self._node, self._state)
        col   = "#50b870" if self._affordable else "#b04050"
        extra = Text.from_markup(
            f"\n[bold #5a7090]REVELATION COST[/]\n"
            f"  [{col}]Cost: {self._cost}  ·  Pool: {self._pool:.0f}[/]"
        )
        base.append_text(extra)
        return base

    def compose(self) -> "ComposeResult":
        with Vertical(classes="modal-box-tall"):
            yield Label("Reveal Imāgō — Confirm", classes="modal-title")
            with ScrollableContainer():
                yield Static(self._body())
            with Horizontal(classes="btn-row"):
                yield Button("← Back",  id="back-btn")
                yield Button("✕ Cancel",  id="cancel-btn",  classes="-danger")
                yield Button(
                    "Reveal", id="confirm-btn", classes="-primary",
                    disabled=not self._affordable,
                )

    def on_mount(self) -> None:
        self.query_one("#confirm-btn", Button).focus()

    @on(Button.Pressed, "#confirm-btn")
    def _confirm(self, _: Button.Pressed) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#back-btn")
    def _back(self, _: Button.Pressed) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#cancel-btn")
    def _cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_back(self) -> None:
        self.dismiss(False)

    def action_force_cancel(self) -> None:
        self.dismiss(None)


class ChangeAffiliatedDomainModal(ModalScreen):
    """
    Single-screen Change Affiliated Domain configuration.
    Affiliated row (3 selectable DomainSquares + placeholder) → 4×4 new domain grid → confirm.
    First affiliated domain is pre-selected on mount.
    Dismisses with (old_tag, new_tag) tuple, BACK, or None.
    """

    BINDINGS = [
        ("escape",    "force_cancel", "Cancel"),
        ("backspace", "go_back",      "Back"),
        ("up",        "nav_new('up')",    ""),
        ("down",      "nav_new('down')",  ""),
        ("left",      "nav_new('left')",  ""),
        ("right",     "nav_new('right')", ""),
    ]

    def __init__(self, state: "SimulationState", initial: "tuple[str, str] | None" = None) -> None:
        super().__init__()
        self._state      = state
        self._dreg       = get_domain_registry()
        self._affiliated = list(state.demiurge.affiliated_domains)
        self._initial    = initial                   # (old_tag, new_tag)
        self._old_tag: "str | None" = initial[0] if initial else (self._affiliated[0] if self._affiliated else None)
        self._new_tag: "str | None" = initial[1] if initial else None

        affiliated_set = set(self._affiliated)
        self._accessible_new: "set[str]" = set(self._dreg.all_tags) - affiliated_set
        self._selected_old_widget: "DomainSquare | None" = None
        self._selected_new_widget: "DomainSquare | None" = None

    def compose(self) -> "ComposeResult":
        with Vertical(classes="change-affiliated-modal"):
            yield Label("Change Affiliated Domain", classes="modal-title")
            yield Label(
                f"Domain to Replace: {_domain_display_name(self._old_tag)}"
                if self._old_tag else "Domain to Replace: —",
                id="old-label",
            )
            with Horizontal(classes="affiliated-domain-row"):
                for tag in self._affiliated:
                    yield DomainSquare(
                        tag=tag,
                        icon=self._dreg.icon(tag),
                        name="",
                        affiliated=True,
                        accessible=True,
                    )
                yield Static("", classes="affiliated-placeholder")
            yield Label("New Domain: —", id="new-label")
            with Grid(id="new-domain-grid"):
                yield from _domain_grid_squares(
                    self._state, self._dreg, self._accessible_new, show_names=True,
                )
            with Horizontal(classes="btn-row"):
                yield Button("← Back",    id="back-btn")
                yield Button("✕ Cancel",    id="cancel-btn",  classes="-danger")
                yield Button("Continue →", id="confirm-btn", classes="-primary", disabled=True)

    def on_mount(self) -> None:
        if self._initial:
            _, new_tag = self._initial
            self.query_one("#new-label", Label).update(
                f"New Domain: {_domain_display_name(new_tag)}"
            )
            self._check_confirm()
        for sq in self.query(DomainSquare):
            if sq._tag == self._old_tag:
                sq.focus()
                self._mark_old_selected(sq)
                break

    def action_nav_new(self, direction: str) -> None:
        # Use all squares from the new-domain grid (including disabled) so positions
        # match the visual 4-column layout and disabled-skip works correctly.
        squares = list(self.query_one("#new-domain-grid", Grid).query(DomainSquare))
        if any(sq.has_focus for sq in squares):
            _nav_domain_grid(squares, direction, cols=4)

    def on_key(self, event) -> None:
        focused = self.focused
        affiliated_set = set(self._affiliated)
        aff_squares = [sq for sq in self.query(DomainSquare) if sq._tag in affiliated_set]

        if event.key in ("left", "right") and isinstance(focused, DomainSquare) and focused._tag in affiliated_set:
            dc = 1 if event.key == "right" else -1
            idx = next((i for i, sq in enumerate(aff_squares) if sq.has_focus), -1)
            if idx != -1:
                target_idx = (idx + dc) % len(aff_squares)
                aff_squares[target_idx].focus()
            event.prevent_default(); event.stop()

        elif event.key == "enter" and isinstance(focused, DomainSquare) and focused._tag not in affiliated_set and not focused.disabled:
            self._new_tag = focused._tag
            self._mark_new_selected(focused)
            self.query_one("#new-label", Label).update(
                f"New Domain: {_domain_display_name(focused._tag)}"
            )
            self._check_confirm()
            if self._old_tag and self._new_tag:
                self.dismiss((self._old_tag, self._new_tag))
            event.prevent_default(); event.stop()

        elif event.key == "tab":
            if isinstance(focused, DomainSquare) and focused._tag in affiliated_set:
                self._old_tag = focused._tag
                self._mark_old_selected(focused)
                self.query_one("#old-label", Label).update(
                    f"Domain to Replace: {_domain_display_name(focused._tag)}"
                )
                new_squares = list(self.query_one("#new-domain-grid", Grid).query(DomainSquare))
                target = next((sq for sq in new_squares if not sq.disabled), None)
                if target:
                    target.focus()
                event.prevent_default(); event.stop()
            elif isinstance(focused, DomainSquare) and focused._tag not in affiliated_set:
                if not focused.disabled:
                    self._new_tag = focused._tag
                    self._mark_new_selected(focused)
                    self.query_one("#new-label", Label).update(
                        f"New Domain: {_domain_display_name(focused._tag)}"
                    )
                    self._check_confirm()
                self.query_one("#back-btn", Button).focus()
                event.prevent_default(); event.stop()
            elif isinstance(focused, Button) and focused.id == "confirm-btn":
                if aff_squares:
                    aff_squares[0].focus()
                event.prevent_default(); event.stop()
        elif event.key == "shift+tab":
            if isinstance(focused, DomainSquare) and focused._tag in affiliated_set:
                self.query_one("#confirm-btn", Button).focus()
                event.prevent_default(); event.stop()
            elif isinstance(focused, Button) and focused.id == "back-btn":
                new_squares = list(self.query_one("#new-domain-grid", Grid).query(DomainSquare))
                target = next((sq for sq in new_squares if not sq.disabled), None)
                if target:
                    target.focus()
                event.prevent_default(); event.stop()
            elif isinstance(focused, DomainSquare) and focused._tag not in affiliated_set:
                if aff_squares:
                    aff_squares[0].focus()
                event.prevent_default(); event.stop()

    def _mark_old_selected(self, sq: "DomainSquare") -> None:
        if self._selected_old_widget is not None:
            self._selected_old_widget.remove_class("selected-active")
        self._selected_old_widget = sq
        sq.add_class("selected-active")

    def _mark_new_selected(self, sq: "DomainSquare") -> None:
        if self._selected_new_widget is not None:
            self._selected_new_widget.remove_class("selected-active")
        self._selected_new_widget = sq
        sq.add_class("selected-active")

    def on_domain_square_focused(self, event: "DomainSquare.Focused") -> None:
        tag = event.tag
        if tag in set(self._affiliated):
            self.query_one("#old-label", Label).update(
                f"Domain to Replace: {_domain_display_name(tag)}"
            )
        else:
            self.query_one("#new-label", Label).update(
                f"New Domain: {_domain_display_name(tag)}"
            )

    def on_domain_square_blurred(self, event: "DomainSquare.Blurred") -> None:
        tag = event.tag
        if tag in set(self._affiliated):
            label = _domain_display_name(self._old_tag) if self._old_tag else "—"
            self.query_one("#old-label", Label).update(f"Domain to Replace: {label}")
        else:
            label = _domain_display_name(self._new_tag) if self._new_tag else "—"
            self.query_one("#new-label", Label).update(f"New Domain: {label}")

    def on_domain_square_selected(self, event: "DomainSquare.Selected") -> None:
        tag = event.tag
        if tag in set(self._affiliated):
            self._old_tag = tag
            self._mark_old_selected(event._sender)
            self.query_one("#old-label", Label).update(
                f"Domain to Replace: {_domain_display_name(tag)}"
            )
        else:
            self._new_tag = tag
            self._mark_new_selected(event._sender)
            self.query_one("#new-label", Label).update(
                f"New Domain: {_domain_display_name(tag)}"
            )
            self._check_confirm()

    def _check_confirm(self) -> None:
        ready = bool(self._old_tag and self._new_tag)
        btn   = self.query_one("#confirm-btn", Button)
        btn.disabled = not ready
        if ready:
            btn.add_class("continue-ready")
        else:
            btn.remove_class("continue-ready")

    @on(Button.Pressed, "#confirm-btn")
    def _confirm(self, _: Button.Pressed) -> None:
        if self._old_tag and self._new_tag:
            self.dismiss((self._old_tag, self._new_tag))

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
# CHANGE AFFILIATED DOMAIN CONFIRM MODAL
# ─────────────────────────────────────────

class ChangeAffiliatedDomainConfirmModal(ModalScreen):
    """
    Confirmation screen for Change Affiliated Domain.
    Shows which domain is being replaced and what the new one will be.
    Dismisses with True (confirm), False (back to config), or None (cancel).
    """

    BINDINGS = [
        ("escape",    "force_cancel", "Cancel"),
        ("backspace", "back",         "Back"),
    ]

    def __init__(
        self,
        state: "SimulationState",
        old_tag: str,
        new_tag: str,
    ) -> None:
        super().__init__()
        self._state   = state
        self._old_tag = old_tag
        self._new_tag = new_tag

    def _body(self) -> Text:
        dreg     = get_domain_registry()
        old_icon = dreg.icon(self._old_tag)
        new_icon = dreg.icon(self._new_tag)
        old_name = _domain_display_name(self._old_tag)
        new_name = _domain_display_name(self._new_tag)
        return Text.from_markup(
            f"[#5a7090]Replace[/]  [bold #c0ccdc]{old_icon} {_e(old_name)}[/]\n"
            f"[#5a7090]with[/]     [bold #50b870]{new_icon} {_e(new_name)}[/]"
        )

    def compose(self) -> "ComposeResult":
        with Vertical(classes="modal-box"):
            yield Label("Change Affiliated Domain — Confirm", classes="modal-title")
            yield Static(self._body())
            with Horizontal(classes="btn-row"):
                yield Button("← Back",  id="back-btn")
                yield Button("✕ Cancel",  id="cancel-btn",  classes="-danger")
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
    def _cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_back(self) -> None:
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
                yield Button("✕ Cancel",             id="cancel-btn",  classes="-danger")
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
                yield Button("✕ Cancel", id="cancel-btn", classes="-danger")

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
            pop_name = _pop_stratum_label(state, pop_obj) if pop_obj else "?"
            from core.universe_core import TravelLocation as _TravelLocation
            loc_obj  = state.locations.get(str(m.current_location))
            _loc_hidden = (
                loc_obj is None
                or isinstance(loc_obj, _TravelLocation)
                or getattr(loc_obj, "visibility", 0.0) <= ENTITY_VISIBILITY_FLOOR
            )
            if _loc_hidden:
                _home_pop = state.pops.get(str(m.pop_id)) if m.pop_id else None
                _home_loc = state.locations.get(str(_home_pop.current_location)) if _home_pop else None
                loc = (_home_loc.name or "?") if _home_loc else "?"
            else:
                loc = loc_obj.name or "?"
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
            pop_label = _pop_stratum_label(state, pop)
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
        self._selected_domain_widget: "DomainSquare | None" = None
        self._selected_imago_widget:  "ImagoCell | None"    = None

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
                        yield Button("✕ Cancel",     id="cancel-btn",   classes="-danger")
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
                if self._selected_imago_widget is not None:
                    self._selected_imago_widget.remove_class("selected-active")
                    self._selected_imago_widget = None
                self._mark_domain_selected(focused)
                self._check_continue()
                self._swap_imago_tree("whisper-tree-container", tag, focus_first=True)
                event.prevent_default(); event.stop()
            elif isinstance(focused, ImagoCell):
                if focused._unlocked:
                    node_id = focused._node.node_id
                    self._imago_node_id = node_id
                    ireg = get_imago_registry()
                    node = ireg.get_node(node_id)
                    name = node.name if node else node_id
                    self.query_one("#imago-label", Label).update(f"Imāgō: {name}")
                    self._mark_imago_selected(focused)
                    self._check_continue()
                self.query_one("#back-btn", Button).focus()
                event.prevent_default(); event.stop()
            elif isinstance(focused, Button) and focused.id == "continue-btn":
                self.query_one("#mortal-list", ListView).focus()
                event.prevent_default(); event.stop()
        elif event.key == "enter":
            if isinstance(focused, ImagoCell) and focused._unlocked:
                node_id = focused._node.node_id
                if self._mortal_id and self._domain_tag:
                    self.dismiss((self._mortal_id, self._domain_tag, node_id))
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
                if self._selected_domain_widget is not None:
                    self._selected_domain_widget.remove_class("selected-active")
                    self._selected_domain_widget = None
                if self._selected_imago_widget is not None:
                    self._selected_imago_widget.remove_class("selected-active")
                    self._selected_imago_widget = None
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

    def _mark_domain_selected(self, sq: "DomainSquare") -> None:
        if self._selected_domain_widget is not None:
            self._selected_domain_widget.remove_class("selected-active")
        self._selected_domain_widget = sq
        sq.add_class("selected-active")

    def _mark_imago_selected(self, cell: "ImagoCell") -> None:
        if self._selected_imago_widget is not None:
            self._selected_imago_widget.remove_class("selected-active")
        self._selected_imago_widget = cell
        cell.add_class("selected-active")

    def on_domain_square_focused(self, event: DomainSquare.Focused) -> None:
        self.query_one("#domain-label", Label).update(f"Domain: {_domain_display_name(event.tag)}")

    def on_domain_square_blurred(self, event: DomainSquare.Blurred) -> None:
        label = _domain_display_name(self._domain_tag) if self._domain_tag else "—"
        self.query_one("#domain-label", Label).update(f"Domain: {label}")

    def on_domain_square_selected(self, event: DomainSquare.Selected) -> None:
        tag = event.tag
        self._domain_tag    = tag
        self._imago_node_id = None
        self.query_one("#domain-label", Label).update(f"Domain: {_domain_display_name(tag)}")
        self.query_one("#imago-label",  Label).update("Imāgō: —")
        if self._selected_imago_widget is not None:
            self._selected_imago_widget.remove_class("selected-active")
            self._selected_imago_widget = None
        sq = next((s for s in self.query(DomainSquare) if s._tag == tag), None)
        if sq:
            self._mark_domain_selected(sq)
        self._check_continue()
        self._swap_imago_tree("whisper-tree-container", tag)

    def on_imago_cell_focused(self, event: ImagoCell.Focused) -> None:
        ireg = get_imago_registry()
        node = ireg.get_node(event.node_id)
        name = node.name if node else event.node_id
        self.query_one("#imago-label", Label).update(f"Imāgō: {name}")

    def on_imago_cell_blurred(self, event: ImagoCell.Blurred) -> None:
        if self._imago_node_id:
            ireg = get_imago_registry()
            node = ireg.get_node(self._imago_node_id)
            name = node.name if node else self._imago_node_id
            self.query_one("#imago-label", Label).update(f"Imāgō: {name}")
        else:
            self.query_one("#imago-label", Label).update("Imāgō: —")

    def on_imago_cell_selected(self, event: ImagoCell.Selected) -> None:
        self._imago_node_id = event.node_id
        ireg = get_imago_registry()
        node = ireg.get_node(event.node_id)
        name = node.name if node else event.node_id
        self.query_one("#imago-label", Label).update(f"Imāgō: {name}")
        cell = next((c for c in self.query(ImagoCell) if c._node.node_id == event.node_id), None)
        if cell:
            self._mark_imago_selected(cell)
        self._check_continue()

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
        self._selected_domain_a: "DomainSquare | None" = None
        self._selected_domain_b: "DomainSquare | None" = None
        self._selected_imago_a:  "ImagoCell | None"    = None
        self._selected_imago_b:  "ImagoCell | None"    = None

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
                        yield Button("✕ Cancel",     id="sd-cancel-btn",   classes="-danger")
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
                self._mark_sd_domain_selected(slot, focused)
                self._select_slot_domain(slot, focused._tag)
                event.prevent_default(); event.stop()
            elif isinstance(focused, ImagoCell):
                container_a = self.query_one("#shape-dream-tree-container-a", ScrollableContainer)
                in_slot_a = container_a in focused.ancestors_with_self
                slot = "a" if in_slot_a else "b"
                if focused._unlocked:
                    node_id = focused._node.node_id
                    ireg = get_imago_registry()
                    node = ireg.get_node(node_id)
                    name = node.name if node else node_id
                    setattr(self, f"_imago_{slot}", node_id)
                    slot_num = "1" if in_slot_a else "2"
                    self.query_one(f"#sd-imago-label-{slot}", Label).update(f"Imāgō: {name}")
                    self.query_one("#sd-tabs", TabbedContent).get_tab(f"sd-tab-{slot}").label = \
                        self._tab_label(slot_num, getattr(self, f"_domain_{slot}"), node_id)
                    self._mark_sd_imago_selected(slot, focused)
                    self._check_continue()
                if in_slot_a:
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
        elif event.key == "enter":
            if isinstance(focused, ImagoCell) and focused._unlocked:
                container_a = self.query_one("#shape-dream-tree-container-a", ScrollableContainer)
                in_slot_a   = container_a in focused.ancestors_with_self
                slot        = "a" if in_slot_a else "b"
                other       = "b" if in_slot_a else "a"
                node_id     = focused._node.node_id
                if getattr(self, f"_imago_{other}") and self._mortal_id:
                    self.dismiss((self._mortal_id,
                                  node_id if in_slot_a else self._imago_a,
                                  self._imago_b if in_slot_a else node_id))
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
                    for attr in ("_selected_domain_a", "_selected_imago_a"):
                        w = getattr(self, attr)
                        if w is not None:
                            w.remove_class("selected-active")
                            setattr(self, attr, None)
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
                    for attr in ("_selected_domain_b", "_selected_imago_b"):
                        w = getattr(self, attr)
                        if w is not None:
                            w.remove_class("selected-active")
                            setattr(self, attr, None)
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

    def _mark_sd_domain_selected(self, slot: str, sq: "DomainSquare") -> None:
        prev = getattr(self, f"_selected_domain_{slot}")
        if prev is not None:
            prev.remove_class("selected-active")
        setattr(self, f"_selected_domain_{slot}", sq)
        sq.add_class("selected-active")

    def _mark_sd_imago_selected(self, slot: str, cell: "ImagoCell") -> None:
        prev = getattr(self, f"_selected_imago_{slot}")
        if prev is not None:
            prev.remove_class("selected-active")
        setattr(self, f"_selected_imago_{slot}", cell)
        cell.add_class("selected-active")

    def on_domain_square_focused(self, event: DomainSquare.Focused) -> None:
        grid_a = self.query_one("#shape-dream-domain-grid-a", Grid)
        slot   = "a" if grid_a in event._sender.ancestors_with_self else "b"
        self.query_one(f"#sd-domain-label-{slot}", Label).update(
            f"Domain: {_domain_display_name(event.tag)}"
        )

    def on_domain_square_blurred(self, event: DomainSquare.Blurred) -> None:
        grid_a = self.query_one("#shape-dream-domain-grid-a", Grid)
        slot   = "a" if grid_a in event._sender.ancestors_with_self else "b"
        committed = getattr(self, f"_domain_{slot}")
        label = _domain_display_name(committed) if committed else "—"
        self.query_one(f"#sd-domain-label-{slot}", Label).update(f"Domain: {label}")

    def on_domain_square_selected(self, event: DomainSquare.Selected) -> None:
        grid_a   = self.query_one("#shape-dream-domain-grid-a", Grid)
        slot     = "a" if grid_a in event._sender.ancestors_with_self else "b"
        other    = "b" if slot == "a" else "a"
        slot_num = "1" if slot == "a" else "2"
        prev = getattr(self, f"_domain_{slot}")
        setattr(self, f"_domain_{slot}", event.tag)
        setattr(self, f"_imago_{slot}", None)
        # Clear imago selection marker for this slot
        prev_imago_widget = getattr(self, f"_selected_imago_{slot}")
        if prev_imago_widget is not None:
            prev_imago_widget.remove_class("selected-active")
            setattr(self, f"_selected_imago_{slot}", None)
        self.query_one(f"#sd-domain-label-{slot}", Label).update(
            f"Domain: {_domain_display_name(event.tag)}"
        )
        self.query_one(f"#sd-imago-label-{slot}", Label).update("Imāgō: —")
        self.query_one("#sd-tabs", TabbedContent).get_tab(f"sd-tab-{slot}").label = \
            self._tab_label(slot_num, event.tag, None)
        self._mark_sd_domain_selected(slot, event._sender)
        self._set_domain_excluded(f"shape-dream-domain-grid-{other}", event.tag, prev)
        self._swap_imago_tree(f"shape-dream-tree-container-{slot}", event.tag)
        self._check_continue()

    def on_imago_cell_focused(self, event: ImagoCell.Focused) -> None:
        container_a = self.query_one("#shape-dream-tree-container-a", ScrollableContainer)
        in_tab_a = container_a in event._sender.ancestors_with_self
        ireg = get_imago_registry()
        node = ireg.get_node(event.node_id)
        name = node.name if node else event.node_id
        slot_label = "a" if in_tab_a else "b"
        self.query_one(f"#sd-imago-label-{slot_label}", Label).update(f"Imāgō: {name}")

    def on_imago_cell_blurred(self, event: ImagoCell.Blurred) -> None:
        container_a = self.query_one("#shape-dream-tree-container-a", ScrollableContainer)
        in_tab_a = container_a in event._sender.ancestors_with_self
        slot = "a" if in_tab_a else "b"
        committed = getattr(self, f"_imago_{slot}")
        if committed:
            ireg = get_imago_registry()
            node = ireg.get_node(committed)
            name = node.name if node else committed
            self.query_one(f"#sd-imago-label-{slot}", Label).update(f"Imāgō: {name}")
        else:
            self.query_one(f"#sd-imago-label-{slot}", Label).update("Imāgō: —")

    def on_imago_cell_selected(self, event: ImagoCell.Selected) -> None:
        container_a = self.query_one("#shape-dream-tree-container-a", ScrollableContainer)
        in_tab_a = container_a in event._sender.ancestors_with_self
        slot     = "a" if in_tab_a else "b"
        slot_num = "1" if in_tab_a else "2"

        ireg = get_imago_registry()
        node = ireg.get_node(event.node_id)
        name = node.name if node else event.node_id

        setattr(self, f"_imago_{slot}", event.node_id)
        self.query_one(f"#sd-imago-label-{slot}", Label).update(f"Imāgō: {name}")
        self.query_one("#sd-tabs", TabbedContent).get_tab(f"sd-tab-{slot}").label = \
            self._tab_label(slot_num, getattr(self, f"_domain_{slot}"), event.node_id)
        self._mark_sd_imago_selected(slot, event._sender)
        self._check_continue()

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


# ─────────────────────────────────────────
# SCRY CONFIG MODAL
# Single-screen Scry configuration.
# Scope chips + cascading location pickers + auto-stop radio.
# Dismisses with (scope, target_id_or_None, target_type, stop_when),
# BACK, or None on cancel.
# ─────────────────────────────────────────

def _loc_display_name(name: str, max_len: int = 25) -> str:
    if len(name) > max_len:
        name = name.removeprefix("The ")
    return name[:max_len] if len(name) > max_len else name


_SCOPE_CHIP_IDS: dict[str, ScryScope] = {
    "chip-universe": ScryScope.UNIVERSE,
    "chip-galaxy":   ScryScope.GALAXY,
    "chip-system":   ScryScope.SYSTEM,
    "chip-world":    ScryScope.WORLD,
}

_SCOPE_TARGET_TYPE: dict[ScryScope, TargetType] = {
    ScryScope.UNIVERSE: TargetType.UNIVERSE,
    ScryScope.GALAXY:   TargetType.GALAXY,
    ScryScope.SYSTEM:   TargetType.SYSTEM,
    ScryScope.WORLD:    TargetType.WORLD,
}


class ScryPickerList(LoopingListView):
    """
    LoopingListView that intercepts Tab/Shift+Tab at widget level (before any
    binding or screen-level handler) and posts a message for the modal to act on.
    The picker's ID and current index are embedded in the message payload so the
    handler never needs to rely on _sender.
    """

    class TabForward(Message):
        def __init__(self, picker_id: str, index: "int | None") -> None:
            super().__init__()
            self.picker_id = picker_id
            self.index     = index

    class TabBackward(Message):
        def __init__(self, picker_id: str) -> None:
            super().__init__()
            self.picker_id = picker_id

    def on_key(self, event) -> None:
        if event.key == "tab":
            event.prevent_default()
            self.post_message(self.TabForward(self.id, self.index))
        elif event.key == "shift+tab":
            event.prevent_default()
            self.post_message(self.TabBackward(self.id))


def _scry_chip_label(scope: ScryScope, cooldown: int) -> Text:
    """Build the two-line chip label for a Scry scope button."""
    fp = SCRY_FP_BASE[scope]
    if scope == ScryScope.WORLD:
        fp_str = f"+{fp * 100:.0f}%→{(fp + SCRY_FP_WORLD_MOM) * 100:.0f}% subtle FP"
    else:
        fp_str = f"+{fp * 100:.0f}% subtle FP"
    ess = SCRY_ESSENCE[scope]
    ess_str = f" + {ess:.0f} Ess" if ess > 0 else ""
    label = Text(justify="center")
    label.append(scope.value.title(), style="bold #e8f0f8")
    label.append(f"\n{fp_str}{ess_str} / {cooldown} ticks", style="#5a7090")
    return label


# Arrow-key navigation map for scope chips: (chip_id, direction) → target_chip_id
_CHIP_NAV: dict[tuple[str, str], str] = {
    ("chip-universe", "down"):  "chip-system",
    ("chip-galaxy",   "up"):    "chip-universe",
    ("chip-galaxy",   "right"): "chip-system",
    ("chip-system",   "up"):    "chip-universe",
    ("chip-system",   "left"):  "chip-galaxy",
    ("chip-system",   "right"): "chip-world",
    ("chip-world",    "up"):    "chip-universe",
    ("chip-world",    "left"):  "chip-system",
}


class ScryConfigModal(ModalScreen):
    """
    Single-screen Scry configuration.
    Dismisses with (ScryScope, target_id_or_None, TargetType, stop_when_str).
    """

    BINDINGS = [
        Binding("escape",    "cancel", "Cancel"),
        Binding("backspace", "back",   "Back"),
    ]

    def __init__(
        self,
        state: SimulationState,
        prefill: "tuple[ScryScope, object, str] | None" = None,
    ) -> None:
        super().__init__()
        self._state = state
        self._scope:     ScryScope | None = None
        self._galaxy_id: str | None = None
        self._system_id: str | None = None
        self._world_id:  str | None = None
        self._stop_when: str = "visible"
        self._shown_systems: list[tuple[str, str]] = []
        self._shown_worlds:  list[tuple[str, str]] = []
        # Generation counter: incremented on every repopulate request.
        # The worker captures its generation at start and bails if it has
        # been superseded. _repopulating is True while the worker runs so
        # Highlighted handlers ignore programmatic events.
        self._repopulate_gen: int = 0
        self._repopulating:   bool = False
        # Widget ID to focus once _repopulate_all finishes; None = no pending focus.
        self._pending_focus:  str | None = None

        # Precompute all visible locations
        self._galaxies: list[tuple[str, str]] = []
        for gid, g in state.galaxies.items():
            if is_in_window(g):
                c = g.coordinates
                self._galaxies.append((gid, f"{_loc_display_name(g.name):<25}  ({c.x:g},{c.y:g},{c.z:g})"))

        self._systems: list[tuple[str, str, str]] = []
        for sid, s in state.systems.items():
            if is_in_window(s):
                gal_id = str(s.parent_id) if s.parent_id else ""
                c = s.coordinates
                self._systems.append((sid, f"{_loc_display_name(s.name):<25}  ({c.x:g},{c.y:g},{c.z:g})", gal_id))

        self._worlds: list[tuple[str, str, str]] = []
        for wid, w in state.worlds.items():
            if is_in_window(w):
                sys_id = str(w.parent_id) if w.parent_id else ""
                n_civs = sum(
                    1 for cid in w.civilization_ids
                    if str(cid) in state.civilizations and is_in_window(state.civilizations[str(cid)])
                )
                life = f"{n_civs} civ(s) known" if n_civs else "no life known"
                c = w.coordinates
                self._worlds.append((wid, f"{_loc_display_name(w.name, 20):<20}  ({c.x:g},{c.y:g},{c.z:g})  {life}", sys_id))

        # Apply prefill
        if prefill:
            p_scope, p_target, p_stop = prefill
            self._scope     = p_scope
            self._stop_when = p_stop
            if p_target is not None:
                tid = str(p_target)
                if p_scope == ScryScope.GALAXY:
                    if any(gid == tid for gid, _ in self._galaxies):
                        self._galaxy_id = tid
                elif p_scope == ScryScope.SYSTEM:
                    match = next((s for s in self._systems if s[0] == tid), None)
                    if match:
                        self._system_id = match[0]
                        self._galaxy_id = match[2]
                elif p_scope == ScryScope.WORLD:
                    match = next((w for w in self._worlds if w[0] == tid), None)
                    if match:
                        self._world_id  = match[0]
                        sys_m = next((s for s in self._systems if s[0] == match[2]), None)
                        if sys_m:
                            self._system_id = sys_m[0]
                            self._galaxy_id = sys_m[2]

    def compose(self) -> ComposeResult:
        _scry_cd = CATEGORY_BASE_COOLDOWNS[ActionCategory.OBSERVATION]
        with Vertical(classes="scry-config-modal"):
            yield Label("Scry", classes="modal-title")

            # ── Scope chips ──
            with Vertical(classes="scry-scope-panel"):
                with Horizontal(classes="scry-scope-row-1"):
                    yield Static(classes="scope-chip-spacer")
                    yield ScopeChip(_scry_chip_label(ScryScope.UNIVERSE, _scry_cd), "chip-universe")
                    yield Static(classes="scope-chip-spacer")
                with Horizontal(classes="scry-scope-row-2"):
                    yield ScopeChip(_scry_chip_label(ScryScope.GALAXY, _scry_cd), "chip-galaxy")
                    yield ScopeChip(_scry_chip_label(ScryScope.SYSTEM, _scry_cd), "chip-system")
                    yield ScopeChip(_scry_chip_label(ScryScope.WORLD,  _scry_cd), "chip-world")

            # ── Three-column pickers ──
            with Horizontal(classes="scry-pickers"):
                with Vertical(id="galaxy-col", classes="scry-picker-col picker-col--dull"):
                    yield Label("Galaxy", classes="scry-picker-header")
                    yield ScryPickerList(id="galaxy-list")
                with Vertical(id="system-col", classes="scry-picker-col picker-col--dull"):
                    yield Label("System", classes="scry-picker-header")
                    yield ScryPickerList(id="system-list")
                with Vertical(id="world-col", classes="scry-picker-col picker-col--dull"):
                    yield Label("World", classes="scry-picker-header")
                    yield ScryPickerList(id="world-list")

            # ── Auto-stop + buttons ──
            with Vertical(classes="scry-stop-panel"):
                yield Label("Stop when", classes="scry-stop-label")
                with RadioSet(id="stop-radio"):
                    yield RadioButton("Entities within scope become visible",    id="stop-visible", value=True)
                    yield RadioButton("Entities within scope are fully revealed", id="stop-full")
                with Horizontal(classes="btn-row"):
                    yield Button("← Back",     id="back-btn")
                    yield Button("✕ Cancel",   id="cancel-btn", classes="-danger")
                    yield Button("Continue →", id="continue-btn", disabled=True)

    def on_mount(self) -> None:
        if self._stop_when == "full":
            self.query_one("#stop-full", RadioButton).value = True
        if self._scope is not None:
            self._apply_scope(self._scope, restore=True)
            self.call_after_refresh(self._focus_active_chip)
        else:
            self.call_after_refresh(self.query_one("#chip-universe", ScopeChip).focus)

    # ── Keyboard navigation ───────────────────────

    def _focus_active_chip(self) -> None:
        for cid, scope in _SCOPE_CHIP_IDS.items():
            if scope == self._scope:
                self.query_one(f"#{cid}", ScopeChip).focus()
                return
        self.query_one("#chip-universe", ScopeChip).focus()

    def _focus_stop_radio(self) -> None:
        btn_id = "stop-full" if self._stop_when == "full" else "stop-visible"
        self.query_one(f"#{btn_id}", RadioButton).focus()

    def _can_continue(self) -> bool:
        if self._scope == ScryScope.UNIVERSE: return True
        if self._scope == ScryScope.GALAXY:   return self._galaxy_id is not None
        if self._scope == ScryScope.SYSTEM:   return self._system_id is not None
        if self._scope == ScryScope.WORLD:    return self._world_id is not None
        return False

    def _dismiss_with_result(self) -> None:
        if not self._can_continue():
            return
        from uuid import UUID as _UUID
        target_id: object = None
        if self._scope == ScryScope.GALAXY and self._galaxy_id:
            target_id = _UUID(self._galaxy_id)
        elif self._scope == ScryScope.SYSTEM and self._system_id:
            target_id = _UUID(self._system_id)
        elif self._scope == ScryScope.WORLD and self._world_id:
            target_id = _UUID(self._world_id)
        self.dismiss((self._scope, target_id, _SCOPE_TARGET_TYPE[self._scope], self._stop_when))

    def on_key(self, event) -> None:
        focused = self.focused
        key     = event.key

        # ── Arrow keys within chips (navigate without selecting) ──
        if isinstance(focused, ScopeChip) and key in ("up", "down", "left", "right"):
            event.prevent_default()
            target = _CHIP_NAV.get((focused.id, key))
            if target:
                self.query_one(f"#{target}", ScopeChip).focus()
            return

        # ── Tab forward (pickers handle their own Tab via ScryPickerList.on_key) ──
        if key == "tab":
            if isinstance(focused, ScopeChip):
                event.prevent_default()
                self._apply_scope(_SCOPE_CHIP_IDS[focused.id])
                if self._scope == ScryScope.UNIVERSE:
                    self.call_later(self._focus_stop_radio)
                else:
                    self._pending_focus = "galaxy-list"
            elif isinstance(focused, (RadioButton, RadioSet)):
                event.prevent_default()
                self.call_later(self.query_one("#back-btn", Button).focus)
            elif getattr(focused, "id", None) == "continue-btn":
                event.prevent_default()
                self.call_later(self.query_one("#chip-universe", ScopeChip).focus)
            return

        # ── Shift+Tab backward (pickers handle their own Shift+Tab via ScryPickerList.on_key) ──
        if key == "shift+tab":
            if getattr(focused, "id", None) == "back-btn":
                event.prevent_default()
                self.call_later(self._focus_stop_radio)
            elif isinstance(focused, (RadioButton, RadioSet)):
                event.prevent_default()
                if self._scope == ScryScope.WORLD:
                    self.call_later(self.query_one("#world-list", ScryPickerList).focus)
                elif self._scope == ScryScope.SYSTEM:
                    self.call_later(self.query_one("#system-list", ScryPickerList).focus)
                elif self._scope == ScryScope.GALAXY:
                    self.call_later(self.query_one("#galaxy-list", ScryPickerList).focus)
                else:
                    self.call_later(self._focus_active_chip)
            elif isinstance(focused, ScopeChip):
                event.prevent_default()
                btn = self.query_one("#continue-btn", Button)
                target = btn if not btn.disabled else self.query_one("#cancel-btn", Button)
                self.call_later(target.focus)
            return

        # ── Enter on auto-stop when all choices are made → advance ──
        if key == "enter" and isinstance(focused, RadioButton) and self._can_continue():
            self.call_later(self._dismiss_with_result)

    # ── Picker Tab/Shift+Tab (widget-level, fires before all bindings) ─

    @on(ScryPickerList.TabForward)
    def _on_picker_tab_forward(self, event: ScryPickerList.TabForward) -> None:
        lid = event.picker_id
        idx = event.index
        # Confirm the current selection from the embedded index.
        if lid == "galaxy-list" and idx is not None and idx < len(self._galaxies):
            new_gid = self._galaxies[idx][0]
            if new_gid != self._galaxy_id:
                self._galaxy_id = new_gid
                self._system_id = None
                self._world_id  = None
        elif lid == "system-list" and idx is not None and idx < len(self._shown_systems):
            new_sid = self._shown_systems[idx][0]
            if new_sid != self._system_id:
                self._system_id = new_sid
                self._world_id  = None
        elif lid == "world-list" and idx is not None and idx < len(self._shown_worlds):
            self._world_id = self._shown_worlds[idx][0]
        # Navigate forward.
        if lid == "galaxy-list" and self._scope in (ScryScope.SYSTEM, ScryScope.WORLD):
            self._trigger_repopulate()
            self._pending_focus = "system-list"
        elif lid == "system-list" and self._scope == ScryScope.WORLD:
            self._trigger_repopulate()
            self._pending_focus = "world-list"
        else:
            self._focus_stop_radio()

    @on(ScryPickerList.TabBackward)
    def _on_picker_tab_backward(self, event: ScryPickerList.TabBackward) -> None:
        lid = event.picker_id
        if lid == "world-list":
            self.call_later(self.query_one("#system-list", ScryPickerList).focus)
        elif lid == "system-list":
            self.call_later(self.query_one("#galaxy-list", ScryPickerList).focus)
        else:
            self.call_later(self._focus_active_chip)

    # ── Scope chip handling ────────────────────────

    def _apply_scope(self, scope: ScryScope, restore: bool = False) -> None:
        self._scope = scope
        for cid in _SCOPE_CHIP_IDS:
            chip = self.query_one(f"#{cid}", ScopeChip)
            if _SCOPE_CHIP_IDS[cid] == scope:
                chip.add_class("scope-chip--active")
                chip.remove_class("scope-chip--inactive")
            else:
                chip.remove_class("scope-chip--active")
                chip.add_class("scope-chip--inactive")

        uses_galaxy = scope in (ScryScope.GALAXY, ScryScope.SYSTEM, ScryScope.WORLD)
        uses_system = scope in (ScryScope.SYSTEM, ScryScope.WORLD)
        uses_world  = scope == ScryScope.WORLD

        for col_id, active in (
            ("galaxy-col", uses_galaxy),
            ("system-col", uses_system),
            ("world-col",  uses_world),
        ):
            col = self.query_one(f"#{col_id}")
            if active:
                col.remove_class("picker-col--dull")
                col.add_class("picker-col--active")
            else:
                col.remove_class("picker-col--active")
                col.add_class("picker-col--dull")

        if not restore:
            if not uses_world:
                self._world_id = None
            if not uses_system:
                self._system_id = None
            if not uses_galaxy:
                self._galaxy_id = None

        self._trigger_repopulate()

    @on(ScopeChip.Pressed)
    def _on_chip_pressed(self, event: ScopeChip.Pressed) -> None:
        scope = _SCOPE_CHIP_IDS.get(event.chip_id)
        if scope is not None:
            self._apply_scope(scope)

    # ── List population ───────────────────────────
    # A single exclusive worker populates all three lists in sequence.
    # _repopulate_gen is incremented before each launch; the worker bails
    # after any await if it no longer holds the latest generation, so
    # rapid scope changes never produce interleaved results.
    # _repopulating is True for the entire worker run so that
    # programmatic ListView.Highlighted events are ignored by the handlers.

    def _trigger_repopulate(self) -> None:
        self._repopulate_gen += 1
        self._repopulating = True
        self._repopulate_all()

    @work(exclusive=True)
    async def _repopulate_all(self) -> None:
        gen = self._repopulate_gen

        uses_galaxy = self._scope in (ScryScope.GALAXY, ScryScope.SYSTEM, ScryScope.WORLD)
        uses_system = self._scope in (ScryScope.SYSTEM, ScryScope.WORLD)
        uses_world  = self._scope == ScryScope.WORLD

        # ── Galaxy ──
        lst = self.query_one("#galaxy-list", ScryPickerList)
        lst.disabled = not uses_galaxy
        await lst.clear()
        if gen != self._repopulate_gen: return
        if uses_galaxy:
            if self._galaxies:
                for i, (gid, label) in enumerate(self._galaxies):
                    await lst.append(ListItem(Label(label), id=f"gal-{i}"))
                    if gen != self._repopulate_gen: return
                saved = next((i for i, (gid, _) in enumerate(self._galaxies) if gid == self._galaxy_id), None) if self._galaxy_id else None
                lst.index = saved if saved is not None else 0
            else:
                await lst.append(ListItem(Label("None in scope!"), id="gal-none", disabled=True))
        if gen != self._repopulate_gen: return

        # ── System ──
        lst = self.query_one("#system-list", ScryPickerList)
        lst.disabled = not uses_system
        await lst.clear()
        if gen != self._repopulate_gen: return
        if uses_system and self._galaxy_id is not None:
            filtered = [(sid, label) for sid, label, gid in self._systems if gid == self._galaxy_id]
            if filtered:
                self._shown_systems = filtered
                for i, (sid, label) in enumerate(filtered):
                    await lst.append(ListItem(Label(label), id=f"sys-{i}"))
                    if gen != self._repopulate_gen: return
                saved = next((i for i, (sid, _) in enumerate(filtered) if sid == self._system_id), None) if self._system_id else None
                lst.index = saved if saved is not None else 0
            else:
                await lst.append(ListItem(Label("None in scope!"), id="sys-none", disabled=True))
        if gen != self._repopulate_gen: return

        # ── World ──
        lst = self.query_one("#world-list", ScryPickerList)
        lst.disabled = not uses_world
        await lst.clear()
        if gen != self._repopulate_gen: return
        if uses_world and self._system_id is not None:
            filtered = [(wid, label) for wid, label, sid in self._worlds if sid == self._system_id]
            if filtered:
                self._shown_worlds = filtered
                for i, (wid, label) in enumerate(filtered):
                    await lst.append(ListItem(Label(label), id=f"wld-{i}"))
                    if gen != self._repopulate_gen: return
                saved = next((i for i, (wid, _) in enumerate(filtered) if wid == self._world_id), None) if self._world_id else None
                lst.index = saved if saved is not None else 0
            else:
                await lst.append(ListItem(Label("None in scope!"), id="wld-none", disabled=True))

        self._repopulating = False
        self._check_continue()
        # Resolve any focus jump that was deferred while lists were being built.
        if self._pending_focus:
            target = self._pending_focus
            self._pending_focus = None
            has_content = (
                target != "system-list" or bool(self._shown_systems)
            ) and (
                target != "world-list" or bool(self._shown_worlds)
            )
            try:
                if has_content:
                    self.query_one(f"#{target}").focus()
                else:
                    self._focus_stop_radio()
            except Exception:
                pass

    # ── List selection events ─────────────────────

    @on(ListView.Highlighted, "#galaxy-list")
    def _on_galaxy_highlighted(self, event: ListView.Highlighted) -> None:
        if self._repopulating or event.item is None or event.item.id == "gal-none":
            return
        if self._scope not in (ScryScope.GALAXY, ScryScope.SYSTEM, ScryScope.WORLD):
            return
        idx = int(event.item.id.rsplit("-", 1)[1])
        if idx < len(self._galaxies):
            new_gid = self._galaxies[idx][0]
            if new_gid != self._galaxy_id:
                self._galaxy_id = new_gid
                self._system_id = None
                self._world_id  = None
                self._trigger_repopulate()
        self._check_continue()

    @on(ListView.Highlighted, "#system-list")
    def _on_system_highlighted(self, event: ListView.Highlighted) -> None:
        if self._repopulating or event.item is None or event.item.id == "sys-none":
            return
        if self._scope not in (ScryScope.SYSTEM, ScryScope.WORLD):
            return
        idx = int(event.item.id.rsplit("-", 1)[1])
        if idx < len(self._shown_systems):
            new_sid = self._shown_systems[idx][0]
            if new_sid != self._system_id:
                self._system_id = new_sid
                self._world_id  = None
                self._trigger_repopulate()
        self._check_continue()

    @on(ListView.Highlighted, "#world-list")
    def _on_world_highlighted(self, event: ListView.Highlighted) -> None:
        if self._repopulating or event.item is None or event.item.id == "wld-none":
            return
        if self._scope != ScryScope.WORLD:
            return
        idx = int(event.item.id.rsplit("-", 1)[1])
        if idx < len(self._shown_worlds):
            self._world_id = self._shown_worlds[idx][0]
        self._check_continue()

    # ── Continue gating ───────────────────────────

    def _check_continue(self) -> None:
        ready = self._can_continue()
        btn = self.query_one("#continue-btn", Button)
        btn.disabled = not ready
        if ready:
            btn.add_class("continue-ready")
        else:
            btn.remove_class("continue-ready")

    # ── Auto-stop radio ───────────────────────────

    @on(RadioSet.Changed, "#stop-radio")
    def _on_stop_changed(self, event: RadioSet.Changed) -> None:
        self._stop_when = "full" if (event.pressed.id == "stop-full") else "visible"

    # ── Buttons ───────────────────────────────────

    @on(Button.Pressed, "#continue-btn")
    def _on_continue(self, _: Button.Pressed) -> None:
        self._dismiss_with_result()

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


# ─────────────────────────────────────────
# SCRY CONFIRM MODAL
# Plain-language confirmation for a queued Scry action.
# Dismisses with True (confirm), False (back), or None (cancel).
# ─────────────────────────────────────────

class ScryConfirmModal(ModalScreen):
    """Confirmation step for Scry. Shows scope/target/stop-condition summary."""

    BINDINGS = [
        ("escape",    "cancel", "Cancel"),
        ("backspace", "back",   "Back"),
    ]

    def __init__(
        self,
        scope:       ScryScope,
        target_id:   object,
        target_type: TargetType,
        stop_when:   str,
        state:       SimulationState,
    ) -> None:
        super().__init__()
        if target_id is not None:
            loc = state.locations.get(str(target_id))
            self._target_name = loc.name if loc else str(target_id)
        else:
            self._target_name = "the universe"
        self._condition = (
            "entities within scope are fully revealed"
            if stop_when == "full"
            else "entities within scope become visible"
        )

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box"):
            yield Label("Confirm Scry", classes="modal-title")
            yield Static(
                f"You have chosen to scry [bold]{_e(self._target_name)}[/bold] "
                f"and stop when {_e(self._condition)}.",
                classes="modal-desc",
            )
            with Horizontal(classes="btn-row"):
                yield Button("← Back",    id="back-btn")
                yield Button("✕ Cancel",  id="cancel-btn",  classes="-danger")
                yield Button("✓ Confirm", id="confirm-btn", classes="continue-ready")

    @on(Button.Pressed, "#confirm-btn")
    def _on_confirm(self, _: Button.Pressed) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#back-btn")
    def _on_back(self, _: Button.Pressed) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#cancel-btn")
    def _on_cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_back(self) -> None:
        self.dismiss(False)


# ─────────────────────────────────────────
# HARVEST ESSENCE CONFIG MODAL
# Concealment slider + optional auto-stop conditions.
# ─────────────────────────────────────────

class HarvestEssenceConfigModal(ModalScreen):
    """Config modal for the Harvest Essence from Underreal action."""

    DEFAULT_CSS = """
    HarvestEssenceConfigModal {
        align: center middle;
    }
    HarvestEssenceConfigModal > Vertical {
        width: 90;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: solid $primary;
    }
    HarvestEssenceConfigModal #modal-title {
        text-style: bold;
        margin-bottom: 1;
    }
    HarvestEssenceConfigModal Slider {
        width: 1fr;
        margin-bottom: 0;
    }
    HarvestEssenceConfigModal #preview {
        margin: 0 0 1 0;
        color: $text-muted;
    }
    HarvestEssenceConfigModal #stop-label {
        margin-top: 1;
        margin-bottom: 1;
    }
    HarvestEssenceConfigModal .stop-row {
        height: 3;
        margin-bottom: 1;
    }
    HarvestEssenceConfigModal .stop-input {
        width: 10;
        margin-left: 2;
    }
    HarvestEssenceConfigModal #buttons {
        margin-top: 1;
        height: 3;
        align: center middle;
    }
    """

    _BASE_YIELD = 3.0

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Harvest Essence from Underreal", id="modal-title")
            yield Label("Concealment priority  (0 = max yield / max leak → 100 = min yield / no leak)")
            yield _Slider(min=0, max=100, step=5, value=70, id="conc_slider")
            yield Label("", id="preview")
            yield Label(
                "Auto-stop conditions (leave unchecked to harvest indefinitely):",
                id="stop-label",
            )
            with Horizontal(classes="stop-row"):
                yield Checkbox(
                    "Stop when suspicious Essence ≥", id="chk_suspicious", value=False
                )
                yield Input(
                    placeholder="e.g. 20",
                    id="inp_suspicious",
                    disabled=True,
                    classes="stop-input",
                )
            with Horizontal(classes="stop-row"):
                yield Checkbox(
                    "Stop when concealment integrity < (0–100 %)",
                    id="chk_integrity",
                    value=False,
                )
                yield Input(
                    placeholder="e.g. 40",
                    id="inp_integrity",
                    disabled=True,
                    classes="stop-input",
                )
            with Horizontal(classes="stop-row"):
                yield Checkbox(
                    "Stop when Essence stockpile ≥", id="chk_stockpile", value=False
                )
                yield Input(
                    placeholder="e.g. 50",
                    id="inp_stockpile",
                    disabled=True,
                    classes="stop-input",
                )
            with Horizontal(id="buttons"):
                yield Button("✕ Cancel", id="cancel", variant="default")
                yield Button("Confirm", id="confirm", variant="primary")

    def on_mount(self) -> None:
        self._update_preview(0.7)

    def _update_preview(self, conc: float) -> None:
        yield_val = self._BASE_YIELD * (0.5 + conc * 0.5)
        leak_val  = self._BASE_YIELD * (1.0 - conc) * 0.5
        self.query_one("#preview", Label).update(
            f"Expected yield: ~{yield_val:.2f}  |  Suspicious leak: ~{leak_val:.2f}  (per tick, on success)"
        )

    def on_slider_changed(self, event: _Slider.Changed) -> None:
        self._update_preview(event.value / 100.0)

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        mapping = {
            "chk_suspicious": "inp_suspicious",
            "chk_integrity":  "inp_integrity",
            "chk_stockpile":  "inp_stockpile",
        }
        inp_id = mapping.get(event.checkbox.id)
        if inp_id:
            self.query_one(f"#{inp_id}", Input).disabled = not event.value

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        if event.button.id == "confirm":
            self.dismiss(self._build_result())

    def _parse_optional_float(self, input_id: str, checkbox_id: str) -> Optional[float]:
        if not self.query_one(f"#{checkbox_id}", Checkbox).value:
            return None
        raw = self.query_one(f"#{input_id}", Input).value.strip()
        try:
            return float(raw)
        except ValueError:
            return None

    def _build_result(self) -> dict:
        conc = self.query_one("#conc_slider", _Slider).value / 100.0
        stop_suspicious = self._parse_optional_float("inp_suspicious", "chk_suspicious")
        stop_stockpile  = self._parse_optional_float("inp_stockpile",  "chk_stockpile")
        # Integrity input is in % (0–100); store as fraction
        raw_integrity  = self._parse_optional_float("inp_integrity",  "chk_integrity")
        stop_integrity = raw_integrity / 100.0 if raw_integrity is not None else None
        return {
            "concealment": conc,
            "stop_suspicious": stop_suspicious,
            "stop_integrity": stop_integrity,
            "stop_stockpile": stop_stockpile,
        }

