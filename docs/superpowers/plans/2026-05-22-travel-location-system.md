# TravelLocation System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the abstract per-mortal travel fields with a first-class `TravelLocation` entity that is scryable, shared by co-travelers, and uses infrastructure-gated routing with proper leg-cost calculation.

**Architecture:** `TravelLocation(Location)` drops into `state.locations` like any other location. Routing lives in `utilities/travel_routing.py`. Tick logic is rewritten to iterate over `TravelLocation` entities rather than per-mortal `TravelIntent`. Durenn Vail (already in the scenario) is the regression target.

**Tech Stack:** Python 3.11+, Pydantic v2, SQLite (via scenario_loader/exporter), autoplay strategy for integration testing.

---

## File Map

| File | Change |
|---|---|
| `core/universe_core.py` | Add `TravelLocation(Location)`; add `travel_features: set[str]` to `PopLocation` |
| `core/agent_core.py` | Replace `TravelIntent` (3 fields → 1) |
| `utilities/travel_routing.py` | **New** — `find_route`, `leg_cost`, `build_legs`, `get_or_create_travel_location` |
| `core/scenario_schema.sql` | Add 5 columns to `locations` table |
| `utilities/scenario_loader.py` | Load `travel_features` for `PopLocation`; new `TravelLocation` branch |
| `utilities/scenario_exporter.py` | Serialize `travel_features` + `TravelLocation` fields in INSERT |
| `logic/tick_logic.py` | Rewrite `_resolve_mortal_travel_decisions` + `_process_mortal_travel`; add Vail hardcode |
| `autoplay/strategies/vail_travel_test.py` | **New** — validation strategy |
| `ui/detail_renderers.py` | Add `render_travel_location_detail` + register in `RENDERERS` |

---

### Task 1: Data Models

**Files:**
- Modify: `core/universe_core.py`
- Modify: `core/agent_core.py`

- [ ] **Step 1: Add `travel_features` to `PopLocation` in `universe_core.py`**

In `core/universe_core.py`, find the `PopLocation` class (line ~184) and add the field:

```python
class PopLocation(Location):
    """Low-tier locations that house Pops (cities, towns, space stations, etc.)"""
    pop_ids: list[UUID] = Field(default_factory=list)
    distance_from_core: int = 0
    travel_features: set[str] = Field(default_factory=set)
```

- [ ] **Step 2: Add `TravelLocation` class after `PopLocation`**

Insert the following class immediately after the `PopLocation` class definition:

```python
class TravelLocation(Location):
    """Ephemeral in-transit location. Lives in state.locations while occupied."""
    location_type: str = "travel_location"
    legs: dict[str, int] = Field(default_factory=dict)
    # Ordered dict: PopLocation UUID str → tick cost for leg starting at that waypoint.
    # Last entry always has value 0 — that key IS the destination.
    current_waypoint: str = ""   # UUID str of the leg currently in progress
    ticks_remaining: int = 0
    occupants: list[UUID] = Field(default_factory=list)
```

- [ ] **Step 3: Replace `TravelIntent` in `agent_core.py`**

In `core/agent_core.py`, replace:

```python
class TravelIntent(BaseModel):
    destination: UUID
    ticks_remaining: int
    in_transit: bool = False
```

with:

```python
class TravelIntent(BaseModel):
    travel_location_id: UUID
```

- [ ] **Step 4: Smoke test — confirm the game still loads**

```bash
cd /root/demiurge && source bin/activate && python main.py --autoplay wardens_compact 2>&1 | head -30
```

Expected: the run starts without `AttributeError` or `ValidationError`. It will likely error mid-tick once old `TravelIntent` usage in tick_logic hits the missing fields — that's expected and will be fixed in Task 4. If it errors before tick 1 completes, that's a problem in the model itself.

- [ ] **Step 5: Commit**

```bash
git add core/universe_core.py core/agent_core.py
git commit -m "feat: add TravelLocation model and update TravelIntent"
```

---

### Task 2: Travel Routing Utility

**Files:**
- Create: `utilities/travel_routing.py`

- [ ] **Step 1: Create `utilities/travel_routing.py`**

