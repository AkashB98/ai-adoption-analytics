import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generator import generate_records
from report import build_report, format_report_text


class TestReport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = build_report(generate_records())

    def test_headline_counts(self):
        self.assertEqual(self.report["accounts"], 120)
        self.assertEqual(self.report["records"], 2400)

    def test_cohort_list(self):
        self.assertEqual(self.report["cohorts_list"],
                         ["2026-01", "2026-02", "2026-03", "2026-04"])
        self.assertEqual(len(self.report["cohorts"]), 4)

    def test_health_tiers_sum_to_accounts(self):
        self.assertEqual(sum(self.report["health"]["tiers"].values()), 120)
        self.assertEqual(len(self.report["health_per_account"]), 120)

    def test_anomaly_count_matches_list(self):
        self.assertEqual(self.report["anomaly_count"],
                         len(self.report["anomalies"]))
        self.assertEqual(self.report["anomaly_count"], 125)

    def test_ai_metrics_in_report(self):
        ai = self.report["ai_metrics"]
        self.assertEqual(ai["overall_acceptance_rate"], 0.770089)
        self.assertEqual(ai["time_to_first_success_median_days"], 0.0)
        self.assertEqual(len(self.report["ai_metrics_per_account"]), 120)

    def test_health_contract_in_report(self):
        contract = self.report["health_contract"]
        self.assertEqual(contract["schema_version"], "1.0")
        self.assertEqual(len(contract["records"]), 120)

    def test_report_deterministic(self):
        self.assertEqual(build_report(generate_records()), self.report)

    def test_text_contains_headlines(self):
        text = format_report_text(self.report)
        for needle in ("AI ADOPTION SCORECARD", "84.2%", "thriving: 37",
                       "at-risk: 25", "dormant: 24", "Anomalies: 125",
                       "AI outputs accepted", "77.0%",
                       "time to first successful AI task"):
            self.assertIn(needle, text)

    def test_text_deterministic(self):
        self.assertEqual(format_report_text(build_report(generate_records())),
                         format_report_text(self.report))

    def test_activation_definition_in_report(self):
        definition = self.report["activation"]["definition"]
        self.assertEqual(definition["min_active_users"], 3)
        self.assertEqual(definition["min_sessions"], 5)
        self.assertEqual(definition["window_weeks"], [0, 1])


if __name__ == "__main__":
    unittest.main()
