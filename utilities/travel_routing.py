"""
utilities/travel_routing.py

Routing helpers for the TravelLocation system.
  find_route              — BFS over PopLocations connected by shared TravelNetwork membership
  find_qualified_routes   — condition-aware BFS returning TravelRoute with cost/danger metrics
  leg_cost                — tick cost for one hop between two adjacent PopLocations
  build_legs              — convert a route list into the TravelLocation.legs dict
  get_or_create_travel_location — find joinable TravelLocation or create new one
"""
from __future__ import annotations
import math
from collections import deque
from dataclasses import dataclass
from uuid import UUID

from core.universe_core import EntityAge


@dataclass
class TravelRoute:
    waypoints: list[UUID]   # ordered PopLocation UUIDs origin→destination
    legs: dict[str, int]    # str(UUID) → tick cost; last entry value=0
    total_ticks: int
    resource_costs: list    # list[ResourceCost] — resources consumed on this route
    network_ids: list[UUID] # networks traversed (for transit name)
    total_danger: float     # sum of effective danger across traversed waypoints (excl. origin)
    avg_danger_per_location: float  # total_danger / number of traversed locations
    avg_danger_per_tick: float      # sum(danger_i × leg_ticks_i) / total_ticks


def _mortal_meets_condition(condition, mortal, state) -> bool:
    """Return True if mortal satisfies ALL non-empty criteria in condition.
    An empty list on any criterion means 'no restriction on that criterion'.
    """
    # faction_ids: mortal's Pop must share a faction with condition
    if condition.faction_ids:
        pop = state.pops.get(str(mortal.pop_id)) if mortal.pop_id else None
        if pop is None:
            return False
        if not (set(str(f) for f in pop.faction_ids) & set(str(f) for f in condition.faction_ids)):
            return False

    # civilization_ids: mortal's civ must be in condition list
    if condition.civilization_ids:
        if mortal.civilization_id is None:
            return False
        if str(mortal.civilization_id) not in {str(c) for c in condition.civilization_ids}:
            return False

    # asset_types: mortal must own at least one matching asset type
    if condition.asset_types:
        mortal_asset_types = {a.asset_type for a in mortal.assets}
        if not (mortal_asset_types & set(condition.asset_types)):
            return False

    # pop_strata: mortal's Pop social_class must be in condition list
    if condition.pop_strata:
        pop = state.pops.get(str(mortal.pop_id)) if mortal.pop_id else None
        if pop is None or pop.social_class is None:
            return False
        if pop.social_class not in condition.pop_strata:
            return False

    # pop_occupations: mortal's occupation must be in condition list
    if condition.pop_occupations:
        if mortal.occupation not in condition.pop_occupations:
            return False

    return True


def _network_hard_gates_mortal(net, mortal, state) -> bool:
    """Return True if ANY hard-gated condition on this network fails for this mortal.
    A network with no conditions is never gated.
    A network with mixed hard-gate and non-hard-gate conditions: failing ANY hard-gate condition blocks the entire network.
    """
    return any(
        c.hard_gate and not _mortal_meets_condition(c, mortal, state)
        for c in net.conditions
    )


