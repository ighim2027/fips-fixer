"""Run with: python -m unittest test_fips_fixer -v"""

import unittest
from fips_fixer import normalize, state_of, audit_join, FipsError


class TestNormalize(unittest.TestCase):

    def test_recodes(self):
        self.assertEqual(normalize("46113"), "46102")  # Shannon -> Oglala Lakota
        self.assertEqual(normalize("51515"), "51019")  # Bedford City -> Bedford Co
        self.assertEqual(normalize("02270"), "02158")  # Wade Hampton -> Kusilvak

    def test_leading_zero(self):
        self.assertEqual(normalize("1001"), "01001")
        self.assertEqual(normalize(1001), "01001")

    def test_pandas_float_artifact(self):
        self.assertEqual(normalize("39049.0"), "39049")

    def test_state_level(self):
        self.assertEqual(normalize("2"), "02000")
        self.assertEqual(normalize("39"), "39000")

    def test_idempotent(self):
        # normalize(normalize(x)) == normalize(x), for every recode
        for old in ["46113", "51515", "02270", "39049", "1001"]:
            once = normalize(old)
            self.assertEqual(normalize(once), once, f"not idempotent: {old}")

    def test_connecticut_returns_none(self):
        self.assertIsNone(normalize("09110"))

    def test_connecticut_strict_raises(self):
        with self.assertRaises(FipsError):
            normalize("09110", strict=True)

    def test_garbage_raises(self):
        for bad in ["", "abc", None, "1234567"]:
            with self.assertRaises(FipsError):
                normalize(bad)

    def test_state_of(self):
        self.assertEqual(state_of("39049"), "39")
        self.assertEqual(state_of("1001"), "01")


class TestAuditJoin(unittest.TestCase):

    def setUp(self):
        self.cdc = ["46113", "51515", "1001", "02270", "39049"]
        self.epa = ["46102", "51019", "01001", "02158", "39049"]

    def test_raw_join_is_a_disaster(self):
        """This is the whole point of the library."""
        raw_matches = set(self.cdc) & set(self.epa)
        self.assertEqual(len(raw_matches), 1)  # only 39049 survives

    def test_normalized_join_is_complete(self):
        report = audit_join(self.cdc, self.epa)
        self.assertEqual(report["matched"], 5)
        self.assertEqual(report["match_rate"], 1.0)

    def test_unmappable_is_reported_not_hidden(self):
        report = audit_join(self.cdc + ["09110"], self.epa)
        self.assertIn("09110", report["unmappable_dropped"])

    def test_unparseable_is_reported_not_hidden(self):
        report = audit_join(self.cdc + ["oops"], self.epa)
        self.assertEqual(len(report["unparseable"]), 1)


if __name__ == "__main__":
    unittest.main()
