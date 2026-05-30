> [← CLAUDE.md](../../CLAUDE.md)

# Linked Pops

_Last updated: 2026-05-29. All constants live in `logic/sim_utils.py`._

---

Two Pops can be **linked** when they represent the same demographic in different circumstances — same stratum and often same occupation, but separated by location or political affiliation. Links are the plumbing for future mechanics: migration, cross-location cultural influence, event propagation between connected communities.

Current use case: Neran Surface ↔ Neran Orbital Ring Pop pairs in the Warden's Compact scenario.

---

## Data model

`Pop.linked_pop_ids: dict[str, float]` — keys are pop ID strings; values are the **base link factor** (0.0–1.0). The dict is **asymmetric by design**: each Pop stores its own perspective independently. A link between Pop A and Pop B requires entries in both A's and B's dicts; the base factors may differ.

---

## Computed link factor (`compute_link_factor`)

```
lf = clamp(base + stratum_bonus + occupation_bonus + LINK_COSINE_WEIGHT × cosine, 0.0, 1.0)
```

| Component | Value | Condition |
|---|---|---|
| `stratum_bonus` | +0.05 | both Pops share the same `social_class` |
| `occupation_bonus` | +0.10 | both Pops share the same `occupation` string |
| `LINK_COSINE_WEIGHT × cosine` | up to +0.20 | cosine similarity of `{**dominant_beliefs, **culture_tags}` vectors |

`rider_traits` are deliberately excluded from the cosine vector — they are preaching artifacts, not core identity.

---

## Link drift (`_process_link_drift`)

Fires every **17 ticks** (`LINK_DRIFT_STRIDE`). Co-prime with the 10-tick conformity stride to avoid tick stacking.

For each linked pair `(pop, other_pop, base)`:

1. Compute cosine similarity of the merged belief+culture vectors.
2. Lerp the base: `new_base = base + (cosine − base) × LINK_DRIFT_RATE (0.008)`.  
   Half-life ≈ 87 strides (~1,474 ticks).
3. Compute `lf = compute_link_factor(pop, other_pop, new_base)`.
4. If `lf < LINK_BREAK_THRESHOLD (0.16)`: remove the link entry. Emit a `NarrativeEvent` only if at least one Pop is `pinned`.
5. Otherwise: write `new_base` back to `pop.linked_pop_ids`.

Both Pops' bases drift independently toward the same cosine target, preserving asymmetry throughout the lifecycle.

**Why 0.16 threshold:** the structural floor for same-stratum + same-occupation is 0.05 + 0.10 = 0.15. At `base=0.0` and `cosine=0.0`, computed lf = 0.15 < 0.16, so structural links can dissolve after extreme cultural divergence has eroded the base to near zero. Intentional.

---

## Whisper / Shape Dream cascade

Linked-pop cascade fires from every call to `_emit_whisper_splash` (Whisper action, Shape Dream action, Whisper echo).

### Co-located linked Pops (same world)

When a world-splash Pop `sp` is found in `src_pop.linked_pop_ids`, normal splash mechanics are **replaced**:

```
splash_delta = vec.direction × per_unit_delta × WHISPER_POP_SPLASH × lf × influence
```

Resistance, distance factor, and domain receptivity are all bypassed — the link relationship overrides social-boundary factors. `emit_lineage_bleed` is still called (co-location preserves within-world heritage).

### Cross-world linked Pops

After the world-splash loop, `_emit_linked_pop_belief_cascade` sends mutations to each linked Pop that is **not** on the mortal's world:

```
cascade_delta = vec.direction × per_unit_delta × WHISPER_POP_SPLASH × lf × cascade_scale
```

| Context | `cascade_scale` |
|---|---|
| Source is mortal's own Pop | `LINK_SPLASH_OWN_POP_SCALE = 0.80` |
| Source is any other world Pop | `LINK_SPLASH_WORLD_POP_SCALE = 0.40` |

Resistance, distance, and receptivity are bypassed here too — cross-world reach is the intended benefit. `emit_lineage_bleed` is **not** called from the cross-world cascade: lineage bleed is a within-world heritage mechanic.

Cascade depth is structurally bounded to 1: `_emit_linked_pop_belief_cascade` only emits `StateMutation` objects and never re-enters `_emit_whisper_splash`.

### Visibility cascade

After `emit_influence_visibility_splash` boosts Pop visibility from an influence action, the same linked-Pop cascade pattern fires for visibility:

```
vis_delta = boost × lf × LINK_VISIBILITY_CASCADE_SCALE (0.60)
```

Applied as `new_value = min(1.0, lp.visibility + vis_delta)`. `emit_upward_visibility_splash` is not called for cascade Pops — no world-hierarchy resolution is needed for cross-world links.

---

## TravelIntent milieu

When a mortal arrives at a destination with no explicit `target_pop_id`, `_default_arrival_milieu` uses this priority order:

1. Mortal's own Pop is at the destination → use it.
2. A Pop linked to the mortal's origin Pop is at the destination → use the one with the highest computed link factor. FERAL/WILD filter is not applied for this step — an explicit link overrides social-class aversions.
3. Same occupation match among filtered/sorted candidates.
4. Same stratum match.
5. Closest stratum within 2 steps (WARRIOR has a special fallback order: COMMON > TRADER > ARTISAN).
6. `None`.

See `mortal-system.md` for the full `pop_milieu` field description.

---

## Constants summary

| Constant | Value | Purpose |
|---|---|---|
| `LINK_STRATUM_BONUS` | 0.05 | flat bonus for shared stratum |
| `LINK_OCCUPATION_BONUS` | 0.10 | flat bonus for shared occupation |
| `LINK_COSINE_WEIGHT` | 0.20 | max cosine contribution |
| `LINK_DRIFT_RATE` | 0.008 | per-stride base lerp rate |
| `LINK_BREAK_THRESHOLD` | 0.16 | computed lf below this → link dissolves |
| `LINK_DRIFT_STRIDE` | 17 | ticks between drift passes |
| `LINK_SPLASH_OWN_POP_SCALE` | 0.80 | cross-world cascade scale from own Pop |
| `LINK_SPLASH_WORLD_POP_SCALE` | 0.40 | cross-world cascade scale from other world Pops |
| `LINK_VISIBILITY_CASCADE_SCALE` | 0.60 | visibility cascade scale |
