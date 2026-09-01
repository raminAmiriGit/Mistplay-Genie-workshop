"""Step 5: curated high-quality examples — all five asset types, ~2 each.

Each example teaches a pattern the metric views (Step 4) do NOT model:

* example QUERY  x2 — anti-join (orders never shipped); refunded-but-shipped.
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

    # ---- 2 example QUERIES ------------------------------------------- #
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
    builder.add_measure(
        f"SUM(CASE WHEN `{ft.rsplit('.',1)[-1]}`.status = 'REFUNDED' "
        f"THEN -`{ft.rsplit('.',1)[-1]}`.amount ELSE `{ft.rsplit('.',1)[-1]}`.amount END)",
        display_name="Revenue net of refunds",
        instruction="Revenue counting refunds as negative amounts.",
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

    return {"examples": 2, "filters": 2, "measures": 2, "expressions": 2, "joins": 2}
