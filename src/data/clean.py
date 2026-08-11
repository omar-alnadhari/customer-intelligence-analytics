"""Clean and classify the Online Retail II transactions.

The raw dataset is never modified. This script:

1. Removes exact duplicate rows.
2. Standardizes text, date, and numeric fields.
3. Adds transaction-quality and business flags.
4. Calculates the line amount.
5. Produces separate datasets for different analytical purposes.
6. Writes a reproducible cleaning summary.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "transactions_raw.parquet"
)

PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed"
REPORTS_DIR = PROJECT_ROOT / "reports"

CLEAN_TRANSACTIONS_PATH = (
    PROCESSED_DATA_DIR / "transactions_clean.parquet"
)

SALES_TRANSACTIONS_PATH = (
    PROCESSED_DATA_DIR / "sales_transactions.parquet"
)

CUSTOMER_TRANSACTIONS_PATH = (
    PROCESSED_DATA_DIR / "customer_transactions.parquet"
)

CUSTOMER_SALES_PATH = (
    PROCESSED_DATA_DIR / "customer_sales.parquet"
)

CLEANING_SUMMARY_PATH = (
    REPORTS_DIR / "cleaning_summary.json"
)


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

TEXT_COLUMNS = [
    "invoice",
    "stock_code",
    "description",
    "customer_id",
    "country",
    "source_period",
]


def validate_input_schema(dataframe: pd.DataFrame) -> None:
    """Validate that all expected raw columns are available."""

    missing_columns = [
        column
        for column in EXPECTED_COLUMNS
        if column not in dataframe.columns
    ]

    unexpected_columns = [
        column
        for column in dataframe.columns
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


def standardize_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Standardize text, numeric, and date columns."""

    cleaned = dataframe.copy()

    for column in TEXT_COLUMNS:
        cleaned[column] = (
            cleaned[column]
            .astype("string")
            .str.strip()
        )

    # Empty strings should be represented as missing values.
    cleaned[TEXT_COLUMNS] = cleaned[
        TEXT_COLUMNS
    ].replace("", pd.NA)

    # Invoice and stock codes are identifiers rather than numbers.
    cleaned["invoice"] = cleaned["invoice"].str.upper()
    cleaned["stock_code"] = cleaned["stock_code"].str.upper()

    cleaned["invoice_date"] = pd.to_datetime(
        cleaned["invoice_date"],
        errors="raise",
    )

    cleaned["quantity"] = pd.to_numeric(
        cleaned["quantity"],
        errors="raise",
    )

    cleaned["unit_price"] = pd.to_numeric(
        cleaned["unit_price"],
        errors="raise",
    )

    return cleaned


def remove_exact_duplicates(
    dataframe: pd.DataFrame,
) -> tuple[pd.DataFrame, int]:
    """Remove exact duplicate rows while retaining the first occurrence."""

    duplicate_mask = dataframe.duplicated(
        subset=EXPECTED_COLUMNS,
        keep="first",
    )

    duplicate_count = int(duplicate_mask.sum())

    deduplicated = (
        dataframe.loc[~duplicate_mask]
        .copy()
        .reset_index(drop=True)
    )

    return deduplicated, duplicate_count


