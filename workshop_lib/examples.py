"""Step 5: curated high-quality examples — all five asset types, ~2 each.

Each example teaches a pattern the metric views (Step 4) do NOT model:

* example QUERY  x8 — anti-join, refunded-but-shipped, top products, monthly
  trend, revenue net of refunds, margin by subcategory, on-time by carrier,
  repeat customers.
* FILTER         x2 — high-value orders; refunded transactions.
* MEASURE        x2 — revenue net of refunds; distinct active customers.
* FIELD (expr)   x2 — customer age group; order-size bucket.
* JOIN spec      x2 — orders->shipments; transactions->shipments.

`add_examples(builder, cfg)` mutates a SpaceBuilder in place.
"""

from __future__ import annotations


def add_examples(builder, cfg) -> dict:
    fo = cfg.gold("fact_orders")
    ft = cfg.gold("fact_transactions")
    fs = cfg.gold("fact_shipments")
    dc = cfg.gold("dim_customers")
    dp = cfg.gold("dim_products")

    # ---- 8 example QUERIES ------------------------------------------- #
    builder.add_example_sql(
        "Which customers placed orders that never shipped?",
        f"""SELECT DISTINCT c.customer_id, c.customer_name
FROM {fo} o
JOIN {dc} c ON o.customer_id = c.customer_id
LEFT JOIN {fs} s ON o.order_id = s.order_id
WHERE s.shipment_id IS NULL""",
        guidance="Anti-join pattern: LEFT JOIN shipments and keep rows with no match.",
    )
    builder.add_example_sql(
        "List orders that were refunded but still shipped.",
        f"""SELECT DISTINCT t.order_id, t.amount, s.ship_date
FROM {ft} t
JOIN {fs} s ON t.order_id = s.order_id
WHERE t.status = 'REFUNDED'""",
        guidance="Cross-check: refunded transactions that nonetheless have a shipment.",
    )
    builder.add_example_sql(
        "Top 5 products by completed revenue.",
        f"""SELECT p.product_name, ROUND(SUM(o.net_amount), 2) AS revenue
FROM {fo} o
JOIN {dp} p ON o.product_id = p.product_id
JOIN {ft} t ON o.order_id = t.order_id
WHERE t.status = 'COMPLETED'
GROUP BY p.product_name
ORDER BY revenue DESC
LIMIT 5""",
        guidance="Revenue counts only COMPLETED payments — join transactions to enforce it.",
    )
    builder.add_example_sql(
        "Monthly completed revenue trend.",
        f"""SELECT date_trunc('MONTH', o.order_date) AS month,
       ROUND(SUM(o.net_amount), 2) AS revenue
FROM {fo} o
JOIN {ft} t ON o.order_id = t.order_id
WHERE t.status = 'COMPLETED'
GROUP BY month
ORDER BY month""",
        guidance="Truncate order_date to month; completed payments only.",
    )
    builder.add_example_sql(
        "Revenue net of refunds by month (refunds counted as negative).",
        f"""SELECT date_trunc('MONTH', txn_date) AS month,
       ROUND(SUM(CASE WHEN status = 'REFUNDED' THEN -amount
                      WHEN status = 'COMPLETED' THEN amount
                      ELSE 0 END), 2) AS net_revenue
FROM {ft}
GROUP BY month
ORDER BY month""",
        guidance="Refunds subtract; failed/pending are excluded.",
    )
    builder.add_example_sql(
        "Gross margin % by subcategory, excluding internal test accounts.",
        f"""SELECT p.subcategory,
       ROUND(SUM(o.net_amount - o.cogs_amount) / SUM(o.net_amount) * 100, 1) AS margin_pct
FROM {fo} o
JOIN {dp} p ON o.product_id = p.product_id
JOIN {dc} c ON o.customer_id = c.customer_id
WHERE c.is_internal = false
GROUP BY p.subcategory
ORDER BY margin_pct DESC""",
        guidance="Aggregate then divide (sum of margin / sum of revenue); exclude internal accounts.",
    )
    builder.add_example_sql(
        "On-time delivery rate by carrier.",
        f"""SELECT carrier,
       ROUND(AVG(CASE WHEN on_time_flag THEN 1.0 ELSE 0 END) * 100, 1) AS on_time_pct,
       COUNT(*) AS shipments
FROM {fs}
GROUP BY carrier
ORDER BY on_time_pct DESC""",
        guidance="Rate = on-time shipments / total shipments, at shipment grain.",
    )
    builder.add_example_sql(
        "Repeat customers and their total completed spend.",
        f"""SELECT o.customer_id,
       COUNT(DISTINCT o.order_id) AS orders,
       ROUND(SUM(o.net_amount), 2) AS spend
FROM {fo} o
JOIN {ft} t ON o.order_id = t.order_id
WHERE t.status = 'COMPLETED'
GROUP BY o.customer_id
HAVING COUNT(DISTINCT o.order_id) > 1
ORDER BY spend DESC""",
        guidance="HAVING on distinct order count identifies repeat buyers.",
    )

    # ---- 2 FILTERS ---------------------------------------------------- #
    builder.add_filter(
        f"`{fo.rsplit('.',1)[-1]}`.net_amount > 500",
        display_name="High-value orders",
        instruction="When the user asks about high-value or large orders (over $500).",
        synonyms=["large orders", "big orders", "high value"],
    )
    builder.add_filter(
        f"`{ft.rsplit('.',1)[-1]}`.status = 'REFUNDED'",
        display_name="Refunded only",
        instruction="When the user is only interested in refunded transactions.",
        synonyms=["refunds only", "just refunds"],
    )

    # ---- 2 MEASURES --------------------------------------------------- #
    _ftt = ft.rsplit('.', 1)[-1]
    builder.add_measure(
        f"SUM(CASE WHEN `{_ftt}`.status = 'COMPLETED' THEN `{_ftt}`.amount "
        f"WHEN `{_ftt}`.status = 'REFUNDED' THEN -`{_ftt}`.amount ELSE 0 END)",
        display_name="Revenue net of refunds",
        instruction=("Collected revenue with refunds subtracted: COMPLETED amounts "
                     "count positive, REFUNDED negative, FAILED/PENDING excluded (0)."),
        synonyms=["net revenue", "revenue after refunds"],
    )
    builder.add_measure(
        f"COUNT(DISTINCT `{fo.rsplit('.',1)[-1]}`.customer_id)",
        display_name="Distinct customers",
        instruction="Number of unique customers who placed orders.",
        synonyms=["unique customers", "number of customers"],
    )

    # ---- 2 FIELDS (expressions) -------------------------------------- #
    builder.add_expression(
        f"""CASE
  WHEN datediff(current_date(), `{dc.rsplit('.',1)[-1]}`.birth_date)/365 < 25 THEN 'Under 25'
  WHEN datediff(current_date(), `{dc.rsplit('.',1)[-1]}`.birth_date)/365 < 40 THEN '25-39'
  WHEN datediff(current_date(), `{dc.rsplit('.',1)[-1]}`.birth_date)/365 < 60 THEN '40-59'
  ELSE '60+'
END AS customer_age_group""",
        display_name="Customer age group",
        instruction="When grouping or filtering by customer age bracket.",
        synonyms=["age bracket", "age band"],
    )
    builder.add_expression(
        f"""CASE
  WHEN `{fo.rsplit('.',1)[-1]}`.net_amount < 50 THEN 'Small'
  WHEN `{fo.rsplit('.',1)[-1]}`.net_amount < 200 THEN 'Medium'
  ELSE 'Large'
END AS order_size_bucket""",
        display_name="Order size bucket",
        instruction="When bucketing orders into small / medium / large by net amount.",
        synonyms=["order size", "basket size"],
    )

    # ---- 2 JOIN specs ------------------------------------------------- #
    builder.add_join_spec(fo, "fact_orders", fs, "fact_shipments",
                          "`fact_orders`.`order_id` = `fact_shipments`.`order_id`")
    builder.add_join_spec(ft, "fact_transactions", fs, "fact_shipments",
                          "`fact_transactions`.`order_id` = `fact_shipments`.`order_id`")

    return {"examples": 8, "filters": 2, "measures": 2, "expressions": 2, "joins": 2}
