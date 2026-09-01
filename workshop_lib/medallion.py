"""Step 1 (part 2): bronze -> silver -> gold medallion build.

* silver: parse string dates, standardize inconsistent casing, dedupe, conform types.
* gold  : model the clean star schema (dims + facts) and apply rich table/column
          COMMENTs. The gold layer is what the Genie space is built on in Step 2.

Code columns (state_code, country_code, payment_method, status, currency) are
kept AS CODES on purpose — they are the raw material for the Step 3 value-matching
lesson (e.g. users ask "California", the data stores 'CA').
"""

from __future__ import annotations

from pyspark.sql import SparkSession, functions as F

# --------------------------------------------------------------------------- #
# Canonical value maps (used to standardize messy bronze casing)
# --------------------------------------------------------------------------- #
_SEGMENT_MAP = {"SMB": "SMB", "CONSUMER": "Consumer", "CORPORATE": "Corporate"}
_CARRIER_MAP = {"USPS": "USPS", "FEDEX": "FedEx", "UPS": "UPS", "DHL": "DHL"}


def _canonical(col, mapping: dict):
    """Build a CASE expression mapping upper(col) -> canonical value."""
    expr = F
    c = F.upper(F.trim(col))
    result = None
    for raw, canon in mapping.items():
        cond = c == raw
        result = F.when(cond, F.lit(canon)) if result is None else result.when(cond, F.lit(canon))
    return result.otherwise(col)


# --------------------------------------------------------------------------- #
# SILVER
# --------------------------------------------------------------------------- #
def build_silver(spark: SparkSession, cfg) -> dict:
    """Clean & conform bronze -> silver. Returns {table_name: row_count}."""
    written = {}

    # customers: parse dates, standardize segment casing, keep NULL emails visible.
    df = spark.table(cfg.bronze("customers"))
    df = (
        df.withColumn("segment", _canonical(F.col("segment"), _SEGMENT_MAP))
        .withColumn("signup_date", F.to_date("signup_date"))
        .withColumn("birth_date", F.to_date("birth_date"))
        .dropDuplicates(["customer_id"])
    )
    written[cfg.silver("customers")] = _write(df, cfg.silver("customers"))

    # products: already clean; ensure types.
    df = spark.table(cfg.bronze("products"))
    written[cfg.silver("products")] = _write(df, cfg.silver("products"))

    # geography: already clean.
    df = spark.table(cfg.bronze("geography"))
    written[cfg.silver("geography")] = _write(df, cfg.silver("geography"))

    # orders: parse date, dedupe on order_line_id.
    df = spark.table(cfg.bronze("orders"))
    df = df.withColumn("order_date", F.to_date("order_date")).dropDuplicates(["order_line_id"])
    written[cfg.silver("orders")] = _write(df, cfg.silver("orders"))

    # transactions: parse date.
    df = spark.table(cfg.bronze("transactions"))
    df = df.withColumn("txn_date", F.to_date("txn_date")).dropDuplicates(["transaction_id"])
    written[cfg.silver("transactions")] = _write(df, cfg.silver("transactions"))

    # shipments: parse dates, standardize carrier casing.
    df = spark.table(cfg.bronze("shipments"))
    df = (
        df.withColumn("carrier", _canonical(F.col("carrier"), _CARRIER_MAP))
        .withColumn("ship_date", F.to_date("ship_date"))
        .withColumn("delivery_date", F.to_date("delivery_date"))
        .dropDuplicates(["shipment_id"])
    )
    written[cfg.silver("shipments")] = _write(df, cfg.silver("shipments"))

    return written


# --------------------------------------------------------------------------- #
# GOLD (star schema + comments)
# --------------------------------------------------------------------------- #
def build_gold(spark: SparkSession, cfg) -> dict:
    """Model the gold star schema from silver and apply comments."""
    written = {}

    written[cfg.gold("dim_customers")] = _write(
        spark.table(cfg.silver("customers")), cfg.gold("dim_customers")
    )
    written[cfg.gold("dim_products")] = _write(
        spark.table(cfg.silver("products")), cfg.gold("dim_products")
    )
    written[cfg.gold("dim_geography")] = _write(
        spark.table(cfg.silver("geography")), cfg.gold("dim_geography")
    )
    written[cfg.gold("fact_orders")] = _write(
        spark.table(cfg.silver("orders")), cfg.gold("fact_orders")
    )
    written[cfg.gold("fact_transactions")] = _write(
        spark.table(cfg.silver("transactions")), cfg.gold("fact_transactions")
    )
    written[cfg.gold("fact_shipments")] = _write(
        spark.table(cfg.silver("shipments")), cfg.gold("fact_shipments")
    )

    apply_gold_comments(spark, cfg)
    return written


