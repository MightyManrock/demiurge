"""
Civilization / Species / Pop schemas and operations for Phase 4 of the
scenario builder. Same shape as `location_editor.py`: pure data + validation
+ mutation helpers; the BuilderScreen owns the actual flow.

Fields covered per kind (the lighter end of each entity's surface area —
domain affinity tags, belief dicts, culture tags, and back-reference lists
are deferred to a polish pass):

  - Species:       name, lifespan_min, lifespan_max, sapient, condition,
                   origin_world (picker)
  - Civilization:  name, scale, origin_location (picker),
                   primary_species (picker, optional), stability,
                   prosperity, cohesion, age
  - Pop:           civilization (picker), species (picker),
                   current_location (picker → PopLocation),
                   social_class OR wild_stratum (picker depending on
                   species sapience), size_fractional
"""
from __future__ import annotations
from typing import Optional
from uuid import UUID

from core.universe_core import (
    Civilization, CivilizationHealth, CivilizationScale,
    PopLocation, Pop, SignificantLocation, SocialClass,
    Species, SpeciesCondition, WildStratum,
)


# ── Enum picker item tables ────────────────────────────────────────────────

CIV_SCALE_ITEMS: list[tuple[str, str]] = [
    (s.value, s.value.replace("_", " ").title()) for s in CivilizationScale
]
SPECIES_CONDITION_ITEMS: list[tuple[str, str]] = [
    (c.value, c.value.title()) for c in SpeciesCondition
]
SOCIAL_CLASS_ITEMS: list[tuple[str, str]] = [
    (c.value, c.value.title()) for c in SocialClass
]
WILD_STRATUM_ITEMS: list[tuple[str, str]] = [
    (w.value, w.value.title()) for w in WildStratum
]
YESNO_ITEMS: list[tuple[str, str]] = [("yes", "Yes"), ("no", "No")]


# ── Picker label builders ──────────────────────────────────────────────────

def civ_picker_items(state) -> list[tuple[str, str]]:
    rows = []
    for cid, civ in state.civilizations.items():
        origin = state.locations.get(str(civ.origin_location_id)) if civ.origin_location_id else None
        origin_name = origin.name if origin else "?"
        rows.append((cid, f"{civ.name}  [{civ.scale.value}]  @ {origin_name}"))
    rows.sort(key=lambda kv: kv[1].lower())
    return rows


def species_picker_items(state, allow_none: bool = False) -> list[tuple[str, str]]:
    rows = [(sid, sp.name) for sid, sp in state.species.items()]
    rows.sort(key=lambda kv: kv[1].lower())
    if allow_none:
        rows.insert(0, ("__none__", "(none)"))
    return rows


def pop_picker_items(state) -> list[tuple[str, str]]:
    from ui.display import _pop_identity_label
    rows = []
    for pid, pop in state.pops.items():
        loc = state.locations.get(str(pop.current_location)) if pop.current_location else None
        loc_name = loc.name if loc else "?"
        civ = state.civilizations.get(str(pop.civilization_id)) if pop.civilization_id else None
        civ_tag = f"  · {civ.name}" if civ else ""
        rows.append((pid, f"{_pop_identity_label(state, pop)} @ {loc_name}{civ_tag}"))
    rows.sort(key=lambda kv: kv[1].lower())
    return rows


def world_picker_items(state, allow_none: bool = False) -> list[tuple[str, str]]:
    rows = [
        (eid, loc.name) for eid, loc in state.locations.items()
        if isinstance(loc, SignificantLocation)
    ]
    rows.sort(key=lambda kv: kv[1].lower())
    if allow_none:
        rows.insert(0, ("__none__", "(none)"))
    return rows


def poploc_picker_items(state) -> list[tuple[str, str]]:
    rows = [
        (eid, loc.name) for eid, loc in state.locations.items()
        if isinstance(loc, PopLocation)
    ]
    rows.sort(key=lambda kv: kv[1].lower())
    return rows


# ── Field schemas for TextFormModal ────────────────────────────────────────

def species_text_fields(sp: Optional[Species] = None) -> list[tuple[str, str, str]]:
    return [
        ("Name",         "name",         sp.name if sp else "New Species"),
        ("Description",  "description",  sp.description if sp else ""),
        ("Lifespan min", "lifespan_min", f"{sp.lifespan_min}" if sp else "40"),
        ("Lifespan max", "lifespan_max", f"{sp.lifespan_max}" if sp else "80"),
    ]


