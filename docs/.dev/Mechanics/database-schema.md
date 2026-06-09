# Database Schema Reference

Two SQLite databases. All UUID columns are `TEXT`. List/dict fields are JSON text. Embedded value-objects are flattened as prefixed columns in the parent table.

**sqlite3 CLI is not available in this environment.** All DB inspection must go through Python:

```python
import sqlite3, json
conn = sqlite3.connect("scenarios/oros_test_sandbox.db")
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT id, name, band_id FROM pops").fetchall()
for r in rows:
    print(r["id"], r["name"], r["band_id"])
```

---

## `core/core.db` — scenario-agnostic registries

Auto-bootstrapped on first load. Never written during a simulation run.

| Table | Key columns | Purpose |
|---|---|---|
| `actions` | `action_key` PK, `name`, `category`, `reliability`, `fp_*` costs, `essence_cost`, `tags` JSON | Action library |
| `domain_registry` | `tag` PK, `display_name`, `partner_tag`, `authoritative/mercurial/wrathful_score`, `color`, `symbols` JSON, `speed` | All canonical `domain:…` tags |
| `domain_similarity` | `(tag_a, tag_b)` PK, `similarity` | Pairwise domain similarity |
| `culture_registry` | `tag` PK, `display_name`, `sort_order` | All canonical `culture:…` tags |
| `culture_synergy` | `(tag_a, tag_b)` PK, `synergy` | Pairwise culture synergy |
| `culture_domain_affinity` | `(culture_tag, domain_tag)` PK, `modifier` | Culture → domain influence modifier |
| `imago_node` | `node_id` PK, `tree`, `tier`, `name`, `mechanics_json`, `min_prereqs` | 112 Imago nodes across 16 trees |
| `imago_prerequisite` | `(node_id, required_node_id)` PK | Imago unlock graph edges |

---

## `scenarios/*.db` — scenario state

Schema defined in `core/scenario_schema.sql`. Loader: `utilities/scenario_loader.py`. Exporter: `utilities/scenario_exporter.py`.

### `scenario_meta` (one row)
Universe identity, age columns (`age_billions/millions/thousands/years/month/day`), `tick_number`, `demiurge_id`, `pantheon_id`, various JSON accumulator dicts (`luminary_production_accum`, `domain_essence_claimed`, etc.).

### `locations` (unified table — discriminated by `subclass`)

| `subclass` value | Python class | Extra columns used |
|---|---|---|
| `location` | `Location` | base columns only |
| `system` | `System` | `coordinates_x/y/z`, `star_type` |
| `significant_location` | `SignificantLocation` | `domain_expression`, `lf_*` footprint, `civilization_ids`, `species_ids`, `geo_tags`, `atmo_tags` |
| `pop_location` | `PopLocation` | `pop_ids`, `collectible_resources`, `stockpiles`, `wealth`, `danger`, `commerce_quality`, `travel_network_ids` |
| `travel_location` | `TravelLocation` | `legs`, `travel_current_wp`, `travel_ticks_rem`, `travel_occupants`, `travel_pop_ids` |

Key columns on all rows: `id`, `name`, `description`, `location_type` (free-form label), `subclass` (discriminator), `parent_id`, `child_ids` JSON, `visibility`, `pinned`.

**`stockpiles`** — JSON array of `ResourceStockpile` objects: `{"quantities": {resource_type: float}, "owner_faction_id": str|null, "owner_band_id": str|null, "is_charity": bool}`.

**`collectible_resources`** — JSON array of `CollectibleResource` objects: `{"resource_type": str, "current_yield": float, "max_yield": float, "yield_renew_rate": float, "action_types": [...]}`.

