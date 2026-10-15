"""
Update customer C002 city Denver → Portland  (triggers SCD-2 in dim_customer)
Update product P001 unit_cost 22.50 → 44.99  (triggers SCD-1 overwrite in dim_product)

Run AFTER generate_sample_data.py and a first pipeline run:
    python scripts/generate_sample_data.py
    python -m src.pipeline --date 2025-11-10 --backfill 3
    python scripts/generate_sample_data_v2.py
    python -m src.pipeline --date 2025-11-11

Then verify:
    - dim_customer has TWO rows for CUST-002 (Denver closed, Portland current)
    - dim_product P001 unit_cost == 44.99
"""
from __future__ import annotations
import csv
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent.parent
CUSTOMER_DIR = ROOT / "data" / "landing" / "customers"
ORDERS_DIR   = ROOT / "data" / "landing" / "orders"
DB_PATH      = ROOT / "data" / "landing" / "products.db"


# ── Add orders for 2025-11-11 so the pipeline has something to process ────────

order_path = ORDERS_DIR / "orders_2025-11-11.csv"
with order_path.open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["order_id","customer_id","product_id","order_date","quantity","unit_price","status"])
    w.writerow(["ORD-015","CUST-001","PROD-001","2025-11-11","1","44.99","shipped"])
    w.writerow(["ORD-016","CUST-002","PROD-002","2025-11-11","2","199.00","pending"])
print(f"  wrote {order_path}")


# ── Update customers.json: C002 moves Denver → Portland ─────────────────────

cust_path = CUSTOMER_DIR / "customers.json"
customers = json.loads(cust_path.read_text())

for rec in customers:
    if rec["customer_id"] == "CUST-002":
        rec["address"]["city"] = "Portland"
        rec["address"]["country"] = "US"
        break

cust_path.write_text(json.dumps(customers, indent=2))
print(f"  updated {cust_path}: CUST-002 city → Portland")


# ── Update products.db: P001 unit_cost 22.50 → 44.99 ────────────────────────

conn = sqlite3.connect(DB_PATH)
conn.execute(
    "UPDATE products SET unit_cost = 44.99, updated_at = '2025-11-11T08:00:00' "
    "WHERE product_id = 'PROD-001'"
)
conn.commit()
conn.close()
print(f"  updated {DB_PATH}: PROD-001 unit_cost → 44.99")

print()
print("v2 data ready. Now run:")
print("  python -m src.pipeline --date 2025-11-11")
print()
print("Then verify SCD-2:")
print("  python -c \""
      "import pandas as pd; "
      "df = pd.read_parquet('data/gold/dim_customer.parquet'); "
      "print(df[df.customer_id=='CUST-002'][['customer_id','city','_eff_start','_eff_end','_current']])"
      "\"")
print()
print("Then verify SCD-1:")
print("  python -c \""
      "import pandas as pd; "
      "df = pd.read_parquet('data/gold/dim_product.parquet'); "
      "print(df[df.product_id=='PROD-001'][['product_id','name','unit_cost']])"
      "\"")
