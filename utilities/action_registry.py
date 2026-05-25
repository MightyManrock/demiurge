#!/usr/bin/env python3
"""
action_registry.py
Scenario-agnostic canonical action definitions.

Loads from (and bootstraps) core/core.db. Provides:
  - build_action_library() -> dict[str, ActionDefinition]
    Returns the full set of 35 ActionDefinition objects, with fresh UUIDs
    generated each run (same behaviour as the previous hardcoded version).

Action data (names, descriptions, costs) can be edited directly in
core/core.db. To reset to Python defaults, run:
  python rebuild_databases.py --actions
"""

from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_CORE_DB = _PROJECT_ROOT / "core" / "core.db"

# ── Seed data ─────────────────────────────────────────────────────────────────
# Each dict maps directly to an `actions` table row.
# valid_targets and tags are stored as JSON arrays of their enum .value strings.

_ACTION_SEED: list[dict] = [

    # ── Direct Creation ────────────────────────────────────────────────────────

    {
        "action_key": "seed_world",
        "short_name": "Seed Life",
        "name": "Seed World with Life",
        "category": "direct_creation",
        "description": (
            "Introduce a named species to a barren world. "
            "You define the species' basic biology and lifespan. "
            "Sapience requires a separate uplift action."
        ),
        "valid_targets": ["world"],
        "reliability": "certain",
        "fp_overt_miracles": 0.0, "fp_subtle_influence": 0.0,
        "fp_proxius_activity": 0.0, "fp_direct_creation": 0.8,
        "essence_cost": 5.0, "concealment_impact": 0.0,
        "requires_proxius": 0,
        "tags": ["creation", "world_shaping", "high_footprint", "species"],
    },
    {
        "action_key": "uplift_species",
        "short_name": "Uplift",
        "name": "Uplift Species to Sapience",
        "category": "direct_creation",
        "description": (
            "Catalyze a non-sapient species toward full sapience. "
            "A civilization will eventually emerge. High footprint."
        ),
        "valid_targets": ["species"],
        "reliability": "probable",
        "fp_overt_miracles": 0.0, "fp_subtle_influence": 0.2,
        "fp_proxius_activity": 0.0, "fp_direct_creation": 0.6,
        "essence_cost": 3.0, "concealment_impact": 0.0,
        "requires_proxius": 0,
        "tags": ["creation", "species", "high_footprint", "civilization_seed"],
    },
    {
        "action_key": "reshape_world",
        "short_name": "Reshape",
        "name": "Reshape World Geography",
        "category": "direct_creation",
        "description": (
            "Alter a world's physical features — continents, climate, "
            "atmosphere. Unmistakable as divine intervention."
        ),
        "valid_targets": ["world"],
        "reliability": "certain",
        "fp_overt_miracles": 0.0, "fp_subtle_influence": 0.0,
        "fp_proxius_activity": 0.0, "fp_direct_creation": 0.9,
        "essence_cost": 4.0, "concealment_impact": 0.0,
        "requires_proxius": 0,
        "tags": ["world_shaping", "high_footprint", "irreversible"],
    },
    {
        "action_key": "extinguish_civilization",
        "short_name": "Extinguish",
        "name": "Extinguish Civilization",
        "category": "direct_creation",
        "description": "Directly destroy a civilization. Maximum footprint.",
        "valid_targets": ["civilization"],
        "reliability": "certain",
        "fp_overt_miracles": 0.8, "fp_subtle_influence": 0.0,
        "fp_proxius_activity": 0.0, "fp_direct_creation": 1.0,
        "essence_cost": 3.0, "concealment_impact": 0.0,
        "requires_proxius": 0,
        "tags": ["destruction", "high_footprint", "irreversible", "politically_sensitive"],
    },

    # ── Overt Miracles ─────────────────────────────────────────────────────────

    {
        "action_key": "manifest_omen",
        "short_name": "Show Omen",
        "name": "Manifest Omen",
        "category": "overt_miracle",
        "description": (
            "Send a world-scale sign. Interpretable — mortals decide "
            "what it means, which affects belief drift unpredictably."
        ),
        "valid_targets": ["world"],
        "reliability": "probable",
        "fp_overt_miracles": 0.5, "fp_subtle_influence": 0.0,
        "fp_proxius_activity": 0.0, "fp_direct_creation": 0.0,
        "essence_cost": 2.0, "concealment_impact": 0.0,
        "requires_proxius": 0,
        "tags": ["belief_shift", "divine_awareness", "interpretable"],
    },
    {
        "action_key": "direct_miracle",
        "short_name": "Perform Miracle",
        "name": "Perform Direct Miracle",
        "category": "overt_miracle",
        "description": "A visibly supernatural act for a specific mortal.",
        "valid_targets": ["mortal"],
        "reliability": "certain",
        "fp_overt_miracles": 0.6, "fp_subtle_influence": 0.0,
        "fp_proxius_activity": 0.0, "fp_direct_creation": 0.0,
        "essence_cost": 1.5, "concealment_impact": 0.0,
        "requires_proxius": 0,
        "tags": ["mortal_directed", "divine_awareness", "high_footprint"],
    },
    {
        "action_key": "divine_manifestation",
        "short_name": "Manifest",
        "name": "Manifest in Divine Form",
        "category": "overt_miracle",
        "description": (
            "Appear directly. Maximally high divine_awareness impact. "
            "Luminaries who care about subtlety will be displeased."
        ),
        "valid_targets": ["civilization", "mortal"],
        "reliability": "certain",
        "fp_overt_miracles": 0.9, "fp_subtle_influence": 0.0,
        "fp_proxius_activity": 0.0, "fp_direct_creation": 0.0,
        "essence_cost": 3.0, "concealment_impact": 0.0,
        "requires_proxius": 0,
        "tags": ["divine_awareness", "high_footprint", "belief_anchor"],
    },

    # ── Subtle Influence ───────────────────────────────────────────────────────

    {
        "action_key": "whisper",
        "short_name": "Whisper",
        "name": "Whisper to Mortal",
        "category": "subtle_influence",
        "description": (
            "Plant an inspiration, warning, or idea in a mortal's mind. "
            "Deniable. Effect depends on mortal's receptivity and alignment."
        ),
        "valid_targets": ["mortal"],
        "reliability": "probable",
        "fp_overt_miracles": 0.0, "fp_subtle_influence": 0.1,
        "fp_proxius_activity": 0.0, "fp_direct_creation": 0.0,
        "essence_cost": 0.1, "concealment_impact": 0.0,
        "requires_proxius": 0,
        "tags": ["mortal_directed", "low_footprint", "deniable"],
    },
    {
        "action_key": "shape_dream",
        "short_name": "Shape Dream",
        "name": "Shape Dream",
        "category": "subtle_influence",
        "description": (
            "Deliver complex intent through a mortal's dreams. "
            "More information than a whisper; slightly more footprint."
        ),
        "valid_targets": ["mortal"],
        "reliability": "probable",
        "fp_overt_miracles": 0.0, "fp_subtle_influence": 0.15,
        "fp_proxius_activity": 0.0, "fp_direct_creation": 0.0,
        "essence_cost": 0.2, "concealment_impact": 0.0,
        "requires_proxius": 0,
        "tags": ["mortal_directed", "low_footprint", "deniable", "complex_intent"],
    },
    {
        "action_key": "nudge_probability",
        "short_name": "Nudge",
        "name": "Nudge Probability",
        "category": "subtle_influence",
        "description": (
            "Weight the odds around a coming event — a battle, discovery, "
            "natural disaster. Not guaranteed; you tilt, not control."
        ),
        "valid_targets": ["civilization", "world"],
        "reliability": "uncertain",
        "fp_overt_miracles": 0.0, "fp_subtle_influence": 0.2,
        "fp_proxius_activity": 0.0, "fp_direct_creation": 0.0,
        "essence_cost": 0.3, "concealment_impact": 0.0,
        "requires_proxius": 0,
        "tags": ["low_footprint", "deniable", "probabilistic"],
    },
    {
        "action_key": "accelerate_development",
        "short_name": "Accelerate",
        "name": "Accelerate Civilizational Development",
        "category": "subtle_influence",
        "description": (
            "Nudge a civilization toward faster growth in a domain area. "
            "Slow. Plausibly natural. Compounds over time."
        ),
        "valid_targets": ["civilization"],
        "reliability": "probable",
        "fp_overt_miracles": 0.0, "fp_subtle_influence": 0.25,
        "fp_proxius_activity": 0.0, "fp_direct_creation": 0.0,
        "essence_cost": 0.5, "concealment_impact": 0.0,
        "requires_proxius": 0,
        "tags": ["long_term", "low_footprint", "domain_shaping"],
    },

    # ── Proxius Direction ──────────────────────────────────────────────────────

    {
        "action_key": "appoint_proxius",
        "short_name": "Appoint Proxius",
        "name": "Appoint Proxius",
        "category": "proxius_direction",
        "description": (
            "Elevate a mortal to Proxius status. Generates proxius_activity "
            "footprint. Subject to Pantheon proxius_policy."
        ),
        "valid_targets": ["mortal"],
        "reliability": "certain",
        "fp_overt_miracles": 0.0, "fp_subtle_influence": 0.0,
        "fp_proxius_activity": 0.10, "fp_direct_creation": 0.0,
        "essence_cost": 1.0, "concealment_impact": 0.0,
        "requires_proxius": 0,
        "tags": ["proxii", "appointment", "politically_sensitive"],
    },
    {
        "action_key": "preach_imago",
        "short_name": "Preach Imāgō",
        "name": "Preach Imāgō",
        "category": "proxius_direction",
        "description": (
            "Direct a Proxius to preach an Imāgō framework to a target community. "
            "They interpret and execute according to their alignment and personal tags. "
            "Directing a dormant Proxius reactivates them."
        ),
        "valid_targets": ["mortal"],
        "reliability": "uncertain",
        "fp_overt_miracles": 0.0, "fp_subtle_influence": 0.0,
        "fp_proxius_activity": 0.15, "fp_direct_creation": 0.0,
        "essence_cost": 0.1, "concealment_impact": 0.0,
        "requires_proxius": 1,
        "tags": ["proxii", "indirect", "alignment_dependent", "include_dormant_proxius"],
    },
    {
        "action_key": "empower_proxius",
        "short_name": "Empower",
        "name": "Empower Proxius",
        "category": "proxius_direction",
        "description": "Grant a Proxius a temporary boost of divine capability.",
        "valid_targets": ["mortal"],
        "reliability": "certain",
        "fp_overt_miracles": 0.2, "fp_subtle_influence": 0.0,
        "fp_proxius_activity": 0.4, "fp_direct_creation": 0.0,
        "essence_cost": 1.5, "concealment_impact": 0.0,
        "requires_proxius": 1,
        "tags": ["proxii", "essence_consuming", "high_footprint"],
    },
    {
        "action_key": "dismiss_proxius",
        "short_name": "Dismiss",
        "name": "Dismiss Proxius",
        "category": "proxius_direction",
        "description": "Revoke a mortal's Proxius status.",
        "valid_targets": ["mortal"],
        "reliability": "certain",
        "fp_overt_miracles": 0.0, "fp_subtle_influence": 0.0,
        "fp_proxius_activity": 0.1, "fp_direct_creation": 0.0,
        "essence_cost": 0.0, "concealment_impact": 0.0,
        "requires_proxius": 1,
        "tags": ["proxii", "appointment", "include_dormant_proxius"],
    },
    {
        "action_key": "go_quiet_proxius",
        "short_name": "Go Quiet",
        "name": "Go Quiet",
        "category": "proxius_direction",
        "description": (
            "Signal a Proxius to suspend visible activity. "
            "They enter dormancy — appointed but generating no ongoing "
            "proxius_activity footprint. Bio-age resumes during dormancy. "
            "A future directive reactivates them."
        ),
        "valid_targets": ["mortal"],
        "reliability": "certain",
        "fp_overt_miracles": 0.0, "fp_subtle_influence": 0.0,
        "fp_proxius_activity": 0.05, "fp_direct_creation": 0.0,
        "essence_cost": 0.0, "concealment_impact": 0.0,
        "requires_proxius": 1,
        "tags": ["proxii", "appointment", "footprint_management"],
    },
    {
        "action_key": "rescind_directive",
        "short_name": "Rescind Directive",
        "name": "Rescind Directive",
        "category": "proxius_direction",
        "description": (
            "Recall an active directive from a Proxius, returning them to idle. "
            "They retain their appointment and alignment but cease pursuing their current goal."
        ),
        "valid_targets": ["mortal"],
        "reliability": "certain",
        "fp_overt_miracles": 0.0, "fp_subtle_influence": 0.0,
        "fp_proxius_activity": 0.02, "fp_direct_creation": 0.0,
        "essence_cost": 0.0, "concealment_impact": 0.0,
        "requires_proxius": 1,
        "tags": ["proxii", "appointment"],
    },

    # ── Observation ────────────────────────────────────────────────────────────

    {
        "action_key": "scry",
        "short_name": "Scry",
        "name": "Scry",
        "category": "observation",
        "description": (
            "Survey the cosmos at the chosen scope. World-scope reveals mortal detail "
            "with minimal footprint. Broader scopes (system, galaxy, universe) reveal "
            "locations, civilizations, and species at increasing footprint cost."
        ),
        "valid_targets": ["world", "system", "galaxy", "universe"],
        "reliability": "certain",
        "fp_overt_miracles": 0.0, "fp_subtle_influence": 0.01,
        "fp_proxius_activity": 0.0, "fp_direct_creation": 0.0,
        "essence_cost": 0.0, "concealment_impact": 0.0,
        "requires_proxius": 0,
        "tags": ["observation", "low_footprint", "intelligence", "can_persist"],
    },
    # read_divine_traces — parked pending Herald mechanics. When the Herald
    # entity class lands and divine-trace detection is specified, restore this
    # entry. Until then, omitting it keeps it out of the action browser.
    # {
#         "action_key": "read_divine_traces",
#         "short_name": "Read Traces",
    #     "name": "Read Divine Traces",
    #     "category": "observation",
    #     "description": (
    #         "Detect residual footprint and Herald activity on a world. "
    #         "Reveals what other divine actors have been doing."
    #     ),
    #     "valid_targets": ["world"],
    #     "reliability": "probable",
    #     "fp_overt_miracles": 0.0, "fp_subtle_influence": 0.0,
    #     "fp_proxius_activity": 0.0, "fp_direct_creation": 0.0,
    #     "essence_cost": 0.0, "concealment_impact": 0.0,
    #     "requires_proxius": 0,
    #     "tags": ["observation", "zero_footprint", "intelligence", "herald_detection"],
    # },
    {
        "action_key": "audit_proxius",
        "short_name": "Audit",
        "name": "Audit Proxius",
        "category": "observation",
        "description": (
            "Read a Proxius's actual current alignment and recent behavior. "
            "Passive — they don't know you're checking."
        ),
        "valid_targets": ["mortal"],
        "reliability": "certain",
        "fp_overt_miracles": 0.0, "fp_subtle_influence": 0.0,
        "fp_proxius_activity": 0.0, "fp_direct_creation": 0.0,
        "essence_cost": 0.0, "concealment_impact": 0.0,
        "requires_proxius": 1,
        "tags": ["observation", "zero_footprint", "proxii", "alignment_check",
                 "include_dormant_proxius"],
    },
    # ── Herald Interaction ─────────────────────────────────────────────────────

    {
        "action_key": "negotiate_herald",
        "short_name": "Negotiate",
        "name": "Negotiate with Herald",
        "category": "herald_interaction",
        "description": (
            "Attempt to find common ground with a Herald whose agenda "
            "partially overlaps yours. Outcome depends on their alignment "
            "with their patron and personal tags."
        ),
        "valid_targets": ["mortal"],
        "reliability": "uncertain",
        "fp_overt_miracles": 0.0, "fp_subtle_influence": 0.1,
        "fp_proxius_activity": 0.0, "fp_direct_creation": 0.0,
        "essence_cost": 0.0, "concealment_impact": 0.0,
        "requires_proxius": 0,
        "tags": ["herald", "political", "alignment_dependent"],
    },
    {
        "action_key": "obstruct_herald",
        "short_name": "Obstruct",
        "name": "Obstruct Herald",
        "category": "herald_interaction",
        "description": (
            "Actively work against a Herald's activities. "
            "Their patron will likely notice. High political risk."
        ),
        "valid_targets": ["mortal"],
        "reliability": "probable",
        "fp_overt_miracles": 0.2, "fp_subtle_influence": 0.3,
        "fp_proxius_activity": 0.0, "fp_direct_creation": 0.0,
        "essence_cost": 0.0, "concealment_impact": 0.0,
        "requires_proxius": 0,
        "tags": ["herald", "political", "politically_sensitive", "risky"],
    },
    {
        "action_key": "petition_luminary_herald",
        "short_name": "Petition re: Herald",
        "name": "Petition Luminary re: Herald",
        "category": "herald_interaction",
        "description": (
            "Formally request a Luminary recall or redirect their Herald. "
            "Costs political capital but is legitimate."
        ),
        "valid_targets": ["luminary"],
        "reliability": "uncertain",
        "fp_overt_miracles": 0.0, "fp_subtle_influence": 0.0,
        "fp_proxius_activity": 0.0, "fp_direct_creation": 0.0,
        "essence_cost": 0.0, "concealment_impact": 0.0,
        "requires_proxius": 0,
        "tags": ["luminary_relations", "herald", "political", "disposition_dependent"],
    },

    # ── Luminary Relations ─────────────────────────────────────────────────────

    {
        "action_key": "report_to_luminary",
        "short_name": "Report",
        "name": "Report to Luminary",
        "category": "luminary_relations",
        "description": (
            "Proactively update a liege on your universe's state. "
            "Affects results disposition. Framing matters."
        ),
        "valid_targets": ["luminary"],
        "reliability": "certain",
        "fp_overt_miracles": 0.0, "fp_subtle_influence": 0.0,
        "fp_proxius_activity": 0.0, "fp_direct_creation": 0.0,
        "essence_cost": 0.0, "concealment_impact": 0.0,
        "requires_proxius": 0,
        "tags": ["luminary_relations", "disposition_shift", "narrative"],
    },
    {
        "action_key": "petition_constraint_relaxation",
        "short_name": "Petition Relief",
        "name": "Petition for Constraint Relaxation",
        "category": "luminary_relations",
        "description": (
            "Ask a Luminary for more latitude on a specific constraint. "
            "Requires good standing. May reveal you've been straining against it."
        ),
        "valid_targets": ["luminary"],
        "reliability": "uncertain",
        "fp_overt_miracles": 0.0, "fp_subtle_influence": 0.0,
        "fp_proxius_activity": 0.0, "fp_direct_creation": 0.0,
        "essence_cost": 0.0, "concealment_impact": 0.0,
        "requires_proxius": 0,
        "tags": ["luminary_relations", "constraint", "politically_sensitive"],
    },
    {
        "action_key": "dispute_demand",
        "short_name": "Dispute Demand",
        "name": "Dispute Demand",
        "category": "luminary_relations",
        "description": (
            "Push back against a Luminary directive. "
            "Risky — degrades methods disposition, possibly results. "
            "Sometimes necessary when demands conflict."
        ),
        "valid_targets": ["luminary"],
        "reliability": "uncertain",
        "fp_overt_miracles": 0.0, "fp_subtle_influence": 0.0,
        "fp_proxius_activity": 0.0, "fp_direct_creation": 0.0,
        "essence_cost": 0.0, "concealment_impact": 0.0,
        "requires_proxius": 0,
        "tags": ["luminary_relations", "risky", "disposition_shift", "conflict"],
    },
    {
        "action_key": "ask_for_orders",
        "short_name": "Ask for Orders",
        "name": "Ask for Orders",
        "category": "luminary_relations",
        "description": (
            "Petition a Luminary for guidance. Produces a detailed report next tick: "
            "Essence expectations by domain, accumulated production vs. threshold, "
            "and a full read of their current satisfaction. Raises their attention."
        ),
        "valid_targets": ["luminary"],
        "reliability": "certain",
        "fp_overt_miracles": 0.0, "fp_subtle_influence": 0.0,
        "fp_proxius_activity": 0.0, "fp_direct_creation": 0.0,
        "essence_cost": 0.0, "concealment_impact": 0.0,
        "requires_proxius": 0,
        "tags": ["luminary_relations", "observation", "intelligence"],
    },

    # ── Underreal ──────────────────────────────────────────────────────────────

    {
        "action_key": "harvest_essence",
        "short_name": "Harvest Essence",
        "name": "Harvest Essence from Underreal",
        "category": "underreal",
        "description": (
            "Draw Divine Essence from unrealized and abandoned concepts "
            "in the Underreal. Primary Essence source. "
            "Must be concealed — Luminaries are hostile to this."
        ),
        "valid_targets": ["underreal"],
        "reliability": "probable",
        "fp_overt_miracles": 0.0, "fp_subtle_influence": 0.0,
        "fp_proxius_activity": 0.0, "fp_direct_creation": 0.0,
        "essence_cost": -0.3, "concealment_impact": 0.2,
        "requires_proxius": 0,
        "tags": ["underreal", "essence_source", "high_risk", "conceal", "can_persist"],
    },
    {
        "action_key": "salvage_concept",
        "short_name": "Salvage Concept",
        "name": "Salvage Concept from Underreal",
        "category": "underreal",
        "description": (
            "Pull a half-formed concept into your universe — "
            "a lost civilization, a forgotten technology, an unrealized species. "
            "Outcome is genuinely unpredictable."
        ),
        "valid_targets": ["underreal"],
        "reliability": "chaotic",
        "fp_overt_miracles": 0.0, "fp_subtle_influence": 0.0,
        "fp_proxius_activity": 0.0, "fp_direct_creation": 0.4,
        "essence_cost": 2.0, "concealment_impact": 0.3,
        "requires_proxius": 0,
        "tags": ["underreal", "essence_consuming", "chaotic", "creation", "conceal"],
    },
    {
        "action_key": "exile_to_underreal",
        "short_name": "Exile",
        "name": "Exile to Underreal",
        "category": "underreal",
        "description": (
            "Suppress and exile something from your universe — "
            "a civilization, concept, or entity — into the conceptual graveyard. "
            "Permanent and leaves a distinctive trace."
        ),
        "valid_targets": ["civilization", "mortal", "world"],
        "reliability": "certain",
        "fp_overt_miracles": 0.3, "fp_subtle_influence": 0.0,
        "fp_proxius_activity": 0.0, "fp_direct_creation": 0.7,
        "essence_cost": 3.0, "concealment_impact": 0.0,
        "requires_proxius": 0,
        "tags": ["underreal", "destruction", "essence_consuming", "irreversible", "high_footprint"],
    },
    {
        "action_key": "investigate_underreal",
        "short_name": "Investigate Underreal",
        "name": "Investigate Underreal",
        "category": "underreal",
        "description": (
            "Survey what failed Demiurges and abandoned concepts left behind. "
            "Intelligence on available salvage and Underreal inhabitants."
        ),
        "valid_targets": ["underreal"],
        "reliability": "probable",
        "fp_overt_miracles": 0.0, "fp_subtle_influence": 0.0,
        "fp_proxius_activity": 0.0, "fp_direct_creation": 0.0,
        "essence_cost": 0.5, "concealment_impact": 0.05,
        "requires_proxius": 0,
        "tags": ["underreal", "observation", "intelligence"],
    },
    {
        "action_key": "maintain_concealment",
        "short_name": "Conceal Harvest",
        "name": "Maintain Concealment",
        "category": "underreal",
        "description": (
            "Actively reinforce the veil over your Essence stockpile. "
            "Spend a small amount of Essence to restore concealment integrity. "
            "Diminishing returns when integrity is already high. "
            "Cannot be combined with an Essence harvest in the same tick."
        ),
        "valid_targets": ["underreal"],
        "reliability": "probable",
        "fp_overt_miracles": 0.0, "fp_subtle_influence": 0.0,
        "fp_proxius_activity": 0.0, "fp_direct_creation": 0.0,
        "essence_cost": 1.0, "concealment_impact": 0.0,
        "requires_proxius": 0,
        "tags": ["underreal", "concealment", "essence_consuming", "maintenance"],
    },
    {
        "action_key": "overthrow_luminary",
        "short_name": "Move Against",
        "name": "Move Against Luminary",
        "category": "underreal",
        "description": (
            "Spend massive accumulated Essence to challenge or sever a "
            "Luminary's hold over your universe. "
            "The ultimate high-risk action — possible victory state, "
            "possible immediate demotion to the Underreal."
        ),
        "valid_targets": ["luminary"],
        "reliability": "uncertain",
        "fp_overt_miracles": 1.0, "fp_subtle_influence": 0.0,
        "fp_proxius_activity": 0.0, "fp_direct_creation": 0.8,
        "essence_cost": 10.0, "concealment_impact": 1.0,
        "requires_proxius": 0,
        "tags": ["underreal", "essence_consuming", "victory_condition",
                 "catastrophic_risk", "irreversible"],
    },

    # ── Demiurge Self-Development ──────────────────────────────────────────────

    {
        "action_key": "explore_beliefs",
        "short_name": "Explore Beliefs",
        "name": "Explore Beliefs",
        "category": "self_refinement",
        "description": (
            "Turn your divine awareness inward and meditate on a Domain. "
            "Each tick this action runs, Revelation accumulates in that Domain's pool. "
            "Affiliated Domains accrue Revelation faster. "
            "Spend Revelation via Reveal Imāgō to internalize Imāgō nodes."
        ),
        "valid_targets": ["underreal"],
        "reliability": "certain",
        "fp_overt_miracles": 0.0, "fp_subtle_influence": 0.0,
        "fp_proxius_activity": 0.0, "fp_direct_creation": 0.0,
        "essence_cost": 0.2, "concealment_impact": 0.0,
        "requires_proxius": 0,
        "tags": ["zero_footprint", "self_refinement", "can_persist"],
    },
    {
        "action_key": "reveal_imago",
        "short_name": "Reveal Imāgō",
        "name": "Reveal Imāgō",
        "category": "self_refinement",
        "description": (
            "Spend accumulated Revelation from a Domain's pool to permanently "
            "internalize an Imāgō node from that Domain's tree. "
            "Prerequisites must be met; costs rise slightly with each Imāgō you reveal."
        ),
        "valid_targets": ["underreal"],
        "reliability": "certain",
        "fp_overt_miracles": 0.0, "fp_subtle_influence": 0.0,
        "fp_proxius_activity": 0.0, "fp_direct_creation": 0.0,
        "essence_cost": 0.0, "concealment_impact": 0.0,
        "requires_proxius": 0,
        "tags": ["zero_footprint", "self_refinement"],
    },
    {
        "action_key": "commission_inquiry",
        "short_name": "Commission Inquiry",
        "name": "Commission Inquiry",
        "category": "proxius_direction",
        "description": (
            "Direct a Proxius to conduct ongoing research into a Domain, "
            "funneling a small trickle of Revelation into your pool each tick. "
            "Mortal research is slower than direct contemplation but runs in parallel."
        ),
        "valid_targets": ["mortal"],
        "reliability": "certain",
        "fp_overt_miracles": 0.0, "fp_subtle_influence": 0.0,
        "fp_proxius_activity": 0.0, "fp_direct_creation": 0.0,
        "essence_cost": 0.0, "concealment_impact": 0.0,
        "requires_proxius": 1,
        "tags": ["proxius_direction", "research"],
    },
    {
        "action_key": "change_affiliated_domains",
        "short_name": "Change Affiliation",
        "name": "Change Affiliated Domain",
        "category": "self_refinement",
        "description": (
            "Reorient one of your affiliated domain focuses. "
            "Swap an existing affiliation for any canonical domain. "
            "Affiliated domains give future bonuses to aligned Imāgō effects "
            "and research point generation."
        ),
        "valid_targets": ["underreal"],
        "reliability": "certain",
        "fp_overt_miracles": 0.0, "fp_subtle_influence": 0.0,
        "fp_proxius_activity": 0.0, "fp_direct_creation": 0.0,
        "essence_cost": 1.5, "concealment_impact": 0.0,
        "requires_proxius": 0,
        "tags": ["zero_footprint", "self_refinement"],
    },
]


