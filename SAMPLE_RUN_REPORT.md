# Sample Run Report — NovaCart ETL Pipeline

Captured on a clean checkout. All generated output (bronze/silver/gold/quarantine/state/logs)
was deleted before this run via `python scripts/cleanup.py`.

---

## Environment

| Item | Value |
|------|-------|
| Platform | macOS (darwin 25.5.0, arm64) |
| Python | 3.9.6 |
| Key dependencies | pandas 2.2.3, pydantic 2.13.0, pyarrow 20.0.0, pyyaml 6.0.2, pytest 8.4.2 |

---

## Step 1 — Generate Sample Data

```
python scripts/generate_sample_data.py
```

```
wrote data/landing/orders/orders_2025-11-07.csv
wrote data/landing/orders/orders_2025-11-08.csv
wrote data/landing/orders/orders_2025-11-09.csv
wrote data/landing/orders/orders_2025-11-10.csv
wrote data/landing/customers/customers.json
wrote data/landing/products.db (4 products)

Sample data generation complete.
Next: python -m src.pipeline --date 2025-11-10 --backfill 3
```

---

## Step 2 — Run Pipeline (4-date backfill)

```
python -m src.pipeline --date 2025-11-10 --backfill 3
```

```
[OK]   2025-11-07: 0.07s
[OK]   2025-11-08: 0.04s
[OK]   2025-11-09: 0.04s
[OK]   2025-11-10: 0.04s
```

### Key log events (selected from logs/pipeline.jsonl)

**2025-11-07** — 5 orders in, 1 quarantined (qty=0), 1 deduped → 3 to Silver; 6 customers in, 2 quarantined (bad email) → 4 to Silver; 4 products loaded (first run, watermark from epoch):
```json
{"event": "orders_quarantined",      "rows_in": 5, "rows_quarantined": 1, "run_id": "547f8284b335"}
{"event": "orders_deduped",          "dropped": 1,                         "run_id": "547f8284b335"}
{"event": "silver_orders_written",   "rows_in": 5, "rows_out": 3, "rows_quarantined": 1, "run_id": "547f8284b335"}
{"event": "customers_quarantined",   "rows_in": 6, "rows_quarantined": 2,  "run_id": "547f8284b335"}
{"event": "silver_customers_written","rows_in": 6, "rows_out": 4, "rows_quarantined": 2, "run_id": "547f8284b335"}
{"event": "products_watermark_advanced", "new_watermark": "2025-11-05T11:15:00"}
{"event": "dim_customer_initial_load","rows": 4}
{"event": "dim_date_written",         "rows": 4018, "start": "2020-01-01", "end": "2030-12-31"}
```

**2025-11-09** — 3 bad orders quarantined (qty=0, invalid status, negative price):
```json
{"event": "orders_quarantined", "rows_in": 5, "rows_quarantined": 3, "run_id": "69f3bb2400cc"}
{"event": "silver_orders_written", "rows_in": 5, "rows_out": 2, "rows_quarantined": 3, "run_id": "69f3bb2400cc"}
```

---

## Step 3 — Output Verification

### Bronze layer (all-string, metadata columns present)

```
data/bronze/orders/date=2025-11-07/data.parquet   — 5 rows, dtype=object for all business cols
data/bronze/orders/date=2025-11-08/data.parquet   — 3 rows
data/bronze/orders/date=2025-11-09/data.parquet   — 5 rows
data/bronze/orders/date=2025-11-10/data.parquet   — 2 rows
data/bronze/customers/data.parquet                — 6 rows
data/bronze/products/data.parquet                 — 4 rows
Metadata columns present: _source_file, _ingested_at, _row_hash
```

### Quarantine (bad rows isolated with _error_reason)

```
data/quarantine/orders/dt=2025-11-07/orders_bad.parquet    — 1 row  (qty=0)
data/quarantine/orders/dt=2025-11-08/orders_bad.parquet    — 1 row  (status=refunded)
data/quarantine/orders/dt=2025-11-09/orders_bad.parquet    — 3 rows (qty=0, status=refunded, price=-5)
data/quarantine/customers/dt=2025-11-07/customers_bad.parquet — 2 rows (bad email)
```

### Silver layer (typed, deduplicated)