def add_transaction_features(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """Add data-quality and business-analysis features."""

    featured = dataframe.copy()

    invoice_text = featured["invoice"].fillna("")

    featured["has_customer_id"] = (
        featured["customer_id"].notna()
    )

    featured["has_description"] = (
        featured["description"].notna()
    )

    featured["is_cancelled"] = invoice_text.str.startswith(
        "C",
        na=False,
    )

    featured["is_negative_quantity"] = (
        featured["quantity"] < 0
    )

    featured["is_zero_quantity"] = (
        featured["quantity"] == 0
    )

    featured["is_negative_price"] = (
        featured["unit_price"] < 0
    )

    featured["is_zero_price"] = (
        featured["unit_price"] == 0
    )

    # A return or reversal may be represented by a cancelled invoice,
    # a negative quantity, or both.
    featured["is_return_or_reversal"] = (
        featured["is_cancelled"]
        | featured["is_negative_quantity"]
    )

    featured["line_amount"] = (
        featured["quantity"]
        * featured["unit_price"]
    )

    # A valid sale must represent a positive, non-cancelled transaction.
    # Customer ID is intentionally not required here because anonymous
    # sales remain useful for general revenue analysis.
    featured["is_valid_sale"] = (
        ~featured["is_cancelled"]
        & (featured["quantity"] > 0)
        & (featured["unit_price"] > 0)
    )

    featured["is_customer_sale"] = (
        featured["is_valid_sale"]
        & featured["has_customer_id"]
    )

    # Rows not representing normal sales are retained for auditing and
    # behavioural analysis rather than deleted.
    featured["requires_review"] = (
        featured["is_cancelled"]
        | featured["is_negative_quantity"]
        | featured["is_zero_quantity"]
        | featured["is_negative_price"]
        | featured["is_zero_price"]
        | ~featured["has_description"]
    )

    featured = featured.sort_values(
        by=[
            "invoice_date",
            "invoice",
            "stock_code",
        ],
        kind="stable",
    ).reset_index(drop=True)

    return featured


def save_parquet(
    dataframe: pd.DataFrame,
    path: Path,
) -> None:
    """Save a DataFrame safely as a compressed Parquet file."""

    temporary_path = path.with_suffix(".tmp.parquet")

    if temporary_path.exists():
        temporary_path.unlink()

    dataframe.to_parquet(
        temporary_path,
        index=False,
        compression="snappy",
    )

    temporary_path.replace(path)


def json_safe(value: Any) -> Any:
    """Convert pandas or NumPy scalar values into JSON-safe values."""

    if pd.isna(value):
        return None

    if hasattr(value, "item"):
        return value.item()

    return value


def create_cleaning_summary(
    raw_rows: int,
    cleaned: pd.DataFrame,
    duplicates_removed: int,
    sales: pd.DataFrame,
    customer_transactions: pd.DataFrame,
    customer_sales: pd.DataFrame,
) -> dict[str, Any]:
    """Build a summary of cleaning decisions and generated datasets."""

    return {
        "input": {
            "raw_rows": raw_rows,
        },
        "cleaning": {
            "exact_duplicates_removed": duplicates_removed,
            "rows_after_deduplication": int(len(cleaned)),
            "rows_with_customer_id": int(
                cleaned["has_customer_id"].sum()
            ),
            "rows_without_customer_id": int(
                (~cleaned["has_customer_id"]).sum()
            ),
            "cancelled_rows": int(
                cleaned["is_cancelled"].sum()
            ),
            "negative_quantity_rows": int(
                cleaned["is_negative_quantity"].sum()
            ),
            "zero_quantity_rows": int(
                cleaned["is_zero_quantity"].sum()
            ),
            "negative_price_rows": int(
                cleaned["is_negative_price"].sum()
            ),
            "zero_price_rows": int(
                cleaned["is_zero_price"].sum()
            ),
            "return_or_reversal_rows": int(
                cleaned["is_return_or_reversal"].sum()
            ),
            "rows_requiring_review": int(
                cleaned["requires_review"].sum()
            ),
        },
        "output_datasets": {
            "transactions_clean_rows": int(len(cleaned)),
            "sales_transactions_rows": int(len(sales)),
            "customer_transactions_rows": int(
                len(customer_transactions)
            ),
            "customer_sales_rows": int(
                len(customer_sales)
            ),
        },
        "business_overview": {
            "unique_known_customers": int(
                cleaned["customer_id"].nunique(
                    dropna=True
                )
            ),
            "unique_sales_customers": int(
                customer_sales["customer_id"].nunique(
                    dropna=True
                )
            ),
            "valid_sales_revenue": json_safe(
                sales["line_amount"].sum()
            ),
            "known_customer_sales_revenue": json_safe(
                customer_sales["line_amount"].sum()
            ),
            "minimum_invoice_date": str(
                cleaned["invoice_date"].min()
            ),
            "maximum_invoice_date": str(
                cleaned["invoice_date"].max()
            ),
        },
        "rules": {
            "duplicates": (
                "Exact duplicate rows were removed while retaining "
                "the first occurrence."
            ),
            "missing_customer_ids": (
                "Rows without customer IDs were retained for general "
                "sales analysis but excluded from customer-level datasets."
            ),
            "returns_and_cancellations": (
                "Returns and cancellations were retained in the complete "
                "and customer-transaction datasets, but excluded from "
                "valid-sales datasets."
            ),
            "zero_or_negative_prices": (
                "Rows with non-positive prices were retained for auditing "
                "but excluded from valid-sales datasets."
            ),
        },
    }


def main() -> None:
    """Run the complete transaction-cleaning pipeline."""

    if not INPUT_PATH.exists():
        raise FileNotFoundError(
            f"Input file was not found: {INPUT_PATH}\n"
            "Run src/data/ingest.py first."
        )

    PROCESSED_DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 70)
    print("Online Retail II — Transaction Cleaning")
    print("=" * 70)
    print(f"Reading: {INPUT_PATH}")

    raw = pd.read_parquet(INPUT_PATH)

    validate_input_schema(raw)

    raw_rows = len(raw)

    standardized = standardize_columns(raw)

    cleaned, duplicates_removed = remove_exact_duplicates(
        standardized
    )

    cleaned = add_transaction_features(cleaned)

    # All valid positive sales, including anonymous customers.
    sales = cleaned.loc[
        cleaned["is_valid_sale"]
    ].copy()

    # All known-customer activity, including returns and cancellations.
    customer_transactions = cleaned.loc[
        cleaned["has_customer_id"]
    ].copy()

    # Valid positive sales belonging to known customers.
    customer_sales = cleaned.loc[
        cleaned["is_customer_sale"]
    ].copy()

    # Fundamental consistency checks.
    if len(cleaned) != raw_rows - duplicates_removed:
        raise RuntimeError(
            "Deduplication row-count validation failed."
        )

    if not customer_sales["customer_id"].notna().all():
        raise RuntimeError(
            "Customer sales contain missing customer IDs."
        )

    if not customer_sales["is_valid_sale"].all():
        raise RuntimeError(
            "Customer sales contain invalid sale rows."
        )

    if not (customer_sales["quantity"] > 0).all():
        raise RuntimeError(
            "Customer sales contain non-positive quantities."
        )

    if not (customer_sales["unit_price"] > 0).all():
        raise RuntimeError(
            "Customer sales contain non-positive prices."
        )

    print("\nSaving processed datasets...", flush=True)

    save_parquet(
        cleaned,
        CLEAN_TRANSACTIONS_PATH,
    )

    save_parquet(
        sales,
        SALES_TRANSACTIONS_PATH,
    )

    save_parquet(
        customer_transactions,
        CUSTOMER_TRANSACTIONS_PATH,
    )

    save_parquet(
        customer_sales,
        CUSTOMER_SALES_PATH,
    )

    summary = create_cleaning_summary(
        raw_rows=raw_rows,
        cleaned=cleaned,
        duplicates_removed=duplicates_removed,
        sales=sales,
        customer_transactions=customer_transactions,
        customer_sales=customer_sales,
    )

    CLEANING_SUMMARY_PATH.write_text(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print("\n" + "=" * 70)
    print("Cleaning completed successfully")
    print("=" * 70)

    print(f"Raw rows:                    {raw_rows:,}")
    print(f"Exact duplicates removed:    {duplicates_removed:,}")
    print(f"Clean transaction rows:      {len(cleaned):,}")
    print(f"Valid sales rows:            {len(sales):,}")
    print(
        f"Known-customer transactions: "
        f"{len(customer_transactions):,}"
    )
    print(
        f"Known-customer sales:        "
        f"{len(customer_sales):,}"
    )
    print(
        f"Unique known customers:      "
        f"{cleaned['customer_id'].nunique(dropna=True):,}"
    )
    print(
        f"Unique purchasing customers: "
        f"{customer_sales['customer_id'].nunique(dropna=True):,}"
    )
    print(
        f"Valid sales revenue:         "
        f"{sales['line_amount'].sum():,.2f}"
    )

    print("\nSaved files:")
    print(f"- {CLEAN_TRANSACTIONS_PATH}")
    print(f"- {SALES_TRANSACTIONS_PATH}")
    print(f"- {CUSTOMER_TRANSACTIONS_PATH}")
    print(f"- {CUSTOMER_SALES_PATH}")
    print(f"- {CLEANING_SUMMARY_PATH}")


if __name__ == "__main__":
    main()

