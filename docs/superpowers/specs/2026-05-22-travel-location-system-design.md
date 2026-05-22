# TravelLocation System — Design Spec

**Date:** 2026-05-22
**Plan:** `docs/plans/travel-location-system.md`
**Prereq:** `mortal-travel-initial.md` (complete) — `TravelIntent`, tick phases, leg-based countdown already in place.

---

## Goal

Replace the abstract "in transit" mortal state with a first-class `TravelLocation` entity that is scryable, joinable by multiple travelers on the same route, and a foundation for future in-transit events. Add `travel_features` to `PopLocation` for infrastructure-gated routing. Validate with Durenn Vail: a merchant who commutes between Neran (Ardent System) and Sethis (The Velar Corridor).

---

## Data Model

### `TravelLocation(Location)` — `core/universe_core.py`

```python
class TravelLocation(Location):
    location_type: str = "travel_location"
    legs: dict[str, int]
    # Ordered dict: PopLocation UUID (str) → tick cost for leg starting at that waypoint.
    # Last entry always has value 0 — that key IS the destination.
    # Example: {"neran-surface-uuid": 2, "neran-orbital-uuid": 4, "sethis-orbital-uuid": 1, "sethis-surface-uuid": 0}
    current_waypoint: str       # UUID str of the leg currently in progress
    ticks_remaining: int        # ticks left on the current leg
    occupants: list[UUID] = Field(default_factory=list)
```

Lives in `state.locations` keyed by its UUID — scryable exactly like any other location.

**Name:** auto-set to e.g. `"In transit: Neran Surface → Sethis Surface"` at instantiation.

**Leg advancement (each tick):**
1. Decrement `ticks_remaining`.
2. When `ticks_remaining <= 0`, get the next key in `legs` after `current_waypoint`.
3. If that key's value is `0` → arrival. Teleport all occupants to that PopLocation; remove `TravelLocation` from `state.locations`.
4. Otherwise → `current_waypoint = next_key`, `ticks_remaining = legs[next_key]`.

### Updated `TravelIntent` — `core/agent_core.py`

```python
class TravelIntent(BaseModel):
    travel_location_id: UUID
```

All per-journey state lives on `TravelLocation`. `TravelIntent` is just the mortal's pointer to it.

**Backward compatibility:** the existing `destination`, `ticks_remaining`, `in_transit` fields are removed. The Karath Omn logic must be updated to create a `TravelLocation` and set `TravelIntent(travel_location_id=...)`.

### `PopLocation` addition — `core/universe_core.py`

```python
travel_features: set[str] = Field(default_factory=set)
```

Tags indicating what kinds of travel connections this location supports. Two PopLocations can be adjacent in a route only if they share at least one feature. Examples: `space_elevator`, `shuttle_service`, `commercial_space_port`.

---

## Routing

### Algorithm — `logic/tick_logic.py` (or `utilities/travel_routing.py`)

BFS over PopLocations connected by shared `travel_features`. Returns an ordered list of PopLocation UUIDs from origin to destination (inclusive).

```
_find_route(state, origin_id, destination_id) -> list[UUID] | None
```

Returns `None` if no route exists.

### Leg cost

**Intra-world** (two PopLocations share the same parent `SignificantLocation`):
```
dist_between = origin.distance_from_core + dest.distance_from_core
ticks = dist_between if (origin.dfc > 0 and dest.dfc > 0) else dist_between + 1
```
Same formula as the existing Karath Omn implementation.

**Interstellar** (PopLocations on different SignificantLocations):
Walk up the parent chain from each PopLocation: `PopLocation → SignificantLocation → System`. Use the **System-level** `CosmicCoordinates` for distance.
```python
SPACE_TRAVEL_CONSTANT = 3.0  # tune later; ties in to transport tech
ticks = max(1, math.ceil(euclidean(system_a.coords, system_b.coords) / SPACE_TRAVEL_CONSTANT))
```

For the Vail test: Ardent System (0,0,0) → The Velar Corridor (8,4,-2) = √84 ≈ 9.17 → `ceil(9.17/3.0)` = **4 ticks**.

### Joining