def civ_text_fields(civ: Optional[Civilization] = None) -> list[tuple[str, str, str]]:
    h = civ.health if civ else CivilizationHealth()
    return [
        ("Name",             "name",             civ.name if civ else "New Civilization"),
        ("Description",      "description",      civ.description if civ else ""),
        ("Age",              "age",              f"{civ.age.elapsed_years()}" if civ else "0"),
        ("Divine awareness (0.0–1.0)", "divine_awareness",
         f"{civ.divine_awareness}" if civ else "0.3"),
        ("Stability",        "stability",        f"{h.stability}"),
        ("Wealth",           "wealth",           f"{h.wealth}"),
        ("Cohesion",         "cohesion",         f"{h.cohesion}"),
    ]


def pop_text_fields(pop: Optional[Pop] = None) -> list[tuple[str, str, str]]:
    return [
        ("Name (optional — overrides the stratum label when set)",
         "name", pop.name or "" if pop else ""),
        ("Size (log-magnitude, e.g. 6 ≈ 1M)", "size_fractional",
         f"{pop.size_fractional}" if pop else "6.0"),
    ]


# ── Validation ─────────────────────────────────────────────────────────────

def validate_species_fields(result: dict[str, str]) -> Optional[str]:
    if not result.get("name", "").strip():
        return "Name cannot be empty."
    try:
        lmin = float(result["lifespan_min"])
        lmax = float(result["lifespan_max"])
    except (KeyError, TypeError, ValueError):
        return "Lifespans must be numbers."
    if lmin < 0 or lmax < 0:
        return "Lifespans cannot be negative."
    if lmax < lmin:
        return "Lifespan max must be ≥ lifespan min."
    return None


def validate_civ_fields(result: dict[str, str]) -> Optional[str]:
    if not result.get("name", "").strip():
        return "Name cannot be empty."
    try:
        age = float(result["age"])
        s = float(result["stability"])
        p = float(result["wealth"])
        c = float(result["cohesion"])
        da = float(result["divine_awareness"])
    except (KeyError, TypeError, ValueError):
        return "Age, health, and divine awareness must be numbers."
    if age < 0:
        return "Age cannot be negative."
    for label, val in (
        ("Stability", s), ("Prosperity", p), ("Cohesion", c),
        ("Divine awareness", da),
    ):
        if not (0.0 <= val <= 1.0):
            return f"{label} must be between 0.0 and 1.0."
    return None


def validate_pop_fields(result: dict[str, str]) -> Optional[str]:
    try:
        sz = float(result["size_fractional"])
    except (KeyError, TypeError, ValueError):
        return "Size must be a number (log-magnitude; 6 ≈ 1 million)."
    if sz < 0:
        return "Size cannot be negative."
    return None


# ── Constructors ───────────────────────────────────────────────────────────

def construct_species(
    fields: dict[str, str],
    origin_world_id: Optional[UUID],
    sapient: bool,
    condition: SpeciesCondition,
) -> Species:
    return Species(
        name=fields["name"].strip(),
        lifespan_min=float(fields["lifespan_min"]),
        lifespan_max=float(fields["lifespan_max"]),
        origin_world_id=origin_world_id,
        sapient=sapient,
        condition=condition,
        visibility=1.0, pinned=True,
    )


def construct_civilization(
    fields: dict[str, str],
    scale: CivilizationScale,
    origin_location_id: UUID,
    primary_species_id: Optional[UUID],
) -> Civilization:
    return Civilization(
        name=fields["name"].strip(),
        scale=scale,
        origin_location_id=origin_location_id,
        primary_species_id=primary_species_id,
        core_locs=[origin_location_id],
        health=CivilizationHealth(
            stability =float(fields["stability"]),
            wealth=float(fields["wealth"]),
            cohesion  =float(fields["cohesion"]),
        ),
        age=float(fields["age"]),
        visibility=1.0, pinned=True,
    )


def construct_pop(
    fields: dict[str, str],
    civilization_id: Optional[UUID],
    species_id: Optional[UUID],
    current_location: UUID,
    social_class: Optional[SocialClass],
    wild_stratum: Optional[WildStratum],
    seed_beliefs: Optional[dict[str, float]] = None,
    seed_culture: Optional[dict[str, float]] = None,
) -> Pop:
    raw_name = fields.get("name", "").strip()
    return Pop(
        name=raw_name or None,
        civilization_id=civilization_id,
        species_id=species_id,
        current_location=current_location,
        social_class=social_class,
        wild_stratum=wild_stratum,
        size_fractional=float(fields["size_fractional"]),
        dominant_beliefs=dict(seed_beliefs) if seed_beliefs else {},
        culture_tags=dict(seed_culture) if seed_culture else {},
        visibility=1.0, pinned=True,
    )


# ── Mutation (apply edits to existing entities) ────────────────────────────

