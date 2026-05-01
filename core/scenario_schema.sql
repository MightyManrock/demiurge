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
    universe_name       TEXT NOT NULL,
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
    herald_id            TEXT,
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

CREATE TABLE IF NOT EXISTS galaxies (
    id                   TEXT PRIMARY KEY,
    name                 TEXT NOT NULL,
    x                    REAL NOT NULL DEFAULT 0.0,
    y                    REAL NOT NULL DEFAULT 0.0,
    z                    REAL NOT NULL DEFAULT 0.0,
    dominant_domain_tags TEXT NOT NULL DEFAULT '[]'  -- JSON array
);

CREATE TABLE IF NOT EXISTS systems (
    id        TEXT PRIMARY KEY,
    name      TEXT NOT NULL,
    galaxy_id TEXT NOT NULL,
    star_type TEXT NOT NULL DEFAULT 'main_sequence',
    x         REAL NOT NULL DEFAULT 0.0,
    y         REAL NOT NULL DEFAULT 0.0,
    z         REAL NOT NULL DEFAULT 0.0
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
    bio_tags         TEXT NOT NULL DEFAULT '[]',   -- JSON array
    cultural_tags    TEXT NOT NULL DEFAULT '{}',   -- JSON object {tag: strength_float}
    condition        TEXT NOT NULL DEFAULT 'stable'
);

CREATE TABLE IF NOT EXISTS worlds (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    system_id         TEXT NOT NULL,
    condition         TEXT NOT NULL DEFAULT 'stable',
    domain_expression TEXT NOT NULL DEFAULT '{}',  -- JSON object {tag: strength_float}
    geo_tags          TEXT NOT NULL DEFAULT '[]',  -- JSON array
    atmo_tags         TEXT NOT NULL DEFAULT '[]',  -- JSON array
    species_ids       TEXT NOT NULL DEFAULT '[]',  -- JSON array
    age               REAL NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS civilizations (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    world_id         TEXT NOT NULL,
    scale            TEXT NOT NULL DEFAULT 'tribal',
    -- CivilizationHealth (embedded)
    health_stability  REAL NOT NULL DEFAULT 0.5,
    health_prosperity REAL NOT NULL DEFAULT 0.5,
    health_cohesion   REAL NOT NULL DEFAULT 0.5,
    primary_species_id TEXT,
    dominant_beliefs  TEXT NOT NULL DEFAULT '{}',  -- JSON object {tag: strength_float}
    culture_tags      TEXT NOT NULL DEFAULT '{}',  -- JSON object {tag: strength_float}
    theistic          INTEGER NOT NULL DEFAULT 1,  -- bool
    divine_awareness  REAL NOT NULL DEFAULT 0.3,
    age               REAL NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS mortals (
    id                     TEXT PRIMARY KEY,
    name                   TEXT NOT NULL,
    world_id               TEXT NOT NULL,
    civilization_id        TEXT,
    role                   TEXT NOT NULL DEFAULT 'other',
    status                 TEXT NOT NULL DEFAULT 'active',
    species_id             TEXT,
    prominence_roles       TEXT NOT NULL DEFAULT '[]',  -- JSON array of MortalProminence values
    prominence             REAL NOT NULL DEFAULT 0.5,
    visibility             REAL NOT NULL DEFAULT 0.0,
    personal_tags          TEXT NOT NULL DEFAULT '[]',  -- JSON array
    culture_tags           TEXT NOT NULL DEFAULT '{}',  -- JSON object {tag: strength_float}
    alignment              REAL NOT NULL DEFAULT 0.8,
    chrono_age             REAL NOT NULL DEFAULT 0.0,
    bio_age                REAL NOT NULL DEFAULT 0.0,
    appointed_by_demiurge  TEXT,
    appointed_by_luminary  TEXT,
    home_location          TEXT,  -- UUID of home world / location (fixed at creation)
    current_location       TEXT   -- UUID of current world / location (changes on movement)
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
    unlocked_imagines     TEXT NOT NULL DEFAULT '[]'   -- JSON array of imago node_id strings
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
    mortal_visibility_decay_rate       REAL NOT NULL DEFAULT 0.03,
    proxius_passive_footprint_rate     REAL NOT NULL DEFAULT 0.03
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
