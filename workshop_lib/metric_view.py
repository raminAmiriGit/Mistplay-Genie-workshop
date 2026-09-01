"""Step 4: build Unity Catalog METRIC VIEWS (measures + joins + filter).

Metric views are the governed semantic layer. We build two, because grain
matters and mixing grains fan-traps the math:

* ``mv_order_analytics``      — order-LINE grain. Joins products / geography /
  customers / transactions; a built-in FILTER keeps only COMPLETED payments;
  measures for revenue, gross margin %, AOV, units.
* ``mv_shipment_performance`` — SHIPMENT grain. Joins geography; measures for
  on-time delivery rate, avg delivery days, shipping cost.

Created via ``CREATE OR REPLACE VIEW <name> WITH METRICS LANGUAGE YAML AS $$...$$``
(YAML spec version 1.1). Genie queries measures through ``MEASURE(...)`` — but the
attendee never writes that; attaching the metric view to the space is enough.
"""

from __future__ import annotations

ORDER_MV = "mv_order_analytics"
SHIPMENT_MV = "mv_shipment_performance"


def _order_yaml(cfg) -> str:
    src = cfg.gold("fact_orders")
    products = cfg.gold("dim_products")
    geography = cfg.gold("dim_geography")
    customers = cfg.gold("dim_customers")
    transactions = cfg.gold("fact_transactions")
    return f"""version: 1.1
comment: "Order analytics (line grain). Completed payments only."
source: {src}

joins:
  - name: products
    source: {products}
    on: source.product_id = products.product_id
    rely:
      at_most_one_match: true
  - name: geography
    source: {geography}
    on: source.geo_id = geography.geo_id
    rely:
      at_most_one_match: true
  - name: customers
    source: {customers}
    on: source.customer_id = customers.customer_id
    rely:
      at_most_one_match: true
  - name: transactions
    source: {transactions}
    on: source.order_id = transactions.order_id
    rely:
      at_most_one_match: true

filter: transactions.status = 'COMPLETED'

dimensions:
  - name: Order Month
    expr: date_trunc('MONTH', source.order_date)
  - name: Order Channel
    expr: source.order_channel
  - name: Region
    expr: geography.region_name
  - name: State
    expr: geography.state_code
  - name: Country
    expr: geography.country_name
  - name: Category
    expr: products.category
  - name: Subcategory
    expr: products.subcategory
  - name: Product
    expr: products.product_name
  - name: Customer Segment
    expr: customers.segment
  - name: Payment Method
    expr: transactions.payment_method
  - name: Currency
    expr: transactions.currency

measures:
  - name: Total Revenue
    expr: SUM(source.net_amount)
  - name: Total COGS
    expr: SUM(source.cogs_amount)
  - name: Gross Profit
    expr: SUM(source.net_amount - source.cogs_amount)
  - name: Gross Margin Pct
    expr: SUM(source.net_amount - source.cogs_amount) / NULLIF(SUM(source.net_amount), 0)
  - name: Order Count
    expr: COUNT(DISTINCT source.order_id)
  - name: Units Sold
    expr: SUM(source.quantity)
  - name: Average Order Value
    expr: SUM(source.net_amount) / NULLIF(COUNT(DISTINCT source.order_id), 0)
"""


def _shipment_yaml(cfg) -> str:
    src = cfg.gold("fact_shipments")
    geography = cfg.gold("dim_geography")
    return f"""version: 1.1
comment: "Shipment performance (shipment grain)."
source: {src}

joins:
  - name: geography
    source: {geography}
    on: source.geo_id = geography.geo_id
    rely:
      at_most_one_match: true

dimensions:
  - name: Ship Month
    expr: date_trunc('MONTH', source.ship_date)
  - name: Region
    expr: geography.region_name
  - name: State
    expr: geography.state_code
  - name: Carrier
    expr: source.carrier

measures:
  - name: Shipment Count
    expr: COUNT(1)
  - name: On Time Count
    expr: SUM(CASE WHEN source.on_time_flag THEN 1 ELSE 0 END)
  - name: On Time Rate
    expr: SUM(CASE WHEN source.on_time_flag THEN 1 ELSE 0 END) / NULLIF(COUNT(1), 0)
  - name: Average Delivery Days
    expr: AVG(source.delivery_days)
  - name: Total Shipping Cost
    expr: SUM(source.shipping_cost)
"""


def build_metric_views(spark, cfg) -> list[str]:
    """Create both metric views. Returns their fully-qualified names."""
    created = []
    for name, yaml_fn in ((ORDER_MV, _order_yaml), (SHIPMENT_MV, _shipment_yaml)):
        fqn = cfg.gold(name)
        ddl = f"CREATE OR REPLACE VIEW {fqn}\nWITH METRICS\nLANGUAGE YAML\nAS $$\n{yaml_fn(cfg)}$$"
        spark.sql(ddl)
        created.append(fqn)
    return created
