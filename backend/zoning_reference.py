"""
Minimal NYC zoning reference data used for live property enrichment.

This ports the lightweight FAR/height/lot-coverage slice needed for
property lookup and UAP / 485-x scenario framing.
"""

from __future__ import annotations

from typing import Any, Optional


ZONE_HEIGHT_LIMITS: dict[str, dict[str, Any]] = {
    "R6A": {"Standard": 75, "UAP": 95},
    "R6-1": {"Standard": 75, "UAP": 95},
    "R6B": {"Standard": 55, "UAP": 65},
    "R6D": {"Standard": 65, "UAP": 75},
    "R6-2": {"Standard": 65, "UAP": 75},
    "R7A": {"Standard": 85, "UAP": 115},
    "R7-1": {"Narrow": {"Standard": 75, "UAP": 105}, "Wide": {"Standard": 85, "UAP": 115}},
    "R7-2": {"Narrow": {"Standard": 75, "UAP": 105}, "Wide": {"Standard": 85, "UAP": 115}},
    "R7B": {"Standard": 75, "UAP": 95},
    "R7D": {"Standard": 105, "UAP": 125},
    "R7X": {"Standard": 125, "UAP": 145},
    "R7-3": {"Standard": 125, "UAP": 145},
    "R8A": {"Standard": 125, "UAP": 145},
    "R8B": {"Standard": 75, "UAP": 95},
    "R8X": {"Standard": 155, "UAP": 175},
    "R8": {"Narrow": {"Standard": 115, "UAP": 145}, "Wide": {"Standard": 135, "UAP": 145}},
    "R9A": {"Narrow": {"Standard": 135, "UAP": 185}, "Wide": {"Standard": 145, "UAP": 185}},
    "R9D": {"Standard": 175, "UAP": 215},
    "R9-1": {"Standard": 175, "UAP": 215},
    "R9X": {"Narrow": {"Standard": 165, "UAP": 215}, "Wide": {"Standard": 175, "UAP": 215}},
    "R9": {"Narrow": {"Standard": 135, "UAP": 185}, "Wide": {"Standard": 145, "UAP": 185}},
    "R10A": {"Narrow": {"Standard": 185, "UAP": 235}, "Wide": {"Standard": 215, "UAP": 235}},
    "R10X": {"Narrow": {"Standard": 185, "UAP": 235}, "Wide": {"Standard": 215, "UAP": 235}},
    "R10": {"Narrow": {"Standard": 185, "UAP": 235}, "Wide": {"Standard": 215, "UAP": 235}},
    "R11A": {"Narrow": {"Standard": 255, "UAP": 325}, "Wide": {"Standard": 255, "UAP": 325}},
    "R11": {"Narrow": {"Standard": 255, "UAP": 325}, "Wide": {"Standard": 255, "UAP": 325}},
    "R12": {"Standard": 325, "UAP": 395},
}


