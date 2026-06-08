"""Tests for ResourceStockpile, CargoStockpile, Band, and MortalInventory capacity."""
import pytest
from unittest.mock import MagicMock
from uuid import uuid4


# ── Helpers ───────────────────────────────────────────────────────────────────

def _entity(faction_ids=None, band_id=None):
    e = MagicMock()
    e.faction_ids = [uuid4() if f is True else f for f in (faction_ids or [])]
    e.band_id = band_id
    return e


# ── can_access_stockpile ──────────────────────────────────────────────────────

class TestCanAccessStockpile:
    def test_public_stockpile_allows_anyone(self):
        from core.agent_core import ResourceStockpile, can_access_stockpile
        s = ResourceStockpile()
        assert can_access_stockpile(_entity(), s) is True

    def test_faction_owned_allows_matching_member(self):
        from core.agent_core import ResourceStockpile, can_access_stockpile
        fid = uuid4()
        s = ResourceStockpile(owner_faction_id=fid)
        assert can_access_stockpile(_entity(faction_ids=[fid]), s) is True

    def test_faction_owned_blocks_non_member(self):
        from core.agent_core import ResourceStockpile, can_access_stockpile
        s = ResourceStockpile(owner_faction_id=uuid4())
        assert can_access_stockpile(_entity(faction_ids=[uuid4()]), s) is False

    def test_faction_owned_blocks_entity_with_no_factions(self):
        from core.agent_core import ResourceStockpile, can_access_stockpile
        s = ResourceStockpile(owner_faction_id=uuid4())
        assert can_access_stockpile(_entity(), s) is False

    def test_band_owned_allows_matching_member(self):
        from core.agent_core import ResourceStockpile, can_access_stockpile
        bid = uuid4()
        s = ResourceStockpile(owner_band_id=bid)
        assert can_access_stockpile(_entity(band_id=bid), s) is True

    def test_band_owned_blocks_non_member(self):
        from core.agent_core import ResourceStockpile, can_access_stockpile
        s = ResourceStockpile(owner_band_id=uuid4())
        assert can_access_stockpile(_entity(band_id=uuid4()), s) is False

    def test_band_owned_blocks_entity_with_no_band(self):
        from core.agent_core import ResourceStockpile, can_access_stockpile
        s = ResourceStockpile(owner_band_id=uuid4())
        assert can_access_stockpile(_entity(), s) is False

    def test_either_owner_condition_is_sufficient(self):
        """An entity matching via band can access a faction+band stockpile even without faction membership."""
        from core.agent_core import ResourceStockpile, can_access_stockpile
        bid = uuid4()
        s = ResourceStockpile(owner_faction_id=uuid4(), owner_band_id=bid)
        assert can_access_stockpile(_entity(band_id=bid), s) is True

    def test_faction_match_sufficient_when_band_also_set(self):
        from core.agent_core import ResourceStockpile, can_access_stockpile
        fid = uuid4()
        s = ResourceStockpile(owner_faction_id=fid, owner_band_id=uuid4())
        assert can_access_stockpile(_entity(faction_ids=[fid]), s) is True


# ── MortalInventory capacity ──────────────────────────────────────────────────

class TestMortalInventoryCapacity:
    def test_add_resource_below_capacity_succeeds_fully(self):
        from core.agent_core import MortalInventory
        inv = MortalInventory(max_slots=4, slot_capacity=10.0)
        added = inv.add_resource("food_flora", 5.0)
        assert added == 5.0
        assert inv.get_resource("food_flora").quantity == 5.0

    def test_add_resource_capped_at_slot_capacity(self):
        from core.agent_core import MortalInventory
        inv = MortalInventory(max_slots=4, slot_capacity=10.0)
        inv.add_resource("food_flora", 8.0)
        added = inv.add_resource("food_flora", 5.0)  # would reach 13, capped at 10
        assert added == 2.0
        assert inv.get_resource("food_flora").quantity == 10.0

    def test_add_resource_slot_full_returns_zero(self):
        from core.agent_core import MortalInventory
        inv = MortalInventory(max_slots=4, slot_capacity=10.0)
        inv.add_resource("food_flora", 10.0)
        added = inv.add_resource("food_flora", 1.0)
        assert added == 0.0

    def test_add_new_resource_type_blocked_when_slots_full(self):
        from core.agent_core import MortalInventory
        inv = MortalInventory(max_slots=2, slot_capacity=10.0)
        inv.add_resource("food_flora", 1.0)
        inv.add_resource("potable_water", 1.0)
        added = inv.add_resource("food_fauna", 1.0)  # 3rd type, max_slots=2
        assert added == 0.0
        assert inv.get_resource("food_fauna") is None

    def test_add_existing_type_not_blocked_by_slot_count(self):
        from core.agent_core import MortalInventory
        inv = MortalInventory(max_slots=2, slot_capacity=10.0)
        inv.add_resource("food_flora", 1.0)
        inv.add_resource("potable_water", 1.0)
        added = inv.add_resource("food_flora", 2.0)  # existing type, slots full but OK
        assert added == 2.0

    def test_no_capacity_limits_by_default_for_backwards_compat(self):
        """Existing code that doesn't set limits should not be broken."""
        from core.agent_core import MortalInventory
        inv = MortalInventory()  # max_slots and slot_capacity default to None/unlimited
        for i in range(10):
            inv.add_resource(f"resource_{i}", 1000.0)
        assert len(inv.items) == 10
        assert inv.get_resource("resource_0").quantity == 1000.0


