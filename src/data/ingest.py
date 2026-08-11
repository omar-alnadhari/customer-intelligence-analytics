"""Load the Online Retail II dataset and convert it to Parquet.

This module:

1. Finds the Online Retail II ZIP file.
2. Extracts the Excel workbook temporarily.
3. Reads both yearly worksheets.
4. Standardizes column names.
5. Adds the source period.
6. Validates the dataset.
7. Saves the combined data as a Parquet file.
"""

from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pandas.api.types import is_numeric_dtype


# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
INTERIM_DATA_DIR = PROJECT_ROOT / "data" / "interim"

OUTPUT_PATH = INTERIM_DATA_DIR / "transactions_raw.parquet"


# ---------------------------------------------------------------------------
# Dataset configuration
# ---------------------------------------------------------------------------

EXPECTED_ROWS_BY_SHEET = {
    "Year 2009-2010": 525_461,
    "Year 2010-2011": 541_910,
}

EXPECTED_TOTAL_ROWS = sum(EXPECTED_ROWS_BY_SHEET.values())

ORIGINAL_COLUMNS = [
    "Invoice",
    "StockCode",
    "Description",
    "Quantity",
    "InvoiceDate",
    "Price",
    "Customer ID",
    "Country",
]

COLUMN_MAPPING = {
    "Invoice": "invoice",
    "StockCode": "stock_code",
    "Description": "description",
    "Quantity": "quantity",
    "InvoiceDate": "invoice_date",
    "Price": "unit_price",
    "Customer ID": "customer_id",
    "Country": "country",
}

# These columns must remain strings because some values contain letters,
# such as cancelled invoices beginning with "C".
TEXT_DTYPES = {
    "Invoice": "string",
    "StockCode": "string",
    "Description": "string",
    "Customer ID": "string",
    "Country": "string",
}


def find_zip_file() -> Path:
    """Find the dataset ZIP file inside data/raw."""

    possible_names = [
        RAW_DATA_DIR / "online_retail_ii.zip",
        RAW_DATA_DIR / "online+retail+ii.zip",
    ]

    for path in possible_names:
        if path.exists():
            return path

    zip_files = list(RAW_DATA_DIR.glob("*.zip"))

    if len(zip_files) == 1:
        return zip_files[0]

    raise FileNotFoundError(
        "Dataset ZIP file was not found.\n"
        f"Place it inside: {RAW_DATA_DIR}\n"
        "Recommended filename: online_retail_ii.zip"
    )


def find_excel_workbook(extracted_directory: Path) -> Path:
    """Find the extracted Excel workbook."""

    workbooks = list(extracted_directory.rglob("*.xlsx"))

    if not workbooks:
        raise FileNotFoundError(
            "No .xlsx workbook was found inside the ZIP file."
        )

    if len(workbooks) > 1:
        workbook_names = [path.name for path in workbooks]

        raise RuntimeError(
            "More than one Excel workbook was found inside the ZIP file: "
            f"{workbook_names}"
        )

    return workbooks[0]


def load_and_prepare_sheet(
    excel_file: pd.ExcelFile,
    sheet_name: str,
) -> pd.DataFrame:
    """Read and prepare one worksheet."""

    print(f"\nReading sheet: {sheet_name}", flush=True)

    dataframe = pd.read_excel(
        excel_file,
        sheet_name=sheet_name,
        dtype=TEXT_DTYPES,
    )

    missing_columns = [
        column
        for column in ORIGINAL_COLUMNS
        if column not in dataframe.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Missing columns in sheet '{sheet_name}': {missing_columns}"
        )

    # Keep only the columns that belong to the original dataset.
    dataframe = dataframe[ORIGINAL_COLUMNS].copy()

    # Convert and validate the date column.
    dataframe["InvoiceDate"] = pd.to_datetime(
        dataframe["InvoiceDate"],
        errors="raise",
    )

    if not is_numeric_dtype(dataframe["Quantity"]):
        raise TypeError(
            f"Quantity is not numeric in sheet '{sheet_name}'."
        )

    if not is_numeric_dtype(dataframe["Price"]):
        raise TypeError(
            f"Price is not numeric in sheet '{sheet_name}'."
        )

    expected_rows = EXPECTED_ROWS_BY_SHEET[sheet_name]
    actual_rows = len(dataframe)

    if actual_rows != expected_rows:
        raise ValueError(
            f"Unexpected row count in sheet '{sheet_name}'. "
            f"Expected {expected_rows:,}, found {actual_rows:,}."
        )

    dataframe = dataframe.rename(columns=COLUMN_MAPPING)

    # Store the period from which every transaction originated.
    dataframe["source_period"] = sheet_name.replace("Year ", "", 1)

    print(f"Rows loaded: {actual_rows:,}", flush=True)

    return dataframe


