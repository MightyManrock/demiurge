> **Status:** active
> **TO-DO ref:** Rework action success/failure math
> **Last updated:** 2026-05-21

## Goal

Replace the flat per-action reliability roll with a dynamic success system. Introduce `puissance` as a Demiurge stat that reflects accumulated power and scales success chances across the board. Influence actions (Whisper, Shape Dream) get a richer roll that also incorporates target visibility and Framing resonance. Manifest Omen is excluded — it has no miss state.

---

## Puissance

### Definition

`puissance` is a computed `float` in `[0.0, 1.0]` derived from three inputs:

```
puissance = clamp(
    lifetime_revelation / REV_SCALE * 0.50
    + imago_tier_score  / IMAGO_SCALE * 0.35
    + tick_number       / TICK_SCALE  * 0.15
, 0.0, 1.0)
```

| Input | Scale constant (suggested) | Notes |
|---|---|---|
| `lifetime_revelation` | `REV_SCALE = 500.0` | Saturates at ~500 total revelation generated |
| `imago_tier_score` | `IMAGO_SCALE = 40` | See tier weights below; 112 nodes × avg ~3 ≈ 336 theoretical max, but 40 reaches 1.0 around ~10–15 good unlocks |
| `tick_number` | `TICK_SCALE = 200` | Minor contribution; saturates after ~200 ticks |

**Tier weights** for imago_tier_score: T1 = 1, T2 = 2, T3 = 4, T4 = 8 (exponential to reward deep tree engagement).

Constants are intentionally conservative starting points — tune after playtesting.

### New data fields

- `Demiurge.lifetime_revelation: float = 0.0` — running total of all revelation generated, never decremented. Incremented alongside `revelation_pools` in the `explore_beliefs` resolution path.
- Tier-weighted imago score is **computed at runtime** from the set of unlocked node IDs (cross-referenced against `ImagoRegistry` for tier). No new stored field needed unless profiling shows it's expensive.

### UI

Display `puissance` in the **Status tab**, below the Essence-by-Domain section. Format: `Puissance  0.42` (or similar). Computed each render from `Demiurge` state.

---

## Influence action success roll (Whisper, Shape Dream)

Replaces the flat `ActionReliability` roll for these two actions only.

```
success_chance = clamp(
    BASE_INFLUENCE
    + puissance          * PUISSANCE_WEIGHT
    + target.visibility  * VISIBILITY_WEIGHT
    + framing_resonance  * FRAMING_WEIGHT
, 0.75, 0.92)
```

| Constant | Suggested value | Rationale |
|---|---|---|
| `BASE_INFLUENCE` | `0.75` | Floor at all-zero inputs |
| `PUISSANCE_WEIGHT` | `0.08` | Max +8% from a fully mature Demiurge |
| `VISIBILITY_WEIGHT` | `0.05` | Max +5% at visibility 1.0 |
| `FRAMING_WEIGHT` | `0.04` | Max +4% at full resonance |

`framing_resonance` reuses the existing `_framing_resonance()` helper already in `tick_logic.py` (built for Manifest Omen interpretation). Note: AMBIGUOUS Framing has **no explicit penalty** here (unlike Manifest Omen), it simply contributes 0 resonance.

At floor inputs (puissance=0, visibility=0, resonance=0): `success_chance = 0.75` ✓  
At ceiling inputs (puissance=1, visibility=1, resonance=1): `success_chance = 0.75 + 0.08 + 0.05 + 0.04 = 0.92` ✓

Outcome mapping: roll a `float` in `[0, 1)`.
- `< success_chance` → `SUCCESS`
- `< success_chance + 0.15` → `PARTIAL`
- else → `FAILURE`

(Partial band stays fixed at 15%pp; only the success/failure boundary shifts.)

---

## All other actions (reliability tiers)

Keep the existing `PROBABLE / UNCERTAIN / CHAOTIC` chart, but puissance shifts the success threshold:

```
adjusted_success_threshold = base_threshold - puissance * PUISSANCE_TIER_BONUS
```

| Tier | Base success | Max adjusted (puissance=1) |
|---|---|---|
| PROBABLE | 0.75 | 0.83 |
| UNCERTAIN | 0.50 | 0.58 |
| CHAOTIC | 0.30 | 0.38 |

`PUISSANCE_TIER_BONUS = 0.08` (same weight as influence, keeps it consistent).

---

## Implementation steps

1. **Add `lifetime_revelation` to `Demiurge`** (`core/onto_core.py`).
2. **Increment it in `explore_beliefs` resolution** (`logic/tick_logic.py`) alongside `revelation_pools` update.
3. **Add DB column** (`core/scenario_schema.sql`), load via `.get()` in `scenario_loader.py`, export in `scenario_exporter.py`.
4. **Write `_compute_puissance(state)`** helper in `tick_logic.py` — pulls `lifetime_revelation`, computes imago tier score from `state.demiurge.unlocked_imagines` (or equivalent), applies formula.
5. **Rework `_roll_reliability()`** to accept optional `puissance` and shift tier thresholds.
6. **Add influence-specific roll path** in `_execute_action()` for Whisper/Shape Dream intents, calling the new formula instead of `_roll_reliability()`.
7. **Expose puissance in Status tab** (`ui/display.py` snapshot renderer or `ui/widgets.py`).
8. **Update `docs/Mechanics/action-system.md`** and **`docs/Mechanics/influence-actions.md`**.
9. **Run `--autoplay` with multiple strategies** and verify ~75–92% success rate on influence actions, no regressions elsewhere.

## Files affected

- `core/onto_core.py` — `Demiurge.lifetime_revelation`
- `core/scenario_schema.sql` — new column
- `utilities/scenario_loader.py` — load new column
- `utilities/scenario_exporter.py` — export new column
- `logic/tick_logic.py` — `_compute_puissance()`, updated `_roll_reliability()`, influence roll path, revelation accumulation
- `ui/display.py` or `ui/widgets.py` — puissance display in Status tab
- `docs/Mechanics/action-system.md`
- `docs/Mechanics/influence-actions.md`

## Notes

- All weight constants (`REV_SCALE`, `IMAGO_SCALE`, `TICK_SCALE`, `PUISSANCE_WEIGHT`, etc.) should be defined as module-level constants in `tick_logic.py` for easy tuning.
- Alignment remains unchanged: it scales mutation effectiveness post-success, not the roll itself.
- `ProxiusDirectiveIntent` has its own alignment-based roll — leave it alone for now.
- Manifest Omen: excluded entirely. Its Framing interaction is already in the interpretation path, not the success roll.
