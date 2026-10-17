"""Unit tests: feature engineering + decision bands."""

from __future__ import annotations

from types import SimpleNamespace

from app.data_generator import generate_events
from app.features import FeatureEngineer
from app.pipeline import FraudDetector


def test_generate_events_has_expected_columns_and_labels():
    df = generate_events(n_bona_fide=300, n_fraud=60, seed=7, n_reviewish=20)
    for col in ("event_id", "user_id", "amount_inr", "true_label",
                "payment_method", "device_id", "event_ts"):
        assert col in df.columns, col
    assert set(df["true_label"].unique()).issubset({0, 1})
    assert (df["true_label"] == 1).sum() >= 1


def test_feature_engineer_builds_numeric_matrix_without_nans():
    df = generate_events(n_bona_fide=200, n_fraud=40, seed=3, n_reviewish=10)
    feat = FeatureEngineer().build(df)
    assert len(feat) == len(df)
    assert len(feat.columns) >= 40
    assert int(feat.isna().any().sum()) == 0
    # feature matrix must be strictly numeric
    assert all(str(d).startswith(("int", "float", "bool")) for d in feat.dtypes)


def test_decision_bands():
    det = FraudDetector()
    det.investigator = SimpleNamespace(approve_thresh=0.44, review_thresh=0.80)
    assert det._decide(0.10) == "approve"
    assert det._decide(0.43999) == "approve"
    assert det._decide(0.44) == "review"
    assert det._decide(0.79999) == "review"
    assert det._decide(0.80) == "block"
    assert det._decide(0.99) == "block"