```python
"""
utilities/travel_routing.py

Routing helpers for the TravelLocation system.
  find_route     — BFS over PopLocations connected by shared travel_features
  leg_cost       — tick cost for one hop between two adjacent PopLocations
  build_legs     — convert a route list into the TravelLocation.legs dict
  get_or_create_travel_location — find joinable TravelLocation or create new one
"""
from __future__ import annotations
import math
from collections import deque
from uuid import UUID, uuid4

from pydantic import Field


def find_route(state, origin_id: UUID, destination_id: UUID) -> list[UUID] | None:
    """BFS over PopLocations connected by shared travel_features.
    Returns ordered list of PopLocation UUIDs from origin to destination,
    or None if no route exists.
    """
    from core.universe_core import PopLocation

    origin_str = str(origin_id)
    dest_str   = str(destination_id)

    if origin_str == dest_str:
        return [origin_id]

    queue: deque[list[str]] = deque([[origin_str]])
    visited: set[str] = {origin_str}

    while queue:
        path = queue.popleft()
        current_str = path[-1]
        current_loc = state.locations.get(current_str)
        if not isinstance(current_loc, PopLocation) or not current_loc.travel_features:
            continue
        for cand_str, cand_loc in state.locations.items():
            if not isinstance(cand_loc, PopLocation):
                continue
            if cand_str in visited:
                continue
            if not (current_loc.travel_features & cand_loc.travel_features):
                continue
            new_path = path + [cand_str]
            if cand_str == dest_str:
                return [UUID(s) for s in new_path]
            visited.add(cand_str)
            queue.append(new_path)
    return None


_SPACE_TRAVEL_CONSTANT = 3.0


def leg_cost(state, origin_id: UUID, dest_id: UUID) -> int:
    """Compute tick cost for one hop.
    Intra-world: distance_from_core formula.
    Cross-world: euclidean distance at divergence level / SPACE_TRAVEL_CONSTANT.
    """
    from core.universe_core import PopLocation
    origin = state.locations.get(str(origin_id))
    dest   = state.locations.get(str(dest_id))
    if not isinstance(origin, PopLocation) or not isinstance(dest, PopLocation):
        return 1

    coords = _divergence_coordinates(state, origin, dest)
    if coords is None:
        # Intra-world
        d = origin.distance_from_core + dest.distance_from_core
        return d if (origin.distance_from_core > 0 and dest.distance_from_core > 0) else d + 1

    ca, cb = coords
    dist = math.sqrt((ca.x - cb.x)**2 + (ca.y - cb.y)**2 + (ca.z - cb.z)**2)
    return max(1, math.ceil(dist / _SPACE_TRAVEL_CONSTANT))


def _divergence_coordinates(state, loc_a, loc_b):
    """Return (coord_a, coord_b) at the divergence level, or None for intra-world."""
    pid_a = str(loc_a.parent_id) if loc_a.parent_id else None
    pid_b = str(loc_b.parent_id) if loc_b.parent_id else None

    if pid_a == pid_b:
        return None  # same SignificantLocation → intra-world

    parent_a = state.locations.get(pid_a) if pid_a else None
    parent_b = state.locations.get(pid_b) if pid_b else None
    if parent_a is None or parent_b is None:
        return None

    gpid_a = str(parent_a.parent_id) if parent_a.parent_id else None
    gpid_b = str(parent_b.parent_id) if parent_b.parent_id else None

    if gpid_a == gpid_b:
        # Same System → use SignificantLocation coordinates (sublight)
        return (parent_a.coordinates, parent_b.coordinates)

    # Different Systems → use System coordinates (interstellar)
    gp_a = state.locations.get(gpid_a) if gpid_a else None
    gp_b = state.locations.get(gpid_b) if gpid_b else None
    if gp_a is None or gp_b is None:
        # Fall back to SignificantLocation coords
        return (parent_a.coordinates, parent_b.coordinates)
    return (gp_a.coordinates, gp_b.coordinates)


def build_legs(state, route: list[UUID]) -> dict[str, int]:
    """Convert a route (list of PopLocation UUIDs) into a TravelLocation.legs dict.
    Last entry always has value 0 (destination sentinel).
    """
    legs: dict[str, int] = {}
    for i, loc_id in enumerate(route):
        if i == len(route) - 1:
            legs[str(loc_id)] = 0
        else:
            legs[str(loc_id)] = leg_cost(state, loc_id, route[i + 1])
    return legs


def get_or_create_travel_location(state, legs: dict[str, int]):
    """Find an existing joinable TravelLocation or create a new one.
    Joinable = same legs dict AND current_waypoint is the first key (traveler starts at origin).
    Returns the TravelLocation instance (already added to state.locations if new).
    """
    from core.universe_core import TravelLocation, Location

    first_wp = next(iter(legs))
    for loc in state.locations.values():
        if (
            isinstance(loc, TravelLocation)
            and loc.legs == legs
            and loc.current_waypoint == first_wp
        ):
            return loc

    dest_key = next(k for k, v in legs.items() if v == 0)
    origin_loc = state.locations.get(first_wp)
    dest_loc   = state.locations.get(dest_key)
    origin_name = origin_loc.name if origin_loc else first_wp
    dest_name   = dest_loc.name   if dest_loc   else dest_key

    tl = TravelLocation(
        name=f"In transit: {origin_name} → {dest_name}",
        legs=legs,
        current_waypoint=first_wp,
        ticks_remaining=legs[first_wp],
    )
    state.locations[str(tl.id)] = tl
    return tl
```

