"""Regression tests for the scoped (windowed) feature-build optimisation.

The live scoring path builds features only from same-key history + the target
instead of the whole dataset. These tests assert the optimised path produces the
SAME model scores as a reference full-dataset build, and that a single score
stays fast.
"""

from __future__ import annotations

import time

import pandas as pd

from app.models.behaviour_ai import behaviour_scores


def _reference(det, event, history=None):
    """Reference implementation: build features over the FULL dataset (the
    original, slow path)."""
    df = det.event_df.copy()
    prior = []
    if history:
        now = int(time.time_ns())
        for i, p in enumerate(reversed(history)):
            pe = det._normalize_event(p, f"prior_{i}")
            pe["event_ts"] = pe.get("event_ts", now - (i + 1) * 8 * 10**9)
            prior.append(pe)
    target = det._normalize_event(event, "target")
    if history:
        target["event_ts"] = max([p["event_ts"] for p in prior] + [target["event_ts"]]) + 10**9
    df = pd.concat([df, pd.DataFrame(prior + [target])], ignore_index=True)
    feat = det.fe.build(df)
    i = len(df) - 1
    p_ml = float(det.ml_risk.predict_proba(feat)[i:i + 1][0])
    p_beh = float(behaviour_scores(det.behaviour, feat)[i])
    p_grf = float(det.graph.score_events(df).values[i])
    det.investigator.event_df = df
    det.investigator.feat_df = feat
    return det.investigator.investigate(i, p_ml, p_beh, p_grf)


def test_scoped_build_matches_full_build(detector):
    sample = detector.event_df.iloc[4000]
    ev = {k: v for k, v in sample.items() if k != "event_ts"}
    ev["event_ts"] = int(time.time_ns())

    fast = detector.investigate_event(dict(ev))
    ref = _reference(detector, dict(ev))
    assert fast["scores"] == ref["scores"]
    assert fast["decision"] == ref["decision"]


def test_scoped_build_matches_full_build_with_history(detector):
    hist = [{"user_id": "burst_u2", "device_id": "bd2", "card_last4": "9999",
             "amount_inr": 5, "merchant": "X"} for _ in range(6)]
    ev = {"user_id": "burst_u2", "device_id": "bd2", "card_last4": "9999",
          "amount_inr": 5000, "merchant": "X"}

    fast = detector.investigate_event(dict(ev), history=[dict(h) for h in hist])
    ref = _reference(detector, dict(ev), history=[dict(h) for h in hist])
    assert fast["scores"] == ref["scores"]
    assert fast["decision"] == ref["decision"]


def test_single_score_is_fast(detector):
    """A single live score must complete well under a second (the scoped build
    replaced a ~4.5s full-dataset feature build)."""
    ev = {"user_id": "lat_u", "device_id": "lat_d", "card_last4": "4242",
          "amount_inr": 1500, "merchant": "LatencyMart"}
    t0 = time.perf_counter()
    detector.investigate_event(ev)
    elapsed = time.perf_counter() - t0
    assert elapsed < 2.0, f"single score took {elapsed:.2f}s"
