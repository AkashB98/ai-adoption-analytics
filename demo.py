"""End-to-end demo: generate -> cohorts -> utilization -> health
-> report -> check -> serve.

SYNTHETIC DATA ONLY (fictional accounts). Runs fully offline; the
serve round-trip is loopback-only on an ephemeral port.
Every stage asserts.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cli import main as cli_main, make_server, reset_state  # noqa: E402
from generator import generate_records  # noqa: E402
from report import build_report, format_report_text  # noqa: E402
from validation import validate_records  # noqa: E402


def _request(port: int, path: str, payload=None, method: str = "GET"):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                 data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, json.loads(resp.read())


def main() -> None:
    print("== 1. generate synthetic accounts (seed=42) ==")
    records = generate_records()
    again = generate_records()
    assert records == again, "generator must be deterministic"
    assert validate_records(records) == [], validate_records(records)[:3]
    print(f"   {len(records)} account-weeks, deterministic, clean")

    print("\n== 2. scorecard report ==")
    report = build_report(records)
    print(format_report_text(report), end="")
    assert report["accounts"] == 120
    assert report["activation"]["accounts"] == 120
    assert len(report["cohorts"]) == 4
    ai = report["ai_metrics"]
    assert ai["total_outputs_accepted"] <= ai["total_outputs_generated"]
    assert ai["accounts_with_first_success"] > 0
    contract = report["health_contract"]
    assert contract["schema_version"] == "1.0"
    assert len(contract["records"]) == 120
    print(f"   AI metrics: acceptance={ai['overall_acceptance_rate']:.1%}, "
          f"health contract v{contract['schema_version']} "
          f"({len(contract['records'])} records)")

    print("== 3. CLI check gate on the seeded dataset ==")
    code = cli_main(["check"])
    code_err = cli_main(["check", "--input", "/tmp/no-such-adopt-xyz.json"])
    print(f"   seeded={code} missing-file={code_err}")
    assert code_err == 2

    print("\n== 4. live localhost serve round-trip ==")
    reset_state(records)
    server = make_server(0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, health = _request(port, "/health")
        assert status == 200 and health == {"status": "ok"}
        status, served = _request(port, "/report", payload={}, method="POST")
        assert status == 200 and served == report, "empty body -> seeded"
        status, served2 = _request(port, "/report",
                                   payload={"records": records},
                                   method="POST")
        assert status == 200 and served2 == report
        print("   POST /report (seeded + explicit records) matches local")
    finally:
        server.shutdown()
        server.server_close()
        reset_state()

    print("\nDemo OK: generate, report, check and serve verified.")


if __name__ == "__main__":
    main()
