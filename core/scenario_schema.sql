-- scenario_schema.sql
-- Shared DDL for all Demiurge scenarios.
-- Applied first whenever a scenario .db is opened or created.
-- All UUID columns are stored as TEXT.
-- List/dict fields are stored as JSON text.
-- Embedded value-objects (Disposition, CivilizationHealth, etc.)
-- are flattened as prefixed columns in the parent table.

PRAGMA foreign_keys = ON;

-- ─────────────────────────────────────────
-- SCENARIO METADATA
-- One row per file.
-- ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS scenario_meta (
    name                TEXT NOT NULL,
    description         TEXT NOT NULL DEFAULT '',
    universe_id         TEXT NOT NULL DEFAULT '',   -- UUID of the Universe object
    universe_name       TEXT NOT NULL,
    universe_save_name  TEXT NOT NULL,
    universe_description TEXT NOT NULL DEFAULT '',
    current_age         REAL NOT NULL DEFAULT 0.0,
    tick_number         INTEGER NOT NULL DEFAULT 0,
    demiurge_id         TEXT NOT NULL,
    pantheon_id         TEXT NOT NULL,
    luminary_production_accum TEXT NOT NULL DEFAULT '{}',  -- JSON {luminary_id: float} weighted-production accumulator
    domain_essence_claimed  TEXT NOT NULL DEFAULT '{}',  -- JSON {domain_tag: float} cumulative Demiurge claim
    universe_domain_expression TEXT NOT NULL DEFAULT '{}', -- JSON {domain_tag: float} per-domain baseline (0.1 default if absent)
    starting_pinned_ids        TEXT NOT NULL DEFAULT '[]',  -- JSON [str(UUID), ...] entities pinned at scenario start; unpinned at tick 10
    last_tick_essence_by_domain TEXT NOT NULL DEFAULT '{}', -- JSON {domain_tag: float} Demiurge Essence claimed last tick, for Status display
    category_cooldowns          TEXT NOT NULL DEFAULT '{}', -- JSON CategoryCooldowns model (counters: dict[ActionCategory, int])
    pause_config                TEXT NOT NULL DEFAULT '{}'  -- JSON PauseConfig model (overrides: dict[PauseEventType, bool])
);

-- ─────────────────────────────────────────
-- OVERREAL — ontological layer
-- ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS luminaries (
    id                   TEXT PRIMARY KEY,
    name                 TEXT NOT NULL,
    domains              TEXT NOT NULL DEFAULT '[]',  -- JSON array of domain UUIDs
    pantheon_id          TEXT,
    -- Disposition (embedded)
    disposition_results  REAL NOT NULL DEFAULT 0.0,
    disposition_methods  REAL NOT NULL DEFAULT 0.0,
    herald_ids           TEXT NOT NULL DEFAULT '[]',  -- JSON array
    status_tags          TEXT NOT NULL DEFAULT '[]',  -- JSON array
    essence_received_log         TEXT NOT NULL DEFAULT '[]',  -- JSON array of floats (last 2 evaluation totals)
    essence_expectation_raised   REAL NOT NULL DEFAULT 0.0,   -- additive bonus above base threshold
    consecutive_essence_shortfalls INTEGER NOT NULL DEFAULT 0,  -- back-to-back shortfall counter
    last_evaluation              TEXT,           -- JSON of LuminaryEvaluation.model_dump() or NULL
    previous_evaluation          TEXT,           -- JSON; one cycle behind last_evaluation
    last_evaluation_tick         INTEGER,        -- tick the last evaluation was recorded
    last_orders_response         TEXT,           -- narrative text from most recent Ask for Orders
    last_orders_response_tick    INTEGER         -- tick the orders response was recorded
);

