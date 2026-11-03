"""Golden evals for ai-adoption-analytics.

SYNTHETIC DATA ONLY (fictional accounts). Every eval is
deterministic: run_evals.py writes eval_report.json and the file
must be byte-identical across runs. No timestamps, ports, or temp
paths enter the report - only names, booleans, pinned counts and
hashes.

E1-E5 pin the seeded dataset and headline numbers. E6-E8 pin the
definitions on hand-computed cases. E9-E12 pin health tiers and the
anomaly method (rolling median / MAD, the only method). E13-E14 pin
the CLI gate, the serve round-trip, and the bundled fixture.
E15 pins the AI-specific metrics; E16 pins the health contract.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import threading
import urllib.request
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_metrics import time_to_first_success_days  # noqa: E402
from cli import EXIT_ERROR, EXIT_FAIL, EXIT_OK, main as cli_main, make_server, reset_state  # noqa: E402
from cohorts import is_activated, retention_at  # noqa: E402
from generator import generate_records, records_to_jsonl, write_records  # noqa: E402
from health import (HEALTH_CONTRACT_FIELDS, HEALTH_CONTRACT_VERSION,  # noqa: E402
                    HEALTH_RULES, classify_health, detect_anomalies,
                    health_contract, health_contract_csv,
                    health_contract_json)
from report import build_report  # noqa: E402
from utilization import utilization_score  # noqa: E402
from validation import validate_records  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RESULTS = []


def check(name, passed, detail=""):
    RESULTS.append({"name": name, "passed": bool(passed), "detail": detail})
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))
    return passed


def _run_cli(argv):
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return cli_main(argv)


def _mk(**kw):
    base = {"account_id": "acct_x", "account_name": "Eval Co",
            "cohort": "2026-01", "segment": "smb", "industry": "retail",
            "licensed_seats": 100, "week_start": "2026-01-05",
            "week_index": 0, "weeks_since_rollout": 0,
            "active_users": 10, "sessions": 50, "features_used": 4,
            "prompts": 150, "outputs_generated": 150,
            "outputs_accepted": 120}
    base.update(kw)
    return base


def _rows(sessions_list, active=10):
    return [_mk(week_index=w, weeks_since_rollout=w,
                active_users=active if s else 0, sessions=s,
                features_used=4 if s else 0,
                prompts=s * 3, outputs_generated=s * 3,
                outputs_accepted=int(s * 3 * 0.8))
            for w, s in enumerate(sessions_list)]


def main():
    print("== golden evals: ai-adoption-analytics ==")
    records = generate_records()
    report = build_report(records)

    # E1: generator determinism (bytes pinned)
    text1 = records_to_jsonl(generate_records())
    md5 = hashlib.md5(text1.encode()).hexdigest()
    check("E1 generator determinism (seed=42, jsonl md5 pinned)",
          text1 == records_to_jsonl(records)
          and md5 == "afeaf0f2457e34e2cfbb080202f3cdad",
          f"jsonl_md5={md5}")

    # E2: headline counts pinned
    check("E2 headline counts (120 accounts, 2400 records, clean)",
          report["accounts"] == 120 and report["records"] == 2400
          and validate_records(records) == [])

    # E3: activation pinned
    act = report["activation"]
    check("E3 activation pinned (101/120 = 0.841667)",
          act["activated"] == 101 and act["activation_rate"] == 0.841667
          and act["definition"]["min_active_users"] == 3
          and act["definition"]["min_sessions"] == 5
          and act["definition"]["window_weeks"] == [0, 1],
          f"rate={act['activation_rate']}")

    # E4: cohort table pinned
    cohorts = report["cohorts"]
    check("E4 cohorts pinned (rates + week-12 retention)",
          [c["activation_rate"] for c in cohorts]
          == [0.9, 0.833333, 0.866667, 0.766667]
          and [c["week12_retention"] for c in cohorts]
          == [0.851852, 0.88, 0.961538, 0.73913]
          and all(c["week4_retention"] == 1.0 for c in cohorts)
          and all(c["accounts"] == 30 for c in cohorts))

    # E5: utilization pinned
    util = report["utilization"]
    check("E5 utilization pinned (score 0.413675, seats 7807/28049)",
          util["mean_utilization_score"] == 0.413675
          and util["mean_seat_utilization"] == 0.294862
          and util["total_licensed_seats"] == 28049
          and util["total_active_users_last_week"] == 7807
          and util["overall_seat_utilization"] == 0.278334
          and util["mean_feature_breadth"] == 0.55625)

    # E6: utilization score hand-computed
    check("E6 score hand-computed (weights 0.5/0.3/0.2, spa capped)",
          utilization_score(0.5, 5.0, 0.5) == 0.5
          and utilization_score(1.0, 10.0, 1.0) == 1.0
          and utilization_score(0.0, 99.0, 0.0) == 0.3)

    # E7: activation definition on hand cases
    check("E7 activation window + floors (week-2 first use excluded)",
          is_activated(_rows([50, 50, 50]))
          and not is_activated(_rows([0, 0, 50]))
          and not is_activated([_mk(active_users=2, sessions=50)])
          and not is_activated([_mk(active_users=10, sessions=4)])
          and is_activated([_mk(active_users=3, sessions=5)]))

    # E8: retention denominator semantics
    rows = _rows([50, 50, 50, 50, 50, 50])
    rows[4] = _mk(week_index=4, weeks_since_rollout=4, active_users=0,
                  sessions=0, features_used=0)
    check("E8 retention semantics (unactivated/missing excluded)",
          retention_at(rows, 4) == (0, 1)
          and retention_at(_rows([50, 50]), 12) is None
          and retention_at(_rows([0, 0, 0]), 0) is None)

    # E9: health tiers pinned on seeded data
    health = report["health"]
    check("E9 health tiers pinned (37/34/25/24, share 0.408333)",
          health["tiers"] == {"thriving": 37, "steady": 34,
                              "at-risk": 25, "dormant": 24}
          and health["at_risk_share"] == 0.408333
          and health["within_threshold"]
          and health["at_risk_threshold"] == 0.5)

    # E10: health rules as data, order and hand cases
    util_ok = {"utilization_score": 0.7, "feature_breadth": 0.75,
               "seat_utilization": 0.5}
    check("E10 health rules order + hand cases",
          [r["tier"] for r in HEALTH_RULES]
          == ["dormant", "thriving", "at-risk", "steady"]
          and classify_health(util_ok, _rows([50, 50])) == "thriving"
          and classify_health(util_ok, _rows([0, 0])) == "dormant"
          and classify_health({"utilization_score": 0.2,
                               "feature_breadth": 0.5,
                               "seat_utilization": 0.5},
                              _rows([50, 50])) == "at-risk")

    # E11: anomalies pinned on seeded data + all planted drops caught
    anomalies = report["anomalies"]
    planted = {"acct_016", "acct_026", "acct_041", "acct_046", "acct_051"}
    caught_at_15 = {a["account_id"] for a in anomalies
                    if a["weeks_since_rollout"] == 15}
    check("E11 anomalies pinned (125 flags, 72 accounts, plants caught)",
          report["anomaly_count"] == 125
          and report["anomaly_accounts"] == 72
          and anomalies[0]["account_id"] == "acct_002"
          and anomalies[0]["robust_z"] == -4.24935
          and anomalies[0]["baseline_median_sessions"] == 177.0
          and all(a["kind"] == "sudden_drop" for a in anomalies)
          and planted <= caught_at_15,
          f"planted_caught={sorted(planted & caught_at_15)}")

    # E12: anomaly method on hand cases (rolling median / MAD only)
    hand = detect_anomalies(_rows([100, 110, 90, 100, 40]))
    check("E12 MAD hand cases (z=-8.094 flags; noise/variance hold)",
          len(hand) == 1 and hand[0]["robust_z"] == -8.094
          and hand[0]["mad"] == 5.0
          and detect_anomalies(_rows([100, 110, 90, 100, 85])) == []
          and detect_anomalies(_rows([50, 150, 50, 150, 40])) == []
          and detect_anomalies(_rows([100, 100, 10])) == []
          and detect_anomalies(_rows([100, 100, 100, 100, 50]))[0]
          ["robust_z"] == -999.9)

    # E13: CLI check exit codes 0 / 1 / 2
    import tempfile
    tmp = tempfile.mkdtemp(prefix="adopt-evals-")
    dormant = []
    for n in range(4):
        dormant += [_mk(account_id=f"acct_d{n}", week_index=w,
                        weeks_since_rollout=w, active_users=0,
                        sessions=0, features_used=0, prompts=0,
                        outputs_generated=0, outputs_accepted=0)
                    for w in range(3)]
    bad_path = os.path.join(tmp, "dormant.json")
    write_records(dormant, bad_path)
    codes = (_run_cli(["check"]),
             _run_cli(["check", "--input", bad_path]),
             _run_cli(["check", "--input", "/tmp/no-such-adopt-xyz.json"]))
    check("E13 CLI check exit codes 0/1/2",
          codes == (EXIT_OK, EXIT_FAIL, EXIT_ERROR), f"codes={codes}")

    # E14: serve round-trip + bundled fixture
    with open(os.path.join(ROOT, "fixtures", "example_records.json"),
              encoding="utf-8") as fh:
        fixture = json.load(fh)
    fixture_report = build_report(fixture)
    reset_state(records)
    server = make_server(0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        def _post(payload):
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/report",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        serve_ok = _post({}) == report and _post({"records": records}) == report
    finally:
        server.shutdown()
        server.server_close()
        reset_state()
    check("E14 serve round-trip + fixture (2 accounts, 1 activated)",
          serve_ok
          and validate_records(fixture) == []
          and fixture_report["accounts"] == 2
          and fixture_report["activation"]["activated"] == 1
          and fixture_report["health"]["tiers"]["dormant"] == 1)

    # E15: AI-specific metrics pinned (time-to-first-success,
    # prompts per active seat, acceptance rate, feature breadth)
    ai = report["ai_metrics"]
    ttf_rows = _rows([50, 50, 50])
    ttf_rows[0]["outputs_accepted"] = 0
    ttf_rows[1]["outputs_accepted"] = 0
    check("E15 AI metrics pinned (acceptance 0.770089, ttf median 0)",
          ai["overall_acceptance_rate"] == 0.770089
          and ai["total_prompts"] == 3182142
          and ai["total_outputs_accepted"] == 2450533
          and ai["prompts_per_active_seat_mean"] == 16.440152
          and ai["time_to_first_success_median_days"] == 0.0
          and ai["time_to_first_success_mean_days"] == 2.333333
          and ai["share_first_success_in_week0"] == 0.733333
          and ai["mean_feature_breadth"] == 0.55625
          and time_to_first_success_days(ttf_rows) == 14
          and time_to_first_success_days(_rows([50])) == 0,
          f"acceptance={ai['overall_acceptance_rate']}")

    # E16: health contract pinned (version, fields, CSV/JSON agreement)
    contract = health_contract(records)
    csv_lines = health_contract_csv(records).splitlines()
    doc = json.loads(health_contract_json(records))
    check("E16 health contract v1.0 (fields, order, CSV=JSON tiers)",
          HEALTH_CONTRACT_VERSION == "1.0"
          and report["health_contract"]["schema_version"] == "1.0"
          and doc["fields"] == HEALTH_CONTRACT_FIELDS
          and all(list(r.keys()) == HEALTH_CONTRACT_FIELDS
                  for r in contract)
          and contract[0]["account_id"] == "acct_001"
          and contract[0]["health_tier"] == "steady"
          and csv_lines[0] == ",".join(HEALTH_CONTRACT_FIELDS)
          and len(csv_lines) == 121
          and len(doc["records"]) == 120)

    passed = sum(1 for r in RESULTS if r["passed"])
    total_n = len(RESULTS)
    summary_doc = {"passed": passed, "total": total_n,
                   "all_passed": passed == total_n, "evals": RESULTS}
    with open(os.path.join(HERE, "eval_report.json"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(summary_doc, sort_keys=True) + "\n")
    print(f"\n{passed}/{total_n} evals passed -> evals/eval_report.json")
    return 0 if passed == total_n else 1


if __name__ == "__main__":
    sys.exit(main())
