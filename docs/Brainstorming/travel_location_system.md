# TravelLocation System — Concept & Initial Implementation

## The TravelLocation Entity

When a mortal begins traveling, a `TravelLocation` entity is instantiated to represent where they actually are during transit. This replaces the abstract "in transit" state with a real, scryable location that has mechanical meaning.

### Key Properties

- **Route**: an ordered sequence of `PopLocation` waypoints from origin to destination
- **Legs**: the segments between consecutive waypoints; the character advances one leg per tick (or per however many ticks that leg costs)
- **Occupants**: the mortals currently sharing this `TravelLocation`
- **Current leg**: which segment of the journey is currently active

### Why a Real Entity

Making `TravelLocation` a first-class entity rather than an abstract state gives the system several properties for free:

- **Scryable**: The Demiurge can observe that two mortals are traveling together without having anticipated it. You discover this the way you discover anything — by looking.
- **Joinable**: If a second mortal begins traveling the same route, they join the existing `TravelLocation` rather than instantiating a parallel one. Two characters who book the same commercial route are mechanically in the same place.
- **An event space**: Things that happen in transit have somewhere real to happen. Characters on the same leg can interact; future systems can trigger travel events within a `TravelLocation`.
- **Leg-aware**: Characters traveling in opposite directions on a shared route could share a waypoint leg briefly, enabling chance encounters even between travelers moving in opposite directions.

---

## PopLocation `travel_features`

`PopLocation` entities gain a `travel_features` field: a set of tags indicating what kinds of travel connections that location supports. Two `PopLocations` can be connected in a route only if they share a compatible `travel_feature`.

This means travel is **infrastructure-gated**: a mortal cannot route through a connection that doesn't exist. Travel features also carry flavor that can eventually affect travel time, cost, event probability, and discovery mechanics.

### Routing

Route planning is a graph traversal over `PopLocations` connected by shared `travel_features`. Given an origin and a destination, the system finds a valid path through connected waypoints.

### Distance

Travel between SignificantLocations, in this case planets, uses CosmicCoordinates to calculate the distance and therefore the duration of the journey. In the future, different levels of tech belonging to a Civilization will modify this.

---

## Implementation Test: Durenn Vail

Durenn Vail is a merchant on Neran whose business takes him regularly to the colony world Sethis. His journey tests cross-`SignificantLocation` travel, multi-waypoint routing, and `travel_feature`-gated connections.

### Locations and Features

**Neran** (SignificantLocation)

| PopLocation | Travel Features |
|---|---|
| Neran Surface | `space_elevator` |
| Neran Orbital Ring | `space_elevator`, `commercial_space_port` |

**Sethis** (SignificantLocation)

| PopLocation | Travel Features |
|---|---|
| Sethis Orbital Station | `commercial_space_port`, `shuttle_service` |
| Sethis Surface | `shuttle_service` |

### Vail's Route

```
Neran Surface
    ↓ space_elevator
Neran Orbital Ring
    ↓ commercial_space_port  [interstellar leg]
Sethis Orbital Station
    ↓ shuttle_service
Sethis Surface
```

The routing algorithm selects this path by finding the chain of shared `travel_features` between consecutive waypoints. Where multiple features connect two `PopLocations` (Neran Surface ↔ Neran Orbital Ring has both `space_elevator` and `shuttle_service`), the implementation can initially pick either; future systems might let the character or routing logic prefer one based on cost, time, or circumstance.

### What the Test Validates

1. **Route planning**: the routing algorithm correctly traverses `travel_features` to build Vail's four-waypoint route
2. **TravelLocation instantiation**: a `TravelLocation` is created at journey start and Vail is placed in it
3. **Leg advancement**: Vail advances through legs correctly, crossing the `SignificantLocation` boundary between Neran and Sethis
4. **Scryability**: Vail is observable at each stage of his journey, including during the interstellar leg
5. **Arrival**: Vail's `PopLocation` updates to Sethis Surface on journey completion and the `TravelLocation` is cleared

---

## Future Extensions

- **Joinable routes**: a second traveler on the same route joins Vail's `TravelLocation` rather than spawning a new one
- **Leg-based interactions**: characters sharing a leg can interact, enabling emergent meetings in transit
- **Travel events**: events that fire within a `TravelLocation` based on route, occupants, or leg context
- **Feature-based modifiers**: `space_elevator` vs. `shuttle_service` having different travel times, costs, or encounter probabilities
- **Infrastructure as a target**: destroying or disrupting a `travel_feature` severs the connection for all future routing through it