### `pops`

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | UUID |
| `name` | TEXT | optional authored name; UI falls back to stratum |
| `current_location` | TEXT | UUID of PopLocation (or TravelLocation while migrating) |
| `size_fractional` | REAL | internal log size; `int(size_fractional)` = displayed magnitude |
| `social_class` | TEXT | `SocialStratum` value (`COMMON`, `WARRIOR`, `ARTISAN`, `SCHOLAR`, `WILD`, `FERAL`, …) |
| `occupation` | TEXT | `Occupation` enum value |
| `civilization_id` | TEXT | UUID |
| `species_id` | TEXT | UUID |
| `faction_ids` | TEXT | JSON array of Faction UUIDs |
| `band_id` | TEXT | UUID of Band; NULL if not in a band |
| `active_directives` | TEXT | JSON array of `Directive` objects |
| `pop_state` | TEXT | JSON of `PopAgentState` (needs, cargo, KB, supply_run state, etc.) |
| `linked_pop_ids` | TEXT | JSON object `{pop_id_str: base_link_factor}` |
| `migration_ticks_remaining` | INTEGER | display cache; authoritative countdown is in TravelLocation |
| `migration_destination_id` | TEXT | UUID of destination PopLocation |
| `migration_travel_location_id` | TEXT | UUID of current TravelLocation |
| `asset_crew_for` | TEXT | asset_type string if this is a vessel crew pop |
| `dominant_beliefs`, `culture_tags`, `rider_traits` | TEXT | JSON objects `{tag: float}` |

### `factions`

| Column | Notes |
|---|---|
| `id` | UUID PK |
| `name`, `description` | |
| `civilization_id` | UUID |
| `member_pop_ids` | JSON array of Pop UUIDs |
| `member_mortal_ids` | JSON array of NotableMortal UUIDs |
| `mortal_leader_ids` | JSON array |
| `active_directives` | JSON array of `Directive` objects |
| `home_location_id` | UUID of canonical home PopLocation; governs stockpile ownership routing |
| `values` | JSON object of faction trait floats, e.g. `{"charity": 0.3}` |
| `visibility`, `pinned` | |

### `mortals`

| Column | Notes |
|---|---|
| `id` | UUID PK |
| `name`, `description` | |
| `current_location` | UUID of current location |
| `home_location` | UUID of home SignificantLocation (fixed at creation) |
| `faction_ids`, `led_faction_ids` | JSON arrays |
| `band_id` | UUID of Band; NULL if not in a band |
| `pop_id` | UUID of origin Pop |
| `pop_milieu` | UUID of Pop the mortal is currently embedded among |
| `mortal_state` | JSON of `MortalAgentState` (needs, desires, assets, KB, cooldowns, cargo, etc.) |
| `knowledge_base` | JSON of `KnowledgeBase` (legacy column; superseded by `mortal_state.knowledge_base`) |
| `assets` | JSON array (legacy column; superseded by `mortal_state.assets`) |
| `travel_intent_json` | JSON of `TravelIntent` |
| `fatigue` | REAL |
| `occupation` | `Occupation` enum value |
| `belief_tags`, `culture_tags`, `skill_tags` | JSON objects `{tag: float}` |
| `alignment`, `prominence`, `chrono_age`, `bio_age` | REAL |

### `bands`

| Column | Notes |
|---|---|
| `id` | UUID PK |
| `label` | display name |
| `pop_ids` | JSON array of Pop UUIDs |
| `mortal_ids` | JSON array of NotableMortal UUIDs |

### Other tables

| Table | Purpose |
|---|---|
| `luminaries` | Luminary identity, disposition (flattened), evaluation history |
| `constraints` | Narrative/footprint/results constraints; `owner_id` → luminary or pantheon |
| `pantheons` | Pantheon identity + `luminary_ids` |
| `universe_rules` | Footprint tolerances, caps, flags (one row) |
| `species` | Species identity, `life_basis`, `solvent`, bio/domain tags |
| `civilizations` | Civ identity, health (flattened), beliefs/culture (JSON), `pop_ids` |
| `demiurge` | Demiurge identity, footprint profile, proxii/imago/domain lists, revelation |
| `essence` | One row: `actual`, `suspicious`, `concealment_integrity` |
| `tick_config` | All tick-rate parameters (one row) |
| `travel_networks` | `TravelNetwork` objects with `edges` and `conditions` JSON |
| `ongoing_actions` | Actions persisted across ticks |
| `pending_resume` | Repeating actions displaced by a one-shot override |
| `active_events` | Multi-tick `Event` objects |
| `civ_momentum` | Per-civ natural momentum deltas at scenario start |
| `civ_momentum_belief_drift` | Per-civ belief drift vectors |
| `luminary_state` | Per-luminary attention and evaluation timer at scenario start |
