> [← CLAUDE.md](../../CLAUDE.md)

# Influence Actions: Whisper, Shape Dream, Omen

All three carry an Imago's full mechanics — both `domain_vectors` and `culture_vectors`. Domain shifts route through `*_BELIEF_SHIFT`, culture shifts through `*_CULTURE_SHIFT`. Handlers live in `_resolve_intent_mutations`; the 4-tick echo path is `_process_active_events`.

## Whisper (`WhisperIntent`)

Targets a single mortal. Immediate effect: `effectiveness = (1.0 SUCCESS | 0.4 PARTIAL) × mortal.alignment` scales every downstream shift. Emits `MORTAL_BELIEF_SHIFT` / `MORTAL_CULTURE_SHIFT` on the target, plus a `WHISPER` `RAMP_FADE` event (`duration=4`, `peak_offset=1`) that echoes the same shifts for 3 more ticks.

**Pop splash** (`_emit_whisper_splash`): ripples to Pops on the mortal's world. Per-Pop delta = `vec.direction × per_unit_delta × WHISPER_POP_SPLASH(0.20) × receptivity × resistance × dist_factor × influence`. `influence` is prominence-derived: own-Pop = `WHISPER_OWN_POP_BASE_INFLUENCE(0.5) + prominence × WHISPER_OWN_POP_PROMINENCE_GAIN(2.0)`; cross-Pop = `prominence × WHISPER_CROSS_POP_PROMINENCE_GAIN(1.5)`. Culture-vector splash skips the domain-receptivity term.

## Shape Dream (`ShapeDreamIntent`)

Targets a mortal with **two Imagines from different Domain trees**. At resolution one Imago is randomly **boosted ×1.15** and the other **suppressed ×0.60**. Combine rules (`_combine_shape_dream_vectors`): multiplier applies only to positive-direction entries; for a tag in both Imagines, two positives take the mean, anything else sums. Otherwise resolves exactly like a Whisper (same splash, same 4-tick echo).

## Manifest Omen (`OmenIntent`) — "shotgun" interpretation

Targets a world. Every Pop and every active mortal on it runs the shotgun resolver (`_resolve_omen_target`):

- Effect `E` = the omen's vectors scaled by `OMEN_BASE(0.35)`. A Pop runs `n = max(1, size_magnitude)` interpretation checks; a mortal runs 1. Subdivided component `e = E/n`.
- Each check rolls `rng.random() < pass_prob`. **Pass** → adds `e` to the true tags. **Fail** → adds `e`'s magnitudes to random same-category substitute tags. Total magnitude is conserved; only coherence degrades.
- `pass_prob = base(0.55 SUCCESS | 0.35 PARTIAL) + framing_resonance×0.25 + (receptivity−1)×0.20 + (cohesion−0.5)×0.20`, minus `0.15` for `AMBIGUOUS` framing, clamped `[0.05, 0.95]`.
- Multiplied by `_pop_distance_factor` (`0.7^|distance|`).

The belief/culture shotgun resolves **once**. The `OMEN` `SPIKE_FADE` event emits but carries no vectors — only the `divine_awareness` + Luminary-attention ripple over 5 ticks.
