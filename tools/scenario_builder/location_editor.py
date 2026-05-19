"""
Location entity helpers for Phase 3 of the scenario builder.

Pure data and validation utilities — the BuilderScreen owns the actual flow
(picker → form → apply). Here we collect the four spatial entity kinds and
their per-kind field schemas in one place so the flow code stays small.

Phase 3 covers Galaxy / System / SignificantLocation / PopLocation create,
edit, and delete. Fields covered per kind:

  - Galaxy: name
  - System: name, parent (Galaxy), star_type
  - SignificantLocation: name, parent (System), location_type tag,
                         condition, age
  - PopLocation: name, parent (SignificantLocation), location_type tag,
                 distance_from_core

Out of scope for Phase 3 (deferred to a polish pass): per-world
`domain_expression`, `geo_tags`, `atmo_tags`, `LocFootprint`,
`CosmicCoordinates`. New entities start with their Pydantic defaults
for those fields; existing values survive edits untouched.
"""
from __future__ import annotations
from typing import Optional
from uuid import UUID

from core.universe_core import (
    Location, LocCondition, PopLocation, SignificantLocation,
    StarType, System,
)

# ── Entity-kind catalog ────────────────────────────────────────────────────

KIND_ITEMS: list[tuple[str, str]] = [
    ("galaxy",     "Galaxy (top-level)"),
    ("system",     "System (inside a Galaxy)"),
    ("world",      "World / SignificantLocation (inside a System)"),
    ("poploc",     "Settlement / PopLocation (inside a World)"),
]

# Parent constraints: which kind a given kind sits inside.
PARENT_KIND: dict[str, Optional[str]] = {
    "galaxy": None,
    "system": "galaxy",
    "world":  "system",
    "poploc": "world",
}

STAR_TYPE_ITEMS: list[tuple[str, str]] = [
    (st.value, st.value.replace("_", " ").title()) for st in StarType
]

CONDITION_ITEMS: list[tuple[str, str]] = [
    (c.value, c.value.title()) for c in LocCondition
]


# ── Lookup helpers ─────────────────────────────────────────────────────────

def location_kind(loc: Location) -> str:
    """Return the builder's kind tag ('galaxy'/'system'/'world'/'poploc')
    for a Location instance, falling back to the location's own
    `location_type` string when none of the structural subclasses match."""
    if isinstance(loc, System):
        return "system"
    if isinstance(loc, SignificantLocation):
        return "world"
    if isinstance(loc, PopLocation):
        return "poploc"
    if loc.location_type == "galaxy":
        return "galaxy"
    return loc.location_type


def candidates_for_kind(state, kind: str) -> list[tuple[str, str]]:
    """Return PickerModal items (id, display) for all locations matching
    a given builder kind. Used for parent pickers and edit/delete pickers."""
    items: list[tuple[str, str]] = []
    for eid, loc in state.locations.items():
        if location_kind(loc) == kind:
            items.append((eid, loc.name))
    items.sort(key=lambda kv: kv[1].lower())
    return items


def all_locations_grouped(state) -> list[tuple[str, str]]:
    """Picker items spanning every location, prefixed with their kind so
    the user can tell them apart. Sorted by (kind, name)."""
    order = {"galaxy": 0, "system": 1, "world": 2, "poploc": 3}
    rows: list[tuple[int, str, str, str]] = []
    for eid, loc in state.locations.items():
        k = location_kind(loc)
        rows.append((order.get(k, 9), k, loc.name, eid))
    rows.sort(key=lambda r: (r[0], r[2].lower()))
    return [(eid, f"[{kind}]  {name}") for _ord, kind, name, eid in rows]


# ── Field schemas for TextFormModal ────────────────────────────────────────

def text_fields_for(kind: str, loc: Optional[Location] = None) -> list[tuple[str, str, str]]:
    """Return TextFormModal field tuples (label, id, default) for the
    free-text portion of a given kind's edit form. Enum pickers (parent,
    star_type, condition) are handled separately via PickerModal.

    `loc` is the existing entity when editing, or None when creating.
    """
    name_default = loc.name if loc is not None else _default_name_for_kind(kind)
    if kind == "galaxy":
        return [("Name", "name", name_default)]
    if kind == "system":
        return [("Name", "name", name_default)]
    if kind == "world":
        age_default = f"{loc.age}" if isinstance(loc, SignificantLocation) else "0"
        return [
            ("Name",          "name",          name_default),
            ("Location type", "location_type", loc.location_type if loc else "planet"),
            ("Age",           "age",           age_default),
        ]
    if kind == "poploc":
        dist_default = f"{loc.distance_from_core}" if isinstance(loc, PopLocation) else "0"
        return [
            ("Name",                  "name",              name_default),
            ("Location type",         "location_type",     loc.location_type if loc else "pop_location"),
            ("Distance from core",    "distance_from_core", dist_default),
        ]
    raise ValueError(f"Unknown location kind: {kind}")


def _default_name_for_kind(kind: str) -> str:
    return {
        "galaxy": "New Galaxy",
        "system": "New System",
        "world":  "New World",
        "poploc": "New Settlement",
    }.get(kind, "New Location")


# ── Validation ─────────────────────────────────────────────────────────────

