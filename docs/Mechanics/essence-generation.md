> [← CLAUDE.md](../../CLAUDE.md)

# Essence Generation

Each tick (tail end of Phase 1), `_process_essence_generation` in `tick_logic.py` builds a per-Domain universe pool of Essence and distributes it between the Luminaries and the Demiurge.

## Hierarchy (dominant → minimal)

1. **Sapient Pops** — primary source; `essence_pop_weight = 10.0` baseline, boosted by civ scale and belief-match alignment.
2. **SignificantLocations** — secondary; `essence_location_weight = 3.0` per strength unit.
3. **Pre-sapient / wild Pops** — tertiary; `essence_presapient_weight = 2.0` × `size_fractional`, bypasses scale/match formula.
4. **Notable Mortals** — floor; `essence_mortal_weight = 0.5` per strength unit.

## Pool Inputs

For each `domain:...` tag:

- **Worlds** — every `SignificantLocation`'s `domain_expression[tag]` contributes `strength * essence_location_weight` (default 3.0).
- **Sapient Pops** — Pop is sapient when neither `pop.is_wild` nor `is_wild_civ(civ)` is true. Contribution: `strength * size_weight * essence_pop_weight * (1 + (scale_mult − 1) * match)`, where `size_weight` is the Pop's share of its civ's total `size_fractional`, `scale_mult` comes from `_CIV_SCALE_ESSENCE_MULT`, and `match` is the weighted overlap between the Pop's beliefs and its civ's `established_beliefs`. Unciv'd sapient Pops use `scale_mult = 0.05` and `match = 0`.
- **Pre-sapient / wild Pops** — `pop.is_wild` or a wild civ. Contribution: `strength * pop.size_fractional * essence_presapient_weight`. Not normalized by civ total size.
- **Mortals** — every active mortal's `belief_tags[tag]` contributes `strength * essence_mortal_weight` (default 0.5).

## Claim Split

For each Domain pool, let `lum_total_aff = min(0.9, Σ lum.domains[tag])` across all Luminaries. The Luminaries collectively claim `lum_fraction = lum_total_aff ** essence_claiming_exponent` (default exponent 0.40 — a concave curve). The Demiurge claims `pool * (1 − lum_fraction)` **iff** `tag in Demiurge.affiliated_domains` — otherwise the Demiurge's share sinks to the Underreal.

**Edge case.** When `lum_total_aff == 0`: the Demiurge claims 100% if affiliated; otherwise the entire pool sinks to the Underreal.

## Accounting

Luminary satisfaction and Demiurge income are **separate accounts**. Each Luminary accumulates `lum_aff * pool` into `state.luminary_production_this_eval[lid]` regardless of what the Demiurge claims. Reducing the Demiurge's affiliated count does **not** reduce Luminary satisfaction.

Claimed Essence flows to `Demiurge.essence.actual` via an `ESSENCE_CHANGE` mutation (no `apparent` impact). Per-Domain breakdown is exposed on `TickResult.essence_claimed_by_domain` and mirrored on `state.last_tick_essence_by_domain`. Domains in `Demiurge.tracked_essence_domains` accumulate into `state.domain_essence_claimed` for cumulative tracking.

## Luminary Expectations

Baselines and expectation creep are scaled to the 10× Essence economy:
- `luminary_essence_baseline_rate = 10.0` — expected Essence per effective-affinity-point per tick.
- `luminary_essence_passive_rise = 5.0` — per-tick creep added each evaluation period (diminishing with age).