ZONE_INFO: dict[str, dict[str, Any]] = {
    "R1-1": {"Density": "Low", "Standard": 0.75, "QRS": 1.00},
    "R1-2": {"Density": "Low", "Standard": 0.75, "QRS": 1.00},
    "R1-2A": {"Density": "Low", "Standard": 0.75, "QRS": 1.00},
    "R2": {"Density": "Low", "Standard": 0.75, "QRS": 1.00},
    "R2A": {"Density": "Low", "Standard": 0.75, "QRS": 1.00},
    "R2X": {"Density": "Low", "Standard": 1.00, "QRS": 1.00},
    "R3-1": {"Density": "Low", "Standard": 0.75, "QRS": 1.00},
    "R3-2": {"Density": "Low", "Standard": 0.75, "QRS": 1.00},
    "R3A": {"Density": "Low", "Standard": 0.75, "QRS": 1.00},
    "R3X": {"Density": "Low", "Standard": 0.75, "QRS": 1.00},
    "R4": {"Density": "Low", "Standard": 1.00, "QRS": 1.50},
    "R4-1": {"Density": "Low", "Standard": 1.00, "QRS": 1.50},
    "R4A": {"Density": "Low", "Standard": 1.00, "QRS": 1.50},
    "R4B": {"Density": "Low", "Standard": 1.00, "QRS": 1.50},
    "R5": {"Density": "Low", "Standard": 1.50, "QRS": 2.00},
    "R5A": {"Density": "Low", "Standard": 1.50, "QRS": 2.00},
    "R5B": {"Density": "Low", "Standard": 1.50, "QRS": 2.00},
    "R5D": {"Density": "Low", "Standard": 2.00, "QRS": 2.00},
    "R6": {"Density": "High", "Narrow": {"Standard": 2.20, "UAP": 3.90}, "Wide": {"Standard": 3.00, "UAP": 3.90}},
    "R6-1": {"Density": "High", "Standard": 3.00, "UAP": 3.90},
    "R6-2": {"Density": "High", "Standard": 2.50, "UAP": 3.00},
    "R6A": {"Density": "High", "Standard": 3.00, "UAP": 3.90},
    "R6B": {"Density": "High", "Standard": 2.00, "UAP": 2.40},
    "R6D": {"Density": "High", "Standard": 2.50, "UAP": 3.00},
    "R7-1": {"Density": "High", "Narrow": {"Standard": 3.44, "UAP": 5.01}, "Wide": {"Standard": 4.00, "UAP": 5.01}},
    "R7-2": {"Density": "High", "Narrow": {"Standard": 3.44, "UAP": 5.01}, "Wide": {"Standard": 4.00, "UAP": 5.01}},
    "R7-3": {"Density": "High", "Standard": 5.00, "UAP": 6.00},
    "R7A": {"Density": "High", "Standard": 4.00, "UAP": 5.01},
    "R7B": {"Density": "High", "Standard": 3.00, "UAP": 3.90},
    "R7D": {"Density": "High", "Standard": 4.66, "UAP": 5.60},
    "R7X": {"Density": "High", "Standard": 5.00, "UAP": 6.00},
    "R8": {"Density": "High", "Narrow": {"Standard": 6.02, "UAP": 7.20}, "Wide": {"Standard": 7.20, "UAP": 8.64}},
    "R8A": {"Density": "High", "Standard": 6.02, "UAP": 7.20},
    "R8B": {"Density": "High", "Standard": 4.00, "UAP": 4.80},
    "R8X": {"Density": "High", "Standard": 6.02, "UAP": 7.20},
    "R9": {"Density": "High", "Standard": 7.52, "UAP": 9.02},
    "R9-1": {"Density": "High", "Standard": 9.00, "UAP": 10.80},
    "R9A": {"Density": "High", "Standard": 7.52, "UAP": 9.02},
    "R9D": {"Density": "High", "Standard": 9.00, "UAP": 10.80},
    "R9X": {"Density": "High", "Standard": 9.00, "UAP": 10.80},
    "R10": {"Density": "High", "Standard": 10.00, "UAP": 12.00},
    "R10A": {"Density": "High", "Standard": 10.00, "UAP": 12.00},
    "R10X": {"Density": "High", "Standard": 10.00, "UAP": 12.00},
    "R11": {"Density": "High", "Standard": 12.50, "UAP": 15.00},
    "R12": {"Density": "High", "Standard": 15.00, "UAP": 18.00},
}


LOT_COVERAGE: dict[str, dict[str, float]] = {
    "R1-1": {"Corner": 60, "Interior": 55},
    "R1-2": {"Corner": 60, "Interior": 55},
    "R1-2A": {"Corner": 60, "Interior": 55},
    "R2": {"Corner": 60, "Interior": 55},
    "R2A": {"Corner": 60, "Interior": 55},
    "R2X": {"Corner": 60, "Interior": 55},
    "R3-1": {"Corner": 60, "Interior": 55},
    "R3-2": {"Corner": 60, "Interior": 55},
    "R3A": {"Corner": 60, "Interior": 55},
    "R3X": {"Corner": 60, "Interior": 55},
    "R4": {"Corner": 60, "Interior": 55},
    "R4-1": {"Corner": 60, "Interior": 55},
    "R4A": {"Corner": 60, "Interior": 55},
    "R4B": {"Corner": 60, "Interior": 55},
    "R5": {"Corner": 60, "Interior": 55},
    "R5A": {"Corner": 60, "Interior": 55},
    "R5B": {"Corner": 60, "Interior": 55},
    "R5D": {"Corner": 80, "Interior": 60},
    "R6A": {"Corner": 80, "Interior": 60},
    "R6B": {"Corner": 80, "Interior": 60},
    "R6D": {"Corner": 80, "Interior": 65},
    "R7A": {"Corner": 80, "Interior": 65},
    "R7B": {"Corner": 80, "Interior": 65},
    "R7D": {"Corner": 80, "Interior": 65},
    "R7X": {"Corner": 80, "Interior": 70},
    "R8A": {"Corner": 80, "Interior": 70},
    "R8B": {"Corner": 80, "Interior": 70},
    "R8X": {"Corner": 80, "Interior": 70},
    "R9A": {"Corner": 80, "Interior": 70},
    "R9D": {"Corner": 80, "Interior": 70},
    "R9X": {"Corner": 80, "Interior": 70},
    "R10A": {"Corner": 100, "Interior": 70},
    "R10X": {"Corner": 100, "Interior": 70},
    "R11A": {"Corner": 100, "Interior": 70},
    "R6": {"Corner": 70, "Interior": 65},
    "R6-1": {"Corner": 70, "Interior": 65},
    "R6-2": {"Corner": 70, "Interior": 65},
    "R7-1": {"Corner": 70, "Interior": 65},
    "R7-2": {"Corner": 70, "Interior": 65},
    "R7-3": {"Corner": 70, "Interior": 65},
    "R8": {"Corner": 75, "Interior": 65},
    "R9": {"Corner": 75, "Interior": 65},
    "R9-1": {"Corner": 75, "Interior": 65},
    "R10": {"Corner": 75, "Interior": 65},
    "R11": {"Corner": 100, "Interior": 70},
    "R12": {"Corner": 100, "Interior": 70},
}


