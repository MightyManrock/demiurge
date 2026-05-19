"""
Broken-reference detector for the scenario builder.

After a "delete and flag" operation, some entities will be left with
dangling outgoing pointers — a mortal whose `species_id` no longer
resolves, a pop whose `civilization_id` is gone, etc. `find_broken_refs`
scans the current state and returns a mapping `{entity_id: [reasons]}`.

The BuilderScreen runs this on every refresh, populates `_flagged_ids`
from the keys, and registers a flag predicate with the widgets layer so
clickable entity links render in red wherever they appear. Saving is
refused while any flags exist; quitting requires explicit confirmation.

Only outgoing primary references are checked. Back-ref lists
(`civilization.pop_ids`, `world.proxius_ids`, etc.) are deliberately not
flagged — they're auto-maintained on delete and would clutter the report.
"""
from __future__ import annotations
from typing import Optional
from uuid import UUID

from core.universe_core import PopLocation, SignificantLocation
from logic.tick_logic import SimulationState


def _has_location(state: SimulationState, uid: Optional[UUID]) -> bool:
    return uid is None or str(uid) in state.locations


def _has_species(state: SimulationState, uid: Optional[UUID]) -> bool:
    return uid is None or str(uid) in state.species


def _has_civ(state: SimulationState, uid: Optional[UUID]) -> bool:
    return uid is None or str(uid) in state.civilizations


def _has_pop(state: SimulationState, uid: Optional[UUID]) -> bool:
    return uid is None or str(uid) in state.pops


def _has_mortal(state: SimulationState, uid: Optional[UUID]) -> bool:
    return uid is None or str(uid) in state.mortals


def _has_luminary(state: SimulationState, uid: Optional[UUID]) -> bool:
    return uid is None or str(uid) in state.luminaries


def find_broken_refs(state: SimulationState) -> dict[str, list[str]]:
    """Return {entity_id_str: [reason_strings, ...]} for every entity with
    one or more dangling outgoing references. Empty dict means clean."""
    broken: dict[str, list[str]] = {}

    def _flag(eid: str, reason: str) -> None:
        broken.setdefault(eid, []).append(reason)

    # Mortals
    for mid, m in state.mortals.items():
        if not _has_species(state, m.species_id):
            _flag(mid, f"species_id → missing species ({str(m.species_id)[:8]})")
        if not _has_civ(state, m.civilization_id):
            _flag(mid, f"civilization_id → missing civ ({str(m.civilization_id)[:8]})")
        if not _has_pop(state, m.pop_id):
            _flag(mid, f"pop_id → missing pop ({str(m.pop_id)[:8]})")
        if not _has_location(state, m.home_location):
            _flag(mid, f"home_location → missing location ({str(m.home_location)[:8]})")
        if not _has_location(state, m.current_location):
            _flag(mid, f"current_location → missing location ({str(m.current_location)[:8]})")
        if m.appointed_by_luminary and not _has_luminary(state, m.appointed_by_luminary):
            _flag(mid, f"appointed_by_luminary → missing luminary ({str(m.appointed_by_luminary)[:8]})")

    # Pops
    for pid, pop in state.pops.items():
        if not _has_civ(state, pop.civilization_id):
            _flag(pid, f"civilization_id → missing civ ({str(pop.civilization_id)[:8]})")
        if not _has_species(state, pop.species_id):
            _flag(pid, f"species_id → missing species ({str(pop.species_id)[:8]})")
        if not _has_location(state, pop.current_location):
            _flag(pid, f"current_location → missing location ({str(pop.current_location)[:8]})")
        if pop.parent_pop_id and not _has_pop(state, pop.parent_pop_id):
            _flag(pid, f"parent_pop_id → missing pop ({str(pop.parent_pop_id)[:8]})")

    # Civilizations
    for cid, civ in state.civilizations.items():
        if not _has_location(state, civ.origin_location_id):
            _flag(cid, f"origin_location_id → missing location ({str(civ.origin_location_id)[:8]})")
        if not _has_species(state, civ.primary_species_id):
            _flag(cid, f"primary_species_id → missing species ({str(civ.primary_species_id)[:8]})")
        for lid in civ.core_locs:
            if not _has_location(state, lid):
                _flag(cid, f"core_locs entry → missing location ({str(lid)[:8]})")

    # Species
    for sid, sp in state.species.items():
        if not _has_location(state, sp.origin_world_id):
            _flag(sid, f"origin_world_id → missing location ({str(sp.origin_world_id)[:8]})")

    # Locations: parent_id integrity. Galaxies' parent_id is None and they
    # should appear in Universe.child_ids (a missing universe entry is a
    # data bug, not an authoring concern, so we don't flag it).
    universe_children = {str(c) for c in state.universe.child_ids}
    for eid, loc in state.locations.items():
        if loc.parent_id is not None:
            if not _has_location(state, loc.parent_id):
                _flag(eid, f"parent_id → missing parent location ({str(loc.parent_id)[:8]})")
        # SignificantLocation back-ref lists pointing at deleted entities.
        if isinstance(loc, SignificantLocation):
            for sub in loc.species_ids:
                if not _has_species(state, sub):
                    _flag(eid, f"species_ids → missing species ({str(sub)[:8]})")
            for sub in loc.civilization_ids:
                if not _has_civ(state, sub):
                    _flag(eid, f"civilization_ids → missing civ ({str(sub)[:8]})")

    # Demiurge
    for lid in state.demiurge.liege_luminary_ids:
        if not _has_luminary(state, lid):
            _flag(str(state.demiurge.id),
                  f"liege_luminary_ids → missing luminary ({str(lid)[:8]})")

    return broken


def render_flag_report(state: SimulationState, broken: dict[str, list[str]]) -> str:
    """Format a human-readable flag report. Used by save and quit guards."""
    if not broken:
        return ""
    name_lookups = [
        ("mortal",   state.mortals),
        ("pop",      state.pops),
        ("civ",      state.civilizations),
        ("species",  state.species),
        ("location", state.locations),
    ]
    def _label(eid: str) -> str:
        for kind, table in name_lookups:
            entry = table.get(eid)
            if entry is None:
                continue
            name = getattr(entry, "name", None) or eid[:8]
            return f"{kind}: {name}"
        if eid == str(state.demiurge.id):
            return f"demiurge: {state.demiurge.name}"
        return eid[:8]
    lines = [f"{_label(eid)}" for eid in broken.keys()]
    detail = []
    for eid, reasons in broken.items():
        detail.append(f"  • {_label(eid)}")
        for r in reasons[:3]:
            detail.append(f"      — {r}")
        if len(reasons) > 3:
            detail.append(f"      …and {len(reasons) - 3} more")
    return "\n".join(detail)
