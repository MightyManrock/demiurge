> **Status:** active
> **TO-DO ref:** —
> **Last updated:** 2026-05-24

## Goal

Improve the visibility system with several targeted changes:

1. Lower the "in Window" floor from `0.05` to `0.005` to retain more visibility across the longer tick cadence.
2. After decay is applied, snap any visibility that fell below the floor to exactly `0.0`. Skip decay entirely on entities already at `0.0` (optimization — no float drift, no wasted math).
3. Splinter Pops inherit `parent.visibility × 0.75` instead of `× 0.5`.
4. **Omen visibility splash** — a successful Manifest Omen sets the target world's visibility to `1.0` and boosts all above-floor mortals and Pops on that world by `0.6 / (pop_location.distance_from_core + 1)`, capped at `1.0`.
5. **Whisper / Shape Dream visibility splash** — in addition to the existing belief splash, these actions boost the target mortal's own Pop's visibility by `+0.8` and all other Pops in the same `SignificantLocation` by `0.6 / (pop_location.distance_from_core + 1)`, capped at `1.0`. Unlike Omen, **this splash reaches sub-floor Pops too** — if a Pop was at `0.0` and is brought above the floor, emit a discovery log message ("Through [mortal], you sense a community you hadn't noticed before" or similar). Only the mortal's own world is affected.
6. **Upward visibility splash** — when any Pop or mortal is boosted by an action-based splash (Phases 2–3), their ancestor entities also receive a flat `+0.003` boost, deduplicated.
7. **Visibility stall counter** — replaces the `pinned=True` starting-visibility mechanism with a per-entity countdown that defers decay after visibility peaks.

---

## Phases

### Phase 1: Floor + splinter + snap-to-zero

**1a — Lower visibility floor**
- `logic/tick_logic.py`: Change `ENTITY_VISIBILITY_FLOOR = 0.05` → `0.005`
- Verify `is_in_window()` usage is consistent (it uses this constant directly)
- Run `--autoplay` regression

**1b — Splinter pop inheritance** ✓
- `logic/tick_logic.py`: Change `visibility=max(0.0, pop.visibility * 0.5)` → `× 0.75` at both splinter-creation sites (Pop splinter and Imago goal-pop)
- Run `--autoplay` regression

**1c — Snap below-floor to zero** ✓
- `logic/tick_logic.py`, in the decay phase for all five entity types: after applying decay, if `entity.visibility < ENTITY_VISIBILITY_FLOOR`, set `entity.visibility = 0.0`
- This fires on the *new* value after decay (not the old value before)
- Run `--autoplay` regression

**1d — Skip decay on zero-visibility entities**
- `logic/tick_logic.py`, in the decay phase for all five entity types: if `entity.visibility == 0.0` and the entity is not receiving a visibility boost this tick, skip decay entirely
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
    - For each PopLocation, compute `boost = min(1.0, 0.6 / (loc.distance_from_core + 1))`
    - For each Pop at that PopLocation whose `visibility > ENTITY_VISIBILITY_FLOOR`: emit a visibility delta mutation clamping to `[0.0, 1.0]`
    - For each mortal whose `current_location` resolves to that PopLocation and whose `visibility > ENTITY_VISIBILITY_FLOOR`: emit a mortal visibility delta mutation
    - Return the sets of boosted pop IDs and mortal IDs (for Phase 4)
  - Call this helper when `outcome != FAILURE` (matches the existing omen pass-check guard)
- Run `--autoplay` regression

---

### Phase 3: Whisper / Shape Dream visibility splash

