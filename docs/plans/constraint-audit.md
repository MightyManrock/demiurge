> **Status:** completed
> **TO-DO ref:** Investigate canonicity of Luminary/Pantheon constraints; Canonical constraint types and tunables
> **Last updated:** 2026-05-21
> **Completed:** 2026-05-21 — FootprintConstraint implemented per `docs/superpowers/specs/2026-05-21-constraint-footprint-design.md`

## Goal

Ensure every constraint in existing scenarios has real mechanical teeth, and produce a canonical taxonomy of constraint types — with clear rulings on what's immediately implementable, scaffoldable now, and what must wait on future systems.

## Approach

### Phase 1 — Audit existing scenarios
1. Read the `Constraint` model in `core/onto_core.py` to understand the current data shape.
2. Inspect constraints defined in `scenarios/wardens_compact.db` and `scenarios/ledger_and_ash.db` (via loader or direct SQL).
3. Check `logic/tick_logic.py` for any constraint evaluation logic — where and how constraints are enforced, if at all.
4. Report: which constraints have real mechanical effects, which are stored but never evaluated (flavor text), and what the gaps are.

### Phase 2 — Canonical constraint types
1. Using `docs/Brainstorming/constraint_types.md` as input, produce a formal ruling for each type:
   - **Implemented**: already enforced in tick logic
   - **Implementable now**: all required systems exist; just needs code
   - **Scaffoldable**: can be stored/modeled now; enforcement waits on a named future system
   - **Deferred**: requires systems too far out to scaffold meaningfully
2. Write the canonical taxonomy to `docs/Mechanics/constraint-system.md`.
3. Flag any gaps found in Phase 1 as implementation tickets.

## Files affected

- `core/onto_core.py` — `Constraint` model (audit/possibly extend)
- `logic/tick_logic.py` — constraint evaluation hooks (gaps to fill)
- `docs/Mechanics/constraint-system.md` — new canonical reference (Phase 2 output)
- `docs/Brainstorming/constraint_types.md` — source material for Phase 2
- `CLAUDE.md` — add constraint-system.md to Mechanics reference table

## Notes

- Phase 2 depends on Phase 1 findings — the gap report shapes which types get "implementable now" vs. "scaffoldable."
- Do not implement anything during this audit; the goal is diagnosis and documentation, not fixes.
- `[[constraint_types]]` (Obsidian link in TO-DO) resolves to `docs/Brainstorming/constraint_types.md`.

## Completion summary (2026-05-21)

Phase 1 finding: all constraints were flavor text — stored but never evaluated. The only footprint evaluation was a hard-coded block in `tick_logic.py` using `UniverseRules.footprint_tolerances` with a fixed 0.6 weight.

Phase 2 deliverables:
- **`NarrativeConstraint | FootprintConstraint` discriminated union** in `core/onto_core.py`. Narrative is never evaluated; Footprint is evaluated every Luminary evaluation tick.
- **`FootprintConstraint.footprint_tolerances: dict[str, float]`** — one entry per category, each producing its own `ConstraintEvaluation` with compliance band logic.
- **Warden's Compact** migrated: Subtlety Mandate and Proxius Restraint (Cassiel) and Collective Subtlety Expectation (Pantheon) are now real `FootprintConstraint` objects. Results Demand (Vrath) stays `NarrativeConstraint`.
- **Three stress-test autoplay strategies**: `footprint_violator`, `footprint_compliant`, `footprint_mixed`.
- **Mechanics documented** in `docs/Mechanics/belief-footprint.md`.
- `UniverseRules.footprint_tolerances` marked deprecated but retained for backwards compatibility.
