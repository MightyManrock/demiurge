> **Status:** active
> **TO-DO ref:** TravelLocation and travel routing
> **Last updated:** 2026-05-22

## Goal

Promote `TravelLocation` to a first-class scryable entity. Replace the abstract "in transit" state with a real location object that has mechanical meaning: observable, joinable by multiple travelers on the same route, and a foundation for future in-transit events. Add `travel_features` to `PopLocation` for infrastructure-gated routing.

## Approach

### Phase 1 — Data model

- Add `TravelLocation(BaseModel)` to `core/universe_core.py` with `route: list[UUID]` (ordered `PopLocation` waypoints), `current_leg: int`, `occupants: list[UUID]` (mortal IDs)
- Add `travel_features: set[str] = set()` to `PopLocation`
- Extend `TravelIntent` in `core/agent_core.py` to reference a `TravelLocation` ID instead of just a raw destination

### Phase 2 — Routing

- Add a route-planning function (graph traversal over `PopLocations` connected by shared `travel_features`) in `logic/tick_logic.py` or a new `utilities/travel_routing.py`
- Two `PopLocations` are connectable iff they share at least one `travel_feature`

### Phase 3 — Persistence

- Add `travel_locations` table to `core/scenario_schema.sql`
- Load in `utilities/scenario_loader.py`
- Export in `utilities/scenario_exporter.py`
- Add `travel_features` column to `pop_locations` table; load/export accordingly
- Run migrator

### Phase 4 — Tick logic

- On new travel intent: instantiate or join an existing `TravelLocation` for the route
- `_process_mortal_travel`: advance `current_leg`, handle multi-occupant leg advancement, clear `TravelLocation` when all occupants arrive

### Phase 5 — Scryability

- `TravelLocation` shows up in Scry results and Locations tab while occupied
- Dev mode: mortal detail tab shows current leg and travel-location ID

### Phase 6 — Durenn Vail test

- Inject Durenn Vail into `wardens_compact.db` as a merchant on Neran with an autonomous Neran→Sethis route
- Add `travel_features` to the four relevant `PopLocations` (see brainstorming doc)
- Validates: routing, `TravelLocation` instantiation, leg advancement across `SignificantLocation` boundary, scryability, arrival

## Files affected

- `core/universe_core.py` — `TravelLocation` model; `travel_features` on `PopLocation`
- `core/agent_core.py` — updated `TravelIntent` referencing `TravelLocation`
- `core/scenario_schema.sql` — `travel_locations` table; `travel_features` column on `pop_locations`
- `utilities/scenario_loader.py` — load `travel_locations`, `travel_features`
- `utilities/scenario_exporter.py` — export same
- `logic/tick_logic.py` — routing + updated travel processing
- `utilities/travel_routing.py` *(new, optional)* — route-planning graph traversal
- `ui/detail_renderers.py` — `TravelLocation` scry display; dev mode mortal detail
- `scenarios/wardens_compact.db` — Durenn Vail + travel_features injection

## Notes

- Prerequisite: `mortal-travel-initial.md` (complete) — `TravelIntent`, tick phases, and basic leg-based countdown are already in place.
- Design doc: `docs/Brainstorming/travel_location_system.md`
- Joinable routes (second traveler merges into existing `TravelLocation`) should be in scope for Phase 4 — it's the main reason `TravelLocation` exists as a shared entity.
- Infrastructure-as-target (disrupting a `travel_feature`) and feature-based modifiers are deferred to a future plan.
