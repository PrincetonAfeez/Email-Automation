""" Unsafe cache as truth for EmailAuto."""

from __future__ import annotations

def run_demo() -> dict[str, str]:
    cached_state = "pending"
    durable_state = "sent"
    decision = "send" if cached_state == "pending" else "skip"
    return {
        "cached_state": cached_state,
        "durable_state": durable_state,
        "bad_decision": decision,
        "problem": "stale cache caused a duplicate send decision",
    }