def apply_gold_comments(spark: SparkSession, cfg) -> None:
    """Add rich table + column COMMENTs to every gold table (Genie reads these)."""
    for short_name, (table_comment, col_comments) in _GOLD_COMMENTS.items():
        fqn = cfg.gold(short_name)
        spark.sql(f"COMMENT ON TABLE {fqn} IS '{_esc(table_comment)}'")
        for col, comment in col_comments.items():
            spark.sql(
                f"ALTER TABLE {fqn} ALTER COLUMN {col} COMMENT '{_esc(comment)}'"
            )


# --------------------------------------------------------------------------- #
# Comment metadata — deliberately rich (this lifts the Step 2 Genie baseline)
# --------------------------------------------------------------------------- #
_GOLD_COMMENTS: dict[str, tuple[str, dict[str, str]]] = {
    "dim_customers": (
        "Customer dimension. One row per customer, keyed by customer_id.",
        {
            "customer_id": "Unique customer identifier (format C####).",
            "customer_name": "Customer full name.",
            "email": "Customer email address. May be NULL when not captured at signup.",
            "segment": "Customer segment: SMB, Consumer, or Corporate.",
            "signup_date": "Date the customer created their account.",
            "loyalty_points": "Current loyalty points balance (integer).",
            "birth_date": "Customer date of birth.",
            "is_internal": "TRUE for internal / test accounts that should normally be excluded from business reporting.",
        },
    ),
    "dim_products": (
        "Product dimension. One row per product, keyed by product_id. All products are Electronics.",
        {
            "product_id": "Unique product identifier (format P##).",
            "product_name": "Product display name.",
            "category": "Top-level product category (Electronics).",
            "subcategory": "Product subcategory: Audio, Wearables, Computing, Mobile Accessories, Smart Home, or Gaming.",
            "list_price": "Retail list price per unit, in the order currency.",
            "standard_cost": "Standard unit cost of goods (used for margin calculations).",
        },
    ),
    "dim_geography": (
        "Geography dimension covering US states and Canadian provinces. Keyed by geo_id.",
        {
            "geo_id": "Unique geography identifier (format G##).",
            "state_code": "State or province code.",
            "region_name": "Sales region grouping (e.g. West, Northeast, Western Canada).",
            "country_code": "Two-letter country code: US=United States, CA=Canada.",
            "country_name": "Full country name.",
        },
    ),
    "fact_orders": (
        "Order line-item fact. Grain = one row per product line within an order. "
        "Join to dim_customers, dim_products and dim_geography on their id keys.",
        {
            "order_id": "Order identifier (format O#####). Repeats across multiple line items.",
            "order_line_id": "Unique order line identifier (format L######). Primary key of this table.",
            "customer_id": "Foreign key to dim_customers.customer_id.",
            "product_id": "Foreign key to dim_products.product_id.",
            "geo_id": "Foreign key to dim_geography.geo_id.",
            "order_date": "Date the order was placed.",
            "order_channel": "Sales channel: Mobile, Web, Store, or Partner.",
            "quantity": "Units ordered on this line.",
            "discount_pct": "Discount applied to this line, as a fraction (0.0 to 0.25).",
            "net_amount": "Net revenue for this line after discount, in the order currency.",
            "cogs_amount": "Cost of goods sold for this line.",
        },
    ),
    "fact_transactions": (
        "Payment transaction fact. Grain = one payment per order. "
        "status indicates whether revenue was actually collected.",
        {
            "transaction_id": "Unique transaction identifier (format T#####).",
            "order_id": "Foreign key to the order (fact_orders.order_id).",
            "customer_id": "Foreign key to dim_customers.customer_id.",
            "payment_method": "Internal payment gateway code.",
            "txn_date": "Date the payment was attempted.",
            "amount": "Transaction amount (sum of order net_amount), in the transaction currency.",
            "status": "Transaction status code (values include COMPLETED, REFUNDED, FAILED, PENDING).",
            "currency": "ISO currency code for the transaction amount.",
        },
    ),
    "fact_shipments": (
        "Shipment fact. Grain = one shipment per shipped order. "
        "Some orders are never shipped and have no row here.",
        {
            "shipment_id": "Unique shipment identifier (format S#####).",
            "order_id": "Foreign key to the order (fact_orders.order_id).",
            "geo_id": "Foreign key to dim_geography.geo_id (ship-to geography).",
            "carrier": "Shipping carrier: USPS, FedEx, UPS, or DHL.",
            "ship_date": "Date the shipment left the warehouse.",
            "delivery_date": "Date the shipment was delivered.",
            "shipping_cost": "Shipping cost charged for this shipment.",
            "delivery_days": "Number of days between ship_date and delivery_date.",
            "on_time_flag": "TRUE when the shipment was delivered within the on-time threshold (6 days).",
        },
    ),
}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _write(df, fqn: str) -> int:
    df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(fqn)
    return df.count()


def _esc(text: str) -> str:
    """Escape single quotes for a Spark SQL string literal."""
    return text.replace("'", "''")
