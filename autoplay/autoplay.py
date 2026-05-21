#!/usr/bin/env python3
"""
autoplay/autoplay.py — headless autoplay runner.

`run(strategy_name)` loads the named strategy module from autoplay.strategies,
loads the Warden's Compact scenario, advances 50 ticks, and prints per-tick
narrative to stdout. Used by `python main.py --autoplay [name]`.

A strategy module is any module under autoplay.strategies that exports
a `decide(loop, state, tick) -> str` callable.
"""
from __future__ import annotations
import importlib
from pathlib import Path

from utilities.scenario_loader import load_scenario
from logic.tick_logic import TickLoop, SimulationState, is_mortal_visible
from core.universe_core import MortalRole, MortalStatus
from ui.display import _format_beliefs


# ── Display helpers ────────────────────────────────────────────────────────

def fmt_disposition(state: SimulationState) -> str:
    parts = []
    for lid, l in state.luminaries.items():
        d   = l.disposition
        att = state.luminary_attention.get(lid, 0.0)
        parts.append(f"{l.name}: res={d.results:+.2f} meth={d.methods:+.2f} att={att:.2f}")
    return "  ".join(parts)


def visible_mortal_summary(state: SimulationState) -> str:
    lines = []
    for mid, m in state.mortals.items():
        if not (is_mortal_visible(m) and m.status == MortalStatus.ACTIVE):
            continue
        sp = state.species.get(str(m.species_id)) if m.species_id else None
        bio_str = (f" bio={m.bio_age:.0f}/{sp.lifespan_min:.0f}–{sp.lifespan_max:.0f}"
                   if sp else "")
        lines.append(f"    {m.name} [{m.role.value}] align={m.alignment:.2f}{bio_str}")
    return "\n".join(lines) if lines else "    (none visible)"


def civ_summary(state: SimulationState) -> str:
    lines = []
    for cid, c in state.civilizations.items():
        h = c.health
        beliefs = "  ".join(
            f"{tag}({v:.2f})"
            for tag, v in sorted(c.dominant_beliefs.items(), key=lambda kv: -kv[1])
        ) or "none"
        lines.append(
            f"    {c.name} [{c.scale.value}] "
            f"stab={h.stability:.2f} pros={h.prosperity:.2f} coh={h.cohesion:.2f}\n"
            f"      beliefs: {beliefs}"
        )
    return "\n".join(lines)


def _active_proxii(state: SimulationState):
    return [(mid, m) for mid, m in state.mortals.items()
            if m.role == MortalRole.PROXIUS and m.status == MortalStatus.ACTIVE]


# ── Runner ─────────────────────────────────────────────────────────────────

_DEFAULT_SCENARIO = Path(__file__).resolve().parent.parent / "scenarios" / "wardens_compact.db"


def run(
    strategy_name: str = "wardens_default",
    scenario_path: Path | str | None = None,
    n_ticks: int = 50,
    seed: int = 42,
) -> None:
    """
    Run a headless autoplay session and print narrative to stdout.

    strategy_name : module name under autoplay.strategies (without the
                    package prefix). The module must export `decide`.
    scenario_path : optional override for the scenario .db; defaults to
                    scenarios/wardens_compact.db at the project root.
    n_ticks       : number of ticks to advance before stopping (default 50).
    seed          : RNG seed for the TickLoop (default 42, matches autoplay.py).
    """
    # Resolve strategy
    module_path = f"autoplay.strategies.{strategy_name}"
    strategy = importlib.import_module(module_path)
    if not hasattr(strategy, "decide"):
        raise AttributeError(
            f"Strategy module '{module_path}' does not export a `decide` function."
        )
    decide = strategy.decide

    path = Path(scenario_path) if scenario_path else _DEFAULT_SCENARIO
    state = load_scenario(path)
    loop  = TickLoop(rng_seed=seed)

    print("=" * 70)
    print("  DEMIURGE AUTOPLAY — The Warden's Compact")
    print(f"  {n_ticks}-tick run  |  Strategy: Essence + Dual Appeasement")
    print("=" * 70)
    print(f"\n  Start: {fmt_disposition(state)}")
    print(f"  Essence: {state.essence.actual:.2f} | Concealment: {state.essence.concealment_integrity:.2f}\n")

    for tick in range(1, n_ticks + 1):
        action_desc = decide(loop, state, tick)
        state, result = loop.advance(state)

        passive_events     = result.passive_result.narrative_events
        action_narratives  = [e.narrative for e in result.action_result.entries]
        disp_changes       = result.disposition_changes

        print(f"── Tick {tick:02d}  (age {result.universe_age_after:.1f}) {'─'*38}")
        print(f"  ACTION: {action_desc}")

        for narr in action_narratives:
            if narr and "executed." not in narr:
                print(f"  → {narr}")

        for ev in passive_events:
            print(f"  ⚡ {ev.text}")

        if disp_changes:
            for lid, (res, meth) in disp_changes.items():
                name = state.luminaries[lid].name if lid in state.luminaries else lid[:8]
                print(f"  ♦ {name} updated: res={res:+.2f} meth={meth:+.2f}")

        print(f"  {fmt_disposition(state)}")
        print(f"  Ess: actual={state.essence.actual:.2f} apparent={state.essence.apparent:.2f} "
              f"conceal={state.essence.concealment_integrity:.2f}")

        if result.terminal.triggered:
            print(f"\n{'='*70}")
            print(f"  TERMINAL: {result.terminal.condition.value.upper()}")
            print(f"  {result.terminal.note}")
            print(f"{'='*70}")
            break

        print()

    # ── Final summary ─────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  FINAL STATE (tick {n_ticks})")
    print(f"{'='*70}\n")

    print("CIVILISATIONS:")
    print(civ_summary(state))

    print("\nVISIBLE MORTALS:")
    print(visible_mortal_summary(state))

    print("\nESSENCE:")
    print(f"  actual={state.essence.actual:.2f}  apparent={state.essence.apparent:.2f}  "
          f"concealment={state.essence.concealment_integrity:.2f}")

    print("\nLUMINARY DISPOSITIONS:")
    for lid, l in state.luminaries.items():
        d   = l.disposition
        att = state.luminary_attention.get(lid, 0.0)
        print(f"  {l.name:10s}  results={d.results:+.2f}  methods={d.methods:+.2f}  "
              f"overall={d.overall:+.2f}  attention={att:.2f}")

    print("\nWORLDS:")
    for wid, w in state.worlds.items():
        tags = _format_beliefs(w.domain_expression) or "none"
        print(f"  {w.name:12s} [{w.condition.value}]  domains: {tags}  age={w.age:.1f}")

    proxii = _active_proxii(state)
    print(f"\nACTIVE PROXII: {len(proxii)}")
    for mid, m in proxii:
        sp     = state.species.get(str(m.species_id)) if m.species_id else None
        bio_str = f" bio={m.bio_age:.0f}" if sp else ""
        print(f"  {m.name}  align={m.alignment:.2f}{bio_str}")


if __name__ == "__main__":
    run()
