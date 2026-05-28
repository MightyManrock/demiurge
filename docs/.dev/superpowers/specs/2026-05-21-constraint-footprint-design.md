# Constraint System: Footprint Constraints — Design Spec

**Date:** 2026-05-21
**Scope:** Phase 1 — footprint-adjacent constraints only
**Status:** Approved

---

## Problem

The `Constraint` model and scenario data exist but are never evaluated. All named constraints — "Subtlety Mandate," "Proxius Restraint," etc. — are flavor text. The only real footprint enforcement is a hard-coded block in `tick_logic.py` that evaluates 4 fixed categories against `UniverseRules.footprint_tolerances` using a hard-coded `enforcement_weight` of 0.6. This block is not scenario-aware and cannot express per-Luminary expectations.

---

## Design

### 1. Data Model (`core/onto_core.py`)

Replace the flat `Constraint` model with a Pydantic v2 discriminated union:

```python
class NarrativeConstraint(BaseModel):
    constraint_type: Literal["narrative"] = "narrative"
    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str
    enforcement_weight: float = Field(ge=0.0, le=1.0, default=0.5)
    domain_tag: Optional[str] = None

class FootprintConstraint(BaseModel):
    constraint_type: Literal["footprint"] = "footprint"
    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str
    enforcement_weight: float = Field(ge=0.0, le=1.0, default=0.5)
    footprint_tolerances: dict[str, float]
    # e.g. {"overt_miracles": 0.2, "subtle_influence": 0.4}
    # Keys must be valid footprint categories; values are tolerance ceilings [0, 1]

Constraint = Annotated[
    NarrativeConstraint | FootprintConstraint,
    Field(discriminator="constraint_type")
]
```

`Luminary.constraints` and `Pantheon.collective_constraints` remain `list[Constraint]` — no structural change.

**Ownership and attribution:**
- Luminary-owned `FootprintConstraint` violations affect only that Luminary's disposition.
- Pantheon-owned `FootprintConstraint` violations fan out to every Luminary in the Pantheon.

---

### 2. Evaluation Pipeline (`core/eval_core.py`)

Refactor the existing `evaluate_footprint_constraint()` to accept a `FootprintConstraint` directly:

- Iterates `constraint.footprint_tolerances.items()`
- For each `(category, tolerance)`: reads `state.demiurge.footprint.<category>`, computes compliance band (EXEMPLARY → COMPLIANT → STRAINING → BREACHING → FLAGRANT)
- Scales disposition delta by `constraint.enforcement_weight` (replaces hard-coded 0.6)
- Returns `list[ConstraintEvaluation]` — one per category in the dict

---

### 3. Tick Loop (`logic/tick_logic.py`)

Replace the hard-coded footprint evaluation block entirely:

```python
# Per-Luminary constraints
for luminary in state.luminaries.values():
    for constraint in luminary.constraints:
        if isinstance(constraint, FootprintConstraint):
            evals = engine.evaluate_footprint_constraint(constraint, state, attention_level)
            # apply disposition deltas to this luminary only

# Pantheon collective constraints
for constraint in state.pantheon.collective_constraints:
    if isinstance(constraint, FootprintConstraint):
        evals = engine.evaluate_footprint_constraint(constraint, state, attention_level)
        # fan disposition deltas out to every luminary in the pantheon

# NarrativeConstraint: skipped, no evaluation
```

`UniverseRules.footprint_tolerances` becomes vestigial — mark with a deprecation comment, do not remove yet.

---

### 4. DB Schema (`core/scenario_schema.sql`)

Add two columns to the `constraints` table:

```sql
constraint_type     TEXT NOT NULL DEFAULT 'narrative',
footprint_tolerances TEXT  -- JSON blob, e.g. '{"overt_miracles": 0.2}'; NULL for narrative
```

Existing rows auto-migrate to `NarrativeConstraint` via the default.

**Loader** (`utilities/scenario_loader.py`): read `constraint_type`, JSON-deserialize `footprint_tolerances` if present, hydrate the correct subclass. Unknown types fall back to `NarrativeConstraint`.

**Exporter** (`utilities/scenario_exporter.py`): write `constraint_type`; write `json.dumps(constraint.footprint_tolerances)` for `FootprintConstraint`, `None` for `NarrativeConstraint`.

---

### 5. Scenario Migration (Warden's Compact)

Convert three constraints in `scenarios/wardens_compact.db` from narrative to `FootprintConstraint`:

| Name | Owner | Categories + Tolerances |
|------|-------|------------------------|
| Subtlety Mandate | Luminary | `{"overt_miracles": 0.2}` |
| Proxius Restraint | Luminary | `{"proxius_activity": 0.25}` |
| Collective Subtlety Expectation | Pantheon | `{"overt_miracles": 0.3}` |

"Results Demand" and all Ash & Ledger constraints remain `NarrativeConstraint`.

Tolerance values above are reasonable starting points; adjust after stress testing.

---

### 6. Stress Test Autoplay Strategies

Three new strategies in `autoplay/strategies/`:

| Script | Behavior | Validates |
|--------|----------|-----------|
| `footprint_violator` | Aggressively queues overt actions (Direct Miracle, Manifest Omen) to push footprint into BREACHING/FLAGRANT | Owning Luminary disposition drops; Pantheon constraints fan out |
| `footprint_compliant` | Plays cautiously, stays well under all tolerances | EXEMPLARY/COMPLIANT bands produce correct (neutral/positive) deltas; no spurious violations |
| `footprint_mixed` | Violates one Luminary's footprint constraints, respects another's | Disposition damage is correctly isolated to the owning Luminary |

---

## Out of Scope (This Phase)

- Expression floor/ceiling constraints (`ExpressionConstraint`)
- Action prohibition constraints (`ActionProhibitionConstraint`)
- Notable mortal, civilization, cultural, or temporal constraints
- Removing `UniverseRules.footprint_tolerances` (marked deprecated, removed later)
- In-game display changes for constraint evaluation results
