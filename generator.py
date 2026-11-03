"""Deterministic synthetic AI-rollout generator.

SYNTHETIC DATA ONLY. Every account is fictional, fabricated from a
seeded PRNG so the same seed always yields the same dataset,
byte-for-byte. No real company, customer, or user data is used.

One row per account per observed week:

  account_id, account_name, cohort (YYYY-MM of rollout),
  segment (smb / midmarket / enterprise), industry,
  licensed_seats, week_start (YYYY-MM-DD, a Monday),
  week_index (calendar week, 0-based), weeks_since_rollout (0-based),
  active_users, sessions, features_used (0..FEATURE_COUNT),
  prompts, outputs_generated, outputs_accepted

The last three are the AI-specific usage signals: ``prompts`` is the
number of prompts / AI actions submitted, ``outputs_generated`` the
AI outputs they produced, and ``outputs_accepted`` how many of those
outputs the users kept (accepted into their work rather than
discarded or regenerated away). They are drawn from a *separate*
PRNG stream keyed by (seed, account), so adding them never disturbs
the session trajectory above.

120 accounts roll out in four monthly cohorts over a 26-week window
starting 2026-01-05 (a Monday). Each account follows one hidden
generation archetype (thriving / steady / at_risk / dormant) that
shapes its trajectory; the health tiers in health.py are *derived*
from the observed data by explicit rules, never copied from the
archetype, so the two can disagree - and the evals pin where they land.
"""

from __future__ import annotations

import hashlib
import json
import random
from datetime import date, timedelta
from typing import Dict, List

DEFAULT_SEED = 42
START = date(2026, 1, 5)  # a Monday
WEEKS = 26
ACCOUNT_COUNT = 120
FEATURE_COUNT = 8
FEATURES = ["chat_assistant", "doc_summary", "search",
            "workflow_automation", "report_writer", "code_helper",
            "meeting_notes", "data_analysis"]
INDUSTRIES = ["logistics", "retail", "healthcare_admin", "finance_ops",
              "education", "manufacturing", "hospitality", "legal_ops"]
SEGMENTS = ("smb", "midmarket", "enterprise")
ARCHETYPES = ("thriving", "steady", "at_risk", "dormant")

# Cohort rollout calendar weeks and their month labels.
COHORT_WEEKS = [0, 4, 8, 12]
COHORT_LABELS = ["2026-01", "2026-02", "2026-03", "2026-04"]

_NAME_A = ["Aster", "Beacon", "Cinder", "Drift", "Ember", "Fable",
           "Glacier", "Harbor", "Ion", "Juniper", "Kestrel", "Lantern",
           "Meadow", "North", "Onyx", "Prairie", "Quartz", "Ridge",
           "Summit", "Timber"]
_NAME_B = ["Labs", "Works", "Group", "Systems", "Partners", "Collective"]

ROW_FIELDS = ["account_id", "account_name", "cohort", "segment",
              "industry", "licensed_seats", "week_start", "week_index",
              "weeks_since_rollout", "active_users", "sessions",
              "features_used", "prompts", "outputs_generated",
              "outputs_accepted"]

_ACCEPTANCE_BASE = {  # centre of each archetype's acceptance rate
    "thriving": 0.84, "steady": 0.70, "at_risk": 0.52, "dormant": 0.42,
}


def _ai_rng(seed: int, account_id: str, wsr: int) -> random.Random:
    """Separate, stable PRNG stream for the AI-usage fields."""
    digest = hashlib.sha256(
        f"{seed}:{account_id}:{wsr}".encode()).hexdigest()
    return random.Random(int(digest[:12], 16))


def account_name(index: int) -> str:
    """120 unique fictional names: 20 first parts x 6 second parts."""
    return f"{_NAME_A[index % 20]} {_NAME_B[(index // 20) % 6]}"