def ingest_dataset() -> None:
    """Run the complete data-ingestion pipeline."""

    zip_path = find_zip_file()

    INTERIM_DATA_DIR.mkdir(parents=True, exist_ok=True)

    temporary_output_path = OUTPUT_PATH.with_suffix(".tmp.parquet")

    if temporary_output_path.exists():
        temporary_output_path.unlink()

    print("=" * 70)
    print("Online Retail II — Data Ingestion")
    print("=" * 70)
    print(f"Input ZIP: {zip_path}")
    print(f"Output:    {OUTPUT_PATH}")
    print(
        "\nReading the Excel workbook can take several minutes. "
        "Do not interrupt the process.",
        flush=True,
    )

    total_rows = 0
    missing_customer_ids = 0
    minimum_date: pd.Timestamp | None = None
    maximum_date: pd.Timestamp | None = None

    parquet_writer: pq.ParquetWriter | None = None

    try:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)

            print("\nExtracting workbook...", flush=True)

            with zipfile.ZipFile(zip_path, mode="r") as zip_file:
                zip_file.extractall(temporary_path)

            workbook_path = find_excel_workbook(temporary_path)

            print(f"Workbook found: {workbook_path.name}", flush=True)

            with pd.ExcelFile(
                workbook_path,
                engine="openpyxl",
            ) as excel_file:

                available_sheets = set(excel_file.sheet_names)
                expected_sheets = set(EXPECTED_ROWS_BY_SHEET)

                missing_sheets = expected_sheets - available_sheets

                if missing_sheets:
                    raise ValueError(
                        f"Missing worksheets: {sorted(missing_sheets)}"
                    )

                for sheet_name in EXPECTED_ROWS_BY_SHEET:
                    dataframe = load_and_prepare_sheet(
                        excel_file=excel_file,
                        sheet_name=sheet_name,
                    )

                    total_rows += len(dataframe)

                    missing_customer_ids += int(
                        dataframe["customer_id"].isna().sum()
                    )

                    sheet_minimum_date = dataframe["invoice_date"].min()
                    sheet_maximum_date = dataframe["invoice_date"].max()

                    if (
                        minimum_date is None
                        or sheet_minimum_date < minimum_date
                    ):
                        minimum_date = sheet_minimum_date

                    if (
                        maximum_date is None
                        or sheet_maximum_date > maximum_date
                    ):
                        maximum_date = sheet_maximum_date

                    arrow_table = pa.Table.from_pandas(
                        dataframe,
                        preserve_index=False,
                    )

                    if parquet_writer is None:
                        parquet_writer = pq.ParquetWriter(
                            temporary_output_path,
                            arrow_table.schema,
                            compression="snappy",
                        )

                    parquet_writer.write_table(
                        arrow_table,
                        row_group_size=100_000,
                    )

                    # Release the sheet before loading the next one.
                    del dataframe
                    del arrow_table

        if total_rows != EXPECTED_TOTAL_ROWS:
            raise ValueError(
                f"Unexpected total number of rows. "
                f"Expected {EXPECTED_TOTAL_ROWS:,}, "
                f"found {total_rows:,}."
            )

    except Exception:
        if parquet_writer is not None:
            parquet_writer.close()

        if temporary_output_path.exists():
            temporary_output_path.unlink()

        raise

    else:
        if parquet_writer is not None:
            parquet_writer.close()

        temporary_output_path.replace(OUTPUT_PATH)

    output_size_mb = OUTPUT_PATH.stat().st_size / (1024**2)

    print("\n" + "=" * 70)
    print("Ingestion completed successfully")
    print("=" * 70)
    print(f"Total rows:              {total_rows:,}")
    print(f"Total columns:           {len(COLUMN_MAPPING) + 1}")
    print(f"Minimum invoice date:    {minimum_date}")
    print(f"Maximum invoice date:    {maximum_date}")
    print(f"Missing customer IDs:    {missing_customer_ids:,}")
    print(f"Parquet file size:       {output_size_mb:,.2f} MB")
    print(f"Saved to:                {OUTPUT_PATH}")


if __name__ == "__main__":
    ingest_dataset()
