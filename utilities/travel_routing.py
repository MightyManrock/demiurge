"""
utilities/travel_routing.py

Routing helpers for the TravelLocation system.
  find_route     — BFS over PopLocations connected by shared travel_features
  leg_cost       — tick cost for one hop between two adjacent PopLocations
  build_legs     — convert a route list into the TravelLocation.legs dict
  get_or_create_travel_location — find joinable TravelLocation or create new one
"""
from __future__ import annotations
import math
from collections import deque
from uuid import UUID


def find_route(state, origin_id: UUID, destination_id: UUID) -> list[UUID] | None:
    """BFS over PopLocations connected by shared travel_features.
    Returns ordered list of PopLocation UUIDs from origin to destination,
    or None if no route exists.
    """
    from core.universe_core import PopLocation

    origin_str = str(origin_id)
    dest_str   = str(destination_id)

    if origin_str == dest_str:
        return [origin_id]

    queue: deque[list[str]] = deque([[origin_str]])
    visited: set[str] = {origin_str}

    while queue:
        path = queue.popleft()
        current_str = path[-1]
        current_loc = state.locations.get(current_str)
        if not isinstance(current_loc, PopLocation) or not current_loc.travel_features:
            continue
        for cand_str, cand_loc in state.locations.items():
            if not isinstance(cand_loc, PopLocation):
                continue
            if cand_str in visited:
                continue
            if not (current_loc.travel_features & cand_loc.travel_features):
                continue
            new_path = path + [cand_str]
            if cand_str == dest_str:
                return [UUID(s) for s in new_path]
            visited.add(cand_str)
            queue.append(new_path)
    return None


_SPACE_TRAVEL_CONSTANT = 3.0


def leg_cost(state, origin_id: UUID, dest_id: UUID) -> int:
    """Compute tick cost for one hop.
    Intra-world: distance_from_core formula.
    Cross-world: euclidean distance at divergence level / SPACE_TRAVEL_CONSTANT.
    """
    from core.universe_core import PopLocation
    origin = state.locations.get(str(origin_id))
    dest   = state.locations.get(str(dest_id))
    if not isinstance(origin, PopLocation) or not isinstance(dest, PopLocation):
        return 1

    coords = _divergence_coordinates(state, origin, dest)
    if coords is None:
        # Intra-world
        d = origin.distance_from_core + dest.distance_from_core
        return d if (origin.distance_from_core > 0 and dest.distance_from_core > 0) else d + 1

    ca, cb = coords
    dist = math.sqrt((ca.x - cb.x)**2 + (ca.y - cb.y)**2 + (ca.z - cb.z)**2)
    return max(1, math.ceil(dist / _SPACE_TRAVEL_CONSTANT))


def _divergence_coordinates(state, loc_a, loc_b):
    """Return (coord_a, coord_b) at the divergence level, or None for intra-world."""
    pid_a = str(loc_a.parent_id) if loc_a.parent_id else None
    pid_b = str(loc_b.parent_id) if loc_b.parent_id else None

    if pid_a == pid_b:
        return None  # same SignificantLocation → intra-world

    parent_a = state.locations.get(pid_a) if pid_a else None
    parent_b = state.locations.get(pid_b) if pid_b else None
    if parent_a is None or parent_b is None:
        return None

    gpid_a = str(parent_a.parent_id) if parent_a.parent_id else None
    gpid_b = str(parent_b.parent_id) if parent_b.parent_id else None

    if gpid_a == gpid_b:
        # Same System → use SignificantLocation coordinates (sublight)
        return (parent_a.coordinates, parent_b.coordinates)

    # Different Systems → use System coordinates (interstellar)
    gp_a = state.locations.get(gpid_a) if gpid_a else None
    gp_b = state.locations.get(gpid_b) if gpid_b else None
    if gp_a is None or gp_b is None:
        # Fall back to SignificantLocation coords
        return (parent_a.coordinates, parent_b.coordinates)
    return (gp_a.coordinates, gp_b.coordinates)


def build_legs(state, route: list[UUID]) -> dict[str, int]:
    """Convert a route (list of PopLocation UUIDs) into a TravelLocation.legs dict.
    Last entry always has value 0 (destination sentinel).
    """
    legs: dict[str, int] = {}
    for i, loc_id in enumerate(route):
        if i == len(route) - 1:
            legs[str(loc_id)] = 0
        else:
            legs[str(loc_id)] = leg_cost(state, loc_id, route[i + 1])
    return legs


def get_or_create_travel_location(state, legs: dict[str, int]):
    """Find an existing joinable TravelLocation or create a new one.
    Joinable = same legs dict AND current_waypoint is the first key (traveler starts at origin).
    Returns the TravelLocation instance (already added to state.locations if new).
    """
    from core.universe_core import TravelLocation

    first_wp = next(iter(legs))
    for loc in state.locations.values():
        if (
            isinstance(loc, TravelLocation)
            and loc.legs == legs
            and loc.current_waypoint == first_wp
        ):
            return loc

    dest_key = next(k for k, v in legs.items() if v == 0)
    origin_loc = state.locations.get(first_wp)
    dest_loc   = state.locations.get(dest_key)
    origin_name = origin_loc.name if origin_loc else first_wp
    dest_name   = dest_loc.name   if dest_loc   else dest_key

    tl = TravelLocation(
        name=f"In transit: {origin_name} → {dest_name}",
        legs=legs,
        current_waypoint=first_wp,
        ticks_remaining=legs[first_wp],
    )
    state.locations[str(tl.id)] = tl
    return tl
