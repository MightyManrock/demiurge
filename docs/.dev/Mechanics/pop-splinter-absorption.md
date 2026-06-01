# Pop Splitting and Reabsorption

Pops can spontaneously split into two factions when their beliefs diverge too far from their civilization's established beliefs. Over time, a splinter that converges back toward the civ can be gradually reabsorbed. Both mechanics run in `logic/tick_logic.py` on a shared stride.

---

## Splinter check (`_check_pop_splinters`)

### When it runs

The check is **stride-gated**: it only fires when `state.tick_number % SPLINTER_CHECK_STRIDE == 0` (every 10 ticks by default). This allows divergence to accumulate between checks rather than being cut off the moment it crosses the threshold.

### Eligibility gates (all must pass)

| Gate | Value |
|---|---|
| `asset_crew_for is None` | Vessel crew pops are permanently exempt |
| `splinter_cooldown == 0` | 10-tick cooldown after any split (applies to both parent and new splinter) |
| `size_fractional >= SPLINTER_MIN_SIZE` | Minimum viable size (4.0, ≈ 10,000 people) |
| `civilization_id` set | Must belong to a civilization |
| `civ.established_beliefs` non-empty | Civ must have an aggregate belief profile |
| `divergence >= SPLINTER_DIVERGENCE_THRESHOLD` | Cosine divergence ≥ 0.50 |

`divergence = 1.0 - cosine_similarity(pop.dominant_beliefs, civ.established_beliefs)`

### Probabilistic gate

Crossing the threshold does **not** guarantee a split. Each eligible pop is run through a sigmoid probability function:

```
P(split) = sigmoid(SPLINTER_PROB_STEEPNESS × (divergence − effective_midpoint))
```

where `effective_midpoint = SPLINTER_PROB_MIDPOINT + civ_scale_offset`.

| Divergence | P(split per check) | Mean ticks to split |
|---|---|---|
| 0.50 (threshold) | ~5% | ~200 ticks |
| 0.60 | ~18% | ~56 ticks |
| 0.70 | ~50% | ~20 ticks |
| 0.80 | ~82% | ~12 ticks |
| 0.90 | ~97% | ~10 ticks |

### Civilization scale modifier (`_CIV_SCALE_SPLINTER_OFFSET`)

Larger, more centralized civs enforce conformity earlier. The offset shifts the sigmoid midpoint:

| Scale | Offset | Effect |
|---|---|---|
| `nascent` | +0.20 | Very high tolerance — needs ~0.90 divergence for 50% chance |
| `tribal` | +0.15 | High tolerance |
| `city_state` | +0.08 | Moderate tolerance |
| `regional` | +0.03 | Slight tolerance |
| `continental` | 0.00 | Baseline |
| `planetary` | −0.03 | Slight pressure |
| `interplanetary` | −0.06 | Moderate pressure |
| `interstellar` | −0.10 | Strong enforcement |
| `intergalactic` | −0.15 | Near-total conformity enforcement |

### Splinter size (divergence-scaled)

The fraction of the parent's population that breaks away scales linearly with divergence:

```
fraction = SPLINTER_MIN_FRACTION + (divergence − threshold) / (1 − threshold) × (MAX − MIN)
```

- At threshold (0.50): **10%** breaks away — a small fringe
- At max (1.00): **45%** breaks away — a near-even split

Parent shrinks by `log10(1 − fraction)` in log-space; splinter gets `original_size + log10(fraction)`. Population is conserved.

### Post-split belief adjustment

1. **Original beliefs captured** before any mutation
2. **Parent shrunk** in-place
3. **Parent beliefs nudged** toward `civ.established_beliefs`: `Δ = (civ_val − pop_val) × fraction × SPLINTER_BELIEF_NUDGE_FACTOR (0.5)`
4. **Splinter created** with the captured pre-nudge beliefs — it is the deviant faction, frozen at the moment of schism

### Mortal redistribution

After the split, each `NotableMortal` in the parent's `notable_mortal_ids` is checked. Their `belief_tags` are compared (cosine similarity) against both the nudged parent and the splinter's beliefs. Mortals more similar to the splinter move to it — `pop_id` updated, transferred between `notable_mortal_ids` lists. A narrative event fires if both the mortal and the parent pop are in-Window (always shown in dev mode).

