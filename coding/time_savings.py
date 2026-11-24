"""Workload scenarios using measured minutes; audio duration is not annotation labor."""
import argparse
import json


def estimate(calls, manual_minutes, review_minutes, review_rate, setup_minutes=0, audit_rate=0):
    if type(calls) is not int or calls < 1: raise ValueError("calls must be a positive integer")
    if min(manual_minutes, review_minutes, setup_minutes) < 0 or manual_minutes == 0:
        raise ValueError("manual minutes must be positive and other times nonnegative")
    if not (0 <= review_rate <= 1 and 0 <= audit_rate <= 1): raise ValueError("rates must be between zero and one")
    reviewed = calls * (review_rate + (1-review_rate)*audit_rate)
    manual = calls*manual_minutes
    assisted = setup_minutes + reviewed*review_minutes
    return {"calls": calls, "expected_reviewed_calls": reviewed, "manual_labor_hours": manual/60,
            "assisted_labor_hours": assisted/60, "labor_hours_saved": (manual-assisted)/60,
            "fraction_labor_saved": 1-assisted/manual,
            "note": "Scenario conditional on supplied measurements; model wall-clock time and API cost are reported separately."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calls", type=int, required=True)
    parser.add_argument("--manual-minutes", type=float, required=True)
    parser.add_argument("--review-minutes", type=float, required=True)
    parser.add_argument("--review-rate", type=float, required=True)
    parser.add_argument("--setup-minutes", type=float, default=0)
    parser.add_argument("--audit-rate", type=float, default=0)
    args = parser.parse_args(); print(json.dumps(estimate(**vars(args)), indent=2))
