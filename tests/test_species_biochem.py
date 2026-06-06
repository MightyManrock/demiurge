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