- [ ] **Step 2: Verify routing math for the Vail route**

Run this quick check to confirm the routing utility produces expected leg costs:

```bash
cd /root/demiurge && source bin/activate && python3 -c "
from utilities.scenario_loader import load_scenario
state = load_scenario('scenarios/wardens_compact.db')

# Temporarily inject travel_features (before DB migration)
from core.universe_core import PopLocation
for lid, loc in state.locations.items():
    if isinstance(loc, PopLocation):
        if loc.name == 'Neran Surface':
            loc.travel_features = {'shuttle_service', 'space_elevator'}
        elif loc.name == 'Neran Orbital Ring':
            loc.travel_features = {'shuttle_service', 'space_elevator', 'commercial_space_port'}
        elif loc.name == 'Sethis Orbital Station':
            loc.travel_features = {'commercial_space_port', 'shuttle_service'}
        elif loc.name == 'Sethis Surface':
            loc.travel_features = {'shuttle_service'}

from utilities.travel_routing import find_route, leg_cost, build_legs
from uuid import UUID

neran_surf  = next(UUID(k) for k, v in state.locations.items() if v.name == 'Neran Surface')
sethis_surf = next(UUID(k) for k, v in state.locations.items() if v.name == 'Sethis Surface')

route = find_route(state, neran_surf, sethis_surf)
print('Route:', [state.locations[str(r)].name for r in route])
legs  = build_legs(state, route)
print('Legs:', {state.locations[k].name: v for k, v in legs.items()})
print('Total ticks:', sum(v for v in legs.values()))
"
```

Expected output:
```
Route: ['Neran Surface', 'Neran Orbital Ring', 'Sethis Orbital Station', 'Sethis Surface']
Legs: {'Neran Surface': 2, 'Neran Orbital Ring': 4, 'Sethis Orbital Station': 3, 'Sethis Surface': 0}
Total ticks: 9
```

If total ticks ≠ 9 or route has wrong length, debug `leg_cost` before proceeding.

- [ ] **Step 3: Commit**

```bash
git add utilities/travel_routing.py
git commit -m "feat: add travel routing utility (find_route, leg_cost, build_legs)"
```

---

### Task 3: Persistence — Schema, Loader, Exporter

**Files:**
- Modify: `core/scenario_schema.sql`
- Modify: `utilities/scenario_loader.py`
- Modify: `utilities/scenario_exporter.py`

- [ ] **Step 1: Add columns to `core/scenario_schema.sql`**

Find the `locations` table (line ~102). After the `distance_from_core` line and before the `visibility` line, add:

```sql
    -- TravelLocation-specific (subclass='travel_location')
    legs                  TEXT    NOT NULL DEFAULT '{}',   -- JSON object (ordered dict)
    travel_current_wp     TEXT    NOT NULL DEFAULT '',     -- UUID str of current waypoint
    travel_ticks_rem      INTEGER NOT NULL DEFAULT 0,
    travel_occupants      TEXT    NOT NULL DEFAULT '[]',   -- JSON array of UUID strs
    -- PopLocation addition
    travel_features       TEXT    NOT NULL DEFAULT '[]',   -- JSON array (stored as set)
```

The block should look like:
```sql
    pop_ids             TEXT    NOT NULL DEFAULT '[]',
    distance_from_core  INTEGER NOT NULL DEFAULT 0,
    -- TravelLocation-specific (subclass='travel_location')
    legs                  TEXT    NOT NULL DEFAULT '{}',
    travel_current_wp     TEXT    NOT NULL DEFAULT '',
    travel_ticks_rem      INTEGER NOT NULL DEFAULT 0,
    travel_occupants      TEXT    NOT NULL DEFAULT '[]',
    -- PopLocation addition
    travel_features       TEXT    NOT NULL DEFAULT '[]',
    -- Window visibility
    visibility  REAL    NOT NULL DEFAULT 0.0,
    pinned      INTEGER NOT NULL DEFAULT 0
```

