from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from openpyxl.utils.datetime import to_excel


def serialize_underwriting_cell_value(
    value: Any,
    epoch: Any,
) -> str | int | float | bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        if value != value:
            return None
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, (datetime, date, time, timedelta)):
        return to_excel(value, epoch=epoch)
    if isinstance(value, str):
        return value
    return str(value)


def normalize_underwriting_number_format(number_format: str | None) -> str | None:
    if number_format is None:
        return None
    cleaned = str(number_format).strip()
    return cleaned or None


def build_underwriting_cell_payload(
    value: Any,
    *,
    row: int,
    col: int,
    is_formula: bool,
    number_format: str | None,
    epoch: Any,
) -> dict[str, Any] | None:
    serialized_value = serialize_underwriting_cell_value(value, epoch)
    if serialized_value is None and not is_formula:
        return None

    cell_payload: dict[str, Any] = {"v": serialized_value, "r": row, "c": col}
    normalized_format = normalize_underwriting_number_format(number_format)
    if normalized_format is not None:
        cell_payload["z"] = normalized_format
    if is_formula:
        cell_payload["f"] = True
    return cell_payload
