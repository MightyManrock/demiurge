from __future__ import annotations
from typing import TYPE_CHECKING

from core.universe_core import SignificantLocation, PopLocation

if TYPE_CHECKING:
    from logic.tick_logic import SimulationState


def resolve_world_id_for(state: "SimulationState", loc_id) -> "str | None":
    """Return the str id of the SignificantLocation (world) covering loc_id.

    If loc_id is already a SignificantLocation, returns it. If it's a
    PopLocation, walks up to its parent. Returns None for anything else."""
    if loc_id is None:
        return None
    loc = state.locations.get(str(loc_id))
    if isinstance(loc, SignificantLocation):
        return str(loc.id)
    if isinstance(loc, PopLocation) and loc.parent_id is not None:
        parent = state.locations.get(str(loc.parent_id))
        if isinstance(parent, SignificantLocation):
            return str(parent.id)
    return None


def resolve_world_for(state: "SimulationState", loc_id) -> "SignificantLocation | None":
    """Same as resolve_world_id_for but returns the SignificantLocation object."""
    wid = resolve_world_id_for(state, loc_id)
    return state.worlds.get(wid) if wid else None


def cosine_similarity(a: dict[str, float], b: dict[str, float]) -> float:
    """Cosine similarity between two belief/domain dicts. Returns 0.0–1.0."""
    if not a or not b:
        return 0.0
    tags = set(a) | set(b)
    dot = sum(a.get(t, 0.0) * b.get(t, 0.0) for t in tags)
    mag_a = sum(v * v for v in a.values()) ** 0.5
    mag_b = sum(v * v for v in b.values()) ** 0.5
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)