```
data/silver/orders/date=2025-11-07/data.parquet   — 3 rows (1 bad quarantined, 1 deduped)
data/silver/orders/date=2025-11-08/data.parquet   — 2 rows
data/silver/orders/date=2025-11-09/data.parquet   — 2 rows
data/silver/orders/date=2025-11-10/data.parquet   — 2 rows
data/silver/customers/data.parquet                — 4 rows
data/silver/products/data.parquet                 — 4 rows
```

### Gold layer (star schema)

```
data/gold/dim_customer.parquet   — 4 rows  (SCD-2: _eff_start, _eff_end, _current columns)
data/gold/dim_product.parquet    — 4 rows  (SCD-1: latest snapshot)
data/gold/dim_date.parquet       — 4,018 rows  (2020-01-01 → 2030-12-31)
data/gold/fact_orders/date=2025-11-07/data.parquet — 3 rows (includes date_key FK, total_amount)
data/gold/fact_orders/date=2025-11-08/data.parquet — 2 rows
data/gold/fact_orders/date=2025-11-09/data.parquet — 2 rows
data/gold/fact_orders/date=2025-11-10/data.parquet — 2 rows
```

### State & watermark

```
state/watermarks.json      — {"products_updated_at": "2025-11-05T11:15:00"}
state/run_history.jsonl    — 4 run records, all status=SUCCESS
```

---

## Step 4 — SCD Demo (run generate_sample_data_v2.py then pipeline for 2025-11-11)

```
python scripts/generate_sample_data_v2.py
python -m src.pipeline --date 2025-11-11
```

**SCD-2 result** — CUST-002 has TWO rows in dim_customer:

| customer_id | city     | _eff_start | _eff_end   | _current |
|-------------|----------|------------|------------|----------|
| CUST-002    | Denver   | 2026-10-15 | 2026-10-15 | False    |
| CUST-002    | Portland | 2026-10-15 | 9999-12-31 | True     |

**SCD-1 result** — PROD-001 unit_cost overwritten to 44.99:

| product_id | name                | unit_cost |
|------------|---------------------|-----------|
| PROD-001   | Wireless Headphones | 44.99     |

---

## Step 5 — Tests

```
pytest -v
```

```
tests/test_pipeline_scenarios.py::test_happy_path_fact_rows PASSED
tests/test_pipeline_scenarios.py::test_happy_path_total_amount_calculated PASSED
tests/test_pipeline_scenarios.py::test_duplicates_collapsed PASSED
tests/test_pipeline_scenarios.py::test_duplicates_keep_last_value PASSED
tests/test_pipeline_scenarios.py::test_bad_rows_quarantined PASSED
tests/test_pipeline_scenarios.py::test_bad_rows_dont_reach_gold PASSED
tests/test_pipeline_scenarios.py::test_additive_drift_succeeds PASSED
tests/test_pipeline_scenarios.py::test_additive_drift_data_still_lands PASSED
tests/test_pipeline_scenarios.py::test_subtractive_drift_fails PASSED
tests/test_pipeline_scenarios.py::test_subtractive_drift_error_message PASSED
tests/test_pipeline_scenarios.py::test_idempotency_same_row_count PASSED
tests/test_pipeline_scenarios.py::test_idempotency_same_values PASSED
tests/test_pipeline_scenarios.py::test_backfill_all_dates_present PASSED
tests/test_pipeline_scenarios.py::test_backfill_equals_individual_runs PASSED
tests/test_schemas.py::TestOrderRow::test_valid_order PASSED
tests/test_schemas.py::TestOrderRow::test_status_normalised_to_lowercase PASSED
tests/test_schemas.py::TestOrderRow::test_zero_quantity_rejected PASSED
tests/test_schemas.py::TestOrderRow::test_negative_quantity_rejected PASSED
tests/test_schemas.py::TestOrderRow::test_negative_price_rejected PASSED
tests/test_schemas.py::TestOrderRow::test_invalid_status_rejected PASSED
tests/test_schemas.py::TestCustomerRow::test_valid_customer PASSED
tests/test_schemas.py::TestCustomerRow::test_email_normalised_to_lowercase PASSED
tests/test_schemas.py::TestCustomerRow::test_bad_email_rejected PASSED
tests/test_schemas.py::TestCustomerRow::test_tier_defaults_to_standard PASSED
tests/test_schemas.py::TestProductRow::test_valid_product PASSED
tests/test_schemas.py::TestProductRow::test_negative_cost_rejected PASSED
tests/test_schemas.py::TestProductRow::test_zero_cost_allowed PASSED

============================== 27 passed in 0.89s ==============================
```
