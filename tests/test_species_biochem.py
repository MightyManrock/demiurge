import pytest
from core.universe_core import Species, LifeBasis, Solvent, SpeciesCondition


def _make_species(**kwargs) -> Species:
    defaults = dict(
        name="Test",
        lifespan_min=50.0,
        lifespan_max=100.0,
        condition=SpeciesCondition.STABLE,
    )
    defaults.update(kwargs)
    return Species(**defaults)


# ── LifeBasis enum ──────────────────────────────────────────────────────────

def test_life_basis_values():
    assert LifeBasis.CARBON.value == "carbon"
    assert LifeBasis.SILICON.value == "silicon"
    assert LifeBasis.METHANE.value == "methane"


def test_solvent_values():
    assert Solvent.WATER.value == "water"
    assert Solvent.AMMONIA.value == "ammonia"
    assert Solvent.METHANE.value == "methane"
    assert Solvent.SULFURIC_ACID.value == "sulfuric_acid"


# ── Species defaults ────────────────────────────────────────────────────────

def test_species_defaults_to_carbon_water():
    sp = _make_species()
    assert sp.life_basis == LifeBasis.CARBON
    assert sp.solvent == Solvent.WATER


def test_species_explicit_silicon_sulfuric_acid():
    sp = _make_species(life_basis=LifeBasis.SILICON, solvent=Solvent.SULFURIC_ACID)
    assert sp.life_basis == LifeBasis.SILICON
    assert sp.solvent == Solvent.SULFURIC_ACID


def test_species_explicit_methane_ammonia():
    sp = _make_species(life_basis=LifeBasis.METHANE, solvent=Solvent.AMMONIA)
    assert sp.life_basis == LifeBasis.METHANE
    assert sp.solvent == Solvent.AMMONIA


from core.agent_core import Resource, CollectibleResource, species_can_consume


# ── biochem_tags defaults ───────────────────────────────────────────────────

def test_resource_biochem_tags_default_empty():
    r = Resource(resource_type="credits")
    assert r.biochem_tags == []


def test_collectible_resource_biochem_tags_default_empty():
    cr = CollectibleResource()
    assert cr.biochem_tags == []


# ── species_can_consume ─────────────────────────────────────────────────────

def _carbon_water() -> Species:
    return _make_species(life_basis=LifeBasis.CARBON, solvent=Solvent.WATER)


def _silicon_sulfuric() -> Species:
    return _make_species(life_basis=LifeBasis.SILICON, solvent=Solvent.SULFURIC_ACID)


def _methane_ammonia() -> Species:
    return _make_species(life_basis=LifeBasis.METHANE, solvent=Solvent.AMMONIA)


def test_inert_resource_not_consumable():
    r = Resource(resource_type="inert_carbon", biochem_tags=[])
    assert species_can_consume(_carbon_water(), r) is False


def test_carbon_water_consumes_organic_flora():
    r = Resource(resource_type="organic_flora", biochem_tags=["basis:carbon", "solvent:water"])
    assert species_can_consume(_carbon_water(), r) is True


def test_carbon_water_consumes_potable_water():
    r = Resource(resource_type="potable_water", biochem_tags=["solvent:water"])
    assert species_can_consume(_carbon_water(), r) is True


def test_carbon_water_cannot_consume_silicate_flora():
    r = Resource(resource_type="silicate_flora", biochem_tags=["basis:silicon", "solvent:sulfuric_acid"])
    assert species_can_consume(_carbon_water(), r) is False


def test_silicon_sulfuric_consumes_silicate_flora():
    r = Resource(resource_type="silicate_flora", biochem_tags=["basis:silicon", "solvent:sulfuric_acid"])
    assert species_can_consume(_silicon_sulfuric(), r) is True


def test_silicon_sulfuric_cannot_consume_organic_flora():
    r = Resource(resource_type="organic_flora", biochem_tags=["basis:carbon", "solvent:water"])
    assert species_can_consume(_silicon_sulfuric(), r) is False


def test_methane_ammonia_consumes_methane_flora():
    r = Resource(resource_type="methane_flora", biochem_tags=["basis:methane", "solvent:ammonia"])
    assert species_can_consume(_methane_ammonia(), r) is True


def test_partial_tag_mismatch_not_consumable():
    # Carbon/water species vs a resource that needs silicon basis (even though solvent matches)
    r = Resource(resource_type="silicate_flora", biochem_tags=["basis:silicon", "solvent:water"])
    assert species_can_consume(_carbon_water(), r) is False
