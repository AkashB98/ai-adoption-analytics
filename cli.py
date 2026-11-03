"""CLI: generate | cohorts | utilization | health | ai-metrics |
health-contract | report | check | demo | serve.

SYNTHETIC DATA ONLY - every account is fictional and every dataset
handled here is fabricated sample data.

Exit codes:
  check : 0 = at-risk share within the stated threshold,
          1 = at-risk share breaches the threshold,
          2 = usage / IO / data-quality error
  others: 0 = success, 2 = usage / IO error

Commands without --input run on the seeded dataset (seed 42).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai_metrics import ai_metrics_summary  # noqa: E402
from cohorts import cohort_summary, overall_activation  # noqa: E402
from generator import DEFAULT_SEED, generate_records, load_records, write_records  # noqa: E402
from health import (health_contract_csv, health_contract_json,  # noqa: E402
                    health_summary)
from report import build_report, format_report_text  # noqa: E402
from utilization import utilization_summary  # noqa: E402
from validation import validate_records  # noqa: E402

EXIT_OK, EXIT_FAIL, EXIT_ERROR = 0, 1, 2


def canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True)


def _records_or_error(args):
    if not getattr(args, "input", None):
        return generate_records(), EXIT_OK
    try:
        records = load_records(args.input)
    except FileNotFoundError:
        print(f"error: file not found: {args.input}", file=sys.stderr)
        return None, EXIT_ERROR
    except (ValueError, OSError) as exc:
        print(f"error: cannot read {args.input}: {exc}", file=sys.stderr)
        return None, EXIT_ERROR
    issues = validate_records(records)
    if issues:
        for issue in issues[:20]:
            print(f"data-quality: {issue}", file=sys.stderr)
        return None, EXIT_ERROR
    return records, EXIT_OK


def _write_out(args, text: str, summary: str) -> int:
    if getattr(args, "out", None):
        try:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(text)
        except OSError as exc:
            print(f"error: cannot write {args.out}: {exc}", file=sys.stderr)
            return EXIT_ERROR
        print(summary)
    else:
        print(text, end="")
    return EXIT_OK


def cmd_generate(args) -> int:
    records = generate_records(seed=args.seed)
    if args.out:
        try:
            write_records(records, args.out)
        except OSError as exc:
            print(f"error: cannot write {args.out}: {exc}", file=sys.stderr)
            return EXIT_ERROR
        print(f"generated {len(records)} synthetic account-weeks "
              f"(seed={args.seed}) -> {args.out}")
        return EXIT_OK
    from generator import records_to_json
    print(records_to_json(records), end="")
    return EXIT_OK


def cmd_cohorts(args) -> int:
    records, code = _records_or_error(args)
    if records is None:
        return code
    payload = {"activation": overall_activation(records),
               "cohorts": cohort_summary(records)}
    return _write_out(args, canonical(payload) + "\n",
                      f"cohorts -> {args.out}")


def cmd_utilization(args) -> int:
    records, code = _records_or_error(args)
    if records is None:
        return code
    return _write_out(args, canonical(utilization_summary(records)) + "\n",
                      f"utilization -> {args.out}")


def cmd_health(args) -> int:
    records, code = _records_or_error(args)
    if records is None:
        return code
    payload = health_summary(records)
    payload.pop("per_account", None)
    from health import detect_anomalies
    payload["anomalies"] = detect_anomalies(records)
    return _write_out(args, canonical(payload) + "\n",
                      f"health -> {args.out}")


def cmd_ai_metrics(args) -> int:
    records, code = _records_or_error(args)
    if records is None:
        return code
    payload = ai_metrics_summary(records)
    payload.pop("per_account", None)
    return _write_out(args, canonical(payload) + "\n",
                      f"ai-metrics -> {args.out}")


def cmd_health_contract(args) -> int:
    records, code = _records_or_error(args)
    if records is None:
        return code
    if getattr(args, "format", "json") == "csv":
        return _write_out(args, health_contract_csv(records),
                          f"health-contract -> {args.out}")
    return _write_out(args, health_contract_json(records),
                      f"health-contract -> {args.out}")


def cmd_report(args) -> int:
    records, code = _records_or_error(args)
    if records is None:
        return code
    report = build_report(records)
    if getattr(args, "format", "json") == "text":
        return _write_out(args, format_report_text(report),
                          f"report -> {args.out}")
    return _write_out(args, canonical(report) + "\n",
                      f"report -> {args.out}")


def cmd_check(args) -> int:
    records, code = _records_or_error(args)
    if records is None:
        return code
    report = build_report(records)
    health = report["health"]
    print(f"activation_rate={report['activation']['activation_rate']}")
    print(f"health_tiers={health['tiers']}")
    print(f"at_risk_share={health['at_risk_share']} "
          f"threshold={health['at_risk_threshold']}")
    if not health["within_threshold"]:
        print("check FAIL: at-risk share breaches threshold")
        return EXIT_FAIL
    print("check PASS")
    return EXIT_OK


def cmd_demo(args) -> int:
    import demo as demo_mod
    try:
        demo_mod.main()
    except AssertionError as exc:
        print(f"demo FAILED: {exc}", file=sys.stderr)
        return EXIT_FAIL
    return EXIT_OK


# ------------------------------------------------------------------- serve

class _State:
    def __init__(self):
        self.records: List[Dict] = generate_records()


_STATE = _State()


def get_state() -> _State:
    return _STATE


def reset_state(records: Optional[List[Dict]] = None) -> None:
    _STATE.records = list(records) if records is not None \
        else generate_records()


class _Handler(BaseHTTPRequestHandler):
    def _send_json(self, code: int, payload: Any) -> None:
        body = (canonical(payload) + "\n").encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            return self._send_json(200, {"status": "ok"})
        if self.path == "/report":
            return self._send_json(200, build_report(_STATE.records))
        return self._send_json(404, {"error": "unknown endpoint"})

    def do_POST(self):  # noqa: N802
        if self.path != "/report":
            return self._send_json(404, {"error": "unknown endpoint"})
        length = int(self.headers.get("Content-Length", 0) or 0)
        try:
            raw = self.rfile.read(length) if length else b""
            body = json.loads(raw) if raw.strip() else {}
            if not isinstance(body, dict):
                raise ValueError("expected a JSON object")
            records = body.get("records", _STATE.records)
            issues = validate_records(records)
            if issues:
                raise ValueError(f"invalid records: {issues[0]}")
            return self._send_json(200, build_report(records))
        except (ValueError, TypeError, KeyError) as exc:
            return self._send_json(400, {"error": f"bad request: {exc}"})

    def log_message(self, *a: Any) -> None:
        pass


def make_server(port: int) -> HTTPServer:
    return HTTPServer(("127.0.0.1", port), _Handler)


def cmd_serve(args) -> int:
    if args.input:
        records, code = _records_or_error(args)
        if records is None:
            return code
        reset_state(records)
    server = make_server(args.port)
    print(f"serving on http://127.0.0.1:{args.port}  "
          f"(POST /report, GET /report, GET /health)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ai-adoption-analytics",
        description="AI-rollout adoption scorecard (synthetic data).")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="generate the synthetic dataset")
    g.add_argument("--seed", type=int, default=DEFAULT_SEED)
    g.add_argument("--out", default=None)
    g.set_defaults(func=cmd_generate)

    for name, fn, helptext in (
            ("cohorts", cmd_cohorts, "cohort adoption + retention"),
            ("utilization", cmd_utilization, "utilization summary"),
            ("health", cmd_health, "health tiers + anomaly flags"),
            ("check", cmd_check, "CI gate: exit 0 pass / 1 breach / 2 error")):
        s = sub.add_parser(name, help=helptext)
        s.add_argument("--input", default=None)
        s.add_argument("--out", default=None)
        s.set_defaults(func=fn)

    a = sub.add_parser("ai-metrics", help="AI-specific metrics summary")
    a.add_argument("--input", default=None)
    a.add_argument("--out", default=None)
    a.set_defaults(func=cmd_ai_metrics)

    h = sub.add_parser("health-contract",
                       help="health tiers as the stable v1.0 contract")
    h.add_argument("--input", default=None)
    h.add_argument("--out", default=None)
    h.add_argument("--format", choices=("json", "csv"), default="json")
    h.set_defaults(func=cmd_health_contract)

    r = sub.add_parser("report", help="full scorecard report")
    r.add_argument("--input", default=None)
    r.add_argument("--out", default=None)
    r.add_argument("--format", choices=("json", "text"), default="json")
    r.set_defaults(func=cmd_report)

    sub.add_parser("demo", help="run the end-to-end demo").set_defaults(
        func=cmd_demo)

    s = sub.add_parser("serve", help="localhost JSON API")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--input", default=None)
    s.set_defaults(func=cmd_serve)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
