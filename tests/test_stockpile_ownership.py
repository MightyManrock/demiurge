"""Tests for Phase 2.61 — _tick_stockpile_ownership transitions."""
import pytest
from unittest.mock import MagicMock
from uuid import uuid4, UUID

from core.agent_core import ResourceStockpile
from core.universe_core import PopLocation, Faction
from logic.tick_logic import TickLoop, SimulationState


# ─── helpers ──────────────────────────────────────────────────────────────────

def _make_state(locs=None, pops=None, mortals=None, factions=None):
    state = MagicMock(spec=SimulationState)
    state.locations = locs or {}
    state.pops = pops or {}
    state.mortals = mortals or {}
    state.factions = factions or {}
    return state


def _make_pop(loc_id, faction_ids=None, band_id=None):
    pop = MagicMock()
    pop.current_location = loc_id
    pop.faction_ids = faction_ids or []
    pop.band_id = band_id
    return pop


def _make_mortal(loc_id, faction_ids=None, band_id=None):
    m = MagicMock()
    m.current_location = loc_id
    m.faction_ids = faction_ids or []
    m.band_id = band_id
    return m


def _make_loc(stockpiles=None):
    loc = PopLocation(name="Test", location_type="pop_location")
    if stockpiles:
        loc.stockpiles = stockpiles
    return loc


def _loop():
    loop = MagicMock(spec=TickLoop)
    loop._tick_stockpile_ownership = TickLoop._tick_stockpile_ownership.__get__(loop, TickLoop)
    return loop


# ─── Rule 1: band leaves → band stockpile converts to public ─────────────────

def test_band_stockpile_releases_when_band_absent():
    band_id = uuid4()
    stk = ResourceStockpile(owner_band_id=band_id, quantities={"food_flora": 5.0})
    loc = _make_loc([stk])
    loc_id = str(loc.id)

    # No pops at this location
    state = _make_state(locs={loc_id: loc})

    _loop()._tick_stockpile_ownership(state)

    assert stk.owner_band_id is None
    assert stk.owner_faction_id is None


def test_band_stockpile_kept_when_band_present():
    band_id = uuid4()
    stk = ResourceStockpile(owner_band_id=band_id, quantities={"food_flora": 5.0})
    loc = _make_loc([stk])
    loc_id = str(loc.id)

    pop = _make_pop(loc_id, band_id=band_id)
    state = _make_state(locs={loc_id: loc}, pops={"p1": pop})

    _loop()._tick_stockpile_ownership(state)

    assert stk.owner_band_id == band_id


# ─── Rule 2: faction leaves home → faction stockpile converts to public ──────

def test_faction_stockpile_releases_at_home_when_faction_absent():
    faction_id = uuid4()
    loc = _make_loc()
    loc_id = str(loc.id)

    faction = Faction(id=faction_id, name="Test Faction", home_location_id=loc.id)
    stk = ResourceStockpile(owner_faction_id=faction_id, quantities={"potable_water": 4.0})
    loc.stockpiles = [stk]

    state = _make_state(locs={loc_id: loc}, factions={str(faction_id): faction})

    _loop()._tick_stockpile_ownership(state)

    assert stk.owner_faction_id is None


def test_faction_stockpile_not_released_at_non_home():
    """A faction-owned stockpile at a location that is NOT the faction's home is not released."""
    faction_id = uuid4()
    other_loc_id = uuid4()
    loc = _make_loc()
    loc_id = str(loc.id)

    faction = Faction(id=faction_id, name="Test Faction", home_location_id=other_loc_id)
    stk = ResourceStockpile(owner_faction_id=faction_id, quantities={"potable_water": 4.0})
    loc.stockpiles = [stk]

    state = _make_state(locs={loc_id: loc}, factions={str(faction_id): faction})

    _loop()._tick_stockpile_ownership(state)

    assert stk.owner_faction_id == faction_id  # unchanged


# ─── Merge: multiple public stockpiles merge after release ───────────────────

