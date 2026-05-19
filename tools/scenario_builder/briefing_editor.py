"""
BriefingEditorTab — Phase 2 right-panel tab in the scenario builder.

Three modes, switched via a row of buttons at the top:

  - Edit             — two TextArea widgets for the scenario description
                       (scenario_meta.description) and the universe description
                       (Universe.description). Plain text only for now.
  - Preview (load)   — read-only render of display_briefing(state, dev_mode=False);
                       this is what a player sees at scenario start.
  - Preview (dev)    — display_briefing(state, dev_mode=True); full extent,
                       including out-of-Window entities, dimmed.

The author's two prose blocks (scenario description, universe description) are
prepended above the regular display_briefing output in both preview modes.
display_briefing() itself doesn't render them today, so this preview is the
only place those fields surface visually.

Edits are pushed back to BuilderScreen via the `_on_scenario_description_changed`
and `_on_universe_description_changed` callbacks supplied by the screen, so the
screen owns the source of truth for both fields and persists them on save.
"""
from __future__ import annotations
from typing import Callable, Optional, TYPE_CHECKING

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Label, Static, TextArea

from ui.display import display_briefing, _lines_to_text

if TYPE_CHECKING:
    from logic.tick_logic import SimulationState


class BriefingEditorTab(Vertical):
    """Composite widget mounted inside the Builder's right-panel Briefing tab."""

    DEFAULT_CSS = """
    BriefingEditorTab {
        height: 1fr;
        padding: 0 1;
    }
    BriefingEditorTab #briefing-modebar {
        height: 3;
        padding: 0 0 1 0;
    }
    BriefingEditorTab #briefing-modebar Button {
        margin: 0 1 0 0;
    }
    BriefingEditorTab .briefing-edit-area {
        height: 1fr;
    }
    BriefingEditorTab .briefing-field-label {
        padding: 1 0 0 0;
        color: #8a9ab0;
    }
    BriefingEditorTab .briefing-textarea {
        height: 1fr;
        min-height: 6;
    }
    BriefingEditorTab #briefing-preview {
        height: 1fr;
        padding: 0 1;
    }
    BriefingEditorTab #briefing-preview-body {
        height: auto;
    }
    """

    def __init__(
        self,
        scenario_description: str = "",
        universe_description: str = "",
        on_scenario_description_changed: Optional[Callable[[str], None]] = None,
        on_universe_description_changed: Optional[Callable[[str], None]] = None,
    ):
        super().__init__()
        self._scenario_desc = scenario_description
        self._universe_desc = universe_description
        self._on_sd = on_scenario_description_changed
        self._on_ud = on_universe_description_changed
        self._state: "SimulationState | None" = None
        self._mode: str = "edit"  # "edit" | "preview_load" | "preview_dev"

    def compose(self) -> ComposeResult:
        with Horizontal(id="briefing-modebar"):
            yield Button("Edit",            id="mode-edit",         classes="-primary")
            yield Button("Preview (load)",  id="mode-preview-load")
            yield Button("Preview (dev)",   id="mode-preview-dev")
        # Edit panel
        with Vertical(classes="briefing-edit-area", id="briefing-edit"):
            yield Label("Scenario description", classes="briefing-field-label")
            yield TextArea(
                self._scenario_desc, id="briefing-scenario-desc",
                classes="briefing-textarea", show_line_numbers=False,
            )
            yield Label("Universe description", classes="briefing-field-label")
            yield TextArea(
                self._universe_desc, id="briefing-universe-desc",
                classes="briefing-textarea", show_line_numbers=False,
            )
        # Preview panel — VerticalScroll so long briefings can scroll.
        with VerticalScroll(id="briefing-preview"):
            yield Static("", id="briefing-preview-body")

    def on_mount(self) -> None:
        self._apply_mode()

    # ── Public API ─────────────────────────────────────────────────────────

    def refresh_state(self, state: "SimulationState") -> None:
        """Called by BuilderScreen._refresh_all when the underlying state
        changes (e.g. entity edits land in later phases)."""
        self._state = state
        if self._mode != "edit":
            self._render_preview()

    def sync_descriptions(
        self,
        scenario_description: str,
        universe_description: str,
    ) -> None:
        """Push fresh values into the textareas from the screen (e.g. when a
        Universe meta-edit modal changes universe.description externally)."""
        self._scenario_desc = scenario_description
        self._universe_desc = universe_description
        sd = self.query_one("#briefing-scenario-desc", TextArea)
        ud = self.query_one("#briefing-universe-desc", TextArea)
        # Avoid firing TextArea.Changed in a loop by checking equality first.
        if sd.text != scenario_description:
            sd.text = scenario_description
        if ud.text != universe_description:
            ud.text = universe_description
        if self._mode != "edit":
            self._render_preview()

    # ── Mode switching ─────────────────────────────────────────────────────

    @on(Button.Pressed, "#mode-edit")
    def _mode_edit(self, _: Button.Pressed) -> None:
        self._set_mode("edit")

    @on(Button.Pressed, "#mode-preview-load")
    def _mode_preview_load(self, _: Button.Pressed) -> None:
        self._set_mode("preview_load")

    @on(Button.Pressed, "#mode-preview-dev")
    def _mode_preview_dev(self, _: Button.Pressed) -> None:
        self._set_mode("preview_dev")

    def _set_mode(self, mode: str) -> None:
        if mode == self._mode:
            return
        self._mode = mode
        self._apply_mode()

    def _apply_mode(self) -> None:
        edit_panel    = self.query_one("#briefing-edit",    Vertical)
        preview_panel = self.query_one("#briefing-preview", VerticalScroll)
        # Mode button styling
        for btn_id, name in (
            ("#mode-edit",         "edit"),
            ("#mode-preview-load", "preview_load"),
            ("#mode-preview-dev",  "preview_dev"),
        ):
            btn = self.query_one(btn_id, Button)
            if name == self._mode:
                btn.add_class("-primary")
            else:
                btn.remove_class("-primary")
        if self._mode == "edit":
            edit_panel.display    = True
            preview_panel.display = False
        else:
            edit_panel.display    = False
            preview_panel.display = True
            self._render_preview()

    # ── Preview rendering ──────────────────────────────────────────────────

    def _render_preview(self) -> None:
        preview = self.query_one("#briefing-preview-body", Static)
        if self._state is None:
            preview.update("[#5a7090](no state loaded)[/]")
            return
        dev = self._mode == "preview_dev"

        # Prose preamble: scenario + universe descriptions. These don't appear
        # in display_briefing() today, so this tab is the only place authors
        # see their effect.
        preamble_lines: list[str] = []
        if self._scenario_desc.strip():
            preamble_lines.append("[bold]SCENARIO BLURB[/]")
            preamble_lines.append(self._scenario_desc.strip())
            preamble_lines.append("")
        if self._universe_desc.strip():
            preamble_lines.append("[bold]UNIVERSE DESCRIPTION[/]")
            preamble_lines.append(self._universe_desc.strip())
            preamble_lines.append("")
        if preamble_lines:
            preamble_lines.append("")  # spacer before the regular briefing

        # dev_mode=False filters OOW entries entirely; dev_mode=True keeps
        # them and marks them with the _OOW sentinel that _lines_to_text dims.
        briefing_lines = display_briefing(self._state, dev_mode=dev)
        body = Text.from_markup("\n".join(preamble_lines)) + _lines_to_text(briefing_lines)
        preview.update(body)

    # ── Text edits ─────────────────────────────────────────────────────────

    @on(TextArea.Changed, "#briefing-scenario-desc")
    def _scenario_desc_changed(self, event: TextArea.Changed) -> None:
        new_text = event.text_area.text
        if new_text == self._scenario_desc:
            return
        self._scenario_desc = new_text
        if self._on_sd is not None:
            self._on_sd(new_text)

    @on(TextArea.Changed, "#briefing-universe-desc")
    def _universe_desc_changed(self, event: TextArea.Changed) -> None:
        new_text = event.text_area.text
        if new_text == self._universe_desc:
            return
        self._universe_desc = new_text
        if self._on_ud is not None:
            self._on_ud(new_text)
