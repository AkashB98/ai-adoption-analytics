"""Scorecard report assembly: JSON structure + readable text.

The report is a pure function of the records: cohorts, utilization,
health tiers, and anomaly flags, assembled once so the CLI, the
serve endpoint, and the evals all read exactly the same numbers.
"""

from __future__ import annotations

from typing import Dict, List

from ai_metrics import ai_metrics_summary
from cohorts import cohort_summary, overall_activation
from generator import accounts_of
from health import (HEALTH_CONTRACT_VERSION, detect_anomalies,
                    health_contract, health_summary)
from utilization import utilization_summary


def build_report(records: List[Dict]) -> Dict:
    accounts = accounts_of(records)
    health = health_summary(records)
    anomalies = detect_anomalies(records)
    per_account_health = health.pop("per_account")
    ai = ai_metrics_summary(records)
    ai_per_account = ai.pop("per_account")
    return {
        "accounts": len(accounts),
        "records": len(records),
        "cohorts_list": sorted({a["cohort"] for a in accounts}),
        "activation": overall_activation(records),
        "cohorts": cohort_summary(records),
        "utilization": utilization_summary(records),
        "ai_metrics": ai,
        "ai_metrics_per_account": ai_per_account,
        "health": health,
        "health_per_account": per_account_health,
        "health_contract": {
            "schema_version": HEALTH_CONTRACT_VERSION,
            "records": health_contract(records),
        },
        "anomalies": anomalies,
        "anomaly_count": len(anomalies),
        "anomaly_accounts": len({a["account_id"] for a in anomalies}),
    }


def format_report_text(report: Dict) -> str:
    lines = []
    act = report["activation"]
    lines.append("AI ADOPTION SCORECARD")
    lines.append(f"Accounts: {report['accounts']}  "
                 f"Records: {report['records']}")
    lines.append(f"Activation: {act['activated']}/{act['accounts']} "
                 f"({act['activation_rate']:.1%}) - activated = >=3 active "
                 f"users and >=5 sessions in week 0 or 1")
    lines.append("")
    lines.append("Cohorts:")
    for c in report["cohorts"]:
        w4 = c["week4_retention"]
        w12 = c["week12_retention"]
        lines.append(
            f"  {c['cohort']}: n={c['accounts']} "
            f"activation={c['activation_rate']:.1%} "
            f"week4_retention={w4:.1%}" if w4 is not None else
            f"  {c['cohort']}: n={c['accounts']} "
            f"activation={c['activation_rate']:.1%}")
        if w12 is not None:
            lines[-1] += f" week12_retention={w12:.1%}"
    util = report["utilization"]
    lines.append("")
    lines.append("Utilization (last observed week):")
    lines.append(f"  mean score={util['mean_utilization_score']:.3f} "
                 f"mean seat utilization={util['mean_seat_utilization']:.1%} "
                 f"overall seats active="
                 f"{util['total_active_users_last_week']}/"
                 f"{util['total_licensed_seats']} "
                 f"({util['overall_seat_utilization']:.1%})")
    ai = report["ai_metrics"]
    lines.append("")
    lines.append("AI-specific metrics:")
    lines.append(f"  time to first successful AI task: median "
                 f"{ai['time_to_first_success_median_days']:.0f} days, "
                 f"mean {ai['time_to_first_success_mean_days']:.1f} days "
                 f"({ai['accounts_with_first_success']}/"
                 f"{ai['accounts']} accounts reached a first kept output)")
    lines.append(f"  prompts per active seat (mean, last week): "
                 f"{ai['prompts_per_active_seat_mean']:.1f} "
                 f"from {ai['total_prompts']} prompts overall")
    lines.append(f"  AI outputs accepted / kept: "
                 f"{ai['total_outputs_accepted']}/"
                 f"{ai['total_outputs_generated']} "
                 f"({ai['overall_acceptance_rate']:.1%})")
    lines.append(f"  AI feature breadth (mean): "
                 f"{ai['mean_feature_breadth']:.3f}")
    health = report["health"]
    lines.append("")
    lines.append("Health tiers:")
    for tier in ("thriving", "steady", "at-risk", "dormant"):
        lines.append(f"  {tier}: {health['tiers'][tier]}")
    lines.append(f"  at-risk share (at-risk + dormant): "
                 f"{health['at_risk_share']:.1%} "
                 f"(threshold {health['at_risk_threshold']:.0%}, "
                 f"within={health['within_threshold']})")
    lines.append("")
    lines.append(f"Anomalies: {report['anomaly_count']} sudden-drop flags "
                 f"across {report['anomaly_accounts']} accounts")
    for flag in report["anomalies"][:10]:
        lines.append(f"  {flag['account_id']} {flag['week_start']}: "
                     f"sessions {flag['sessions']} vs rolling median "
                     f"{flag['baseline_median_sessions']:.1f} "
                     f"(MAD {flag['mad']:.1f}, "
                     f"robust z {flag['robust_z']:.2f})")
    return "\n".join(lines) + "\n"
