> status: active | last updated: 2026-06-09

# Pop Migration and Faction Directives

## Goal

Give Pops the ability to actually move between PopLocations, then build the Faction Directive system that assigns each Pop a *purpose* — overriding default survival-optimization behavior with faction-defined roles. The Oros scenario is the reference implementation: Stonecaller trade couriers, desert patrol bands, garrison support pairs, pilgrimage events, and sacred-site bonuses all fall under this plan.

The resource container models and Band grouping (Phases 0–0.5) are prerequisites for everything that follows. Pop migration is the critical path for behavioral mechanics.

---

## Phase 0: New Data Models + Persistence

**Goal:** Define all new container and grouping models, add fields to existing models, and update schema/loader/exporter. **No behavioral changes** — all existing logic continues to work; these are purely additive. Phase 0.5 then wires the new structures into existing behavior.

### `Band`

A politically lightweight travel-and-resource-sharing unit. Distinct from Faction: band membership carries no diplomatic weight, creates no raid-politics implications, and implies no hierarchy. A Pop can belong to both a Band and a Faction (e.g. the Dunes of Tor Pops are both ADC faction members and members of the same band). A Pop can belong to a Band with no Faction (the Plains of Kir'an and Asvelim Savannah nomads — visible to other factions as unaffiliated).

```python
class Band(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    label: str = ""
    pop_ids: list[UUID] = []
    mortal_ids: list[UUID] = []
```

`SimulationState` gains `bands: dict[str, Band] = {}`.

`Pop` gains `band_id: Optional[UUID] = None`.

`NotableMortal` gains `band_id: Optional[UUID] = None` (for embedded mortals like Asha Keln who travel with their band).

Schema: a `bands` table (`id`, `label`, `pop_ids` JSON, `mortal_ids` JSON) + `pop.band_id` and `mortal.band_id` columns.

### `ResourceStockpile`

Replaces `PopLocation.resource_stockpile: dict[str, float]`. A location can hold multiple stockpiles — one per owning Faction or Band, plus an optional public one.

```python
class ResourceStockpile(BaseModel):
    quantities: dict[str, float] = {}
    owner_faction_id: Optional[UUID] = None
    owner_band_id: Optional[UUID] = None
    # Both None = public; any co-located entity may draw.
```

Access rule (implemented in Phase 0.5 as `can_access_stockpile(entity, stockpile) -> bool`):
- Public (both owners None) → True for any co-located entity.
- `owner_faction_id` set → True if entity's `faction_ids` contains it.
- `owner_band_id` set → True if entity's `band_id` matches.
- Either condition is sufficient — a Pop with both band and faction access uses whichever applies.

`PopLocation.resource_stockpile: dict[str, float]` is replaced by `PopLocation.stockpiles: list[ResourceStockpile]`. The loader migrates the old dict to a single public `ResourceStockpile` on load; the exporter serialises the list.

### `CargoStockpile`

Mobile resource container for Pops executing supply runs or raids.

```python
class CargoStockpile(BaseModel):
    quantities: dict[str, float] = {}
    max_slots: int = 4        # max distinct resource types simultaneously held
    slot_capacity: float = 20.0  # max quantity per slot
```

No owner fields — cargo is always the carrier's. Transfer functions (Phase 0.5):
- `load_cargo(cargo, stockpile, resource_type, qty, entity) -> float`
- `unload_cargo(cargo, stockpile, resource_type, qty) -> float`

`Pop.cargo: Optional[CargoStockpile] = None` (introduced in Phase 2) uses this type.

### `MortalInventory` capacity fields

`MortalInventory` gains two new fields (enforcement wired in Phase 0.5):
- `max_slots: int = 4` — maximum distinct resource types held simultaneously.
- `slot_capacity: float = 10.0` — maximum quantity per resource type.

Transfer functions (Phase 0.5):
- `mortal_draw_from_stockpile(inventory, stockpile, resource_type, qty, entity) -> float`
- `mortal_donate_to_stockpile(inventory, stockpile, resource_type, qty) -> float`

### Files affected

- `core/universe_core.py` — `Band` model; `SimulationState.bands`; `PopLocation.stockpiles` replaces `resource_stockpile`; `Pop.band_id`; `NotableMortal.band_id`
- `core/agent_core.py` — `ResourceStockpile`, `CargoStockpile` models; `MortalInventory.max_slots` / `slot_capacity`
- `core/scenario_schema.sql` — `bands` table; `pop.band_id`; `mortal.band_id`; `pop_location.stockpiles` JSON column replaces `resource_stockpile`
- `utilities/scenario_loader.py` — load `bands` table; `Pop.band_id`; migrate old `resource_stockpile` dict to single public `ResourceStockpile`
- `utilities/scenario_exporter.py` — export `bands`; serialise `PopLocation.stockpiles`

---

## Phase 0.5: Wire Models into Existing Behavior

**Goal:** Replace all current ad-hoc stockpile reads with the new access-controlled API. Enforce `MortalInventory` capacity limits. No new gameplay mechanics — existing behavior is preserved, just running through the new structures.

### `can_access_stockpile(entity, stockpile) -> bool`

Shared utility in `core/agent_core.py` (or `logic/sim_utils.py`). Implements the access rule defined in Phase 0. All stockpile reads go through this.

### Entitlement resolver

`_resolve_mortal_entitlement` in `tick_logic.py` currently navigates Pop relationships to decide stockpile access. Replace with: find all `ResourceStockpile` objects at the mortal's location where `can_access_stockpile(mortal, stockpile)` is True. Draw from the highest-quantity accessible stockpile first. Entitlement factor (the existing `0.0–1.0` fraction) is preserved — it scales *how much* is drawn, not *whether* access is granted.

### `MortalInventory.add_resource()` enforcement

`add_resource()` enforces `max_slots` and `slot_capacity`: returns the amount actually added (may be less than requested). All callers — forage, hunt, collect in `tick_logic.py` — receive the capped quantity without change to their own logic.

### Transfer functions

`load_cargo`, `unload_cargo`, `mortal_draw_from_stockpile`, `mortal_donate_to_stockpile` implemented here. These are used immediately by the mortal sustenance pass (draw from stockpile before travel) and will be reused by Phase 2 directive execution.

### Files affected

- `core/agent_core.py` — `can_access_stockpile`; `add_resource` enforcement; transfer functions
- `logic/tick_logic.py` — all `loc.resource_stockpile` reads replaced with `stockpiles` list + access check; entitlement resolver rewrite; `add_resource` return value used in forage/hunt/collect
- `logic/mortal_agent_logic.py` — any direct stockpile reads
- `logic/pop_agent_logic.py` — stockpile reads in action resolution
- `tests/` — update fixtures constructing `PopLocation` with `resource_stockpile`; add tests for `can_access_stockpile` and capacity enforcement

---

## Phase 1: Real Pop Migration

**Goal:** Pops can travel between PopLocations using the same TravelLocation infrastructure that mortals already use.

### Data model

`TravelLocation` already has `pop_ids: list[UUID]` — Pops in transit live there. No new model needed.

`Pop` needs:
- `migration_ticks_remaining: int = 0` — ticks left in current leg (mirrors `MortalAgentState.migration_ticks_remaining`, which already exists on `PopAgentState`)
- `migration_destination_id: Optional[UUID] = None` — final destination PopLocation
- `migration_travel_location_id: Optional[UUID] = None` — current TravelLocation if in transit

Loader/exporter/schema support for these three fields.

### Routing

`utilities/travel_routing.py` already has `get_or_create_travel_location()` and route-cost helpers. Pop routing reuses the same path-finding: find the cheapest route from `pop.current_location` to the chosen destination, create or join a `TravelLocation`, set `skip_initial_tick=True`.

### Tick phase: `_process_pop_travel`

New Phase 2.58 (between mortal travel 2.6b and Pop agent 2.57 — needs ordering review):
- For each Pop in a TravelLocation: decrement `migration_ticks_remaining`; on arrival, move Pop to destination `pop_ids`, update `pop.current_location`, embed any mortals whose `pop_id` matches (see below).

### Band cascade migration

When a Pop decides to migrate (wanderlust or directive), check all other Pops sharing the same `band_id` at the same location. Any band member without a conflicting directive joins the migration to the same destination automatically — band travel is all-or-nothing by design. Non-band neighbors in the same Faction may also join if they have pressing wanderlust and no conflicting directive, but they are not dragged; they opt in. Cascade is one step in both cases — no transitive following.

### Mortal embedding

When a Pop begins migration, any mortal whose `band_id` matches the Pop's band (or whose `pop_id` matches the Pop) enters the same `TravelLocation` and arrives together. Mortals with their own `pending_travel_dest` are not dragged — autonomous travel takes priority.

### Files affected

- `core/universe_core.py` — Pop fields
- `core/scenario_schema.sql` — three new columns
- `utilities/scenario_loader.py` / `scenario_exporter.py`
- `utilities/travel_routing.py` — shared routing helpers (no new logic, just reuse)
- `logic/tick_logic.py` — `_process_pop_travel`, phase ordering, mortal-embedding hook
- `logic/pop_agent_logic.py` — migration decision in `compute_pop_priorities`

---

## Phase 2.61: Stockpile Ownership Transitions

**Status:** Complete (2026-06-09).

Steady-state ownership rules that fire every tick after all movement resolves:

- **Band abandons location** → band-owned stockpile converts to public; all public stockpiles at the location merge into one.
- **Faction abandons its home** → faction-owned stockpile at that home converts to public; merge as above.
- **Band is sole occupant** (non-faction home, all pops/mortals same band) → claims any unclaimed public stockpile.
- **Faction member re-enters faction home** → claims any unclaimed public stockpile (priority over band rule).

Charity-donated public stockpiles (`ResourceStockpile.is_charity = True`) are exempt from both claiming rules and the flag propagates through merges. Set by `_charity_rate()` gather splits in `pop_agent_logic.py`.

Also implemented in this block: `Faction.home_location_id`, `Faction.values` (faction-level trait dict, e.g. `{"charity": 0.3}`), `_entitled_stockpile()` helper that routes gather output to faction-owned (at home), band-owned (away), or public stockpile. Demand calculation for owned stockpiles sweeps all entitled pops across state rather than only co-located ones.

---

## Phase 2: Faction Directive Types for Pops

**Status:** `hold_position` and `supply_run` complete and playtested (2026-06-08). `patrol` implemented but not yet playtested end-to-end. `pilgrimage`, `raid`, `support_garrison` deferred.

**Goal:** A Faction can issue typed directives to Pops it owns. Each directive type drives a specific behavior pattern that overrides the Pop's default welfare-maximizing logic.

### Data model changes

`Directive` (on `Pop.active_directives`) gains:
- `interval_ticks: int = 0` — 0 = persistent; N = re-trigger every N ticks (for pilgrimage)
- `last_triggered_tick: int = 0`
- `cargo_resource_type: Optional[str] = None` — for supply_run and raid
- `cargo_quantity: float = 0.0`
- `target_pop_id: Optional[UUID] = None` — destination Pop for supply_run / raid / support
- `territory_pop_ids: list[UUID]` — for patrol: locations the Pop should range between

`Pop` gains:
- `cargo: Optional[CargoStockpile] = None` — active only while executing a `supply_run` or `raid` directive; created on directive assignment, cleared on completion

**Implementation note:** cargo was placed on `PopAgentState` (not directly on `Pop`), mirroring how `MortalInventory` lives on `MortalAgentState`. Serialized as part of the `pop_state` JSON blob. Lifecycle is always-present with empty `quantities` rather than `Optional`.

### Directive types

**`hold_position`**
Suppress wanderlust migration regardless of need pressure. Pop stays at its current location. Optional `action_type_bonus: dict[str, float]` field boosts specific actions at this location (e.g. Scholar:clergy at Ancestor Stones gets `{"enact_rituals": 1.5}`). Does not prevent being dragged by band cascade unless the Pop has a Faction directive — directive wins.

**`supply_run`** (fields: `target_pop_id`, `cargo_resource_type`, `cargo_quantity`, source is the Pop's home location)
Four-step loop:
1. At home location: `load_cargo` action — calls `load_cargo(pop.cargo, home_stockpile, ...)` to fill the Pop's `CargoStockpile` from the Faction's home `ResourceStockpile`.
2. Travel to `target_pop_id`'s current location.
3. At destination: `deposit_cargo` action — calls `unload_cargo(pop.cargo, dest_stockpile, ...)`. Pop satisfaction: `purpose` tops off.
4. Travel home. Repeat.

New actions `load_cargo` and `deposit_cargo` added to `resolve_pop_actions`. Neither fires without an active `supply_run` directive.

**`patrol`** (fields: `territory_pop_ids`)
Pop ranges between its current location and the listed territory locations, spending a set number of ticks at each performing `fortify` or `hunt`. Garrison/safety effects propagate to co-located Pops via the existing spillover system. Contested movement mechanics (blocking hostile entry) are deferred — patrol currently just performs `fortify` at each stop.

**`pilgrimage`** (fields: `target_location_id`, `interval_ticks`, `cargo_resource_type` optionally for offerings)
Faction-wide directive — issued to all Pops (and all embedded mortals) in a Faction simultaneously. When `current_tick % interval_ticks == 0`, override each Pop's migration decision to travel toward `target_location_id`. Pops that are already there perform `enact_rituals` for `duration_ticks` (a new directive field) before dispersing home. Pops that cannot reach in time still travel and contribute on arrival even if late.

**`raid`** (fields: `target_pop_id`, `cargo_resource_type`, `cargo_quantity`)
Travel to target Pop's location. Attempt to draw `cargo_quantity` from that Pop's stockpile. Whether the transfer succeeds or fails depends on whether the target Pop has a `guard` action available (deferred — Phase 4). For now, raid is an uncontested draw with a small `danger` increase at the target location and a `purpose` / `status` satisfaction boost for the raiding Pop.

**`support_garrison`** (fields: `target_pop_id`)
Co-locate with the garrison Pop; weight `build`, `collect`, and `fortify` toward satisfying the garrison Pop's `nourishment`, `shelter`, and `safety` needs via the spillover system. Does not suppress wanderlust on its own — the Pop stays because it needs to, not because it is forbidden to leave.

### Purpose need integration

Any Pop with an active directive that it is actively executing gains `purpose` satisfaction at the end of a successful action cycle. A Pop with a directive it *cannot* execute (destination unreachable, cargo type unavailable) decays purpose normally — the Demiurge or Faction should notice and reassign.

### Files affected

- `core/universe_core.py` — Directive fields, `Pop.cargo: Optional[CargoStockpile]`
- `core/scenario_schema.sql` — new directive columns, pop.cargo column (serialised JSON)
- `utilities/scenario_loader.py` / `scenario_exporter.py`
- `logic/pop_agent_logic.py` — directive-aware action scoring, new `load_cargo` / `deposit_cargo` branches
- `logic/tick_logic.py` — pilgrimage trigger in pop agent phase, raid execution, `_process_pop_travel` integration

---

## Phase 3: Location Action Bonuses

**Goal:** Specific PopLocations amplify or dampen the effectiveness of certain actions, giving location choice strategic weight beyond resource availability.

### Data model

`PopLocation` gains `action_bonuses: dict[str, float] = {}`.

A value of `2.0` doubles the action's effectiveness (need satisfaction gain, resource yield, domain expression magnitude). A value of `0.5` halves it. Absent entry = `1.0`.

### Reference values (Oros)

| Location | Bonus |
|---|---|
| Ancestor Stones | `enact_rituals: 3.0` |
| Taem's Oasis | `enact_rituals: 1.5`, `commune: 1.3` |
| Hiparun's Rift | `enact_rituals: 1.5`, `fortify: 1.2` |
| The Salt Flats | `collect: 1.3` (for salt_mineral specifically — see note) |

Note: resource-specific bonuses may eventually want a separate `resource_bonuses: dict[str, float]` field to avoid conflating action-type bonuses with resource-type bonuses. For now, `action_bonuses` is sufficient.

### Resolver integration

`resolve_pop_actions` reads `pop_loc.action_bonuses.get(action_type, 1.0)` and multiplies the action's need-satisfaction delta and any resource quantity by this factor before applying. The bonus affects output magnitude, not action selection probability — Pops at Ancestor Stones are not more likely to pick `enact_rituals`, but when they do it counts for much more.

### Files affected

- `core/universe_core.py` — PopLocation.action_bonuses
- `core/scenario_schema.sql` — new JSON column
- `utilities/scenario_loader.py` / `scenario_exporter.py`
- `logic/pop_agent_logic.py` — bonus lookup in resolve_pop_actions
- `scenarios/oros_test_sandbox.db` (and scenario builder) — set Ancestor Stones / Taem's Oasis / Hiparun's Rift values

---

## Phase 4: Mass Ritual Scaling

**Goal:** When multiple Pops perform `enact_rituals` at the same PopLocation in the same tick, the combined effect exceeds what any one Pop could achieve alone — capturing the emergent power of communal religious practice.

### Mechanic

After all per-Pop `enact_rituals` actions resolve individually, a post-pass in the pop agent phase checks each location for ≥ 2 Pops that performed the ritual this tick. A `cohort_multiplier = 1.0 + 0.15 * (n_pops - 1)` (capped at 2.5) is applied to the total domain-expression delta at that location for this tick. The multiplier is on the *combined* output, not per-Pop — so 5 Pops ritualizing together produce 1.6× the sum of their individual contributions, not 1.6× each.

This makes pilgrimage gatherings at sacred sites meaningfully more powerful than the same Pops ritualizing at home, without making any single Pop's action disproportionately strong.

Mortal `enact_rituals` actions at the same location contribute to the cohort count.

### Files affected

- `logic/pop_agent_logic.py` — post-pass cohort check, returns ritual location deltas
- `logic/tick_logic.py` — apply cohort-scaled domain expression delta

---

## Phase 5: Contested Mechanics (Deferred)

The following are acknowledged design intentions that are out of scope until a conflict / combat layer exists:

- **Raid resistance**: target Pops with `patrol` / `fortify` directives can reduce or block raid draws; outcome depends on relative martial strength (no model yet).
- **Thrall capture**: a successful raid against a weakened Pop may extract population (reduce target Pop size, increase raiding Pop size or create a new subjugated Pop). Requires a pop-splitting/merging mechanism on demand, not just via splinter divergence.
- **Path interdiction**: a Pop with a `patrol` directive guarding a TravelNetwork edge increases the danger or cost for hostile Pops passing through. Requires TravelEdge-level danger or access-control fields.
- **Charity/appeal**: a resource-poor Pop arriving at a wealthy Pop's location can appeal for resource transfer; success gated by faction relationship and target Pop's surplus. Contested only if the target Pop refuses.

---

## Notes

- **Common:producer → Common:builder** for the Ulum Highlands Pop: a one-line change to `OCCUPATION_BASELINE_WEIGHTS` and the scenario data once there is a scenario-editing pass for Oros. Not a plan item — just do it during Phase 1 or the next scenario edit pass.
- **Asha Keln's embedded mortal behavior**: once mortal embedding (Phase 1) works, Asha Keln will move with the Dunes of Tor band automatically when they patrol or raid. No special-casing needed.
- **`POP_NEED_PURPOSE` re-activation**: currently suspended along with `NEED_PURPOSE` on mortals. Re-activate when directive infrastructure exists (Phase 2) — purpose need satisfaction will then be driven by directive execution rather than by FactionAgent infrastructure that doesn't exist yet.