- [ ] **Step 2: Update `scenario_loader.py` — `PopLocation` branch + new `TravelLocation` branch**

In `utilities/scenario_loader.py`, find the `elif subclass == "pop_location":` branch (line ~407). Add `travel_features` to the `PopLocation(...)` constructor:

```python
        elif subclass == "pop_location":
            loc = PopLocation(
                id=loc_id,
                name=row["name"],
                description=description,
                location_type=location_type,
                parent_id=parent_id,
                child_ids=child_ids,
                traits=traits,
                condition=condition,
                coordinates=coordinates,
                visibility=visibility,
                pinned=pinned,
                pop_ids=[UUID(x) for x in _j(row.get("pop_ids", "[]"))],
                distance_from_core=int(row.get("distance_from_core", 0) or 0),
                travel_features=set(_j(row.get("travel_features", "[]"))),
            )
```

Then add a new branch **before** the `else:` fallback:

```python
        elif subclass == "travel_location":
            from core.universe_core import TravelLocation
            loc = TravelLocation(
                id=loc_id,
                name=row["name"],
                description=description,
                location_type=location_type,
                parent_id=parent_id,
                child_ids=child_ids,
                traits=traits,
                condition=condition,
                coordinates=coordinates,
                visibility=visibility,
                pinned=pinned,
                legs=_jd(row.get("legs", "{}")),
                current_waypoint=row.get("travel_current_wp", ""),
                ticks_remaining=int(row.get("travel_ticks_rem", 0) or 0),
                occupants=[UUID(x) for x in _j(row.get("travel_occupants", "[]"))],
            )
```

(`_jd` is already defined in the loader for JSON dict deserialization.)

- [ ] **Step 3: Update `scenario_exporter.py`**

In `utilities/scenario_exporter.py`, update `_loc_subclass` to handle `TravelLocation`. Add the new case before `return "location"`:

```python
def _loc_subclass(loc: Location) -> str:
    if isinstance(loc, SignificantLocation):
        return "significant_location"
    if isinstance(loc, System):
        return "system"
    if isinstance(loc, PopLocation):
        return "pop_location"
    if isinstance(loc, TravelLocation):
        return "travel_location"
    return "location"
```

Also add `TravelLocation` to the imports at the top of the file (wherever `PopLocation`, `SignificantLocation`, `System` are imported from `core.universe_core`).

Then update `_write_locations`. The full modified function:

```python
def _write_locations(conn, state: SimulationState):
    from core.universe_core import TravelLocation
    for loc in state.locations.values():
        subclass = _loc_subclass(loc)

        parent_id_str = str(loc.parent_id) if loc.parent_id else None
        coords_x = loc.coordinates.x
        coords_y = loc.coordinates.y
        coords_z = loc.coordinates.z

        # Type-specific field defaults
        star_type = "main_sequence"
        domain_expression = "{}"
        lf_overt = lf_subtle = lf_proxius = lf_direct = 0.0
        civilization_ids = species_ids = proxius_ids = herald_ids_loc = "[]"
        geo_tags = atmo_tags = "[]"
        age = 0.0
        pop_ids = "[]"
        distance_from_core = 0
        travel_features = "[]"
        legs = "{}"
        travel_current_wp = ""
        travel_ticks_rem = 0
        travel_occupants = "[]"

        if isinstance(loc, System):
            star_type = loc.star_type.value
        elif isinstance(loc, SignificantLocation):
            domain_expression = _j(loc.domain_expression)
            lf = loc.local_footprint
            lf_overt   = lf.overt_miracles
            lf_subtle  = lf.subtle_influence
            lf_proxius = lf.proxius_activity
            lf_direct  = lf.direct_creation
            civilization_ids = _j(loc.civilization_ids)
            species_ids      = _j(loc.species_ids)
            proxius_ids      = _j(loc.proxius_ids)
            herald_ids_loc   = _j(loc.herald_ids)
            geo_tags  = _j(loc.geo_tags)
            atmo_tags = _j(loc.atmo_tags)
            age = loc.age
        elif isinstance(loc, PopLocation):
            pop_ids = _j(loc.pop_ids)
            distance_from_core = int(loc.distance_from_core)
            travel_features = _j(sorted(loc.travel_features))
        elif isinstance(loc, TravelLocation):
            legs             = _j(loc.legs)
            travel_current_wp = loc.current_waypoint
            travel_ticks_rem  = loc.ticks_remaining
            travel_occupants  = _j([str(oid) for oid in loc.occupants])

        conn.execute(
            """INSERT INTO locations
               (id, name, description, location_type, subclass, parent_id, child_ids,
                traits, condition,
                coordinates_x, coordinates_y, coordinates_z, star_type,
                domain_expression,
                lf_overt_miracles, lf_subtle_influence, lf_proxius_activity, lf_direct_creation,
                civilization_ids, species_ids, proxius_ids, herald_ids_loc,
                geo_tags, atmo_tags, age,
                pop_ids, distance_from_core,
                legs, travel_current_wp, travel_ticks_rem, travel_occupants,
                travel_features,
                visibility, pinned)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?,
                       ?, ?, ?, ?,
                       ?,
                       ?, ?, ?, ?,
                       ?, ?, ?, ?,
                       ?, ?, ?,
                       ?, ?,
                       ?, ?, ?, ?,
                       ?,
                       ?, ?)""",
            (
                str(loc.id), loc.name, loc.description,
                loc.location_type, subclass, parent_id_str,
                _j(loc.child_ids), _j(loc.traits), loc.condition.value,
                coords_x, coords_y, coords_z, star_type,
                domain_expression,
                lf_overt, lf_subtle, lf_proxius, lf_direct,
                civilization_ids, species_ids, proxius_ids, herald_ids_loc,
                geo_tags, atmo_tags, age,
                pop_ids, distance_from_core,
                legs, travel_current_wp, travel_ticks_rem, travel_occupants,
                travel_features,
                loc.visibility, int(loc.pinned),
            ),
        )
```

