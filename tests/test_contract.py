import csv
import io
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generator import generate_records
from health import (HEALTH_CONTRACT_FIELDS, HEALTH_CONTRACT_VERSION,
                    HEALTH_TIERS, health_contract, health_contract_csv,
                    health_contract_document, health_contract_json)


class TestHealthContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = generate_records()
        cls.contract = health_contract(cls.records)

    def test_version_pinned(self):
        self.assertEqual(HEALTH_CONTRACT_VERSION, "1.0")
        doc = health_contract_document(self.records)
        self.assertEqual(doc["schema_version"], "1.0")
        self.assertEqual(doc["fields"], HEALTH_CONTRACT_FIELDS)
        self.assertEqual(doc["tiers"], list(HEALTH_TIERS))

    def test_field_order_exact(self):
        for row in self.contract:
            self.assertEqual(list(row.keys()), HEALTH_CONTRACT_FIELDS)

    def test_sorted_by_account_and_complete(self):
        ids = [r["account_id"] for r in self.contract]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(len(ids), 120)

    def test_tiers_are_closed_enum(self):
        for row in self.contract:
            self.assertIn(row["health_tier"], HEALTH_TIERS)

    def test_first_record_pinned(self):
        first = self.contract[0]
        self.assertEqual(first["account_id"], "acct_001")
        self.assertEqual(first["health_tier"], "steady")
        self.assertEqual(first["utilization_score"], 0.569185)
        self.assertEqual(first["week_start"], "2026-06-29")

    def test_tier_counts_match_summary(self):
        counts = {}
        for row in self.contract:
            counts[row["health_tier"]] = counts.get(row["health_tier"], 0) + 1
        self.assertEqual(counts, {"thriving": 37, "steady": 34,
                                  "at-risk": 25, "dormant": 24})

    def test_csv_header_and_rows(self):
        text = health_contract_csv(self.records)
        lines = text.splitlines()
        self.assertEqual(lines[0], ",".join(HEALTH_CONTRACT_FIELDS))
        self.assertEqual(len(lines), 121)
        reader = csv.DictReader(io.StringIO(text))
        self.assertEqual(reader.fieldnames, HEALTH_CONTRACT_FIELDS)

    def test_csv_and_json_agree(self):
        doc = json.loads(health_contract_json(self.records))
        reader = list(csv.DictReader(
            io.StringIO(health_contract_csv(self.records))))
        self.assertEqual(len(reader), len(doc["records"]))
        for csv_row, json_row in zip(reader, doc["records"]):
            self.assertEqual(csv_row["account_id"], json_row["account_id"])
            self.assertEqual(csv_row["health_tier"],
                             json_row["health_tier"])
            self.assertEqual(csv_row["week_start"], json_row["week_start"])

    def test_json_is_deterministic(self):
        self.assertEqual(health_contract_json(self.records),
                         health_contract_json(generate_records()))


if __name__ == "__main__":
    unittest.main()
