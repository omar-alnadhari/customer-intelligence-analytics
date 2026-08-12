import json

import numpy as np
import pandas as pd


def _load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_current_churn_scores_are_point_in_time_and_joined_without_imputation(
    current_churn_scores,
    retention_decisions,
):
    scores = current_churn_scores.copy()
    decisions = retention_decisions.copy()

    assert len(scores) == 3_477
    assert scores["customer_id"].is_unique
    assert not scores["customer_id"].isna().any()
    assert scores["churn_probability"].between(0, 1, inclusive="both").all()
    assert scores["snapshot_date"].nunique() == 1
    assert scores["snapshot_date"].iloc[0] == pd.Timestamp("2011-12-10")
    assert not any(
        column.startswith("future_") or column == "churn_90d"
        for column in scores.columns
    )

    eligible = decisions.loc[decisions["churn_model_eligible"]].copy()
    outside_scope = decisions.loc[~decisions["churn_model_eligible"]].copy()
    assert set(eligible["customer_id"]) == set(scores["customer_id"])
    assert outside_scope["churn_probability"].isna().all()
    assert not outside_scope["campaign_selected"].any()

    joined = eligible.merge(
        scores[["customer_id", "churn_probability", "predicted_churn"]],
        on="customer_id",
        how="left",
        suffixes=("_decision", "_source"),
        validate="one_to_one",
    )
    np.testing.assert_allclose(
        joined["churn_probability_decision"],
        joined["churn_probability_source"],
        rtol=0,
        atol=1e-12,
    )
    np.testing.assert_array_equal(
        joined["predicted_churn_decision"],
        joined["predicted_churn_source"],
    )


def test_retention_economics_recompute_from_configurable_assumptions(
    reports_dir,
    retention_decisions,
):
    assumptions = _load_json(reports_dir / "retention_assumptions.json")
    decisions = retention_decisions.copy()

    action_assumptions = assumptions["action_assumptions"]
    intervention_cost = {
        action: values["intervention_cost"]
        for action, values in action_assumptions.items()
    } | {"Separate reactivation review": 0.0}
    recovery_rate = {
        action: values["assumed_recoverable_share"]
        for action, values in action_assumptions.items()
    } | {"Separate reactivation review": 0.0}

    expected_cost = decisions["recommended_action"].map(intervention_cost)
    expected_recovery = decisions["recommended_action"].map(recovery_rate)
    assert expected_cost.notna().all()
    assert expected_recovery.notna().all()
    np.testing.assert_allclose(decisions["intervention_cost"], expected_cost)
    np.testing.assert_allclose(decisions["assumed_recoverable_share"], expected_recovery)

    eligible = decisions.loc[decisions["churn_model_eligible"]].copy()
    revenue_at_risk = eligible["churn_probability"] * eligible["expected_revenue_clv_12m"]
    preserved_revenue = revenue_at_risk * eligible["assumed_recoverable_share"]
    expected_benefit = preserved_revenue * assumptions["decision_config"]["gross_margin_rate"]
    net_value = expected_benefit - eligible["intervention_cost"]

    np.testing.assert_allclose(eligible["scenario_revenue_at_risk_proxy"], revenue_at_risk)
    np.testing.assert_allclose(eligible["scenario_expected_revenue_preserved"], preserved_revenue)
    np.testing.assert_allclose(eligible["scenario_expected_retention_benefit"], expected_benefit)
    np.testing.assert_allclose(eligible["scenario_expected_net_benefit"], net_value)

    positive_cost = eligible["intervention_cost"] > 0
    np.testing.assert_allclose(
        eligible.loc[positive_cost, "scenario_benefit_cost_ratio"],
        expected_benefit.loc[positive_cost] / eligible.loc[positive_cost, "intervention_cost"],
    )
    assert eligible["priority_score"].between(0, 100, inclusive="both").all()


def test_campaign_selection_respects_budget_capacity_and_economic_gates(
    reports_dir,
    retention_decisions,
):
    assumptions = _load_json(reports_dir / "retention_assumptions.json")
    summary = _load_json(reports_dir / "retention_engine_summary.json")
    config = assumptions["decision_config"]
    decisions = retention_decisions.copy()
    selected = decisions.loc[decisions["campaign_selected"]].copy()

    campaign = pd.read_csv(
        reports_dir / "retention_campaign_targets.csv",
        dtype={"customer_id": "string"},
        parse_dates=["decision_date"],
    )

    assert len(selected) == 708
    assert len(campaign) == len(selected)
    assert set(campaign["customer_id"]) == set(selected["customer_id"])
    assert selected["churn_model_eligible"].all()
    assert selected["churn_probability"].ge(config["policy_risk_floor"]).all()
    assert selected["scenario_expected_net_benefit"].gt(0).all()
    assert selected["decision_status"].eq("selected").all()
    assert selected["campaign_rank"].sort_values().tolist() == list(range(1, len(selected) + 1))
    assert campaign["campaign_rank"].sort_values().tolist() == list(range(1, len(campaign) + 1))

    assert selected["intervention_cost"].sum() <= config["campaign_budget"] + 1e-9
    assert len(selected) <= config["campaign_capacity"]
    for action, action_config in assumptions["action_assumptions"].items():
        assert int((selected["recommended_action"] == action).sum()) <= action_config["capacity"]

    candidates = decisions.loc[
        decisions["churn_model_eligible"]
        & decisions["churn_probability"].ge(config["policy_risk_floor"])
        & decisions["scenario_expected_net_benefit"].gt(0)
    ]
    not_funded = decisions.loc[
        decisions["decision_status"].eq("positive_economics_not_funded")
    ]
    assert set(candidates["customer_id"]) == set(selected["customer_id"]) | set(
        not_funded["customer_id"]
    )

    assert summary["selected_customers"] == len(selected)
    assert summary["candidate_customers"] == len(candidates)
    np.testing.assert_allclose(summary["campaign_spend"], selected["intervention_cost"].sum())
    np.testing.assert_allclose(
        summary["scenario_expected_retention_benefit"],
        selected["scenario_expected_retention_benefit"].sum(),
    )
    np.testing.assert_allclose(
        summary["scenario_expected_net_benefit"],
        selected["scenario_expected_net_benefit"].sum(),
    )
    assert sum(summary["decision_status_counts"].values()) == len(decisions)


def test_retention_outputs_keep_predictions_distinct_from_causal_uplift(
    reports_dir,
    retention_decisions,
):
    assumptions = _load_json(reports_dir / "retention_assumptions.json")
    decisions = retention_decisions

    assert "not measured causal uplift" in assumptions["causal_disclaimer"]
    assert assumptions["action_assumptions"]
    assert "causal_uplift" not in decisions.columns
    assert "incremental_uplift" not in decisions.columns
    assert decisions["expected_revenue_clv_12m"].ge(0).all()
    assert decisions["historical_revenue"].ge(0).all()
