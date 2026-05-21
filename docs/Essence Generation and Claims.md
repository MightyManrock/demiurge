# Essence Generation and Claims

This document describes the passive Essence economy: how domain expression across the universe generates Essence each tick, how Luminaries and the Demiurge claim shares of it, and how Luminaries form and revise expectations about their domains' output.

This system runs in parallel with the active `harvest_essence` action. Harvesting draws from the Underreal and carries concealment risk; passive generation does not. They are fully independent income streams.

---

## World Pools

Each tick, every `SignificantLocation` (planet, plane, or equivalent) contributes to a per-domain **world pool** based on what is expressed there. Three sources are summed:

```
pool[domain] =
    location.domain_expression[domain]  x 3.0        (location weight)
  + sum(civ.dominant_beliefs[domain]    x SCALE_MULT) (for each civ on this world)
  + sum(mortal.belief_tags[domain]      x 0.05)       (for each notable mortal here)
```

### Civilization scale multipliers

A civilization's contribution scales with its reach. Larger civilizations generate substantially more Essence per unit of belief than smaller ones, reflecting the number of mortal minds behind them.

| Scale | Multiplier |
|---|---|
| Nascent | 0.05 |
| Tribal | 0.10 |
| City-State | 0.20 |
| Regional | 0.35 |
| Continental | 0.50 |
| Planetary | 0.70 |
| Interplanetary | 0.90 |
| Interstellar | 1.20 |
| Intergalactic | 1.60 |

### Weight hierarchy

The weights are calibrated so that a world's intrinsic domain expression always outweighs any single civilization's contribution: at max expression, the location yields 3.0, while even the largest civilization yields at most 1.60 per unit of belief. Mortal individuals contribute very little individually but can accumulate meaningfully in aggregate.

### Universe pool

World pools are summed across all `SignificantLocation`s to produce a single `dict[domain -> float]` representing total Essence available this tick for each domain. Only domains with a positive pool value are processed.

---

## Claiming

For each domain in the universe pool, either Luminaries or the Demiurge (or both) may claim a portion. The remainder sinks to the Underreal and is not tracked.

### Case A: No Luminary holds this domain

If no Luminary has any affinity for a domain, Luminaries make no claim.

- If the Demiurge has this domain in their **affiliated domains**: Demiurge claims 100% of the pool.
- Otherwise: the entire pool sinks to the Underreal.

### Case B: At least one Luminary holds this domain

Luminaries collectively claim a fraction derived from their combined affinity for the domain:

```
lum_total_aff = sum of each Luminary's affinity for this domain

lum_fraction = lum_total_aff ^ 0.40
dem_fraction = 1.0 - lum_fraction
```

The exponent of 0.40 produces a strongly concave curve: Luminaries claim a much larger share than their raw affinity fraction would suggest.

| Combined Luminary affinity | Luminary claim | Demiurge claim |
|---|---|---|
| 0.2 | ~52.5% | ~47.5% |
| 0.5 | ~75.8% | ~24.2% |
| 0.8 | ~91.5% | ~8.5% |
| 0.9 | ~95.9% | ~4.1% |

The Demiurge only receives their `dem_fraction` share if the domain is in their **affiliated domains**. Otherwise that portion also sinks to the Underreal.

### Demiurge Essence

The Demiurge's total claim across all domains is added to `essence.actual` each tick. Passive claiming does **not** increment `apparent` and does not affect concealment decay. Luminaries regard the passive flow as part of the natural divine order; only active Underreal draws register as suspicious.

The Demiurge may optionally designate domains in `tracked_essence_domains`; cumulative claims for those domains are recorded in `domain_essence_claimed` for display or future mechanics.

---

## Luminary Weighted Production

Luminaries do not directly receive or stockpile Essence. Instead they evaluate how well their domains are being expressed in the universe. The satisfaction metric is **weighted domain production**: for each domain a Luminary has affinity for, their contribution is `affinity x universe_pool[domain]`.

```
weighted_production = sum(luminary.domains[D] x universe_pool[D])
```

This accumulates each tick in `luminary_production_this_eval` and is read at each Luminary evaluation interval (typically every 5-10 ticks). After evaluation the accumulator resets to zero.