COMMERCIAL_TO_RESIDENTIAL: dict[str, str] = {
    "C1-6": "R7-2",
    "C1-6A": "R7A",
    "C1-7": "R8",
    "C1-7A": "R8A",
    "C1-8": "R9",
    "C1-8A": "R9A",
    "C1-8X": "R9X",
    "C1-9": "R10",
    "C1-9A": "R10A",
    "C2-6": "R7-2",
    "C2-6A": "R7A",
    "C2-7": "R9",
    "C2-7A": "R9A",
    "C2-7X": "R9X",
    "C2-8": "R10",
    "C2-8A": "R10A",
    "C3": "R3-2",
    "C3A": "R3A",
    "C4-1": "R5",
    "C4-2": "R6",
    "C4-2A": "R6A",
    "C4-2F": "R8",
    "C4-3": "R6",
    "C4-3A": "R6A",
    "C4-4": "R7-2",
    "C4-4A": "R7A",
    "C4-4D": "R8A",
    "C4-4L": "R7A",
    "C4-5": "R7-2",
    "C4-5A": "R7A",
    "C4-5D": "R7D",
    "C4-5X": "R7X",
    "C4-6": "R10",
    "C4-6A": "R10A",
    "C4-7": "R10",
    "C4-7A": "R10A",
    "C4-8": "R8",
    "C4-9": "R9",
    "C4-11": "R11",
    "C4-11A": "R11A",
    "C4-12": "R12",
    "C5": "R10",
    "C5-1": "R10",
    "C5-1A": "R10A",
    "C5-2": "R10",
    "C5-2A": "R10A",
    "C5-3": "R10",
    "C5-4": "R10",
    "C5-5": "R10",
    "C6-1": "R7-2",
    "C6-1A": "R6",
    "C6-2": "R8",
    "C6-2A": "R8A",
    "C6-3": "R9",
    "C6-3A": "R9A",
    "C6-3D": "R9D",
    "C6-3X": "R9X",
    "C6-4": "R10",
    "C6-4A": "R10A",
    "C6-4X": "R10X",
    "C6-5": "R10",
    "C6-6": "R10",
    "C6-7": "R10",
    "C6-8": "R10",
    "C6-9": "R10",
    "C6-11": "R11",
    "C6-12": "R12",
}


COMMERCIAL_OVERLAY_FAR: dict[str, float] = {
    "C1-1": 1.0,
    "C1-2": 2.0,
    "C1-3": 1.0,
    "C1-4": 2.0,
    "C1-5": 1.5,
    "C2-1": 2.0,
    "C2-2": 2.0,
    "C2-3": 2.0,
    "C2-4": 2.0,
    "C2-5": 2.0,
}


