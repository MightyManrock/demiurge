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
