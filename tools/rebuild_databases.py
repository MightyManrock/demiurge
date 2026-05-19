#!/usr/bin/env python3
"""
Rebuild Demiurge databases selectively. Invoked via `python main.py --rebuild`.

  python main.py --rebuild                  # interactive TUI checklist
  python main.py --rebuild --all            # rebuild everything non-interactively
  python main.py --rebuild --domains        # rebuild only domain registry
  python main.py --rebuild --cultures       # rebuild only culture registry
  python main.py --rebuild --imagines       # rebuild only imago registry
  python main.py --rebuild --actions        # rebuild only action registry
  python main.py --rebuild --scenario       # rebuild only default scenario
  python main.py --rebuild --actions --scenario   # any combination works

When all four registries are selected, core/core.db is deleted and fully
re-bootstrapped. When fewer than four are selected, core/core.db is preserved
and only the selected registries' tables are dropped and re-populated —
leaving imago_editor edits intact if Imago is unchecked.

To rebuild actions without touching Imago edits:
  python main.py --rebuild --actions --scenario
"""

import argparse
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
CORE_DB = _PROJECT_ROOT / "core" / "core.db"


# ── Shared dispatcher ──────────────────────────────────────────────────────────

def run_operations(
    domains: bool, cultures: bool, imagines: bool, actions: bool, scenario: bool
) -> list[str]:
    """Execute selected rebuild operations. Returns result lines for display."""
    results: list[str] = []

    if domains or cultures or imagines or actions:
        all_four = domains and cultures and imagines and actions
        if all_four:
            if CORE_DB.exists():
                CORE_DB.unlink()
                results.append("Deleted existing core/core.db")
            from utilities.domain_registry  import get_registry as get_domain_registry
            from utilities.culture_registry import get_registry as get_culture_registry
            from utilities.imago_registry   import get_registry as get_imago_registry
            from utilities.action_registry  import get_registry as get_action_registry
            get_domain_registry()
            results.append("  Domain registry written (full bootstrap)")
            get_culture_registry()
            results.append("  Culture registry written (full bootstrap)")
            get_imago_registry()
            results.append("  Imago registry written (full bootstrap)")
            get_action_registry()
            results.append("  Action registry written (full bootstrap)")
        else:
            results.append("Partial rebuild — core/core.db preserved")
            if domains:
                from utilities.domain_registry import reinstate as reinstate_domains
                reinstate_domains(CORE_DB)
                results.append("  Domain registry reinstated")
            if cultures:
                from utilities.culture_registry import reinstate as reinstate_cultures
                reinstate_cultures(CORE_DB)
                results.append("  Culture registry reinstated")
            if imagines:
                from utilities.imago_registry import reinstate as reinstate_imagines
                reinstate_imagines(CORE_DB)
                results.append("  Imago registry reinstated")
            if actions:
                from utilities.action_registry import reinstate as reinstate_actions
                reinstate_actions(CORE_DB)
                results.append("  Action registry reinstated")

    if scenario:
        from utilities.scenario_exporter import build_scenario_default, export_scenario
        _scenario_db = _PROJECT_ROOT / "scenarios" / "wardens_compact.db"
        export_scenario(
            build_scenario_default(),
            _scenario_db,
            scenario_name="The Warden's Compact",
        )
        results.append("Default scenario exported to scenarios/wardens_compact.db")

    return results


# ── CLI mode ───────────────────────────────────────────────────────────────────

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="main.py --rebuild",
        description="Rebuild Demiurge databases (TUI if no flags given).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "With no flags: opens interactive TUI checklist.\n"
            "With --all or specific flags: runs non-interactively."
        ),
    )
    p.add_argument("--domains",  action="store_true", help="Rebuild domain registry in core/core.db")
    p.add_argument("--cultures", action="store_true", help="Rebuild culture registry in core/core.db")
    p.add_argument("--imagines", action="store_true", help="Rebuild imago registry in core/core.db")
    p.add_argument("--actions",  action="store_true", help="Rebuild action registry in core/core.db")
    p.add_argument("--scenario", action="store_true", help="Rebuild default scenario (wardens_compact.db)")
    p.add_argument("--all",      action="store_true", help="Rebuild everything (equivalent to all five flags)")
    return p.parse_args(argv)


