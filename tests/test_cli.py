import io
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cli import EXIT_ERROR, EXIT_FAIL, EXIT_OK, main, make_server, reset_state
from generator import generate_records, write_records
from report import build_report
from tests.helpers import account_rows


def run_cli(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


class TestCli(unittest.TestCase):
    def test_generate_stdout(self):
        code, out, _ = run_cli(["generate"])
        self.assertEqual(code, EXIT_OK)
        data = json.loads(out)
        self.assertEqual(len(data), 2400)

    def test_generate_out_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "data.json")
            code, _, _ = run_cli(["generate", "--out", path])
            self.assertEqual(code, EXIT_OK)
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(len(json.load(fh)), 2400)

    def test_cohorts_command(self):
        code, out, _ = run_cli(["cohorts"])
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(json.loads(out)["activation"]["activated"], 101)

    def test_utilization_command(self):
        code, out, _ = run_cli(["utilization"])
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(json.loads(out)["total_licensed_seats"], 28049)

    def test_health_command(self):
        code, out, _ = run_cli(["health"])
        self.assertEqual(code, EXIT_OK)
        payload = json.loads(out)
        self.assertEqual(payload["tiers"]["thriving"], 37)
        self.assertEqual(len(payload["anomalies"]), 125)

    def test_ai_metrics_command(self):
        code, out, _ = run_cli(["ai-metrics"])
        self.assertEqual(code, EXIT_OK)
        payload = json.loads(out)
        self.assertEqual(payload["overall_acceptance_rate"], 0.770089)
        self.assertNotIn("per_account", payload)

    def test_health_contract_json_command(self):
        code, out, _ = run_cli(["health-contract"])
        self.assertEqual(code, EXIT_OK)
        doc = json.loads(out)
        self.assertEqual(doc["schema_version"], "1.0")
        self.assertEqual(len(doc["records"]), 120)

    def test_health_contract_csv_command(self):
        code, out, _ = run_cli(["health-contract", "--format", "csv"])
        self.assertEqual(code, EXIT_OK)
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("account_id,account_name,"))
        self.assertEqual(len(lines), 121)

    def test_report_json(self):
        code, out, _ = run_cli(["report"])
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(json.loads(out)["accounts"], 120)

    def test_report_text(self):
        code, out, _ = run_cli(["report", "--format", "text"])
        self.assertEqual(code, EXIT_OK)
        self.assertIn("AI ADOPTION SCORECARD", out)

    def test_check_seeded_passes(self):
        code, out, _ = run_cli(["check"])
        self.assertEqual(code, EXIT_OK)
        self.assertIn("check PASS", out)

    def test_check_missing_file_is_error(self):
        code, _, _ = run_cli(["check", "--input", "/tmp/no-such-adopt-xyz.json"])
        self.assertEqual(code, EXIT_ERROR)

    def test_check_invalid_data_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.json")
            write_records([{"account_id": "x"}], path)
            code, _, _ = run_cli(["check", "--input", path])
            self.assertEqual(code, EXIT_ERROR)

    def test_check_breach_is_fail(self):
        rows = []
        for n in range(4):
            rows += account_rows(f"acct_d{n}", weeks=3, active=0,
                                 sessions=0, features=0)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "dormant.json")
            write_records(rows, path)
            code, out, _ = run_cli(["check", "--input", path])
            self.assertEqual(code, EXIT_FAIL)
            self.assertIn("FAIL", out)

    def test_input_file_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "seeded.json")
            write_records(generate_records(), path)
            code, out, _ = run_cli(["report", "--input", path])
            self.assertEqual(code, EXIT_OK)
            self.assertEqual(json.loads(out)["records"], 2400)


class TestServe(unittest.TestCase):
    def setUp(self):
        self.records = generate_records()
        reset_state(self.records)
        self.server = make_server(0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        reset_state()

    def _req(self, path, payload=None, method="GET"):
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"} if data else {}
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=data,
            headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read())

    def test_health_endpoint(self):
        status, body = self._req("/health")
        self.assertEqual((status, body), (200, {"status": "ok"}))

    def test_post_report_seeded(self):
        status, body = self._req("/report", payload={}, method="POST")
        self.assertEqual(status, 200)
        self.assertEqual(body, build_report(self.records))

    def test_post_report_explicit(self):
        status, body = self._req("/report",
                                 payload={"records": self.records},
                                 method="POST")
        self.assertEqual(status, 200)
        self.assertEqual(body["activation"]["activated"], 101)

    def test_get_report(self):
        status, body = self._req("/report")
        self.assertEqual(status, 200)
        self.assertEqual(body["accounts"], 120)

    def test_unknown_endpoint_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._req("/nope")
        self.assertEqual(ctx.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
