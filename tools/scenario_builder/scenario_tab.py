"""
ScenarioTab — left-panel tab holding every "edit a thing" action button in
the scenario builder. Replaces the top-of-screen toolbars used in Phases 1–3.

Buttons emit standard Textual `Button.Pressed` events; BuilderScreen catches
them via `@on(Button.Pressed, "#<id>")` handlers — the same handlers used
before this restructure, no rewiring needed.

Section labels group buttons by entity type. New sections will be appended
here as later phases land (Mortal, Luminary, Constraint editors).
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.widgets import Button, Label


class ScenarioTab(Vertical):
    """Vertical stack of section labels and action buttons."""

    DEFAULT_CSS = """
    ScenarioTab {
        height: 1fr;
        padding: 0 1;
    }
    ScenarioTab .scenario-section {
        padding: 1 0 0 0;
        color: #8a9ab0;
    }
    ScenarioTab Button {
        width: 100%;
        margin: 0 0 1 0;
    }
    """

    def compose(self) -> ComposeResult:
        with ScrollableContainer():
            yield Label("Meta",          classes="scenario-section")
            yield Button("Edit Universe", id="edit-universe-btn")
            yield Button("Edit Demiurge", id="edit-demiurge-btn")
            yield Button("Edit Pantheon", id="edit-pantheon-btn")

            yield Label("Locations",        classes="scenario-section")
            yield Button("+ Add Location",  id="add-location-btn")
            yield Button("Edit Location",   id="edit-location-btn")
            yield Button("Delete Location", id="delete-location-btn")

            yield Label("Civilizations",         classes="scenario-section")
            yield Button("+ Add Civilization",   id="add-civ-btn")
            yield Button("Edit Civilization",    id="edit-civ-btn")
            yield Button("Delete Civilization",  id="delete-civ-btn")

            yield Label("Species",        classes="scenario-section")
            yield Button("+ Add Species", id="add-species-btn")
            yield Button("Edit Species",  id="edit-species-btn")
            yield Button("Delete Species", id="delete-species-btn")

            yield Label("Pops",        classes="scenario-section")
            yield Button("+ Add Pop",  id="add-pop-btn")
            yield Button("Edit Pop",   id="edit-pop-btn")
            yield Button("Delete Pop", id="delete-pop-btn")

            yield Label("Notable Mortals",  classes="scenario-section")
            yield Button("+ Add Mortal",    id="add-mortal-btn")
            yield Button("Edit Mortal",     id="edit-mortal-btn")
            yield Button("Delete Mortal",   id="delete-mortal-btn")

            yield Label("Luminaries",        classes="scenario-section")
            yield Button("+ Add Luminary",   id="add-luminary-btn")
            yield Button("Edit Luminary",    id="edit-luminary-btn")
            yield Button("Delete Luminary",  id="delete-luminary-btn")
            yield Button("Edit Pantheon Constraints", id="edit-pantheon-constraints-btn")
