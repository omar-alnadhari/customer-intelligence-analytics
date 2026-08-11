"""Generate a data-quality report for the raw Online Retail II dataset."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "transactions_raw.parquet"
)

REPORTS_DIR = PROJECT_ROOT / "reports"

JSON_REPORT_PATH = REPORTS_DIR / "data_quality_report.json"
MARKDOWN_REPORT_PATH = REPORTS_DIR / "data_quality_report.md"


EXPECTED_COLUMNS = [
    "invoice",
    "stock_code",
    "description",
    "quantity",
    "invoice_date",
    "unit_price",
    "customer_id",
    "country",
    "source_period",
]


def validate_schema(dataframe: pd.DataFrame) -> None:
    """Ensure that the expected columns are present."""

    actual_columns = dataframe.columns.tolist()

    missing_columns = [
        column
        for column in EXPECTED_COLUMNS
        if column not in actual_columns
    ]

    unexpected_columns = [
        column
        for column in actual_columns
        if column not in EXPECTED_COLUMNS
    ]

    if missing_columns:
        raise ValueError(
            f"Missing required columns: {missing_columns}"
        )

    if unexpected_columns:
        raise ValueError(
            f"Unexpected columns found: {unexpected_columns}"
        )


def safe_number(value: Any) -> Any:
    """Convert NumPy and pandas scalar values to JSON-safe Python values."""

    if pd.isna(value):
        return None

    if hasattr(value, "item"):
        return value.item()

    return value


def build_data_quality_report(
    dataframe: pd.DataFrame,
) -> dict[str, Any]:
    """Calculate the main data-quality and dataset-profile statistics."""

    invoice_text = dataframe["invoice"].astype("string")

    cancelled_mask = invoice_text.str.startswith(
        "C",
        na=False,
    )

    negative_quantity_mask = dataframe["quantity"] < 0
    zero_quantity_mask = dataframe["quantity"] == 0

    negative_price_mask = dataframe["unit_price"] < 0
    zero_price_mask = dataframe["unit_price"] == 0

    missing_values = {
        column: int(count)
        for column, count in dataframe.isna().sum().items()
    }

    missing_percentages = {
        column: round(
            count / len(dataframe) * 100,
            4,
        )
        for column, count in missing_values.items()
    }

    rows_by_period = {
        str(period): int(count)
        for period, count in dataframe[
            "source_period"
        ].value_counts(dropna=False).items()
    }

    top_countries = {
        str(country): int(count)
        for country, count in dataframe[
            "country"
        ].value_counts(dropna=False).head(15).items()
    }

    quantity_statistics = {
        key: safe_number(value)
        for key, value in dataframe[
            "quantity"
        ].describe().to_dict().items()
    }

    unit_price_statistics = {
        key: safe_number(value)
        for key, value in dataframe[
            "unit_price"
        ].describe().to_dict().items()
    }

    report = {
        "dataset_overview": {
            "rows": int(len(dataframe)),
            "columns": int(dataframe.shape[1]),
            "memory_usage_mb": round(
                dataframe.memory_usage(
                    deep=True
                ).sum()
                / (1024**2),
                2,
            ),
            "minimum_invoice_date": str(
                dataframe["invoice_date"].min()
            ),
            "maximum_invoice_date": str(
                dataframe["invoice_date"].max()
            ),
        },
        "business_entities": {
            "unique_invoices": int(
                dataframe["invoice"].nunique(
                    dropna=True
                )
            ),
            "unique_products": int(
                dataframe["stock_code"].nunique(
                    dropna=True
                )
            ),
            "unique_customers": int(
                dataframe["customer_id"].nunique(
                    dropna=True
                )
            ),
            "unique_countries": int(
                dataframe["country"].nunique(
                    dropna=True
                )
            ),
        },
        "missing_values": missing_values,
        "missing_percentages": missing_percentages,
        "duplicates": {
            "exact_duplicate_rows": int(
                dataframe.duplicated().sum()
            ),
            "exact_duplicate_percentage": round(
                dataframe.duplicated().mean() * 100,
                4,
            ),
        },
        "transaction_quality": {
            "cancelled_rows": int(
                cancelled_mask.sum()
            ),
            "cancelled_percentage": round(
                cancelled_mask.mean() * 100,
                4,
            ),
            "negative_quantity_rows": int(
                negative_quantity_mask.sum()
            ),
            "zero_quantity_rows": int(
                zero_quantity_mask.sum()
            ),
            "negative_price_rows": int(
                negative_price_mask.sum()
            ),
            "zero_price_rows": int(
                zero_price_mask.sum()
            ),
            "cancelled_with_positive_quantity": int(
                (
                    cancelled_mask
                    & (
                        dataframe["quantity"]
                        > 0
                    )
                ).sum()
            ),
            "negative_quantity_without_cancellation_code": int(
                (
                    negative_quantity_mask
                    & ~cancelled_mask
                ).sum()
            ),
        },
        "numeric_statistics": {
            "quantity": quantity_statistics,
            "unit_price": unit_price_statistics,
        },
        "rows_by_source_period": rows_by_period,
        "top_15_countries_by_rows": top_countries,
    }

    return report


def create_markdown_report(
    report: dict[str, Any],
) -> str:
    """Create a human-readable Markdown data-quality report."""

    overview = report["dataset_overview"]
    entities = report["business_entities"]
    duplicates = report["duplicates"]
    quality = report["transaction_quality"]

    lines = [
        "# Online Retail II — Data Quality Report",
        "",
        "## Dataset overview",
        "",
        f"- Rows: {overview['rows']:,}",
        f"- Columns: {overview['columns']:,}",
        (
            "- DataFrame memory usage: "
            f"{overview['memory_usage_mb']:,.2f} MB"
        ),
        (
            "- Minimum invoice date: "
            f"{overview['minimum_invoice_date']}"
        ),
        (
            "- Maximum invoice date: "
            f"{overview['maximum_invoice_date']}"
        ),
        "",
        "## Business entities",
        "",
        f"- Unique invoices: {entities['unique_invoices']:,}",
        f"- Unique products: {entities['unique_products']:,}",
        f"- Unique customers: {entities['unique_customers']:,}",
        f"- Unique countries: {entities['unique_countries']:,}",
        "",
        "## Missing values",
        "",
        "| Column | Missing rows | Missing percentage |",
        "|---|---:|---:|",
    ]

    for column, count in report["missing_values"].items():
        percentage = report[
            "missing_percentages"
        ][column]

        lines.append(
            f"| {column} | {count:,} | {percentage:.4f}% |"
        )

    lines.extend(
        [
            "",
            "## Duplicate rows",
            "",
            (
                "- Exact duplicate rows: "
                f"{duplicates['exact_duplicate_rows']:,}"
            ),
            (
                "- Exact duplicate percentage: "
                f"{duplicates['exact_duplicate_percentage']:.4f}%"
            ),
            "",
            "## Transaction-quality indicators",
            "",
            f"- Cancelled rows: {quality['cancelled_rows']:,}",
            (
                "- Cancelled percentage: "
                f"{quality['cancelled_percentage']:.4f}%"
            ),
            (
                "- Negative quantity rows: "
                f"{quality['negative_quantity_rows']:,}"
            ),
            (
                "- Zero quantity rows: "
                f"{quality['zero_quantity_rows']:,}"
            ),
            (
                "- Negative price rows: "
                f"{quality['negative_price_rows']:,}"
            ),
            (
                "- Zero price rows: "
                f"{quality['zero_price_rows']:,}"
            ),
            (
                "- Cancelled invoices with positive quantities: "
                f"{quality['cancelled_with_positive_quantity']:,}"
            ),
            (
                "- Negative quantities without cancellation code: "
                f"{quality['negative_quantity_without_cancellation_code']:,}"
            ),
            "",
            "## Rows by source period",
            "",
            "| Source period | Rows |",
            "|---|---:|",
        ]
    )

    for period, count in report[
        "rows_by_source_period"
    ].items():
        lines.append(
            f"| {period} | {count:,} |"
        )

    lines.extend(
        [
            "",
            "## Top countries by transaction rows",
            "",
            "| Country | Rows |",
            "|---|---:|",
        ]
    )

    for country, count in report[
        "top_15_countries_by_rows"
    ].items():
        lines.append(
            f"| {country} | {count:,} |"
        )

    lines.extend(
        [
            "",
            "## Initial interpretation",
            "",
            (
                "- Missing customer IDs require separate treatment because "
                "customer-level segmentation, churn prediction, and CLV "
                "cannot be performed without a customer identifier."
            ),
            (
                "- Cancelled invoices and negative quantities should not be "
                "removed blindly. They provide useful information about "
                "returns, cancellations, and customer behavior."
            ),
            (
                "- Exact duplicates must be investigated before removal to "
                "determine whether they are accidental duplicates or valid "
                "repeated invoice lines."
            ),
            (
                "- Zero or negative prices require investigation before "
                "revenue and customer-value calculations."
            ),
            "",
        ]
    )

    return "\n".join(lines)


def main() -> None:
    """Run the data-quality profiling process."""

    if not INPUT_PATH.exists():
        raise FileNotFoundError(
            f"Input file was not found: {INPUT_PATH}\n"
            "Run src/data/ingest.py first."
        )

    REPORTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 70)
    print("Online Retail II — Data Quality Profiling")
    print("=" * 70)
    print(f"Reading: {INPUT_PATH}")

    dataframe = pd.read_parquet(INPUT_PATH)

    validate_schema(dataframe)

    report = build_data_quality_report(
        dataframe
    )

    JSON_REPORT_PATH.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    markdown_report = create_markdown_report(
        report
    )

    MARKDOWN_REPORT_PATH.write_text(
        markdown_report,
        encoding="utf-8",
    )

    print("\nData-quality profiling completed successfully.")
    print(
        "JSON report:     "
        f"{JSON_REPORT_PATH}"
    )
    print(
        "Markdown report: "
        f"{MARKDOWN_REPORT_PATH}"
    )

    print("\nMain findings:")
    print(
        f"Rows:                   "
        f"{report['dataset_overview']['rows']:,}"
    )
    print(
        f"Unique customers:       "
        f"{report['business_entities']['unique_customers']:,}"
    )
    print(
        f"Missing customer IDs:   "
        f"{report['missing_values']['customer_id']:,}"
    )
    print(
        f"Exact duplicate rows:   "
        f"{report['duplicates']['exact_duplicate_rows']:,}"
    )
    print(
        f"Cancelled rows:         "
        f"{report['transaction_quality']['cancelled_rows']:,}"
    )
    print(
        f"Negative quantities:    "
        f"{report['transaction_quality']['negative_quantity_rows']:,}"
    )
    print(
        f"Zero prices:            "
        f"{report['transaction_quality']['zero_price_rows']:,}"
    )


if __name__ == "__main__":
    main()
