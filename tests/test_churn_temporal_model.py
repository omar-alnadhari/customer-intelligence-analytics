"""Temporal leakage and saved churn-model regression tests."""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)


TRAIN_END = pd.Timestamp("2011-01-01")
VALIDATION_START = pd.Timestamp("2011-05-01")
VALIDATION_END = pd.Timestamp("2011-06-01")
TEST_DATE = pd.Timestamp("2011-09-01")


def test_churn_snapshots_are_point_in_time_and_targets_are_consistent(
    churn_snapshots: pd.DataFrame,
) -> None:
    churn = churn_snapshots

    assert len(churn) == 48_079
    assert churn["customer_id"].nunique() == 5_236
    assert churn["snapshot_date"].nunique() == 16
    assert not churn.duplicated(["customer_id", "snapshot_date"]).any()

    assert (churn["first_purchase"] <= churn["last_purchase"]).all()
    assert (churn["last_purchase"] < churn["snapshot_date"]).all()
    assert (
        churn["prediction_end_date"]
        == churn["snapshot_date"] + pd.Timedelta(days=90)
    ).all()

    np.testing.assert_array_equal(
        churn["recency_days"],
        (churn["snapshot_date"] - churn["last_purchase"]).dt.days,
    )
    np.testing.assert_array_equal(
        churn["customer_age_days"],
        (churn["snapshot_date"] - churn["first_purchase"]).dt.days,
    )
    np.testing.assert_array_equal(
        churn["tenure_days"],
        (churn["last_purchase"] - churn["first_purchase"]).dt.days,
    )

    assert churn["recency_days"].between(0, 180).all()
    assert (churn["eligibility_orders"] > 0).all()
    assert (churn["last_30d_orders"] <= churn["last_90d_orders"]).all()
    assert (churn["last_90d_orders"] <= churn["eligibility_orders"]).all()
    assert churn["churn_90d"].isin([0, 1]).all()
    np.testing.assert_array_equal(
        churn["churn_90d"],
        (churn["future_orders_90d"] == 0).astype("int8"),
    )


def test_train_validation_test_target_windows_are_separated(
    churn_snapshots: pd.DataFrame,
) -> None:
    churn = churn_snapshots
    train = churn.loc[churn["snapshot_date"] <= TRAIN_END]
    validation = churn.loc[
        churn["snapshot_date"].between(VALIDATION_START, VALIDATION_END)
    ]
    test = churn.loc[churn["snapshot_date"] == TEST_DATE]

    assert len(train) == 24_092
    assert len(validation) == 5_708
    assert len(test) == 2_772

    assert train["snapshot_date"].min() == pd.Timestamp("2010-06-01")
    assert train["snapshot_date"].max() == TRAIN_END
    assert validation["snapshot_date"].unique().tolist() == [
        np.datetime64("2011-05-01"),
        np.datetime64("2011-06-01"),
    ]
    assert test["snapshot_date"].nunique() == 1

    assert train["prediction_end_date"].max() == pd.Timestamp("2011-04-01")
    assert train["prediction_end_date"].max() <= VALIDATION_START
    assert validation["prediction_end_date"].max() == pd.Timestamp("2011-08-30")
    assert validation["prediction_end_date"].max() <= TEST_DATE
    assert test["prediction_end_date"].max() == pd.Timestamp("2011-11-30")

    used_dates = set(train["snapshot_date"]) | set(validation["snapshot_date"]) | {
        TEST_DATE
    }
    purged_dates = set(churn["snapshot_date"]) - used_dates
    assert purged_dates == {
        pd.Timestamp("2011-02-01"),
        pd.Timestamp("2011-03-01"),
        pd.Timestamp("2011-04-01"),
        pd.Timestamp("2011-07-01"),
        pd.Timestamp("2011-08-01"),
    }


def test_saved_churn_bundle_contains_only_point_in_time_features(
    project_root: Path,
) -> None:
    bundle = joblib.load(project_root / "models" / "churn_random_forest.joblib")
    features = list(bundle["features"])

    assert set(bundle) == {
        "model",
        "features",
        "threshold",
        "prediction_horizon_days",
    }
    assert len(features) == bundle["model"].n_features_in_ == 28
    assert bundle["prediction_horizon_days"] == 90
    assert np.isclose(bundle["threshold"], 0.31)

    forbidden = {
        "customer_id",
        "snapshot_date",
        "prediction_end_date",
        "first_purchase",
        "last_purchase",
        "future_orders_90d",
        "future_revenue_90d",
        "churn_90d",
        "segment",
        "value_tier",
        "ml_cluster",
        "cluster_name",
    }
    assert not forbidden.intersection(features)
    assert not any(feature.startswith("future_") for feature in features)


def test_threshold_selection_code_uses_validation_before_test(
    project_root: Path,
) -> None:
    notebook = json.loads(
        (project_root / "notebooks" / "05_churn_modeling.ipynb").read_text(
            encoding="utf-8"
        )
    )
    threshold_search = "".join(notebook["cells"][19]["source"])
    threshold_choice = "".join(notebook["cells"][20]["source"])
    test_scoring = "".join(notebook["cells"][25]["source"])

    assert "validation_probs" in threshold_search
    assert "y_validation" in threshold_search
    assert "y_test" not in threshold_search
    assert "test_probabilities" not in threshold_search
    assert "threshold_evaluation" in threshold_choice
    assert "SELECTED_THRESHOLD" in threshold_choice
    assert "X_test" in test_scoring
    assert "SELECTED_THRESHOLD" in test_scoring


def test_saved_test_predictions_reproduce_reported_metrics(
    reports_dir: Path,
) -> None:
    scored = pd.read_csv(reports_dir / "churn_test_predictions.csv")
    metrics = json.loads(
        (reports_dir / "churn_final_test_metrics.json").read_text(
            encoding="utf-8"
        )
    )
    threshold = metrics["Selected Threshold"]
    expected_predictions = (scored["churn_probability"] >= threshold).astype(int)
    np.testing.assert_array_equal(scored["predicted_churn"], expected_predictions)

    actual = scored["churn_90d"]
    probability = scored["churn_probability"]
    prediction = scored["predicted_churn"]
    recomputed = {
        "ROC-AUC": roc_auc_score(actual, probability),
        "PR-AUC": average_precision_score(actual, probability),
        "Brier Score": brier_score_loss(actual, probability),
        "Accuracy": accuracy_score(actual, prediction),
        "Balanced Accuracy": balanced_accuracy_score(actual, prediction),
        "Precision": precision_score(actual, prediction),
        "Recall": recall_score(actual, prediction),
        "F1": f1_score(actual, prediction),
        "Test Churn Rate": actual.mean(),
        "Predicted Churn Rate": prediction.mean(),
    }

    for name, value in recomputed.items():
        assert np.isclose(value, metrics[name], rtol=0, atol=1e-12), name
