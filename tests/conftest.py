"""Shared fixtures for artifact-level analytics regression tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def require_file(path: Path) -> Path:
    """Return an artifact path or fail with a useful pipeline hint."""

    if not path.is_file():
        pytest.fail(
            f"Required project artifact is missing: {path}. "
            "Run the upstream pipeline notebooks first."
        )

    return path


@pytest.fixture(scope="session")
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def processed_dir(project_root: Path) -> Path:
    return project_root / "data" / "processed"


@pytest.fixture(scope="session")
def reports_dir(project_root: Path) -> Path:
    return project_root / "reports"


@pytest.fixture(scope="session")
def rfm(processed_dir: Path) -> pd.DataFrame:
    return pd.read_parquet(
        require_file(processed_dir / "rfm_customer_segments.parquet")
    )


@pytest.fixture(scope="session")
def ml_segments(processed_dir: Path) -> pd.DataFrame:
    return pd.read_parquet(
        require_file(processed_dir / "ml_customer_segments.parquet")
    )


@pytest.fixture(scope="session")
def churn_snapshots(processed_dir: Path) -> pd.DataFrame:
    dataframe = pd.read_parquet(
        require_file(processed_dir / "churn_snapshots.parquet")
    )

    for column in [
        "snapshot_date",
        "prediction_end_date",
        "first_purchase",
        "last_purchase",
    ]:
        dataframe[column] = pd.to_datetime(dataframe[column])

    return dataframe


@pytest.fixture(scope="session")
def customer_clv(processed_dir: Path) -> pd.DataFrame:
    return pd.read_parquet(
        require_file(processed_dir / "customer_clv.parquet")
    )


@pytest.fixture(scope="session")
def current_churn_scores(processed_dir: Path) -> pd.DataFrame:
    dataframe = pd.read_parquet(
        require_file(processed_dir / "current_churn_scores.parquet")
    )
    dataframe["snapshot_date"] = pd.to_datetime(dataframe["snapshot_date"])
    return dataframe


@pytest.fixture(scope="session")
def retention_decisions(processed_dir: Path) -> pd.DataFrame:
    dataframe = pd.read_parquet(
        require_file(processed_dir / "retention_decisions.parquet")
    )
    dataframe["decision_date"] = pd.to_datetime(dataframe["decision_date"])
    return dataframe


@pytest.fixture(scope="session")
def customer_sales_profile(processed_dir: Path) -> dict[str, Any]:
    sales = pd.read_parquet(
        require_file(processed_dir / "customer_sales.parquet"),
        columns=["customer_id", "invoice_date", "line_amount"],
    )

    return {
        "rows": len(sales),
        "customers": int(sales["customer_id"].nunique()),
        "minimum_date": pd.Timestamp(sales["invoice_date"].min()),
        "maximum_date": pd.Timestamp(sales["invoice_date"].max()),
        "revenue": float(sales["line_amount"].sum()),
    }


def read_json(path: Path) -> dict[str, Any]:
    """Read a required UTF-8 JSON artifact."""

    return json.loads(require_file(path).read_text(encoding="utf-8"))
