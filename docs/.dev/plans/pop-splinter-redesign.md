> status: parked | last updated: 2026-05-31

# Pop Splinter Redesign: Probabilistic, Divergence-Scaled Schisms

## Goal

Replace the current deterministic per-tick splinter check with a probabilistic stride-gated system, and replace the fixed 35% splinter fraction with a divergence-scaled one. Add a post-split belief nudge on the parent, and a civ-scale modifier on the divergence threshold. The result is a system where social schisms are organic events that build over time rather than automatic hair-triggers.

**Context:** Current behavior splits any eligible pop every tick the moment divergence crosses 0.50, producing cascading chains of identical-belief splinters. The cooldown added in `14116a0` is a stopgap only — after 10 ticks, the conditions are identical and the cascade resumes.

---

## Design

### Problem with the current approach

The deterministic check means divergence never gets a chance to grow beyond the threshold. A pop crosses 0.50 and immediately loses 35% of its people, forever, every 10 ticks. The splinter inherits the same beliefs, meets the same condition, and the chain continues until pops are too small to split.

### The new model

Four interlocking changes:

**1. Stride-gated probabilistic check**

`_check_pop_splinters` runs only every `SPLINTER_CHECK_STRIDE` ticks. When it runs, each eligible pop passes through a probability gate — not a deterministic threshold. The probability is a sigmoid function of divergence:

```
P(split) = sigmoid(SPLINTER_PROB_STEEPNESS × (divergence − SPLINTER_PROB_MIDPOINT))
```

Suggested parameters:
- `SPLINTER_CHECK_STRIDE = 10`
- `SPLINTER_PROB_MIDPOINT = 0.70`  (50% chance of splitting at this divergence)
- `SPLINTER_PROB_STEEPNESS = 15.0`

Approximate probabilities per check:

| Divergence | P(split per check) | Avg ticks to split |
|---|---|---|
| 0.50 (threshold) | ~5% | ~200 ticks |
| 0.60 | ~18% | ~56 ticks |
| 0.70 | ~50% | ~20 ticks |
| 0.80 | ~82% | ~12 ticks |
| 0.90 | ~97% | ~10 ticks |

This means low divergence is a slow background pressure that occasionally tips over, while high divergence is nearly guaranteed to split within a few checks.

**2. Divergence-scaled splinter fraction**

Instead of a fixed 35%, the splinter takes a fraction proportional to how severe the disagreement is. A barely-divergent pop sheds a small fringe; a deeply opposed pop loses nearly half its people.

```python
span  = divergence - SPLINTER_DIVERGENCE_THRESHOLD
scale = span / (1.0 - SPLINTER_DIVERGENCE_THRESHOLD)   # normalize to [0, 1]
fraction = SPLINTER_MIN_FRACTION + scale * (SPLINTER_MAX_FRACTION - SPLINTER_MIN_FRACTION)
```

Suggested parameters:
- `SPLINTER_MIN_FRACTION = 0.10`  (10% at threshold — small fringe)
- `SPLINTER_MAX_FRACTION = 0.45`  (45% at max divergence — near-even split)

At divergence 0.70: fraction ≈ 27%. At divergence 0.90: fraction ≈ 38%.

The log-space deltas become:
```python
_splinter_delta = math.log10(fraction)
_parent_delta   = math.log10(1.0 - fraction)
```

These replace the current module-level constants `_SPLINTER_SIZE_DELTA` and `_SPLINTER_PARENT_DELTA`.

**3. Post-split belief nudge on parent**

After a split, the parent represents the people who stayed — the more conformist remainder. Their beliefs should shift slightly toward the civ's `established_beliefs`, proportional to how large the departing faction was (bigger split = more deviants left = bigger shift).

```python
nudge = fraction * SPLINTER_BELIEF_NUDGE_FACTOR
for tag, val in parent_pop.dominant_beliefs.items():
    civ_val = civ.established_beliefs.get(tag, 0.0)
    parent_pop.dominant_beliefs[tag] = val + (civ_val - val) * nudge
```

Suggested parameter:
- `SPLINTER_BELIEF_NUDGE_FACTOR = 0.5`  (at max 45% fraction, nudge is 22.5% of the gap)

This means the cascade naturally self-limits: after the parent sheds its deviants and nudges toward establishment beliefs, its divergence drops. If it drops below threshold, no further splits. If it remains above threshold, it will eventually split again — but less severely each time.

The splinter itself keeps the original beliefs (it IS the deviant faction), so it remains divergent. Whether it continues to split depends on its size and the probability function — and because each generation is smaller than the last, eventually they fall below `SPLINTER_MIN_SIZE` and the chain ends.

