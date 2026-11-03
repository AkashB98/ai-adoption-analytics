import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generator import (ACCOUNT_COUNT, COHORT_LABELS, FEATURE_COUNT,
                       account_name, cohort_for_index, generate_records,
                       accounts_of, records_by_account, records_to_jsonl)


class TestGenerator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = generate_records()

    def test_record_count(self):
        self.assertEqual(len(self.records), 2400)

    def test_account_count(self):
        self.assertEqual(len(accounts_of(self.records)), ACCOUNT_COUNT)

    def test_deterministic(self):
        self.assertEqual(generate_records(), self.records)
        self.assertEqual(records_to_jsonl(generate_records()),
                         records_to_jsonl(self.records))

    def test_different_seed_differs(self):
        self.assertNotEqual(generate_records(seed=7), self.records)

    def test_names_unique(self):
        names = [a["account_name"] for a in accounts_of(self.records)]
        self.assertEqual(len(set(names)), 120)
        self.assertEqual(account_name(0), "Aster Labs")
        self.assertEqual(account_name(119), account_name(119))

    def test_cohorts_balanced(self):
        accts = accounts_of(self.records)
        for label in COHORT_LABELS:
            self.assertEqual(
                sum(1 for a in accts if a["cohort"] == label), 30)

    def test_cohort_for_index_blocks(self):
        self.assertEqual([cohort_for_index(i) for i in (0, 29, 30, 60, 90, 119)],
                         [0, 0, 1, 2, 3, 3])

    def test_rows_per_account_by_cohort(self):
        grouped = records_by_account(self.records)
        self.assertEqual(len(grouped["acct_001"]), 26)
        self.assertEqual(len(grouped["acct_031"]), 22)
        self.assertEqual(len(grouped["acct_061"]), 18)
        self.assertEqual(len(grouped["acct_091"]), 14)

    def test_active_never_exceeds_seats(self):
        for r in self.records:
            self.assertLessEqual(r["active_users"], r["licensed_seats"])
            self.assertGreaterEqual(r["active_users"], 0)

    def test_zero_active_means_zero_use(self):
        for r in self.records:
            if r["active_users"] == 0:
                self.assertEqual(r["sessions"], 0)
                self.assertEqual(r["features_used"], 0)
                self.assertEqual(r["prompts"], 0)
                self.assertEqual(r["outputs_generated"], 0)
                self.assertEqual(r["outputs_accepted"], 0)

    def test_ai_fields_consistent(self):
        for r in self.records:
            if r["active_users"] > 0:
                self.assertTrue(2 * r["sessions"] <= r["prompts"]
                                <= 4 * r["sessions"])
                self.assertEqual(r["outputs_generated"], r["prompts"])
                self.assertTrue(0 < r["outputs_accepted"]
                                <= r["outputs_generated"])

    def test_features_within_available(self):
        for r in self.records:
            self.assertTrue(0 <= r["features_used"] <= FEATURE_COUNT)

    def test_weeks_are_mondays_and_sequential(self):
        grouped = records_by_account(self.records)
        for rows in grouped.values():
            self.assertEqual([r["weeks_since_rollout"] for r in rows],
                             list(range(len(rows))))
            for r in rows:
                self.assertEqual(date.fromisoformat(r["week_start"]).weekday(), 0)

    def test_sessions_positive_when_active(self):
        for r in self.records:
            if r["active_users"] > 0:
                self.assertGreater(r["sessions"], 0)


if __name__ == "__main__":
    unittest.main()