def _build_travel_route(state, mortal, waypoints) -> TravelRoute:
    """Given an ordered list of waypoint UUIDs, compute a full TravelRoute."""
    from core.universe_core import PopLocation

    if len(waypoints) == 1:
        origin_str = str(waypoints[0])
        return TravelRoute(
            waypoints=list(waypoints),
            legs={origin_str: 0},
            total_ticks=0,
            resource_costs=[],
            network_ids=[],
            total_danger=0.0,
            avg_danger_per_location=0.0,
            avg_danger_per_tick=0.0,
        )

    legs: dict[str, int] = {}
    seen_network_ids: set[str] = set()
    network_ids: list = []
    resource_costs: list = []
    seen_resource_net_ids: set[str] = set()
    total_danger = 0.0
    weighted_danger = 0.0

    for i in range(len(waypoints) - 1):
        a_id = waypoints[i]
        b_id = waypoints[i + 1]
        a_str = str(a_id)
        b_str = str(b_id)

        a_loc = state.locations.get(a_str)
        b_loc = state.locations.get(b_str)

        baseline = leg_cost(state, a_id, b_id)
        best_cost = baseline

        # Find shared networks between A and B
        a_nets = set(str(n) for n in (a_loc.travel_network_ids if isinstance(a_loc, PopLocation) else []))
        b_nets = set(str(n) for n in (b_loc.travel_network_ids if isinstance(b_loc, PopLocation) else []))
        shared_net_strs = a_nets & b_nets

        # Track danger modifier for this leg
        leg_danger_modifier = 0.0

        for net_str in shared_net_strs:
            net = state.travel_networks.get(net_str)
            if net is None:
                continue

            # Track network IDs and names
            if net_str not in seen_network_ids:
                seen_network_ids.add(net_str)
                network_ids.append(net.id)

            # Check qualifying conditions for privileged cost and danger modifier
            for cond in net.conditions:
                if _mortal_meets_condition(cond, mortal, state):
                    # Apply privileged cost: find the TravelEdge for this pair
                    for edge in net.edges:
                        edge_a = str(edge.node_a)
                        edge_b = str(edge.node_b)
                        if (edge_a == a_str and edge_b == b_str) or (edge_a == b_str and edge_b == a_str):
                            best_cost = min(best_cost, edge.privileged_cost)

                    # Accumulate danger modifier (additive)
                    leg_danger_modifier += cond.danger_modifier

                    # Collect resource costs once per network
                    if net_str not in seen_resource_net_ids and cond.resource_cost:
                        seen_resource_net_ids.add(net_str)
                        resource_costs.extend(cond.resource_cost)

        legs[a_str] = max(1, best_cost)

        # Compute effective danger at destination waypoint (b)
        b_danger = b_loc.danger if isinstance(b_loc, PopLocation) else 0.0
        effective_danger = max(0.0, min(1.0, b_danger + leg_danger_modifier))
        total_danger += effective_danger
        weighted_danger += effective_danger * best_cost

    # Sentinel: destination has cost 0
    legs[str(waypoints[-1])] = 0

    total_ticks = sum(v for v in legs.values())
    traversed_count = len(waypoints) - 1  # exclude origin
    avg_danger_per_location = total_danger / traversed_count if traversed_count > 0 else 0.0
    avg_danger_per_tick = weighted_danger / total_ticks if total_ticks > 0 else 0.0

    return TravelRoute(
        waypoints=list(waypoints),
        legs=legs,
        total_ticks=total_ticks,
        resource_costs=resource_costs,
        network_ids=network_ids,
        total_danger=total_danger,
        avg_danger_per_location=avg_danger_per_location,
        avg_danger_per_tick=avg_danger_per_tick,
    )


def find_qualified_routes(state, mortal, mortal_state, origin_id, destination_id) -> list:
    """BFS over PopLocations, filtering networks that hard-gate this mortal.
    Returns a list containing one TravelRoute (the BFS-optimal path), or [] if unreachable.
    Returns the hop-minimum path (fewest intermediate locations), not necessarily the tick-cost-minimum path.
    mortal_state is accepted for API completeness but not currently used in condition evaluation.
    """
    from core.universe_core import PopLocation

    origin_str = str(origin_id)
    dest_str = str(destination_id)

    # Trivial case
    if origin_str == dest_str:
        route = TravelRoute(
            waypoints=[origin_id],
            legs={origin_str: 0},
            total_ticks=0,
            resource_costs=[],
            network_ids=[],
            total_danger=0.0,
            avg_danger_per_location=0.0,
            avg_danger_per_tick=0.0,
        )
        return [route]

    queue: deque[list[str]] = deque([[origin_str]])
    visited: set[str] = {origin_str}

    while queue:
        path = queue.popleft()
        current_str = path[-1]
        current_loc = state.locations.get(current_str)
        if not isinstance(current_loc, PopLocation):
            continue

        neighbors: set[str] = set()
        for net_id in current_loc.travel_network_ids:
            net = state.travel_networks.get(str(net_id))
            if net is None:
                continue
            # Skip this network entirely if it hard-gates the mortal
            if _network_hard_gates_mortal(net, mortal, state):
                continue
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
                waypoints = [UUID(s) for s in new_path]
                route = _build_travel_route(state, mortal, waypoints)
                return [route]
            visited.add(cand_str)
            queue.append(new_path)

    return []


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
