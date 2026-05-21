"""
JSON-patch injector for scenario .db files. Invoked as:

  python main.py --inject <scenario_ref> <patch_ref>

where `<scenario_ref>` is a path or a bare name (`.db` extension optional;
bare names resolve to `scenarios/<name>.db`) and `<patch_ref>` is either
a path to a JSON file or a bare JSON string starting with `{` or `[`.

If the scenario .db does not yet exist, it is created from a fresh skeleton
(matching what the builder's New-Scenario wizard produces) before operations
apply. The patch can include any operations to populate it from scratch.

Patch format:
{
  "scenario_name": "Optional human-facing name (for scenario_meta.name)",
  "description":   "Optional scenario_meta.description",
  "operations": [
    {"op": "<name>", ...op-specific fields...},
    ...
  ]
}

`scenario_name` and `description` are written through to scenario_meta when
provided; absent fields leave the existing meta untouched.

See `tools/scenario_builder/injector.py:OPERATIONS_DOC` (and CLAUDE.md) for
the full operation vocabulary.
"""
from __future__ import annotations
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from core.universe_core import (
    Civilization, CivilizationHealth, CivilizationScale,
    LocCondition, Location, MortalProminence, MortalRole, MortalStatus,
    NotableMortal, Pop, PopLocation, SignificantLocation, SocialClass,
    Species, SpeciesCondition, StarType, System, Universe, UniverseRules,
    WildStratum,
)
from core.onto_core import Constraint, NarrativeConstraint, Disposition, FootprintProfile, Luminary, Pantheon, Demiurge
from core.action_core import EssenceStockpile
from logic.tick_logic import SimulationState
from ui.constants import _SCENARIOS_DIR
from utilities.scenario_loader import load_scenario, validate_luminary_affinities
from utilities.scenario_exporter import export_scenario
from utilities.scenario_migrator import migrate_scenario

from .flag_check import find_broken_refs, render_flag_report
from .meta_io import peek_meta
from .skeleton import build_skeleton_state


# ── Result types ───────────────────────────────────────────────────────────

@dataclass
class InjectorResult:
    """Per-op result. `ok=False` means the op was skipped or failed; the
    `error` field carries the message."""
    op: str
    ok: bool
    note: str
    error: Optional[str] = None


@dataclass
class InjectorRun:
    scenario_path: Path
    created: bool                # True if the .db was newly created
    results: list[InjectorResult] = field(default_factory=list)
    saved: bool = False
    broken_refs: dict[str, list[str]] = field(default_factory=dict)
    summary_lines: list[str] = field(default_factory=list)


# ── Reference resolution ───────────────────────────────────────────────────

