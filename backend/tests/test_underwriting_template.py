import unittest
from datetime import date

from openpyxl.utils.datetime import CALENDAR_WINDOWS_1900

from underwriting_template import (
    build_underwriting_cell_payload,
    serialize_underwriting_cell_value,
)


class UnderwritingTemplateTests(unittest.TestCase):
    def test_build_underwriting_cell_payload_preserves_format_and_precision(self):
        payload = build_underwriting_cell_payload(
            1234.56789,
            row=4,
            col=2,
            is_formula=False,
            number_format='$#,##0.00_);($#,##0.00)',
            epoch=CALENDAR_WINDOWS_1900,
        )

        self.assertEqual(payload, {
            "v": 1234.56789,
            "r": 4,
            "c": 2,
            "z": '$#,##0.00_);($#,##0.00)',
        })

    def test_build_underwriting_cell_payload_serializes_dates_to_excel_serials(self):
        payload = build_underwriting_cell_payload(
            date(2024, 1, 15),
            row=7,
            col=3,
            is_formula=False,
            number_format="m/d/yy",
            epoch=CALENDAR_WINDOWS_1900,
        )

        self.assertEqual(payload, {
            "v": 45306.0,
            "r": 7,
            "c": 3,
            "z": "m/d/yy",
        })

    def test_formula_cells_keep_null_cached_value_and_number_format(self):
        payload = build_underwriting_cell_payload(
            None,
            row=10,
            col=5,
            is_formula=True,
            number_format="0.00%",
            epoch=CALENDAR_WINDOWS_1900,
        )

        self.assertEqual(payload, {
            "v": None,
            "r": 10,
            "c": 5,
            "z": "0.00%",
            "f": True,
        })

    def test_serialize_underwriting_cell_value_does_not_round_floats(self):
        self.assertEqual(
            serialize_underwriting_cell_value(12.3456789, CALENDAR_WINDOWS_1900),
            12.3456789,
        )


if __name__ == "__main__":
    unittest.main()
