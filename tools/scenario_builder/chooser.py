"""
ScenarioChooserScreen — first screen the builder shows.

Lists every `scenarios/*.db` plus a "+ New Scenario…" entry. Selecting an
existing scenario loads it into a BuilderScreen; selecting "+ New" pushes
the NewScenarioWizardScreen.
"""
from __future__ import annotations
import sqlite3
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.screen import Screen
from textual.widgets import Label, ListItem, ListView

from ui.constants import _SCENARIOS_DIR
from ui.display import _wrap_desc
from ui.widgets import LoopingListView

_NEW_ID = "file-__new__"


def _peek_meta(path: Path) -> dict:
    try:
        with sqlite3.connect(path) as c:
            row = c.execute(
                "SELECT name, description FROM scenario_meta LIMIT 1"
            ).fetchone()
        if row:
            return {"name": row[0] or path.stem, "description": row[1] or ""}
    except Exception:
        pass
    return {"name": path.stem, "description": ""}


class ScenarioChooserScreen(Screen):
    """First screen shown by the scenario builder."""

    BINDINGS = [("q", "quit_app", "Quit")]

    def compose(self) -> ComposeResult:
        scenarios = sorted(_SCENARIOS_DIR.glob("*.db")) if _SCENARIOS_DIR.exists() else []
        with Vertical(classes="load-box"):
            yield Label("SCENARIO BUILDER", classes="load-title")
            with ScrollableContainer():
                with LoopingListView(id="chooser-list"):
                    yield ListItem(
                        Label("[bold]+ New Scenario…[/]\n  start a fresh skeleton"),
                        id=_NEW_ID, name="__new__",
                    )
                    if scenarios:
                        yield ListItem(
                            Label("── EXISTING SCENARIOS ──", classes="load-section"),
                            disabled=True,
                        )
                        for path in scenarios:
                            meta = _peek_meta(path)
                            desc_wrapped = _wrap_desc(meta["description"])
                            label_text = (
                                f"{meta['name']}\n{desc_wrapped}"
                                if desc_wrapped else meta["name"]
                            )
                            yield ListItem(
                                Label(label_text),
                                id=f"file-{path.stem}",
                                name=str(path),
                            )
                    else:
                        yield ListItem(
                            Label("[#5a7090](no scenarios yet — pick \"New\" above)[/]"),
                            disabled=True,
                        )

    def on_mount(self) -> None:
        self.query_one("#chooser-list", ListView).focus()

    @on(ListView.Selected)
    def _on_selected(self, event: ListView.Selected) -> None:
        sel = event.item.name
        if not sel:
            return
        # Defer to BuilderApp to handle dispatch; the chooser shouldn't know
        # about the screens it pushes next.
        self.app.choose_scenario(sel)  # type: ignore[attr-defined]

    def action_quit_app(self) -> None:
        self.app.exit()