- [ ] **Step 4: Commit**

```bash
git add core/scenario_schema.sql utilities/scenario_loader.py utilities/scenario_exporter.py
git commit -m "feat: add TravelLocation + travel_features persistence columns"
```

---

### Task 4: Tick Logic

**Files:**
- Modify: `logic/tick_logic.py`

- [ ] **Step 1: Add import for `TravelLocation` and routing utilities at top of method**

`tick_logic.py` uses lazy imports inside methods. No top-of-file change needed — imports go inside the methods below.

- [ ] **Step 2: Add class constants for Vail**

Find the existing constants near line 4679:

```python
_KARATH_OMN_NAME      = "Karath Omn"
_KARATH_OMN_SHUTTLE_A = "Neran Surface"
_KARATH_OMN_SHUTTLE_B = "Neran Orbital Ring"
```

Add two more constants directly below them:

```python
_DURENN_VAIL_NAME = "Durenn Vail"
_VAIL_DEST_A      = "Neran Surface"
_VAIL_DEST_B      = "Sethis Surface"
```

- [ ] **Step 3: Rewrite `_resolve_mortal_travel_decisions`**

Replace the entire method (lines ~4683–4721) with:

```python
def _resolve_mortal_travel_decisions(self, state: SimulationState) -> list[str]:
    """Phase 2.6a — assign new TravelIntents via TravelLocation routing."""
    from core.universe_core import PopLocation, TravelLocation
    from core.agent_core import TravelIntent
    from utilities.travel_routing import find_route, build_legs, get_or_create_travel_location

    narratives: list[str] = []
    pop_locs_by_name: dict[str, str] = {
        loc.name: lid
        for lid, loc in state.locations.items()
        if isinstance(loc, PopLocation)
    }

    for mortal in state.mortals.values():
        if mortal.travel_intent is not None:
            continue

        current_loc = state.locations.get(str(mortal.current_location))
        current_name = current_loc.name if current_loc else ""

        dest_name: str | None = None
        if mortal.name == self._KARATH_OMN_NAME:
            dest_name = (
                self._KARATH_OMN_SHUTTLE_B
                if current_name == self._KARATH_OMN_SHUTTLE_A
                else self._KARATH_OMN_SHUTTLE_A
            )
        elif mortal.name == self._DURENN_VAIL_NAME:
            dest_name = (
                self._VAIL_DEST_B
                if current_name == self._VAIL_DEST_A
                else self._VAIL_DEST_A
            )

        if dest_name is None or dest_name not in pop_locs_by_name:
            continue

        dest_id_str = pop_locs_by_name[dest_name]
        route = find_route(state, mortal.current_location, UUID(dest_id_str))
        if route is None or len(route) < 2:
            continue

        legs  = build_legs(state, route)
        tl    = get_or_create_travel_location(state, legs)
        tl.occupants.append(mortal.id)
        mortal.travel_intent = TravelIntent(travel_location_id=tl.id)

        total_ticks = sum(v for v in legs.values())
        narratives.append(
            f"{mortal.name} begins traveling to {dest_name} "
            f"({total_ticks} tick{'s' if total_ticks != 1 else ''})."
        )
    return narratives
```

