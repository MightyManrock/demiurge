> [← CLAUDE.md](../../CLAUDE.md)

# Belief & Footprint Conventions

## Belief/Culture Dicts

`Civilization.dominant_beliefs`, `Pop.dominant_beliefs`, `Pop.culture_tags`, `SignificantLocation.domain_expression`, `Civilization.culture_tags`, and `NotableMortal.belief_tags` / `culture_tags` are all `dict[str, float]` (0.0–1.0).

- Belief entries below `BELIEF_FLOOR = 0.02` and culture entries below `CULTURE_FLOOR = 0.01` are pruned each passive phase by `_prune_weak_beliefs`. The lower culture floor exists because Imago `culture:*` riders propagate at smaller per-tick magnitudes.
- **`BELIEF_CAP = 0.9`** caps upward growth at every belief/culture mutation site. Location `domain_expression` is uncapped. Values seeded above 0.9 are not capped retroactively.
- **`_belief_inertia(current, delta)`** applies a [0,1] multiplier; resistance rises near the cap and below 0.2.

## Footprint

Categories: `overt_miracles`, `subtle_influence`, `proxius_activity`, `direct_creation`. Decay rates in `TickConfig.footprint_decay_multipliers`.

- `Demiurge.footprint` is universe-wide.
- `SignificantLocation.local_footprint` is per-location.
- Luminaries evaluate `EssenceStockpile.apparent`, not `actual`. The player manages the gap via `maintain_concealment`.

## FootprintConstraint

Constraints stored on `Luminary.constraints` or `Pantheon.collective_constraints` can be `NarrativeConstraint` (flavor text, never evaluated) or `FootprintConstraint` (evaluated each tick). Both live in the `Constraint` discriminated union in `core/onto_core.py`.

`FootprintConstraint.footprint_tolerances: dict[str, float]` maps one or more footprint categories to their tolerance ceilings (e.g. `{"overt_miracles": 0.2}`).

### AttentionLevel dampening

Each Luminary perceives footprint through their current `AttentionLevel`, multiplied against the raw value before comparing to tolerances:

| AttentionLevel | Multiplier |
|---|---|
| NEGLIGENT | 0.2 |
| PASSIVE | 0.5 |
| WATCHFUL | 0.8 |
| SCRUTINOUS | 0.95 |
| INVASIVE | 1.0 |

### Compliance bands

Compliance is determined by `perceived / tolerance` ratio:

| Ratio | Band | Disposition delta | Attention delta |
|---|---|---|---|
| ≤ 0.5 | EXEMPLARY | +0.02 × weight | −0.02 |
| ≤ 1.0 | COMPLIANT | 0 | 0 |
| ≤ 1.3 | STRAINING | −0.05 × weight | +0.05 |
| ≤ 1.6 | BREACHING | −0.15 × weight | +0.15 |
| > 1.6 | FLAGRANT | −0.35 × weight | +0.30 |

Each `footprint_tolerances` entry produces one `ConstraintEvaluation`.

### Per-Luminary vs. Pantheon ownership

- **Luminary-owned** `FootprintConstraint`: evaluated once, using that Luminary's `AttentionLevel`. Disposition delta applies only to that Luminary.
- **Pantheon-owned** `FootprintConstraint`: iterated inside the per-Luminary loop, so the same constraint is evaluated at each Luminary's own `AttentionLevel`. Each Luminary receives the resulting disposition delta independently.

### DB schema

`constraints` table columns: `constraint_type TEXT NOT NULL DEFAULT 'narrative'` and `footprint_tolerances TEXT` (JSON blob, NULL for narrative). Round-trip via `--rebuild --scenario` migrates existing rows.
