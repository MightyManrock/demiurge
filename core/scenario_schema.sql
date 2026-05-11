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
    pantheon_id         TEXT NOT NULL
);

-- ─────────────────────────────────────────
-- OVERREAL — ontological layer
-- ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS powers (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS domains (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    description   TEXT NOT NULL,
    source_powers TEXT NOT NULL DEFAULT '[]',  -- JSON array of power UUIDs
    tags          TEXT NOT NULL DEFAULT '[]'   -- JSON array of strings
);

CREATE TABLE IF NOT EXISTS luminaries (
    id                   TEXT PRIMARY KEY,
    name                 TEXT NOT NULL,
    domains              TEXT NOT NULL DEFAULT '[]',  -- JSON array of domain UUIDs
    pantheon_id          TEXT,
    temperament          TEXT NOT NULL,
    -- Disposition (embedded)
    disposition_results  REAL NOT NULL DEFAULT 0.0,
    disposition_methods  REAL NOT NULL DEFAULT 0.0,
    herald_ids           TEXT NOT NULL DEFAULT '[]',  -- JSON array
    status_tags          TEXT NOT NULL DEFAULT '[]'   -- JSON array
);

-- Constraints belong to either a Luminary or a Pantheon.
CREATE TABLE IF NOT EXISTS constraints (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    description       TEXT NOT NULL,
    domain_source     TEXT,                -- UUID or NULL
    enforcement_weight REAL NOT NULL DEFAULT 0.5,
    owner_id          TEXT NOT NULL,       -- luminary or pantheon UUID
    owner_type        TEXT NOT NULL        -- 'luminary' | 'pantheon'
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
    pop_ids          TEXT NOT NULL DEFAULT '[]',     -- JSON array
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
    dominant_beliefs    TEXT NOT NULL DEFAULT '{}',  -- JSON object {tag: strength_float}
    culture_tags        TEXT NOT NULL DEFAULT '{}',  -- JSON object {tag: strength_float}
    theistic            INTEGER NOT NULL DEFAULT 1,  -- bool
    divine_awareness    REAL NOT NULL DEFAULT 0.3,
    age                 REAL NOT NULL DEFAULT 0.0,
    visibility          REAL    NOT NULL DEFAULT 0.0,
    pinned              INTEGER NOT NULL DEFAULT 0
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
    personal_tags          TEXT NOT NULL DEFAULT '[]',  -- JSON array
    culture_tags           TEXT NOT NULL DEFAULT '{}',  -- JSON object {tag: strength_float}
    alignment              REAL NOT NULL DEFAULT 0.8,
    chrono_age             REAL NOT NULL DEFAULT 0.0,
    bio_age                REAL NOT NULL DEFAULT 0.0,
    appointed_by_demiurge  TEXT,
    appointed_by_luminary  TEXT,
    home_location          TEXT NOT NULL,  -- UUID of home SignificantLocation (fixed at creation)
    current_location       TEXT NOT NULL,  -- UUID of current SignificantLocation (changes on movement)
    starting_visible       INTEGER NOT NULL DEFAULT 0,  -- bool; decays at slow rate instead of normal
    pinned                     INTEGER NOT NULL DEFAULT 0 -- bool; mortal stays at max visibility
);

-- ─────────────────────────────────────────
-- DEMIURGE
-- ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS demiurge (
    id                    TEXT PRIMARY KEY,
    name                  TEXT NOT NULL,
    liege_luminary_ids    TEXT NOT NULL DEFAULT '[]',  -- JSON array
    granted_domains       TEXT NOT NULL DEFAULT '[]',  -- JSON array
    -- FootprintProfile (embedded)
    fp_overt_miracles     REAL NOT NULL DEFAULT 0.0,
    fp_subtle_influence   REAL NOT NULL DEFAULT 0.0,
    fp_proxius_activity   REAL NOT NULL DEFAULT 0.0,
    fp_direct_creation    REAL NOT NULL DEFAULT 0.0,
    proxius_ids           TEXT NOT NULL DEFAULT '[]',  -- JSON array
    unlocked_domain_tags  TEXT NOT NULL DEFAULT '[]',  -- JSON array of domain:... strings
    unlocked_imagines     TEXT NOT NULL DEFAULT '[]',  -- JSON array of imago node_id strings
    affiliated_domains    TEXT NOT NULL DEFAULT '[]'   -- JSON array of domain:... strings
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
    starting_visible_decay_rate             REAL NOT NULL DEFAULT 0.005
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
    domain_vectors         TEXT NOT NULL DEFAULT '[]',
    domain_shift_rate      REAL NOT NULL DEFAULT 0.10,
    divine_awareness_rate  REAL NOT NULL DEFAULT 0.0,
    attention_per_tick     REAL NOT NULL DEFAULT 0.0,
    imago_node_id          TEXT,
    framing                TEXT,
    sign_description       TEXT NOT NULL DEFAULT '',
    concept                TEXT NOT NULL DEFAULT ''
);
