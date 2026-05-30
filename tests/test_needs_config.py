import pytest
from logic.needs_config import (
    compute_need_profile,
    NEED_DEFAULTS,
    CANONICAL_NEEDS,
    NEED_LEISURE,
    NEED_BELONGING,
    NEED_SUSTENANCE,
    NEED_STATUS,
    NEED_PURPOSE,
    NEED_SAFETY,
)


def test_all_canonical_needs_present():
    needs = compute_need_profile({})
    names = {n.name for n in needs}
    assert names == set(CANONICAL_NEEDS)


def test_defaults_with_no_traits():
    needs = compute_need_profile({})
    by_name = {n.name: n for n in needs}
    for need_name, defaults in NEED_DEFAULTS.items():
        n = by_name[need_name]
        assert abs(n.decay_rate - defaults["decay_rate"]) < 1e-6
        assert abs(n.pressing_threshold - defaults["pressing_threshold"]) < 1e-6
        assert abs(n.urgent_threshold - defaults["urgent_threshold"]) < 1e-6


def test_indulgence_amplifies_leisure():
    needs = compute_need_profile({"values:indulgence": 0.8})
    by_name = {n.name: n for n in needs}
    leisure   = by_name[NEED_LEISURE]
    default_d = NEED_DEFAULTS[NEED_LEISURE]["decay_rate"]
    default_p = NEED_DEFAULTS[NEED_LEISURE]["pressing_threshold"]
    assert leisure.decay_rate     > default_d
    assert leisure.pressing_threshold > default_p


def test_moderation_suppresses_leisure():
    needs = compute_need_profile({"values:moderation": 0.8})
    by_name = {n.name: n for n in needs}
    leisure   = by_name[NEED_LEISURE]
    default_d = NEED_DEFAULTS[NEED_LEISURE]["decay_rate"]
    default_p = NEED_DEFAULTS[NEED_LEISURE]["pressing_threshold"]
    assert leisure.decay_rate         < default_d
    assert leisure.pressing_threshold < default_p


def test_autonomy_reduces_belonging():
    needs = compute_need_profile({"values:autonomy": 0.7})
    by_name = {n.name: n for n in needs}
    belonging = by_name[NEED_BELONGING]
    assert belonging.pressing_threshold < NEED_DEFAULTS[NEED_BELONGING]["pressing_threshold"]
    assert belonging.urgent_threshold   < NEED_DEFAULTS[NEED_BELONGING]["urgent_threshold"]


def test_solidarity_amplifies_belonging():
    needs = compute_need_profile({"values:solidarity": 0.8})
    by_name = {n.name: n for n in needs}
    belonging = by_name[NEED_BELONGING]
    assert belonging.pressing_threshold > NEED_DEFAULTS[NEED_BELONGING]["pressing_threshold"]


def test_threshold_invariant_urgent_less_than_pressing():
    """urgent_threshold < pressing_threshold for all needs, all trait combinations."""
    combos = [
        {},
        {"values:indulgence": 1.0},
        {"values:autonomy": 1.0, "values:solidarity": 1.0},
        {"values:prowess": 1.0, "values:humility": -0.5},
        {"values:idealism": 1.0, "values:pragmatism": -0.5},
    ]
    for tags in combos:
        for need in compute_need_profile(tags):
            assert need.urgent_threshold < need.pressing_threshold, (
                f"{need.name} with {tags}: urgent={need.urgent_threshold} "
                f">= pressing={need.pressing_threshold}"
            )


def test_threshold_clamping_bounds():
    """No threshold outside [0.05, 0.9], no decay below 0.005."""
    extreme = {
        "values:indulgence": 10.0,
        "values:solidarity": 10.0,
        "values:prowess":    10.0,
        "values:idealism":   10.0,
    }
    for need in compute_need_profile(extreme):
        assert need.decay_rate     >= 0.005
        assert need.pressing_threshold <= 0.90
        assert need.urgent_threshold   >= 0.05


def test_negative_trait_values_reduce():
    """Negative xenophilia (xenophobia) applied as a signed modifier."""
    needs_neg = compute_need_profile({"values:indulgence": -0.5})
    needs_def = compute_need_profile({})
    by_name_neg = {n.name: n for n in needs_neg}
    by_name_def = {n.name: n for n in needs_def}
    # Negative indulgence should reduce leisure decay
    assert by_name_neg[NEED_LEISURE].decay_rate < by_name_def[NEED_LEISURE].decay_rate


def test_satisfaction_always_starts_at_full():
    for need in compute_need_profile({"values:indulgence": 0.9}):
        assert need.satisfaction == 1.0
