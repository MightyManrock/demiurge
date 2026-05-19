#!/usr/bin/env python3
"""
main.py — Demiurge entry point.

This file is intentionally thin: it parses CLI flags, configures runtime
modules (display.DEV_MODE), and dispatches to one of several modes:
  - default: the Textual UI in ui/ui.py
  - --autoplay: headless playtest via autoplay/autoplay.py
  - --rebuild: database rebuilder TUI/CLI from tools/rebuild_databases.py
  - --edit-imago: Imago registry editor TUI from tools/imago_editor.py

The Textual UI itself lives under ui/ (ui.py, modals.py, widgets.py,
session_log.py, constants.py, styles.tcss, display.py). Autoplay strategies
live under autoplay/strategies/. Maintenance tools live under tools/.

Run with:
  python main.py                       # launch the TUI
  python main.py --dev                 # launch with developer mode
  python main.py --autoplay            # headless: choose a strategy interactively
  python main.py --autoplay <name>     # headless: run a specific strategy
  python main.py --edit-imago          # open the Imago registry editor
  python main.py --rebuild             # open the database rebuilder TUI
  python main.py --rebuild --all       # CLI rebuild; --rebuild --help for flags
"""
from __future__ import annotations
import argparse
import importlib
import sys
from pathlib import Path


def _list_strategies() -> list[tuple[str, str]]:
    """Return (name, short_description) pairs for every strategy module under
    autoplay/strategies/. Modules starting with `_` are skipped."""
    strat_dir = Path(__file__).resolve().parent / "autoplay" / "strategies"
    out: list[tuple[str, str]] = []
    for path in sorted(strat_dir.glob("*.py")):
        if path.stem.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f"autoplay.strategies.{path.stem}")
        except Exception as exc:
            out.append((path.stem, f"(import error: {exc})"))
            continue
        doc = (mod.__doc__ or "").strip()
        first_line = ""
        for line in doc.splitlines():
            line = line.strip()
            if line and not line.startswith("autoplay/"):
                first_line = line
                break
        out.append((path.stem, first_line or "(no description)"))
    return out


def _choose_strategy() -> str | None:
    """Display a numbered list of available autoplay strategies and prompt the
    user to pick one. Returns the chosen strategy name, or None if cancelled."""
    strategies = _list_strategies()
    if not strategies:
        print("No autoplay strategies found in autoplay/strategies/.", file=sys.stderr)
        return None

    print("Available autoplay strategies:\n")
    width = max(len(name) for name, _ in strategies)
    for idx, (name, desc) in enumerate(strategies, start=1):
        print(f"  {idx:>2}. {name:<{width}}  {desc}")
    print()

    while True:
        try:
            raw = input(f"Choose a strategy [1-{len(strategies)}, or q to cancel]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if raw.lower() in ("q", "quit", "exit"):
            return None
        if raw.isdigit():
            n = int(raw)
            if 1 <= n <= len(strategies):
                return strategies[n - 1][0]
        for name, _ in strategies:
            if raw == name:
                return name
        print(f"  '{raw}' is not a valid choice — enter a number 1-{len(strategies)}, "
              f"a strategy name, or q to cancel.")


def main() -> None:
    # Pre-dispatch on tool subcommands so their own --help / flags pass through
    # unmolested by main.py's top-level parser.
    argv = sys.argv[1:]
    if "--rebuild" in argv:
        rest = [a for a in argv if a != "--rebuild"]
        from tools.rebuild_databases import main as rebuild_main
        rebuild_main(rest)
        sys.exit(0)
    if "--edit-imago" in argv:
        rest = [a for a in argv if a != "--edit-imago"]
        if rest:
            print(f"--edit-imago takes no extra arguments; got: {' '.join(rest)}",
                  file=sys.stderr)
            sys.exit(2)
        from tools.imago_editor import main as imago_main
        imago_main()
        sys.exit(0)
    if "--edit-scenario" in argv or "--build-scenario" in argv:
        rest = [a for a in argv if a not in ("--edit-scenario", "--build-scenario")]
        if rest:
            print(f"--edit-scenario/--build-scenario take no extra arguments; got: {' '.join(rest)}",
                  file=sys.stderr)
            sys.exit(2)
        from tools.scenario_builder import main as builder_main
        builder_main()
        sys.exit(0)

    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Demiurge — god-game prototype entry point.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "With no arguments, launches the interactive Textual TUI (the "
            "default game interface).\n\n"
            "Examples:\n"
            "  python main.py                       # launch the TUI\n"
            "  python main.py --dev                 # TUI with developer mode\n"
            "  python main.py --autoplay            # headless; choose a strategy interactively\n"
            "  python main.py --autoplay passive    # headless run of a named strategy\n"
            "  python main.py --edit-imago          # open the Imago registry editor\n"
            "  python main.py --edit-scenario       # open the scenario builder/editor\n"
            "  python main.py --build-scenario      # alias for --edit-scenario\n"
            "  python main.py --rebuild             # database rebuilder TUI\n"
            "  python main.py --rebuild --all       # rebuild everything non-interactively\n"
            "  python main.py --rebuild --help      # show all rebuilder flags"
        ),
    )
    parser.add_argument(
        "--dev", action="store_true",
        help="Developer mode: show out-of-Window entities and events (italicized).",
    )
    parser.add_argument(
        "--autoplay", nargs="?", const="__choose__", default=None,
        metavar="STRATEGY",
        help="Run a headless autoplay session using the named strategy from "
             "autoplay/strategies/. With no value, prompts to choose from the "
             "available strategies. Skips the TUI.",
    )
    parser.add_argument(
        "--rebuild", action="store_true",
        help="Launch the database rebuilder (TUI if no further flags; pass "
             "extra flags like --all/--actions/--scenario for CLI mode).",
    )
    parser.add_argument(
        "--edit-imago", action="store_true", dest="edit_imago",
        help="Launch the Imago registry editor TUI.",
    )
    parser.add_argument(
        "--edit-scenario", action="store_true", dest="edit_scenario",
        help="Launch the scenario builder/editor (chooser → builder).",
    )
    parser.add_argument(
        "--build-scenario", action="store_true", dest="build_scenario",
        help="Alias for --edit-scenario; enters the same chooser flow.",
    )
    args = parser.parse_args()

    if args.autoplay:
        strategy = args.autoplay
        if strategy == "__choose__":
            strategy = _choose_strategy()
            if strategy is None:
                sys.exit(0)
        from autoplay.autoplay import run as autoplay_run
        autoplay_run(strategy_name=strategy)
        sys.exit(0)

    from ui import display
    from ui.ui import DemiurgeApp
    display.DEV_MODE = args.dev
    DemiurgeApp().run()


if __name__ == "__main__":
    main()
