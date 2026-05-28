# Essence Satisfaction: Continuous Scoring — Design Spec

**Date:** 2026-05-21
**Scope:** (1) Replace binary above/below threshold check with ratio-based continuous scoring; (2) compute Luminary domain_production from the post-Demiurge-claim net pool
**Status:** Draft
**Affects:** `core/eval_core.py` — `evaluate_essence_satisfaction` and `EssenceSatisfaction`; `logic/tick_logic.py` — essence generation loop

---

## Problem

### 1. Binary satisfaction scoring

`evaluate_essence_satisfaction` currently uses two binary checks:

```python
above = domain_production >= threshold
growing = bool(production_log) and domain_production > production_log[-1]

if above and growing:   delta = 0.05
elif above or growing:  delta = 0.0
else:                   delta = -min(0.10, deficit * 0.05)
```

This means:
- **Stable good play produces zero results delta.** A Luminary sitting at 1.5× their threshold gives the same signal as one sitting at 1.001×.
- **The growth signal is binary.** A run producing 0.21, 0.22, 0.23 is "growing" at every tick, but so is one that spikes from 0.10 → 0.11 → 0.10 (technically). No proportionality to the magnitude of improvement.
- **The deficit penalty is too gentle.** `deficit * 0.05` for small deficits produces nearly zero penalty; only a severe shortage accumulates meaningful signal.

As a result, both the `results_tanker` and `results_builder` autoplay strategies produce the same `disposition.results` score, because the universe sits stably above threshold in both cases.

### 2. Luminary domain_production uses the gross pool

In `tick_logic.py`, `luminary_production_this_eval` is accumulated before the Demiurge claim is subtracted:

```python
# Current (lines 1758-1760):
state.luminary_production_this_eval[lid] = (
    state.luminary_production_this_eval.get(lid, 0.0) + lum_aff * pool  # gross pool
)
# dem_claim computed at line 1778 — after luminary accumulation
```

This means a Demiurge who drops affinity for a shared domain (yielding it entirely to the Luminary) gains nothing in satisfaction terms — the Luminary's `domain_production` was already calculated from the full pool. The strategic lever of *yielding a domain to boost a Luminary's essence income* is simply absent.

The fix: compute `dem_claim` before the per-Luminary accumulation loop, then use `net_pool = pool - dem_claim`. When the Demiurge drops or reduces affinity, `dem_claim` falls, `net_pool` rises, and `luminary_production_this_eval` increases accordingly.

**Strategic tension:** yielding a domain reduces the Demiurge's own essence income. A player who drops `domain:order` to boost Vrath's satisfaction must then find essence elsewhere to fund the actions needed to keep Vrath satisfied. This is the intended trade-off.

---

## Design

### Core Change: Ratio-Based Surplus/Deficit

Replace the binary check with a continuous `surplus_ratio`:

```python
surplus_ratio = (domain_production - threshold) / max(threshold, 0.001)
```

`surplus_ratio > 0` means production exceeded threshold; `< 0` means shortfall.

Map through a linear-with-clamp formula:

```python
base_delta = clamp(surplus_ratio * 0.12, -0.15, 0.06)
```

This gives:
- **+0.06** at `surplus_ratio ≥ 0.5` (50% above threshold — strong overperformance)
- **+0.03** at `surplus_ratio = 0.25` (25% above)
- **+0.01** at `surplus_ratio = 0.083` (barely above)
- **0.00** at threshold exactly
- **−0.05** at `surplus_ratio = −0.42` (42% below)
- **−0.15** at `surplus_ratio ≤ −1.25` (production essentially zero)

### Trajectory Modifier: Continuous Growth Signal

Replace the binary `growing` flag with a slope multiplier based on recent production log:

```python
if len(production_log) >= 2:
    # Average change per evaluation period over the log window
    slope = (production_log[-1] - production_log[0]) / len(production_log)
    # Normalize by threshold to make it scale-independent
    normalized_slope = slope / max(threshold, 0.001)
    trajectory_modifier = clamp(normalized_slope * 0.5, -0.02, 0.02)
else:
    trajectory_modifier = 0.0
```

