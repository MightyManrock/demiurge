# Scry Action Redesign

**Status:** Approved, pending implementation
**Date:** 2026-05-30

---

## Context

The current scry system is broken for NotableMortals. Mortals require a four-level location cascade (galaxy → system → world → PopLocation all in-window) before they're even checked, then face the deepest anchor depth (5) with harsh distance penalties. The momentum system lives on `Demiurge.scry_momentum` as a global dict — detached from any specific action, decaying even while actively scrying, carrying over when the player cancels and restarts.

The redesign makes scry a proper `OngoingAction` with two goals: (1) fix mortal discovery, and (2) give the player a "set and ignore" sweep that auto-terminates when its scope is fully revealed.

---

## Design

### Scope-to-primary-entity mapping

Each scope sweeps one entity level below itself to guaranteed completion:

| Scope | Target | Primary entities |
|---|---|---|
| UNIVERSE | (none) | All Galaxy locations |
| GALAXY | A galaxy | All System locations in that galaxy |
| SYSTEM | A system | All SignificantLocations in that system |
| WORLD | A world/SignificantLocation | All PopLocations, Pops, NotableMortals, Civs, Species at target |

Everything outside the primary set is incidental.

---

### OngoingAction state

Add `momentum: float = 0.0` to the `OngoingAction` model. Momentum is now scoped to the action instance — persists through save/load, disappears on cancel. The global `Demiurge.scry_momentum` dict is removed entirely.

Cancelling a scry loses all accumulated momentum. Cancelling is a deliberate reset, not a pause.

---

### Primary sweep (per tick)

Each tick:
1. Increment momentum: `new = old + (1 − old) × 0.15`
2. For each primary-scope entity **not yet visible**: run discovery roll
3. For each primary-scope entity **already visible**: run boost roll

**Probability formula:**
```
p = base_rate + (momentum × 0.35) + domain_bonus
```
- `base_rate = 0.45` — generous flat start; most entities findable within a handful of ticks even without momentum
- `momentum × 0.35` — up to +0.35 at full ramp
- `domain_bonus` — existing logic unchanged: up to +0.20, scaled down when base is high, 0 if no affiliated domains

**On discovery:** `visibility = max(current_visibility, base_rate + momentum × 0.35)`. Later discoveries during a mature scry land at higher visibility than early ones. The old `scope_start_vis` dict is removed.

**Boost roll outcome:** `visibility = min(1.0, visibility + p × 0.3)` — keeps already-found entities from decaying back out as the sweep nears completion.

---

### Termination condition

After the sweep pass each tick, check: are all primary-scope entities above `ENTITY_VISIBILITY_FLOOR`?

- **Yes** → auto-resolve the ongoing action; fire log entry "Scry of [Target] complete"
- **No** → continue next tick

Newly spawned entities at the target join the primary set immediately. Boost rolls on already-visible entities prevent the action from stalling indefinitely on a single latecomer.

**Toast notification** (auto-stop/auto-pause events across all actions): deferred to a future system. For now, a log entry on resolve is sufficient.

---

### Incidental discovery pass

Runs after the primary sweep as a separate, independent pass. Two candidate pools:

**Relationship-adjacent:**
- Pops linked to visible Pops (via `linked_pops`)
- Civs/Species present on a location where the player already has visibility
- NotableMortals whose `pop_milieu` Pop is visible ← *the mortal visibility fix*
- Locations that are parent/child of a known location but outside current scope

**Coordinate-adjacent:**
- Locations within a CosmicCoordinates distance threshold of the target or any already-visible primary entity

**Probability:** existing harsh delta math (depth anchor, distance penalties) as floor. Domain bonus applies. No momentum contribution. Incidentals are genuinely rare — this preserves the current flavor where scrying a world might incidentally surface a nearby system, but you won't chart a galaxy by accident.

**`pop_milieu` exception:** if a mortal's milieu Pop has visibility > 0.5, treat the mortal as depth delta 1 (not their raw distance delta). They're in a visible crowd; they should be findable.

---

### Schema and persistence changes

**Add:** `momentum REAL NOT NULL DEFAULT 0.0` to `ongoing_actions` table in `scenario_schema.sql`. Load via `.get("momentum", 0.0)` in loader. Export in exporter.

**Remove:** `scry_momentum` column from `demiurge` table. Remove `scry_momentum` field from `Demiurge` model. Handled by migrator round-trip.

---

### Tick logic restructure

**Remove:**
- Phase 1 momentum decay loop (`scry_momentum *= 0.95` over global dict)
- Entire scry resolution block in Phase 2 action resolution (~lines 2544–2950 in tick_logic.py)

**Add:**
- Scry handler in the ongoing action phase — runs primary sweep + incidental pass, increments momentum, checks termination, fires resolve mutation when done

---

## Files affected

| File | Change |
|---|---|
| `core/action_core.py` | Add `momentum: float = 0.0` to `OngoingAction`; remove `scry_momentum` from `Demiurge` |
| `core/scenario_schema.sql` | Add momentum to ongoing_actions; remove scry_momentum from demiurge |
| `utilities/scenario_loader.py` | Load momentum from ongoing_actions; remove scry_momentum load |
| `utilities/scenario_exporter.py` | Export momentum; remove scry_momentum export |
| `utilities/scenario_migrator.py` | Round-trip handles schema delta automatically |
| `logic/tick_logic.py` | Remove Phase 1 decay + Phase 2 scry block; add ongoing scry handler |
| `docs/.dev/Mechanics/scry-action.md` | Rewrite to reflect new mechanics |

---

## Verification

1. `python main.py --autoplay` completes 50 ticks without errors
2. Queue WORLD scry on a world with known pops → after sufficient ticks, all pops and mortals become visible, action auto-resolves with log entry
3. Cancel a scry mid-way, restart → momentum begins at 0.0 (no carryover)
4. Save mid-scry, reload → momentum restores correctly, sweep continues
5. Spawn a new mortal to a scried world mid-sweep → scry does not resolve until the new mortal is also visible
6. Mortal in a visible-pop milieu is discoverable at reasonable rates
7. `pytest` passes
