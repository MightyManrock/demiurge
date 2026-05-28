> [← CLAUDE.md](../../CLAUDE.md)

# Scry Action

Four scope levels (`ScryScope.WORLD/SYSTEM/GALAXY/UNIVERSE`), each with progressively higher subtle-influence footprint and lower per-entity discovery probability. WORLD/SYSTEM scopes require a target; GALAXY/UNIVERSE do not.

Discovery is probabilistic, gated by **depth delta** (how far the candidate is below the scry's anchor), **container prerequisite** (the entity's spatial container must already be in the Window), **proximity bonus**, and **domain-affinity bonus** with `Demiurge.affiliated_domains`. Civilizations use scale-aware anchor depth (`_CIV_SCALE_DEPTH`). Discovery cascades within a single scry: a system found mid-pass unlocks its worlds in the same pass.

Implementation: `_process_scry` in `tick_logic.py`.

---

## Footprint cost

| Scope    | Base fp (subtle_influence) | With max momentum |
|----------|---------------------------|-------------------|
| WORLD    | 0.01                      | ~0.10             |
| SYSTEM   | 0.10                      | 0.10 (unchanged)  |
| GALAXY   | 0.20                      | 0.20 (unchanged)  |
| UNIVERSE | 0.35                      | 0.35 (unchanged)  |

At WORLD scope the actual footprint charged is `0.01 + momentum * 0.09`, scaling up as the Demiurge scrys the same target repeatedly. All other scopes pay their fixed base regardless of momentum.

---

## Momentum

`Demiurge.scry_momentum` is a `dict[str, float]` keyed by `"{scope}:{target_id_or_None}"` (e.g. `"world:uuid-of-neran"`, `"galaxy:None"`). Values live in `[0, 1]`.

**Growth** (each firing, inside `_process_scry`):
```
new = old + (1 − old) × 0.15
```
Asymptotic — approaches 1.0 but never reaches it. ~7 consecutive scrys to reach 0.70, ~15 to reach 0.90.

**Decay** (each tick, before Phase 2 action processing):
```
momentum *= 0.95   (pruned if < 0.001)
```
~14 ticks of inactivity to halve from 1.0; ~65 ticks to drop below 0.05.

**Discovery bonus** (additive to `base`, capped at 0.95):

| Entity type    | Bonus formula                               |
|----------------|---------------------------------------------|
| Location       | `base += momentum × 0.25`                  |
| Civilization   | `base += momentum × 0.25`                  |
| Species        | `base += momentum × 0.25`                  |
| NotableMortal  | `base += momentum × 0.25`                  |
| Pop            | `world_scry_base *= (1 + momentum × 0.35)` |

---

## Parent-visibility cascades

When a parent entity is already visible, child discovery becomes easier.

**Pop → Mortal** (applied after momentum bonus, before spatial factor):
```
if mortal.pop_id and parent_pop exists:
    base = min(0.95, base + parent_pop.visibility × 0.25)
```

**Civ → Pop** (applied after momentum `world_scry_base`, before distance factor):
```
if pop.civilization_id and parent_civ exists:
    world_scry_base = min(start_vis, world_scry_base × (1 + parent_civ.visibility × 0.30))
```
Capped at `start_vis` so a fully-visible civ cannot make its pops auto-discover.

---

## Distance cap (WORLD scope)

At WORLD scope, a `PopLocation`'s `distance_from_core` contributes at most +2 to the depth delta used for mortal discovery:
```
m_dist_eff = min(m_dist, 2)   # only at WORLD scope
delta = abs(5 − anchor) + m_dist_eff
```
At other scopes the raw `distance_from_core` is used unchanged. This prevents peripheral PopLocations from becoming effectively impenetrable to world-scope scrys.

---

## Probability tables

`_depth_chance(delta)` baseline (before momentum / cascade / spatial / domain bonuses):

| delta | base chance |
|-------|-------------|
| 0     | 0.70        |
| 1     | 0.50        |
| 2     | 0.35        |
| 3     | 0.25        |
| 4     | 0.18        |
| 5     | 0.12        |
| 6+    | 0.08        |

**Mortal at WORLD scope, dist=0, anchor=5** (delta=0):

| Momentum | Pop vis (parent) | Base after cascade | Notes                         |
|----------|------------------|--------------------|-------------------------------|
| 0.0      | 0.0              | 0.70               | cold start                    |
| 0.5      | 0.0              | 0.825              | momentum bonus +0.125         |
| 1.0      | 0.0              | 0.95 (cap)         | momentum bonus +0.25          |
| 0.5      | 0.8              | 0.95 (cap)         | cascade adds +0.20 on top     |
| 0.0      | 0.8              | 0.90               | cascade alone lifts by +0.20  |

---

## Uncharted-galaxy exception

Galaxies without any in-Window systems use a special entry point: `_pick_uncharted_galaxy_entry`. This logic is unchanged by the redesign.