class _NameResolver:
    """Resolves human-readable entity names to UUIDs. Raises on ambiguity.
    Falls back to UUID-string match when names don't match (so callers can
    pass either)."""

    def __init__(self, state: SimulationState):
        self._state = state

    # Each lookup returns (entity, eid_str) or (None, None) when not found.

    def _by_name_or_id(self, table: dict, name: str):
        if not name:
            return None, None
        # UUID match first (cheap)
        if name in table:
            return table[name], name
        matches = [
            (entity, eid) for eid, entity in table.items()
            if getattr(entity, "name", None) == name
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError(
                f"name {name!r} is ambiguous — {len(matches)} matches"
            )
        return None, None

    def civ(self, name: str):       return self._by_name_or_id(self._state.civilizations, name)
    def species(self, name: str):   return self._by_name_or_id(self._state.species, name)
    def mortal(self, name: str):    return self._by_name_or_id(self._state.mortals, name)
    def luminary(self, name: str):  return self._by_name_or_id(self._state.luminaries, name)
    def location(self, name: str):  return self._by_name_or_id(self._state.locations, name)

    def pop(self, name: str):
        """Pops have an optional `name`. Falls back to a compound key
        `{stratum}@{location_name}` if no name match."""
        if not name:
            return None, None
        if name in self._state.pops:
            return self._state.pops[name], name
        # By name
        named = [
            (p, pid) for pid, p in self._state.pops.items()
            if getattr(p, "name", None) == name
        ]
        if len(named) == 1:
            return named[0]
        if len(named) > 1:
            raise ValueError(f"pop name {name!r} matches {len(named)} pops")
        # Compound {stratum}@{location} (case-insensitive)
        if "@" in name:
            stratum_part, loc_part = name.split("@", 1)
            stratum_part = stratum_part.strip().lower()
            loc_part = loc_part.strip()
            for pid, p in self._state.pops.items():
                loc = self._state.locations.get(str(p.current_location)) if p.current_location else None
                if (
                    p.stratum.lower() == stratum_part
                    and loc is not None
                    and loc.name == loc_part
                ):
                    return p, pid
        return None, None


# ── Kind dispatch tables ───────────────────────────────────────────────────

# Kinds the injector knows about. Maps to the relevant resolver method.
_KIND_RESOLVERS = {
    "civ":       "civ",
    "species":   "species",
    "mortal":    "mortal",
    "luminary":  "luminary",
    "pop":       "pop",
    "galaxy":    "location",
    "system":    "location",
    "world":     "location",
    "poploc":    "location",
    "location":  "location",  # alias — accept any subtype
    "universe":  "_universe",
    "demiurge":  "_demiurge",
    "pantheon":  "_pantheon",
}


def _get_kind_entity(state: SimulationState, kind: str, name: str):
    """Resolve a (kind, name) to (entity, eid_str). Singletons ignore name."""
    if kind == "universe":  return state.universe, str(state.universe.id)
    if kind == "demiurge":  return state.demiurge, str(state.demiurge.id)
    if kind == "pantheon":  return state.pantheon, str(state.pantheon.id)
    resolver = _NameResolver(state)
    method = _KIND_RESOLVERS.get(kind)
    if method is None or method.startswith("_"):
        raise ValueError(f"unknown or unsupported kind: {kind!r}")
    return getattr(resolver, method)(name)


# ── Operation implementations ──────────────────────────────────────────────

def _coerce_value_to_field(target, leaf: str, value):
    """If `target.leaf` is a Pydantic-declared enum field, coerce a string
    `value` to the enum member so the exporter's `.value` access works.
    Returns the (possibly coerced) value unchanged otherwise."""
    import typing
    from enum import Enum
    cls = type(target)
    fields = getattr(cls, "model_fields", None)
    if not fields or leaf not in fields:
        return value
    annotation = fields[leaf].annotation
    # Strip Optional[X] / Union[X, None] wrappers.
    origin = typing.get_origin(annotation)
    if origin is typing.Union:
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            annotation = args[0]
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        if isinstance(value, str):
            try:
                return annotation(value)
            except ValueError:
                pass  # let the assignment fail naturally
    return value


def _apply_set_field(state, op: dict) -> InjectorResult:
    kind = op["kind"]
    name = op.get("name", "")
    field_name = op["field"]
    value = op["value"]
    entity, _eid = _get_kind_entity(state, kind, name)
    if entity is None:
        return InjectorResult("set_field", False, f"{kind} {name!r} not found",
                              error="not_found")
    # Dot-path support for nested attributes (e.g. "disposition.results"
    # on a Luminary, "health.stability" on a Civilization).
    if "." in field_name:
        parts = field_name.split(".")
        target = entity
        for p in parts[:-1]:
            if not hasattr(target, p):
                return InjectorResult("set_field", False,
                                      f"{kind} {name!r} has no nested field {p!r}",
                                      error="bad_field")
            target = getattr(target, p)
            if target is None:
                return InjectorResult("set_field", False,
                                      f"{kind} {name!r}.{p} is None — cannot descend",
                                      error="bad_field")
        leaf = parts[-1]
        if not hasattr(target, leaf):
            return InjectorResult("set_field", False,
                                  f"{kind} {name!r} has no leaf field {field_name!r}",
                                  error="bad_field")
        setattr(target, leaf, _coerce_value_to_field(target, leaf, value))
        return InjectorResult("set_field", True,
                              f"set {kind} {name!r}.{field_name} = {value!r}")
    if not hasattr(entity, field_name):
        return InjectorResult("set_field", False,
                              f"{kind} {name!r} has no field {field_name!r}",
                              error="bad_field")
    setattr(entity, field_name, _coerce_value_to_field(entity, field_name, value))
    return InjectorResult("set_field", True,
                          f"set {kind} {name!r}.{field_name} = {value!r}")


def _apply_set_dict_entry(state, op: dict) -> InjectorResult:
    kind = op["kind"]
    name = op.get("name", "")
    field_name = op["field"]
    key = op["key"]
    value = float(op["value"])
    entity, _eid = _get_kind_entity(state, kind, name)
    if entity is None:
        return InjectorResult("set_dict_entry", False,
                              f"{kind} {name!r} not found", error="not_found")
    target = getattr(entity, field_name, None)
    if not isinstance(target, dict):
        return InjectorResult("set_dict_entry", False,
                              f"{kind} {name!r}.{field_name} is not a dict",
                              error="bad_field")
    target[key] = value
    return InjectorResult("set_dict_entry", True,
                          f"set {kind} {name!r}.{field_name}[{key!r}] = {value}")


def _apply_remove_dict_entry(state, op: dict) -> InjectorResult:
    kind = op["kind"]; name = op.get("name", "")
    field_name = op["field"]; key = op["key"]
    entity, _eid = _get_kind_entity(state, kind, name)
    if entity is None:
        return InjectorResult("remove_dict_entry", False,
                              f"{kind} {name!r} not found", error="not_found")
    target = getattr(entity, field_name, None)
    if not isinstance(target, dict):
        return InjectorResult("remove_dict_entry", False,
                              f"{kind} {name!r}.{field_name} is not a dict",
                              error="bad_field")
    if key not in target:
        return InjectorResult("remove_dict_entry", True,
                              f"{kind} {name!r}.{field_name}[{key!r}] already absent")
    target.pop(key, None)
    return InjectorResult("remove_dict_entry", True,
                          f"removed {kind} {name!r}.{field_name}[{key!r}]")


def _apply_add_list_entry(state, op: dict) -> InjectorResult:
    kind = op["kind"]; name = op.get("name", "")
    field_name = op["field"]; value = op["value"]
    entity, _eid = _get_kind_entity(state, kind, name)
    if entity is None:
        return InjectorResult("add_list_entry", False,
                              f"{kind} {name!r} not found", error="not_found")
    target = getattr(entity, field_name, None)
    if not isinstance(target, list):
        return InjectorResult("add_list_entry", False,
                              f"{kind} {name!r}.{field_name} is not a list",
                              error="bad_field")
    if value in target:
        return InjectorResult("add_list_entry", True,
                              f"{kind} {name!r}.{field_name} already contains {value!r}")
    target.append(value)
    return InjectorResult("add_list_entry", True,
                          f"appended {value!r} to {kind} {name!r}.{field_name}")


def _apply_remove_list_entry(state, op: dict) -> InjectorResult:
    kind = op["kind"]; name = op.get("name", "")
    field_name = op["field"]; value = op["value"]
    entity, _eid = _get_kind_entity(state, kind, name)
    if entity is None:
        return InjectorResult("remove_list_entry", False,
                              f"{kind} {name!r} not found", error="not_found")
    target = getattr(entity, field_name, None)
    if not isinstance(target, list):
        return InjectorResult("remove_list_entry", False,
                              f"{kind} {name!r}.{field_name} is not a list",
                              error="bad_field")
    if value not in target:
        return InjectorResult("remove_list_entry", True,
                              f"{kind} {name!r}.{field_name} already lacked {value!r}")
    target.remove(value)
    return InjectorResult("remove_list_entry", True,
                          f"removed {value!r} from {kind} {name!r}.{field_name}")


def _apply_rename(state, op: dict) -> InjectorResult:
    kind = op["kind"]; name = op["name"]; new_name = op["new_name"]
    entity, _eid = _get_kind_entity(state, kind, name)
    if entity is None:
        return InjectorResult("rename", False, f"{kind} {name!r} not found",
                              error="not_found")
    if not hasattr(entity, "name"):
        return InjectorResult("rename", False, f"{kind} {name!r} has no name field",
                              error="bad_field")
    entity.name = new_name
    return InjectorResult("rename", True, f"{kind} {name!r} → {new_name!r}")


def _apply_create(state, op: dict) -> InjectorResult:
    """Create a new entity. The `values` dict carries fields; references to
    other entities use `*_name` keys (`civilization_name`, `location_name`,
    `species_name`, `parent_name`, etc.). Names are resolved at create time."""
    kind = op["kind"]
    v = op.get("values", {})
    resolver = _NameResolver(state)
    if kind == "galaxy":
        loc = Location(
            name=v["name"], location_type="galaxy", visibility=1.0, pinned=True,
        )
        state.locations[str(loc.id)] = loc
        state.universe.child_ids.append(loc.id)
        return InjectorResult("create", True, f"created galaxy {v['name']!r}")
    if kind == "system":
        parent, _ = resolver.location(v["parent_name"])
        if parent is None:
            return InjectorResult("create", False,
                                  f"parent galaxy {v['parent_name']!r} not found",
                                  error="not_found")
        sys_obj = System(
            name=v["name"], parent_id=parent.id,
            star_type=StarType(v.get("star_type", "main_sequence")),
            visibility=1.0, pinned=True,
        )
        state.locations[str(sys_obj.id)] = sys_obj
        parent.child_ids.append(sys_obj.id)
        return InjectorResult("create", True, f"created system {v['name']!r}")
    if kind == "world":
        parent, _ = resolver.location(v["parent_name"])
        if parent is None:
            return InjectorResult("create", False,
                                  f"parent system {v['parent_name']!r} not found",
                                  error="not_found")
        w = SignificantLocation(
            name=v["name"],
            location_type=v.get("location_type", "planet"),
            parent_id=parent.id,
            condition=LocCondition(v.get("condition", "stable")),
            age=float(v.get("age", 0)),
            geo_tags=list(v.get("geo_tags", ["geo:terrestrial"])),
            atmo_tags=list(v.get("atmo_tags", ["atmo:nitrogen_oxygen"])),
            visibility=1.0, pinned=True,
        )
        state.locations[str(w.id)] = w
        parent.child_ids.append(w.id)
        return InjectorResult("create", True, f"created world {v['name']!r}")
    if kind == "poploc":
        parent, _ = resolver.location(v["parent_name"])
        if parent is None:
            return InjectorResult("create", False,
                                  f"parent world {v['parent_name']!r} not found",
                                  error="not_found")
        pl = PopLocation(
            name=v["name"],
            location_type=v.get("location_type", "pop_location"),
            parent_id=parent.id,
            distance_from_core=int(v.get("distance_from_core", 0)),
            visibility=1.0, pinned=True,
        )
        state.locations[str(pl.id)] = pl
        parent.child_ids.append(pl.id)
        return InjectorResult("create", True, f"created poploc {v['name']!r}")
    if kind == "species":
        origin_id = None
        if v.get("origin_world_name"):
            origin, _ = resolver.location(v["origin_world_name"])
            if origin is None:
                return InjectorResult("create", False,
                                      f"origin world {v['origin_world_name']!r} not found",
                                      error="not_found")
            origin_id = origin.id
        sp = Species(
            name=v["name"],
            description=v.get("description", ""),
            origin_world_id=origin_id,
            sapient=bool(v.get("sapient", True)),
            lifespan_min=float(v.get("lifespan_min", 40)),
            lifespan_max=float(v.get("lifespan_max", 80)),
            condition=SpeciesCondition(v.get("condition", "stable")),
            visibility=1.0, pinned=True,
        )
        state.species[str(sp.id)] = sp
        if origin_id is not None and isinstance(state.locations.get(str(origin_id)), SignificantLocation):
            state.locations[str(origin_id)].species_ids.append(sp.id)
        return InjectorResult("create", True, f"created species {v['name']!r}")
    if kind == "civ":
        origin, _ = resolver.location(v["origin_location_name"])
        if origin is None:
            return InjectorResult("create", False,
                                  f"origin location {v['origin_location_name']!r} not found",
                                  error="not_found")
        sp_id = None
        if v.get("primary_species_name"):
            sp, _ = resolver.species(v["primary_species_name"])
            if sp is None:
                return InjectorResult("create", False,
                                      f"primary species {v['primary_species_name']!r} not found",
                                      error="not_found")
            sp_id = sp.id
        h = CivilizationHealth(
            stability=float(v.get("stability", 0.5)),
            prosperity=float(v.get("prosperity", 0.5)),
            cohesion=float(v.get("cohesion", 0.5)),
        )
        civ = Civilization(
            name=v["name"],
            description=v.get("description", ""),
            origin_location_id=origin.id,
            primary_species_id=sp_id,
            scale=CivilizationScale(v.get("scale", "tribal")),
            theistic=bool(v.get("theistic", True)),
            divine_awareness=float(v.get("divine_awareness", 0.3)),
            core_locs=[origin.id],
            health=h,
            age=float(v.get("age", 0)),
            visibility=1.0, pinned=True,
        )
        state.civilizations[str(civ.id)] = civ
        if isinstance(origin, SignificantLocation):
            origin.civilization_ids.append(civ.id)
        return InjectorResult("create", True, f"created civ {v['name']!r}")
    if kind == "pop":
        sp, _ = resolver.species(v["species_name"])
        if sp is None:
            return InjectorResult("create", False,
                                  f"species {v['species_name']!r} not found",
                                  error="not_found")
        loc, _ = resolver.location(v["location_name"])
        if loc is None or not isinstance(loc, PopLocation):
            return InjectorResult("create", False,
                                  f"poploc {v['location_name']!r} not found",
                                  error="not_found")
        civ_id = None
        if v.get("civilization_name"):
            civ, _ = resolver.civ(v["civilization_name"])
            if civ is None:
                return InjectorResult("create", False,
                                      f"civilization {v['civilization_name']!r} not found",
                                      error="not_found")
            civ_id = civ.id
        social_class = wild_stratum = None
        if v.get("social_class"):
            social_class = SocialClass(v["social_class"])
        if v.get("wild_stratum"):
            wild_stratum = WildStratum(v["wild_stratum"])
        if social_class is None and wild_stratum is None:
            # Default by species sapience.
            if sp.sapient:
                social_class = SocialClass.COMMON
            else:
                wild_stratum = WildStratum.HERD
        pop = Pop(
            name=v.get("name") or None,
            civilization_id=civ_id,
            species_id=sp.id,
            current_location=loc.id,
            social_class=social_class,
            wild_stratum=wild_stratum,
            size_fractional=float(v.get("size_fractional", 6.0)),
            visibility=1.0, pinned=True,
        )
        state.pops[str(pop.id)] = pop
        if civ_id is not None:
            state.civilizations[str(civ_id)].pop_ids.append(pop.id)
        loc.pop_ids.append(pop.id)
        return InjectorResult("create", True,
                              f"created pop {v.get('name') or pop.stratum!r} at {loc.name!r}")
    if kind == "mortal":
        sp, _ = resolver.species(v["species_name"])
        if sp is None:
            return InjectorResult("create", False,
                                  f"species {v['species_name']!r} not found",
                                  error="not_found")
        home, _ = resolver.location(v["home_location_name"])
        if home is None:
            return InjectorResult("create", False,
                                  f"home location {v['home_location_name']!r} not found",
                                  error="not_found")
        current_name = v.get("current_location_name", v["home_location_name"])
        cur, _ = resolver.location(current_name)
        if cur is None:
            return InjectorResult("create", False,
                                  f"current location {current_name!r} not found",
                                  error="not_found")
        civ_id = None
        if v.get("civilization_name"):
            civ, _ = resolver.civ(v["civilization_name"])
            if civ is None:
                return InjectorResult("create", False,
                                      f"civilization {v['civilization_name']!r} not found",
                                      error="not_found")
            civ_id = civ.id
        pop_id = None
        if v.get("pop_name"):
            pop, _ = resolver.pop(v["pop_name"])
            if pop is None:
                return InjectorResult("create", False,
                                      f"pop {v['pop_name']!r} not found",
                                      error="not_found")
            pop_id = pop.id
        m = NotableMortal(
            name=v["name"],
            description=v.get("description", ""),
            species_id=sp.id,
            civilization_id=civ_id,
            pop_id=pop_id,
            home_location=home.id,
            current_location=cur.id,
            role=MortalRole(v.get("role", "other")),
            status=MortalStatus(v.get("status", "active")),
            prominence=float(v.get("prominence", 0.5)),
            alignment=float(v.get("alignment", 0.8)),
            chrono_age=float(v.get("chrono_age", 30)),
            bio_age=float(v.get("bio_age", 30)),
            visibility=1.0, pinned=True,
        )
        state.mortals[str(m.id)] = m
        # Back-refs.
        if civ_id:
            state.civilizations[str(civ_id)].notable_mortal_ids.append(m.id)
        if pop_id:
            state.pops[str(pop_id)].notable_mortal_ids.append(m.id)
        if m.role == MortalRole.PROXIUS:
            m.appointed_by_demiurge = state.demiurge.id
            state.demiurge.proxius_ids.append(m.id)
            if isinstance(cur, SignificantLocation):
                cur.proxius_ids.append(m.id)
        elif m.role == MortalRole.HERALD:
            if v.get("appointed_by_luminary_name"):
                lum, _ = resolver.luminary(v["appointed_by_luminary_name"])
                if lum is not None:
                    m.appointed_by_luminary = lum.id
                    lum.herald_ids.append(m.id)
            if isinstance(cur, SignificantLocation):
                cur.herald_ids.append(m.id)
        return InjectorResult("create", True, f"created mortal {v['name']!r}")
    if kind == "luminary":
        lum = Luminary(
            name=v["name"],
            domains=dict(v.get("domains", {})),
            pantheon_id=state.pantheon.id,
            disposition=Disposition(
                results=float(v.get("disposition_results", 0.0)),
                methods=float(v.get("disposition_methods", 0.0)),
            ),
        )
        state.luminaries[str(lum.id)] = lum
        state.pantheon.luminary_ids.append(lum.id)
        state.luminary_attention[str(lum.id)] = float(v.get("attention", 0.0))
        return InjectorResult("create", True, f"created luminary {v['name']!r}")
    return InjectorResult("create", False, f"create not implemented for kind {kind!r}",
                          error="unsupported_kind")


def _apply_delete(state, op: dict) -> InjectorResult:
    """Mode: 'cascade' | 'flag' | 'strict' (default 'strict' — fails if any
    reference would dangle)."""
    kind = op["kind"]; name = op["name"]
    mode = op.get("mode", "strict")
    entity, eid = _get_kind_entity(state, kind, name)
    if entity is None:
        return InjectorResult("delete", False, f"{kind} {name!r} not found",
                              error="not_found")
    # Use the builder's existing back-ref-unlink helpers.
    from . import location_editor as locedit, entity_editor as entedit, mortal_editor as medit
    if kind in ("galaxy", "system", "world", "poploc", "location"):
        if mode == "strict":
            blocks = locedit.find_blocking_references(state, eid)
            if blocks:
                return InjectorResult("delete", False,
                    f"{kind} {name!r} has {len(blocks)} blocking ref(s) — use mode 'cascade' or 'flag'",
                    error="blocked")
        locedit.remove_from_parent(state, entity)
        state.locations.pop(eid, None)
    elif kind == "civ":
        if mode == "strict":
            blocks = entedit.find_civ_references(state, eid)
            if blocks:
                return InjectorResult("delete", False,
                    f"civ {name!r} has {len(blocks)} blocking ref(s) — use mode 'cascade' or 'flag'",
                    error="blocked")
        entedit.unlink_civ_back_refs(state, entity)
        state.civilizations.pop(eid, None)
    elif kind == "species":
        if mode == "strict":
            blocks = entedit.find_species_references(state, eid)
            if blocks:
                return InjectorResult("delete", False,
                    f"species {name!r} has {len(blocks)} blocking ref(s) — use mode 'cascade' or 'flag'",
                    error="blocked")
        entedit.unlink_species_back_refs(state, entity)
        state.species.pop(eid, None)
    elif kind == "pop":
        if mode == "strict":
            blocks = entedit.find_pop_references(state, eid)
            if blocks:
                return InjectorResult("delete", False,
                    f"pop {name!r} has {len(blocks)} blocking ref(s) — use mode 'cascade' or 'flag'",
                    error="blocked")
        entedit.unlink_pop_back_refs(state, entity)
        state.pops.pop(eid, None)
    elif kind == "mortal":
        medit.unlink_back_refs(state, entity)
        state.mortals.pop(eid, None)
    elif kind == "luminary":
        from . import luminary_editor as ledit
        ledit.unlink_luminary_back_refs(state, entity)
        state.luminaries.pop(eid, None)
    else:
        return InjectorResult("delete", False, f"delete not implemented for kind {kind!r}",
                              error="unsupported_kind")
    return InjectorResult("delete", True, f"deleted {kind} {name!r}")


def _apply_reassign(state, op: dict) -> InjectorResult:
    """Change a reference field on an entity. Supported (kind, field) combos:
      pop:    civilization|species|location|stratum
      mortal: species|civilization|pop|home_location|current_location|luminary
      civ:    primary_species|origin_location
    """
    kind = op["kind"]; name = op["name"]; field_name = op["field"]
    new_name = op.get("new_name")
    entity, _eid = _get_kind_entity(state, kind, name)
    if entity is None:
        return InjectorResult("reassign", False, f"{kind} {name!r} not found",
                              error="not_found")
    resolver = _NameResolver(state)
    if kind == "pop":
        if field_name == "civilization":
            if entity.civilization_id:
                old = state.civilizations.get(str(entity.civilization_id))
                if old: old.pop_ids = [p for p in old.pop_ids if p != entity.id]
            if new_name is None:
                entity.civilization_id = None
            else:
                civ, _ = resolver.civ(new_name)
                if civ is None:
                    return InjectorResult("reassign", False,
                                          f"civ {new_name!r} not found", error="not_found")
                entity.civilization_id = civ.id
                civ.pop_ids.append(entity.id)
            return InjectorResult("reassign", True, f"pop {name!r}.civ → {new_name!r}")
        if field_name == "species":
            sp, _ = resolver.species(new_name)
            if sp is None:
                return InjectorResult("reassign", False,
                                      f"species {new_name!r} not found", error="not_found")
            entity.species_id = sp.id
            return InjectorResult("reassign", True, f"pop {name!r}.species → {new_name!r}")
        if field_name == "location":
            loc, _ = resolver.location(new_name)
            if loc is None or not isinstance(loc, PopLocation):
                return InjectorResult("reassign", False,
                                      f"poploc {new_name!r} not found", error="not_found")
            if entity.current_location:
                old = state.locations.get(str(entity.current_location))
                if isinstance(old, PopLocation):
                    old.pop_ids = [p for p in old.pop_ids if p != entity.id]
            entity.current_location = loc.id
            loc.pop_ids.append(entity.id)
            return InjectorResult("reassign", True, f"pop {name!r}.location → {new_name!r}")
        if field_name == "stratum":
            # new_name is a SocialClass or WildStratum value string.
            try:
                entity.social_class = SocialClass(new_name); entity.wild_stratum = None
            except ValueError:
                try:
                    entity.wild_stratum = WildStratum(new_name); entity.social_class = None
                except ValueError:
                    return InjectorResult("reassign", False,
                                          f"stratum {new_name!r} not a SocialClass or WildStratum",
                                          error="bad_value")
            return InjectorResult("reassign", True, f"pop {name!r}.stratum → {new_name!r}")
    if kind == "mortal":
        if field_name == "species":
            sp, _ = resolver.species(new_name)
            if sp is None:
                return InjectorResult("reassign", False,
                                      f"species {new_name!r} not found", error="not_found")
            entity.species_id = sp.id
            return InjectorResult("reassign", True, f"mortal {name!r}.species → {new_name!r}")
        if field_name in ("home_location", "current_location"):
            loc, _ = resolver.location(new_name)
            if loc is None:
                return InjectorResult("reassign", False,
                                      f"location {new_name!r} not found", error="not_found")
            setattr(entity, field_name, loc.id)
            return InjectorResult("reassign", True,
                                  f"mortal {name!r}.{field_name} → {new_name!r}")
        if field_name == "civilization":
            if entity.civilization_id:
                old = state.civilizations.get(str(entity.civilization_id))
                if old: old.notable_mortal_ids = [m for m in old.notable_mortal_ids if m != entity.id]
            if new_name is None:
                entity.civilization_id = None
            else:
                civ, _ = resolver.civ(new_name)
                if civ is None:
                    return InjectorResult("reassign", False,
                                          f"civ {new_name!r} not found", error="not_found")
                entity.civilization_id = civ.id
                civ.notable_mortal_ids.append(entity.id)
            return InjectorResult("reassign", True, f"mortal {name!r}.civ → {new_name!r}")
        if field_name == "pop":
            if entity.pop_id:
                old = state.pops.get(str(entity.pop_id))
                if old: old.notable_mortal_ids = [m for m in old.notable_mortal_ids if m != entity.id]
            if new_name is None:
                entity.pop_id = None
            else:
                pop, _ = resolver.pop(new_name)
                if pop is None:
                    return InjectorResult("reassign", False,
                                          f"pop {new_name!r} not found", error="not_found")
                entity.pop_id = pop.id
                pop.notable_mortal_ids.append(entity.id)
            return InjectorResult("reassign", True, f"mortal {name!r}.pop → {new_name!r}")
        if field_name == "luminary":
            # Reappoint a Herald to a different Luminary.
            if entity.role != MortalRole.HERALD:
                return InjectorResult("reassign", False,
                                      f"mortal {name!r} is not a Herald", error="bad_role")
            if entity.appointed_by_luminary:
                old = state.luminaries.get(str(entity.appointed_by_luminary))
                if old: old.herald_ids = [h for h in old.herald_ids if h != entity.id]
            lum, _ = resolver.luminary(new_name)
            if lum is None:
                return InjectorResult("reassign", False,
                                      f"luminary {new_name!r} not found", error="not_found")
            entity.appointed_by_luminary = lum.id
            lum.herald_ids.append(entity.id)
            return InjectorResult("reassign", True,
                                  f"mortal {name!r}.appointed_by_luminary → {new_name!r}")
    if kind == "civ":
        if field_name == "primary_species":
            sp, _ = resolver.species(new_name)
            if sp is None:
                return InjectorResult("reassign", False,
                                      f"species {new_name!r} not found", error="not_found")
            entity.primary_species_id = sp.id
            return InjectorResult("reassign", True,
                                  f"civ {name!r}.primary_species → {new_name!r}")
        if field_name == "origin_location":
            loc, _ = resolver.location(new_name)
            if loc is None:
                return InjectorResult("reassign", False,
                                      f"location {new_name!r} not found", error="not_found")
            entity.origin_location_id = loc.id
            return InjectorResult("reassign", True,
                                  f"civ {name!r}.origin_location → {new_name!r}")
    return InjectorResult("reassign", False,
                          f"unsupported (kind, field): ({kind!r}, {field_name!r})",
                          error="unsupported_field")


def _apply_set_constraint(state, op: dict) -> InjectorResult:
    """Add or update a constraint on a Luminary or the Pantheon."""
    owner_kind = op["owner_kind"]  # 'luminary' | 'pantheon'
    owner_name = op.get("owner_name", "")
    constraint_name = op["constraint_name"]
    description = op.get("description", "")
    weight = float(op.get("enforcement_weight", 0.5))
    domain_tag = op.get("domain_tag")
    if owner_kind == "luminary":
        lum, _ = _NameResolver(state).luminary(owner_name)
        if lum is None:
            return InjectorResult("set_constraint", False,
                                  f"luminary {owner_name!r} not found", error="not_found")
        target_list = lum.constraints
        owner_label = f"luminary {lum.name!r}"
    elif owner_kind == "pantheon":
        target_list = state.pantheon.collective_constraints
        owner_label = "pantheon"
    else:
        return InjectorResult("set_constraint", False,
                              f"unsupported owner_kind: {owner_kind!r}",
                              error="bad_owner")
    existing = next((c for c in target_list if c.name == constraint_name), None)
    if existing is not None:
        existing.description = description
        existing.enforcement_weight = weight
        existing.domain_tag = domain_tag
        return InjectorResult("set_constraint", True,
                              f"updated constraint {constraint_name!r} on {owner_label}")
    target_list.append(NarrativeConstraint(
        name=constraint_name,
        description=description,
        enforcement_weight=weight,
        domain_tag=domain_tag,
    ))
    return InjectorResult("set_constraint", True,
                          f"added constraint {constraint_name!r} to {owner_label}")


def _apply_remove_constraint(state, op: dict) -> InjectorResult:
    owner_kind = op["owner_kind"]
    owner_name = op.get("owner_name", "")
    constraint_name = op["constraint_name"]
    if owner_kind == "luminary":
        lum, _ = _NameResolver(state).luminary(owner_name)
        if lum is None:
            return InjectorResult("remove_constraint", False,
                                  f"luminary {owner_name!r} not found", error="not_found")
        before = len(lum.constraints)
        lum.constraints = [c for c in lum.constraints if c.name != constraint_name]
        removed = before - len(lum.constraints)
    elif owner_kind == "pantheon":
        before = len(state.pantheon.collective_constraints)
        state.pantheon.collective_constraints = [
            c for c in state.pantheon.collective_constraints if c.name != constraint_name
        ]
        removed = before - len(state.pantheon.collective_constraints)
    else:
        return InjectorResult("remove_constraint", False,
                              f"unsupported owner_kind: {owner_kind!r}", error="bad_owner")
    if removed == 0:
        return InjectorResult("remove_constraint", True,
                              f"constraint {constraint_name!r} was already absent")
    return InjectorResult("remove_constraint", True,
                          f"removed constraint {constraint_name!r} ({removed} match(es))")


def _apply_set_luminary_domain(state, op: dict) -> InjectorResult:
    """Set (or remove, with affinity=None) a Luminary's affinity for a Domain."""
    lum, _ = _NameResolver(state).luminary(op["luminary_name"])
    if lum is None:
        return InjectorResult("set_luminary_domain", False,
                              f"luminary {op['luminary_name']!r} not found", error="not_found")
    tag = op["domain_tag"]
    if op.get("affinity") is None:
        lum.domains.pop(tag, None)
        return InjectorResult("set_luminary_domain", True,
                              f"removed {lum.name!r}.domains[{tag!r}]")
    lum.domains[tag] = float(op["affinity"])
    return InjectorResult("set_luminary_domain", True,
                          f"set {lum.name!r}.domains[{tag!r}] = {op['affinity']}")


def _apply_noop(state, op: dict) -> InjectorResult:
    return InjectorResult("noop", True, op.get("note", ""))


# ── Dispatch ───────────────────────────────────────────────────────────────

_OP_DISPATCH = {
    "set_field":          _apply_set_field,
    "set_dict_entry":     _apply_set_dict_entry,
    "remove_dict_entry":  _apply_remove_dict_entry,
    "add_list_entry":     _apply_add_list_entry,
    "remove_list_entry":  _apply_remove_list_entry,
    "rename":             _apply_rename,
    "create":             _apply_create,
    "delete":             _apply_delete,
    "reassign":           _apply_reassign,
    "set_constraint":     _apply_set_constraint,
    "remove_constraint":  _apply_remove_constraint,
    "set_luminary_domain": _apply_set_luminary_domain,
    "noop":               _apply_noop,
}


def apply_operations(state: SimulationState, ops: list[dict]) -> list[InjectorResult]:
    """Apply each op in order, returning per-op results. Errors don't abort
    the run — the caller decides what to do on failure."""
    out: list[InjectorResult] = []
    for raw in ops:
        op_name = raw.get("op")
        fn = _OP_DISPATCH.get(op_name)
        if fn is None:
            out.append(InjectorResult(op_name or "?", False,
                                      f"unknown op {op_name!r}",
                                      error="unknown_op"))
            continue
        try:
            out.append(fn(state, raw))
        except KeyError as exc:
            out.append(InjectorResult(op_name, False,
                                      f"missing required field {exc.args[0]!r}",
                                      error="missing_field"))
        except Exception as exc:
            out.append(InjectorResult(op_name, False, f"unexpected error: {exc}",
                                      error="exception"))
    return out


# ── Argument resolution ────────────────────────────────────────────────────

def resolve_scenario_path(ref: str) -> Path:
    """Resolve a `<scenario_ref>` CLI argument to a Path under `scenarios/`."""
    ref = ref.strip()
    if not ref:
        raise ValueError("scenario reference cannot be empty")
    # If it looks like an explicit path (has a slash), honor it; otherwise
    # treat the bare name as scenarios/<name>.db.
    if "/" in ref or "\\" in ref:
        p = Path(ref)
    else:
        stem = ref[:-3] if ref.endswith(".db") else ref
        p = _SCENARIOS_DIR / f"{stem}.db"
    return p


def resolve_patch(ref: str) -> dict:
    """Resolve a `<patch_ref>` CLI argument to a parsed dict. Accepts either
    a path to a .json file or a bare JSON object literal starting with '{'
    or '['."""
    ref = ref.strip()
    if not ref:
        raise ValueError("patch reference cannot be empty")
    if ref.startswith("{") or ref.startswith("["):
        return json.loads(ref)
    p = Path(ref)
    if not p.exists():
        raise FileNotFoundError(f"patch file not found: {p}")
    return json.loads(p.read_text())


# ── Top-level run ──────────────────────────────────────────────────────────

def run_injection(scenario_ref: str, patch_ref: str) -> InjectorRun:
    """Resolve refs, load (or create) the scenario, apply operations, save."""
    scenario_path = resolve_scenario_path(scenario_ref)
    patch = resolve_patch(patch_ref)
    if not isinstance(patch, dict) or "operations" not in patch:
        raise ValueError("patch must be a JSON object with an 'operations' list")

    created = not scenario_path.exists()
    if created:
        # Build a fresh skeleton named after the requested file.
        from .naming import derive_initialism
        stem = scenario_path.stem
        guess_name = patch.get("scenario_name") or stem.replace("_", " ").title()
        guess_init = derive_initialism(guess_name)
        state = build_skeleton_state(guess_name, guess_init)
    else:
        # Migrate the existing .db to the current schema before applying ops.
        mr = migrate_scenario(scenario_path)
        if not mr.migrated and mr.error is not None:
            raise RuntimeError(f"migration failed for {scenario_path}: {mr.note}")
        state = load_scenario(scenario_path)

    results = apply_operations(state, patch.get("operations", []))

    # Final flag check — surface any broken refs the patch left behind.
    broken = find_broken_refs(state)
    if broken:
        report = render_flag_report(state, broken)

    # Resolve scenario_name / description for the meta row.
    if scenario_path.exists():
        prev = peek_meta(scenario_path)
    else:
        prev = {"name": scenario_path.stem, "description": ""}
    scenario_name = patch.get("scenario_name") or prev.get("name") or scenario_path.stem
    description   = patch.get("description")   if patch.get("description") is not None else prev.get("description", "")
    if created:
        scenario_name = patch.get("scenario_name") or state.universe.name

    # Save unless any op failed in a way the caller flagged as fatal.
    fatal_ops = [r for r in results if not r.ok and r.error not in (None, "")]
    fatal_block_codes = {"missing_field", "unknown_op", "exception"}
    fatal = any(r.error in fatal_block_codes for r in fatal_ops)
    run = InjectorRun(
        scenario_path=scenario_path,
        created=created,
        results=results,
        saved=False,
        broken_refs=broken,
    )
    if fatal:
        run.summary_lines.append(
            f"✗ Refusing to save — {len([r for r in fatal_ops if r.error in fatal_block_codes])} fatal op error(s)."
        )
        return run
    if broken:
        run.summary_lines.append(
            f"⚠ Patch applied but left {len(broken)} broken reference(s); "
            "the file will be saved, but the resulting scenario is flagged "
            "and won't load cleanly in the builder until those are fixed."
        )
    try:
        export_scenario(state, scenario_path,
                        scenario_name=scenario_name, description=description)
        run.saved = True
    except Exception as exc:
        run.summary_lines.append(f"✗ Save failed: {exc}")
    return run


def print_run_report(run: InjectorRun) -> None:
    """Pretty-print the result of a run_injection call to stdout."""
    print(f"{'created' if run.created else 'opened'}: {run.scenario_path}")
    for r in run.results:
        tick = "✓" if r.ok else "✗"
        print(f"  {tick} [{r.op}] {r.note}")
    if run.broken_refs:
        print("")
        print("Broken references after patch:")
        print(render_flag_report(__import__('sys').modules[__name__]._cached_state, run.broken_refs))
    for line in run.summary_lines:
        print(line)
    print(f"{'saved' if run.saved else 'NOT saved'}: {run.scenario_path}")


def main(scenario_ref: str, patch_ref: str) -> int:
    """Entry point used by main.py --inject. Returns a process exit code."""
    try:
        run = run_injection(scenario_ref, patch_ref)
    except Exception as exc:
        print(f"--inject failed: {exc}", file=sys.stderr)
        return 2
    # Lightweight report.
    print(f"{'created' if run.created else 'opened'}: {run.scenario_path}")
    fatal = 0
    for r in run.results:
        tick = "✓" if r.ok else "✗"
        print(f"  {tick} [{r.op}] {r.note}")
        if not r.ok and r.error in {"missing_field", "unknown_op", "exception"}:
            fatal += 1
    if run.broken_refs:
        print("")
        print(f"⚠ {len(run.broken_refs)} broken reference(s) after patch:")
        # Render the report using the in-memory state from this run isn't
        # available here; just list the entity ids and their reasons.
        for eid, reasons in run.broken_refs.items():
            print(f"  • {eid[:8]}: {reasons[0]}")
    for line in run.summary_lines:
        print(line)
    print(f"{'saved' if run.saved else 'NOT saved'}: {run.scenario_path}")
    return 1 if fatal or not run.saved else 0


# ── Documentation: operation vocabulary ────────────────────────────────────

OPERATIONS_DOC = """
Operation vocabulary for --inject patches (see CLAUDE.md for the full
reference and worked examples):

  {"op": "set_field", "kind": "<kind>", "name": "<name>",
   "field": "<field>", "value": <any>}

  {"op": "set_dict_entry", "kind": "<kind>", "name": "<name>",
   "field": "<dict_field>", "key": "<tag>", "value": <float>}

  {"op": "remove_dict_entry", "kind": "<kind>", "name": "<name>",
   "field": "<dict_field>", "key": "<tag>"}

  {"op": "add_list_entry", "kind": "<kind>", "name": "<name>",
   "field": "<list_field>", "value": "<item>"}

  {"op": "remove_list_entry", "kind": "<kind>", "name": "<name>",
   "field": "<list_field>", "value": "<item>"}

  {"op": "rename", "kind": "<kind>", "name": "<old>", "new_name": "<new>"}

  {"op": "create", "kind": "<kind>", "values": { ... }}

  {"op": "delete", "kind": "<kind>", "name": "<name>",
   "mode": "strict|cascade|flag"}

  {"op": "reassign", "kind": "<kind>", "name": "<name>",
   "field": "<ref_field>", "new_name": "<new>"}

  {"op": "set_constraint", "owner_kind": "luminary|pantheon",
   "owner_name": "<lum_name_or_omitted>",
   "constraint_name": "<name>", "description": "<text>",
   "enforcement_weight": <float>, "domain_tag": "domain:..."|null}

  {"op": "remove_constraint", "owner_kind": "luminary|pantheon",
   "owner_name": "<lum_name_or_omitted>", "constraint_name": "<name>"}

  {"op": "set_luminary_domain", "luminary_name": "<name>",
   "domain_tag": "domain:...", "affinity": <float_or_null>}

  {"op": "noop", "note": "<optional explanation>"}

Kinds: universe, demiurge, pantheon, luminary,
       galaxy, system, world, poploc, location,
       civ, species, pop, mortal.

The singletons (universe / demiurge / pantheon) ignore the `name` field.
"""