**3a — Visibility splash helper**
- `logic/tick_logic.py`: Add `_emit_influence_visibility_splash(mutations, state, mortal, world_id)`:
  - Find the mortal's `PopLocation` (their `current_location`)
  - Boost own Pop's visibility by `+0.8`, capped at `1.0` — **no floor guard** (sub-floor allowed); if the pop was at `0.0` and is brought above the floor, record it as a discovery
  - For every other Pop on the same world:
    - Find that Pop's PopLocation; get `distance_from_core`
    - `boost = 0.6 / (distance_from_core + 1)`
    - **No floor guard** — sub-floor pops may be boosted
    - If pop was at `0.0` and boost brings it above the floor, record as discovery
    - Emit visibility delta mutation clamped to `[0.0, 1.0]`
  - Return sets of boosted pop IDs, boosted mortal IDs, and discovered pop IDs (for Phase 4)

**3b — Wire into Whisper and Shape Dream**
- `logic/tick_logic.py`, inside `_resolve_intent_mutations` at the Whisper branch (line ~3421) and Shape Dream branch (line ~3497):
  - After the existing belief/culture mutations are appended, call `_emit_influence_visibility_splash(...)`
  - Only fire on non-FAILURE outcomes (consistent with belief splash guard)
- The existing `_emit_whisper_splash` is for belief/culture; this is a separate visibility-only helper
- Run `--autoplay` regression

**3c — Discovery log messages**
- For each discovered pop ID returned by `_emit_influence_visibility_splash`, emit a log message as part of the Whisper/Shape Dream result narrative
- Message form: "Through [mortal.name], your attention finds [pop.name] — a community you had not noticed before."
- Append after the main result message, one line per discovered pop
- Run `--autoplay` regression

---

### Phase 4: Upward visibility splash

When any Pop or mortal receives a visibility boost from the action-based splashes above (Phases 2–3), their ancestor entities also receive a flat `+0.003` visibility boost (10× the location/civ/species decay rate). Each ancestor is boosted at most once per event regardless of how many boosted Pops/mortals belong to it.

**Ancestors walked per boosted Pop:**
- `pop.civilization_id` → Civilization
- `pop.species_id` → Species (if set)
- `pop.current_location` (PopLocation) → parent SignificantLocation → parent System → parent Galaxy

**Ancestors walked per boosted mortal:**
- Civilization via `mortal.civilization_id`
- Species via `mortal.species_id`
- Location chain: `mortal.current_location` (PopLocation) → SignificantLocation → System → Galaxy

**4a — Upward splash helper**
- Add `_emit_upward_visibility_splash(mutations, state, boosted_pop_ids, boosted_mortal_ids)` to `logic/tick_logic.py`:
  - Collect all ancestor entity IDs into a `set` (deduplication is automatic)
  - For each unique ancestor: emit a `+0.003` visibility delta mutation, clamped to `[0.0, 1.0]`
- **Scry is explicitly excluded** — this mechanic applies only to action-based boosts. Scry has its own visibility logic and will be reworked separately.

**4b — Wire into Omen splash**
- Call `_emit_upward_visibility_splash` from the tail of `_emit_omen_visibility_splash`, passing the sets of boosted pop and mortal IDs returned by that helper
- Run `--autoplay` regression

**4c — Wire into Whisper/Shape Dream splash**
- Call `_emit_upward_visibility_splash` from the tail of `_emit_influence_visibility_splash`, passing the sets of boosted pop and mortal IDs returned by that helper
- Run `--autoplay` regression

---

### Phase 5: Visibility stall counter (replaces starting-pinned)

Add `visibility_stall_remaining: int = 0` to all five entity types that have visibility (locations, mortals, pops, civilizations, species). While `stall_remaining > 0`, decay is skipped and the counter decrements by 1 instead. When visibility reaches or is clamped to `1.0`, the counter is bumped up to `30` if it is currently below `30` (otherwise left unchanged). Pinned entities (Proxii) freeze at `30` and never decrement below it.

**Decay phase rules** (per entity, each tick):
```
if pinned and stall_remaining <= 30:
    skip (no decay, no decrement)          # Proxius freeze
elif stall_remaining > 0:
    stall_remaining -= 1                   # stall tick, no decay
else:
    apply normal visibility decay
```

