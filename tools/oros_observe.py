#!/usr/bin/env python3
"""
tools/oros_observe.py — 100-tick headless observer for the Oros test sandbox.

The Demiurge does nothing. Output tracks what mortals and Pops do tick by
tick: their decisions, needs satisfaction, resource yields, and stockpiles.

Usage (from project root with venv active):
    python tools/oros_observe.py
    python tools/oros_observe.py | tee /tmp/oros_run.txt
"""
from __future__ import annotations
import sys
from pathlib import Path

# Ensure project root is on sys.path when run directly.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utilities.scenario_loader import load_scenario
from logic.tick_logic import TickLoop, SimulationState
from autoplay.strategies.oros_observe import decide

# ── Constants ──────────────────────────────────────────────────────────────────

SCENARIO = _ROOT / "scenarios" / "oros_test_sandbox.db"
N_TICKS   = 100
SEED      = 42
SNAPSHOT_EVERY = 10   # full state snapshot interval

# ── Helpers ────────────────────────────────────────────────────────────────────

def _loc_name(loc_id: str, state: SimulationState) -> str:
    loc = state.locations.get(loc_id)
    if loc is None:
        return f"?{loc_id[:8]}"
    name = getattr(loc, "name", None) or loc_id[:8]
    if getattr(loc, "location_type", "") == "travel_location":
        dest_id = list(loc.legs.keys())[-1] if loc.legs else ""
        dest = state.locations.get(dest_id)
        dest_name = (getattr(dest, "name", None) or dest_id[:8]) if dest else dest_id[:8]
        return f"→{dest_name}({loc.ticks_remaining}t)"
    return name


def _fmt_need(n) -> str:
    bar = "█" * int(n.satisfaction * 10) + "░" * (10 - int(n.satisfaction * 10))
    flag = "!" if n.is_urgent else ("~" if n.is_pressing else " ")
    return f"{flag}{n.name[:8]:8s} {bar} {n.satisfaction:.2f}"


def _mortal_line(m, state: SimulationState) -> str:
    loc = _loc_name(str(m.current_location), state)
    cs  = m.mortal_state
    if cs is None:
        return f"  {m.name:12s}  @ {loc}"
    needs_str = "  ".join(_fmt_need(n) for n in cs.needs)
    inv = cs.mortal_inventory
    inv_str = "  ".join(
        f"{r.resource_type}={r.quantity:.1f}" for r in inv.items if r.quantity > 0
    ) or "empty"
    fatigue = getattr(m, "fatigue", 0.0)
    return (
        f"  {m.name:12s}  @ {loc:30s}  fat={fatigue:.2f}\n"
        f"    needs:  {needs_str}\n"
        f"    inv:    {inv_str}"
    )


def _resource_snapshot(state: SimulationState) -> str:
    lines = []
    pop_locs = {
        lid: loc for lid, loc in state.locations.items()
        if getattr(loc, "location_type", "") == "pop_location"
    }
    for lid, loc in sorted(pop_locs.items(), key=lambda kv: kv[1].name):
        if not loc.collectible_resources and not loc.resource_stockpile:
            continue
        res_parts = []
        for r in loc.collectible_resources:
            pct = r.current_yield / r.max_yield if r.max_yield > 0 else 0.0
            bar = "█" * int(pct * 8) + "░" * (8 - int(pct * 8))
            res_parts.append(f"{r.resource_type}[{bar}]{r.current_yield:.2f}/{r.max_yield:.2f}")
        stock_parts = [
            f"{rtype}={qty:.1f}" for rtype, qty in sorted(loc.resource_stockpile.items())
            if qty > 0.01
        ]
        lines.append(f"  {loc.name:30s}")
        if res_parts:
            lines.append(f"    yields:  {',  '.join(res_parts)}")
        if stock_parts:
            lines.append(f"    stockpile: {',  '.join(stock_parts)}")
    return "\n".join(lines) if lines else "  (no resources)"


def _pop_needs_snapshot(state: SimulationState) -> str:
    """Summarize pop needs per location: mean satisfaction per need name."""
    from collections import defaultdict
    loc_data: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for pop in state.pops.values():
        if pop.pop_state is None:
            continue
        loc_name = _loc_name(str(pop.current_location), state)
        for n in pop.pop_state.needs:
            loc_data[loc_name][n.name].append(n.satisfaction)

    lines = []
    for loc_name in sorted(loc_data):
        need_parts = []
        for need_name, vals in sorted(loc_data[loc_name].items()):
            mean_sat = sum(vals) / len(vals)
            flag = "!" if mean_sat < 0.20 else ("~" if mean_sat < 0.55 else " ")
            need_parts.append(f"{flag}{need_name[:8]:8s}={mean_sat:.2f}(n={len(vals)})")
        lines.append(f"  {loc_name:30s}  {',  '.join(need_parts)}")
    return "\n".join(lines) if lines else "  (no pop state)"


# ── Runner ─────────────────────────────────────────────────────────────────────

def run() -> None:
    state = load_scenario(SCENARIO)
    loop  = TickLoop(rng_seed=SEED)

    print("=" * 80)
    print("  OROS TEST SANDBOX — 100-tick passive observation")
    print("  Demiurge absent. Watching Pops and mortals.")
    print("=" * 80)
    print(f"\n  Scenario: {SCENARIO.name}")
    print(f"  Mortals: {', '.join(m.name for m in state.mortals.values())}")
    print(f"  Pops: {len(state.pops)}")
    print(f"  Locations: {len([l for l in state.locations.values() if getattr(l, 'location_type', '') == 'pop_location'])}")
    print()

    # Initial resource snapshot
    print("── INITIAL RESOURCES " + "─" * 60)
    print(_resource_snapshot(state))
    print()

    for tick in range(1, N_TICKS + 1):
        _ = decide(loop, state, tick)
        state, result = loop.advance(state)

        mortal_narrs = result.mortal_narratives
        passive_evs  = [ev.text for ev in result.passive_result.narrative_events]

        print(f"── Tick {tick:03d} {'─'*70}")

        for narr in mortal_narrs:
            print(f"  ◆ {narr}")

        for text in passive_evs:
            if any(kw in text for kw in ("collect", "forage", "hunger", "thirst",
                                          "travel", "starv", "depart", "arriv",
                                          "fortif", "build", "revel", "commune")):
                print(f"  ⚡ {text}")

        if tick % SNAPSHOT_EVERY == 0:
            print(f"\n  ── SNAPSHOT @tick {tick} " + "─" * 50)
            print("  MORTALS:")
            for m in state.mortals.values():
                print(_mortal_line(m, state))
            print()
            print("  RESOURCES:")
            print(_resource_snapshot(state))
            print()
            print("  POP NEEDS:")
            print(_pop_needs_snapshot(state))
            print()

        if result.terminal.triggered:
            print(f"\n{'='*80}")
            print(f"  TERMINAL: {result.terminal.condition.value.upper()}")
            print(f"  {result.terminal.note}")
            print(f"{'='*80}")
            break

    # ── Final summary ──────────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"  FINAL STATE (tick {N_TICKS})")
    print(f"{'='*80}\n")

    print("MORTALS:")
    for m in state.mortals.values():
        print(_mortal_line(m, state))
        print()

    print("RESOURCES:")
    print(_resource_snapshot(state))

    print("\nPOP NEEDS:")
    print(_pop_needs_snapshot(state))


if __name__ == "__main__":
    run()
