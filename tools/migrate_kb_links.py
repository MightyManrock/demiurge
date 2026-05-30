"""
Expand Durenn Vail's KB and link the Sethis Surface trader Pop to Neran Surface.

Changes:
- Sethis Surface trader pop: occupation = "merchant"
- Bidirectional link (base=0.5): Neran Surface merchant <-> Sethis Surface merchant
- Durenn's KB: add sell quality facts for Neran Orbital Ring + Sethis Orbital Station
- Durenn's KB: correct Sethis Surface sell quality (0.2 -> 0.5, matches actual wealth)
- Durenn's KB: add bidirectional route facts Neran Surface <-> Neran Orbital Ring (2 ticks)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utilities.scenario_loader import load_scenario
from utilities.scenario_exporter import export_scenario
from core.agent_core import LocationQualityFact, RouteFact

DB = "scenarios/wardens_compact.db"

NERAN_SURFACE_ID  = "2ac3f5fc-d4fd-4d72-be5b-eada9fb43e6d"
NERAN_ORBITAL_ID  = "b6e77481-97bd-4d4f-a948-4216d22522c3"
SETHIS_ORBITAL_ID = "38474e57-8d40-4397-ade8-b9751cfa7d3c"
SETHIS_SURFACE_ID = "ef5b9dc6-de3d-46a4-a9e4-6f8e1a6b76bc"

NERAN_MERCHANT_ID = "e7b2dbfb-b9fd-4e76-b614-f84dfad25f31"


def main() -> None:
    state = load_scenario(DB)

    # ── Durenn Vail ─────────────────────────────────────────────────────────
    vail = next((m for m in state.mortals.values() if m.name == "Durenn Vail"), None)
    if vail is None:
        print("ERROR: Durenn Vail not found.")
        sys.exit(1)
    if vail.knowledge_base is None:
        print("ERROR: Durenn has no KnowledgeBase.")
        sys.exit(1)

    # ── Neran Surface merchant pop ──────────────────────────────────────────
    neran_merchant = state.pops.get(NERAN_MERCHANT_ID)
    if neran_merchant is None:
        print(f"ERROR: Neran merchant pop {NERAN_MERCHANT_ID} not found.")
        sys.exit(1)

    # ── Sethis Surface trader pop ───────────────────────────────────────────
    sethis_trader = next(
        (p for p in state.pops.values()
         if p.social_class.value == "trader"
         and str(p.current_location) == SETHIS_SURFACE_ID),
        None,
    )
    if sethis_trader is None:
        print("ERROR: Sethis Surface trader pop not found.")
        sys.exit(1)

    print(f"Sethis trader pop: {sethis_trader.id} (occupation={sethis_trader.occupation!r})")

    # 1. Sethis trader → merchant occupation
    sethis_trader.occupation = "merchant"

    # 2. Bidirectional links (base=0.5)
    neran_merchant.linked_pop_ids[str(sethis_trader.id)] = 0.5
    sethis_trader.linked_pop_ids[str(neran_merchant.id)] = 0.5
    print(f"Linked: {NERAN_MERCHANT_ID[:8]} <-> {str(sethis_trader.id)[:8]} (base=0.5)")

    # ── KB updates ──────────────────────────────────────────────────────────
    kb = vail.knowledge_base

    # 3. Correct Sethis Surface sell quality (was seeded at 0.2, actual wealth is 0.5)
    for f in kb.facts:
        if (getattr(f, "fact_type", None) == "location_quality"
                and getattr(f, "location_id", None) == SETHIS_SURFACE_ID
                and getattr(f, "quality_type", None) == "sell"):
            f.quality = 0.5
            print("Updated Sethis Surface sell quality: 0.2 -> 0.5")
            break

    # 4. Add sell quality facts for Orbital locations (if not already present)
    existing_sell_ids = {
        getattr(f, "location_id", None)
        for f in kb.facts
        if getattr(f, "fact_type", None) == "location_quality"
        and getattr(f, "quality_type", None) == "sell"
    }
    for loc_id, label in [
        (NERAN_ORBITAL_ID, "Neran Orbital Ring"),
        (SETHIS_ORBITAL_ID, "Sethis Orbital Station"),
    ]:
        if loc_id not in existing_sell_ids:
            kb.facts.append(LocationQualityFact(
                location_id=loc_id,
                quality=0.5,
                quality_type="sell",
            ))
            print(f"Added sell quality fact for {label} (quality=0.5)")

    # 5. Bidirectional route: Neran Surface <-> Neran Orbital Ring (2 ticks, no vehicle)
    existing_route_pairs = {
        (getattr(f, "from_id", None), getattr(f, "to_id", None))
        for f in kb.facts
        if getattr(f, "fact_type", None) == "route"
    }
    for from_id, to_id in [
        (NERAN_SURFACE_ID, NERAN_ORBITAL_ID),
        (NERAN_ORBITAL_ID, NERAN_SURFACE_ID),
    ]:
        if (from_id, to_id) not in existing_route_pairs:
            kb.facts.append(RouteFact(
                from_id=from_id,
                to_id=to_id,
                ticks_cost=2,
                vehicle_type=None,
            ))
            print(f"Added route: {from_id[:8]} -> {to_id[:8]} (2 ticks)")

    export_scenario(state, DB)
    print("Done.")


if __name__ == "__main__":
    main()
