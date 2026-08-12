# Customer Intelligence Analytics

An end-to-end customer analytics project that turns two years of retail
transactions into customer segments, churn risk, predictive customer lifetime
value (CLV), and a budget-constrained retention planning shortlist.

The business problem is not simply to identify customers who look valuable or
likely to lapse. It is to combine **risk, future value, customer context, action
cost, and operational capacity** in one reproducible decision process. The
project therefore separates:

- historical revenue from expected future revenue;
- churn-model evaluation from current customer scoring;
- predictive ranking from assumed campaign economics; and
- a planning shortlist from a send-ready campaign audience.

## What the project delivers

| Stage | Business question | Primary output |
|---|---|---|
| Data preparation | Which transactions are reliable for sales and customer analysis? | `data/processed/customer_sales.parquet` |
| RFM segmentation | Which customers are recent, frequent, and valuable? | `data/processed/rfm_customer_segments.parquet` |
| ML segmentation | Which behavioral customer groups emerge from the data? | `data/processed/ml_customer_segments.parquet` |
| Churn dataset | How can 90-day inactivity be modeled without temporal leakage? | `data/processed/churn_snapshots.parquet` |
| Churn model | Which model-supported customers are likely to make no purchase in the next 90 days? | `models/churn_random_forest.joblib` |
| CLV | What future purchase volume and revenue are expected over 12 months? | `data/processed/customer_clv.parquet` |
| Retention engine | Which actions maximize scenario net benefit within budget and capacity? | `data/processed/retention_decisions.parquet` and `reports/retention_campaign_targets.csv` |

## Official data source and provenance

This project uses **Online Retail II** from the UCI Machine Learning
Repository:

- [Official dataset page](https://archive.ics.uci.edu/dataset/502/online%2Bretail%2Bii)
- [Direct archive download](https://archive.ics.uci.edu/static/public/502/online%2Bretail%2Bii.zip)
- [DOI: 10.24432/C5CG6D](https://doi.org/10.24432/C5CG6D)
- Citation: Chen, D. (2012). *Online Retail II* [Dataset]. UCI Machine
  Learning Repository.
- License: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)

UCI describes 1,067,371 transactions from a UK-based non-store retailer,
covering 2009-12-01 through 2011-12-09. Download the archive without extracting
it and place it at:

```text
data/raw/online+retail+ii.zip
```

PowerShell:

```powershell
New-Item -ItemType Directory -Force data/raw | Out-Null
Invoke-WebRequest `
  -Uri "https://archive.ics.uci.edu/static/public/502/online%2Bretail%2Bii.zip" `
  -OutFile "data/raw/online+retail+ii.zip"
```

macOS or Linux:

```bash
mkdir -p data/raw
curl -L "https://archive.ics.uci.edu/static/public/502/online%2Bretail%2Bii.zip" \
  -o "data/raw/online+retail+ii.zip"
```

Expected archive identity:

| Property | Expected value |
|---|---|
| Filename | `online+retail+ii.zip` |
| Size | `45,622,418` bytes |
| SHA-256 | `572e36277c2390fbfde10664750731e0a86f55e33470d91919085f0408e67bfb` |
| Contained workbook | `online_retail_II.xlsx` |

Verify the file with Python on any supported platform:

```console
python -c "import hashlib, pathlib; p=pathlib.Path('data/raw/online+retail+ii.zip'); print(hashlib.file_digest(p.open('rb'), 'sha256').hexdigest())"
```

See [DATA_PROVENANCE.md](DATA_PROVENANCE.md) for the source citation, integrity
checks, expected schema, and raw-to-decision lineage.

## Environment setup

The verified environment is Python **3.14.6**, recorded in `.python-version`.
Direct dependencies are pinned in `requirements.txt`; exact versions matter in
particular for loading the saved scikit-learn model.

### Windows PowerShell

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### macOS or Linux

```bash
python3.14 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt
```

If a Python version manager reads `.python-version`, install/select 3.14.6
before creating the virtual environment. Run all commands from the repository
root.

## Reproduce the complete pipeline

After placing the verified UCI archive in `data/raw/`, use the cross-platform
runner. It executes ingestion, validation, cleaning, and notebooks 01 through
07 in dependency order using the active Python interpreter. Before ingestion,
it verifies the source archive's byte size and SHA-256:

```console
python run_pipeline.py
```

When the virtual environment is not activated, invoke it explicitly:

```powershell
.\.venv\Scripts\python.exe run_pipeline.py
```

```bash
./.venv/bin/python run_pipeline.py
```

Useful runner options:

```console
python run_pipeline.py --list-stages
python run_pipeline.py --dry-run
python run_pipeline.py --start-at clean --stop-after 03
python run_pipeline.py --start-at 06 --notebook-timeout 1800
```

The runner fails immediately when a stage fails. It executes notebooks in
place, so their saved outputs and execution counts document the verified run.
It does not delete old artifacts before rebuilding.

## Manual raw-to-final commands

The same process can be run one stage at a time. Use the virtual environment's
Python executable if the environment is not activated.

```console
python src/data/ingest.py
python src/data/validate.py
python src/data/clean.py

python -m jupyter nbconvert --to notebook --execute --inplace notebooks/01_data_understanding.ipynb --ExecutePreprocessor.timeout=1800
python -m jupyter nbconvert --to notebook --execute --inplace notebooks/02_rfm_segmentation.ipynb --ExecutePreprocessor.timeout=1800
python -m jupyter nbconvert --to notebook --execute --inplace notebooks/03_ml_customer_segmentation.ipynb --ExecutePreprocessor.timeout=1800
python -m jupyter nbconvert --to notebook --execute --inplace notebooks/04_churn_dataset.ipynb --ExecutePreprocessor.timeout=1800
python -m jupyter nbconvert --to notebook --execute --inplace notebooks/05_churn_modeling.ipynb --ExecutePreprocessor.timeout=1800
python -m jupyter nbconvert --to notebook --execute --inplace notebooks/06_clv_modeling.ipynb --ExecutePreprocessor.timeout=1800
python -m jupyter nbconvert --to notebook --execute --inplace notebooks/07_retention_decision_engine.ipynb --ExecutePreprocessor.timeout=1800
```

Notebook order is significant:

1. `01_data_understanding.ipynb`
2. `02_rfm_segmentation.ipynb`
3. `03_ml_customer_segmentation.ipynb`
4. `04_churn_dataset.ipynb`
5. `05_churn_modeling.ipynb`
6. `06_clv_modeling.ipynb`
7. `07_retention_decision_engine.ipynb`

## Canonical outputs

Use Parquet files as canonical machine-readable datasets and CSV/JSON files as
portable business/reporting artifacts.

### Data and model artifacts

- `data/interim/transactions_raw.parquet`: standardized two-sheet ingest.
- `data/processed/transactions_clean.parquet`: deduplicated audit dataset with
  quality and transaction-type flags.
- `data/processed/sales_transactions.parquet`: valid positive sales, including
  anonymous transactions.
- `data/processed/customer_transactions.parquet`: known-customer activity,
  including returns and cancellations.
- `data/processed/customer_sales.parquet`: valid positive known-customer sales.
- `data/processed/rfm_customer_segments.parquet`: one row per customer with RFM
  measures, segments, tiers, and actions.
- `data/processed/ml_customer_segments.parquet`: RFM spine plus ML cluster and
  return behavior.
- `data/processed/churn_snapshots.parquet`: leakage-safe historical churn
  snapshots and labels.
- `models/churn_random_forest.joblib`: fitted churn model, ordered feature list,
  threshold, and prediction horizon.
- `data/processed/customer_clv.parquet`: historical value, predictive CLV,
  predictive tiers, RFM segments, and ML clusters.
- `data/processed/current_churn_scores.parquet`: time-aligned scores for
  customers inside the churn model's 180-day support.
- `data/processed/retention_decisions.parquet`: all-customer decision table with
  scenario economics and allocation status.

### Business-facing reports

- `reports/churn_final_test_metrics.json`: temporal test-set performance.
- `reports/clv_model_summary.json`: validation, model parameters, and CLV
  distribution summary.
- `reports/customer_clv.csv`: portable all-customer CLV export.
- `reports/retention_assumptions.json`: configurable economics and causal
  boundary.
- `reports/retention_engine_summary.json`: campaign constraints, counts, and
  scenario totals.
- `reports/retention_campaign_targets.csv`: funded, ranked planning shortlist.
- `reports/final_business_report.md`: consolidated executive and analytical
  interpretation of the complete project.
- `reports/figures/`: saved charts from every analytical stage.

## Automated validation

After the pipeline has generated its ignored data and model artifacts, run the
automated integrity suite from the repository root:

```console
python -m pytest -q
```

The tests cover source/schema assumptions, cleaning rules, RFM and clustering
integrity, point-in-time churn construction, temporal split separation, CLV
sanity checks, and retention economics and constraints. Missing generated
artifacts are treated as an incomplete rebuild rather than silently skipped.

The GitHub Actions workflow in `.github/workflows/ci.yml` performs the same
fresh-clone process on pushes to `main` and pull requests: it installs the
pinned environment, downloads the official UCI archive, verifies it through
the runner, reproduces all ten stages, and executes this test suite. Generated
data and model binaries remain temporary workflow artifacts and are not
committed.

## Verified headline results

The current executed artifacts report:

- **Data:** 1,067,371 raw rows; 1,055,238 rows after exact deduplication;
  793,609 valid known-customer sales rows; 5,878 purchasing customers.
- **RFM:** 10 interpretable segments and 324 high-value customers flagged as at
  risk.
- **ML segmentation:** 4 customer clusters.
- **Churn:** 90-day Random Forest temporal test ROC-AUC `0.7569`, PR-AUC
  `0.6306`, Brier score `0.1938`, and selected classification threshold `0.31`.
- **BG/NBD validation:** 4,937 holdout customers; MAE `1.078`; RMSE `1.843`;
  8,111 actual versus 7,960.962 predicted purchases; aggregate error `-1.85%`.
- **Gamma-Gamma:** frequency/monetary correlation `0.0233`; 4,189 eligible
  repeat customers.
- **Predictive CLV:** total expected 12-month revenue CLV `9,556,553.97`, median
  `574.08`; tiers use the observed p50, p80, and p95 cutoffs.
- **Retention scenario:** 3,477 customers inside current churn-model support;
  770 positive candidates; 708 funded targets; `4,515.00` campaign spend;
  `7,474.49` scenario expected net benefit. Automated nurture capacity is the
  binding constraint.

Retention totals depend on the configurable assumptions in
`reports/retention_assumptions.json`; they are not measured campaign impact.

## Interpretation and limitations

- The source covers one UK-based retailer in 2009–2011. Results should not be
  treated as current market benchmarks or assumed to generalize unchanged.
- Missing customer IDs prevent customer-level analysis. Anonymous valid sales
  remain in general sales reporting but are excluded from RFM, churn, and CLV.
- Customer sales and revenue use positive, non-cancelled transactions. Returns
  and cancellations are retained separately for auditing and behavioral
  features.
- The churn target is **no purchase during the next 90 days**, not account
  cancellation. The current model is supported only for customers who purchased
  during the previous 180 days; long-lapsed customers receive no invented churn
  probability.
- `churn_test_predictions.csv` is a historical September 2011 evaluation
  artifact. Current retention decisions use the label-free score snapshot dated
  2011-12-10.
- BG/NBD and Gamma-Gamma rely on repeat-purchase and monetary assumptions. The
  current CLV is expected **future revenue**, not historical revenue or profit,
  and uses a zero monthly discount rate.
- ML clusters and RFM segments are descriptive context, not causal treatment
  rules.
- The retention engine multiplies 90-day churn probability and 12-month CLV as
  an explicitly labeled risk-value planning proxy. Assumed recoverable shares
  are scenario inputs, not estimated causal uplift.
- The campaign shortlist is not activation-ready. Consent, contactability,
  suppression, channel eligibility, offer eligibility, prior-contact limits,
  and a randomized holdout must be applied before launch.

## Ignored artifacts and rebuilding

Raw data, generated Parquet files, and trained models are intentionally ignored
by Git:

```text
data/raw/*
data/interim/*
data/processed/*
models/*
```

Therefore a fresh clone does **not** contain the UCI archive, generated data, or
the fitted Random Forest. To rebuild them:

1. create the pinned environment;
2. download and verify the archive at the expected path; and
3. run `python run_pipeline.py` from the repository root.

Notebook 05 recreates the ignored churn model. Notebook 06 refits BG/NBD and
Gamma-Gamma and saves customer predictions and fitted MAP parameters, but it
does not persist those PyMC-Marketing model objects. Reports and figures are
derived artifacts and can be regenerated by the same pipeline.

## License and attribution

The source dataset is licensed separately under CC BY 4.0 and must retain the
UCI/Chen attribution above. Project code and documentation do not override the
dataset's license terms.
