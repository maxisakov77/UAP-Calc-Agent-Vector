import io
import unittest
from unittest import mock

from openpyxl import Workbook

from underwriting_calculator import (
    build_underwriting_calculation_context,
    calculate_underwriting_formula_values,
    enable_workbook_recalculation,
)


def build_workbook_bytes() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Inputs"
    sheet["A1"] = 2
    sheet["A2"] = 3
    sheet["B1"] = "=A1+A2"
    sheet["B2"] = "=B1*10"

    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


class UnderwritingCalculatorTests(unittest.TestCase):
    def test_calculates_formula_values_from_current_updates(self):
        workbook_bytes = build_workbook_bytes()
        context = build_underwriting_calculation_context(
            "underwriting.xlsx",
            workbook_bytes,
            {"Inputs": ["B1", "B2"]},
        )

        formula_values, warnings = calculate_underwriting_formula_values(
            context,
            {"Inputs": {"A1": 5}},
        )

        self.assertEqual(warnings, [])
        self.assertEqual(formula_values["Inputs"]["B1"], 8.0)
        self.assertEqual(formula_values["Inputs"]["B2"], 80.0)

    def test_returns_warning_when_formula_model_cannot_be_built(self):
        workbook_bytes = build_workbook_bytes()

        with mock.patch(
            "underwriting_calculator._load_formula_model",
            side_effect=RuntimeError("unsupported workbook feature"),
        ):
            context = build_underwriting_calculation_context(
                "underwriting.xlsx",
                workbook_bytes,
                {"Inputs": ["B1"]},
            )

        formula_values, warnings = calculate_underwriting_formula_values(
            context,
            {"Inputs": {"A1": 5}},
        )

        self.assertEqual(formula_values, {})
        self.assertEqual(len(warnings), 1)
        self.assertIn("unsupported workbook feature", warnings[0].message)

    def test_enable_workbook_recalculation_sets_calc_properties(self):
        workbook = Workbook()

        enable_workbook_recalculation(workbook)

        self.assertEqual(workbook.calculation.calcMode, "auto")
        self.assertTrue(workbook.calculation.fullCalcOnLoad)
        self.assertTrue(workbook.calculation.forceFullCalc)
        self.assertTrue(workbook.calculation.calcOnSave)


if __name__ == "__main__":
    unittest.main()
