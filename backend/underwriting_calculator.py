from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openpyxl import Workbook


_MODEL_CELL_REF_RE = re.compile(
    r"^'\[(?P<book>[^\]]+)\](?P<sheet>.+)'!(?P<ref>\$?[A-Z]+\$?\d+(?::\$?[A-Z]+\$?\d+)?)$"
)


@dataclass
class UnderwritingFormulaWarning:
    sheet: str
    message: str
    refs: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"sheet": self.sheet, "message": self.message}
        if self.refs:
            payload["refs"] = self.refs
        return payload


@dataclass
class UnderwritingCalculationContext:
    model: Any | None
    input_nodes_by_sheet_ref: dict[str, dict[str, str]]
    formula_nodes_by_sheet_ref: dict[str, dict[str, str]]
    build_warnings: list[UnderwritingFormulaWarning] = field(default_factory=list)


def _normalize_sheet_key(sheet_name: str) -> str:
    return sheet_name.upper()


def _normalize_cell_ref(ref: str) -> str:
    return ref.replace("$", "").upper()


def _load_formula_model(workbook_path: str):
    try:
        from formulas import ExcelModel
    except Exception as exc:  # pragma: no cover - exercised via fallback behavior
        raise RuntimeError(
            "The formulas[excel] package is not available for in-app recalculation."
        ) from exc

    quiet_tqdm = ExcelModel.complete.__globals__["tqdm"].tqdm

    class QuietTqdm:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def update(self, *args, **kwargs):
            return None

        def refresh(self):
            return None

        total = 0

    ExcelModel.complete.__globals__["tqdm"].tqdm = QuietTqdm
    try:
        return ExcelModel().loads(workbook_path).finish(complete=True, circular=True)
    finally:
        ExcelModel.complete.__globals__["tqdm"].tqdm = quiet_tqdm


def _parse_model_cell_ref(node_ref: str) -> tuple[str, str] | None:
    match = _MODEL_CELL_REF_RE.match(node_ref)
    if not match:
        return None

    cell_ref = _normalize_cell_ref(match.group("ref"))
    if ":" in cell_ref:
        return None

    sheet_name = match.group("sheet").replace("''", "'")
    return _normalize_sheet_key(sheet_name), cell_ref


def _extract_scalar_value(value: Any) -> str | int | float | bool | None:
    if hasattr(value, "value"):
        value = value.value

    if hasattr(value, "tolist"):
        value = value.tolist()

    while isinstance(value, list) and len(value) == 1:
        value = value[0]

    if isinstance(value, list):
        raise ValueError("Formula output is not a scalar value.")

    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value != value:
            return None
        return value
    if isinstance(value, str):
        return value

    item = getattr(value, "item", None)
    if callable(item):
        coerced = item()
        return _extract_scalar_value(coerced)

    return str(value)


