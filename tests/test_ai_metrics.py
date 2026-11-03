import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_metrics import (account_ai_metrics, ai_metrics_summary,
                        all_ai_metrics, time_to_first_success_days)
from generator import generate_records
from tests.helpers import account_rows, rec


class TestTimeToFirstSuccess(unittest.TestCase):
    def test_week0_success_is_day0(self):
        self.assertEqual(time_to_first_success_days(account_rows()), 0)

    def test_week2_success_is_day14(self):
        rows = account_rows()
        for r in rows[:2]:
            r.update(outputs_accepted=0)
        self.assertEqual(time_to_first_success_days(rows), 14)

    def test_never_any_accepted_output(self):
        rows = account_rows()
        for r in rows:
            r.update(outputs_accepted=0)
        self.assertIsNone(time_to_first_success_days(rows))


class TestAccountAiMetrics(unittest.TestCase):
    def test_prompts_per_active_seat_last_week(self):
        # helpers: prompts = sessions*3 = 150, active = 10
        metrics = account_ai_metrics(account_rows())
        self.assertEqual(metrics["prompts_per_active_seat"], 15.0)
        self.assertEqual(metrics["prompts_last_week"], 150)

    def test_acceptance_rate_cumulative(self):
        # helpers: accepted = 80% of generated on every row
        metrics = account_ai_metrics(account_rows())
        self.assertEqual(metrics["acceptance_rate"], 0.8)
        self.assertEqual(metrics["outputs_accepted_total"],
                         int(0.8 * metrics["outputs_generated_total"]))

    def test_zero_use_account(self):
        metrics = account_ai_metrics(
            account_rows(active=0, sessions=0, features=0))
        self.assertEqual(metrics["prompts_per_active_seat"], 0.0)
        self.assertEqual(metrics["acceptance_rate"], 0.0)
        self.assertIsNone(metrics["time_to_first_success_days"])

    def test_empty_rows_raise(self):
        with self.assertRaises(ValueError):
            account_ai_metrics([])

    def test_all_sorted_by_account(self):
        records = (account_rows("acct_b", weeks=2)
                   + account_rows("acct_a", weeks=2))
        self.assertEqual([m["account_id"] for m in all_ai_metrics(records)],
                         ["acct_a", "acct_b"])


class TestSeededAiMetrics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary = ai_metrics_summary(generate_records())

    def test_headline_pinned(self):
        s = self.summary
        self.assertEqual(s["accounts_with_first_success"], 120)
        self.assertEqual(s["time_to_first_success_median_days"], 0.0)
        self.assertEqual(s["time_to_first_success_mean_days"], 2.333333)
        self.assertEqual(s["share_first_success_in_week0"], 0.733333)

    def test_acceptance_pinned(self):
        s = self.summary
        self.assertEqual(s["total_prompts"], 3182142)
        self.assertEqual(s["total_outputs_generated"], 3182142)
        self.assertEqual(s["total_outputs_accepted"], 2450533)
        self.assertEqual(s["overall_acceptance_rate"], 0.770089)

    def test_prompts_per_active_seat_pinned(self):
        self.assertEqual(self.summary["prompts_per_active_seat_mean"],
                         16.440152)

    def test_by_cohort(self):
        by = self.summary["by_cohort"]
        self.assertEqual([c["cohort"] for c in by],
                         ["2026-01", "2026-02", "2026-03", "2026-04"])
        self.assertTrue(all(c["median_days"] == 0.0 for c in by))
        self.assertEqual(by[-1]["mean_days"], 2.8)


if __name__ == "__main__":
    unittest.main()