The trajectory modifier adds at most ±0.02 on top of the base delta — enough to reward sustained growth or penalize sustained decline, without dominating the base signal.

### Net Pool: Demiurge Claiming as Strategic Lever

In the `universe_pool` iteration, compute `dem_claim` before the per-Luminary accumulation, then pass `net_pool` to it:

```python
# Compute dem_claim first
lum_fraction = lum_total_aff ** EXP if lum_total_aff > 0.0 else 0.0
dem_fraction = 1.0 - lum_fraction
dem_claim = pool * dem_fraction if tag in demiurge_affiliated else 0.0
net_pool = pool - dem_claim  # what Luminaries actually receive

# Then accumulate with net_pool
for lum in luminaries:
    lum_aff = min(0.8, lum.domains.get(tag, 0.0))
    if lum_aff <= 0.0:
        continue
    lid = str(lum.id)
    state.luminary_production_this_eval[lid] = (
        state.luminary_production_this_eval.get(lid, 0.0) + lum_aff * net_pool
    )
```

When `lum_total_aff == 0.0` the Luminary loop never runs (all affinities are zero), so the edge case requires no special handling. When the tag is not in `demiurge_affiliated`, `dem_claim = 0` and `net_pool = pool` — unchanged from current behavior.

### Final Delta

```python
delta = clamp(base_delta + trajectory_modifier, -0.15, 0.07)
```

### Updated `EssenceSatisfaction` Model

Replace `above_threshold: bool` and `growing: bool` with richer fields:

```python
class EssenceSatisfaction(BaseModel):
    luminary_id: UUID
    domain_production: float
    threshold: float
    surplus_ratio: float       # (production - threshold) / threshold
    trajectory_modifier: float # continuous slope signal, [-0.02, 0.02]
    disposition_delta: float
```

The `above_threshold` and `growing` booleans are dropped; they can be derived from `surplus_ratio > 0` and `trajectory_modifier > 0` if needed for display.

---

## Ask for Orders Report Update

The report currently prints:
```
Produced this period: 0.234  (surplus: +0.034)
```

Update to show:
```
Produced this period: 0.234  (surplus ratio: +23%)
Trajectory: +0.012 / period  (modifier: +0.01)
```

---

## Expected Impact on Tests

| Strategy | Before | After |
|---|---|---|
| `results_tanker` (passive) | Vrath `res` ≈ −0.03 | Vrath `res` similar (threshold satisfaction roughly the same) |
| `results_builder` (active dev) | Vrath `res` ≈ −0.03 | Vrath `res` should pull slightly positive over 50 ticks |
| `footprint_violator` (Omen spam) | n/a | No change (results separate from footprint) |

The difference between tanker and builder should become visible: builder's sustained Accelerate development actions push civ scale and civ-driven essence production, raising `surplus_ratio` over tanker's flat baseline.

---

## Files Affected

| File | Change |
|---|---|
| `core/eval_core.py` | Replace binary logic in `evaluate_essence_satisfaction`; update `EssenceSatisfaction` model |
| `logic/tick_logic.py` | (1) Compute `dem_claim` before luminary accumulation loop; use `net_pool` for `luminary_production_this_eval`. (2) Update Ask for Orders report to display `surplus_ratio` and trajectory. |

No schema changes. No new constraint types. Pure evaluation math.

---

## What This Does NOT Address

- **Civ stability/prosperity as explicit KPIs.** Those are still baked in indirectly through health-weighted domain profile and essence generation. A future `CivHealthConstraint` could surface them directly.
- **Threshold decay when underperforming.** The `raised_expectation` mechanism still only adds to the bar; it doesn't lower it when you've been below. That's a separate design question.
- **Per-domain surplus breakdown.** The surplus is aggregate; a Luminary that cares about `domain:conflict` specifically doesn't see a per-domain breakdown yet.
