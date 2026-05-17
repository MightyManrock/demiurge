#!/usr/bin/env python3
"""
main.py — Demiurge entry point.

This file is intentionally thin: it parses CLI flags, configures runtime
modules (display.DEV_MODE), and dispatches either to the Textual UI in
ui/ui.py or — when --autoplay is given — to the headless autoplay runner
in autoplay/autoplay.py.

The Textual UI itself lives under ui/ (ui.py, modals.py, widgets.py,
session_log.py, constants.py, styles.tcss). Display formatters shared
between the TUI and the plain-text session log live in display.py.
Autoplay strategies live under autoplay/strategies/.

Run with:
  python main.py                       # launch the TUI
  python main.py --dev                 # launch with developer mode
  python main.py --autoplay            # headless: run wardens_default strategy
  python main.py --autoplay <name>     # headless: run a specific strategy
"""
from __future__ import annotations
import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Demiurge")
    parser.add_argument(
        "--dev", action="store_true",
        help="Developer mode: show out-of-Window entities and events (italicized).",
    )
    parser.add_argument(
        "--autoplay", nargs="?", const="wardens_default", default=None,
        metavar="STRATEGY",
        help="Run a headless autoplay session using the named strategy "
             "from autoplay/strategies/ (default: wardens_default). Skips the TUI.",
    )
    args = parser.parse_args()

    if args.autoplay:
        from autoplay.autoplay import run as autoplay_run
        autoplay_run(strategy_name=args.autoplay)
        sys.exit(0)

    import display
    from ui.ui import DemiurgeApp
    display.DEV_MODE = args.dev
    DemiurgeApp().run()


if __name__ == "__main__":
    main()