**On visibility reaching 1.0** (set by mutation or clamped by boost):
```
stall_remaining = max(stall_remaining, 30)
```

**On PROXIUS_APPOINTED:**
```
if stall_remaining < 30:
    stall_remaining = 30
# freeze rule above then holds for all future ticks
```

**5a — Data model changes**
- `core/universe_core.py`: add `visibility_stall_remaining: int = 0` to `Location` (and subclasses), `Civilization`, `Species`, `NotableMortal`, `Pop`

**5b — Schema changes**
- `core/scenario_schema.sql`: add `visibility_stall_remaining INTEGER DEFAULT 0` to all five tables (locations, civilizations, species, mortals, pops)

**5c — Loader / exporter**
- `utilities/scenario_loader.py`: load via `row.get("visibility_stall_remaining", 0)` for each entity type
- `utilities/scenario_exporter.py`: include `visibility_stall_remaining` in INSERT for each entity type

**5d — Decay logic**
- `logic/tick_logic.py`: integrate stall counter into decay phase for all five entity types, following the decay phase rules above
- Add constants: `VISIBILITY_STALL_ON_CAP = 30` and `VISIBILITY_STALL_SCENARIO_START = 360`
- Run `--autoplay` regression

**5e — On-cap logic**
- `logic/tick_logic.py`: wherever visibility is set to `1.0` by mutation or clamped to `1.0` by a boost, apply `entity.visibility_stall_remaining = max(entity.visibility_stall_remaining, VISIBILITY_STALL_ON_CAP)`
- Run `--autoplay` regression

**5f — PROXIUS_APPOINTED**
- `logic/tick_logic.py`: on appointment, if `stall_remaining < 30`, set it to 30
- The freeze rule in decay phase then holds for all future ticks
- Run `--autoplay` regression

**5g — DB migration**
- Both scenario DBs: set `visibility_stall_remaining = 360` on all entities where `visibility >= 1.0`
- Apply via SQL patch directly to `scenarios/wardens_compact.db` and `scenarios/ledger_and_ash.db`
- Run `--rebuild --scenario` to migrate any saves

---

## Files affected

- `logic/tick_logic.py` — all changes; `ENTITY_VISIBILITY_FLOOR`, splinter sites, snap-to-zero, zero-skip, omen resolution, influence resolution, new helpers, stall counter decay logic
- `core/universe_core.py` — `visibility_stall_remaining` field on 5 models
- `core/scenario_schema.sql` — new column on 5 tables
- `utilities/scenario_loader.py` — load new field
- `utilities/scenario_exporter.py` — export new field
- `scenarios/wardens_compact.db`, `scenarios/ledger_and_ash.db` — SQL migration to set stall=360 on visibility=1.0 entities

## Notes

- Omen splash retains the "above floor" guard — it is a broadcast across observable space. Whisper/Shape Dream can reach sub-floor pops via the mortal vector (contact, not sight).
- Discovery messages (Phase 3c) only fire when a pop crosses from `0.0` to above-floor as a direct result of the influence splash. One message per discovered pop per action.
- Both Omen and Whisper/Shape Dream use `0.6 / (distance_from_core + 1)` attenuation: distance 0 → +0.6, distance 1 → +0.3, distance 2 → +0.2, etc.
- Upward splash flat boost `0.003 = 10 × location_visibility_decay_rate`. One tick of activity in an area fully offsets one tick of decay on every ancestor entity.
- Stall counter replaces `pinned=True` for scenario-start visibility; `pinned` field is retained only for the Proxius freeze rule.
- No new mutation types needed — mortal visibility uses `MORTAL_VISIBILITY` with delta; entity (pop/location/civ/species) visibility uses the existing delta-apply path.
- Snap-to-zero (1c) fires on the post-decay value; zero-skip (1d) fires before decay math runs. These are separate checks in order.