def validate_text_fields(kind: str, result: dict[str, str]) -> Optional[str]:
    """Return None on success or a human-readable error string on failure."""
    name = result.get("name", "").strip()
    if not name:
        return "Name cannot be empty."
    if kind == "world":
        try:
            age = float(result.get("age", "0"))
        except (TypeError, ValueError):
            return "Age must be a number."
        if age < 0:
            return "Age cannot be negative."
    if kind == "poploc":
        try:
            d = int(result.get("distance_from_core", "0"))
        except (TypeError, ValueError):
            return "Distance from core must be an integer."
        if d < 0:
            return "Distance from core cannot be negative."
    if kind in ("world", "poploc"):
        ltype = result.get("location_type", "").strip()
        if not ltype:
            return "Location type tag cannot be empty."
    return None


# ── Mutation ───────────────────────────────────────────────────────────────

def construct_location(
    kind: str,
    fields: dict[str, str],
    parent_id: Optional[UUID],
    star_type: Optional[str] = None,
    condition: Optional[str] = None,
) -> Location:
    """Instantiate a new Location subclass appropriate to `kind`."""
    name = fields["name"].strip()
    if kind == "galaxy":
        return Location(
            name=name, location_type="galaxy",
            parent_id=parent_id, visibility=1.0, pinned=True,
        )
    if kind == "system":
        return System(
            name=name, parent_id=parent_id,
            star_type=StarType(star_type) if star_type else StarType.MAIN_SEQUENCE,
            visibility=1.0, pinned=True,
        )
    if kind == "world":
        return SignificantLocation(
            name=name,
            location_type=fields["location_type"].strip() or "planet",
            parent_id=parent_id,
            condition=LocCondition(condition) if condition else LocCondition.STABLE,
            age=float(fields["age"]),
            # Earth-like defaults — authors can later strip or replace these
            # via the per-world geo/atmo editor (polish-pass backlog).
            geo_tags=["geo:terrestrial"],
            atmo_tags=["atmo:nitrogen_oxygen"],
            visibility=1.0, pinned=True,
        )
    if kind == "poploc":
        return PopLocation(
            name=name,
            location_type=fields["location_type"].strip() or "pop_location",
            parent_id=parent_id,
            distance_from_core=int(fields["distance_from_core"]),
            visibility=1.0, pinned=True,
        )
    raise ValueError(f"Unknown location kind: {kind}")


def apply_text_fields(
    loc: Location,
    kind: str,
    fields: dict[str, str],
) -> None:
    """Apply edited text fields back to an existing Location in place."""
    loc.name = fields["name"].strip()
    if kind == "world":
        loc.location_type = fields["location_type"].strip() or loc.location_type
        loc.age = float(fields["age"])
    elif kind == "poploc":
        loc.location_type = fields["location_type"].strip() or loc.location_type
        loc.distance_from_core = int(fields["distance_from_core"])


# ── Reference-checking for delete ──────────────────────────────────────────

def find_blocking_references(state, location_id: str) -> list[str]:
    """Return a list of human-readable descriptions of every entity that
    references `location_id`. The caller refuses delete when this is
    non-empty. Children of the deleted location count as references —
    callers must delete those first."""
    lid_uuid: UUID
    try:
        lid_uuid = UUID(location_id)
    except (TypeError, ValueError):
        return ["invalid location id"]
    blocks: list[str] = []

    # Children of this location.
    loc = state.locations.get(location_id)
    if loc is not None and loc.child_ids:
        for cid in loc.child_ids:
            child = state.locations.get(str(cid))
            label = child.name if child else str(cid)[:8]
            blocks.append(f"child location: {label}")

    # Universe.child_ids — galaxies are referenced by the Universe directly.
    if state.universe.child_ids and lid_uuid in state.universe.child_ids:
        blocks.append("referenced by Universe (galaxy slot)")

    # Civilizations
    for cid, civ in state.civilizations.items():
        if civ.origin_location_id == lid_uuid:
            blocks.append(f"civilization origin: {civ.name}")
        if lid_uuid in civ.core_locs:
            blocks.append(f"civilization core_loc: {civ.name}")

    # Species
    for sid, sp in state.species.items():
        if sp.origin_world_id == lid_uuid:
            blocks.append(f"species origin: {sp.name}")

    # Pops
    for pid, pop in state.pops.items():
        if pop.current_location == lid_uuid:
            blocks.append(f"pop current_location: id {pid[:8]}")

    # Notable mortals
    for mid, m in state.mortals.items():
        if m.home_location    == lid_uuid: blocks.append(f"mortal home: {m.name}")
        if m.current_location == lid_uuid: blocks.append(f"mortal current: {m.name}")

    # SignificantLocation back-references (civilization_ids etc.)
    for eid, other in state.locations.items():
        if isinstance(other, SignificantLocation):
            if lid_uuid in other.civilization_ids:
                blocks.append(f"world.civilization_ids: {other.name}")
            if lid_uuid in other.species_ids:
                blocks.append(f"world.species_ids: {other.name}")

    return blocks


def remove_from_parent(state, loc: Location) -> None:
    """Strip loc.id from its parent's child_ids list (Location parent or
    Universe for galaxies). Safe to call even when no parent link exists."""
    if loc.parent_id is None:
        if loc.id in state.universe.child_ids:
            state.universe.child_ids = [
                c for c in state.universe.child_ids if c != loc.id
            ]
        return
    parent = state.locations.get(str(loc.parent_id))
    if parent is not None and loc.id in parent.child_ids:
        parent.child_ids = [c for c in parent.child_ids if c != loc.id]
