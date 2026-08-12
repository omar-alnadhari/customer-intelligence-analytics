"""Regression tests for ingestion assumptions and transaction cleaning."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.data.clean import EXPECTED_COLUMNS as CLEAN_INPUT_COLUMNS
from src.data.ingest import EXPECTED_ROWS_BY_SHEET, EXPECTED_TOTAL_ROWS


def test_source_archive_identity_and_workbook_member(
    project_root: Path,
) -> None:
    archive_path = project_root / "data" / "raw" / "online+retail+ii.zip"

    assert archive_path.is_file(), (
        "Download the verified UCI archive before running the tests. "
        "See README.md and DATA_PROVENANCE.md."
    )
    assert archive_path.stat().st_size == 45_622_418

    with archive_path.open("rb") as archive_handle:
        archive_sha256 = hashlib.file_digest(
            archive_handle,
            "sha256",
        ).hexdigest()

    assert archive_sha256 == (
        "572e36277c2390fbfde10664750731e0a86f55e33470d91919085f0408e67bfb"
    )

    with zipfile.ZipFile(archive_path) as archive:
        assert archive.namelist() == ["online_retail_II.xlsx"]


def test_ingested_parquet_schema_and_source_period_counts(
    project_root: Path,
) -> None:
    raw_path = project_root / "data" / "interim" / "transactions_raw.parquet"
    parquet = pq.ParquetFile(raw_path)
    schema = parquet.schema_arrow

    assert parquet.metadata.num_rows == EXPECTED_TOTAL_ROWS == 1_067_371
    assert schema.names == CLEAN_INPUT_COLUMNS

    for column in [
        "invoice",
        "stock_code",
        "description",
        "customer_id",
        "country",
        "source_period",
    ]:
        assert pa.types.is_large_string(schema.field(column).type)

    assert pa.types.is_integer(schema.field("quantity").type)
    assert pa.types.is_floating(schema.field("unit_price").type)
    assert pa.types.is_timestamp(schema.field("invoice_date").type)

    source_period = pd.read_parquet(raw_path, columns=["source_period"])
    actual_counts = source_period["source_period"].value_counts().to_dict()
    expected_counts = {
        sheet.replace("Year ", "", 1): rows
        for sheet, rows in EXPECTED_ROWS_BY_SHEET.items()
    }
    assert actual_counts == expected_counts


def test_clean_transaction_flags_follow_documented_rules(
    processed_dir: Path,
) -> None:
    clean = pd.read_parquet(
        processed_dir / "transactions_clean.parquet",
        columns=[
            "invoice",
            "description",
            "quantity",
            "unit_price",
            "customer_id",
            "has_customer_id",
            "has_description",
            "is_cancelled",
            "is_negative_quantity",
            "is_zero_quantity",
            "is_negative_price",
            "is_zero_price",
            "is_return_or_reversal",
            "line_amount",
            "is_valid_sale",
            "is_customer_sale",
            "requires_review",
        ],
    )

    invoice = clean["invoice"].fillna("")
    expected_cancelled = invoice.str.startswith("C", na=False)
    expected_negative_quantity = clean["quantity"] < 0
    expected_zero_quantity = clean["quantity"] == 0
    expected_negative_price = clean["unit_price"] < 0
    expected_zero_price = clean["unit_price"] == 0
    expected_has_customer = clean["customer_id"].notna()
    expected_has_description = clean["description"].notna()
    expected_valid_sale = (
        ~expected_cancelled
        & (clean["quantity"] > 0)
        & (clean["unit_price"] > 0)
    )

    np.testing.assert_array_equal(clean["is_cancelled"], expected_cancelled)
    np.testing.assert_array_equal(
        clean["is_negative_quantity"], expected_negative_quantity
    )
    np.testing.assert_array_equal(clean["is_zero_quantity"], expected_zero_quantity)
    np.testing.assert_array_equal(clean["is_negative_price"], expected_negative_price)
    np.testing.assert_array_equal(clean["is_zero_price"], expected_zero_price)
    np.testing.assert_array_equal(clean["has_customer_id"], expected_has_customer)
    np.testing.assert_array_equal(clean["has_description"], expected_has_description)
    np.testing.assert_array_equal(
        clean["is_return_or_reversal"],
        expected_cancelled | expected_negative_quantity,
    )
    np.testing.assert_allclose(
        clean["line_amount"],
        clean["quantity"] * clean["unit_price"],
        rtol=0,
        atol=1e-12,
    )
    np.testing.assert_array_equal(clean["is_valid_sale"], expected_valid_sale)
    np.testing.assert_array_equal(
        clean["is_customer_sale"], expected_valid_sale & expected_has_customer
    )
    np.testing.assert_array_equal(
        clean["requires_review"],
        (
            expected_cancelled
            | expected_negative_quantity
            | expected_zero_quantity
            | expected_negative_price
            | expected_zero_price
            | ~expected_has_description
        ),
    )


def test_cleaning_row_counts_and_output_subsets(
    project_root: Path,
    processed_dir: Path,
    customer_sales_profile: dict[str, object],
) -> None:
    summary = json.loads(
        (project_root / "reports" / "cleaning_summary.json").read_text(
            encoding="utf-8"
        )
    )
    clean_path = processed_dir / "transactions_clean.parquet"
    clean_metadata = pq.ParquetFile(clean_path).metadata

    raw_rows = summary["input"]["raw_rows"]
    duplicates_removed = summary["cleaning"]["exact_duplicates_removed"]
    assert clean_metadata.num_rows == raw_rows - duplicates_removed == 1_055_238

    clean_flags = pd.read_parquet(
        clean_path,
        columns=["is_valid_sale", "has_customer_id", "is_customer_sale"],
    )

    expected_output_rows = {
        "sales_transactions.parquet": int(clean_flags["is_valid_sale"].sum()),
        "customer_transactions.parquet": int(clean_flags["has_customer_id"].sum()),
        "customer_sales.parquet": int(clean_flags["is_customer_sale"].sum()),
    }

    for filename, expected_rows in expected_output_rows.items():
        assert pq.ParquetFile(processed_dir / filename).metadata.num_rows == expected_rows

    assert expected_output_rows["customer_sales.parquet"] == 793_609
    assert customer_sales_profile["customers"] == 5_878
    assert np.isclose(customer_sales_profile["revenue"], 17_685_460.638)

    sales_flags = pd.read_parquet(
        processed_dir / "sales_transactions.parquet",
        columns=["is_valid_sale"],
    )
    customer_activity_flags = pd.read_parquet(
        processed_dir / "customer_transactions.parquet",
        columns=["has_customer_id"],
    )
    customer_sales_flags = pd.read_parquet(
        processed_dir / "customer_sales.parquet",
        columns=["is_customer_sale", "quantity", "unit_price"],
    )

    assert sales_flags["is_valid_sale"].all()
    assert customer_activity_flags["has_customer_id"].all()
    assert customer_sales_flags["is_customer_sale"].all()
    assert (customer_sales_flags["quantity"] > 0).all()
    assert (customer_sales_flags["unit_price"] > 0).all()
