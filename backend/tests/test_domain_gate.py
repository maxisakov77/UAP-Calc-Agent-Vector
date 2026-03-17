import unittest

from property_models import PropertyContext
from main import _is_domain_query


def sample_context() -> PropertyContext:
    return PropertyContext(
        primary_bbl="3012340001",
        selected_bbls=["3012340001"],
        address="100 Example Street",
        borough="Brooklyn",
        block="1234",
        lots=["1"],
        zoning_district="R8A",
        lot_area=10_000,
        building_area=20_000,
        units_total=24,
        property_brief="Synthetic property brief",
    )


class DomainGateTests(unittest.TestCase):
    def test_domain_gate_allows_explicit_nyc_development_queries(self):
        self.assertTrue(_is_domain_query("What is the best UAP 485-x strategy for this site?", None))
        self.assertTrue(_is_domain_query("Explain zoning FAR limits for this property", None))

    def test_domain_gate_requires_property_context_for_implicit_site_questions(self):
        self.assertFalse(_is_domain_query("What should we build here?", None))
        self.assertTrue(_is_domain_query("What should we build on this site?", sample_context()))

    def test_domain_gate_rejects_off_domain_queries(self):
        self.assertFalse(_is_domain_query("Write me a pasta recipe", None))


if __name__ == "__main__":
    unittest.main()
