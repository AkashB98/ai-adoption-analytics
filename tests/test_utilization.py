import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generator import generate_records
from tests.helpers import account_rows, rec
from utilization import (account_utilization, all_utilization,
                         feature_breadth, seat_utilization,
                         sessions_per_active, utilization_score,
                         utilization_summary)


class TestPrimitives(unittest.TestCase):
    def test_seat_utilization(self):
        self.assertEqual(seat_utilization(25, 100), 0.25)

    def test_seat_utilization_capped(self):
        self.assertEqual(seat_utilization(150, 100), 1.0)

    def test_seat_utilization_zero_seats(self):
        self.assertEqual(seat_utilization(5, 0), 0.0)

    def test_sessions_per_active(self):
        self.assertEqual(sessions_per_active(50, 10), 5.0)

    def test_sessions_per_active_no_users(self):
        self.assertEqual(sessions_per_active(0, 0), 0.0)

    def test_feature_breadth(self):
        self.assertEqual(feature_breadth(4), 0.5)
        self.assertEqual(feature_breadth(8), 1.0)
        self.assertEqual(feature_breadth(0), 0.0)

    def test_score_hand_computed(self):
        # 0.5*0.5 + 0.3*(5/10) + 0.2*0.5 = 0.25+0.15+0.10
        self.assertEqual(utilization_score(0.5, 5.0, 0.5), 0.5)

    def test_score_sessions_capped(self):
        self.assertEqual(utilization_score(0.0, 99.0, 0.0), 0.3)

    def test_score_max(self):
        self.assertEqual(utilization_score(1.0, 10.0, 1.0), 1.0)


class TestAccountUtilization(unittest.TestCase):
    def test_uses_last_week_not_first(self):
        rows = account_rows(active=10, sessions=50)
        rows[-1].update(active_users=40, sessions=400, features_used=8)
        util = account_utilization(rows)
        self.assertEqual(util["active_users"], 40)
        self.assertEqual(util["seat_utilization"], 0.4)
        self.assertEqual(util["feature_breadth"], 1.0)

    def test_empty_rows_raise(self):
        with self.assertRaises(ValueError):
            account_utilization([])

    def test_all_sorted_by_account(self):
        records = (account_rows("acct_b", weeks=2)
                   + account_rows("acct_a", weeks=2))
        self.assertEqual([u["account_id"] for u in all_utilization(records)],
                         ["acct_a", "acct_b"])


class TestSummary(unittest.TestCase):
    def test_seeded_summary_pinned(self):
        summary = utilization_summary(generate_records())
        self.assertEqual(summary["accounts"], 120)
        self.assertEqual(summary["total_licensed_seats"], 28049)
        self.assertEqual(summary["total_active_users_last_week"], 7807)
        self.assertEqual(summary["mean_utilization_score"], 0.413675)
        self.assertEqual(summary["overall_seat_utilization"], 0.278334)

    def test_empty_summary(self):
        summary = utilization_summary([])
        self.assertEqual(summary["accounts"], 0)
        self.assertEqual(summary["mean_utilization_score"], 0.0)


if __name__ == "__main__":
    unittest.main()
