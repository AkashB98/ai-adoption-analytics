"""Customer-health tiers, the stable health contract, and
usage-anomaly flags.

Health tiers are RULE-BASED and the rules live here as data
(``HEALTH_RULES``), evaluated in order - first match wins:

  dormant   no active users in either of the last two observed weeks
  thriving  utilization score >= 0.60 AND feature breadth >= 0.50
            AND seat utilization >= 0.35 (all on the last week)
  at-risk   utilization score < 0.30 OR seat utilization < 0.08
  steady    everything else

STABLE CONTRACT: ``health_contract`` emits the tiers as a versioned
data contract (schema ``HEALTH_CONTRACT_VERSION``) for downstream
consumers - a future renewals-forecasting repo is the named first
consumer. Contract records carry exactly ``HEALTH_CONTRACT_FIELDS``,
in that order, sorted by account_id, in JSON and CSV forms that
agree field-for-field. Within a major version, fields are never
removed, renamed, or retyped; new fields are only appended.

Anomaly method (pinned, the ONLY method): rolling median / MAD.
For each week with at least 4 prior observed weeks, the baseline is
the *median* sessions of the previous 4 weeks and the spread is the
MAD (median absolute deviation - the median of |x - median| over
the same window). The robust z-score is
``0.6745 * (current - median) / MAD`` (0.6745 scales MAD to be
comparable to a standard deviation for well-behaved data). A week
flags ``sudden_drop`` iff robust z <= -3.5. Special case: when
MAD == 0 (a perfectly flat baseline), any week below the median
flags - a deviation from a flat baseline is maximally surprising,
and the robust z is reported as the sentinel -999.9 (the true value
is unbounded and a literal infinity is not JSON-safe). Median/MAD
is used because a mean and standard deviation are dragged around by
the very spikes being hunted; the median barely moves.
"""

from __future__ import annotations

import csv
import io
import json
import statistics
from typing import Dict, List

from generator import records_by_account
from utilization import account_utilization, all_utilization

HEALTH_TIERS = ("thriving", "steady", "at-risk", "dormant")

HEALTH_RULES = [
    {"tier": "dormant", "kind": "trailing_inactivity",
     "last_n_weeks": 2, "max_total_active_users": 0},
    {"tier": "thriving", "kind": "min_thresholds",
     "min_utilization_score": 0.60, "min_feature_breadth": 0.50,
     "min_seat_utilization": 0.35},
    {"tier": "at-risk", "kind": "below_thresholds",
     "max_utilization_score": 0.30, "max_seat_utilization": 0.08},
    {"tier": "steady", "kind": "fallback"},
]

# ------------------------------------------------------- health contract

HEALTH_CONTRACT_VERSION = "1.0"
HEALTH_CONTRACT_FIELDS = [
    "account_id",        # str: stable account identifier
    "account_name",      # str: fictional account name
    "cohort",            # str: rollout month, YYYY-MM
    "segment",           # str: smb / midmarket / enterprise
    "health_tier",       # str: one of HEALTH_TIERS
    "utilization_score", # float: 0..1, see utilization.py
    "seat_utilization",  # float: 0..1, last observed week
    "feature_breadth",   # float: 0..1, last observed week
    "active_users",      # int: last observed week
    "licensed_seats",    # int
    "week_start",        # str: ISO date of the last observed week
]

# ------------------------------------------------------------- anomalies

ANOMALY_BASELINE_WEEKS = 4
ANOMALY_ROBUST_Z_THRESHOLD = -3.5
ROBUST_Z_SCALE = 0.6745
FLAT_BASELINE_Z = -999.9  # sentinel when MAD == 0 and current < median

# Share of accounts in (at-risk + dormant) above which `check` fails.
AT_RISK_SHARE_THRESHOLD = 0.50


def _r6(x: float) -> float:
    return round(x, 6)


