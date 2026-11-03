"""Data-quality gate for account-week records.

Reports issues, never raises on bad data, so the CLI ``check`` gate
can map data problems to exit code 2 - distinct from a health breach
(exit 1). Enforces the int/bool trap: in Python ``True`` is an
``int``, so counts must be checked as real ints before range checks.
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List

from generator import COHORT_LABELS, FEATURE_COUNT, INDUSTRIES, SEGMENTS

_INT_FIELDS = ("licensed_seats", "week_index", "weeks_since_rollout",
               "active_users", "sessions", "features_used", "prompts",
               "outputs_generated", "outputs_accepted")


def _parse_date(text):
    return date.fromisoformat(text)


def validate_record(rec) -> List[str]:
    if not isinstance(rec, dict):
        return ["record is not an object"]
    issues = []
    if not isinstance(rec.get("account_id"), str) or not rec.get("account_id"):
        issues.append("account_id must be a non-empty string")
    if not isinstance(rec.get("account_name"), str) \
            or not rec.get("account_name"):
        issues.append("account_name must be a non-empty string")
    if rec.get("cohort") not in COHORT_LABELS:
        issues.append(f"cohort must be one of {COHORT_LABELS}")
    if rec.get("segment") not in SEGMENTS:
        issues.append(f"segment must be one of {list(SEGMENTS)}")
    if rec.get("industry") not in INDUSTRIES:
        issues.append("industry must be a known industry label")
    try:
        _parse_date(rec.get("week_start", ""))
    except (ValueError, TypeError, AttributeError):
        issues.append("week_start must be ISO date (YYYY-MM-DD)")
    for field in _INT_FIELDS:
        value = rec.get(field)
        if isinstance(value, bool) or not isinstance(value, int):
            issues.append(f"{field} must be an int")
        elif value < 0:
            issues.append(f"{field} must be >= 0")
    seats, active = rec.get("licensed_seats"), rec.get("active_users")
    if isinstance(seats, int) and not isinstance(seats, bool) \
            and isinstance(active, int) and not isinstance(active, bool):
        if seats <= 0:
            issues.append("licensed_seats must be > 0")
        if active > seats:
            issues.append("active_users must be <= licensed_seats")
    feats = rec.get("features_used")
    if isinstance(feats, int) and not isinstance(feats, bool) \
            and feats > FEATURE_COUNT:
        issues.append(f"features_used must be <= {FEATURE_COUNT}")
    sess, act = rec.get("sessions"), rec.get("active_users")
    if isinstance(sess, int) and isinstance(act, int) \
            and not isinstance(sess, bool) and not isinstance(act, bool):
        if act == 0 and sess != 0:
            issues.append("sessions must be 0 when active_users is 0")
        if act == 0 and isinstance(feats, int) and feats != 0:
            issues.append("features_used must be 0 when active_users is 0")
    gen, acc = rec.get("outputs_generated"), rec.get("outputs_accepted")
    if isinstance(gen, int) and isinstance(acc, int) \
            and not isinstance(gen, bool) and not isinstance(acc, bool):
        if acc > gen:
            issues.append("outputs_accepted must be <= outputs_generated")
    prompts = rec.get("prompts")
    if isinstance(act, int) and not isinstance(act, bool) and act == 0:
        for field, value in (("prompts", prompts),
                             ("outputs_generated", gen),
                             ("outputs_accepted", acc)):
            if isinstance(value, int) and not isinstance(value, bool) \
                    and value != 0:
                issues.append(f"{field} must be 0 when active_users is 0")
    return issues


def validate_records(records) -> List[str]:
    if not isinstance(records, list):
        return ["dataset is not a list"]
    issues: List[str] = []
    seen = set()
    if not records:
        issues.append("dataset is empty")
    for i, rec in enumerate(records):
        for issue in validate_record(rec):
            issues.append(f"record[{i}]: {issue}")
        if isinstance(rec, dict):
            key = (rec.get("account_id"), rec.get("week_index"))
            if key in seen:
                issues.append(f"record[{i}]: duplicate (account, week) {key}")
            seen.add(key)
        if len(issues) > 50:
            break
    return issues
