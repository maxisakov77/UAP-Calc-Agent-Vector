import asyncio
import unittest

from property_service import PropertyService, _calculate_all_scenarios


class StubPropertyService(PropertyService):
    def __init__(self, records: dict[str, dict]):
        self.records = records

    async def lookup_bbl(self, borough: int, block: str, lot: str) -> dict:
        bbl = f"{borough}{int(block):05d}{int(lot):04d}"
        return dict(self.records[bbl])


class PropertyServiceTests(unittest.TestCase):
    def test_calculate_all_scenarios_returns_expected_programs(self):
        scenarios = _calculate_all_scenarios(lot_area=10_000, standard_far=6.02, uap_far=7.2)
        by_code = {scenario.code: scenario for scenario in scenarios}

        self.assertEqual(
            list(by_code),
            [
                "none",
                "485x_only",
                "uap_full_bonus",
                "avoid_prevailing_wages",
                "avoid_40_ami",
                "ideal_match",
            ],
        )
        self.assertEqual(by_code["none"].max_res_floor_area, 60_200)
        self.assertEqual(by_code["none"].max_number_of_units, 88)
        self.assertEqual(by_code["485x_only"].affordable_units_total, 18)
        self.assertEqual(by_code["uap_full_bonus"].max_res_floor_area, 72_000)
        self.assertTrue(by_code["uap_full_bonus"].triggers_prevailing_wages)
        self.assertTrue(by_code["uap_full_bonus"].triggers_40_ami)
        self.assertEqual(by_code["avoid_prevailing_wages"].max_number_of_units, 99)
        self.assertEqual(by_code["avoid_40_ami"].affordable_floor_area, 9_999)
        self.assertEqual(by_code["ideal_match"].max_number_of_units, 99)

    def test_build_property_context_dedupes_and_combines_same_block_lots(self):
        records = {
            "3012340001": {
                "bbl": "3012340001",
                "borough": "Brooklyn",
                "block": "1234",
                "lot": "1",
                "address": "100 Example Street",
                "zoning": "R8A",
                "overlay1": "C2-4",
                "overlay2": None,
                "lot_area": 10_000,
                "building_area": 20_000,
                "res_far": 6.02,
                "units_total": 24,
                "year_built": 1930,
                "assessed_value": 1_250_000,
                "market_value": 5_200_000,
                "dof_taxable": 1_100_000,
                "has_pluto": True,
                "has_dof": True,
                "lot_type_code": 5,
            },
            "3012340002": {
                "bbl": "3012340002",
                "borough": "Brooklyn",
                "block": "1234",
                "lot": "2",
                "address": "102 Example Street",
                "zoning": "R8A",
                "overlay1": "C2-4",
                "overlay2": None,
                "lot_area": 5_000,
                "building_area": 7_500,
                "res_far": 6.02,
                "units_total": 8,
                "year_built": 1955,
                "assessed_value": 600_000,
                "market_value": 2_000_000,
                "dof_taxable": 550_000,
                "has_pluto": True,
                "has_dof": True,
                "lot_type_code": 4,
            },
        }
        service = StubPropertyService(records)

        context = asyncio.run(
            service.build_property_context(
                primary_bbl="3012340001",
                adjacent_bbls=["3012340001", "3012340002"],
            )
        )

        self.assertEqual(context.primary_bbl, "3012340001")
        self.assertEqual(context.adjacent_bbls, ["3012340002"])
        self.assertEqual(context.selected_bbls, ["3012340001", "3012340002"])
        self.assertEqual(context.lot_area, 15_000)
        self.assertEqual(context.building_area, 27_500)
        self.assertEqual(context.units_total, 32)
        self.assertEqual(context.market_value, 7_200_000)
        self.assertEqual(context.standard_far, 6.02)
        self.assertEqual(context.qah_far, 7.2)
        self.assertEqual(len(context.lots_detail), 2)
        self.assertIn("ACTIVE PROPERTY CONTEXT", context.property_brief)
        self.assertIn("3012340002", context.property_brief)

    def test_build_property_context_rejects_cross_block_adjacent_lots(self):
        records = {
            "3012340001": {
                "bbl": "3012340001",
                "borough": "Brooklyn",
                "block": "1234",
                "lot": "1",
                "address": "100 Example Street",
                "zoning": "R8A",
                "lot_area": 10_000,
                "building_area": 20_000,
                "res_far": 6.02,
                "units_total": 24,
                "has_pluto": True,
                "has_dof": False,
            }
        }
        service = StubPropertyService(records)

        with self.assertRaisesRegex(ValueError, "same borough and block"):
            asyncio.run(
                service.build_property_context(
                    primary_bbl="3012340001",
                    adjacent_bbls=["3012350001"],
                )
            )


if __name__ == "__main__":
    unittest.main()
