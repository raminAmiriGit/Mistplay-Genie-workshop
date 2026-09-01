"""Step 1 (part 1): synthetic RAW data generation → bronze landing tables.

Domain: e-commerce orders / transactions / shipments across customers, products
and geographies (US states + Canadian provinces). Modeled on the shape of
`ramin_serverless_aws_catalog.metric_view_workshop`, enriched with a
``fact_transactions`` (payments) table, state/province granularity, and an
``is_internal`` customer flag so later Genie steps have something to teach.

Bronze tables are deliberately "raw": dates as strings, inconsistent casing,
a few NULLs, and some duplicate rows — the silver step cleans all of it.

Everything is reproducible via a fixed ``seed``.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

# --------------------------------------------------------------------------- #
# Reference / categorical values
# --------------------------------------------------------------------------- #
SEGMENTS = ["SMB", "Consumer", "Corporate"]
CHANNELS = ["Mobile", "Web", "Store", "Partner"]
CARRIERS = ["USPS", "FedEx", "UPS", "DHL"]
# Payment methods & statuses are stored as CODES on purpose (Step 3 value matching).
# Opaque internal payment-gateway codes (PM01=Credit Card, PM02=PayPal,
# PM03=Gift Card, PM04=Debit Card). Deliberately NOT self-describing — decoding
# them is the Step 3 value-matching lesson.
PAYMENT_METHODS = ["PM01", "PM02", "PM03", "PM04"]
TXN_STATUSES = ["COMPLETED", "REFUNDED", "FAILED", "PENDING"]

# geo_id, state_code, region_name, country_code, country_name
# NOTE: no full state_name column on purpose — "California" -> 'CA' must be taught
# via value matching in Step 3, not read from a lookup column.
GEOGRAPHIES = [
    ("G01", "CA", "West", "US", "United States"),
    ("G02", "NY", "Northeast", "US", "United States"),
    ("G03", "TX", "South", "US", "United States"),
    ("G04", "IL", "Midwest", "US", "United States"),
    ("G05", "WA", "West", "US", "United States"),
    ("G06", "FL", "Southeast", "US", "United States"),
    ("G07", "MA", "Northeast", "US", "United States"),
    ("G08", "ON", "Central Canada", "CA", "Canada"),
    ("G09", "QC", "Central Canada", "CA", "Canada"),
    ("G10", "BC", "Western Canada", "CA", "Canada"),
    ("G11", "AB", "Prairies", "CA", "Canada"),
]

# product_name, subcategory, list_price, standard_cost
PRODUCT_CATALOG = [
    ("Wireless Headphones", "Audio", 129.99, 62.00),
    ("Bluetooth Speaker", "Audio", 79.99, 33.00),
    ("Noise-Cancelling Earbuds", "Audio", 149.99, 70.00),
    ("Studio Microphone", "Audio", 119.99, 55.00),
    ("Soundbar", "Audio", 199.99, 96.00),
    ("Smartwatch", "Wearables", 199.99, 88.00),
    ("Fitness Tracker", "Wearables", 89.99, 38.00),
    ("Smart Ring", "Wearables", 149.99, 61.00),
    ("VR Headset", "Wearables", 179.99, 90.00),
    ("Laptop Stand", "Computing", 49.99, 18.00),
    ("Mechanical Keyboard", "Computing", 109.99, 44.00),
    ("Wireless Mouse", "Computing", 39.99, 14.00),
    ("USB-C Hub", "Computing", 59.99, 22.00),
    ("External SSD 1TB", "Computing", 139.99, 68.00),
    ("Webcam 1080p", "Computing", 69.99, 28.00),
    ("Phone Case", "Mobile Accessories", 24.99, 6.00),
    ("Fast Charger", "Mobile Accessories", 34.99, 11.00),
    ("Power Bank", "Mobile Accessories", 44.99, 17.00),
    ("Screen Protector", "Mobile Accessories", 14.99, 3.00),
    ("Car Mount", "Mobile Accessories", 29.99, 9.00),
    ("Smart Bulb", "Smart Home", 29.99, 10.00),
    ("Smart Plug", "Smart Home", 24.99, 8.00),
    ("Video Doorbell", "Smart Home", 159.99, 74.00),
    ("Smart Thermostat", "Smart Home", 179.99, 82.00),
    ("Indoor Camera", "Smart Home", 89.99, 39.00),
    ("Game Controller", "Gaming", 64.99, 26.00),
    ("Gaming Headset", "Gaming", 99.99, 42.00),
    ("Streaming Mic", "Gaming", 89.99, 37.00),
    ("Capture Card", "Gaming", 149.99, 72.00),
    ("RGB Mousepad", "Gaming", 34.99, 12.00),
]

_FIRST_NAMES = [
    "Ivy", "Mason", "Ava", "Liam", "Noah", "Emma", "Olivia", "Ethan", "Sophia",
    "Lucas", "Mia", "Aiden", "Isla", "Leo", "Zoe", "Kai", "Nora", "Owen",
    "Maya", "Ezra", "Priya", "Arjun", "Wei", "Yuki", "Omar", "Fatima", "Diego",
    "Chloe", "Hana", "Sam",
]
_LAST_NAMES = [
    "Patel", "Costa", "Nguyen", "Smith", "Kim", "Garcia", "Rossi", "Khan",
    "Chen", "Dubois", "Silva", "Brown", "Wang", "Lopez", "Muller", "Ivanov",
    "Tanaka", "Okoye", "Haddad", "Singh",
]
_EMAIL_DOMAINS = ["globex.com", "initech.com", "umbrella.co", "hooli.com", "acme.io"]
_INTERNAL_DOMAINS = ["mistplay-test.com", "databricks.com"]


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def generate_raw(spark, cfg, seed: int = 42) -> dict:
    """Generate all bronze (raw landing) tables. Returns {table_name: row_count}."""
    rng = random.Random(seed)
    cfg.ensure_schema(spark)

    customers = _gen_customers(rng, n=200)
    products = _gen_products()
    geos = list(GEOGRAPHIES)
    orders = _gen_orders(rng, customers, products, geos, n_orders=1500)
    transactions = _gen_transactions(rng, orders, customers)
    shipments = _gen_shipments(rng, orders, geos)

    written = {}
    written[cfg.bronze("customers")] = _write_bronze_customers(spark, cfg, rng, customers)
    written[cfg.bronze("products")] = _write_bronze_products(spark, cfg, products)
    written[cfg.bronze("geography")] = _write_bronze_geography(spark, cfg, geos)
    written[cfg.bronze("orders")] = _write_bronze_orders(spark, cfg, rng, orders)
    written[cfg.bronze("transactions")] = _write_bronze_transactions(spark, cfg, rng, transactions)
    written[cfg.bronze("shipments")] = _write_bronze_shipments(spark, cfg, rng, shipments)
    return written


# --------------------------------------------------------------------------- #
# Record generators (clean Python dicts; messiness is injected at write time)
# --------------------------------------------------------------------------- #
def _gen_customers(rng: random.Random, n: int) -> list[dict]:
    rows = []
    n_internal = max(5, n // 25)  # ~4% internal/test accounts
    internal_idx = set(rng.sample(range(n), n_internal))
    for i in range(n):
        cid = f"C{i + 1:04d}"
        first = rng.choice(_FIRST_NAMES)
        last = rng.choice(_LAST_NAMES)
        is_internal = i in internal_idx
        domain = rng.choice(_INTERNAL_DOMAINS if is_internal else _EMAIL_DOMAINS)
        rows.append(
            {
                "customer_id": cid,
                "customer_name": f"{first} {last}",
                "email": f"{first.lower()}.{last.lower()}@{domain}",
                "segment": rng.choice(SEGMENTS),
                "signup_date": _rand_date(rng, date(2023, 1, 1), date(2024, 12, 31)),
                "loyalty_points": rng.randint(0, 5000),
                "birth_date": _rand_date(rng, date(1965, 1, 1), date(2003, 12, 31)),
                "is_internal": is_internal,
            }
        )
    return rows


def _gen_products() -> list[dict]:
    rows = []
    for i, (name, subcat, price, cost) in enumerate(PRODUCT_CATALOG, start=1):
        rows.append(
            {
                "product_id": f"P{i:02d}",
                "product_name": name,
                "category": "Electronics",
                "subcategory": subcat,
                "list_price": price,
                "standard_cost": cost,
            }
        )
    return rows


def _gen_orders(rng, customers, products, geos, n_orders: int) -> list[dict]:
    """Line-item grain: each order has 1-4 lines. ~n_orders headers."""
    rows = []
    line_seq = 0
    start, end = date(2025, 1, 1), date(2026, 6, 30)
    prod_by_id = {p["product_id"]: p for p in products}
    for o in range(1, n_orders + 1):
        order_id = f"O{o:05d}"
        cust = rng.choice(customers)
        geo = rng.choice(geos)
        order_date = _rand_date(rng, start, end)
        channel = rng.choice(CHANNELS)
        for _ in range(rng.randint(1, 4)):
            line_seq += 1
            prod = rng.choice(products)
            qty = rng.randint(1, 3)
            discount = rng.choice([0.0, 0.0, 0.0, 0.05, 0.10, 0.15, 0.20, 0.25])
            gross = prod_by_id[prod["product_id"]]["list_price"] * qty
            net = round(gross * (1 - discount), 2)
            cogs = round(prod_by_id[prod["product_id"]]["standard_cost"] * qty, 2)
            rows.append(
                {
                    "order_id": order_id,
                    "order_line_id": f"L{line_seq:06d}",
                    "customer_id": cust["customer_id"],
                    "product_id": prod["product_id"],
                    "geo_id": geo[0],
                    "order_date": order_date,
                    "order_channel": channel,
                    "quantity": qty,
                    "discount_pct": discount,
                    "net_amount": net,
                    "cogs_amount": cogs,
                }
            )
    return rows


def _gen_transactions(rng, orders, customers) -> list[dict]:
    """One payment transaction per order header (grain = order)."""
    geo_currency = {g[0]: ("CAD" if g[3] == "CA" else "USD") for g in GEOGRAPHIES}
    order_totals: dict[str, dict] = {}
    for line in orders:
        agg = order_totals.setdefault(
            line["order_id"],
            {"customer_id": line["customer_id"], "geo_id": line["geo_id"],
             "order_date": line["order_date"], "amount": 0.0},
        )
        agg["amount"] += line["net_amount"]

    rows = []
    for t, (order_id, agg) in enumerate(order_totals.items(), start=1):
        # Status distribution: mostly completed, some refunded/failed/pending.
        status = rng.choices(
            TXN_STATUSES, weights=[80, 10, 6, 4], k=1
        )[0]
        rows.append(
            {
                "transaction_id": f"T{t:05d}",
                "order_id": order_id,
                "customer_id": agg["customer_id"],
                "payment_method": rng.choice(PAYMENT_METHODS),
                "txn_date": agg["order_date"],
                "amount": round(agg["amount"], 2),
                "status": status,
                "currency": geo_currency.get(agg["geo_id"], "USD"),
            }
        )
    return rows


def _gen_shipments(rng, orders, geos) -> list[dict]:
    """One shipment per order header, but ~12% of orders never ship (Step 5 anti-join)."""
    order_headers: dict[str, dict] = {}
    for line in orders:
        order_headers.setdefault(
            line["order_id"], {"geo_id": line["geo_id"], "order_date": line["order_date"]}
        )
    rows = []
    s = 0
    for order_id, hdr in order_headers.items():
        if rng.random() < 0.12:  # unshipped orders
            continue
        s += 1
        ship_date = hdr["order_date"] + timedelta(days=rng.randint(0, 3))
        delivery_days = rng.randint(2, 10)
        delivery_date = ship_date + timedelta(days=delivery_days)
        on_time = delivery_days <= 6
        rows.append(
            {
                "shipment_id": f"S{s + 1000:05d}",
                "order_id": order_id,
                "geo_id": hdr["geo_id"],
                "carrier": rng.choice(CARRIERS),
                "ship_date": ship_date,
                "delivery_date": delivery_date,
                "shipping_cost": round(rng.uniform(6.75, 24.15), 2),
                "delivery_days": delivery_days,
                "on_time_flag": on_time,
            }
        )
    return rows


# --------------------------------------------------------------------------- #
# Bronze writers (inject realistic raw messiness)
# --------------------------------------------------------------------------- #
def _write_bronze_customers(spark, cfg, rng, customers) -> int:
    rows = []
    for c in customers:
        email = c["email"]
        if rng.random() < 0.03:  # a few missing emails
            email = None
        rows.append(
            (
                c["customer_id"],
                c["customer_name"],
                email,
                _maybe_mess_case(rng, c["segment"]),  # inconsistent casing
                c["signup_date"].isoformat(),          # date as string
                c["loyalty_points"],
                c["birth_date"].isoformat(),
                c["is_internal"],
            )
        )
    cols = ["customer_id", "customer_name", "email", "segment", "signup_date",
            "loyalty_points", "birth_date", "is_internal"]
    return _overwrite(spark, cfg.bronze("customers"), rows, cols)


def _write_bronze_products(spark, cfg, products) -> int:
    rows = [
        (p["product_id"], p["product_name"], p["category"], p["subcategory"],
         p["list_price"], p["standard_cost"])
        for p in products
    ]
    cols = ["product_id", "product_name", "category", "subcategory",
            "list_price", "standard_cost"]
    return _overwrite(spark, cfg.bronze("products"), rows, cols)


def _write_bronze_geography(spark, cfg, geos) -> int:
    cols = ["geo_id", "state_code", "region_name", "country_code", "country_name"]
    return _overwrite(spark, cfg.bronze("geography"), [tuple(g) for g in geos], cols)


def _write_bronze_orders(spark, cfg, rng, orders) -> int:
    rows = []
    for o in orders:
        rows.append(
            (
                o["order_id"], o["order_line_id"], o["customer_id"], o["product_id"],
                o["geo_id"], o["order_date"].isoformat(), o["order_channel"],
                o["quantity"], o["discount_pct"], o["net_amount"], o["cogs_amount"],
            )
        )
    # Inject ~1% duplicate lines (silver dedupes on order_line_id).
    dupes = rng.sample(rows, max(1, len(rows) // 100))
    rows = rows + dupes
    cols = ["order_id", "order_line_id", "customer_id", "product_id", "geo_id",
            "order_date", "order_channel", "quantity", "discount_pct",
            "net_amount", "cogs_amount"]
    return _overwrite(spark, cfg.bronze("orders"), rows, cols)


def _write_bronze_transactions(spark, cfg, rng, transactions) -> int:
    rows = [
        (t["transaction_id"], t["order_id"], t["customer_id"], t["payment_method"],
         t["txn_date"].isoformat(), t["amount"], t["status"], t["currency"])
        for t in transactions
    ]
    cols = ["transaction_id", "order_id", "customer_id", "payment_method",
            "txn_date", "amount", "status", "currency"]
    return _overwrite(spark, cfg.bronze("transactions"), rows, cols)


def _write_bronze_shipments(spark, cfg, rng, shipments) -> int:
    rows = []
    for s in shipments:
        rows.append(
            (
                s["shipment_id"], s["order_id"], s["geo_id"],
                _maybe_mess_case(rng, s["carrier"]),  # 'fedex' vs 'FedEx'
                s["ship_date"].isoformat(), s["delivery_date"].isoformat(),
                s["shipping_cost"], s["delivery_days"], s["on_time_flag"],
            )
        )
    cols = ["shipment_id", "order_id", "geo_id", "carrier", "ship_date",
            "delivery_date", "shipping_cost", "delivery_days", "on_time_flag"]
    return _overwrite(spark, cfg.bronze("shipments"), rows, cols)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _overwrite(spark, fqn: str, rows: list[tuple], cols: list[str]) -> int:
    df = spark.createDataFrame(rows, schema=cols)
    df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(fqn)
    return len(rows)


def _rand_date(rng: random.Random, start: date, end: date) -> date:
    return start + timedelta(days=rng.randint(0, (end - start).days))


def _maybe_mess_case(rng: random.Random, value: str) -> str:
    """Return the value with inconsistent casing ~30% of the time."""
    if rng.random() < 0.3:
        return value.lower()
    return value