def test_public_stockpiles_merge_after_release():
    band_id = uuid4()
    stk_band = ResourceStockpile(owner_band_id=band_id, quantities={"food_flora": 3.0, "potable_water": 1.0})
    stk_public = ResourceStockpile(quantities={"food_flora": 2.0, "salt_mineral": 0.5})
    loc = _make_loc([stk_band, stk_public])
    loc_id = str(loc.id)

    state = _make_state(locs={loc_id: loc})

    _loop()._tick_stockpile_ownership(state)

    # Both stockpiles now public; should be merged into one
    assert len(loc.stockpiles) == 1
    merged = loc.stockpiles[0]
    assert merged.owner_band_id is None
    assert merged.owner_faction_id is None
    assert merged.quantities["food_flora"] == pytest.approx(5.0)
    assert merged.quantities["potable_water"] == pytest.approx(1.0)
    assert merged.quantities["salt_mineral"] == pytest.approx(0.5)


# ─── Rule 3: band sole-occupancy → claims public ─────────────────────────────

def test_band_claims_public_when_sole_occupant():
    band_id = uuid4()
    stk = ResourceStockpile(quantities={"potable_water": 2.0})
    loc = _make_loc([stk])
    loc_id = str(loc.id)

    pop = _make_pop(loc_id, band_id=band_id)
    state = _make_state(locs={loc_id: loc}, pops={"p1": pop})

    _loop()._tick_stockpile_ownership(state)

    assert stk.owner_band_id == band_id


def test_band_does_not_claim_when_non_band_pop_present():
    band_id = uuid4()
    stk = ResourceStockpile(quantities={"potable_water": 2.0})
    loc = _make_loc([stk])
    loc_id = str(loc.id)

    band_pop = _make_pop(loc_id, band_id=band_id)
    other_pop = _make_pop(loc_id, band_id=None)  # independent pop
    state = _make_state(locs={loc_id: loc}, pops={"p1": band_pop, "p2": other_pop})

    _loop()._tick_stockpile_ownership(state)

    assert stk.owner_band_id is None


def test_band_does_not_claim_at_faction_home():
    """Band sole-occupancy rule does not fire at a faction's home location."""
    band_id = uuid4()
    faction_id = uuid4()
    loc = _make_loc()
    loc_id = str(loc.id)

    faction = Faction(id=faction_id, name="Test Faction", home_location_id=loc.id)
    stk = ResourceStockpile(quantities={"potable_water": 2.0})
    loc.stockpiles = [stk]

    pop = _make_pop(loc_id, faction_ids=[faction_id], band_id=band_id)
    state = _make_state(
        locs={loc_id: loc},
        pops={"p1": pop},
        factions={str(faction_id): faction},
    )

    _loop()._tick_stockpile_ownership(state)

    # Faction home rule fires instead: stockpile becomes faction-owned
    assert stk.owner_faction_id == faction_id
    assert stk.owner_band_id is None


# ─── Rule 4: faction member at home → claims public ──────────────────────────

def test_faction_member_claims_public_at_home():
    faction_id = uuid4()
    loc = _make_loc()
    loc_id = str(loc.id)

    faction = Faction(id=faction_id, name="Test Faction", home_location_id=loc.id)
    stk = ResourceStockpile(quantities={"potable_water": 4.0})
    loc.stockpiles = [stk]

    pop = _make_pop(loc_id, faction_ids=[faction_id])
    state = _make_state(
        locs={loc_id: loc},
        pops={"p1": pop},
        factions={str(faction_id): faction},
    )

    _loop()._tick_stockpile_ownership(state)

    assert stk.owner_faction_id == faction_id
    assert stk.owner_band_id is None


def test_faction_does_not_claim_at_non_home():
    faction_id = uuid4()
    other_loc_id = uuid4()
    loc = _make_loc()
    loc_id = str(loc.id)

    faction = Faction(id=faction_id, name="Test Faction", home_location_id=other_loc_id)
    stk = ResourceStockpile(quantities={"potable_water": 4.0})
    loc.stockpiles = [stk]

    pop = _make_pop(loc_id, faction_ids=[faction_id])
    state = _make_state(
        locs={loc_id: loc},
        pops={"p1": pop},
        factions={str(faction_id): faction},
    )

    _loop()._tick_stockpile_ownership(state)

    assert stk.owner_faction_id is None
