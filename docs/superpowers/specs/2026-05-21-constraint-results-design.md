# Constraint System: Results Constraints — Design Spec

**Date:** 2026-05-21
**Scope:** Phase 2 — outcome-focused constraints
**Status:** Draft
**Depends on:** `2026-05-21-constraint-footprint-design.md` (discriminated union already in place)

---

## Problem

Vrath's "Results Demand" constraint is still a `NarrativeConstraint` — never evaluated. It represents Vrath's expectation that the Demiurge produce tangible outcomes in the universe. The existing `FootprintConstraint` mechanism covers *how* you act; this covers *whether it's working*.

---

## Design

### 1. Data Model (`core/onto_core.py`)

Add a third subtype to the `Constraint` discriminated union:

```python
class ResultsConstraint(BaseModel):
    constraint_type: Literal["results"] = "results"
    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str
    domain_tag: Optional[str] = None
    enforcement_weight: float = Field(ge=0.0, le=1.0, default=0.5)
    min_results: float = Field(ge=-1.0, le=1.0)
    # Floor for the owning Luminary's disposition.results axis.
    # The constraint fires when actual results fall below this value.
```

`Constraint` union becomes:

```python
Constraint = Annotated[
    Union[NarrativeConstraint, FootprintConstraint, ResultsConstraint],
    Field(discriminator="constraint_type"),
]
```

### 2. Compliance Logic (`core/eval_core.py`)

`EvaluationEngine.evaluate_results_constraint(constraint, luminary, attention_level) -> list[ConstraintEvaluation]`

Compliance is determined by the **absolute delta** between the Luminary's current `disposition.results` and `min_results`:

```
delta = luminary.disposition.results - constraint.min_results
```

| delta | Band | Disposition delta (methods) | Attention delta |
|---|---|---|---|
| ≥ 0.30 | EXEMPLARY | +0.02 × weight | −0.02 |
| ≥ 0.00 | COMPLIANT | 0 | 0 |
| ≥ −0.10 | STRAINING | −0.05 × weight | +0.05 |
| ≥ −0.20 | BREACHING | −0.15 × weight | +0.15 |
| < −0.20 | FLAGRANT | −0.35 × weight | +0.30 |

**No AttentionLevel dampening.** Footprint is a measure of divine activity — a distracted Luminary can miss subtle actions. Results are the state of the universe itself, which a Luminary can observe regardless of attention level. AttentionLevel modulates *perception of activity*, not *reading of outcomes*.

One `ConstraintEvaluation` is produced per `ResultsConstraint` (not per-category like FootprintConstraint).

### 3. Tick Logic Integration (`logic/tick_logic.py`)

In the per-Luminary evaluation loop, alongside the existing FootprintConstraint block:

```python
for constraint in luminary.constraints:
    if isinstance(constraint, ResultsConstraint):
        constraint_evals.extend(
            engine.evaluate_results_constraint(constraint, luminary, attention_level)
        )

for constraint in state.pantheon.collective_constraints:
    if isinstance(constraint, ResultsConstraint):
        constraint_evals.extend(
            engine.evaluate_results_constraint(constraint, luminary, attention_level)
        )
```

**Evaluation order note:** `evaluate_results_constraint` reads `luminary.disposition.results` as it stands at the *start* of the current evaluation phase — before this tick's disposition deltas are applied. This is consistent with how FootprintConstraint reads footprint (snapshot at evaluation time).

### 4. DB Schema (`core/scenario_schema.sql`)

Add one column to the `constraints` table:

```sql
min_results  REAL  -- NULL for narrative and footprint constraints
```

`constraint_type` already exists from Phase 1. Add `'results'` as a valid value in code comments.

### 5. Loader (`utilities/scenario_loader.py`)

Extend the constraint dispatch:

```python
elif ctype == "results" and d.get("min_results") is not None:
    c = ResultsConstraint(
        **base,
        min_results=d["min_results"],
    )
```

### 6. Exporter (`utilities/scenario_exporter.py`)

Add `min_results` to the INSERT:

```python
min_results = c.min_results if isinstance(c, ResultsConstraint) else None
```

### 7. Warden's Compact Migration

Convert Results Demand (Vrath) from `narrative` to `results`:

```sql
UPDATE constraints
SET constraint_type = 'results', min_results = -0.5
WHERE name = 'Results Demand';
```

`min_results = -0.5` is deliberately forgiving. Vrath's results score starts at +0.00 and would need to fall to −0.50 before STRAINING fires — leaving substantial room for the Demiurge to have bad stretches without immediate penalty. This reflects Vrath as patient about long-term outcomes, not micromanaging.

To make Vrath stricter in future scenarios, raise `min_results` toward 0.0 or above.

---

## What this does NOT cover

- **Domain-targeted outcome expectations** (e.g., "Conflict domain must be above 0.4 on Oros"). Deferred — would require a separate constraint subtype with per-domain target maps.
- **Absolute universe metrics** (avg civ stability/prosperity). Deferred — `ResultsConstraint` delegates this computation to the existing results-scoring machinery.
- **Cross-Luminary result comparisons.** Not needed yet.

---

## Stress-test strategies

### `results_tanker.py`

Do nothing meaningful. Scry passively, harvest occasionally, avoid any civilization-building actions. Let Vrath's results score drift toward −0.5 and beyond. Verify:
- Vrath `meth` drops as Results Demand fires STRAINING → BREACHING.
- Cassiel is unaffected (Results Demand is Vrath-only, not Pantheon).
- Attention rises on Vrath only.

### `results_builder.py`

Accelerate development on civs aligned to Vrath's domain preferences, Whisper to raise alignment. Verify:
- Vrath `meth` holds steady or improves (COMPLIANT or EXEMPLARY).
- `results_tanker` and `footprint_compliant` produce opposite outcomes for Vrath.

---

## Files affected

| File | Change |
|---|---|
| `core/onto_core.py` | Add `ResultsConstraint`; extend `Constraint` union |
| `core/eval_core.py` | Add `evaluate_results_constraint` |
| `logic/tick_logic.py` | Route `ResultsConstraint` in per-luminary + Pantheon loops |
| `core/scenario_schema.sql` | Add `min_results REAL` column |
| `utilities/scenario_loader.py` | Dispatch `'results'` ctype |
| `utilities/scenario_exporter.py` | Write `min_results` |
| `scenarios/wardens_compact.db` | Migrate Results Demand |
| `docs/Mechanics/belief-footprint.md` | Document `ResultsConstraint` |
| `autoplay/strategies/results_tanker.py` | New stress-test strategy |
| `autoplay/strategies/results_builder.py` | New stress-test strategy |