-- Constraints belong to either a Luminary or a Pantheon.
CREATE TABLE IF NOT EXISTS constraints (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    description       TEXT NOT NULL,
    domain_tag        TEXT,                -- canonical 'domain:...' tag, or NULL
    enforcement_weight REAL NOT NULL DEFAULT 0.5,
    owner_id          TEXT NOT NULL,       -- luminary or pantheon UUID
    owner_type        TEXT NOT NULL,       -- 'luminary' | 'pantheon'
    constraint_type   TEXT NOT NULL DEFAULT 'narrative',  -- 'narrative' | 'footprint' | 'results'
    footprint_tolerances TEXT,             -- JSON blob e.g. '{"overt_miracles": 0.2}'; NULL for non-footprint
    min_results       REAL               -- floor for disposition.results; NULL for non-results
);

CREATE TABLE IF NOT EXISTS pantheons (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    luminary_ids TEXT NOT NULL DEFAULT '[]'  -- JSON array
);

-- ─────────────────────────────────────────
-- THE REAL — universe layer
-- ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS universe_rules (
    -- One row per scenario.
    fp_tolerance_overt_miracles    REAL NOT NULL DEFAULT 0.3,
    fp_tolerance_subtle_influence  REAL NOT NULL DEFAULT 0.8,
    fp_tolerance_proxius_activity  REAL NOT NULL DEFAULT 0.6,
    fp_tolerance_direct_creation   REAL NOT NULL DEFAULT 0.2,
    proxii_max_per_world           INTEGER,       -- NULL = no cap
    proxii_tolerance_for_excess    REAL NOT NULL DEFAULT 0.3,
    mortals_can_perceive_divinity  INTEGER NOT NULL DEFAULT 1,  -- bool
    active_shaping_expected        INTEGER NOT NULL DEFAULT 1,  -- bool
    special_flags                  TEXT NOT NULL DEFAULT '[]',  -- JSON array
    notes                          TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS travel_networks (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    member_ids TEXT NOT NULL DEFAULT '[]'
);

-- Unified locations table: galaxies, systems, planets/planes, pop locations.
-- The 'subclass' column controls which Python class is instantiated on load:
--   'location'             → Location (base; used for galaxies and freeform locations)
--   'system'               → System
--   'significant_location' → SignificantLocation (planets, planes — collects footprint/domain data)
--   'pop_location'         → PopLocation (cities, towns, stations — houses Pops)
CREATE TABLE IF NOT EXISTS locations (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    location_type TEXT NOT NULL DEFAULT 'location',  -- free-form label: "galaxy", "planet", "city", etc.
    subclass      TEXT NOT NULL DEFAULT 'location',  -- Python class discriminator
    parent_id     TEXT,                              -- NULL for galaxies (universe not in table)
    child_ids     TEXT NOT NULL DEFAULT '[]',        -- JSON array of child location UUIDs
    traits        TEXT NOT NULL DEFAULT '[]',        -- JSON array of trait strings
    condition     TEXT NOT NULL DEFAULT 'stable',
    -- System-specific (populated for subclass='system')
    coordinates_x REAL NOT NULL DEFAULT 0.0,
    coordinates_y REAL NOT NULL DEFAULT 0.0,
    coordinates_z REAL NOT NULL DEFAULT 0.0,
    star_type     TEXT NOT NULL DEFAULT 'main_sequence',
    -- SignificantLocation-specific (populated for subclass='significant_location')
    domain_expression TEXT NOT NULL DEFAULT '{}',   -- JSON object {tag: strength_float}
    lf_overt_miracles   REAL NOT NULL DEFAULT 0.0,  -- local_footprint fields (flattened)
    lf_subtle_influence REAL NOT NULL DEFAULT 0.0,
    lf_proxius_activity REAL NOT NULL DEFAULT 0.0,
    lf_direct_creation  REAL NOT NULL DEFAULT 0.0,
    civilization_ids TEXT NOT NULL DEFAULT '[]',    -- JSON array
    species_ids      TEXT NOT NULL DEFAULT '[]',    -- JSON array
    proxius_ids      TEXT NOT NULL DEFAULT '[]',    -- JSON array
    herald_ids_loc   TEXT NOT NULL DEFAULT '[]',    -- JSON array (disambiguated from luminary herald_ids)
    geo_tags         TEXT NOT NULL DEFAULT '[]',    -- JSON array
    atmo_tags        TEXT NOT NULL DEFAULT '[]',    -- JSON array
    age              REAL NOT NULL DEFAULT 0.0,
    -- PopLocation-specific (populated for subclass='pop_location')
    pop_ids             TEXT    NOT NULL DEFAULT '[]',  -- JSON array
    distance_from_core  INTEGER NOT NULL DEFAULT 0,     -- 0 = core surface; >0 adds to scry/travel distance
    -- TravelLocation-specific (subclass='travel_location')
    legs                  TEXT    NOT NULL DEFAULT '{}',   -- JSON object (ordered dict)
    travel_current_wp     TEXT    NOT NULL DEFAULT '',     -- UUID str of current waypoint
    travel_ticks_rem      INTEGER NOT NULL DEFAULT 0,
    travel_occupants      TEXT    NOT NULL DEFAULT '[]',   -- JSON array of UUID strs
    -- PopLocation addition
    travel_network_ids    TEXT    NOT NULL DEFAULT '[]',   -- JSON array of TravelNetwork UUIDs
    -- Window visibility
    visibility  REAL    NOT NULL DEFAULT 0.0,   -- 0.0–1.0; how clearly Demiurge perceives this
    pinned      INTEGER NOT NULL DEFAULT 0       -- bool; 1 = never decays (all starting locations)
);

CREATE TABLE IF NOT EXISTS species (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    description      TEXT NOT NULL DEFAULT '',
    origin_world_id  TEXT,
    sapient          INTEGER NOT NULL DEFAULT 1,   -- bool
    transplanted     INTEGER NOT NULL DEFAULT 0,   -- bool
    lifespan_min     REAL NOT NULL DEFAULT 100.0,
    lifespan_max     REAL NOT NULL DEFAULT 200.0,
    domain_tags      TEXT NOT NULL DEFAULT '[]',   -- JSON array of domain:... strings (innate affinity)
    bio_tags         TEXT NOT NULL DEFAULT '[]',   -- JSON array
    condition        TEXT NOT NULL DEFAULT 'stable',
    visibility       REAL    NOT NULL DEFAULT 0.0,
    pinned           INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS civilizations (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    description         TEXT NOT NULL DEFAULT '',
    origin_location_id  TEXT,                       -- UUID of home SignificantLocation (nullable)
    scale               TEXT NOT NULL DEFAULT 'tribal',
    -- CivilizationHealth (embedded)
    health_stability    REAL NOT NULL DEFAULT 0.5,
    health_prosperity   REAL NOT NULL DEFAULT 0.5,
    health_cohesion     REAL NOT NULL DEFAULT 0.5,
    primary_species_id  TEXT,
    dominant_beliefs    TEXT NOT NULL DEFAULT '{}',  -- JSON object {tag: strength_float}; derived aggregate of Pops
    established_beliefs TEXT NOT NULL DEFAULT '{}',  -- JSON object {tag: strength_float}; institutional/official profile
    pop_ids             TEXT NOT NULL DEFAULT '[]',  -- JSON array of Pop UUIDs
    culture_tags             TEXT NOT NULL DEFAULT '{}',  -- JSON object {tag: strength_float}; derived aggregate of Pops
    established_culture_tags TEXT NOT NULL DEFAULT '{}',  -- JSON object {tag: strength_float}; institutional/official profile
    theistic            INTEGER NOT NULL DEFAULT 1,  -- bool
    divine_awareness    REAL NOT NULL DEFAULT 0.3,
    core_locs           TEXT    NOT NULL DEFAULT '[]',  -- JSON array of SignificantLocation UUIDs
    age                 REAL NOT NULL DEFAULT 0.0,
    visibility          REAL    NOT NULL DEFAULT 0.0,
    pinned              INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS pops (
    id               TEXT PRIMARY KEY,
    name             TEXT,                           -- optional authored identity; UI falls back to stratum when NULL
    demiurge_authored INTEGER NOT NULL DEFAULT 0,    -- 1 if the Demiurge created this pop via Proxius preaching
    civilization_id  TEXT,                           -- UUID of owning Civilization (nullable)
    species_id       TEXT,                           -- UUID of Species (nullable)
    social_class     TEXT,                           -- SocialClass value; NULL for non-sapient Pops
    wild_stratum     TEXT,                           -- WildStratum value; NULL for sapient Pops
    current_location TEXT NOT NULL,                  -- UUID of PopLocation
    size_fractional  REAL NOT NULL DEFAULT 6.0,      -- internal log size; int(size_fractional) = displayed magnitude
    dominant_beliefs TEXT NOT NULL DEFAULT '{}',     -- JSON object {tag: strength_float}
    culture_tags     TEXT NOT NULL DEFAULT '{}',     -- JSON object {tag: strength_float}
    rider_traits     TEXT NOT NULL DEFAULT '{}',     -- JSON object {tag: strength_float}; traits from Imago preaching
    notable_mortal_ids TEXT NOT NULL DEFAULT '[]',   -- JSON array of NotableMortal UUIDs
    parent_pop_id    TEXT,                           -- UUID of parent Pop if this is a splinter; NULL otherwise
    child_pop_ids    TEXT NOT NULL DEFAULT '[]',     -- JSON array of splinter Pop UUIDs
    visibility       REAL NOT NULL DEFAULT 0.0,
    pinned           INTEGER NOT NULL DEFAULT 0,
    preaching_imago_id            TEXT DEFAULT NULL,     -- imago_node_id if this Pop is an active preaching goal target
    preaching_goal_cooldown_until INTEGER NOT NULL DEFAULT 0  -- tick before which Pop cannot be a source target
);

CREATE TABLE IF NOT EXISTS mortals (
    id                     TEXT PRIMARY KEY,
    name                   TEXT NOT NULL,
    description            TEXT NOT NULL DEFAULT '',
    civilization_id        TEXT,
    role                   TEXT NOT NULL DEFAULT 'other',
    status                 TEXT NOT NULL DEFAULT 'active',
    species_id             TEXT,
    prominence_roles       TEXT NOT NULL DEFAULT '[]',  -- JSON array of MortalProminence values
    prominence             REAL NOT NULL DEFAULT 0.5,
    visibility             REAL NOT NULL DEFAULT 0.0,
    belief_tags            TEXT NOT NULL DEFAULT '{}',  -- JSON object {tag: strength_float}
    personal_tags          TEXT NOT NULL DEFAULT '[]',  -- JSON array (descriptive traits)
    status_tags            TEXT NOT NULL DEFAULT '[]',  -- JSON array (situational state: exiled, imprisoned, …)
    culture_tags           TEXT NOT NULL DEFAULT '{}',  -- JSON object {tag: strength_float}
    alignment              REAL NOT NULL DEFAULT 0.8,
    chrono_age             REAL NOT NULL DEFAULT 0.0,
    bio_age                REAL NOT NULL DEFAULT 0.0,
    appointed_by_demiurge  TEXT,
    appointed_by_luminary  TEXT,
    home_location          TEXT NOT NULL,  -- UUID of home SignificantLocation (fixed at creation)
    current_location       TEXT NOT NULL,  -- UUID of current SignificantLocation (changes on movement)
    pinned                 INTEGER NOT NULL DEFAULT 0,  -- bool; mortal stays at max visibility
    active_goal_json       TEXT DEFAULT NULL,           -- JSON of ProxiusGoal, or NULL
    pop_id                 TEXT DEFAULT NULL,           -- UUID of origin Pop; cleared on age-out
    proxius_appointed_tick INTEGER DEFAULT NULL,        -- tick of first Proxius elevation (wall-clock)
    herald_appointed_tick  INTEGER DEFAULT NULL,        -- tick of first Herald elevation (wall-clock)
    origin_pop_subsumed    INTEGER NOT NULL DEFAULT 0,  -- bool; True when mortal's origin Pop was absorbed into the goal Pop
    last_audit_text        TEXT,                         -- narrative from last Audit Proxius
    last_audit_tick        INTEGER,                      -- tick the last audit was recorded
    travel_intent_json     TEXT DEFAULT NULL             -- JSON of TravelIntent, or NULL
);

-- ─────────────────────────────────────────
-- DEMIURGE
-- ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS demiurge (
    id                    TEXT PRIMARY KEY,
    name                  TEXT NOT NULL,
    liege_luminary_ids    TEXT NOT NULL DEFAULT '[]',  -- JSON array
    -- FootprintProfile (embedded)
    fp_overt_miracles     REAL NOT NULL DEFAULT 0.0,
    fp_subtle_influence   REAL NOT NULL DEFAULT 0.0,
    fp_proxius_activity   REAL NOT NULL DEFAULT 0.0,
    fp_direct_creation    REAL NOT NULL DEFAULT 0.0,
    proxius_ids           TEXT NOT NULL DEFAULT '[]',  -- JSON array
    unlocked_domain_tags  TEXT NOT NULL DEFAULT '[]',  -- JSON array of domain:... strings
    unlocked_imagines         TEXT NOT NULL DEFAULT '[]',  -- JSON array of imago node_id strings
    affiliated_domains        TEXT NOT NULL DEFAULT '[]',  -- JSON array of domain:... strings
    max_affiliated_domains    INTEGER NOT NULL DEFAULT 3,  -- cap on len(affiliated_domains); Stronghold-raisable
    tracked_essence_domains   TEXT NOT NULL DEFAULT '[]',  -- JSON array of domain:... strings
    revelation_pools          TEXT NOT NULL DEFAULT '{}',  -- JSON object {domain_tag: float}
    revealed_imagines         INTEGER NOT NULL DEFAULT 0,  -- count of Imagines unlocked via Reveal Imago
    lifetime_revelation       REAL NOT NULL DEFAULT 0.0    -- running total of all Revelation ever gained
);

CREATE TABLE IF NOT EXISTS essence (
    -- One row per scenario.
    actual                  REAL NOT NULL DEFAULT 0.0,
    apparent                REAL NOT NULL DEFAULT 0.0,
    concealment_integrity   REAL NOT NULL DEFAULT 1.0
);

-- ─────────────────────────────────────────
-- SIMULATION CONFIG
-- ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS tick_config (
    -- One row per scenario.
    tick_duration               REAL NOT NULL DEFAULT 1.0,
    footprint_decay_rate        REAL NOT NULL DEFAULT 0.05,
    -- FootprintProfile decay multipliers (embedded)
    decay_mult_overt_miracles   REAL NOT NULL DEFAULT 1.0,
    decay_mult_subtle_influence REAL NOT NULL DEFAULT 1.8,
    decay_mult_proxius_activity REAL NOT NULL DEFAULT 0.8,
    decay_mult_direct_creation  REAL NOT NULL DEFAULT 0.4,
    concealment_decay_rate      REAL NOT NULL DEFAULT 0.02,
    civ_momentum_rate           REAL NOT NULL DEFAULT 0.02,
    civ_noise_factor            REAL NOT NULL DEFAULT 0.01,
    alignment_drift_rate               REAL NOT NULL DEFAULT 0.01,
    attention_decay_rate               REAL NOT NULL DEFAULT 0.03,
    evaluation_interval                REAL NOT NULL DEFAULT 10.0,
    mortal_visibility_decay_rate            REAL NOT NULL DEFAULT 0.03,
    proxius_passive_footprint_rate          REAL NOT NULL DEFAULT 0.03,
    location_visibility_decay_rate          REAL NOT NULL DEFAULT 0.01,
    civ_visibility_decay_rate               REAL NOT NULL DEFAULT 0.01,
    species_visibility_decay_rate           REAL NOT NULL DEFAULT 0.01,
    starting_visible_decay_rate             REAL NOT NULL DEFAULT 0.005,  -- kept for backward compat with old saves; no longer read
    pop_conformity_base                     REAL NOT NULL DEFAULT 0.005,  -- base rate at which Pops are nudged toward established_beliefs
    pop_visibility_drift_rate               REAL NOT NULL DEFAULT 0.02,   -- rate at which Pop visibility converges toward civ+world floor
    established_drift_base                  REAL NOT NULL DEFAULT 0.01,   -- base rate at which established_beliefs drifts toward dominant_beliefs
    -- Cross-Pop contact
    pop_contact_base_rate       REAL NOT NULL DEFAULT 0.005,
    cross_civ_contact_factor    REAL NOT NULL DEFAULT 0.15,
    cross_civ_scale_penalty     REAL NOT NULL DEFAULT 0.08,
    cross_species_contact_factor REAL NOT NULL DEFAULT 0.50,
    cross_stratum_contact_factor REAL NOT NULL DEFAULT 0.70,
    values_stubbornness_factor  REAL NOT NULL DEFAULT 0.35,
    peripheral_pop_belief_weight  REAL NOT NULL DEFAULT 0.25,
    peripheral_pop_culture_weight REAL NOT NULL DEFAULT 0.25,
    civ_culture_drift_rate      REAL NOT NULL DEFAULT 0.03   -- unused; established_culture_tags drift reuses established_drift_base
);

-- Per-civilization natural momentum at scenario start.
CREATE TABLE IF NOT EXISTS civ_momentum (
    civilization_id  TEXT PRIMARY KEY,
    stability_delta  REAL NOT NULL DEFAULT 0.0,
    prosperity_delta REAL NOT NULL DEFAULT 0.0,
    cohesion_delta   REAL NOT NULL DEFAULT 0.0
);

-- DomainVector belief-drift entries for civ_momentum.
CREATE TABLE IF NOT EXISTS civ_momentum_belief_drift (
    civilization_id TEXT NOT NULL,
    domain_tag      TEXT NOT NULL,
    direction       REAL NOT NULL,
    notes           TEXT NOT NULL DEFAULT ''
);

-- Per-Luminary attention and evaluation timer at scenario start.
CREATE TABLE IF NOT EXISTS luminary_state (
    luminary_id              TEXT PRIMARY KEY,
    attention                REAL NOT NULL DEFAULT 0.2,
    ticks_since_evaluation   REAL NOT NULL DEFAULT 0.0
);

-- Ongoing (persistent) actions active at save time.
CREATE TABLE IF NOT EXISTS ongoing_actions (
    category_key           TEXT PRIMARY KEY,
    action_key             TEXT NOT NULL,
    action_definition_id   TEXT NOT NULL,
    target_type            TEXT NOT NULL,
    target_id              TEXT,
    proxius_id             TEXT,
    intent_type            TEXT,    -- Python class name of the intent, or NULL
    intent_data            TEXT,    -- JSON of intent fields, or NULL
    ticks_active           INTEGER NOT NULL DEFAULT 0,
    executed_ticks         INTEGER NOT NULL DEFAULT 0,
    successful_ticks       INTEGER NOT NULL DEFAULT 0,
    started_at_tick        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS active_events (
    id                     TEXT PRIMARY KEY,
    event_type             TEXT NOT NULL,
    curve                  TEXT NOT NULL,
    source_action_id       TEXT,
    created_at_tick        INTEGER NOT NULL DEFAULT 0,
    duration               INTEGER NOT NULL,
    base_strength          REAL NOT NULL DEFAULT 1.0,
    peak_offset            INTEGER NOT NULL DEFAULT 0,
    decay_rate             REAL NOT NULL DEFAULT 0.6,
    target_world_id        TEXT,
    target_civilization_id TEXT,
    target_mortal_id       TEXT,
    target_loc_id          TEXT,
    domain_vectors         TEXT NOT NULL DEFAULT '[]',
    culture_vectors        TEXT NOT NULL DEFAULT '[]',
    domain_shift_rate      REAL NOT NULL DEFAULT 0.10,
    divine_awareness_rate  REAL NOT NULL DEFAULT 0.0,
    attention_per_tick     REAL NOT NULL DEFAULT 0.0,
    imago_node_id          TEXT,
    framing                TEXT,
    sign_description       TEXT NOT NULL DEFAULT '',
    concept                TEXT NOT NULL DEFAULT ''
);
