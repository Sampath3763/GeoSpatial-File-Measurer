"""Pure unit-conversion functions for GIS measurements.

All conversions are stateless and carry no web, database, or file-system
dependencies, satisfying the Single Responsibility Principle.

Supported area units  : sq_m, sq_km, sq_ft, sq_mi, hectares, acres
Supported length units: m, km, ft, mi, nautical_miles
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# Enumeration types
# ---------------------------------------------------------------------------


class AreaUnit(str, Enum):
    """Canonical area unit identifiers accepted by the API."""

    SQ_M = "sq_m"
    SQ_KM = "sq_km"
    SQ_FT = "sq_ft"
    SQ_MI = "sq_mi"
    HECTARES = "hectares"
    ACRES = "acres"


class LengthUnit(str, Enum):
    """Canonical length unit identifiers accepted by the API."""

    M = "m"
    KM = "km"
    FT = "ft"
    MI = "mi"
    NAUTICAL_MILES = "nautical_miles"


# ---------------------------------------------------------------------------
# Conversion tables (factors relative to the SI base unit)
# ---------------------------------------------------------------------------

_AREA_FACTORS: dict[AreaUnit, float] = {
    AreaUnit.SQ_M: 1.0,
    AreaUnit.SQ_KM: 1e-6,
    AreaUnit.SQ_FT: 10.763_910_417,
    AreaUnit.SQ_MI: 3.861_021_585e-7,
    AreaUnit.HECTARES: 1e-4,
    AreaUnit.ACRES: 2.471_053_815e-4,
}

_LENGTH_FACTORS: dict[LengthUnit, float] = {
    LengthUnit.M: 1.0,
    LengthUnit.KM: 1e-3,
    LengthUnit.FT: 3.280_839_895,
    LengthUnit.MI: 6.213_711_922e-4,
    LengthUnit.NAUTICAL_MILES: 5.399_568_035e-4,
}

# Human-readable labels for each unit (used in PDF/JSON output)
_AREA_LABELS: dict[AreaUnit, str] = {
    AreaUnit.SQ_M: "m2",
    AreaUnit.SQ_KM: "km2",
    AreaUnit.SQ_FT: "ft2",
    AreaUnit.SQ_MI: "mi2",
    AreaUnit.HECTARES: "ha",
    AreaUnit.ACRES: "ac",
}

_LENGTH_LABELS: dict[LengthUnit, str] = {
    LengthUnit.M: "m",
    LengthUnit.KM: "km",
    LengthUnit.FT: "ft",
    LengthUnit.MI: "mi",
    LengthUnit.NAUTICAL_MILES: "NM",
}


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ConvertedArea:
    """Area expressed in every requested unit."""

    primary_unit: AreaUnit
    values: dict[str, float] = field(default_factory=dict)

    def primary_value(self) -> float | None:
        """Return the value in the primary requested unit."""
        return self.values.get(self.primary_unit.value)


@dataclass(slots=True)
class ConvertedLength:
    """Length expressed in every requested unit."""

    primary_unit: LengthUnit
    values: dict[str, float] = field(default_factory=dict)

    def primary_value(self) -> float | None:
        """Return the value in the primary requested unit."""
        return self.values.get(self.primary_unit.value)


# ---------------------------------------------------------------------------
# Public conversion functions
# ---------------------------------------------------------------------------


def convert_area(
    area_sq_m: float,
    units: list[AreaUnit] | None = None,
    precision: int = 6,
) -> ConvertedArea:
    """Convert area_sq_m into each requested unit.

    Parameters
    ----------
    area_sq_m:
        Source area in square metres (the canonical storage unit).
    units:
        List of target AreaUnit values. Defaults to all units when None.
    precision:
        Number of decimal places to round each converted value to.
    """
    target_units: list[AreaUnit] = units or list(AreaUnit)
    primary = target_units[0] if target_units else AreaUnit.SQ_M
    values: dict[str, float] = {
        u.value: round(area_sq_m * _AREA_FACTORS[u], precision) for u in target_units
    }
    return ConvertedArea(primary_unit=primary, values=values)


def convert_length(
    length_m: float,
    units: list[LengthUnit] | None = None,
    precision: int = 6,
) -> ConvertedLength:
    """Convert length_m into each requested unit.

    Parameters
    ----------
    length_m:
        Source length in metres (the canonical storage unit).
    units:
        List of target LengthUnit values. Defaults to all units when None.
    precision:
        Number of decimal places to round each converted value to.
    """
    target_units: list[LengthUnit] = units or list(LengthUnit)
    primary = target_units[0] if target_units else LengthUnit.M
    values: dict[str, float] = {
        u.value: round(length_m * _LENGTH_FACTORS[u], precision) for u in target_units
    }
    return ConvertedLength(primary_unit=primary, values=values)


def area_label(unit: AreaUnit) -> str:
    """Return the display label (e.g. 'ha') for unit."""
    return _AREA_LABELS[unit]


def length_label(unit: LengthUnit) -> str:
    """Return the display label (e.g. 'km') for unit."""
    return _LENGTH_LABELS[unit]


def build_full_area_breakdown(area_sq_m: float) -> dict[str, Any]:
    """Return a JSON-serialisable breakdown across every area unit."""
    converted = convert_area(area_sq_m, list(AreaUnit))
    return {
        unit_str: {
            "value": val,
            "label": _AREA_LABELS[AreaUnit(unit_str)],
        }
        for unit_str, val in converted.values.items()
    }


def build_full_length_breakdown(length_m: float) -> dict[str, Any]:
    """Return a JSON-serialisable breakdown across every length unit."""
    converted = convert_length(length_m, list(LengthUnit))
    return {
        unit_str: {
            "value": val,
            "label": _LENGTH_LABELS[LengthUnit(unit_str)],
        }
        for unit_str, val in converted.values.items()
    }
