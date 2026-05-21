# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A god-game prototype. You play a **Demiurge** — a "middle-management deity" with real power over one universe but accountable upward to **Luminary** lieges. The core loop is: queue actions → advance one tick → Luminaries evaluate your universe and update their disposition toward you → repeat. The simulation is Python/Pydantic; the interactive interface is a Textual TUI.

Key Demiurge stats: **Puissance** (`[0, 1]`, recomputed each tick from lifetime Revelation, Imago tier score, and tick count) scales action success across the board. Influence actions (Whisper, Shape Dream) use a dedicated success formula; all other actions use reliability tiers, both boosted by puissance.

## Running things

```bash
source bin/activate                   # virtualenv; deps: pydantic>=2.0, textual, rich
python main.py                        # Textual TUI (default)
python main.py --dev                  # TUI w/ developer mode (out-of-Window entities dimmed)
python main.py --autoplay             # headless 50-tick playtest (default strategy)
python main.py --autoplay <name>      # headless playtest with a named strategy
python main.py --edit-imago           # standalone TUI for editing core/core.db Imago data
python main.py --rebuild [flags]      # rebuild core.db registries / migrate scenarios (TUI if no flags)
python main.py --edit-scenario        # scenario builder/editor (alias: --build-scenario)
python main.py --inject NAME PATCH    # apply a JSON patch to scenarios/NAME.db (creates if missing)
```

`main.py` is a thin gateway: it parses CLI flags and dispatches to `ui/ui.py` (TUI), `autoplay/autoplay.py` (headless), `tools/rebuild_databases.py`, `tools/imago_editor.py`, or `tools/scenario_builder/`. There is no test suite or linter; `--autoplay` is the closest thing to a regression test.

### Data editing tools

**`tools/imago_editor.py`** — standalone Textual TUI for editing the 112 Imago nodes in `core/core.db`. Edits written back only on `Ctrl+S`, which also creates a timestamped backup.

**`tools/rebuild_databases.py`** — rebuilder for `core/core.db` registries and migrator for `scenarios/*.db`. `--scenario` runs `utilities/scenario_migrator.py` over every `scenarios/*.db`. No flags opens a TUI checklist.

**`tools/scenario_builder/`** — scenario builder/editor (Phases 1–6, feature-complete). Both `--edit-scenario` and `--build-scenario` enter the same chooser. See source for full detail.

**`--inject` CLI** — `tools/scenario_builder/injector.py`. Apply a JSON patch to a scenario `.db` non-interactively. See source for patch envelope and op vocabulary.

## Repository layout

```
demiurge/
├── main.py                # thin entry point: argparse → ui / autoplay / tools
├── ui/                    # Textual TUI package
│   ├── ui.py              #   LoadScreen, GameScreen, DemiurgeApp
│   ├── modals.py          #   modal screens
│   ├── widgets.py         #   custom widgets, tab body widgets, LogTab/LogChip
│   ├── detail_tabs.py     #   DetailTab + DetailTabManager
│   ├── detail_renderers.py #  per-entity detail-tab renderers
│   ├── session_log.py     #   plain-text mirror of TUI feed
│   ├── display.py         #   presentation helpers (shared by TUI and SessionLog)
│   ├── styles.tcss        #   Textual CSS
│   └── constants.py       #   BACK sentinel, path constants, etc.
├── autoplay/              # headless playtest package
│   ├── autoplay.py        #   run(strategy_name, ...) entry point
│   └── strategies/        #   one module per strategy + _helpers.py
├── tools/                 # maintenance tools
│   ├── imago_editor.py
│   ├── rebuild_databases.py
│   └── scenario_builder/  #   chooser → wizard or BuilderScreen
├── core/                  # pure Pydantic data models (no SQL, no UI)
├── logic/                 # simulation engine (tick_logic.py)
├── utilities/             # registries, scenario loader/exporter/migrator
├── core/core.db           # scenario-agnostic registries
├── scenarios/*.db         # scenario starting points
├── saves/*.db             # mid-run save files
└── docs/                  # design docs (Obsidian vault) + plans/
    └── Mechanics/         # per-topic deep-dives (see below)
```

