# Testing

Demiurge uses [pytest](https://docs.pytest.org/) for unit testing pure-logic layers. The headless `--autoplay` mode handles integration-level coverage; pytest fills the gap below that — fast, isolated checks on individual functions and Pydantic models, especially in the autonomous-agent code where silent regressions are easy to introduce and painful to diagnose from a 50-tick playtest.

## Running the suite

```bash
source venv/bin/activate
pytest                                # all tests
pytest tests/test_civilian_logic.py   # one file
pytest -k fatigue                     # tests matching a substring
pytest -v                             # verbose; show every test name
pytest --tb=short                     # shorter tracebacks on failure
pytest -x                             # stop at the first failure
```

The whole suite should run in well under a second. If it ever creeps above ~2s, something is doing real I/O or loading scenarios — push that work down or out.

## Layout

```
tests/
├── conftest.py             # adds project root to sys.path so imports work
├── test_agent_core.py      # Pydantic models in core/agent_core.py
└── test_civilian_logic.py  # evaluate_civilian_action decision tree
```

`conftest.py` is auto-loaded by pytest. The single line it contains lets tests do `from core.agent_core import ...` without any package install dance.

## Conventions

- **One file per logical area.** Mirror source-file names roughly: `test_<module>.py` for `core/<module>.py` or `logic/<module>.py`.
- **Test names describe behavior, not function names.** `test_sell_triggers_travel_to_sell_location` > `test_evaluate_civilian_action_2`. When a test fails, the name should tell you what broke.
- **Group tests with a one-line comment header.** See `test_civilian_logic.py` — comments like `# Sell priority: already at sell location` segment the file into readable chapters.
- **Mock the world, not the unit under test.** The civilian-logic tests use `MagicMock()` to fake `Mortal` and `SimulationState`, setting only the fields the function actually reads. Don't construct a real scenario just to test one decision branch.
- **Use small helpers for repetitive setup.** `_mortal(...)`, `_state(...)`, `_pressing_need()` in `test_civilian_logic.py` keep each test to 5–10 lines.
- **Each test asserts one behavior.** Multiple asserts are fine if they're checking facets of the same outcome; don't bundle independent behaviors into one test.

## Current test index

### `test_agent_core.py` — model layer (18 tests)

Validates default values, invariants, and computed properties on the Pydantic models in `core/agent_core.py`:

- **`Resource`** — defaults (`quantity=0`, `usable_for=[]`), threshold comparison.
- **`MortalNeed`** — default `pressing_threshold` (0.65) and `urgent_threshold` (0.35), `is_pressing` / `is_urgent` computed flags.
- **`CivilianAgentState`** — empty defaults, inventory composition, multi-need state.
- **`KnowledgeBase`** — fact insertion, lookup helpers for `RouteFact`/`LocationQualityFact`/`ResourceFact`.
- **`CollectibleResource`** / **`LocationQualityFact`** / **`RouteFact`** / **`ResourceFact`** — field defaults and required-field enforcement.

### `test_civilian_logic.py` — civilian agent decision loop (9 tests)

Exercises `evaluate_civilian_action()` and the `_trip_too_long_for_urgent_need` helper in `logic/civilian_agent_logic.py`. Covers the sell → spend → collect priority cascade plus the fatigue gate and urgency-aware trip filter:

- `test_no_pressing_needs_returns_idle` — no work to do = idle.
- `test_fatigue_blocks_action` — high fatigue overrides pressing needs.
- `test_sell_at_sell_location` — at sell location with sellable inventory → `sell`.
- `test_sell_triggers_travel_to_sell_location` — away from sell location → `travel:<id>`.
- `test_sell_skipped_below_threshold` — inventory below `threshold` doesn't trigger travel.
- `test_spend_at_spend_location` — credits + at spend location → `spend`.
- `test_collect_at_resource_location` — at a collectible resource → `collect`.
- `test_trip_too_long_for_urgent_need_true` — urgent need + long route → trip rejected.
- `test_trip_too_long_for_urgent_need_false_when_not_urgent` — same route is fine when need is merely pressing.

## What to test next (as agent work expands)

This list is a working backlog — add to it when you notice something that *should* have a test, and check items off (with the test file) when you add coverage.

- [ ] **Need decay** — multi-tick decay, decay rate variations, satiation hold (`docs/.dev/Mechanics/agent-system.md` has the semantics).
- [ ] **Action effects on needs** — sell / spend / collect / consume all mutate `satisfaction` and inventory; lock down those deltas so a future tweak doesn't quietly change economy balance.
- [ ] **Multi-need conflict** — when indulgence and (future) sustenance both go pressing, which wins? Test the ordering rule.
- [ ] **KnowledgeBase staleness** — facts that become invalid (route disappears, location quality changes) should be evictable; test the contract.
- [ ] **Goal pursuit (T1+ agents)** — once `ProxiusGoal` / `AgentActionChoice` are wired into a goal-driven decision loop, mirror the civilian-logic test layout.
- [ ] **Scenario round-trip** — load a `scenarios/*.db`, re-export it, reload, assert structural equality. Catches schema drift after model changes; high-value, low-cost.
- [ ] **Domain similarity** — `utilities/domain_registry.py`. Pure function, trivial to test, currently uncovered.
- [ ] **Puissance formula** — `Demiurge.puissance` should map known inputs to known outputs; lock it before any tuning pass.
- [ ] **Luminary disposition delta** — small fixture universe + a known constraint state → expected `DispositionDelta`. The `EvaluationEngine` is where balance regressions hide.
- [ ] **FootprintConstraint evaluation** — the named constraint system is finicky; one test per constraint shape would be cheap insurance.

## What we deliberately don't test

- **Textual UI rendering.** Snapshotting `Static`/`DataTable` widgets is brittle and high-maintenance. Trust the TUI to a manual playtest.
- **Full tick-loop integration.** That's what `--autoplay` is for. Unit tests should be narrow enough that a failing test names the specific function that broke.
- **SQLite I/O paths.** Loader/exporter coverage is fine via a round-trip test (above); we don't need to mock `sqlite3`.

## Adding a new test file

1. Create `tests/test_<thing>.py`.
2. Import from `core` / `logic` / `utilities` directly — `conftest.py` handles the path.
3. Mock external dependencies (`MagicMock` from `unittest.mock`); only construct real Pydantic models for the thing under test.
4. Run `pytest tests/test_<thing>.py -v` and confirm it passes before committing.
5. Update the **Current test index** above so the next session can find it.