- [ ] **Step 4: Rewrite `_process_mortal_travel`**

Replace the entire method (lines ~4723–4737) with:

```python
def _process_mortal_travel(self, state: SimulationState) -> list[str]:
    """Phase 2.6b — advance TravelLocation countdowns; teleport on arrival."""
    from core.universe_core import TravelLocation
    from uuid import UUID

    narratives: list[str] = []
    to_remove: list[str] = []

    for lid, loc in list(state.locations.items()):
        if not isinstance(loc, TravelLocation):
            continue

        loc.ticks_remaining -= 1
        if loc.ticks_remaining > 0:
            continue

        leg_keys = list(loc.legs.keys())
        try:
            current_idx = leg_keys.index(loc.current_waypoint)
        except ValueError:
            to_remove.append(lid)
            continue

        next_idx = current_idx + 1
        if next_idx >= len(leg_keys):
            to_remove.append(lid)
            continue

        next_wp   = leg_keys[next_idx]
        next_cost = loc.legs[next_wp]

        if next_cost == 0:
            # Arrival
            dest_loc  = state.locations.get(next_wp)
            dest_name = dest_loc.name if dest_loc else next_wp
            for occ_id in loc.occupants:
                mortal = state.mortals.get(str(occ_id))
                if mortal:
                    mortal.current_location = UUID(next_wp)
                    mortal.travel_intent    = None
                    narratives.append(f"{mortal.name} arrives at {dest_name}.")
            to_remove.append(lid)
        else:
            loc.current_waypoint  = next_wp
            loc.ticks_remaining   = next_cost

    for lid in to_remove:
        state.locations.pop(lid, None)

    return narratives
```

- [ ] **Step 5: Commit**

```bash
git add logic/tick_logic.py
git commit -m "feat: rewrite travel tick phases to use TravelLocation"
```

---

### Task 5: DB Migration + Travel Features Injection

**Files:**
- `scenarios/wardens_compact.db` (updated in-place by migrator, then patched with SQL)

- [ ] **Step 1: Run the scenario migrator to apply new schema**

```bash
cd /root/demiurge && source bin/activate && python main.py --rebuild --scenario 2>&1
```

Expected: `wardens_compact.db` is updated to the new schema. The new columns (`travel_features`, `legs`, etc.) will exist with their default values.

Verify the new columns are present:

```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('scenarios/wardens_compact.db')
cols = [r[1] for r in conn.execute('PRAGMA table_info(locations)').fetchall()]
print([c for c in cols if 'travel' in c or c == 'legs'])
"
```

Expected: `['legs', 'travel_current_wp', 'travel_ticks_rem', 'travel_occupants', 'travel_features']`

- [ ] **Step 2: Set `travel_features` on the 4 route PopLocations**

```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('scenarios/wardens_compact.db')
updates = [
    ('2ac3f5fc-d4fd-4d72-be5b-eada9fb43e6d', '[\"space_elevator\"]'),
    ('b6e77481-97bd-4d4f-a948-4216d22522c3', '[\"shuttle_service\",\"space_elevator\",\"commercial_space_port\"]'),
    ('38474e57-8d40-4397-ade8-b9751cfa7d3c', '[\"commercial_space_port\",\"shuttle_service\"]'),
    ('ef5b9dc6-de3d-46a4-a9e4-6f8e1a6b76bc', '[\"shuttle_service\"]'),
]
for uid, features in updates:
    conn.execute('UPDATE locations SET travel_features=? WHERE id=?', (features, uid))
    name = conn.execute('SELECT name FROM locations WHERE id=?', (uid,)).fetchone()[0]
    print(f'Updated {name}: {features}')
conn.commit()
"
```

- [ ] **Step 3: Verify Vail is already in the scenario at Neran Surface**

```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('scenarios/wardens_compact.db')
r = conn.execute('SELECT name, current_location FROM mortals WHERE name=\"Durenn Vail\"').fetchone()
print('Vail:', r)
# Confirm current_location is Neran Surface
loc = conn.execute('SELECT name FROM locations WHERE id=?', (r[1],)).fetchone()
print('At:', loc)
"
```

