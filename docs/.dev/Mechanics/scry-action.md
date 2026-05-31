# Scry Action

Scry is an ongoing action that sweeps its target scope to completion and auto-terminates once every entity within the primary scope is visible.

## Queuing

Scry always queues as a repeating ongoing action (`always_persist` tag). The "once or repeat?" prompt is skipped. Cancel explicitly to stop.

## Scopes and primary entities

| Scope | Target | Primary entities (guaranteed sweep) |
|---|---|---|
| UNIVERSE | (none) | All Galaxy locations |
| GALAXY | A galaxy | All System locations in that galaxy |
| SYSTEM | A system | All non-system child locations in that system |
| WORLD | A world/SignificantLocation | All PopLocations, Pops, NotableMortals, Civs, and Species at target |

## Momentum

Each tick the action fires, momentum increases: `new = old + (1 − old) × 0.15`. Momentum resets to 0 if the action is cancelled. Momentum is stored directly on the `OngoingAction` instance.

## Discovery probability (primary entities)

```
p = 0.45 + (momentum × 0.35) + domain_bonus
```

- `domain_bonus`: up to +0.20 from similarity between entity tags and Demiurge's affiliated domains; scaled down when base is already high.
- No depth/delta penalties for entities within primary scope.
- Already-visible entities receive a boost: `visibility += p × 0.3` (capped at 1.0).
- On discovery: `visibility = max(current, 0.45 + momentum × 0.35)`.

## Termination

After each tick's sweep, the action checks whether all primary-scope entities are above `ENTITY_VISIBILITY_FLOOR` (including entities just discovered this tick). If all are visible, the action auto-resolves and a log entry fires: "Scry of [Target] complete".

Newly-spawned entities at the target join the primary set immediately; scry will not complete until they are found.

## Incidental discovery

A separate pass runs after the primary sweep, finding entities outside the primary scope. Two candidate pools:

1. **Relationship-adjacent**: locations whose parent is in-window, and NotableMortals whose `pop_milieu` Pop is visible.
2. **Coordinate-adjacent**: locations near the target by effective position.

Incidentals use the old harsh delta math (depth anchor + distance penalty + spatial falloff) with no momentum bonus. A mortal whose `pop_milieu` Pop has visibility > 0.5 is treated as depth-delta 1 (visible crowd).

## Footprint costs

| Scope | Subtle influence footprint |
|---|---|
| WORLD | 0.01 + momentum × 0.09 |
| SYSTEM | 0.10 |
| GALAXY | 0.20 |
| UNIVERSE | 0.35 |

GALAXY and UNIVERSE also cost 3 and 5 Essence respectively per tick.
