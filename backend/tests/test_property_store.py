import unittest

from property_models import PropertyContext, PropertyLotRecord, PropertyScenario
from property_store import (
    ACTIVE_PROPERTY_CONTEXT_ID,
    delete_property_context,
    fetch_property_context,
    upsert_property_context,
)


class FakeIndex:
    def __init__(self):
        self.namespaces: dict[str, dict[str, dict]] = {}

    def upsert(self, vectors: list[dict], namespace: str) -> None:
        bucket = self.namespaces.setdefault(namespace, {})
        for vector in vectors:
            bucket[vector["id"]] = {"metadata": dict(vector["metadata"]), "values": list(vector["values"])}

    def fetch(self, ids: list[str], namespace: str) -> dict:
        bucket = self.namespaces.get(namespace, {})
        return {"vectors": {item_id: bucket[item_id] for item_id in ids if item_id in bucket}}

    def delete(self, ids: list[str], namespace: str) -> None:
        bucket = self.namespaces.setdefault(namespace, {})
        for item_id in ids:
            bucket.pop(item_id, None)


def sample_context() -> PropertyContext:
    return PropertyContext(
        primary_bbl="3012340001",
        adjacent_bbls=["3012340002"],
        selected_bbls=["3012340001", "3012340002"],
        address="100 Example Street",
        borough="Brooklyn",
        block="1234",
        lots=["1", "2"],
        zoning_district="R8A",
        overlay="C2-4",
        overlay_far=2.0,
        community_facility_far=6.5,
        standard_far=6.02,
        qah_far=7.2,
        standard_height_limit=125,
        qah_height_limit=145,
        lot_coverage_corner=80,
        lot_coverage_interior=70,
        street_type_assumption="narrow",
        has_narrow_wide=True,
        lot_type="interior",
        lot_area=15_000,
        building_area=27_500,
        units_total=32,
        assessed_value=1_850_000,
        market_value=7_200_000,
        dof_taxable=1_650_000,
        scenarios=[PropertyScenario(code="ideal_match", label="Ideal Match", max_res_floor_area=82_799)],
        lots_detail=[
            PropertyLotRecord(
                bbl="3012340001",
                borough="Brooklyn",
                block="1234",
                lot="1",
                address="100 Example Street",
                zoning="R8A",
                lot_area=10_000,
                building_area=20_000,
                res_far=6.02,
                units_total=24,
                has_pluto=True,
                has_dof=True,
                lot_type="interior",
            )
        ],
        sources={"generated_at": "2026-03-15T00:00:00Z"},
        property_brief="Synthetic property brief",
    )


class PropertyStoreTests(unittest.TestCase):
    def test_upsert_fetch_and_delete_property_context(self):
        index = FakeIndex()
        context = sample_context()

        upsert_property_context(index, "PropertyContextStore", [0.1, 0.2, 0.3], context)
        stored = index.namespaces["PropertyContextStore"][ACTIVE_PROPERTY_CONTEXT_ID]

        self.assertEqual(stored["metadata"]["source"], "Active Property Context")
        self.assertEqual(stored["metadata"]["primary_bbl"], "3012340001")
        self.assertEqual(stored["metadata"]["selected_bbls"], "3012340001,3012340002")

        fetched = fetch_property_context(index, "PropertyContextStore")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.primary_bbl, context.primary_bbl)
        self.assertEqual(fetched.selected_bbls, context.selected_bbls)
        self.assertEqual(fetched.property_brief, "Synthetic property brief")

        delete_property_context(index, "PropertyContextStore")
        self.assertIsNone(fetch_property_context(index, "PropertyContextStore"))


if __name__ == "__main__":
    unittest.main()
