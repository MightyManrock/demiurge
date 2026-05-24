> **Status:** active
> **TO-DO ref:** —
> **Last updated:** 2026-05-24

## Goal

Improve the visibility system with four targeted changes:

1. Lower the "in Window" floor from `0.05` to `0.005` to retain more visibility across the longer tick cadence.
2. Splinter Pops inherit `parent.visibility × 0.75` instead of `× 0.5`.
3. **Omen visibility splash** — a successful Manifest Omen sets the target world's visibility to `1.0` and boosts all above-floor mortals and Pops on that world by `0.6 × (pop_location.distance_from_core + 1)`, capped at `1.0`.
4. **Whisper / Shape Dream visibility splash** — in addition to the existing belief splash, these actions boost the target mortal's own Pop's visibility by `+0.8` and all other Pops in the same `SignificantLocation` by `0.6 / (pop_location.distance_from_core + 1)`, capped at `1.0`. Only Pops already above the visibility floor are affected.

---

## Phases

### Phase 1: Floor + splinter (trivial)

**1a — Lower visibility floor**
- `logic/tick_logic.py`: Change `ENTITY_VISIBILITY_FLOOR = 0.05` → `0.005`
- Verify `is_in_window()` usage is consistent (it uses this constant directly)
- Run `--autoplay` regression

**1b — Splinter pop inheritance**
- `logic/tick_logic.py`: Change `visibility=max(0.0, pop.visibility * 0.5)` → `× 0.75` at both splinter-creation sites (Pop splinter and Imago goal-pop)
- Run `--autoplay` regression

---

### Phase 2: Omen visibility splash

**2a — World visibility refresh on Omen**
- `logic/tick_logic.py`, near the generic visibility-refresh block (line ~2313): Add a parallel branch for `instance.target_type == TargetType.LOCATION` that emits a `MORTAL_VISIBILITY` (or equivalent entity visibility) mutation setting the target location's visibility to `1.0`.
- Currently this block is mortal-only; Omen targets `SignificantLocation` and gets nothing.

**2b — Omen pop/mortal splash**
- `logic/tick_logic.py`, inside the `OmenIntent` resolution (line ~3746), after the existing pop loop on success:
  - Add a new helper `_emit_omen_visibility_splash(mutations, state, world_id)`:
    - Iterate every `PopLocation` on the world
    - For each PopLocation, compute `boost = min(1.0, 0.6 * (loc.distance_from_core + 1))`
    - For each Pop at that PopLocation whose `visibility > ENTITY_VISIBILITY_FLOOR`: emit a visibility delta mutation clamping to `[0.0, 1.0]`
    - For each mortal whose `current_location` resolves to that PopLocation and whose `visibility > ENTITY_VISIBILITY_FLOOR`: emit a mortal visibility delta mutation
  - Call this helper when `outcome != FAILURE` (matches the existing omen pass-check guard)
- Run `--autoplay` regression

---

### Phase 3: Whisper / Shape Dream visibility splash

**3a — Visibility splash helper**
- `logic/tick_logic.py`: Add `_emit_influence_visibility_splash(mutations, state, mortal, world_id)`:
  - Find the mortal's `PopLocation` (their `current_location`)
  - Boost own Pop's visibility by `+0.8`, capped at `1.0` — only if `pop.visibility > ENTITY_VISIBILITY_FLOOR`
  - For every other Pop on the same world:
    - Find that Pop's PopLocation; get `distance_from_core`
    - `boost = 0.6 / (distance_from_core + 1)`
    - Only apply if `pop.visibility > ENTITY_VISIBILITY_FLOOR`
    - Emit visibility delta mutation clamped to `[0.0, 1.0]`

**3b — Wire into Whisper and Shape Dream**
- `logic/tick_logic.py`, inside `_resolve_intent_mutations` at the Whisper branch (line ~3421) and Shape Dream branch (line ~3497):
  - After the existing belief/culture mutations are appended, call `_emit_influence_visibility_splash(...)`
  - Only fire on non-FAILURE outcomes (consistent with belief splash guard)
- The existing `_emit_whisper_splash` is for belief/culture; this is a separate visibility-only helper
- Run `--autoplay` regression

---

## Files affected

- `logic/tick_logic.py` — all changes; `ENTITY_VISIBILITY_FLOOR`, splinter sites, omen resolution, influence resolution, new helper(s)

## Notes

- "Above floor" guard (`visibility > ENTITY_VISIBILITY_FLOOR`) intentionally excludes invisible entities — these splashes represent the Demiurge's *attention* rippling through already-observable space, not new discovery.
- Omen splash boost formula `0.6 × (distance_from_core + 1)` means: distance 0 → +0.6, distance ≥ 1 → capped at 1.0 (full visibility). This reflects an omen manifesting world-wide with increasing force in peripheral regions.
- Whisper/Shape Dream boost formula `0.6 / (distance_from_core + 1)` is inverse: nearby communities are more affected than distant ones.
- No new mutation types needed — mortal visibility uses `MORTAL_VISIBILITY` with `new_value` or `delta`; entity (pop/location) visibility uses the existing delta-apply path.
