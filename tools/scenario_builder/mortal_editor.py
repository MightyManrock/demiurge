"""
NotableMortal schemas and operations for Phase 5 of the scenario builder.

Fields covered: name, species (picker), civilization (optional), pop
(optional), home_location, current_location, role, status, prominence,
alignment, chrono_age, bio_age.

Deferred to polish: description, belief_tags, personal_tags, status_tags,
culture_tags, prominence_roles, active_goal, appointed_by_demiurge /
appointed_by_luminary (these are implied by role and updated automatically
when the mortal's role flips).
"""
from __future__ import annotations
from typing import Optional
from uuid import UUID

from core.universe_core import (
    MortalProminence, MortalRole, MortalStatus, NotableMortal,
    SignificantLocation,
)


# ── Enum picker item tables ────────────────────────────────────────────────

ROLE_ITEMS: list[tuple[str, str]] = [
    (MortalRole.OTHER.value,   "Other (no divine appointment)"),
    (MortalRole.PROXIUS.value, "Proxius (Demiurge's agent)"),
    (MortalRole.HERALD.value,  "Herald (Luminary's agent)"),
]

# Authoring scenarios only — DECEASED/ASCENDED are end-states, not start states.
STATUS_ITEMS: list[tuple[str, str]] = [
    (MortalStatus.ACTIVE.value,  "Active"),
    (MortalStatus.DORMANT.value, "Dormant"),
]

PROMINENCE_ROLE_ITEMS: list[tuple[str, str]] = [
    (p.value, p.value.title()) for p in MortalProminence
]


# ── Picker label builders ──────────────────────────────────────────────────

def mortal_picker_items(state) -> list[tuple[str, str]]:
    rows = []
    for mid, m in state.mortals.items():
        sp = state.species.get(str(m.species_id)) if m.species_id else None
        loc = state.locations.get(str(m.current_location)) if m.current_location else None
        sp_name = sp.name if sp else "?"
        loc_name = loc.name if loc else "?"
        rows.append((mid, f"{m.name}  [{m.role.value}]  ({sp_name}) @ {loc_name}"))
    rows.sort(key=lambda kv: kv[1].lower())
    return rows


# ── Text field schema ──────────────────────────────────────────────────────

def text_fields(m: Optional[NotableMortal] = None) -> list[tuple[str, str, str]]:
    return [
        ("Name",       "name",       m.name if m else "New Mortal"),
        ("Prominence (0.0–1.0)", "prominence", f"{m.prominence}" if m else "0.5"),
        ("Alignment (0.0–1.0)",  "alignment",  f"{m.alignment}"  if m else "0.8"),
        ("Chrono age", "chrono_age", f"{m.chrono_age}" if m else "30"),
        ("Bio age",    "bio_age",    f"{m.bio_age}"    if m else "30"),
    ]


# ── Validation ─────────────────────────────────────────────────────────────

def validate_fields(result: dict[str, str]) -> Optional[str]:
    if not result.get("name", "").strip():
        return "Name cannot be empty."
    try:
        prom = float(result["prominence"])
        align = float(result["alignment"])
        chrono = float(result["chrono_age"])
        bio = float(result["bio_age"])
    except (KeyError, TypeError, ValueError):
        return "Prominence, alignment, and ages must be numbers."
    if not (0.0 <= prom <= 1.0):
        return "Prominence must be between 0.0 and 1.0."
    if not (0.0 <= align <= 1.0):
        return "Alignment must be between 0.0 and 1.0."
    if chrono < 0 or bio < 0:
        return "Ages cannot be negative."
    return None


# ── Construction & mutation ────────────────────────────────────────────────

def construct_mortal(
    fields: dict[str, str],
    species_id: UUID,
    home_location: UUID,
    current_location: UUID,
    role: MortalRole,
    status: MortalStatus,
    civilization_id: Optional[UUID],
    pop_id: Optional[UUID],
    seed_beliefs: Optional[dict[str, float]] = None,
    seed_culture: Optional[dict[str, float]] = None,
) -> NotableMortal:
    return NotableMortal(
        name=fields["name"].strip(),
        species_id=species_id,
        civilization_id=civilization_id,
        pop_id=pop_id,
        home_location=home_location,
        current_location=current_location,
        role=role,
        status=status,
        prominence=float(fields["prominence"]),
        alignment=float(fields["alignment"]),
        chrono_age=float(fields["chrono_age"]),
        bio_age=float(fields["bio_age"]),
        belief_tags=dict(seed_beliefs) if seed_beliefs else {},
        culture_tags=dict(seed_culture) if seed_culture else {},
        visibility=1.0, pinned=True,
    )


def apply_fields(m: NotableMortal, fields: dict[str, str]) -> None:
    m.name = fields["name"].strip()
    m.prominence = float(fields["prominence"])
    m.alignment  = float(fields["alignment"])
    m.chrono_age = float(fields["chrono_age"])
    m.bio_age    = float(fields["bio_age"])


# ── Back-reference housekeeping ────────────────────────────────────────────

def link_back_refs(state, m: NotableMortal) -> None:
    """Register a freshly-created mortal in all the back-ref lists that
    point at it: civ.notable_mortal_ids, pop.notable_mortal_ids, and the
    role-specific lists (Demiurge.proxius_ids, Luminary.herald_ids, world's
    proxius_ids/herald_ids)."""
    if m.civilization_id:
        civ = state.civilizations.get(str(m.civilization_id))
        if civ is not None and m.id not in civ.notable_mortal_ids:
            civ.notable_mortal_ids.append(m.id)
    if m.pop_id:
        pop = state.pops.get(str(m.pop_id))
        if pop is not None and m.id not in pop.notable_mortal_ids:
            pop.notable_mortal_ids.append(m.id)
    if m.role == MortalRole.PROXIUS:
        m.appointed_by_demiurge = state.demiurge.id
        if m.id not in state.demiurge.proxius_ids:
            state.demiurge.proxius_ids.append(m.id)
        loc = state.locations.get(str(m.current_location))
        if isinstance(loc, SignificantLocation) and m.id not in loc.proxius_ids:
            loc.proxius_ids.append(m.id)
    # Heralds are appointed by a specific Luminary; without UI to pick which,
    # we leave appointed_by_luminary unset. The world-level back-ref still
    # makes sense (this world is hosting a Herald).
    if m.role == MortalRole.HERALD:
        loc = state.locations.get(str(m.current_location))
        if isinstance(loc, SignificantLocation) and m.id not in loc.herald_ids:
            loc.herald_ids.append(m.id)


def unlink_back_refs(state, m: NotableMortal) -> None:
    """Strip mortal id from every back-ref list. Always cleanable —
    NotableMortals do not block delete."""
    if m.civilization_id:
        civ = state.civilizations.get(str(m.civilization_id))
        if civ is not None:
            civ.notable_mortal_ids = [x for x in civ.notable_mortal_ids if x != m.id]
    if m.pop_id:
        pop = state.pops.get(str(m.pop_id))
        if pop is not None:
            pop.notable_mortal_ids = [x for x in pop.notable_mortal_ids if x != m.id]
    state.demiurge.proxius_ids = [x for x in state.demiurge.proxius_ids if x != m.id]
    for lum in state.luminaries.values():
        lum.herald_ids = [x for x in lum.herald_ids if x != m.id]
    for loc in state.locations.values():
        if isinstance(loc, SignificantLocation):
            if m.id in loc.proxius_ids:
                loc.proxius_ids = [x for x in loc.proxius_ids if x != m.id]
            if m.id in loc.herald_ids:
                loc.herald_ids = [x for x in loc.herald_ids if x != m.id]