## Architectural layers

The codebase is strictly layered. `logic/tick_logic.py` knows nothing about SQL or UI; `ui/` knows nothing about tick internals; `ui/display.py` is the lower layer that both the TUI and SessionLog depend on, and never imports from either.

### Data models (`core/` — pure Pydantic)

| File | What lives here |
|---|---|
| `core/onto_core.py` | `Power`, `Domain`, `Luminary`, `Pantheon`, `Demiurge` (incl. `puissance`, `lifetime_revelation`), `Disposition`, `NarrativeConstraint`, `FootprintConstraint`, `Constraint` (discriminated union), `FootprintProfile` |
| `core/universe_core.py` | `Universe`, `Location`, `System`, `SignificantLocation`, `PopLocation`, `Civilization`, `Species`, `NotableMortal`, `Pop`, all enums |
| `core/action_core.py` | Action taxonomy: `ActionDefinition`, `ActionInstance`, `OngoingAction`, all `*Intent` types, `build_action_library()` |
| `core/eval_core.py` | Luminary evaluation: `UniverseDomainProfile`, `LuminaryEvaluation`, `DispositionDelta`, `EvaluationEngine` |
| `core/event_core.py` | Multi-tick effect system: `Event`, `EventType`, `StrengthCurve` |
| `core/agent_core.py` | `ProxiusGoal`, `AgentActionChoice` |

### Engine, registries, and persistence

| File | What it does |
|---|---|
| `logic/tick_logic.py` | The simulation engine: `SimulationState`, `TickLoop`, all six tick phases |
| `utilities/domain_registry.py` | Canonical `domain:...` list, pairwise similarity, `luminary_approval()` |
| `utilities/culture_registry.py` | Canonical `culture:...` traits, pairwise synergy |
| `utilities/imago_registry.py` | 112 `ImagoNode` records across 16 trees |
| `utilities/scenario_loader.py` | SQLite → Pydantic; the only file that knows SQL exists at load time |
| `utilities/scenario_exporter.py` | Pydantic → SQLite; always writes current schema |
| `utilities/scenario_migrator.py` | Load → re-export round-trip to bring `.db` files up to current schema |
| `core/scenario_schema.sql` | Canonical DB schema; new columns must be added here + handled with `.get()` in loader |

### Presentation and UI

The TUI is a tabbed workspace: left panel (`Status`, `Locations`, `Entities`, `Actions`) and right panel (`Briefing`, `Universe`, `Luminaries`, `Log`, up to 6 dynamic detail tabs). Detail tabs are managed by `DetailTabManager` with LRU eviction, pin support, and per-tab history stacks.

| File | What it does |
|---|---|
| `ui/display.py` | Snapshot renderers and formatters; shared between TUI and SessionLog |
| `ui/ui.py` | `LoadScreen`, `GameScreen`, `DemiurgeApp`; intent-construction flow |
| `ui/widgets.py` | Custom widgets, tab body widgets, `LogTab`/`LogChip` |
| `ui/detail_tabs.py` | `DetailTab` + `DetailTabManager` |
| `ui/detail_renderers.py` | Per-entity renderers and `RENDERERS` dispatch table |
| `ui/modals.py` | All modal screens |
| `ui/session_log.py` | Plain-text file mirror of the TUI feed |
| `ui/styles.tcss` | Textual CSS; supports live reload |

### Two databases

- **`core/core.db`** — scenario-agnostic: domain, culture, imago, action registries. Auto-bootstrapped on first load.
- **`scenarios/*.db`** — scenario starting points.
- **`saves/*.db`** — mid-run saves. Same schema as scenarios plus `tick_number`, `ongoing_actions`, `active_events` tables.

