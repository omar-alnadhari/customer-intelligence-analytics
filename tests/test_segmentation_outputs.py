"""Integrity tests for RFM and machine-learning customer segments."""

from __future__ import annotations

import numpy as np
import pandas as pd


def test_rfm_customer_level_invariants(
    rfm: pd.DataFrame,
    customer_sales_profile: dict[str, object],
) -> None:
    assert len(rfm) == 5_878
    assert rfm["customer_id"].is_unique
    assert not rfm.isna().any().any()

    assert (rfm["recency"] >= 0).all()
    assert (rfm["frequency"] >= 1).all()
    assert (rfm["monetary"] > 0).all()
    assert (rfm["tenure_days"] >= 0).all()
    assert (rfm["last_purchase"] >= rfm["first_purchase"]).all()

    analysis_date = pd.Timestamp(customer_sales_profile["maximum_date"]) + pd.Timedelta(
        days=1
    )
    expected_recency = (analysis_date - rfm["last_purchase"]).dt.days
    expected_tenure = (rfm["last_purchase"] - rfm["first_purchase"]).dt.days

    np.testing.assert_array_equal(rfm["recency"], expected_recency)
    np.testing.assert_array_equal(rfm["tenure_days"], expected_tenure)
    np.testing.assert_allclose(
        rfm["average_order_value"],
        rfm["monetary"] / rfm["frequency"],
        rtol=1e-12,
        atol=1e-12,
    )
    assert np.isclose(rfm["monetary"].sum(), customer_sales_profile["revenue"])


def test_rfm_scores_segments_and_value_tiers_are_consistent(
    rfm: pd.DataFrame,
) -> None:
    score_columns = ["r_score", "f_score", "m_score"]
    assert rfm[score_columns].isin([1, 2, 3, 4, 5]).all().all()

    np.testing.assert_array_equal(
        rfm["rfm_total_score"], rfm[score_columns].sum(axis=1)
    )
    expected_code = (
        rfm["r_score"].astype(str)
        + rfm["f_score"].astype(str)
        + rfm["m_score"].astype(str)
    )
    np.testing.assert_array_equal(rfm["rfm_code"].astype(str), expected_code)

    expected_tier = np.select(
        [rfm["m_score"] >= 4, rfm["m_score"] == 3],
        ["High Value", "Medium Value"],
        default="Low Value",
    )
    np.testing.assert_array_equal(rfm["value_tier"], expected_tier)

    expected_segments = {
        "About to Sleep",
        "At Risk",
        "Cannot Lose Them",
        "Champions",
        "Hibernating",
        "Loyal Customers",
        "Need Attention",
        "New Customers",
        "Potential Loyalists",
        "Promising",
    }
    assert set(rfm["segment"]) == expected_segments
    assert rfm["recommended_action"].str.len().gt(0).all()


def test_ml_segments_preserve_rfm_spine_and_cluster_mapping(
    rfm: pd.DataFrame,
    ml_segments: pd.DataFrame,
) -> None:
    assert len(ml_segments) == 5_878
    assert ml_segments["customer_id"].is_unique
    assert not ml_segments.isna().any().any()

    rfm_sorted = rfm.sort_values("customer_id").reset_index(drop=True)
    ml_sorted = ml_segments.sort_values("customer_id").reset_index(drop=True)
    pd.testing.assert_frame_equal(
        ml_sorted[rfm.columns],
        rfm_sorted,
        check_dtype=True,
    )

    cluster_names = {
        0: "At-Risk Return-Heavy Customers",
        1: "High-Value Loyal Customers",
        2: "Established Moderate-Value Customers",
        3: "Dormant One-Time Customers",
    }
    assert set(ml_segments["ml_cluster"]) == set(cluster_names)
    expected_names = ml_segments["ml_cluster"].map(cluster_names)
    np.testing.assert_array_equal(ml_segments["cluster_name"], expected_names)

    assert ml_segments["cluster_action"].str.len().gt(0).all()
    assert ml_segments["return_invoice_rate"].between(0, 1).all()
    assert (ml_segments["return_invoices"] <= ml_segments["total_activity_invoices"]).all()
    assert np.isfinite(ml_segments[["pca_1", "pca_2"]].to_numpy()).all()

    expected_counts = {
        0: 986,
        1: 1_455,
        2: 1_848,
        3: 1_589,
    }
    assert ml_segments["ml_cluster"].value_counts().to_dict() == expected_counts
