"""
BuilderApp — Textual App for the scenario builder. Entry point for
`python main.py --edit-scenario` / `--build-scenario`.
"""
from __future__ import annotations
from pathlib import Path

from textual.app import App

from ui import display
from ui.constants import _SCENARIOS_DIR
from utilities.scenario_loader import load_scenario, validate_luminary_affinities
from utilities.scenario_migrator import migrate_scenario

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
        # Migrate the .db to the current schema before opening it. The
        # migrator is a load → re-export round-trip; if the load fails the
        # file is left untouched and we surface the error.
        mr = migrate_scenario(path)
        if not mr.migrated and mr.error is not None:
            self.notify(
                f"Failed to migrate {path.name}: {mr.note}",
                severity="error", timeout=8,
            )
            return
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
    Both flags enter the same chooser.

    The builder always renders with `display.DEV_MODE=True` so authors can
    see every entity (out-of-Window ones dimmed) and can tell at a glance
    which entities start in-Window vs. pinned-only — `pinned=False` +
    `visibility=0.0` is the "lives outside the player's starting view"
    signal that authors need to see while editing.
    """
    _SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)
    display.DEV_MODE = True
    BuilderApp().run()
