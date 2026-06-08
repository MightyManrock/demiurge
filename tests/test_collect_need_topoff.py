"""Collecting a resource tops off the associated need immediately."""
import pytest
from core.agent_core import MortalAgentState, MortalNeed
from logic.tick_logic import _apply_resource_need_topoff


def _cs_with_hydration(sat=0.2):
    return MortalAgentState(needs=[
        MortalNeed(name="hydration", satisfaction=sat,
                   pressing_threshold=0.55, urgent_threshold=0.20, decay_rate=0.03),
        MortalNeed(name="nourishment", satisfaction=sat,
                   pressing_threshold=0.55, urgent_threshold=0.20, decay_rate=0.02),
    ])


def test_collect_potable_water_tops_off_hydration():
    cs = _cs_with_hydration(0.2)
    _apply_resource_need_topoff(cs, "potable_water")
    hydr = cs.get_need("hydration")
    assert hydr.satisfaction == 1.0
    assert hydr.satiation_hold > 0


def test_collect_potable_water_leaves_nourishment_unchanged():
    cs = _cs_with_hydration(0.2)
    _apply_resource_need_topoff(cs, "potable_water")
    nour = cs.get_need("nourishment")
    assert nour.satisfaction == pytest.approx(0.2)


def test_collect_food_flora_tops_off_nourishment():
    cs = _cs_with_hydration(0.3)
    _apply_resource_need_topoff(cs, "food_flora")
    nour = cs.get_need("nourishment")
    assert nour.satisfaction == 1.0
    assert nour.satiation_hold > 0


def test_collect_food_flora_leaves_hydration_unchanged():
    cs = _cs_with_hydration(0.3)
    _apply_resource_need_topoff(cs, "food_flora")
    hydr = cs.get_need("hydration")
    assert hydr.satisfaction == pytest.approx(0.3)


def test_collect_inert_resource_no_topoff():
    cs = _cs_with_hydration(0.4)
    _apply_resource_need_topoff(cs, "credits")
    assert cs.get_need("hydration").satisfaction == pytest.approx(0.4)
    assert cs.get_need("nourishment").satisfaction == pytest.approx(0.4)


def test_collect_unknown_resource_no_topoff():
    cs = _cs_with_hydration(0.5)
    _apply_resource_need_topoff(cs, "unobtanium")
    assert cs.get_need("hydration").satisfaction == pytest.approx(0.5)


def test_topoff_does_not_overflow():
    cs = _cs_with_hydration(0.95)
    _apply_resource_need_topoff(cs, "potable_water")
    assert cs.get_need("hydration").satisfaction == 1.0
