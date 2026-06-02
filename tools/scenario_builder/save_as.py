"""
SaveAsModal — minimal one-field prompt for renaming the target .db.
The scenarios/ directory is implicit; the user provides only the stem.
"""
from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label

from ui.constants import _SCENARIOS_DIR

from .naming import validate_db_filename


class SaveAsModal(ModalScreen[str]):
    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, default_stem: str):
        super().__init__()
        self._default_stem = default_stem

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box"):
            yield Label("SAVE AS", classes="modal-title")
            yield Label(
                f"Save to scenarios/<filename>.db",
                classes="modal-desc",
            )
            yield Label("Filename stem", classes="field-label")
            yield Input(value=self._default_stem, id="field-stem")
            yield Label("", id="save-as-error", classes="modal-desc")
            with Horizontal(classes="btn-row"):
                yield Button("✕ Cancel", id="cancel-btn", classes="-danger")
                yield Button("Save",   id="save-btn",   classes="-primary")

    def on_mount(self) -> None:
        self.query_one("#field-stem", Input).focus()

    @on(Button.Pressed, "#cancel-btn")
    def _cancel_pressed(self, _: Button.Pressed) -> None:
        self.action_cancel()

    @on(Button.Pressed, "#save-btn")
    def _save_pressed(self, _: Button.Pressed) -> None:
        raw = self.query_one("#field-stem", Input).value
        stem, err = validate_db_filename(raw)
        if err:
            self.query_one("#save-as-error", Label).update(f"[#d04040]{err}[/]")
            return
        target = _SCENARIOS_DIR / f"{stem}.db"
        if target.exists():
            # Save-As on top of an existing file is allowed; backup happens
            # on the screen side. But we still tell the user.
            pass
        self.dismiss(stem)

    def action_cancel(self) -> None:
        self.dismiss(None)