Expected: Vail exists with `current_location` pointing to Neran Surface.

- [ ] **Step 4: Smoke test — full load/export round-trip**

```bash
python3 -c "
from utilities.scenario_loader import load_scenario
from utilities.scenario_exporter import export_scenario
state = load_scenario('scenarios/wardens_compact.db')

# Check Vail is loaded
vail = next((m for m in state.mortals.values() if m.name == 'Durenn Vail'), None)
print('Vail loaded:', vail is not None)
print('Vail location:', state.locations.get(str(vail.current_location)).name if vail else 'N/A')

# Check travel_features loaded
from core.universe_core import PopLocation
for loc in state.locations.values():
    if isinstance(loc, PopLocation) and loc.travel_features:
        print(f'  {loc.name}: {sorted(loc.travel_features)}')
"
```

Expected: Vail is loaded at Neran Surface; the 4 route PopLocations show their travel_features.

- [ ] **Step 5: Commit**

```bash
git add scenarios/wardens_compact.db
git commit -m "feat: inject travel_features into wardens_compact.db route PopLocations"
```

---

### Task 6: Validation Autoplay Strategy

**Files:**
- Create: `autoplay/strategies/vail_travel_test.py`

- [ ] **Step 1: Create the strategy**

```python
"""
autoplay/strategies/vail_travel_test.py

Validates the Durenn Vail Neran↔Sethis travel route end-to-end.
Tracks Vail's position each tick and verifies she completes the journey.

Expected: Vail departs tick 1, arrives Sethis Surface on tick 10
          (2 + 4 + 3 = 9 ticks in transit). Then returns.
"""
from __future__ import annotations
from core.universe_core import TravelLocation, PopLocation
from core.agent_core import TravelIntent
from autoplay.strategies._helpers import queue, world_id
from logic.tick_logic import TickLoop, SimulationState

VAIL_NAME = "Durenn Vail"
MAX_TICKS = 25


def _vail(state: SimulationState):
    return next((m for m in state.mortals.values() if m.name == VAIL_NAME), None)


def _loc_name(state: SimulationState, loc_id) -> str:
    if loc_id is None:
        return "?"
    loc = state.locations.get(str(loc_id))
    return loc.name if loc else str(loc_id)


def _print_status(state: SimulationState, tick: int) -> None:
    vail = _vail(state)
    if vail is None:
        print(f"  tick {tick:3d} | Vail NOT FOUND")
        return

    loc_name = _loc_name(state, vail.current_location)
    ti = vail.travel_intent
    if ti is not None:
        tl = state.locations.get(str(ti.travel_location_id))
        if isinstance(tl, TravelLocation):
            wp_name = _loc_name(state, tl.current_waypoint)
            dest_key = next(k for k, v in tl.legs.items() if v == 0)
            dest_name = _loc_name(state, dest_key)
            print(f"  tick {tick:3d} | IN TRANSIT → {dest_name}"
                  f"  (leg: {wp_name}, {tl.ticks_remaining} tick(s) left)")
        else:
            print(f"  tick {tick:3d} | travel_intent points to missing TravelLocation!")
    else:
        print(f"  tick {tick:3d} | AT {loc_name}")


def decide(loop: TickLoop, state: SimulationState, tick: int) -> str:
    _print_status(state, tick)

    if tick >= MAX_TICKS:
        vail = _vail(state)
        if vail:
            loc = _loc_name(state, vail.current_location)
            ti  = vail.travel_intent
            print(f"\n=== RESULT at tick {tick} ===")
            print(f"Vail at: {loc}, in transit: {ti is not None}")
            # Basic assertions
            if ti is None and loc in ("Neran Surface", "Sethis Surface"):
                print("PASS: Vail completed at least one leg.")
            else:
                print("FAIL: Vail did not complete a full journey within 25 ticks.")

    from core.action_core import EssenceHarvestIntent, TargetType
    queue(loop, state, "harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(concealment_priority=0.9))
    return "Idle harvest (watching Vail)."
```

- [ ] **Step 2: Run the strategy and verify Vail travels**

```bash
cd /root/demiurge && source bin/activate && python main.py --autoplay vail_travel_test 2>&1
```

