> **Status:** complete
> **TO-DO ref:** Baby steps toward an expanded Agent system
> **Last updated:** 2026-05-21
> **Completed:** 2026-05-21

## Goal

Implement the first phase of mortal movement: intra-SignificantLocation travel between PopLocations. Mortals get a `TravelIntent` agent state; tick logic handles countdown and arrival teleport. Validated via a hardcoded Karath Omn shuttle in the Warden's Compact scenario.

## Approach

### Phase 1 — Data model
- Add `TravelIntent(BaseModel)` to `core/agent_core.py` with `destination: UUID`, `ticks_remaining: int`, `in_transit: bool = False`
- Add `travel_intent: Optional[TravelIntent] = None` to `NotableMortal` in `core/universe_core.py`

### Phase 2 — Persistence
- Add `travel_intent_json TEXT DEFAULT NULL` to `mortals` table in `core/scenario_schema.sql`
- Load in `utilities/scenario_loader.py` via `row.get("travel_intent_json")`
- Export in `utilities/scenario_exporter.py`
- Run migrator to bring scenario DBs up to current schema

### Phase 3 — Tick logic (Phase 2.6)
- Add `_resolve_mortal_travel_decisions(self, state)` — sets new TravelIntents; hardcoded Karath Omn shuttle between Neran Surface and Neran Orbital Ring
- Add `_process_mortal_travel(self, state)` — decrements countdown, teleports on arrival, clears intent
- Hook both after Phase 2.5 (Proxius agents), before Phase 3 (domain profiling)

### Phase 4 — Dev mode display
- Show travel intent in mortal detail tab when `DEV_MODE` is on

### Travel time formula (from brainstorming doc)
```
travel_ticks = distance_between + 1          # default
travel_ticks = distance_between              # waived when both distances > 0
```
Karath Omn: Neran Surface (dist=0) ↔ Neran Orbital Ring (dist=2) → 3 ticks each way.

## Files affected

- `core/agent_core.py` — new `TravelIntent` model
- `core/universe_core.py` — `travel_intent` field on `NotableMortal`
- `core/scenario_schema.sql` — `travel_intent_json` column in `mortals`
- `utilities/scenario_loader.py` — load `travel_intent_json`
- `utilities/scenario_exporter.py` — export `travel_intent_json`
- `logic/tick_logic.py` — Phase 2.6 travel resolution + processing
- `ui/detail_renderers.py` — dev mode travel display

## Notes

- Karath Omn is currently at Neran Orbital Ring (`b6e77481-97bd-4d4f-a948-4216d22522c3`); both PopLocations already exist in `wardens_compact.db` with correct `distance_from_core` values — no DB injection needed.
- Design doc: `docs/Brainstorming/travel_system_initial.md`
- Inter-world travel, autonomous travel decisions, and in-transit events are explicitly deferred (see Future Extensions in brainstorming doc).