A Luminary whose domains are not expressed in the universe will accumulate very little, regardless of their affinity scores.

---

## Luminary Expectations

At each evaluation a Luminary's production score is compared against their **expectation threshold**. Falling short affects their disposition toward the Demiurge; meeting it while growing improves it.

### Base threshold

The base expectation scales with the Luminary's effective affinity and the length of the evaluation period:

```
base_threshold = effective_affinity x baseline_rate x ticks_since_last_eval
```

`baseline_rate` defaults to 1.0, meaning one unit of production expected per effective-affinity-point per tick.

**Effective affinity** applies diminishing returns to a Luminary's domain portfolio. Affinities are sorted descending (ties broken alphabetically by domain name), and each rank is multiplied by `0.65^rank`:

```
effective_affinity = aff[0] x 1.000
                   + aff[1] x 0.650
                   + aff[2] x 0.423
                   + ...
```

This prevents Luminaries with many domains from having proportionally higher expectations than those with one or two strong commitments. A 3-domain Luminary at `[0.7, 0.7, 0.5]` has a raw sum of 1.9 but an effective affinity of 1.37. A 2-domain Luminary at `[0.7, 0.6]` scores 1.09. The gap is meaningfully narrowed.

### Raised threshold (growing expectations)

When a Luminary's production exceeded their base threshold last period, their expectation does not simply reset to base. It rises slightly to reflect what they have come to expect:

```
raised = max(0.0, last_period_production - base_threshold) x 0.20

lum_threshold = base_threshold + raised
```

Only 20% of the excess above base carries forward. Consistently delivering surplus will gradually raise the bar, but a single large overprovision does not produce a permanent large increase.

**Strategic implication**: do not demonstrate more than you can sustain. A Luminary who sees abundant expression of their domains one period will expect something closer to that level in the next. The expectation is re-derived each evaluation from whatever the previous period actually produced, so there is no permanent "ratchet" from a single spike, but sustained overdelivery compounds.

### Declining expectations (the relief valve)

If a Luminary falls short of their threshold for two consecutive evaluation periods, their raised expectation decreases by 0.10 and the shortfall counter resets:

```
if consecutive_shortfalls >= 2:
    raised = max(0.0, raised - 0.10)
    consecutive_shortfalls = 0
```

The raised amount never falls below 0.0, so expectations never drop below the base threshold. This is a slow process: recovering from a significantly raised expectation requires many evaluation periods of sustained shortfall. The shortfall counter resets on any period where the threshold is met, so alternating good and bad periods do not trigger the reduction.

---

## Satisfaction and Disposition

At each evaluation, the Luminary's period production is compared against their current threshold and against the previous period's production. Four outcomes:

| Above threshold | Growing vs. last period | Disposition delta (results axis) |
|---|---|---|
| Yes | Yes | +0.05 |
| Yes | No | 0.00 |
| No | Yes | 0.00 |
| No | No | -min(0.10, deficit x 0.05) |

Only the case where both conditions fail produces a negative delta. The penalty scales with how far below the threshold production fell, capped at -0.10 per evaluation. A near-miss produces only a small penalty; a large shortfall produces the maximum.

The satisfaction delta is applied to the **results** axis of the Luminary's disposition, alongside domain alignment and other evaluation factors.

---

## Design Notes

**Two separate Essence streams.** Passive domain claiming and active Underreal harvesting (`harvest_essence`) are fully independent. The passive system is invisible to Luminaries as a source of suspicion; the active system can be hidden but carries concealment risk.

**Uncontested domains are most profitable.** In a heavily contested domain (combined Luminary affinity 0.8+), the Demiurge receives less than 10% passively. In a domain no Luminary holds at all, the Demiurge claims 100%. Choosing affiliated domains that diverge from Luminary portfolios therefore yields more passive income, even if it gives the Demiurge less leverage over Luminary satisfaction.

**All tuning parameters live in `TickConfig`.** `essence_location_weight`, `essence_mortal_weight`, `essence_claiming_exponent`, `luminary_essence_baseline_rate`, `luminary_essence_decay`, `luminary_essence_recall`.
