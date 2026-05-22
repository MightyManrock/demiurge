> **Status:** complete
> **TO-DO ref:** TravelNetwork refactor
> **Last updated:** 2026-05-22

## Goal

Replace the implicit `travel_features: set[str]` string-intersection approach with explicit `TravelNetwork` objects. Two locations are adjacent for routing purposes iff they share a TravelNetwork — same semantics, but topology is now declared rather than inferred from matching tag strings. This eliminates the class of BFS shortcut bugs where unintended feature sharing creates phantom routes.

## Approach

### Phase 1 — Data model

- Add `TravelNetwork(BaseModel)` to `core/universe_core.py`:
  - `id: UUID`
  - `name: str` — human-readable, used in TravelLocation naming (e.g. "Ardent Space Elevator")
  - `member_ids: list[UUID]` — PopLocation UUIDs; membership means full mutual adjacency (any member → any other member is one leg)
- Add `travel_network_ids: list[UUID] = []` to `PopLocation`, replacing `travel_features: set[str]`
- Add `travel_networks: dict[str, TravelNetwork] = {}` to `SimulationState`

### Phase 2 — Persistence

- Add `travel_networks` table to `core/scenario_schema.sql`:
  ```sql
  CREATE TABLE IF NOT EXISTS travel_networks (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      member_ids TEXT NOT NULL DEFAULT '[]'
  );
  ```
- Replace `travel_features` column on `locations` with `travel_network_ids TEXT NOT NULL DEFAULT '[]'`
- Load TravelNetworks in `utilities/scenario_loader.py`; populate `state.travel_networks`
- Export in `utilities/scenario_exporter.py`
- Run migrator to bring all scenario DBs up to current schema

### Phase 3 — Routing logic

- Update `utilities/travel_routing.py`: replace feature-intersection adjacency check with TravelNetwork membership check
  - Two PopLocations are adjacent iff they share at least one TravelNetwork ID
- Update `get_or_create_travel_location()`: use network name(s) for TravelLocation naming
- No change to BFS structure, leg cost calculation, or tick logic

### Phase 4 — DB migration for wardens_compact

- Create 3 TravelNetwork objects (working names):
  - "Neran Space Elevator" — members: [Neran Surface, Neran Orbital Ring]
  - "Ardent Commercial Port" — members: [Neran Orbital Ring, Sethis Orbital Station]
  - "Sethis Shuttle Service" — members: [Sethis Orbital Station, Sethis Surface]
- Assign `travel_network_ids` to the 4 PopLocations accordingly
- Remove the old `travel_features` data

### Phase 5 — Validation

- Run `vail_travel_test` autoplay: expect identical 9-tick outbound / 9-tick return / PASS
- No change to tick counts or route structure — this is a pure data-model swap

## Files affected

- `core/universe_core.py` — `TravelNetwork` model; `PopLocation.travel_network_ids` replaces `travel_features`
- `core/scenario_schema.sql` — `travel_networks` table; updated `locations` columns
- `utilities/scenario_loader.py` — load TravelNetworks into `state.travel_networks`
- `utilities/scenario_exporter.py` — export TravelNetworks
- `utilities/travel_routing.py` — adjacency check rewritten to use TravelNetwork membership
- `logic/tick_logic.py` — `SimulationState.travel_networks` field; pass-through to routing
- `scenarios/wardens_compact.db` — inject TravelNetworks, remove travel_features data

## Notes

- Prerequisite: `travel-location-system.md` (complete)
- Fully-connected semantics within a network: all members are mutually adjacent. Directed or ordered routes are modeled by using small 2-node networks.
- The `travel_features` field on `PopLocation` is removed entirely — no fallback compatibility needed.
- `warp-gate-expansion.md` builds on this plan; do not start it until this one passes Vail validation.