When a mortal initiates travel, check `state.locations` for an existing `TravelLocation` where:
- `legs` sequence matches the new route exactly, AND
- `current_waypoint` matches the origin PopLocation UUID

If found, add the mortal to `occupants` and set `TravelIntent(travel_location_id=existing.id)`. Otherwise, instantiate a new `TravelLocation`.

---

## Persistence

### `core/scenario_schema.sql`

Add columns to `locations` table:
```sql
-- TravelLocation-specific (subclass='travel_location')
legs                  TEXT    NOT NULL DEFAULT '{}',   -- JSON object (ordered dict)
travel_current_wp     TEXT    NOT NULL DEFAULT '',     -- UUID str of current waypoint
travel_ticks_rem      INTEGER NOT NULL DEFAULT 0,
travel_occupants      TEXT    NOT NULL DEFAULT '[]',   -- JSON array of UUID strs
-- PopLocation addition
travel_features       TEXT    NOT NULL DEFAULT '[]',   -- JSON array (stored as set)
```

### `utilities/scenario_loader.py`

- Add `travel_features` loading for PopLocation rows.
- Add `TravelLocation` branch: when `subclass == "travel_location"`, instantiate `TravelLocation(legs=json.loads(...), current_waypoint=..., ticks_remaining=..., occupants=...)`.

### `utilities/scenario_exporter.py`

- Add `travel_features` export for `PopLocation`.
- Add `TravelLocation` branch: serialize `legs`, `current_waypoint`, `ticks_remaining`, `occupants`.

---

## Tick Logic — `logic/tick_logic.py`

### `_resolve_mortal_travel_decisions` (Phase 2.6a)

Updated to use routing:
1. For each mortal with no `TravelIntent` who needs to travel, call `_find_route(state, origin, destination)`.
2. Build `legs` dict: for each consecutive pair in the route, compute tick cost (intra-world or interstellar).
3. Check for joinable `TravelLocation`; create or join.
4. Set `mortal.travel_intent = TravelIntent(travel_location_id=tl.id)`.

Karath Omn hardcode is updated to use this same path (two-PopLocation route on the same world — purely intra-world).

Durenn Vail hardcode: if mortal is Vail and has no intent, route between Neran Surface ↔ Sethis Surface.

### `_process_mortal_travel` (Phase 2.6b)

Now iterates over `TravelLocation` entities in `state.locations` rather than per-mortal `TravelIntent`:
1. For each `TravelLocation`: decrement `ticks_remaining`.
2. On reaching 0: advance waypoint or trigger arrival.
3. On arrival: update each occupant's `current_location`, clear their `TravelIntent`, remove `TravelLocation` from `state.locations`.

---

## Scryability

`TravelLocation` appears in `state.locations` while occupied. The Scry system already iterates over locations — no additional hook needed beyond rendering support.

### `ui/detail_renderers.py`

Add a renderer for `TravelLocation`: shows route summary, current leg, occupants, ticks remaining. Dev mode only for now; full display when scry surface is built.

---

## Durenn Vail Test

**What to inject into `scenarios/wardens_compact.db`:**
- Durenn Vail as a `NotableMortal` at Neran Surface.
- `travel_features` on:
  - Neran Surface: `{"shuttle_service", "space_elevator"}`
  - Neran Orbital Ring: `{"shuttle_service", "space_elevator", "commercial_space_port"}`
  - Sethis Orbital Station: `{"commercial_space_port"}`  
  - Sethis Surface: `{"shuttle_service"}` *(or equivalent)*

**Validates:**
1. Routing builds the 4-waypoint route correctly.
2. `TravelLocation` is instantiated and Vail is placed in it.
3. Leg advancement works across the `SignificantLocation` boundary.
4. Interstellar leg uses System coordinates (4 ticks, Ardent → Velar Corridor).
5. Vail is scryable at each stage.
6. Arrival: Vail's `current_location` updates, `TravelLocation` is cleared.

---

## Out of Scope (Future)

- Feature-based travel time/cost modifiers.
- Infrastructure-as-target (disrupting a `travel_feature`).
- In-transit events.
- Player-initiated travel actions (this impl is autonomous mortals only).