COMMUNITY_FACILITY_FAR: dict[str, float] = {
    "R1-1": 1.0,
    "R1-2": 1.0,
    "R1-2A": 1.0,
    "R2": 1.0,
    "R2A": 1.0,
    "R2X": 1.0,
    "R3-1": 1.0,
    "R3-2": 1.0,
    "R3A": 1.0,
    "R3X": 1.0,
    "R4": 2.0,
    "R4-1": 2.0,
    "R4A": 2.0,
    "R4B": 2.0,
    "R5": 2.0,
    "R5A": 2.0,
    "R5B": 2.0,
    "R5D": 2.0,
    "R6": 4.8,
    "R6A": 3.0,
    "R6B": 2.0,
    "R7-1": 4.8,
    "R7-2": 4.8,
    "R7A": 4.0,
    "R7B": 3.0,
    "R7D": 4.2,
    "R7X": 5.0,
    "R8": 6.5,
    "R8A": 6.5,
    "R8B": 5.0,
    "R8X": 6.5,
    "R9": 10.0,
    "R9A": 7.5,
    "R9D": 9.0,
    "R9X": 9.0,
    "R10": 10.0,
    "R10A": 10.0,
    "R10X": 10.0,
    "R11": 10.0,
    "R11A": 10.0,
    "R12": 12.0,
}


def normalize_zone(zone: str | None) -> str:
    return str(zone or "").strip().upper()


def get_overlay_far(overlay: str | None) -> Optional[float]:
    if not overlay:
        return None
    return COMMERCIAL_OVERLAY_FAR.get(normalize_zone(overlay))


def infer_lot_type(lot_type_code: int | None) -> str:
    if lot_type_code == 3:
        return "corner"
    if lot_type_code in {1, 2, 4, 5, 6, 7, 8, 9}:
        return "interior"
    return "unknown"


def get_height_for_zone(zone: str | None, street_type: str | None = None, use_uap: bool = False) -> Optional[int]:
    zone_key = normalize_zone(zone)
    if zone_key in COMMERCIAL_TO_RESIDENTIAL:
        zone_key = COMMERCIAL_TO_RESIDENTIAL[zone_key]
    if zone_key not in ZONE_HEIGHT_LIMITS:
        return None

    height_data = ZONE_HEIGHT_LIMITS[zone_key]
    height_key = "UAP" if use_uap else "Standard"
    if "Narrow" in height_data and "Wide" in height_data:
        branch = height_data["Wide"] if str(street_type or "").strip().lower() == "wide" else height_data["Narrow"]
        value = branch.get(height_key)
    else:
        value = height_data.get(height_key)
    return int(value) if value is not None else None


def get_zoning_info(zone: str | None, street_type: str | None = None) -> Optional[dict[str, Any]]:
    original_zone = normalize_zone(zone)
    if not original_zone:
        return None

    zone_key = original_zone
    is_commercial = False
    residential_equivalent = None
    if zone_key in COMMERCIAL_TO_RESIDENTIAL:
        residential_equivalent = COMMERCIAL_TO_RESIDENTIAL[zone_key]
        zone_key = residential_equivalent
        is_commercial = True

    if zone_key not in ZONE_INFO:
        return None

    zone_info = ZONE_INFO[zone_key]
    lot_coverage = LOT_COVERAGE.get(zone_key, {})
    cf_far = COMMUNITY_FACILITY_FAR.get(zone_key)
    height_standard = get_height_for_zone(zone_key, street_type=street_type, use_uap=False)
    height_uap = get_height_for_zone(zone_key, street_type=street_type, use_uap=True)

    has_narrow_wide = "Narrow" in zone_info and "Wide" in zone_info
    if has_narrow_wide:
        resolved_street_type = "wide" if str(street_type or "").strip().lower() == "wide" else "narrow"
        branch = zone_info["Wide"] if resolved_street_type == "wide" else zone_info["Narrow"]
        return {
            "zone": original_zone,
            "residential_equivalent": residential_equivalent,
            "is_commercial": is_commercial,
            "street_type_assumption": resolved_street_type,
            "has_narrow_wide": True,
            "standard": branch.get("Standard"),
            "uap": branch.get("UAP"),
            "qrs": branch.get("QRS"),
            "cf_far": cf_far,
            "lot_coverage_corner": lot_coverage.get("Corner"),
            "lot_coverage_interior": lot_coverage.get("Interior"),
            "height_limit_standard": height_standard,
            "height_limit_uap": height_uap,
        }

    return {
        "zone": original_zone,
        "residential_equivalent": residential_equivalent,
        "is_commercial": is_commercial,
        "street_type_assumption": "n/a",
        "has_narrow_wide": False,
        "standard": zone_info.get("Standard"),
        "uap": zone_info.get("UAP"),
        "qrs": zone_info.get("QRS"),
        "cf_far": cf_far,
        "lot_coverage_corner": lot_coverage.get("Corner"),
        "lot_coverage_interior": lot_coverage.get("Interior"),
        "height_limit_standard": height_standard,
        "height_limit_uap": height_uap,
    }