def build_underwriting_calculation_context(
    filename: str,
    workbook_bytes: bytes,
    formula_refs_by_sheet: dict[str, list[str]],
) -> UnderwritingCalculationContext:
    warnings: list[UnderwritingFormulaWarning] = []
    input_nodes_by_sheet_ref = {sheet_name: {} for sheet_name in formula_refs_by_sheet}
    formula_nodes_by_sheet_ref = {sheet_name: {} for sheet_name in formula_refs_by_sheet}

    try:
        safe_name = Path(filename or "underwriting.xlsx").name or "underwriting.xlsx"
        with tempfile.TemporaryDirectory(prefix="uap-formulas-") as tempdir:
            workbook_path = os.path.join(tempdir, safe_name)
            with open(workbook_path, "wb") as workbook_file:
                workbook_file.write(workbook_bytes)
            model = _load_formula_model(workbook_path)
    except Exception as exc:
        warnings.append(
            UnderwritingFormulaWarning(
                sheet="",
                message=f"In-app formula recalculation is unavailable: {exc}",
            )
        )
        return UnderwritingCalculationContext(
            model=None,
            input_nodes_by_sheet_ref=input_nodes_by_sheet_ref,
            formula_nodes_by_sheet_ref=formula_nodes_by_sheet_ref,
            build_warnings=warnings,
        )

    sheets_by_key = {
        _normalize_sheet_key(sheet_name): sheet_name for sheet_name in formula_refs_by_sheet
    }
    for node_ref in model.dsp.data_nodes:
        if not isinstance(node_ref, str):
            continue

        parsed = _parse_model_cell_ref(node_ref)
        if not parsed:
            continue

        sheet_key, cell_ref = parsed
        actual_sheet_name = sheets_by_key.get(sheet_key)
        if not actual_sheet_name:
            continue

        input_nodes_by_sheet_ref.setdefault(actual_sheet_name, {})[cell_ref] = node_ref

    for sheet_name, formula_refs in formula_refs_by_sheet.items():
        node_map = input_nodes_by_sheet_ref.get(sheet_name, {})
        missing_refs: list[str] = []
        for ref in formula_refs:
            normalized_ref = _normalize_cell_ref(ref)
            node_ref = node_map.get(normalized_ref)
            if node_ref:
                formula_nodes_by_sheet_ref.setdefault(sheet_name, {})[normalized_ref] = node_ref
            else:
                missing_refs.append(normalized_ref)

        if missing_refs:
            warnings.append(
                UnderwritingFormulaWarning(
                    sheet=sheet_name,
                    refs=missing_refs,
                    message="Some formulas could not be mapped for in-app recalculation.",
                )
            )

    return UnderwritingCalculationContext(
        model=model,
        input_nodes_by_sheet_ref=input_nodes_by_sheet_ref,
        formula_nodes_by_sheet_ref=formula_nodes_by_sheet_ref,
        build_warnings=warnings,
    )


def calculate_underwriting_formula_values(
    context: UnderwritingCalculationContext | None,
    updates: dict[str, dict[str, str | int | float]],
) -> tuple[
    dict[str, dict[str, str | int | float | bool | None]],
    list[UnderwritingFormulaWarning],
]:
    formula_values: dict[str, dict[str, str | int | float | bool | None]] = {}
    warnings = list(context.build_warnings) if context else []

    if context is None or context.model is None:
        return formula_values, warnings

    output_lookup: dict[str, tuple[str, str]] = {}
    output_refs: list[str] = []
    for sheet_name, refs in context.formula_nodes_by_sheet_ref.items():
        for ref, node_ref in refs.items():
            output_lookup[node_ref] = (sheet_name, ref)
            output_refs.append(node_ref)

    if not output_refs:
        return formula_values, warnings

    inputs: dict[str, str | int | float] = {}
    for sheet_name, cells in updates.items():
        input_nodes = context.input_nodes_by_sheet_ref.get(sheet_name, {})
        for ref, value in cells.items():
            node_ref = input_nodes.get(_normalize_cell_ref(ref))
            if node_ref:
                inputs[node_ref] = value

    try:
        solution = context.model.calculate(inputs=inputs, outputs=output_refs)
    except Exception as exc:
        warnings.append(
            UnderwritingFormulaWarning(
                sheet="",
                message=f"Formula recalculation fell back to cached workbook values: {exc}",
            )
        )
        return {}, warnings

    for node_ref, (sheet_name, ref) in output_lookup.items():
        if node_ref not in solution:
            continue
        try:
            extracted = _extract_scalar_value(solution[node_ref])
        except Exception:
            warnings.append(
                UnderwritingFormulaWarning(
                    sheet=sheet_name,
                    refs=[ref],
                    message="A formula produced a non-scalar result and could not be shown in-app.",
                )
            )
            continue
        formula_values.setdefault(sheet_name, {})[ref] = extracted

    return formula_values, warnings


def enable_workbook_recalculation(workbook: Workbook) -> None:
    workbook.calculation.calcMode = "auto"
    workbook.calculation.fullCalcOnLoad = True
    workbook.calculation.forceFullCalc = True
    workbook.calculation.calcOnSave = True