def cohort_for_index(index: int) -> int:
    """Accounts are assigned to cohorts in blocks of 30, in order."""
    return min(index // 30, len(COHORT_WEEKS) - 1)


def _archetype(rng: random.Random) -> str:
    roll = rng.random()
    if roll < 0.30:
        return "thriving"
    if roll < 0.65:
        return "steady"
    if roll < 0.85:
        return "at_risk"
    return "dormant"


_PROPENSITY = {  # base share of licensed seats active at full ramp
    "thriving": (0.45, 0.75),
    "steady": (0.25, 0.50),
    "at_risk": (0.12, 0.32),
    "dormant": (0.05, 0.20),
}
_SESSIONS_PER_ACTIVE = {
    "thriving": (6.0, 12.0),
    "steady": (4.0, 9.0),
    "at_risk": (2.0, 6.0),
    "dormant": (1.0, 4.0),
}
_FEATURE_RANGE = {
    "thriving": (5, 8),
    "steady": (3, 6),
    "at_risk": (1, 4),
    "dormant": (0, 2),
}


def _decline(archetype: str, wsr: int) -> float:
    if archetype == "at_risk":
        if wsr <= 6:
            return 1.0
        return max(0.18, 1.0 - 0.07 * (wsr - 6))
    if archetype == "dormant":
        if wsr <= 2:
            return 1.0
        return max(0.0, 1.0 - 0.25 * (wsr - 2))
    return 1.0


def generate_records(seed: int = DEFAULT_SEED) -> List[Dict]:
    rng = random.Random(seed)
    records: List[Dict] = []
    for i in range(ACCOUNT_COUNT):
        cohort_idx = cohort_for_index(i)
        rollout_week = COHORT_WEEKS[cohort_idx]
        cohort = COHORT_LABELS[cohort_idx]
        seg_roll = rng.random()
        if seg_roll < 0.35:
            segment, seats = "smb", rng.randint(10, 50)
        elif seg_roll < 0.75:
            segment, seats = "midmarket", rng.randint(51, 250)
        else:
            segment, seats = "enterprise", rng.randint(251, 1000)
        industry = rng.choice(INDUSTRIES)
        archetype = _archetype(rng)
        lo, hi = _PROPENSITY[archetype]
        propensity = rng.uniform(lo, hi)
        spa_lo, spa_hi = _SESSIONS_PER_ACTIVE[archetype]
        sessions_per_active = rng.uniform(spa_lo, spa_hi)
        feat_lo, feat_hi = _FEATURE_RANGE[archetype]
        name = account_name(i)
        account_id = f"acct_{i + 1:03d}"

        for wsr in range(WEEKS - rollout_week):
            week_index = rollout_week + wsr
            week_start = START + timedelta(weeks=week_index)
            ramp = min(1.0, 0.35 + 0.22 * wsr)
            fraction = (propensity * ramp * _decline(archetype, wsr)
                        * rng.uniform(0.85, 1.15))
            if archetype == "dormant" and wsr >= 8:
                fraction = 0.0
            active = int(round(seats * fraction))
            active = max(0, min(seats, active))
            # Some low-propensity accounts never really start: in the
            # first two weeks a weak account can record zero use,
            # which is exactly what the activation definition judges.
            if wsr < 2 and rng.random() < (1.0 - propensity) * 0.35:
                active = 0
            sessions = int(round(active * sessions_per_active
                                 * rng.uniform(0.85, 1.15))) if active else 0
            if active:
                features = rng.randint(feat_lo, feat_hi)
                features = min(FEATURE_COUNT, features + (1 if wsr >= 8 else 0))
            else:
                features = 0
            # Planted sudden drop: every fifth at-risk account
            # craters to about a sixth of its sessions for exactly
            # one week at wsr=15, then recovers part-way. The
            # severity is deliberate: a planted anomaly the golden
            # evals must catch has to be unambiguous under the
            # rolling median / MAD detector (see health.py) - at a
            # third of normal, one of the five plants sat at robust
            # z -3.27, inside the noise band of a 4-point MAD.
            if archetype == "at_risk" and i % 5 == 0 and wsr == 15 and active:
                active = max(1, active // 3)
                sessions = max(1, sessions // 6)
                features = max(0, features - 1)
            # AI-specific usage signals, from the separate stream:
            # each session submits 2-4 prompts, each prompt produces
            # one output, and the kept share centres on the
            # archetype's acceptance rate with weekly jitter.
            if active:
                ai_rng = _ai_rng(seed, account_id, wsr)
                prompts = sessions * ai_rng.randint(2, 4)
                outputs_generated = prompts
                acceptance = max(0.05, min(0.98,
                    _ACCEPTANCE_BASE[archetype]
                    + ai_rng.uniform(-0.08, 0.08)))
                outputs_accepted = int(round(outputs_generated
                                             * acceptance))
            else:
                prompts = outputs_generated = outputs_accepted = 0
            records.append({
                "account_id": account_id,
                "account_name": name,
                "cohort": cohort,
                "segment": segment,
                "industry": industry,
                "licensed_seats": seats,
                "week_start": week_start.isoformat(),
                "week_index": week_index,
                "weeks_since_rollout": wsr,
                "active_users": active,
                "sessions": sessions,
                "features_used": features,
                "prompts": prompts,
                "outputs_generated": outputs_generated,
                "outputs_accepted": outputs_accepted,
            })
    return records


def accounts_of(records: List[Dict]) -> List[Dict]:
    """One metadata dict per account, in first-appearance order."""
    seen: Dict[str, Dict] = {}
    for r in records:
        if r["account_id"] not in seen:
            seen[r["account_id"]] = {
                "account_id": r["account_id"],
                "account_name": r["account_name"],
                "cohort": r["cohort"],
                "segment": r["segment"],
                "industry": r["industry"],
                "licensed_seats": r["licensed_seats"],
            }
    return list(seen.values())


def records_by_account(records: List[Dict]) -> Dict[str, List[Dict]]:
    grouped: Dict[str, List[Dict]] = {}
    for r in records:
        grouped.setdefault(r["account_id"], []).append(r)
    for rows in grouped.values():
        rows.sort(key=lambda r: r["weeks_since_rollout"])
    return grouped


def records_to_json(records: List[Dict]) -> str:
    return json.dumps(records, sort_keys=True) + "\n"


def records_to_jsonl(records: List[Dict]) -> str:
    return "".join(json.dumps(r, sort_keys=True) + "\n" for r in records)


def load_records(path: str) -> List[Dict]:
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    stripped = text.strip()
    if not stripped:
        raise ValueError("empty file")
    if stripped.startswith("["):
        data = json.loads(stripped)
        if not isinstance(data, list):
            raise ValueError("expected a JSON array")
        return data
    return [json.loads(line) for line in stripped.splitlines() if line.strip()]


def write_records(records: List[Dict], path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(records_to_json(records))
