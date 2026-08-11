# Online Retail II — Data Quality Report

## Dataset overview

- Rows: 1,067,371
- Columns: 9
- DataFrame memory usage: 138.67 MB
- Minimum invoice date: 2009-12-01 07:45:00
- Maximum invoice date: 2011-12-09 12:50:00

## Business entities

- Unique invoices: 53,628
- Unique products: 5,305
- Unique customers: 5,942
- Unique countries: 43

## Missing values

| Column | Missing rows | Missing percentage |
|---|---:|---:|
| invoice | 0 | 0.0000% |
| stock_code | 0 | 0.0000% |
| description | 4,382 | 0.4105% |
| quantity | 0 | 0.0000% |
| invoice_date | 0 | 0.0000% |
| unit_price | 0 | 0.0000% |
| customer_id | 243,007 | 22.7669% |
| country | 0 | 0.0000% |
| source_period | 0 | 0.0000% |

## Duplicate rows

- Exact duplicate rows: 12,133
- Exact duplicate percentage: 1.1367%

## Transaction-quality indicators

- Cancelled rows: 19,494
- Cancelled percentage: 1.8264%
- Negative quantity rows: 22,950
- Zero quantity rows: 0
- Negative price rows: 5
- Zero price rows: 6,202
- Cancelled invoices with positive quantities: 1
- Negative quantities without cancellation code: 3,457

## Rows by source period

| Source period | Rows |
|---|---:|
| 2010-2011 | 541,910 |
| 2009-2010 | 525,461 |

## Top countries by transaction rows

| Country | Rows |
|---|---:|
| United Kingdom | 981,330 |
| EIRE | 17,866 |
| Germany | 17,624 |
| France | 14,330 |
| Netherlands | 5,140 |
| Spain | 3,811 |
| Switzerland | 3,189 |
| Belgium | 3,123 |
| Portugal | 2,620 |
| Australia | 1,913 |
| Channel Islands | 1,664 |
| Italy | 1,534 |
| Norway | 1,455 |
| Sweden | 1,364 |
| Cyprus | 1,176 |

## Initial interpretation

- Missing customer IDs require separate treatment because customer-level segmentation, churn prediction, and CLV cannot be performed without a customer identifier.
- Cancelled invoices and negative quantities should not be removed blindly. They provide useful information about returns, cancellations, and customer behavior.
- Exact duplicates must be investigated before removal to determine whether they are accidental duplicates or valid repeated invoice lines.
- Zero or negative prices require investigation before revenue and customer-value calculations.
