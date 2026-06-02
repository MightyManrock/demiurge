"""
NewScenarioWizardScreen — three-field form for creating a fresh scenario.

  - Scenario name (default "New Scenario", ≤80 chars).
  - Initialism (1–6 uppercase letters/digits, derived from name; user-editable).
  - DB filename stem (lowercase, derived from name; user-editable).

On confirm, dispatches back to the BuilderApp with the validated trio.
"""
from __future__ import annotations
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Label

from ui.constants import _SCENARIOS_DIR

from .naming import (
    derive_initialism, derive_db_filename,
    validate_scenario_name, validate_initialism, validate_db_filename,
)


class NewScenarioWizardScreen(Screen):
    BINDINGS = [
        ("escape", "cancel",  "Cancel"),
    ]

    DEFAULT_NAME = "New Scenario"

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box"):
            yield Label("NEW SCENARIO", classes="modal-title")
            yield Label(
                "Set the scenario name, the initialism used as the "
                "in-game save-file prefix, and the database filename. "
                "The initialism and filename auto-fill as you type the "
                "name; edit either if you want something different.",
                classes="modal-desc",
            )
            yield Label("Scenario name", classes="field-label")
            yield Input(value=self.DEFAULT_NAME, id="field-name")
            yield Label("Initialism", classes="field-label")
            yield Input(
                value=derive_initialism(self.DEFAULT_NAME),
                id="field-init", max_length=6,
            )
            yield Label("Database filename (scenarios/<name>.db)", classes="field-label")
            yield Input(
                value=derive_db_filename(self.DEFAULT_NAME),
                id="field-filename",
            )
            yield Label("", id="wizard-error", classes="modal-desc")
            with Horizontal(classes="btn-row"):
                yield Button("✕ Cancel",  id="cancel-btn", classes="-danger")
                yield Button("Create",  id="create-btn", classes="-primary")

    def on_mount(self) -> None:
        # Track whether the user has hand-edited init/filename. If so, we stop
        # overwriting them with derivations.
        self._init_touched: bool = False
        self._filename_touched: bool = False
        self.query_one("#field-name", Input).focus()

    # ── Live derivation as the user types the name ─────────────────────────

    @on(Input.Changed, "#field-name")
    def _name_changed(self, event: Input.Changed) -> None:
        if not self._init_touched:
            self.query_one("#field-init", Input).value = derive_initialism(event.value)
        if not self._filename_touched:
            self.query_one("#field-filename", Input).value = derive_db_filename(event.value)

    @on(Input.Changed, "#field-init")
    def _init_changed(self, event: Input.Changed) -> None:
        # Mark as touched only when the user actually deviates from our derivation.
        derived = derive_initialism(self.query_one("#field-name", Input).value)
        if event.value != derived:
            self._init_touched = True

    @on(Input.Changed, "#field-filename")
    def _filename_changed(self, event: Input.Changed) -> None:
        derived = derive_db_filename(self.query_one("#field-name", Input).value)
        if event.value != derived:
            self._filename_touched = True

    # ── Submit ─────────────────────────────────────────────────────────────

    @on(Button.Pressed, "#cancel-btn")
    def _cancel_pressed(self, _: Button.Pressed) -> None:
        self.action_cancel()

    @on(Button.Pressed, "#create-btn")
    def _create_pressed(self, _: Button.Pressed) -> None:
        self._submit()

    def _submit(self) -> None:
        name_raw     = self.query_one("#field-name", Input).value
        init_raw     = self.query_one("#field-init", Input).value
        filename_raw = self.query_one("#field-filename", Input).value

        name, err = validate_scenario_name(name_raw)
        if err:
            self._show_error(err); return
        initialism, err = validate_initialism(init_raw)
        if err:
            self._show_error(err); return
        filename, err = validate_db_filename(filename_raw)
        if err:
            self._show_error(err); return

        target = _SCENARIOS_DIR / f"{filename}.db"
        if target.exists():
            self._show_error(
                f"scenarios/{filename}.db already exists. "
                "Pick a different filename or delete the existing file."
            )
            return

        # Hand off to the app for skeleton construction + screen push.
        self.app.start_new_scenario(name, initialism, target)  # type: ignore[attr-defined]

    def _show_error(self, msg: str) -> None:
        self.query_one("#wizard-error", Label).update(f"[#d04040]{msg}[/]")

    def action_cancel(self) -> None:
        self.app.pop_screen()
