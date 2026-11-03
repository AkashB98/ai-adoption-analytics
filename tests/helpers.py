"""Shared record builders for the test suite (not a test module)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_counter = [0]


def rec(account_id="acct_t01", account_name="Test Co", cohort="2026-01",
        segment="smb", industry="retail", licensed_seats=100,
        week_start="2026-01-05", week_index=0, weeks_since_rollout=0,
        active_users=10, sessions=50, features_used=4, prompts=150,
        outputs_generated=150, outputs_accepted=120):
    return {
        "account_id": account_id, "account_name": account_name,
        "cohort": cohort, "segment": segment, "industry": industry,
        "licensed_seats": licensed_seats, "week_start": week_start,
        "week_index": week_index,
        "weeks_since_rollout": weeks_since_rollout,
        "active_users": active_users, "sessions": sessions,
        "features_used": features_used, "prompts": prompts,
        "outputs_generated": outputs_generated,
        "outputs_accepted": outputs_accepted,
    }


def account_rows(account_id="acct_t01", weeks=6, active=10, sessions=50,
                 features=4, seats=100, **kw):
    """``weeks`` consecutive rows for one account. AI fields are
    derived from sessions so zero-use rows stay zero throughout."""
    prompts = sessions * 3
    return [rec(account_id=account_id, week_index=w,
                weeks_since_rollout=w, active_users=active,
                sessions=sessions, features_used=features,
                licensed_seats=seats, prompts=prompts,
                outputs_generated=prompts,
                outputs_accepted=int(prompts * 0.8),
                **kw) for w in range(weeks)]


def util_dict(score=0.5, breadth=0.5, seat=0.5):
    return {"utilization_score": score, "feature_breadth": breadth,
            "seat_utilization": seat}