**4. Civ-scale modifier on divergence threshold**

Larger, more centralized civilizations have institutions that detect and expel deviant groups earlier. Smaller, looser civilizations tolerate more deviation before a schism crystallizes. This is modeled as a scale-dependent offset to the effective threshold used in the probability sigmoid.

```python
_CIV_SCALE_SPLINTER_OFFSET: dict[str, float] = {
    "nascent":        +0.20,   # very loose, high tolerance
    "tribal":         +0.15,
    "city_state":     +0.08,
    "regional":       +0.03,
    "continental":     0.00,   # baseline
    "planetary":      -0.03,
    "interplanetary": -0.06,
    "interstellar":   -0.10,
    "intergalactic":  -0.15,   # near-total conformity enforcement
}
```

The effective midpoint becomes:
```python
scale_offset = _CIV_SCALE_SPLINTER_OFFSET.get(civ.scale.value, 0.0)
effective_midpoint = SPLINTER_PROB_MIDPOINT + scale_offset
P = sigmoid(SPLINTER_PROB_STEEPNESS × (divergence − effective_midpoint))
```

A NASCENT civ needs divergence of ~0.90 before a split becomes likely. An INTERSTELLAR civ splits pops at ~0.55. This captures both framings from the design discussion: smaller civs lack infrastructure to maintain large deviant pops (less enforcement) AND smaller civs can't centrally prevent deviant beliefs from forming (higher effective tolerance).

`PRE_SAPIENT` and `NON_SENTIENT` skip the splinter check entirely — no social dynamics.

---

## Implementation

### Changes to `logic/tick_logic.py`

**Replace constants:**
```python
# Remove
SPLINTER_FRACTION    = 0.35
_SPLINTER_SIZE_DELTA = math.log10(SPLINTER_FRACTION)
_SPLINTER_PARENT_DELTA = math.log10(1.0 - SPLINTER_FRACTION)

# Add
SPLINTER_CHECK_STRIDE       = 10
SPLINTER_MIN_FRACTION       = 0.10
SPLINTER_MAX_FRACTION       = 0.45
SPLINTER_BELIEF_NUDGE_FACTOR = 0.5
SPLINTER_PROB_MIDPOINT      = 0.70
SPLINTER_PROB_STEEPNESS     = 15.0

_CIV_SCALE_SPLINTER_OFFSET: dict[str, float] = { ... }
```

**Replace `_check_pop_splinters`:**
- Gate the entire method on `state.tick_number % SPLINTER_CHECK_STRIDE == 0`
- Use `self._rng.random() < probability` for the gate
- Compute `fraction` from divergence
- Compute log-space deltas from `fraction`
- Apply belief nudge to parent after splinter object is created
- Pass `fraction`-derived deltas into splinter size and mutation handler

**Update mutation handler** (`_apply_mutations`, `MutationType.POP_SPLINTER`):
- `_SPLINTER_PARENT_DELTA` is now dynamic; pass it via the `StateMutation` (add a `delta` field or encode in the mutation's `new_value`)
- OR: apply the parent size reduction directly in `_check_pop_splinters` before emitting the mutation (simpler — the parent shrinks immediately, splinter is registered via mutation)

The simplest approach: shrink `parent_pop.size_fractional` directly in `_check_pop_splinters` (before the mutation is emitted), and only use the mutation to register the new splinter Pop into state. This avoids threading the dynamic delta through the mutation system.

---

## Files affected

| File | Change |
|---|---|
| `logic/tick_logic.py` | Replace splinter constants, rewrite `_check_pop_splinters`, update mutation handler |

---

## Notes

- The `SPLINTER_COOLDOWN_TICKS = 10` on both parent and splinter stays. The probabilistic check and the cooldown are complementary — cooldown prevents immediate re-split after a schism; probability prevents the check from firing too eagerly in general.
- The splinter's beliefs are NOT adjusted — it represents the deviant faction as it was. Only the parent nudges toward establishment.
- The `child_pop_ids` guard (`if pop.child_pop_ids: continue`) should be revisited after this change. Currently it prevents any pop with children from ever splitting again. With the new model, that may be too restrictive — a pop that has already split could later diverge enough to split again. Consider removing it and relying solely on cooldown + probability.
- Tune parameters against the Warden's Compact scenario. Key things to watch: frequency of splinter events in the log, number of persistent micro-pops accumulating in the world state, and whether the parent's belief nudge is strong enough to close divergence within a reasonable timeframe.
- This plan does not touch the splinter narrative format — the existing `§pop§`, `§domain§` sentinels are already correct.
