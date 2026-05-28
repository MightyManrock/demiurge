> **Status:** complete
> **TO-DO ref:** Warp gate world expansion
> **Last updated:** 2026-05-22

## Goal

Expand the Neran→Sethis travel route to run through real FTL infrastructure: warp gates (or hyperlane nodes) as proper `SignificantLocation` entries in both systems. This makes the route topology physically grounded, gives the leg cost formula meaningful coordinates to work with, and sets up these locations as future sites of activity (garrisons, smugglers, incidents).

Prerequisite: `travel-network-refactor.md` must be complete.

## Approach

### Phase 1 — Coordinate assignment

- Assign `CosmicCoordinates` to Neran and Sethis that reflect their actual separation (they are in different systems in the same galaxy, or different galaxies — confirm with scenario lore)
- These coordinates feed the leg cost formula at the inter-system or inter-galaxy divergence level

### Phase 2 — New SignificantLocations

Add two warp gate / hyperlane `SignificantLocation` entries to `wardens_compact.db`:
- **Ardent Gate** (Neran system) — at the outer edge of the Neran system; assign CosmicCoordinates accordingly
- **Velar Corridor Gate** (Sethis system, or shared corridor) — paired with Ardent Gate; assign matching coordinates

Names are working names — confirm with Canary before injection.

Each warp gate gets at least one `PopLocation` child (e.g. "Ardent Gate Docking Bay") so it can participate in TravelNetworks.

### Phase 3 — New TravelNetworks

Add networks for the new legs (extends the set from `travel-network-refactor.md`):
- **Neran Sublight** — members: [Neran Orbital Ring, Ardent Gate Docking Bay]
- **Ardent FTL Corridor** — members: [Ardent Gate Docking Bay, Velar Corridor Gate Docking Bay]
- **Sethis Sublight** — members: [Velar Corridor Gate Docking Bay, Sethis Orbital Station]

Remove the old "Ardent Commercial Port" network that directly connected Neran Orbital Ring to Sethis Orbital Station.

### Full route after expansion

Neran Surface → Neran Orbital Ring → Ardent Gate → Velar Corridor Gate → Sethis Orbital Station → Sethis Surface

5 legs. Tick counts depend on CosmicCoordinates assigned in Phase 1; the FTL leg will dominate.

### Phase 4 — Validation

- Update `vail_travel_test.py` expected route (update docstring and PASS assertions if any reference specific waypoint names)
- Run autoplay: Vail completes the new route, PASS

## Files affected

- `scenarios/wardens_compact.db` — new SignificantLocations + PopLocations for warp gates; updated CosmicCoordinates for Neran/Sethis; new and updated TravelNetworks
- `autoplay/strategies/vail_travel_test.py` — update docstring with new expected route and tick count

## Notes

- Prerequisite: `travel-network-refactor.md` (active)
- Status is `parked` until the TravelNetwork refactor is complete and validated
- Naming (Ardent Gate, Velar Corridor Gate) should be confirmed with Canary before DB injection — the names will show up in TravelLocation display
- Leg cost for the FTL hop is determined automatically by CosmicCoordinates divergence; no hardcoding needed
- These locations can eventually host events, Proxii, mortals, and constraints — the investment pays off beyond just routing
