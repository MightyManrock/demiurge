> [← CLAUDE.md](../../CLAUDE.md)

# Influence Actions: Whisper, Shape Dream, Omen

All three carry an Imago's full mechanics — both `domain_vectors` and `culture_vectors`. Domain shifts route through `*_BELIEF_SHIFT`, culture shifts through `*_CULTURE_SHIFT`. Handlers live in `_resolve_intent_mutations`; the 4-tick echo path is `_process_active_events`.

## Success Roll (Whisper and Shape Dream)

Both actions use the influence roll instead of the standard reliability tier:

```
success_chance = clamp(0.75 + puissance×0.15 + visibility×0.05 + framing_resonance×0.04, 0.75, 0.99)
```

- **Floor 0.75** — even a weak Demiurge targeting an unknown mortal with mismatched Framing succeeds ~75% of the time.
- **Ceiling 0.99** — unreachable in normal play; rewards a maxed-out Demiurge.
- `framing_resonance` is clamped to `[0, 1]` here. AMBIGUOUS Framing contributes 0 (unlike Manifest Omen, there is no explicit penalty).
- Outcome bands: `< success_chance` → SUCCESS; `< success_chance + 0.15` → PARTIAL; else → FAILURE.

See `_roll_influence()` in `tick_logic.py` and the Puissance section in `action-system.md` for the full formula.

## Whisper (`WhisperIntent`)

Targets a single mortal. Immediate effect: `effectiveness = (1.0 SUCCESS | 0.4 PARTIAL) × mortal.alignment` scales every downstream shift. Emits `MORTAL_BELIEF_SHIFT` / `MORTAL_CULTURE_SHIFT` on the target, plus a `WHISPER` `RAMP_FADE` event (`duration=4`, `peak_offset=1`) that echoes the same shifts for 3 more ticks.

**Pop splash** (`_emit_whisper_splash`): ripples to Pops on the mortal's world. Per-Pop delta = `vec.direction × per_unit_delta × WHISPER_POP_SPLASH(0.20) × receptivity × resistance × dist_factor × influence`. `influence` is prominence-derived: own-Pop = `WHISPER_OWN_POP_BASE_INFLUENCE(0.5) + prominence × WHISPER_OWN_POP_PROMINENCE_GAIN(2.0)`; cross-Pop = `prominence × WHISPER_CROSS_POP_PROMINENCE_GAIN(1.5)`. Culture-vector splash skips the domain-receptivity term.

**Linked-pop override**: if a world-splash Pop is linked to the mortal's origin Pop, resistance, distance factor, and receptivity are replaced by the computed link factor — `vec.direction × per_unit_delta × WHISPER_POP_SPLASH × lf × influence`. After the world loop, `_emit_linked_pop_belief_cascade` sends a scaled copy to each linked Pop that is *off-world*. Visibility from `emit_influence_visibility_splash` cascades to linked Pops similarly. See [linked-pops.md](linked-pops.md) for full details and constants.

## Shape Dream (`ShapeDreamIntent`)

Targets a mortal with **two Imagines from different Domain trees**. At resolution one Imago is randomly **boosted ×1.15** and the other **suppressed ×0.60**. Combine rules (`_combine_shape_dream_vectors`): multiplier applies only to positive-direction entries; for a tag in both Imagines, two positives take the mean, anything else sums. Otherwise resolves exactly like a Whisper (same splash, same 4-tick echo).

## Manifest Omen (`OmenIntent`) — "shotgun" interpretation

**Essence cost: 2.0** (20× Whisper). Targets an entire world including invisible Pops and mortals — the AoE scope and guaranteed activation justify the premium over single-target influence actions.

Targets a world. Every Pop and every active mortal on it runs the shotgun resolver (`_resolve_omen_target`):

- Effect `E` = the omen's vectors scaled by `OMEN_BASE(0.35)`. A Pop runs `n = max(1, size_magnitude)` interpretation checks; a mortal runs 1. Subdivided component `e = E/n`.
- Each check rolls `rng.random() < pass_prob`. **Pass** → adds `e` to the true tags. **Fail** → adds `e`'s magnitudes to random same-category substitute tags. Total magnitude is conserved; only coherence degrades.
- `pass_prob = base(0.55 SUCCESS | 0.35 PARTIAL) + framing_resonance×0.25 + (receptivity−1)×0.20 + (cohesion−0.5)×0.20`, minus `0.15` for `AMBIGUOUS` framing, clamped `[0.05, 0.95]`.
- Multiplied by `_pop_distance_factor` (`0.7^|distance|`).

The belief/culture shotgun resolves **once**. The `OMEN` `SPIKE_FADE` event emits but carries no vectors — only the `divine_awareness` + Luminary-attention ripple over 5 ticks.
