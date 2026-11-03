"""AI-specific adoption metrics.

Generic SaaS analytics (logins, seats, sessions) cannot tell you
whether an *AI* rollout is working. These metrics can:

  time to first successful AI task  Days from rollout to the first
      week with at least one accepted AI output, at weekly
      resolution: the week index times 7 (the start of that week).
      ``None`` if the account never produced an accepted output.
      This is the AI version of time-to-value: how long until a
      customer first got something out of the AI that they kept.
  prompts per active seat  Prompts / AI actions submitted per
      active user in the account's last observed week - how hard
      the people who show up actually lean on the AI.
  output acceptance rate  AI outputs accepted (kept) / AI outputs
      generated, cumulative over the account's observed weeks. The
      quality signal raw usage hides: heavy prompting with a low
      kept share means the AI is being fought, not adopted.
  feature breadth  Distinct AI features used / features available
      (last week, from utilization.py) - whether use is spreading
      across the AI surface or stuck in one corner of it.
"""

from __future__ import annotations

import statistics
from typing import Dict, List, Optional

from generator import COHORT_LABELS, accounts_of, records_by_account
from utilization import account_utilization


def _r6(x: float) -> float:
    return round(x, 6)


def time_to_first_success_days(rows: List[Dict]) -> Optional[int]:
    for r in sorted(rows, key=lambda x: x["weeks_since_rollout"]):
        if r["outputs_accepted"] >= 1:
            return r["weeks_since_rollout"] * 7
    return None


def account_ai_metrics(rows: List[Dict]) -> Dict:
    if not rows:
        raise ValueError("account has no records")
    last = max(rows, key=lambda r: r["weeks_since_rollout"])
    util = account_utilization(rows)
    generated = sum(r["outputs_generated"] for r in rows)
    accepted = sum(r["outputs_accepted"] for r in rows)
    return {
        "account_id": last["account_id"],
        "account_name": last["account_name"],
        "cohort": last["cohort"],
        "time_to_first_success_days": time_to_first_success_days(rows),
        "prompts_last_week": last["prompts"],
        "prompts_per_active_seat": _r6(
            last["prompts"] / last["active_users"])
        if last["active_users"] else 0.0,
        "outputs_generated_total": generated,
        "outputs_accepted_total": accepted,
        "acceptance_rate": _r6(accepted / generated) if generated else 0.0,
        "feature_breadth": util["feature_breadth"],
    }


def all_ai_metrics(records: List[Dict]) -> List[Dict]:
    grouped = records_by_account(records)
    return [account_ai_metrics(grouped[aid]) for aid in sorted(grouped)]


def _ttf_summary(values: List[int]) -> Dict:
    if not values:
        return {"median_days": None, "mean_days": None}
    return {"median_days": _r6(float(statistics.median(values))),
            "mean_days": _r6(sum(values) / len(values))}


def ai_metrics_summary(records: List[Dict]) -> Dict:
    per = all_ai_metrics(records)
    ttf = [p["time_to_first_success_days"] for p in per
           if p["time_to_first_success_days"] is not None]
    total_prompts = sum(r["prompts"] for r in records)
    total_generated = sum(r["outputs_generated"] for r in records)
    total_accepted = sum(r["outputs_accepted"] for r in records)
    by_cohort = []
    for label in COHORT_LABELS:
        members = [p for p in per if p["cohort"] == label]
        if not members:
            continue
        c_ttf = [p["time_to_first_success_days"] for p in members
                 if p["time_to_first_success_days"] is not None]
        entry = {"cohort": label, "accounts": len(members)}
        entry.update(_ttf_summary(c_ttf))
        by_cohort.append(entry)
    summary = {
        "accounts": len(per),
        "accounts_with_first_success": len(ttf),
        "share_first_success_in_week0": _r6(
            sum(1 for d in ttf if d == 0) / len(ttf)) if ttf else 0.0,
        "total_prompts": total_prompts,
        "prompts_per_active_seat_mean": _r6(
            sum(p["prompts_per_active_seat"] for p in per) / len(per))
        if per else 0.0,
        "total_outputs_generated": total_generated,
        "total_outputs_accepted": total_accepted,
        "overall_acceptance_rate": _r6(total_accepted / total_generated)
        if total_generated else 0.0,
        "mean_feature_breadth": _r6(
            sum(p["feature_breadth"] for p in per) / len(per)) if per else 0.0,
        "by_cohort": by_cohort,
        "per_account": per,
    }
    summary.update({f"time_to_first_success_{k}": v
                    for k, v in _ttf_summary(ttf).items()})
    return summary
