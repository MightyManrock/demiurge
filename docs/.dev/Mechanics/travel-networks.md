> [← CLAUDE.md](../../CLAUDE.md)

# Travel Networks

## Overview

Travel between `PopLocation`s is mediated by `TravelNetwork` objects. A network is a named group of locations that are mutually reachable under shared conditions. Mortals route through networks; the network's `conditions` determine who may use each leg.

All models live in `core/universe_core.py`.

---

## Data model

### TravelNetwork

```python
class TravelNetwork(BaseModel):
    id: UUID
    name: str
    member_ids: list[UUID]              # PopLocation IDs in this network
    edges: list[TravelEdge]             # explicit pairwise costs (optional)
    conditions: list[NetworkCondition]  # access gates applied to all members
```

Members are mutually adjacent for routing — a mortal at any member location can reach any other member location. If no `TravelEdge` exists for a pair, a default cost applies.

### TravelEdge

```python
class TravelEdge(BaseModel):
    node_a: UUID
    node_b: UUID
    privileged_cost: int   # tick cost for privileged travellers (lower than default)
```

Edges are bidirectional. `privileged_cost` applies when a `NetworkCondition` gate passes; the default (higher) cost applies otherwise, or when no edge exists.

### NetworkCondition

```python
class NetworkCondition(BaseModel):
    faction_ids: list[UUID]        # allowed factions (empty = no faction gate)
    civilization_ids: list[UUID]   # allowed civs (empty = no civ gate)
    asset_types: list[str]         # required asset types (empty = no asset gate)
    pop_strata: list[SocialClass]  # allowed social classes (empty = no stratum gate)
    pop_occupations: list[str]     # allowed occupations (empty = no occupation gate)
    hard_gate: bool = False        # if True, non-qualifying mortals are blocked entirely
    resource_cost: list[ResourceCost]  # resources consumed on entry
    danger_modifier: float = 0.0   # added to the destination's base danger
```

Each gate field is an allowlist — an empty list means "no restriction on this dimension." A mortal passes the condition if they satisfy all non-empty gates simultaneously.

`hard_gate = True` bars entry entirely for non-qualifying mortals. `hard_gate = False` allows entry at higher cost or danger rather than blocking.

### PopLocation.danger

```python
class PopLocation(Location):
    ...
    danger: float = Field(ge=0.0, le=1.0, default=0.0)
```

Base danger for the location. `NetworkCondition.danger_modifier` is added on top when a mortal uses a conditioned network to reach it. Danger affects travel safety outcomes (future mechanics).

---

## Route selection

When a mortal needs to travel, the routing pass:

1. Finds all `TravelNetwork`s that include the mortal's current location and the target location.
2. Evaluates `NetworkCondition`s for each candidate network against the mortal's profile (faction membership, civ, assets, stratum, occupation).
3. Selects the network with the best cost/danger trade-off the mortal qualifies for.
4. Creates a `TravelLocation` ephemeral record to track the mortal's in-transit state.

### TravelLocation

```python
class TravelLocation(Location):
    location_type: str = "travel_location"
    legs: dict[str, int]       # ordered: PopLocation UUID → tick cost per leg
    current_waypoint: str      # UUID of the leg currently in progress
    ticks_remaining: int       # ticks left on the current leg
    occupants: list[UUID]      # mortal IDs in transit
    pop_ids: list[UUID]        # for compatibility with pop-querying utilities
```

`TravelLocation` lives in `state.locations` only while occupied. It is removed when the last occupant reaches the destination.

---

## Faction-gated networks

Setting `NetworkCondition.faction_ids` restricts a network to members of the listed factions. `NotableMortal.faction_ids` is the authoritative membership field used by the gate check — not `Pop.faction_ids` or indirect pop affiliation.

Example: an Asha Deep trade network restricted to Asha Deep faction members would have a `NetworkCondition` with `faction_ids=[asha_deep_faction_id]` and `hard_gate=True`.

---

## Current state

The `TravelNetwork` data model and persistence layer are fully implemented. Route selection and `NetworkCondition` enforcement are structurally complete; full integration into the mortal agent decision loop is ongoing.