---

## Reabsorption check (`_check_pop_reabsorption`)

### When it runs

Same stride as the splinter check (`SPLINTER_CHECK_STRIDE`). Runs immediately after splinter check in the tick loop.

### Eligibility gates

| Gate | Meaning |
|---|---|
| `asset_crew_for is None` | Vessel crew exempt |
| `preaching_imago_id is None` | Pops actively targeted by Preach Imago are protected |
| `size_fractional < SPLINTER_MIN_SIZE + 1.0` | Only small pops near minimum size are candidates |
| Target found with `cosine_similarity >= REABSORPTION_CONVERGENCE_THRESHOLD (0.85)` | Beliefs must have converged sufficiently |

### Target selection (`_find_reabsorption_target`)

1. **Parent first**: if `parent_pop_id` is set and the parent is alive, in the same location, same stratum and occupation, and larger → use it
2. **Best local match**: otherwise, find the pop in the same location with matching stratum and occupation, higher `size_fractional`, and highest cosine similarity above the convergence threshold

Target must also not be a vessel crew pop or Preach Imago goal.

### Drain mechanics

Each check, **20% of the source's current population** is transferred to the target (log-space, population-conserving):

```python
delta_source = log10(1 - REABSORPTION_DRAIN_FRACTION)   # ≈ −0.097 per check
delta_target = log10(10^target + 10^source × fraction) − target
```

Emitted as two `POP_SIZE_CHANGE` mutations.

### Final absorption

When `new_source_size < SPLINTER_MIN_SIZE`, the source is fully absorbed on that stride:
- The **full remaining population** (not just the 20% fraction) is transferred to the target via a single `POP_SIZE_CHANGE`
- A `POP_ABSORBED` mutation handles lineage cleanup: removes the source from `civ.pop_ids`, `PopLocation.pop_ids`, transfers `notable_mortal_ids` to the target
- Narrative event emitted (same window rules as splinter events)

---

## Key constants (all in `logic/tick_logic.py`)

| Constant | Value | Meaning |
|---|---|---|
| `SPLINTER_CHECK_STRIDE` | 10 | Ticks between splinter/reabsorption checks |
| `SPLINTER_DIVERGENCE_THRESHOLD` | 0.50 | Minimum cosine divergence to be eligible |
| `SPLINTER_MIN_SIZE` | 4.0 | Minimum log-space size to split (≈ 10,000 people) |
| `SPLINTER_COOLDOWN_TICKS` | 10 | Post-split cooldown on both parent and splinter |
| `SPLINTER_MIN_FRACTION` | 0.10 | Smallest splinter (at threshold divergence) |
| `SPLINTER_MAX_FRACTION` | 0.45 | Largest splinter (at maximum divergence) |
| `SPLINTER_PROB_MIDPOINT` | 0.70 | Divergence at which P(split) = 50% |
| `SPLINTER_PROB_STEEPNESS` | 15.0 | Sigmoid steepness |
| `SPLINTER_BELIEF_NUDGE_FACTOR` | 0.50 | Parent nudge strength toward civ beliefs |
| `REABSORPTION_CONVERGENCE_THRESHOLD` | 0.85 | Cosine similarity required to begin drain |
| `REABSORPTION_DRAIN_FRACTION` | 0.20 | Fraction of source drained per check |

---

## Permanent exemptions

- **Vessel crew pops** (`asset_crew_for is not None`): exempt from both splitting and reabsorption. Crew composition is managed separately.
- **Wild civ pops** (`pre_sapient`, `non_sentient` scale): no `established_beliefs` on the civ, so the divergence check never triggers.

---

## Interaction with Preach Imago

The passive reabsorption check skips any pop with `preaching_imago_id` set (it is the active goal of a Proxius directive). The `POP_ABSORBED` mutation handler's Preach Imago side effects (clearing `preaching_imago_id`, unpinning, stamping cooldown) only fire when the *target* pop actually has `preaching_imago_id` set — organic reabsorptions do not trigger these.