## Mechanics reference

Deep-dive docs live in `docs/Mechanics/`. Reach for these when working on a specific system:

| Topic | File |
|-------|------|
| Tick loop, mutation pattern, queue, ongoing actions, active events | [tick-loop.md](docs/Mechanics/tick-loop.md) |
| Action system, adding new actions, success rolls, puissance | [action-system.md](docs/Mechanics/action-system.md) |
| Domain tags, similarity, affiliated domains | [domain-system.md](docs/Mechanics/domain-system.md) |
| Luminary personality axes | [luminary-personality.md](docs/Mechanics/luminary-personality.md) |
| Essence generation and claim split | [essence-generation.md](docs/Mechanics/essence-generation.md) |
| Imago trees, mechanics dict, influence integration | [imago-system.md](docs/Mechanics/imago-system.md) |
| Revelation accumulation and reveal actions | [imago-revelation.md](docs/Mechanics/imago-revelation.md) |
| Whisper, Shape Dream, Manifest Omen; influence success roll | [influence-actions.md](docs/Mechanics/influence-actions.md) |
| Belief/culture floors, caps, inertia; footprint | [belief-footprint.md](docs/Mechanics/belief-footprint.md) |
| Window visibility, entity decay | [window-visibility.md](docs/Mechanics/window-visibility.md) |
| Scry scope and discovery | [scry-action.md](docs/Mechanics/scry-action.md) |
| Mortal aging, alignment, prominence | [mortal-system.md](docs/Mechanics/mortal-system.md) |
| Proxii, authored splinters, planned agent tiers | [agent-system.md](docs/Mechanics/agent-system.md) |

## Extending the system

**Adding a new action**: (1) define the intent class in `core/action_core.py`; (2) add it to the `ActionIntent` union; (3) add an `ActionDefinition` in `build_action_library()`; (4) handle it in `logic/tick_logic._resolve_intent_mutations()`; (5) add to `_validate_and_filter_queue` if needed; (6) add UI prompting in `GameScreen._build_intent()` / `_build_intent_params()` in `ui/ui.py`.

**Adding a new mutation type**: (1) add to `MutationType` enum in `core/action_core.py`; (2) handle in `logic/tick_logic._apply_mutations()`.

**Adding a new model field**: (1) add to the Pydantic model with a default; (2) add the column to `core/scenario_schema.sql`; (3) load it in `utilities/scenario_loader.py` via `row.get("column", default)`; (4) export in `utilities/scenario_exporter.py`.

**Adding a new constraint subtype**: (1) define a new `XConstraint(BaseModel)` with `constraint_type: Literal["x"] = "x"` in `core/onto_core.py`; (2) add it to the `Constraint` union; (3) add a dispatch branch in the `scenario_loader.py` constraint loop; (4) handle `isinstance(c, XConstraint)` in `scenario_exporter.py` INSERT; (5) evaluate it in the per-luminary and Pantheon fan-out loops in `tick_logic.py`; (6) add the `constraint_type` value and any new columns to `core/scenario_schema.sql`. See [belief-footprint.md](docs/Mechanics/belief-footprint.md) for FootprintConstraint as a reference implementation.

**Adding a new autoplay strategy**: create `autoplay/strategies/<name>.py` exporting `decide(loop, state, tick) -> str`.

## Known issues

- **Herald actions are unimplemented stubs.** `negotiate_herald`, `obstruct_herald`, `petition_luminary_herald` require a Herald entity class that does not yet exist. `investigate_underreal` and `overthrow_luminary` are end-game content not yet implemented.
- **`read_divine_traces` is parked.** Commented out in `utilities/action_registry.py`; depends on Herald mechanics. Intent class and tick-logic branch remain in place.

## Fixed issues

- **Weigh Civilization removed.** Now done by clicking a civ name in any tab to open a detail tab.
