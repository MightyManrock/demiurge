> [← CLAUDE.md](../../CLAUDE.md)

# Luminary Personality

Personality is **computed at runtime** from a Luminary's domain affinities; there is no stored `temperament`. `LuminaryPersonality` (in `utilities/domain_registry.py`) has four axes in `[-1.0, +1.0]`: `dynamic`, `reactivity`, `capriciousness`, `harshness`. Each domain carries per-axis scores in `core.db`; `compute_personality(domains)` takes the affinity-weighted average.

Personality drives evaluation interval, attention threshold, capriciousness noise, results-vs-methods weighting, and intervention suppression. See `_run_evaluations()` in `tick_logic.py`.