def _run_cli(args: argparse.Namespace) -> None:
    use_all = args.all
    results = run_operations(
        domains=use_all or args.domains,
        cultures=use_all or args.cultures,
        imagines=use_all or args.imagines,
        actions=use_all or args.actions,
        scenario=use_all or args.scenario,
    )
    if not results:
        print("Nothing selected — pass at least one flag, or run without flags for the TUI.")
        return
    for line in results:
        print(line)
    print("Done.")


# ── TUI mode ───────────────────────────────────────────────────────────────────

_CSS = """
$bg:      #0c0c1e;
$border:  #1e2d50;
$text:    #c0ccdc;
$muted:   #5a7090;
$accent:  #4a80b0;
$good:    #50b870;

Screen { background: $bg; color: $text; }
Header { background: #0a0a1e; color: $muted; height: 1; }
Footer { background: #0a0a1e; color: $muted; }

#checklist {
    width: 100%;
    height: auto;
    padding: 1 3;
    border-bottom: solid $border;
}
#checklist > Checkbox {
    margin: 0 0 1 0;
}
#log-area {
    width: 100%;
    height: 1fr;
    padding: 0 2;
}
#button-row {
    width: 100%;
    height: 3;
    align: center middle;
    border-top: solid $border;
}
#btn-run  { margin: 0 1; }
#btn-quit { margin: 0 1; }
"""


def _build_tui_app():
    from textual.app import App, ComposeResult
    from textual.containers import Vertical, Horizontal
    from textual.widgets import Header, Footer, Checkbox, Button, RichLog
    from textual import work

    class RebuildApp(App):
        TITLE = "Demiurge — Rebuild Databases"
        CSS = _CSS
        BINDINGS = [
            ("q", "quit", "Quit"),
            ("r", "run",  "Run"),
        ]

        def compose(self) -> ComposeResult:
            yield Header()
            with Vertical(id="checklist"):
                yield Checkbox("Domain registry",  value=True, id="cb-domains")
                yield Checkbox("Culture registry", value=True, id="cb-cultures")
                yield Checkbox("Imago registry",   value=True, id="cb-imagines")
                yield Checkbox("Action registry",  value=True, id="cb-actions")
                yield Checkbox("Default scenario", value=True, id="cb-scenario")
            yield RichLog(id="log-area", highlight=True, markup=True)
            with Horizontal(id="button-row"):
                yield Button("Run",  id="btn-run",  variant="primary")
                yield Button("Quit", id="btn-quit", variant="default")
            yield Footer()

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "btn-run":
                self.action_run()
            elif event.button.id == "btn-quit":
                self.exit()

        def action_run(self) -> None:
            self._do_run()

        @work(thread=True)
        def _do_run(self) -> None:
            log = self.query_one("#log-area", RichLog)
            btn = self.query_one("#btn-run", Button)

            domains  = self.query_one("#cb-domains",  Checkbox).value
            cultures = self.query_one("#cb-cultures", Checkbox).value
            imagines = self.query_one("#cb-imagines", Checkbox).value
            actions  = self.query_one("#cb-actions",  Checkbox).value
            scenario = self.query_one("#cb-scenario", Checkbox).value

            if not any([domains, cultures, imagines, actions, scenario]):
                self.call_from_thread(log.write, "[yellow]Nothing selected — check at least one item.[/]")
                return

            self.call_from_thread(setattr, btn, "disabled", True)
            self.call_from_thread(log.clear)
            self.call_from_thread(log.write, "[bold]Starting rebuild...[/]")

            results = run_operations(domains, cultures, imagines, actions, scenario)

            for line in results:
                self.call_from_thread(log.write, line)
            self.call_from_thread(log.write, "[bold green]Done.[/]")
            self.call_from_thread(setattr, btn, "disabled", False)

    return RebuildApp


# ── Entry point ────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> None:
    """Entry point used by main.py --rebuild. Dispatches to TUI when no flags
    are given, CLI mode otherwise."""
    args = _parse_args(argv)
    any_flag = any([args.domains, args.cultures, args.imagines, args.actions, args.scenario, args.all])
    if any_flag:
        _run_cli(args)
    else:
        RebuildApp = _build_tui_app()
        RebuildApp().run()
