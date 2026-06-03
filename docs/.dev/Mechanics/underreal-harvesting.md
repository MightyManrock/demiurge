> [← CLAUDE.md](../../CLAUDE.md)

# Underreal Harvesting

The Underreal is a secondary Essence source beyond what you passively gather from Domain affinities. Harvesting Essence from the Underreal is risky and must be hidden from Luminaries.

## EssenceStockpile model (`core/action_core.py`)

| Field | Type | Meaning |
|---|---|---|
| `actual` | float | True Essence held. |
| `suspicious` | float | Portion Luminaries can attribute to non-sanctioned sources. Always `≤ actual`. |
| `concealment_integrity` | float [0,1] | How well the hidden Essence is concealed. 1.0 = perfectly hidden; degrades over time and under Luminary scrutiny. |

Luminaries evaluate `suspicious`, not `actual`. The gap (`actual − suspicious`) is what the player is successfully hiding.

`exposure_risk()` gives a rough audit-detection probability: `(hidden / actual) × (1 − concealment_integrity)`.

## Harvest Essence action

**Key:** `harvest_essence` | **Reliability:** `probable` (75% SUCCESS, 15% PARTIAL, ~10% FAILURE) | **Tag:** `always_persist` (never prompts "once or repeat?")

### Yield formula

```
base_yield = 3.0
base_yield *= 0.5   # if PARTIAL outcome

actual_yield   = base_yield × (1.0 − concealment_priority × 0.5)
suspicious_leak = base_yield × (1.0 − concealment_priority) × 0.5
```

`concealment_priority` is a per-harvest player setting [0.0, 1.0]:
- **0.0** (risky) — max yield (3.0) / max leak (1.5) per SUCCESS
- **1.0** (safe) — min yield (1.5) / zero leak per SUCCESS
- **FAILURE** — no yield, no leak

`actual_yield` is added to `essence.actual`; `suspicious_leak` is added to `essence.suspicious`.

## Laundering mechanic (`logic/tick_logic.py` — `_apply_mutations`)

Whenever actual Essence is spent (any negative `ESSENCE_CHANGE` on `field="actual"`), suspicious Essence is passively drained proportionally:

```
spend            = abs(delta)
ratio            = suspicious / (actual + spend)   # pre-spend ratio
noise            = uniform(−0.15, +0.15)
drain            = spend × ratio × (1 + noise)
drain            = clamp(drain, 0, suspicious)
suspicious      -= drain
```

This means spending Essence naturally "launders" the suspicious portion over time. The player cannot control how much of each spend comes from the suspicious pool — it tracks the current ratio with mild randomness.

## Auto-stop conditions (`EssenceHarvestIntent`)

The harvest can be configured to pause automatically when any of these thresholds is crossed (checked at the top of each resolution, before yield math):

| Field | Triggers when |
|---|---|
| `stop_at_suspicious: Optional[float]` | `essence.suspicious ≥ value` |
| `stop_at_integrity_below: Optional[float]` | `essence.concealment_integrity < value` |
| `stop_at_stockpile: Optional[float]` | `essence.actual ≥ value` |

When a condition triggers, `OngoingAction.repeating` is set to `False` and a "Harvest paused: {reason}." narrative is emitted. No yield or leak mutations are applied that tick.

## Concealment integrity

`concealment_integrity` is not directly affected by harvesting — it degrades from Luminary scrutiny, Herald investigation, and passage of time without maintenance. The `maintain_concealment` action (`SELF_REFINEMENT`) is the primary way to restore it. Low integrity amplifies how much of the hidden stockpile is exposed during an audit.

## Last harvest tracking

`SimulationState` tracks `last_harvest_amount` and `last_harvest_tick` (set on each successful/partial harvest). The StatusTab displays the last harvest result for 30 ticks after it occurs.