def classify_health(util: Dict, rows: List[Dict]) -> str:
    ordered = sorted(rows, key=lambda r: r["weeks_since_rollout"])
    for rule in HEALTH_RULES:
        tier, kind = rule["tier"], rule["kind"]
        if kind == "trailing_inactivity":
            tail = ordered[-rule["last_n_weeks"]:]
            if sum(r["active_users"] for r in tail) <= \
                    rule["max_total_active_users"]:
                return tier
        elif kind == "min_thresholds":
            if (util["utilization_score"] >= rule["min_utilization_score"]
                    and util["feature_breadth"] >= rule["min_feature_breadth"]
                    and util["seat_utilization"]
                    >= rule["min_seat_utilization"]):
                return tier
        elif kind == "below_thresholds":
            if (util["utilization_score"] < rule["max_utilization_score"]
                    or util["seat_utilization"]
                    < rule["max_seat_utilization"]):
                return tier
        elif kind == "fallback":
            return tier
    return "steady"  # pragma: no cover - fallback rule always returns


def health_for_accounts(records: List[Dict]) -> List[Dict]:
    grouped = records_by_account(records)
    out = []
    for util in all_utilization(records):
        aid = util["account_id"]
        entry = dict(util)
        entry["health_tier"] = classify_health(util, grouped[aid])
        out.append(entry)
    return out


def health_summary(records: List[Dict]) -> Dict:
    per = health_for_accounts(records)
    counts = {tier: 0 for tier in HEALTH_TIERS}
    for entry in per:
        counts[entry["health_tier"]] += 1
    total = len(per)
    at_risk_share = _r6((counts["at-risk"] + counts["dormant"]) / total) \
        if total else 0.0
    return {
        "accounts": total,
        "tiers": counts,
        "tier_shares": {t: (_r6(counts[t] / total) if total else 0.0)
                        for t in HEALTH_TIERS},
        "at_risk_share": at_risk_share,
        "at_risk_threshold": AT_RISK_SHARE_THRESHOLD,
        "within_threshold": at_risk_share <= AT_RISK_SHARE_THRESHOLD,
        "per_account": per,
    }


# ------------------------------------------------------- health contract

def health_contract(records: List[Dict]) -> List[Dict]:
    """Contract records: exactly HEALTH_CONTRACT_FIELDS, in order,
    sorted by account_id (health_for_accounts is already sorted)."""
    out = []
    for entry in health_for_accounts(records):
        out.append({field: entry[field]
                    for field in HEALTH_CONTRACT_FIELDS})
    return out


def health_contract_document(records: List[Dict]) -> Dict:
    return {"schema_version": HEALTH_CONTRACT_VERSION,
            "fields": list(HEALTH_CONTRACT_FIELDS),
            "tiers": list(HEALTH_TIERS),
            "records": health_contract(records)}


def health_contract_json(records: List[Dict]) -> str:
    return json.dumps(health_contract_document(records),
                      sort_keys=True) + "\n"


def health_contract_csv(records: List[Dict]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=HEALTH_CONTRACT_FIELDS,
                            lineterminator="\n")
    writer.writeheader()
    for row in health_contract(records):
        writer.writerow(row)
    return buf.getvalue()


# ------------------------------------------------------------- anomalies

def robust_z(current: float, median: float, mad: float) -> float:
    """Robust z-score; sentinel when MAD == 0 (see module docstring)."""
    if mad == 0:
        if current < median:
            return FLAT_BASELINE_Z
        if current > median:
            return 999.9
        return 0.0
    return _r6(ROBUST_Z_SCALE * (current - median) / mad)


def detect_anomalies(records: List[Dict]) -> List[Dict]:
    grouped = records_by_account(records)
    flags: List[Dict] = []
    for aid in sorted(grouped):
        rows = grouped[aid]
        for idx in range(ANOMALY_BASELINE_WEEKS, len(rows)):
            window = [r["sessions"]
                      for r in rows[idx - ANOMALY_BASELINE_WEEKS:idx]]
            median = float(statistics.median(window))
            mad = float(statistics.median(
                [abs(x - median) for x in window]))
            current = rows[idx]["sessions"]
            z = robust_z(current, median, mad)
            if z <= ANOMALY_ROBUST_Z_THRESHOLD:
                flags.append({
                    "account_id": aid,
                    "account_name": rows[idx]["account_name"],
                    "week_start": rows[idx]["week_start"],
                    "weeks_since_rollout": rows[idx]["weeks_since_rollout"],
                    "kind": "sudden_drop",
                    "sessions": current,
                    "baseline_median_sessions": _r6(median),
                    "mad": _r6(mad),
                    "robust_z": z,
                })
    flags.sort(key=lambda f: (f["account_id"], f["weeks_since_rollout"]))
    return flags
