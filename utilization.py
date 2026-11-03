"""Utilization metrics, per account and overall.

Per-account utilization is judged on the account's *last observed
week* - the current state of the rollout, not a lifetime average
that would hide a recent collapse.

  seat utilization   active_users / licensed_seats (capped at 1.0)
  sessions per active user   sessions / active_users (0 if no actives)
  feature breadth    features_used / FEATURE_COUNT (features in use
                     out of the features available)
  utilization score  0.5 * seat_utilization
                     + 0.3 * min(sessions_per_active / 10, 1.0)
                     + 0.2 * feature_breadth
                     Weights are stated here, in one place, so the
                     score can be argued with and changed in one place.
"""

from __future__ import annotations

from typing import Dict, List

from generator import FEATURE_COUNT, records_by_account

SEAT_WEIGHT = 0.5
SESSION_WEIGHT = 0.3
BREADTH_WEIGHT = 0.2
SESSIONS_PER_ACTIVE_TARGET = 10.0


def _r6(x: float) -> float:
    return round(x, 6)


def seat_utilization(active: int, seats: int) -> float:
    if seats <= 0:
        return 0.0
    return min(1.0, active / seats)


def sessions_per_active(sessions: int, active: int) -> float:
    if active <= 0:
        return 0.0
    return sessions / active


def feature_breadth(features_used: int) -> float:
    return features_used / FEATURE_COUNT


def utilization_score(seat_util: float, spa: float, breadth: float) -> float:
    return _r6(SEAT_WEIGHT * seat_util
               + SESSION_WEIGHT * min(spa / SESSIONS_PER_ACTIVE_TARGET, 1.0)
               + BREADTH_WEIGHT * breadth)


def account_utilization(rows: List[Dict]) -> Dict:
    """Utilization for one account from its last observed week."""
    if not rows:
        raise ValueError("account has no records")
    last = max(rows, key=lambda r: r["weeks_since_rollout"])
    su = seat_utilization(last["active_users"], last["licensed_seats"])
    spa = sessions_per_active(last["sessions"], last["active_users"])
    breadth = feature_breadth(last["features_used"])
    return {
        "account_id": last["account_id"],
        "account_name": last["account_name"],
        "cohort": last["cohort"],
        "segment": last["segment"],
        "week_start": last["week_start"],
        "licensed_seats": last["licensed_seats"],
        "active_users": last["active_users"],
        "sessions": last["sessions"],
        "seat_utilization": _r6(su),
        "sessions_per_active": _r6(spa),
        "feature_breadth": _r6(breadth),
        "utilization_score": utilization_score(su, spa, breadth),
        "prompts": last["prompts"],
        "prompts_per_active_seat": _r6(
            last["prompts"] / last["active_users"])
        if last["active_users"] else 0.0,
        "outputs_generated": last["outputs_generated"],
        "outputs_accepted": last["outputs_accepted"],
        "acceptance_rate": _r6(
            last["outputs_accepted"] / last["outputs_generated"])
        if last["outputs_generated"] else 0.0,
    }


def all_utilization(records: List[Dict]) -> List[Dict]:
    grouped = records_by_account(records)
    return [account_utilization(grouped[aid]) for aid in sorted(grouped)]


def utilization_summary(records: List[Dict]) -> Dict:
    per = all_utilization(records)
    n = len(per)
    if not n:
        return {"accounts": 0, "mean_utilization_score": 0.0,
                "mean_seat_utilization": 0.0, "total_licensed_seats": 0,
                "total_active_users_last_week": 0,
                "overall_seat_utilization": 0.0}
    total_seats = sum(p["licensed_seats"] for p in per)
    total_active = sum(p["active_users"] for p in per)
    return {
        "accounts": n,
        "mean_utilization_score": _r6(
            sum(p["utilization_score"] for p in per) / n),
        "mean_seat_utilization": _r6(
            sum(p["seat_utilization"] for p in per) / n),
        "mean_sessions_per_active": _r6(
            sum(p["sessions_per_active"] for p in per) / n),
        "mean_feature_breadth": _r6(
            sum(p["feature_breadth"] for p in per) / n),
        "total_licensed_seats": total_seats,
        "total_active_users_last_week": total_active,
        "overall_seat_utilization": _r6(total_active / total_seats)
        if total_seats else 0.0,
    }
