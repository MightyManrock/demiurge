> [← CLAUDE.md](../../CLAUDE.md)

# Action System

`build_action_library()` returns `dict[str, ActionDefinition]` keyed by action key. **Critical**: always use `loop._action_library[key]`, never call `build_action_library()` independently — `ActionDefinition.id` is a fresh `uuid4()` each call, and `ActionInstance` UUIDs must match the loop's library or they will be silently skipped.

`ActionInstance` fields: `action_definition_id`, `target_type`, `target_id`, `proxius_id`, `intent` (typed union `ActionIntent`).

## Action Success Rolls

**Influence actions** (Whisper, Shape Dream) use a dedicated formula instead of the reliability tier:

```
success_chance = clamp(0.75 + puissance×0.15 + visibility×0.05 + framing_resonance×0.04, 0.75, 0.99)
```

`framing_resonance` is clamped to `[0, 1]` here — mismatched framing contributes 0, not a penalty. Outcome thresholds: `< success_chance` → SUCCESS; `< success_chance + 0.15` → PARTIAL; else → FAILURE.

**All other actions** use `ActionReliability` tiers with a puissance-adjusted success threshold:

| Tier | Base success | Max (puissance=1) |
|------|-------------|-------------------|
| CERTAIN | always SUCCESS | — |
| PROBABLE | 0.75 | 0.83 |
| UNCERTAIN | 0.50 | 0.58 |
| CHAOTIC | 0.30 | 0.38 |

`adjusted = base + puissance × 0.08`. Partial and failure bands shift with the success boundary; CHAOTIC still has a CHAOTIC_RESULT outcome at the tail.

## Puissance

`puissance` is a Demiurge stat in `[0, 1]` computed at the start of every tick by `_compute_puissance()` in `tick_logic.py`:

```
puissance = clamp(
    lifetime_revelation / 500   × 0.50
  + imago_tier_score   / 40    × 0.35
  + tick_number        / 200   × 0.15
, 0, 1)
```

Imago tier weights: T1=1, T2=2, T3=4, T4=8. `lifetime_revelation` is a running total of all Revelation ever gained (never decremented); it is stored on `Demiurge` and accumulated by the `REVELATION_GAINED` mutation handler.

## Adding a New Action

1. Define the intent class in `core/action_core.py`
2. Add it to the `ActionIntent` union
3. Add an `ActionDefinition` in `build_action_library()`
4. Handle it in `logic/tick_logic._resolve_intent_mutations()`
5. Add to `_validate_and_filter_queue` if needed
6. Add UI prompting in `GameScreen._build_intent()` and/or `_build_intent_params()` in `ui/ui.py`
