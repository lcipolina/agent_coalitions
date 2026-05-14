"""Tests for deterministic validator checks."""
from src.pipeline.validation import (
    _check_lane_geometry, _check_live_load, _check_material_span,
    _check_span_to_depth, _check_support_count, _overall,
)


def test_lane_geometry_pass():
    """Test that lane geometry check passes for valid lane/deck width."""
    assert _check_lane_geometry({"lanes": 2, "deck_width_m": 12})["status"] == "pass"


def test_lane_geometry_fail():
    """Test that lane geometry check fails for too many lanes for the deck width."""
    assert _check_lane_geometry({"lanes": 6, "deck_width_m": 12})["status"] == "fail"


def test_material_span_timber_too_long():
    """Test that material span check fails for overly long timber span."""
    assert _check_material_span(
        {"primary_material": "timber", "span_layout": [{"length_m": 200}]}
    )["status"] == "fail"


def test_support_count_consistency():
    """Test that support count check passes for consistent span layout and support count."""
    spec = {"span_layout": [{"length_m": 200}] * 10, "total_length_m": 2000,
            "n_supports": 11}
    assert _check_support_count(spec)["status"] == "pass"


def test_span_to_depth_warn_zone():
    """Test that span-to-depth ratio check returns warning for borderline cases."""
    spec = {"span_layout": [{"length_m": 200}], "structural_depth_m": 9.0}
    # ratio 200/9 ~= 22 → outside [8,18] but inside [4,30] → warning
    assert _check_span_to_depth(spec)["status"] == "warning"


def test_overall_status_aggregation():
    """Test overall status aggregation for pass, warning, and fail combinations."""
    assert _overall([{"status": "pass"}, {"status": "warning"}]) == "conceptual_pass_with_warnings"
    assert _overall([{"status": "pass"}, {"status": "fail"}]) == "conceptual_fail"
    assert _overall([{"status": "pass"}, {"status": "pass"}]) == "conceptual_pass"


def test_live_load_arithmetic_value():
    """Test that live load arithmetic value is computed correctly."""
    spec = {"design_live_load_kN_per_m": 12, "deck_width_m": 12, "total_length_m": 2000}
    out = _check_live_load(spec)
    assert out["value"] == 12 * 12 * 2000
