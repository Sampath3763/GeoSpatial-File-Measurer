"""Tests for property and attribute normalization."""

from datetime import date

import numpy as np

from app.services.geo_reader import sanitize_properties


def test_property_keys_are_safe_and_duplicate_names_are_suffixed() -> None:
    """Periods and leading dollar signs are removed without losing fields."""
    safe, _warnings = sanitize_properties(
        {
            "a.b": 1,
            "a_b": 2,
            "$owner": "team",
            "": "empty",
        }
    )
    assert safe == {"a_b": 1, "a_b_2": 2, "owner": "team", "field": "empty"}


def test_property_values_are_bson_safe() -> None:
    """NaN, wide integers, dates, and bytes get predictable safe values."""
    safe, warnings = sanitize_properties(
        {
            "nan": float("nan"),
            "wide": 2**80,
            "date": date(2026, 1, 2),
            "bytes": b"not bson safe",
            "numpy_nan": np.float64(np.nan),
        }
    )
    assert safe["nan"] is None
    assert safe["numpy_nan"] is None
    assert safe["wide"] == str(2**80)
    assert safe["date"] == "2026-01-02"
    assert safe["bytes"] is None
    assert any("bytes" in warning for warning in warnings)


def test_nested_property_keys_are_sanitized_too() -> None:
    """Nested attribute documents are normalized recursively."""
    safe, _warnings = sanitize_properties({"nested": {"$a.b": 1, "a_b": 2}})
    assert safe == {"nested": {"a_b": 1, "a_b_2": 2}}
