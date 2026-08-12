"""Sanity and reconciliation tests for predictive CLV artifacts."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd


PREDICTION_COLUMNS = [
    "probability_alive",
    "expected_purchases_90d",
    "expected_purchases_180d",
    "expected_purchases_365d",
    "expected_transaction_value",
    "expected_revenue_clv_12m",
]


def test_clv_customer_predictions_are_complete_and_sane(
    customer_clv: pd.DataFrame,
) -> None:
    clv = customer_clv

    assert len(clv) == 5_878
    assert clv["customer_id"].is_unique
    assert not clv.isna().any().any()
    assert np.isfinite(clv[PREDICTION_COLUMNS].to_numpy(dtype="float64")).all()
    assert clv["probability_alive"].between(0, 1).all()
    assert (clv[PREDICTION_COLUMNS[1:]] >= 0).all().all()
    assert (clv["expected_transaction_value"] > 0).all()
    assert (clv["historical_revenue"] > 0).all()

    assert (
        clv["expected_purchases_90d"] <= clv["expected_purchases_180d"]
    ).all()
    assert (
        clv["expected_purchases_180d"] <= clv["expected_purchases_365d"]
    ).all()

    assert {
        "historical_revenue",
        "expected_revenue_clv_12m",
    }.issubset(clv.columns)
    assert not np.allclose(
        clv["historical_revenue"], clv["expected_revenue_clv_12m"]
    )


def test_predictive_clv_tiers_follow_saved_distribution_cutoffs(
    customer_clv: pd.DataFrame,
) -> None:
    clv = customer_clv
    p50, p80, p95 = clv["expected_revenue_clv_12m"].quantile(
        [0.50, 0.80, 0.95]
    )
    expected = np.select(
        [
            clv["expected_revenue_clv_12m"] <= p50,
            clv["expected_revenue_clv_12m"] <= p80,
            clv["expected_revenue_clv_12m"] <= p95,
        ],
        ["Developing", "Core", "High"],
        default="Strategic",
    )

    np.testing.assert_array_equal(clv["clv_value_tier"].astype(str), expected)
    assert clv["clv_value_tier"].value_counts(sort=False).to_dict() == {
        "Developing": 2_939,
        "Core": 1_763,
        "High": 882,
        "Strategic": 294,
    }


def test_clv_segments_match_upstream_customer_dimensions(
    customer_clv: pd.DataFrame,
    rfm: pd.DataFrame,
    ml_segments: pd.DataFrame,
) -> None:
    dimensions = (
        rfm[
            [
                "customer_id",
                "segment",
                "value_tier",
                "rfm_total_score",
                "recommended_action",
            ]
        ]
        .rename(
            columns={
                "segment": "rfm_segment",
                "value_tier": "rfm_value_tier",
                "recommended_action": "rfm_action",
            }
        )
        .merge(
            ml_segments[
                ["customer_id", "ml_cluster", "cluster_name", "cluster_action"]
            ],
            on="customer_id",
            validate="one_to_one",
        )
    )
    actual = customer_clv.merge(
        dimensions,
        on="customer_id",
        suffixes=("_actual", "_expected"),
        validate="one_to_one",
    )

    for column in [
        "rfm_segment",
        "rfm_value_tier",
        "rfm_total_score",
        "rfm_action",
        "ml_cluster",
        "cluster_name",
        "cluster_action",
    ]:
        np.testing.assert_array_equal(
            actual[f"{column}_actual"].astype(str),
            actual[f"{column}_expected"].astype(str),
        )


def test_clv_model_summary_reconciles_with_customer_output(
    customer_clv: pd.DataFrame,
    reports_dir,
) -> None:
    summary = json.loads(
        (reports_dir / "clv_model_summary.json").read_text(encoding="utf-8")
    )
    clv = customer_clv

    assert summary["customers"] == len(clv) == 5_878
    assert summary["holdout_customers"] == 4_937
    assert summary["holdout_days"] == 191
    assert np.isclose(summary["holdout_mae"], 1.0783059574863216)
    assert np.isclose(summary["holdout_rmse"], 1.84288586042603)
    assert np.isclose(summary["holdout_aggregate_error_pct"], -1.8498065550319864)
    assert summary["gamma_gamma_eligible_customers"] == 4_189
    assert abs(summary["frequency_monetary_correlation"]) < 0.30

    assert np.isclose(
        summary["expected_revenue_clv_12m_total"],
        clv["expected_revenue_clv_12m"].sum(),
    )
    assert np.isclose(
        summary["expected_revenue_clv_12m_mean"],
        clv["expected_revenue_clv_12m"].mean(),
    )
    assert np.isclose(
        summary["expected_revenue_clv_12m_median"],
        clv["expected_revenue_clv_12m"].median(),
    )
    assert summary["monthly_discount_rate"] == 0.0
    assert "not historical revenue" in summary["clv_definition"]
    assert "not profit" in summary["clv_definition"]