Expected output should show:
- Tick 1: `IN TRANSIT → Sethis Surface  (leg: Neran Surface, 2 tick(s) left)` 
- Tick 3: `IN TRANSIT → Sethis Surface  (leg: Neran Orbital Ring, 4 tick(s) left)`
- Tick 7: `IN TRANSIT → Sethis Surface  (leg: Sethis Orbital Station, 3 tick(s) left)`
- Tick 10: `AT Sethis Surface`
- Tick 11: `IN TRANSIT → Neran Surface ...` (return trip begins)
- Tick 25: `PASS: Vail completed at least one leg.`

If you see `travel_intent points to missing TravelLocation!`, the TravelLocation was dropped from `state.locations` prematurely — check `_process_mortal_travel`.

If Vail never departs (stays AT Neran Surface every tick), the routing is failing — check that `travel_features` loaded correctly and `find_route` finds the path.

- [ ] **Step 3: Commit**

```bash
git add autoplay/strategies/vail_travel_test.py
git commit -m "feat: add vail_travel_test autoplay strategy"
```

---

### Task 7: Detail Renderer

**Files:**
- Modify: `ui/detail_renderers.py`

- [ ] **Step 1: Add `render_travel_location_detail`**

In `ui/detail_renderers.py`, add the following function before the `RENDERERS` dict (line ~1227):

```python
def render_travel_location_detail(state: "SimulationState", tl_id: str) -> Text:
    from core.universe_core import TravelLocation
    loc = state.locations.get(tl_id)
    if not isinstance(loc, TravelLocation):
        return _not_found(f"TravelLocation {tl_id}")

    lines: list[str] = []
    a = lines.append

    a(f"[bold #b0804a]IN TRANSIT: {_e(loc.name)}[/]")
    a("")

    # Route summary
    leg_keys = list(loc.legs.keys())
    for i, k in enumerate(leg_keys):
        cost = loc.legs[k]
        name = state.locations.get(k)
        disp = _e(name.name) if name else k[:8]
        active = " ◀ current" if k == loc.current_waypoint else ""
        sentinel = " (destination)" if cost == 0 else f"  [{cost} tick{'s' if cost != 1 else ''}]"
        a(f"  {'→ ' if i > 0 else '   '}{disp}{sentinel}{active}")

    a("")
    a(f"  ticks remaining on current leg: [#e0c080]{loc.ticks_remaining}[/]")

    if loc.occupants:
        a("")
        a("  Travelers:")
        for occ_id in loc.occupants:
            m = state.mortals.get(str(occ_id))
            name = _e(m.name) if m else str(occ_id)[:8]
            a(f"    • {name}")

    return Text.from_markup("\n".join(lines))
```

- [ ] **Step 2: Register in `RENDERERS`**

Update the `RENDERERS` dict to add the new renderer:

```python
RENDERERS = {
    "world":          render_world_detail,
    "system":         render_system_detail,
    "galaxy":         render_galaxy_detail,
    "poploc":         render_poploc_detail,
    "travel_location": render_travel_location_detail,
    "civ":            render_civ_detail,
    "mortal":         render_mortal_detail,
    "luminary":       render_luminary_detail,
    "pop":            render_pop_detail,
    "species":        render_species_detail,
}
```

- [ ] **Step 3: Run the wardens_compact autoplay to confirm no renderer errors**

```bash
cd /root/demiurge && source bin/activate && python main.py --autoplay wardens_compact 2>&1 | tail -20
```

Expected: clean run, no `KeyError` or `AttributeError` related to TravelLocation.

- [ ] **Step 4: Commit**

```bash
git add ui/detail_renderers.py
git commit -m "feat: add TravelLocation detail renderer"
```

---

### Task 8: Final Integration Run

- [ ] **Step 1: Run `vail_travel_test` for a clean pass**

```bash
cd /root/demiurge && source bin/activate && python main.py --autoplay vail_travel_test 2>&1
```

Verify:
1. Vail departs Neran Surface on tick 1 (2 ticks on first leg)
2. Leg transitions happen at the right ticks (tick 3: orbital leg, tick 7: Sethis orbit leg)
3. Vail arrives Sethis Surface on tick 10
4. Vail begins return journey on tick 11
5. Final line: `PASS: Vail completed at least one leg.`

- [ ] **Step 2: Run the default wardens_compact strategy to check for regressions**

```bash
python main.py --autoplay wardens_compact 2>&1 | tail -5
```

Karath Omn should still shuttle between Neran Surface and Neran Orbital Ring as before (2-tick intra-world trip).

- [ ] **Step 3: Push to origin main**

```bash
git push origin main
```
