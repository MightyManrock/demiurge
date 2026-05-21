# Mortal Travel System — Initial Implementation

## Scope

This document describes the first implementation of mortal movement. The scope is intentionally minimal: movement between sub-locations within the same SignificantLocation only. Inter-world and inter-system travel is explicitly deferred.

---

## Location Model

All Pops and notable mortals always reside in a PopLocation, a sub-location of a SignificantLocation. There are no mortals "on a planet" (which is a SignificantLocation) in a generic sense — they are always in a specific sub-location (the PopLocation) attached to that planet.

**Surface** is a default PopLocation with `distance_from_core = 0` (hereby referred to as simply `distance`) that every SignificantLocation has. This represents the accessible, inhabited surface (e.g., of a planet) and serves as the baseline from which all PopLocations are measured.

Every PopLocation has a `distance` integer representing how remote, hidden, or difficult to access it is relative to Surface, considering the level of civilizational development there. Examples:

| Sub-location | Distance |
|---|---|
| Surface | 0 |
| Capital District | 0 |
| Highland Settlement | 2 |
| Ancient Forest | 3 |
| Abyssal Forge | 8 |

---

## Travel Time Formula

Travel between two PopLocations within the same SignificantLocation takes:

```
travel_ticks = distance_between + 1
```

`distance_between` is the sum of the starting and ending PopLocations' `distance` values.

The `+1` represents base overhead for leaving the Planet Surface context — even travel between two distance-0 sub-locations (e.g., from one part of the planet surface to another) takes 1 tick.

**Waiver**: When traveling between two PopLocations where both have `distance > 0`, the `+1` may be waived:

```
travel_ticks = distance_between
```

The rationale: if the mortal is already in a remote location, they have already paid the overhead of leaving civilized territory. Traveling between two wilderness areas should not require a conceptual return to baseline.

---

## Agent: Travel Intent

A mortal can be given a travel intent, which is an agent state indicating that the mortal wants to move to a specific PopLocation. Each tick, the agent evaluates whether to act on this intent.

**Fields:**
- `destination`: target PopLocation
- `ticks_remaining`: countdown to arrival
- `in_transit`: bool, set to True once movement has begun

**Behavior:**
- When the mortal decides to travel, `in_transit` is set to True and `ticks_remaining` is set to the travel time formula result
- Each tick, `ticks_remaining` decrements by 1
- When `ticks_remaining` reaches 0, the mortal's PopLocation is updated to the destination and the travel intent is cleared

---

## Movement Action

A new action — tentatively **Travel** — allows a mortal agent to move between PopLocations. This action:

- Sets the mortal's travel intent
- Initiates the tick countdown
- Marks the mortal as in-transit for the duration

For now, during transit, the mortal is considered to be at their origin PopLocation for most purposes until arrival. (In the future, we may instantiate a temporary TravelLocation—a subclass of PopLocation—attached to both the origin and the destination that the mortal is placed in for resolving scrying actions, targeting, determining which Pops or other mortals are "nearby," etc. — can be refined later.)

---

## Initial Test Implementation

To validate the system before building autonomous decision logic:

- One specific NPC (Karath Omn in the Warden's Compact scenario) will be hardcoded with a travel intent that causes them to move between two PopLocations — Neran Orbital Ring (`distance_from_core` of 2) and Neran Surface (0)
- Each tick, the NPC evaluates whether to travel to the other PopLocation (or return)
- This produces observable, predictable movement that can be verified in-game

**Dev mode display**: A mortal's info tab in dev mode will show their current travel intent and countdown, e.g.:

```
Traveling → Ancient Forest | 2 ticks remaining
```

This confirms that the agent state is being read correctly, the tick countdown is functioning, and the destination is resolving before any autonomous decision logic is built on top.

---

## Future Extensions (Out of Scope for Now)

- **Inter-world travel**: SignificantLocations already have a `CosmicCoordinates` component used for scrying. Travel time between worlds will eventually be derived from the distance between two CosmicCoordinates sets, likely weighted by the civilization's travel/transport tech level, if the latter allows for it at all.
- **Autonomous travel decisions**: Mortals deciding to travel based on goals, knowledge state, and opportunities — the foundation for the emergent agent behavior described in scenario planning.
- **Travel constraints**: Luminary or scenario constraints governing where Proxiī may or may not be directed to travel.
- **In-transit events**: Things that can happen to a mortal while traveling between PopLocations.
