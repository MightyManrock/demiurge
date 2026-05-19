"""
BuilderApp — Textual App for the scenario builder. Entry point for
`python main.py --edit-scenario` / `--build-scenario`.
"""
from __future__ import annotations
from pathlib import Path

from textual.app import App

from ui.constants import _SCENARIOS_DIR
from utilities.scenario_loader import load_scenario, validate_luminary_affinities

from .chooser import ScenarioChooserScreen
from .meta_io import peek_meta
from .screen import BuilderScreen
from .skeleton import build_skeleton_state
from .wizard import NewScenarioWizardScreen


class BuilderApp(App):
    TITLE = "Demiurge — Scenario Builder"
    CSS_PATH = "../../ui/styles.tcss"

    def on_mount(self) -> None:
        self.push_screen(ScenarioChooserScreen())

    # ── Chooser dispatch ───────────────────────────────────────────────────

    def choose_scenario(self, sel: str) -> None:
        """Called by ScenarioChooserScreen when the user picks an item.
        `sel` is either the absolute scenario .db path or the sentinel
        `"__new__"`."""
        if sel == "__new__":
            self.push_screen(NewScenarioWizardScreen())
            return
        path = Path(sel)
        try:
            state = load_scenario(path)
        except Exception as exc:
            self.notify(
                f"Failed to load {path.name}: {exc}",
                severity="error", timeout=8,
            )
            return
        violations = validate_luminary_affinities(state)
        if violations:
            self.notify(
                "Scenario opened with affinity violations:\n  • "
                + "\n  • ".join(violations),
                severity="warning", timeout=8,
            )
        # scenario_loader drops scenario_meta.description; re-peek it so the
        # Briefing tab loads with the author's blurb intact.
        meta = peek_meta(path)
        self.push_screen(BuilderScreen(
            state, path, scenario_description=meta.get("description", "")
        ))

    # ── Wizard dispatch ────────────────────────────────────────────────────

    def start_new_scenario(self, name: str, initialism: str, target: Path) -> None:
        """Called by NewScenarioWizardScreen on confirm."""
        state = build_skeleton_state(name, initialism)
        screen = BuilderScreen(state, target)
        # A brand-new scenario is dirty until first save.
        screen._dirty = True
        # Replace wizard + chooser stack with the builder.
        self.pop_screen()  # wizard
        self.pop_screen()  # chooser
        self.push_screen(screen)


def main(argv: list[str] | None = None) -> None:
    """Entry point invoked by main.py for --edit-scenario / --build-scenario.
    Both flags enter the same chooser."""
    _SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)
    BuilderApp().run()
