import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cohorts import (activation_week, cohort_summary, is_activated,
                     overall_activation, retention_at)
from generator import generate_records
from tests.helpers import account_rows, rec


class TestActivation(unittest.TestCase):
    def test_activated_week0(self):
        self.assertTrue(is_activated(account_rows(active=10, sessions=50)))

    def test_activated_week1_only(self):
        rows = account_rows()
        rows[0].update(active_users=0, sessions=0, features_used=0)
        self.assertTrue(is_activated(rows))
        self.assertEqual(activation_week(rows), 1)

    def test_not_activated_when_first_use_is_week2(self):
        rows = account_rows()
        for r in rows[:2]:
            r.update(active_users=0, sessions=0, features_used=0)
        self.assertFalse(is_activated(rows))
        self.assertIsNone(activation_week(rows))

    def test_active_floor(self):
        rows = account_rows(active=2, sessions=50)
        self.assertFalse(is_activated(rows))

    def test_session_floor(self):
        rows = account_rows(active=10, sessions=4)
        self.assertFalse(is_activated(rows))

    def test_exact_thresholds_activate(self):
        rows = account_rows(active=3, sessions=5)
        self.assertTrue(is_activated(rows))

    def test_empty_rows_not_activated(self):
        self.assertFalse(is_activated([]))


class TestRetention(unittest.TestCase):
    def test_retained(self):
        self.assertEqual(retention_at(account_rows(), 4), (1, 1))

    def test_not_retained(self):
        rows = account_rows()
        rows[4].update(active_users=0, sessions=0, features_used=0)
        self.assertEqual(retention_at(rows, 4), (0, 1))

    def test_unactivated_excluded(self):
        rows = account_rows(active=0, sessions=0, features=0)
        self.assertIsNone(retention_at(rows, 4))

    def test_missing_week_excluded(self):
        self.assertIsNone(retention_at(account_rows(weeks=3), 12))


class TestSeededCohorts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = generate_records()

    def test_overall_activation_pinned(self):
        overall = overall_activation(self.records)
        self.assertEqual(overall["activated"], 101)
        self.assertEqual(overall["activation_rate"], 0.841667)

    def test_cohort_summary_pinned(self):
        summary = cohort_summary(self.records)
        self.assertEqual([c["cohort"] for c in summary],
                         ["2026-01", "2026-02", "2026-03", "2026-04"])
        self.assertEqual([c["activation_rate"] for c in summary],
                         [0.9, 0.833333, 0.866667, 0.766667])
        self.assertTrue(all(c["week4_retention"] == 1.0 for c in summary))

    def test_week12_retention_pinned(self):
        summary = cohort_summary(self.records)
        self.assertEqual([c["week12_retention"] for c in summary],
                         [0.851852, 0.88, 0.961538, 0.73913])


if __name__ == "__main__":
    unittest.main()