# ── CargoStockpile transfer functions ─────────────────────────────────────────

class TestCargoTransfer:
    def _cargo(self, max_slots=4, slot_capacity=20.0, **quantities):
        from core.agent_core import CargoStockpile
        c = CargoStockpile(max_slots=max_slots, slot_capacity=slot_capacity)
        c.quantities = dict(quantities)
        return c

    def _stockpile(self, **quantities):
        from core.agent_core import ResourceStockpile
        s = ResourceStockpile(quantities=dict(quantities))
        return s

    def test_load_cargo_basic(self):
        from core.agent_core import load_cargo
        cargo = self._cargo()
        stockpile = self._stockpile(food_flora=10.0)
        transferred = load_cargo(cargo, stockpile, "food_flora", 5.0)
        assert transferred == 5.0
        assert cargo.quantities["food_flora"] == 5.0
        assert stockpile.quantities["food_flora"] == 5.0

    def test_load_cargo_limited_by_stockpile_quantity(self):
        from core.agent_core import load_cargo
        cargo = self._cargo()
        stockpile = self._stockpile(food_flora=3.0)
        transferred = load_cargo(cargo, stockpile, "food_flora", 10.0)
        assert transferred == 3.0
        assert stockpile.quantities["food_flora"] == 0.0

    def test_load_cargo_limited_by_cargo_slot_capacity(self):
        from core.agent_core import load_cargo
        cargo = self._cargo(slot_capacity=5.0, food_flora=4.0)
        stockpile = self._stockpile(food_flora=10.0)
        transferred = load_cargo(cargo, stockpile, "food_flora", 5.0)
        assert transferred == 1.0
        assert cargo.quantities["food_flora"] == 5.0

    def test_load_cargo_blocked_when_cargo_slots_full(self):
        from core.agent_core import load_cargo
        cargo = self._cargo(max_slots=1, food_flora=1.0)
        stockpile = self._stockpile(potable_water=10.0)
        transferred = load_cargo(cargo, stockpile, "potable_water", 5.0)
        assert transferred == 0.0

    def test_unload_cargo_basic(self):
        from core.agent_core import unload_cargo
        cargo = self._cargo(food_flora=8.0)
        stockpile = self._stockpile(food_flora=2.0)
        transferred = unload_cargo(cargo, stockpile, "food_flora", 5.0)
        assert transferred == 5.0
        assert cargo.quantities["food_flora"] == 3.0
        assert stockpile.quantities["food_flora"] == 7.0

    def test_unload_cargo_limited_by_cargo_quantity(self):
        from core.agent_core import unload_cargo
        cargo = self._cargo(food_flora=2.0)
        stockpile = self._stockpile()
        transferred = unload_cargo(cargo, stockpile, "food_flora", 10.0)
        assert transferred == 2.0
        assert cargo.quantities.get("food_flora", 0.0) == 0.0


# ── Band model ────────────────────────────────────────────────────────────────

class TestBand:
    def test_band_instantiates_with_defaults(self):
        from core.universe_core import Band
        b = Band(label="Dunes of Tor")
        assert b.label == "Dunes of Tor"
        assert b.pop_ids == []
        assert b.mortal_ids == []
        assert b.id is not None

    def test_pop_has_band_id_field(self):
        from core.universe_core import Pop
        p = Pop.__fields__ if hasattr(Pop, "__fields__") else Pop.model_fields
        assert "band_id" in p

    def test_mortal_has_band_id_field(self):
        from core.universe_core import NotableMortal
        fields = NotableMortal.__fields__ if hasattr(NotableMortal, "__fields__") else NotableMortal.model_fields
        assert "band_id" in fields


# ── PopLocation.stockpiles migration ─────────────────────────────────────────

class TestPopLocationStockpiles:
    def test_stockpiles_field_exists(self):
        from core.universe_core import PopLocation
        loc = PopLocation(name="Test", location_type="pop_location")
        assert hasattr(loc, "stockpiles")
        assert isinstance(loc.stockpiles, list)

    def test_old_resource_stockpile_kwarg_migrates(self):
        """Construction with resource_stockpile= still works via model_validator."""
        from core.universe_core import PopLocation
        loc = PopLocation(
            name="Test", location_type="pop_location",
            resource_stockpile={"food_flora": 5.0},
        )
        assert loc.resource_stockpile.get("food_flora") == 5.0

    def test_resource_stockpile_property_reads_public_stockpile(self):
        from core.universe_core import PopLocation
        from core.agent_core import ResourceStockpile
        loc = PopLocation(name="Test", location_type="pop_location")
        loc.stockpiles.append(ResourceStockpile(quantities={"food_flora": 7.0}))
        assert loc.resource_stockpile["food_flora"] == 7.0

    def test_resource_stockpile_property_is_mutable(self):
        """Writes via the shim property propagate back to the stockpile."""
        from core.universe_core import PopLocation
        loc = PopLocation(name="Test", location_type="pop_location")
        loc.resource_stockpile["food_flora"] = 3.0
        assert loc.stockpiles[0].quantities["food_flora"] == 3.0