def apply_species_fields(sp: Species, fields: dict[str, str]) -> None:
    sp.name = fields["name"].strip()
    sp.description = fields["description"]
    sp.lifespan_min = float(fields["lifespan_min"])
    sp.lifespan_max = float(fields["lifespan_max"])


def apply_civ_fields(civ: Civilization, fields: dict[str, str]) -> None:
    civ.name = fields["name"].strip()
    civ.description = fields["description"]
    from core.universe_core import EntityAge
    new_elapsed = int(float(fields["age"]))
    civ.age = EntityAge.from_full_year(
        civ.age.formation_full_year() + new_elapsed,
        formation_date=civ.age.formation_date,
    )
    civ.divine_awareness = float(fields["divine_awareness"])
    civ.health.stability  = float(fields["stability"])
    civ.health.wealth = float(fields["wealth"])
    civ.health.cohesion   = float(fields["cohesion"])


def apply_pop_fields(pop: Pop, fields: dict[str, str]) -> None:
    raw_name = fields.get("name", "").strip()
    pop.name = raw_name or None
    pop.size_fractional = float(fields["size_fractional"])


# ── Reference-checking for delete ──────────────────────────────────────────

def find_civ_references(state, civ_id: str) -> list[str]:
    try:
        cid = UUID(civ_id)
    except (TypeError, ValueError):
        return ["invalid civilization id"]
    blocks: list[str] = []
    for pid, pop in state.pops.items():
        if pop.civilization_id == cid:
            sp = state.species.get(str(pop.species_id)) if pop.species_id else None
            sp_name = sp.name if sp else "?"
            blocks.append(f"pop: {sp_name} ({pid[:8]})")
    for mid, m in state.mortals.items():
        if m.civilization_id == cid:
            blocks.append(f"mortal: {m.name}")
    for eid, loc in state.locations.items():
        if isinstance(loc, SignificantLocation) and cid in loc.civilization_ids:
            blocks.append(f"world.civilization_ids: {loc.name}")
    return blocks


def find_species_references(state, species_id: str) -> list[str]:
    try:
        sid = UUID(species_id)
    except (TypeError, ValueError):
        return ["invalid species id"]
    blocks: list[str] = []
    for pid, pop in state.pops.items():
        if pop.species_id == sid:
            blocks.append(f"pop: id {pid[:8]}")
    for mid, m in state.mortals.items():
        if m.species_id == sid:
            blocks.append(f"mortal: {m.name}")
    for cid, civ in state.civilizations.items():
        if civ.primary_species_id == sid:
            blocks.append(f"civilization primary_species: {civ.name}")
    for eid, loc in state.locations.items():
        if isinstance(loc, SignificantLocation) and sid in loc.species_ids:
            blocks.append(f"world.species_ids: {loc.name}")
    return blocks


def find_pop_references(state, pop_id: str) -> list[str]:
    try:
        pid_uuid = UUID(pop_id)
    except (TypeError, ValueError):
        return ["invalid pop id"]
    blocks: list[str] = []
    for mid, m in state.mortals.items():
        if m.pop_id == pid_uuid:
            blocks.append(f"mortal: {m.name}")
    for other_pid, pop in state.pops.items():
        if other_pid == pop_id:
            continue
        if pop.parent_pop_id == pid_uuid:
            blocks.append(f"child pop: id {other_pid[:8]}")
    return blocks


# ── Back-reference cleanup (called by delete after ref check passes) ───────

def unlink_civ_back_refs(state, civ: Civilization) -> None:
    """Strip civ.id from any SignificantLocation.civilization_ids list.
    Pop / Mortal references are blocked by the ref check, not cleaned here."""
    for eid, loc in state.locations.items():
        if isinstance(loc, SignificantLocation) and civ.id in loc.civilization_ids:
            loc.civilization_ids = [c for c in loc.civilization_ids if c != civ.id]


def unlink_species_back_refs(state, sp: Species) -> None:
    for eid, loc in state.locations.items():
        if isinstance(loc, SignificantLocation) and sp.id in loc.species_ids:
            loc.species_ids = [s for s in loc.species_ids if s != sp.id]


def unlink_pop_back_refs(state, pop: Pop) -> None:
    """Strip the Pop's id from its civilization and PopLocation back-refs."""
    if pop.civilization_id:
        civ = state.civilizations.get(str(pop.civilization_id))
        if civ is not None and pop.id in civ.pop_ids:
            civ.pop_ids = [p for p in civ.pop_ids if p != pop.id]
    if pop.current_location:
        loc = state.locations.get(str(pop.current_location))
        if isinstance(loc, PopLocation) and pop.id in loc.pop_ids:
            loc.pop_ids = [p for p in loc.pop_ids if p != pop.id]
