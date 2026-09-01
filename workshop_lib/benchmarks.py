"""Step 7: benchmark question + answer bank (~40 questions).

Spans the full difficulty range of Steps 2-6 so it can score how well the tuned
space performs. Each entry has a business question, a reference SQL answer, a
category, and a difficulty tier. `build_benchmarks(cfg)` resolves table names for
the attendee's catalog/schema; `add_all(builder, cfg)` pushes them to the space.
"""

from __future__ import annotations


def build_benchmarks(cfg) -> list[dict]:
    o = cfg.gold("fact_orders")
    t = cfg.gold("fact_transactions")
    s = cfg.gold("fact_shipments")
    c = cfg.gold("dim_customers")
    p = cfg.gold("dim_products")
    g = cfg.gold("dim_geography")
    omv = cfg.gold("mv_order_analytics")
    smv = cfg.gold("mv_shipment_performance")

    B: list[dict] = []

    def add(question, sql, category, difficulty):
        B.append({"question": question, "sql": sql, "category": category, "difficulty": difficulty})

    # ---- basic aggregation (Step 2 level) ---------------------------- #
    add("What is the total net revenue across all orders?",
        f"SELECT SUM(net_amount) AS total_revenue FROM {o}", "aggregation", "basic")
    add("How many orders were placed through each sales channel?",
        f"SELECT order_channel, COUNT(DISTINCT order_id) AS orders FROM {o} GROUP BY order_channel", "aggregation", "basic")
    add("How many customers are in each segment?",
        f"SELECT segment, COUNT(*) AS customers FROM {c} GROUP BY segment", "aggregation", "basic")
    add("What is the average delivery time in days?",
        f"SELECT AVG(delivery_days) AS avg_days FROM {s}", "aggregation", "basic")
    add("How many products are in each subcategory?",
        f"SELECT subcategory, COUNT(*) AS n FROM {p} GROUP BY subcategory", "aggregation", "basic")
    add("What is the total quantity of units ordered?",
        f"SELECT SUM(quantity) AS units FROM {o}", "aggregation", "basic")
    add("Which product has the highest list price?",
        f"SELECT product_name, list_price FROM {p} ORDER BY list_price DESC LIMIT 1", "aggregation", "basic")
    add("How many shipments used each carrier?",
        f"SELECT carrier, COUNT(*) AS n FROM {s} GROUP BY carrier", "aggregation", "basic")

    # ---- value matching (Step 3) ------------------------------------- #
    add("How much revenue came from payments made with PayPal?",
        f"SELECT SUM(amount) FROM {t} WHERE payment_method='PM02' AND status='COMPLETED'", "value-matching", "intermediate")
    add("How many orders were paid by credit card?",
        f"SELECT COUNT(DISTINCT order_id) FROM {t} WHERE payment_method='PM01'", "value-matching", "intermediate")
    add("What is the total value of gift-card transactions?",
        f"SELECT SUM(amount) FROM {t} WHERE payment_method='PM03'", "value-matching", "intermediate")
    add("What is total net revenue in California?",
        f"SELECT SUM(o.net_amount) FROM {o} o JOIN {g} g ON o.geo_id=g.geo_id WHERE g.state_code='CA'", "value-matching", "intermediate")
    add("How many orders shipped to Ontario?",
        f"SELECT COUNT(DISTINCT s.order_id) FROM {s} s JOIN {g} g ON s.geo_id=g.geo_id WHERE g.state_code='ON'", "value-matching", "intermediate")
    add("How many transactions were in Canadian dollars?",
        f"SELECT COUNT(*) FROM {t} WHERE currency='CAD'", "value-matching", "intermediate")
    add("How many transactions were refunded?",
        f"SELECT COUNT(*) FROM {t} WHERE status='REFUNDED'", "value-matching", "intermediate")

    # ---- measures / metric view (Step 4) ----------------------------- #
    add("What is our on-time delivery rate by region?",
        f"SELECT `Region`, MEASURE(`On Time Rate`) FROM {smv} GROUP BY `Region`", "measure", "intermediate")
    add("What is the gross margin percentage by product subcategory?",
        f"SELECT `Subcategory`, MEASURE(`Gross Margin Pct`) FROM {omv} GROUP BY `Subcategory`", "measure", "intermediate")
    add("What is the average order value by customer segment?",
        f"SELECT `Customer Segment`, MEASURE(`Average Order Value`) FROM {omv} GROUP BY `Customer Segment`", "measure", "intermediate")
    add("What is total completed revenue by month?",
        f"SELECT `Order Month`, MEASURE(`Total Revenue`) FROM {omv} GROUP BY `Order Month` ORDER BY `Order Month`", "measure", "intermediate")
    add("Compare gross margin percentage across sales channels.",
        f"SELECT `Order Channel`, MEASURE(`Gross Margin Pct`) FROM {omv} GROUP BY `Order Channel`", "measure", "intermediate")
    add("What is the average delivery days by carrier?",
        f"SELECT `Carrier`, MEASURE(`Average Delivery Days`) FROM {smv} GROUP BY `Carrier`", "measure", "intermediate")
    add("What is total gross profit overall?",
        f"SELECT MEASURE(`Gross Profit`) FROM {omv}", "measure", "intermediate")
    add("How many distinct orders had completed payments?",
        f"SELECT MEASURE(`Order Count`) FROM {omv}", "measure", "intermediate")

    # ---- joins / exceptions (Step 5) --------------------------------- #
    add("Which customers placed orders that never shipped?",
        f"SELECT DISTINCT c.customer_id, c.customer_name FROM {o} o JOIN {c} c ON o.customer_id=c.customer_id "
        f"LEFT JOIN {s} s ON o.order_id=s.order_id WHERE s.shipment_id IS NULL", "joins-exceptions", "advanced")
    add("List orders that were refunded but still shipped.",
        f"SELECT DISTINCT t.order_id FROM {t} t JOIN {s} s ON t.order_id=s.order_id WHERE t.status='REFUNDED'", "joins-exceptions", "advanced")
    add("What is revenue net of refunds (refunds counted as negative)?",
        f"SELECT SUM(CASE WHEN status='REFUNDED' THEN -amount ELSE amount END) FROM {t} WHERE status IN ('COMPLETED','REFUNDED')", "joins-exceptions", "advanced")
    add("How many orders were never shipped?",
        f"SELECT COUNT(*) FROM (SELECT DISTINCT o.order_id FROM {o} o LEFT JOIN {s} s ON o.order_id=s.order_id WHERE s.shipment_id IS NULL)", "joins-exceptions", "advanced")
    add("Show high-value orders over $500.",
        f"SELECT order_id, net_amount FROM {o} WHERE net_amount > 500 ORDER BY net_amount DESC", "joins-exceptions", "advanced")
    add("What is the top 10 customers by completed revenue?",
        f"SELECT o.customer_id, SUM(o.net_amount) rev FROM {o} o JOIN {t} t ON o.order_id=t.order_id "
        f"WHERE t.status='COMPLETED' GROUP BY o.customer_id ORDER BY rev DESC LIMIT 10", "joins-exceptions", "advanced")
    add("Break revenue down by customer age group.",
        f"SELECT CASE WHEN datediff(current_date(), c.birth_date)/365 < 25 THEN 'Under 25' "
        f"WHEN datediff(current_date(), c.birth_date)/365 < 40 THEN '25-39' "
        f"WHEN datediff(current_date(), c.birth_date)/365 < 60 THEN '40-59' ELSE '60+' END age_group, "
        f"SUM(o.net_amount) rev FROM {o} o JOIN {c} c ON o.customer_id=c.customer_id GROUP BY age_group", "joins-exceptions", "advanced")
    add("What is the refund rate as a percentage of all transactions?",
        f"SELECT SUM(CASE WHEN status='REFUNDED' THEN 1 ELSE 0 END)/COUNT(*) AS refund_rate FROM {t}", "joins-exceptions", "advanced")
    add("Which region has the most unshipped orders?",
        f"SELECT g.region_name, COUNT(DISTINCT o.order_id) n FROM {o} o JOIN {g} g ON o.geo_id=g.geo_id "
        f"LEFT JOIN {s} s ON o.order_id=s.order_id WHERE s.shipment_id IS NULL GROUP BY g.region_name ORDER BY n DESC LIMIT 1", "joins-exceptions", "advanced")

    # ---- rules / instructions (Step 6) ------------------------------- #
    add("What was our revenue last fiscal quarter?",
        f"-- fiscal year starts Feb 1; compute fiscal quarter of order_date, exclude internal accounts\n"
        f"SELECT SUM(o.net_amount) FROM {o} o JOIN {c} c ON o.customer_id=c.customer_id "
        f"JOIN {t} t ON o.order_id=t.order_id WHERE c.is_internal=false AND t.status='COMPLETED'", "rules", "advanced")
    add("Show this quarter's revenue excluding internal test accounts.",
        f"SELECT SUM(o.net_amount) FROM {o} o JOIN {c} c ON o.customer_id=c.customer_id "
        f"WHERE c.is_internal=false", "rules", "advanced")
    add("How many active customers do we have (ordered in last 90 days)?",
        f"SELECT COUNT(DISTINCT customer_id) FROM {o} WHERE order_date >= date_sub(current_date(), 90)", "rules", "advanced")
    add("What is total revenue including internal accounts?",
        f"SELECT SUM(net_amount) FROM {o}", "rules", "advanced")
    add("Give a concise KPI summary for last month.",
        f"SELECT MEASURE(`Total Revenue`) revenue, MEASURE(`Order Count`) orders, MEASURE(`Gross Margin Pct`) margin "
        f"FROM {omv} WHERE `Order Month` = date_trunc('MONTH', date_sub(current_date(), 30))", "rules", "advanced")
    add("How many internal/test accounts are in the customer base?",
        f"SELECT COUNT(*) FROM {c} WHERE is_internal=true", "rules", "basic")
    add("What is completed revenue by country, excluding internal accounts?",
        f"SELECT g.country_name, SUM(o.net_amount) FROM {o} o JOIN {c} c ON o.customer_id=c.customer_id "
        f"JOIN {g} g ON o.geo_id=g.geo_id JOIN {t} t ON o.order_id=t.order_id "
        f"WHERE c.is_internal=false AND t.status='COMPLETED' GROUP BY g.country_name", "rules", "advanced")
    add("What share of revenue comes from Corporate segment customers?",
        f"SELECT SUM(CASE WHEN c.segment='Corporate' THEN o.net_amount ELSE 0 END)/SUM(o.net_amount) "
        f"FROM {o} o JOIN {c} c ON o.customer_id=c.customer_id", "rules", "advanced")

    return B


def add_all(builder, cfg) -> int:
    bank = build_benchmarks(cfg)
    for item in bank:
        builder.add_benchmark(item["question"], item["sql"])
    return len(bank)
