"""Bronze → Silver: validate with Pydantic, dedupe, quarantine bad rows."""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Type

import pandas as pd
from pydantic import BaseModel, ValidationError

from src.utils.logging_setup import log_event
from src.utils.schemas import OrderRow, CustomerRow, ProductRow


def _validate_df(
    df: pd.DataFrame,
    model: Type[BaseModel],
    primary_key: str,
    quarantine_path: Path,
    logger: logging.Logger,
    source_name: str,
    date_str: str = "unknown",
) -> pd.DataFrame:
    """Validate each row with Pydantic. Good rows → Silver (typed), bad rows → quarantine."""
    good, bad = [], []
    meta_cols = [c for c in df.columns if c.startswith("_")]
    for _, row in df.iterrows():
        row_dict = row.to_dict()
        try:
            validated = model(**row_dict)
            # Use pydantic-coerced values so Silver has correct types, not raw strings
            typed = validated.model_dump()
            # Re-attach Bronze metadata columns unchanged
            for col in meta_cols:
                typed[col] = row_dict[col]
            good.append(typed)
        except (ValidationError, Exception) as exc:
            row_dict["_error_reason"] = str(exc)
            row_dict["_quarantined_at"] = datetime.now(timezone.utc).isoformat()
            bad.append(row_dict)

    rows_in = len(df)
    rows_quarantined = len(bad)

    if bad:
        q_dir = quarantine_path / source_name / f"dt={date_str}"
        q_dir.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(bad).to_parquet(q_dir / f"{source_name}_bad.parquet", index=False)
        log_event(logger, "WARNING", f"{source_name}_quarantined",
                  rows_in=rows_in, rows_quarantined=rows_quarantined)

    result = pd.DataFrame(good) if good else pd.DataFrame(columns=list(df.columns))

    # Deduplicate on primary key — keep last occurrence
    if primary_key in result.columns and not result.empty:
        before = len(result)
        result = result.drop_duplicates(subset=[primary_key], keep="last")
        dupes = before - len(result)
        if dupes:
            log_event(logger, "INFO", f"{source_name}_deduped", dropped=dupes)

    rows_out = len(result)
    return result.reset_index(drop=True), rows_in, rows_out, rows_quarantined


def build_silver_orders(
    date_str: str,
    bronze_dir: Path,
    silver_dir: Path,
    quarantine_dir: Path,
    logger: logging.Logger,
) -> Path:
    src = bronze_dir / "orders" / f"date={date_str}" / "data.parquet"
    if not src.exists():
        log_event(logger, "WARNING", "silver_orders_no_bronze", date=date_str)
        return silver_dir / "orders" / f"date={date_str}" / "data.parquet"

    df = pd.read_parquet(src)
    df, rows_in, rows_out, rows_q = _validate_df(
        df, OrderRow, "order_id", quarantine_dir, logger, "orders", date_str
    )

    out_dir = silver_dir / "orders" / f"date={date_str}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "data.parquet"
    df.to_parquet(out_path, index=False)
    log_event(logger, "INFO", "silver_orders_written",
              date=date_str, rows_in=rows_in, rows_out=rows_out, rows_quarantined=rows_q)
    return out_path


def build_silver_customers(
    date_str: str,
    bronze_dir: Path,
    silver_dir: Path,
    quarantine_dir: Path,
    logger: logging.Logger,
) -> Path:
    src = bronze_dir / "customers" / "data.parquet"
    if not src.exists():
        log_event(logger, "WARNING", "silver_customers_no_bronze")
        return silver_dir / "customers" / "data.parquet"

    df = pd.read_parquet(src)
    df, rows_in, rows_out, rows_q = _validate_df(
        df, CustomerRow, "customer_id", quarantine_dir, logger, "customers", date_str
    )

    out_dir = silver_dir / "customers"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "data.parquet"
    df.to_parquet(out_path, index=False)
    log_event(logger, "INFO", "silver_customers_written",
              rows_in=rows_in, rows_out=rows_out, rows_quarantined=rows_q)
    return out_path


def build_silver_products(
    bronze_dir: Path,
    silver_dir: Path,
    quarantine_dir: Path,
    logger: logging.Logger,
) -> Path:
    src = bronze_dir / "products" / "data.parquet"
    if not src.exists():
        log_event(logger, "WARNING", "silver_products_no_bronze")
        return silver_dir / "products" / "data.parquet"

    df = pd.read_parquet(src)
    if df.empty:
        return silver_dir / "products" / "data.parquet"

    df, rows_in, rows_out, rows_q = _validate_df(
        df, ProductRow, "product_id", quarantine_dir, logger, "products", "snapshot"
    )

    out_dir = silver_dir / "products"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "data.parquet"
    df.to_parquet(out_path, index=False)
    log_event(logger, "INFO", "silver_products_written",
              rows_in=rows_in, rows_out=rows_out, rows_quarantined=rows_q)
    return out_path
