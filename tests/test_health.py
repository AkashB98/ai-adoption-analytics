import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generator import generate_records
from health import (HEALTH_RULES, HEALTH_TIERS, classify_health,
                    detect_anomalies, health_summary)
from tests.helpers import account_rows, rec, util_dict


class TestClassify(unittest.TestCase):
    def test_rules_cover_all_tiers_in_order(self):
        # Evaluation order is deliberate: dormant (inactivity) first,
        # steady as the fallback last - not the display order.
        self.assertEqual([r["tier"] for r in HEALTH_RULES],
                         ["dormant", "thriving", "at-risk", "steady"])
        self.assertEqual({r["tier"] for r in HEALTH_RULES},
                         set(HEALTH_TIERS))

    def test_dormant_last_two_weeks_zero(self):
        rows = account_rows(active=10)
        for r in rows[-2:]:
            r.update(active_users=0, sessions=0, features_used=0)
        self.assertEqual(classify_health(util_dict(score=0.9), rows), "dormant")

    def test_not_dormant_if_one_of_last_two_active(self):
        rows = account_rows(active=10)
        rows[-1].update(active_users=0, sessions=0, features_used=0)
        self.assertNotEqual(classify_health(util_dict(), rows), "dormant")

    def test_dormant_beats_thriving_numbers(self):
        # Rule order: inactivity is checked before thresholds.
        rows = account_rows(active=0, sessions=0, features=0)
        self.assertEqual(
            classify_health(util_dict(0.9, 1.0, 0.9), rows), "dormant")

    def test_thriving(self):
        self.assertEqual(classify_health(
            util_dict(0.60, 0.50, 0.35), account_rows()), "thriving")

    def test_thriving_needs_all_three(self):
        self.assertNotEqual(classify_health(
            util_dict(0.90, 0.49, 0.90), account_rows()), "thriving")

    def test_at_risk_low_score(self):
        self.assertEqual(classify_health(
            util_dict(0.29, 0.5, 0.5), account_rows()), "at-risk")

    def test_at_risk_low_seat_utilization(self):
        self.assertEqual(classify_health(
            util_dict(0.50, 0.5, 0.07), account_rows()), "at-risk")

    def test_steady_fallback(self):
        self.assertEqual(classify_health(
            util_dict(0.45, 0.4, 0.3), account_rows()), "steady")

    def test_score_boundary_030_is_not_at_risk(self):
        self.assertEqual(classify_health(
            util_dict(0.30, 0.4, 0.3), account_rows()), "steady")


class TestSeededHealth(unittest.TestCase):
    def test_tier_counts_pinned(self):
        summary = health_summary(generate_records())
        self.assertEqual(summary["tiers"], {"thriving": 37, "steady": 34,
                                            "at-risk": 25, "dormant": 24})
        self.assertEqual(summary["at_risk_share"], 0.408333)
        self.assertTrue(summary["within_threshold"])

    def test_tier_shares_sum_to_one(self):
        summary = health_summary(generate_records())
        self.assertAlmostEqual(sum(summary["tier_shares"].values()), 1.0,
                               places=5)


class TestAnomalies(unittest.TestCase):
    def _rows(self, sessions_list):
        rows = []
        for w, s in enumerate(sessions_list):
            active = 10 if s else 0
            rows.append(rec(week_index=w, weeks_since_rollout=w,
                            active_users=active, sessions=s,
                            features_used=4 if s else 0))
        return rows

    def test_sudden_drop_flagged(self):
        # median 100, MAD 5 -> robust z = 0.6745 * -60 / 5 = -8.094
        flags = detect_anomalies(self._rows([100, 110, 90, 100, 40]))
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0]["kind"], "sudden_drop")
        self.assertEqual(flags[0]["baseline_median_sessions"], 100.0)
        self.assertEqual(flags[0]["mad"], 5.0)
        self.assertEqual(flags[0]["robust_z"], -8.094)

    def test_no_flag_without_four_prior_weeks(self):
        self.assertEqual(detect_anomalies(self._rows([100, 100, 10])), [])

    def test_flat_baseline_drop_flags_with_sentinel(self):
        flags = detect_anomalies(self._rows([100, 100, 100, 100, 50]))
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0]["mad"], 0.0)
        self.assertEqual(flags[0]["robust_z"], -999.9)

    def test_flat_baseline_no_drop_no_flag(self):
        self.assertEqual(
            detect_anomalies(self._rows([100, 100, 100, 100, 100])), [])

    def test_small_drop_within_noise_no_flag(self):
        # robust z = 0.6745 * -15 / 5 = -2.0235, above the -3.5 line
        self.assertEqual(
            detect_anomalies(self._rows([100, 110, 90, 100, 85])), [])

    def test_high_variance_baseline_absorbs_drop(self):
        # MAD is 50 here, so the same 60-session drop is z = -0.81:
        # the median/MAD pair is not dragged by the wild baseline.
        self.assertEqual(
            detect_anomalies(self._rows([50, 150, 50, 150, 40])), [])

    def test_surge_never_flags(self):
        self.assertEqual(
            detect_anomalies(self._rows([100, 110, 90, 100, 500])), [])

    def test_seeded_anomalies_pinned(self):
        flags = detect_anomalies(generate_records())
        self.assertEqual(len(flags), 125)
        self.assertEqual(len({f["account_id"] for f in flags}), 72)
        self.assertEqual(flags[0]["account_id"], "acct_002")
        self.assertEqual(flags[0]["robust_z"], -4.24935)

    def test_all_planted_anomalies_caught(self):
        flags = detect_anomalies(generate_records())
        planted = {"acct_016", "acct_026", "acct_041", "acct_046",
                   "acct_051"}
        caught = {f["account_id"] for f in flags
                  if f["weeks_since_rollout"] == 15}
        self.assertTrue(planted <= caught)


if __name__ == "__main__":
    unittest.main()
