# Data Provenance

## Source record

| Field | Value |
|---|---|
| Dataset | Online Retail II |
| Creator | Daqing Chen |
| Repository | UCI Machine Learning Repository |
| Official page | <https://archive.ics.uci.edu/dataset/502/online%2Bretail%2Bii> |
| DOI | <https://doi.org/10.24432/C5CG6D> |
| Direct archive | <https://archive.ics.uci.edu/static/public/502/online%2Bretail%2Bii.zip> |
| License | CC BY 4.0 |
| UCI instance count | 1,067,371 |
| Transaction dates | 2009-12-01 through 2011-12-09 |

Recommended attribution:

> Chen, D. (2012). Online Retail II [Dataset]. UCI Machine Learning
> Repository. https://doi.org/10.24432/C5CG6D

## Expected local archive

The ingestion code accepts a ZIP in `data/raw/` and recognizes the official
download name. The reproducible project path is:

```text
data/raw/online+retail+ii.zip
```

Verified archive identity:

- Size: `45,622,418` bytes
- SHA-256:
  `572e36277c2390fbfde10664750731e0a86f55e33470d91919085f0408e67bfb`
- ZIP member: `online_retail_II.xlsx`
- Workbook sheets: `Year 2009-2010` and `Year 2010-2011`
- Expected sheet rows: `525,461` and `541,910`

Download the official archive, leave it compressed, and rename it only if
needed to match the expected project path. Verify it cross-platform with:

```console
python -c "import hashlib, pathlib; p=pathlib.Path('data/raw/online+retail+ii.zip'); print(hashlib.file_digest(p.open('rb'), 'sha256').hexdigest())"
```

The checksum identifies the exact archive used for the verified run. If UCI
repackages the download in the future, compare the contained workbook and
source metadata before accepting a different checksum.

## Raw schema

`src/data/ingest.py` validates and standardizes these workbook fields:

| Workbook field | Project field | Role |
|---|---|---|
| Invoice | `invoice` | Invoice identifier; cancellation codes can start with C |
| StockCode | `stock_code` | Product identifier |
| Description | `description` | Product description; may be missing |
| Quantity | `quantity` | Line quantity; negative values can represent returns |
| InvoiceDate | `invoice_date` | Transaction timestamp |
| Price | `unit_price` | Unit price in sterling |
| Customer ID | `customer_id` | Customer identifier; may be missing |
| Country | `country` | Customer country |
| Derived | `source_period` | Source workbook period |

The ingest stage writes 1,067,371 rows and 9 columns to
`data/interim/transactions_raw.parquet`.

## Transformation lineage

```text
UCI ZIP / XLSX
  -> src/data/ingest.py
  -> data/interim/transactions_raw.parquet
  -> src/data/validate.py
  -> reports/data_quality_report.{json,md}
  -> src/data/clean.py
  -> data/processed/transactions_clean.parquet
     |-> sales_transactions.parquet
     |-> customer_transactions.parquet
     `-> customer_sales.parquet
  -> notebooks/01_data_understanding.ipynb
  -> notebooks/02_rfm_segmentation.ipynb
  -> notebooks/03_ml_customer_segmentation.ipynb
  -> notebooks/04_churn_dataset.ipynb
  -> notebooks/05_churn_modeling.ipynb
  -> notebooks/06_clv_modeling.ipynb
  -> notebooks/07_retention_decision_engine.ipynb
  -> customer_clv.parquet / current_churn_scores.parquet
  -> retention_decisions.parquet / retention_campaign_targets.csv
```

## Cleaning rules and observed row flow

The raw archive is never modified. `src/data/clean.py`:

1. standardizes text, dates, and numeric types;
2. removes 12,133 exact duplicate rows, retaining the first occurrence;
3. records cancellation, quantity, price, return/reversal, and review flags;
4. calculates `line_amount = quantity * unit_price`;
5. defines a valid sale as positive quantity, positive price, and a
   non-cancelled invoice; and
6. preserves returns/cancellations in the audit and customer-activity datasets.

Verified row flow:

| Artifact | Rows | Purpose |
|---|---:|---|
| `transactions_raw.parquet` | 1,067,371 | Standardized source rows |
| `transactions_clean.parquet` | 1,055,238 | Deduplicated audit layer |
| `sales_transactions.parquet` | 1,029,609 | Valid positive sales, anonymous included |
| `customer_transactions.parquet` | 812,368 | All known-customer activity |
| `customer_sales.parquet` | 793,609 | Valid positive known-customer sales |

There are 5,942 known customer IDs in the activity data and 5,878 customers
with a valid positive purchase. Customer-level segmentation, churn, and CLV use
the latter population.

## Integrity and reproducibility controls

- Ingestion checks sheet names, row counts, schema, numeric types, and dates.
- Validation records missingness, duplicates, anomalies, and source-period
  counts before cleaning.
- Cleaning writes through temporary Parquet paths before atomic replacement.
- Churn features are built strictly from data available before each snapshot.
- The current churn scorer reconstructs the historical test snapshot and checks
  all 28 model features exactly before scoring the final decision date.
- Customer-level joins assert one row per customer and preserve the 5,878-row
  analytical spine.
- The pipeline runner stops on the first failed script, notebook, or assertion.
- Before ingestion, the runner verifies the source archive's expected byte size
  and SHA-256.

## Storage and redistribution

`data/raw/*`, `data/interim/*`, `data/processed/*`, and `models/*` are ignored by
Git. A clone must reacquire the UCI archive and rebuild generated data/model
artifacts. This avoids treating a local binary copy as source code and keeps
the external dataset's CC BY 4.0 attribution explicit.

See [README.md](README.md) for environment setup, full commands, outputs,
metrics, and interpretation limits.