# ── Registry class ─────────────────────────────────────────────────────────────

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS actions (
    action_key          TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    short_name          TEXT NOT NULL DEFAULT '',
    category            TEXT NOT NULL,
    description         TEXT NOT NULL DEFAULT '',
    valid_targets       TEXT NOT NULL DEFAULT '[]',
    reliability         TEXT NOT NULL DEFAULT 'certain',
    fp_overt_miracles   REAL NOT NULL DEFAULT 0.0,
    fp_subtle_influence REAL NOT NULL DEFAULT 0.0,
    fp_proxius_activity REAL NOT NULL DEFAULT 0.0,
    fp_direct_creation  REAL NOT NULL DEFAULT 0.0,
    essence_cost        REAL NOT NULL DEFAULT 0.0,
    concealment_impact  REAL NOT NULL DEFAULT 0.0,
    requires_proxius    INTEGER NOT NULL DEFAULT 0,
    tags                TEXT NOT NULL DEFAULT '[]'
);
"""


class ActionRegistry:
    def __init__(self, db_path: Path = DEFAULT_CORE_DB) -> None:
        self._db_path = db_path
        self._data: dict[str, dict] = {}
        self._bootstrap()

    def _bootstrap(self) -> None:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            try:
                existing = {r["action_key"] for r in conn.execute("SELECT action_key FROM actions")}
            except sqlite3.OperationalError:
                existing = set()

            seed_keys = {row["action_key"] for row in _ACTION_SEED}
            needs_write = not existing.issuperset(seed_keys)

            if needs_write:
                conn.execute(_CREATE_TABLE)
                for row in _ACTION_SEED:
                    if row["action_key"] not in existing:
                        conn.execute(
                            "INSERT INTO actions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (
                                row["action_key"],
                                row["name"],
                                row.get("short_name", ""),
                                row["category"],
                                row["description"],
                                json.dumps(row["valid_targets"]),
                                row["reliability"],
                                row["fp_overt_miracles"],
                                row["fp_subtle_influence"],
                                row["fp_proxius_activity"],
                                row["fp_direct_creation"],
                                row["essence_cost"],
                                row["concealment_impact"],
                                row["requires_proxius"],
                                json.dumps(row["tags"]),
                            ),
                        )
                conn.commit()

            rows = conn.execute(
                "SELECT * FROM actions ORDER BY rowid"
            ).fetchall()
            self._data = {r["action_key"]: dict(r) for r in rows}
        finally:
            conn.close()

    def build_action_library(self) -> dict:
        from core.action_core import (
            ActionDefinition, ActionCategory, ActionReliability,
            TargetType, FootprintCost,
        )
        result: dict[str, ActionDefinition] = {}
        for key, row in self._data.items():
            result[key] = ActionDefinition(
                name=row["name"],
                short_name=row["short_name"] if "short_name" in row.keys() else "",
                category=ActionCategory(row["category"]),
                description=row["description"],
                valid_targets=[TargetType(t) for t in json.loads(row["valid_targets"])],
                reliability=ActionReliability(row["reliability"]),
                footprint_cost=FootprintCost(
                    overt_miracles=row["fp_overt_miracles"],
                    subtle_influence=row["fp_subtle_influence"],
                    proxius_activity=row["fp_proxius_activity"],
                    direct_creation=row["fp_direct_creation"],
                ),
                essence_cost=row["essence_cost"],
                concealment_impact=row["concealment_impact"],
                requires_proxius=bool(row["requires_proxius"]),
                tags=json.loads(row["tags"]),
            )
        return result


# ── Singleton ──────────────────────────────────────────────────────────────────

_registry: Optional[ActionRegistry] = None


def get_registry(db_path: Path = DEFAULT_CORE_DB) -> ActionRegistry:
    global _registry
    if _registry is None:
        _registry = ActionRegistry(db_path)
    return _registry


def reinstate(db_path: Path = DEFAULT_CORE_DB) -> ActionRegistry:
    """Drop and re-seed the actions table from Python defaults."""
    global _registry
    _registry = None
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DROP TABLE IF EXISTS actions")
        conn.commit()
    finally:
        conn.close()
    return get_registry(db_path)
