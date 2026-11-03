import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generator import generate_records
from tests.helpers import rec
from validation import validate_record, validate_records


class TestValidation(unittest.TestCase):
    def test_seeded_dataset_clean(self):
        self.assertEqual(validate_records(generate_records()), [])

    def test_single_valid_record(self):
        self.assertEqual(validate_record(rec()), [])

    def test_not_a_list(self):
        self.assertTrue(validate_records({"x": 1}))

    def test_empty_dataset(self):
        self.assertTrue(validate_records([]))

    def test_record_not_object(self):
        self.assertTrue(validate_record(42))

    def test_bad_cohort(self):
        self.assertTrue(any("cohort" in i for i in validate_record(
            rec(cohort="2025-01"))))

    def test_bad_segment(self):
        self.assertTrue(any("segment" in i for i in validate_record(
            rec(segment="huge"))))

    def test_bad_date(self):
        self.assertTrue(any("week_start" in i for i in validate_record(
            rec(week_start="Jan 5"))))

    def test_bool_trap_on_counts(self):
        self.assertTrue(any("sessions" in i for i in validate_record(
            rec(sessions=True))))

    def test_negative_count(self):
        self.assertTrue(any("sessions" in i for i in validate_record(
            rec(sessions=-1))))

    def test_active_exceeds_seats(self):
        self.assertTrue(any("active_users" in i for i in validate_record(
            rec(active_users=101))))

    def test_features_above_available(self):
        self.assertTrue(any("features_used" in i for i in validate_record(
            rec(features_used=9))))

    def test_sessions_without_users(self):
        self.assertTrue(any("sessions" in i for i in validate_record(
            rec(active_users=0, sessions=5, features_used=0))))

    def test_duplicate_account_week(self):
        issues = validate_records([rec(), rec()])
        self.assertTrue(any("duplicate" in i for i in issues))

    def test_accepted_exceeds_generated(self):
        self.assertTrue(any("outputs_accepted" in i
                            for i in validate_record(
                                rec(outputs_accepted=151))))

    def test_bool_trap_on_prompts(self):
        self.assertTrue(any("prompts" in i for i in validate_record(
            rec(prompts=True))))

    def test_prompts_without_users(self):
        self.assertTrue(any("prompts" in i for i in validate_record(
            rec(active_users=0, sessions=0, features_used=0, prompts=5,
                outputs_generated=0, outputs_accepted=0))))

    def test_zero_seats_rejected(self):
        self.assertTrue(any("licensed_seats" in i for i in validate_record(
            rec(licensed_seats=0, active_users=0, sessions=0,
                features_used=0))))


if __name__ == "__main__":
    unittest.main()
