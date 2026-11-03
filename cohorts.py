"""Cohort adoption: activation and retention, defined precisely.

Definitions (pinned by unit tests and golden evals):

  activation  An account is *activated* iff, in at least one of its
              first two observed weeks (weeks_since_rollout 0 or 1),
              it records active_users >= 3 AND sessions >= 5. "First
              real use" means a team actually used the product, not a
              single curious login - hence both a user floor and a
              session floor inside a fixed 14-day window.
  activation rate  activated accounts / all accounts in the cohort.
  week-N retention  Among *activated* accounts that have an observed
              record at week N (weeks_since_rollout == N), the share
              with active_users > 0 in that week. Accounts without a
              week-N record are excluded from the denominator - they
              have not had the chance to be retained yet - never
              silently counted as churned.
"""

from __future__ import annotations

from typing import Dict, List

from generator import COHORT_LABELS, accounts_of, records_by_account

ACTIVATION_WEEKS = (0, 1)
ACTIVATION_MIN_ACTIVE = 3
ACTIVATION_MIN_SESSIONS = 5
RETENTION_WEEKS = (4, 12)


def _r6(x: float) -> float:
    return round(x, 6)


def is_activated(rows: List[Dict]) -> bool:
    for r in rows:
        if r["weeks_since_rollout"] in ACTIVATION_WEEKS:
            if (r["active_users"] >= ACTIVATION_MIN_ACTIVE
                    and r["sessions"] >= ACTIVATION_MIN_SESSIONS):
                return True
    return False


def activation_week(rows: List[Dict]):
    """First week meeting the activation bar, or None."""
    for r in sorted(rows, key=lambda x: x["weeks_since_rollout"]):
        if r["weeks_since_rollout"] in ACTIVATION_WEEKS and \
                r["active_users"] >= ACTIVATION_MIN_ACTIVE and \
                r["sessions"] >= ACTIVATION_MIN_SESSIONS:
            return r["weeks_since_rollout"]
    return None


def retention_at(rows: List[Dict], week: int):
    """(retained, eligible) for one account at one week, or None if
    the account is not activated or has no record at that week."""
    if not is_activated(rows):
        return None
    for r in rows:
        if r["weeks_since_rollout"] == week:
            return (1 if r["active_users"] > 0 else 0, 1)
    return None


def cohort_summary(records: List[Dict]) -> List[Dict]:
    grouped = records_by_account(records)
    accounts = {a["account_id"]: a for a in accounts_of(records)}
    out = []
    for label in COHORT_LABELS:
        ids = [aid for aid, a in accounts.items() if a["cohort"] == label]
        if not ids:
            continue
        activated = sum(1 for aid in ids if is_activated(grouped[aid]))
        entry = {
            "cohort": label,
            "accounts": len(ids),
            "activated": activated,
            "activation_rate": _r6(activated / len(ids)) if ids else 0.0,
        }
        for week in RETENTION_WEEKS:
            retained = eligible = 0
            for aid in ids:
                res = retention_at(grouped[aid], week)
                if res is not None:
                    retained += res[0]
                    eligible += res[1]
            entry[f"week{week}_retention"] = (
                _r6(retained / eligible) if eligible else None)
            entry[f"week{week}_eligible"] = eligible
            entry[f"week{week}_retained"] = retained
        out.append(entry)
    return out


def overall_activation(records: List[Dict]) -> Dict:
    grouped = records_by_account(records)
    total = len(grouped)
    activated = sum(1 for rows in grouped.values() if is_activated(rows))
    return {
        "accounts": total,
        "activated": activated,
        "activation_rate": _r6(activated / total) if total else 0.0,
        "definition": {
            "window_weeks": list(ACTIVATION_WEEKS),
            "min_active_users": ACTIVATION_MIN_ACTIVE,
            "min_sessions": ACTIVATION_MIN_SESSIONS,
        },
    }
