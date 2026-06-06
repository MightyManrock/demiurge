"""
utilities/travel_routing.py

Routing helpers for the TravelLocation system.
  find_route     — BFS over PopLocations connected by shared TravelNetwork membership
  leg_cost       — tick cost for one hop between two adjacent PopLocations
  build_legs     — convert a route list into the TravelLocation.legs dict
  get_or_create_travel_location — find joinable TravelLocation or create new one
"""
from __future__ import annotations
import math
from collections import deque
from uuid import UUID

from core.universe_core import EntityAge


def find_route(state, origin_id: UUID, destination_id: UUID) -> list[UUID] | None:
    """BFS over PopLocations connected by shared TravelNetwork membership.
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
        if not isinstance(current_loc, PopLocation):
            continue
        neighbors = set()
        for net_id in current_loc.travel_network_ids:
            net = state.travel_networks.get(str(net_id))
            if net:
                neighbors.update(str(m) for m in net.member_ids)
        neighbors.discard(current_str)
        for cand_str in neighbors:
            cand_loc = state.locations.get(cand_str)
            if not isinstance(cand_loc, PopLocation):
                continue
            if cand_str in visited:
                continue
            new_path = path + [cand_str]
            if cand_str == dest_str:
                return [UUID(s) for s in new_path]
            visited.add(cand_str)
            queue.append(new_path)
    return None


_SUBLIGHT_SPEED = 50.0   # AU/tick  (intra-system travel)
_WARP_SPEED     = 80.0   # pc/tick  (interstellar warpspace travel)


def leg_cost(state, origin_id: UUID, dest_id: UUID) -> int:
    """Compute tick cost for one hop.
    Intra-world: distance_from_core formula.
    Intra-system cross-world: euclidean AU distance / _SUBLIGHT_SPEED.
    Inter-system: euclidean parsec distance / _WARP_SPEED.
    """
    from core.universe_core import PopLocation
    origin = state.locations.get(str(origin_id))
    dest   = state.locations.get(str(dest_id))
    if not isinstance(origin, PopLocation) or not isinstance(dest, PopLocation):
        return 1

    coords = _divergence_coordinates(state, origin, dest)
    if coords is None:
        # Intra-world: minimum 1 tick; each depth unit costs 1 tick
        d = origin.distance_from_core + dest.distance_from_core
        return max(1, d)

    ca, cb, speed = coords
    dist = math.sqrt((ca.x - cb.x)**2 + (ca.y - cb.y)**2 + (ca.z - cb.z)**2)
    return max(1, math.ceil(dist / speed))


def _divergence_coordinates(state, loc_a, loc_b):
    """Return (coord_a, coord_b, speed) at the divergence level, or None for intra-world.

    Speed is _SUBLIGHT_SPEED when coordinates are in AU (same system, different worlds),
    or _WARP_SPEED when coordinates are in parsecs (different systems).
    """
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
        # Same System → SignificantLocation coordinates in AU → sublight
        return (parent_a.coordinates, parent_b.coordinates, _SUBLIGHT_SPEED)

    # Different Systems → System coordinates in parsecs → warp
    gp_a = state.locations.get(gpid_a) if gpid_a else None
    gp_b = state.locations.get(gpid_b) if gpid_b else None
    if gp_a is None or gp_b is None:
        # Fall back to SignificantLocation coords (treat as sublight)
        return (parent_a.coordinates, parent_b.coordinates, _SUBLIGHT_SPEED)
    return (gp_a.coordinates, gp_b.coordinates, _WARP_SPEED)


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
    from core.universe_core import TravelLocation, PopLocation

    first_wp = next(iter(legs))
    for loc in state.locations.values():
        if (
            isinstance(loc, TravelLocation)
            and loc.legs == legs
            and loc.current_waypoint == first_wp
        ):
            return loc

    dest_key = next(k for k, v in legs.items() if v == 0)

    route_keys = list(legs.keys())
    seen_net_ids: set[str] = set()
    net_names: list[str] = []
    for i in range(len(route_keys) - 1):
        a_loc = state.locations.get(route_keys[i])
        b_loc = state.locations.get(route_keys[i + 1])
        if isinstance(a_loc, PopLocation) and isinstance(b_loc, PopLocation):
            shared = set(str(x) for x in a_loc.travel_network_ids) & set(str(x) for x in b_loc.travel_network_ids)
            for net_id in shared:
                if net_id not in seen_net_ids:
                    seen_net_ids.add(net_id)
                    net = state.travel_networks.get(net_id)
                    if net:
                        net_names.append(net.name)

    if net_names:
        transit_name = f"In transit via {', '.join(net_names)}"
    else:
        origin_loc = state.locations.get(first_wp)
        dest_loc   = state.locations.get(dest_key)
        origin_name = origin_loc.name if origin_loc else first_wp
        dest_name   = dest_loc.name   if dest_loc   else dest_key
        transit_name = f"In transit: {origin_name} → {dest_name}"

    u = state.universe.age
    creation_date: tuple[int, int, int, int, int, int] = (
        u.billions, u.millions, u.thousands, u.years, u.month, u.day,
    )
    tl = TravelLocation(
        name=transit_name,
        legs=legs,
        current_waypoint=first_wp,
        ticks_remaining=legs[first_wp],
        age=EntityAge(
            billions=u.billions, millions=u.millions, thousands=u.thousands,
            years=u.years, month=u.month, day=u.day,
            formation_date=creation_date,
        ),
    )
    state.locations[str(tl.id)] = tl
    return tl
