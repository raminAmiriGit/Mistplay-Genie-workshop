"""Set A / Set B question banks per step, WITH ground-truth answers.

Teaching contract: each step ends with two sets.
  * SET A — the space can answer these NOW (proves the step's change worked).
  * SET B — the space still cannot answer these CORRECTLY; the reason is exactly
            what the NEXT step fixes. **Set B of step N == Set A of step N+1.**

Because Genie *agent mode* can derive joins/filters/exceptions, many Set B items
are "traps": the agent returns an answer, but a WRONG or INCONSISTENT one. So
every question carries a ground-truth so you can check the agent live:
  * ``q``         — the business question (as a user asks it).
  * ``sql``       — ground-truth SQL producing the CORRECT answer ("" if the
                    question is genuinely unanswerable — expect Genie to decline).
  * ``expect``    — plain-language description of the correct answer / behavior.
  * ``trap_sql``  — (optional) the naive/wrong computation the agent tends to do.
  * ``trap_label``— (optional) label for that wrong answer.

``render(step)`` prints the questions + expected answers (static).
``answer_df(spark, cfg, step)`` RUNS the ground-truth (and trap) SQL against the
attendee's data and returns a table of real numbers — call it in the notebook.

Steps 1-2 are intentionally simple (plain string questions, no ground truth).
"""

from __future__ import annotations

# Short placeholder -> gold table name; resolved per attendee via cfg.gold().
_TABLES = {
    "orders": "fact_orders",
    "txns": "fact_transactions",
    "ships": "fact_shipments",
    "custs": "dim_customers",
    "prods": "dim_products",
    "geo": "dim_geography",
    "omv": "mv_order_analytics",
    "smv": "mv_shipment_performance",
}


def _resolve(sql: str, cfg) -> str:
    if not sql:
        return ""
    return sql.format(**{k: cfg.gold(v) for k, v in _TABLES.items()})


# --------------------------------------------------------------------------- #
# Rendering (static — no spark needed)
# --------------------------------------------------------------------------- #
def render(step: int) -> str:
    q = QUESTIONS[step]
    out = [f"### Try these in your Genie space\n", f"**{q['title']}**\n"]
    out.append("#### ✅ Set A — should answer now (expected answer shown)\n")
    out += _render_items(q["set_a"])
    out.append(f"\n> _Why these work now: {q['why_a']}_\n")
    out.append("#### ❌ Set B — agent should NOT get these right yet\n")
    out += _render_items(q["set_b"])
    out.append(f"\n> _Why these fail: {q['why_b']}_  \n> _→ addressed in **Step {step + 1}**._")
    return "\n".join(out)


def _render_items(items) -> list[str]:
    lines = []
    for i, it in enumerate(items, 1):
        if isinstance(it, str):
            lines.append(f"{i}. {it}")
            continue
        lines.append(f"{i}. **{it['q']}**")
        lines.append(f"   - ✅ Expected: {it['expect']}")
        if it.get("trap_label"):
            lines.append(f"   - ⚠️ Common wrong answer: {it['trap_label']}")
        if it.get("why_fail"):
            lines.append(f"   - 🚫 Why the agent can't get this right yet: {it['why_fail']}")
    return lines


# --------------------------------------------------------------------------- #
# Live ground-truth answers (runs SQL against the attendee's data)
# --------------------------------------------------------------------------- #
def answer_df(spark, cfg, step: int):
    """Run each question's ground-truth (and trap) SQL; return a Spark DataFrame.

    Columns: set, question, correct_answer, correct_sql (resolved ground-truth
    query), naive_or_trap_answer (the wrong number/behavior the agent tends to
    produce), why_agent_fails (why the agent can't get Set B right on its own).
    """
    q = QUESTIONS[step]
    rows = []
    for set_name, items in (("A", q["set_a"]), ("B", q["set_b"])):
        for it in items:
            # Plain-string question (Set A of step 2) — no ground truth attached.
            if isinstance(it, str):
                rows.append((set_name, it, "(answerable by agent — no ground-truth query)",
                             "", "", ""))
                continue
            why = it.get("why_fail", "") if set_name == "B" else ""
            # Genuinely unanswerable (no SQL) — e.g. step 6 Set B.
            if not it.get("sql"):
                trap = it.get("trap_label", "agent may hallucinate an answer")
                rows.append((set_name, it["q"], "(not answerable — expect Genie to decline)",
                             "", trap, why))
                continue
            sql = _resolve(it["sql"], cfg)
            correct = _scalar(spark, sql)
            # Trap: numeric (trap_sql) + label, or behavioral label only.
            if it.get("trap_sql"):
                trap = _scalar(spark, _resolve(it["trap_sql"], cfg))
                if it.get("trap_label"):
                    trap = f"{trap}  ({it['trap_label']})"
            else:
                trap = it.get("trap_label", "")
            rows.append((set_name, it["q"], correct, sql, trap, why))
    return spark.createDataFrame(
        rows,
        schema=["set", "question", "correct_answer", "correct_sql",
                "naive_or_trap_answer", "why_agent_fails"],
    )


def _scalar(spark, sql: str) -> str:
    try:
        r = spark.sql(sql).collect()
        if not r:
            return "(no rows)"
        v = r[0][0]
        if isinstance(v, float):
            return f"{v:,.2f}"
        if isinstance(v, int):
            return f"{v:,}"
        return str(v)
    except Exception as e:  # keep the workshop moving if a query errors
        return f"(error: {str(e)[:60]})"


# --------------------------------------------------------------------------- #
# Question bank
# --------------------------------------------------------------------------- #
QUESTIONS: dict[int, dict] = {
    # ---- Steps 1-2 unchanged (simple, no ground truth) ---------------- #
    2: {
        "title": "Step 2 — bare space on gold tables (+ column comments)",
        "set_a": [
            "Total net revenue by product subcategory for orders in the first half of 2026.",
            "Which carrier has the highest average delivery days for shipments to Canada?",
            "Top 5 customers by total order value, showing their segment.",
        ],
        "why_a": "Agent mode can join the well-commented gold tables and aggregate.",
        "set_b": [
            {"q": "How much revenue came from PayPal payments?",
             "sql": "SELECT ROUND(SUM(amount),2) FROM {txns} WHERE payment_method='PM02' AND status='COMPLETED'",
             "expect": "Completed PM02 (PayPal) amount.",
             "trap_label": "no code decodes 'PayPal' → agent guesses a code or returns 0",
             "why_fail": "payment_method is an opaque code (PM02); with no lookup column and nothing to profile, the agent cannot map the word 'PayPal' to PM02."},
            {"q": "What did our gift-card customers spend?",
             "sql": "SELECT ROUND(SUM(amount),2) FROM {txns} WHERE payment_method='PM03' AND status='COMPLETED'",
             "expect": "Completed PM03 (Gift Card) amount.",
             "trap_label": "'gift card' matches no value → likely 0 or a wrong code",
             "why_fail": "PM03 is opaque; 'gift card' appears nowhere in the data for the agent to match."},
            {"q": "How much did our enterprise (B2B) clients spend?",
             "sql": "SELECT ROUND(SUM(o.net_amount),2) FROM {orders} o JOIN {custs} c ON o.customer_id=c.customer_id WHERE c.segment='Corporate'",
             "expect": "Net revenue from Corporate-segment customers.",
             "trap_label": "'enterprise' isn't a segment value → agent may filter nothing",
             "why_fail": "the segment value is 'Corporate'; the word 'enterprise'/'B2B' exists in no column, so the agent has nothing to match."},
        ],
        "why_b": (
            "payment_method stores opaque codes (PM01..PM04) with no lookup, and "
            "'enterprise' is nowhere in the data. Needs value matching."
        ),
    },
    # ---- Step 3: value matching. Set B = revenue-definition traps ----- #
    3: {
        "title": "Step 3 — value matching (decode codes + jargon)",
        "set_a": [
            {"q": "How much completed revenue came from PayPal payments?",
             "sql": "SELECT ROUND(SUM(amount),2) FROM {txns} WHERE payment_method='PM02' AND status='COMPLETED'",
             "expect": "Sum of amount for PM02 (PayPal) completed transactions."},
            {"q": "What did our gift-card customers spend (completed)?",
             "sql": "SELECT ROUND(SUM(amount),2) FROM {txns} WHERE payment_method='PM03' AND status='COMPLETED'",
             "expect": "Sum of amount for PM03 (Gift Card) completed transactions."},
            {"q": "How much did enterprise (B2B) clients spend?",
             "sql": "SELECT ROUND(SUM(o.net_amount),2) FROM {orders} o JOIN {custs} c ON o.customer_id=c.customer_id WHERE c.segment='Corporate'",
             "expect": "Net revenue from Corporate-segment customers."},
            {"q": "How much completed revenue was paid in Canadian dollars?",
             "sql": "SELECT ROUND(SUM(amount),2) FROM {txns} WHERE currency='CAD' AND status='COMPLETED'",
             "expect": "Sum of completed CAD transaction amounts."},
        ],
        "why_a": (
            "Column descriptions now decode the codes (PM02=PayPal, PM03=Gift Card, "
            "Corporate=enterprise/B2B, CAD=Canadian Dollars); synonyms + entity matching "
            "resolve the business words."
        ),
        "set_b": [
            {"q": "What is our total revenue?",
             "sql": "SELECT ROUND(SUM(o.net_amount),2) FROM {orders} o JOIN {txns} t ON o.order_id=t.order_id WHERE t.status='COMPLETED'",
             "expect": "Revenue = net_amount of orders whose payment COMPLETED.",
             "trap_sql": "SELECT ROUND(SUM(net_amount),2) FROM {orders}",
             "trap_label": "agent sums ALL orders incl. failed/pending/refunded → overstated",
             "why_fail": "nothing tells the agent that 'revenue' means collected (COMPLETED) money, so it sums every order and overstates. The definition lives in a metric view."},
            {"q": "What is the average order value?",
             "sql": "SELECT ROUND(SUM(net_amount)/COUNT(DISTINCT order_id),2) FROM {orders}",
             "expect": "Total net_amount / distinct orders (per-order grain).",
             "trap_sql": "SELECT ROUND(AVG(net_amount),2) FROM {orders}",
             "trap_label": "agent averages line amounts (wrong grain)",
             "why_fail": "fact_orders is at line grain; without a governed AOV definition the agent averages line rows instead of dividing by distinct orders."},
            {"q": "What is the gross margin percentage?",
             "sql": "SELECT ROUND(SUM(net_amount-cogs_amount)/SUM(net_amount)*100,1) FROM {orders}",
             "expect": "Aggregate (net - cogs) / net, as a %.",
             "trap_sql": "SELECT ROUND(AVG((net_amount-cogs_amount)/net_amount)*100,1) FROM {orders}",
             "trap_label": "agent averages per-line margins (wrong)",
             "why_fail": "margin can be computed several ways; without one governed formula the agent may average per-line ratios instead of aggregating first."},
        ],
        "why_b": (
            "Agent mode WILL return numbers, but 'revenue' should count only COMPLETED "
            "payments and margin/AOV must use a consistent formula & grain. Those are "
            "governed definitions — a metric view."
        ),
    },
    # ---- Step 4: metric view. Set B = exceptions -> step 5 ------------ #
    4: {
        "title": "Step 4 — metric view (governed measures, joins, completed-only filter)",
        "set_a": [
            {"q": "What is our total (completed) revenue?",
             "sql": "SELECT ROUND(SUM(o.net_amount),2) FROM {orders} o JOIN {txns} t ON o.order_id=t.order_id WHERE t.status='COMPLETED'",
             "expect": "The governed number — the metric view's completed-only revenue."},
            {"q": "What is our overall gross margin percentage?",
             "sql": "SELECT ROUND(SUM(net_amount-cogs_amount)/SUM(net_amount)*100,1) FROM {orders}",
             "expect": "Aggregate margin %, defined once in the metric view."},
            {"q": "What is our on-time delivery rate?",
             "sql": "SELECT ROUND(AVG(CASE WHEN on_time_flag THEN 1.0 ELSE 0 END)*100,1) FROM {ships}",
             "expect": "% of shipments delivered on time (shipment grain)."},
            {"q": "What is the average order value?",
             "sql": "SELECT ROUND(SUM(net_amount)/COUNT(DISTINCT order_id),2) FROM {orders}",
             "expect": "Per-order AOV — one consistent definition."},
        ],
        "why_a": (
            "The metric view defines revenue (completed only), margin %, AOV and on-time "
            "rate once — with joins and the status filter baked in — so answers are "
            "correct and identical every time."
        ),
        "set_b": [
            {"q": "What is revenue net of refunds, counting refunds as negative?",
             "sql": "SELECT ROUND(SUM(CASE WHEN status='REFUNDED' THEN -amount WHEN status='COMPLETED' THEN amount ELSE 0 END),2) FROM {txns}",
             "expect": "Completed amounts minus refunded amounts.",
             "trap_sql": "SELECT ROUND(SUM(amount),2) FROM {txns} WHERE status='COMPLETED'",
             "trap_label": "agent often ignores refunds entirely",
             "why_fail": "the 'refunds count as negative' convention isn't stated anywhere; the agent typically reports completed revenue and silently drops refunds."},
            {"q": "How many orders were placed but never shipped?",
             "sql": "SELECT COUNT(*) FROM (SELECT DISTINCT o.order_id FROM {orders} o LEFT JOIN {ships} s ON o.order_id=s.order_id WHERE s.shipment_id IS NULL)",
             "expect": "Distinct orders with no shipment row (anti-join).",
             "trap_label": "agent inner-joins orders↔shipments and undercounts/returns 0",
             "why_fail": "answering needs an anti-join (LEFT JOIN … WHERE shipment IS NULL); the agent tends to inner-join and never sees the missing rows unless shown the pattern."},
            {"q": "How many delivered orders were later refunded?",
             "sql": "SELECT COUNT(DISTINCT t.order_id) FROM {txns} t JOIN {ships} s ON t.order_id=s.order_id WHERE t.status='REFUNDED'",
             "expect": "Distinct refunded orders that also have a shipment.",
             "trap_label": "agent may not equate 'delivered' with 'has a shipment'",
             "why_fail": "'delivered' isn't a column; it means 'has a shipment row'. Without a worked example the agent guesses at that mapping and the transactions×shipments join."},
        ],
        "why_b": (
            "These need specific exception patterns the metric view doesn't model "
            "(refunds-as-negative convention, anti-join, refunded-and-shipped). Taught "
            "with curated examples."
        ),
    },
    # ---- Step 5: examples. Set B = conventions -> step 6 -------------- #
    5: {
        "title": "Step 5 — curated examples (query, filter, measure, field, join)",
        "set_a": [
            {"q": "What is revenue net of refunds, counting refunds as negative?",
             "sql": "SELECT ROUND(SUM(CASE WHEN status='REFUNDED' THEN -amount WHEN status='COMPLETED' THEN amount ELSE 0 END),2) FROM {txns}",
             "expect": "Completed minus refunded — now via the curated measure."},
            {"q": "How many orders were placed but never shipped?",
             "sql": "SELECT COUNT(*) FROM (SELECT DISTINCT o.order_id FROM {orders} o LEFT JOIN {ships} s ON o.order_id=s.order_id WHERE s.shipment_id IS NULL)",
             "expect": "Distinct unshipped orders — via the curated anti-join example."},
            {"q": "How many delivered orders were later refunded?",
             "sql": "SELECT COUNT(DISTINCT t.order_id) FROM {txns} t JOIN {ships} s ON t.order_id=s.order_id WHERE t.status='REFUNDED'",
             "expect": "Refunded-and-shipped orders — via the curated example."},
        ],
        "why_a": "Curated examples give Genie the exact patterns for these exceptions.",
        "set_b": [
            {"q": "What was revenue in the last fiscal quarter?",
             "sql": "SELECT ROUND(SUM(o.net_amount),2) FROM {orders} o JOIN {txns} t ON o.order_id=t.order_id WHERE t.status='COMPLETED' AND o.order_date BETWEEN '2026-05-01' AND '2026-07-31'",
             "expect": "Fiscal Q2 = May-Jul (fiscal year starts Feb 1).",
             "trap_sql": "SELECT ROUND(SUM(o.net_amount),2) FROM {orders} o JOIN {txns} t ON o.order_id=t.order_id WHERE t.status='COMPLETED' AND o.order_date BETWEEN '2026-04-01' AND '2026-06-30'",
             "trap_label": "agent uses CALENDAR Q2 (Apr-Jun) → wrong window",
             "why_fail": "the company's fiscal calendar (year starts Feb 1) exists nowhere in the data; the agent defaults to calendar quarters and picks the wrong date window."},
            {"q": "How many active customers do we have?",
             "sql": "SELECT COUNT(DISTINCT customer_id) FROM {orders} WHERE order_date >= (SELECT date_sub(MAX(order_date),90) FROM {orders})",
             "expect": "Ordered within 90 days of the latest order (our definition).",
             "trap_sql": "SELECT COUNT(DISTINCT customer_id) FROM {orders}",
             "trap_label": "agent counts ALL customers who ever ordered",
             "why_fail": "'active' is a business definition (ordered in the last 90 days) the agent can't know; it guesses the window or counts everyone."},
            {"q": "What is total revenue, excluding internal test accounts?",
             "sql": "SELECT ROUND(SUM(o.net_amount),2) FROM {orders} o JOIN {custs} c ON o.customer_id=c.customer_id JOIN {txns} t ON o.order_id=t.order_id WHERE c.is_internal=false AND t.status='COMPLETED'",
             "expect": "Completed revenue with is_internal=false.",
             "trap_sql": "SELECT ROUND(SUM(o.net_amount),2) FROM {orders} o JOIN {txns} t ON o.order_id=t.order_id WHERE t.status='COMPLETED'",
             "trap_label": "agent includes internal accounts (not excluded by default)",
             "why_fail": "the policy to exclude internal/test accounts by default is a business rule; the is_internal column exists but the agent won't filter on it unless instructed."},
        ],
        "why_b": (
            "These depend on business RULES not in the data: fiscal calendar (starts "
            "Feb 1), 'active customer' definition, and the default to exclude internal "
            "accounts. Those are instructions."
        ),
    },
    # ---- Step 6: instructions. Set B = genuinely impossible ----------- #
    6: {
        "title": "Step 6 — general instructions (rules, definitions, defaults, tone)",
        "set_a": [
            {"q": "What was revenue in the last fiscal quarter?",
             "sql": "SELECT ROUND(SUM(o.net_amount),2) FROM {orders} o JOIN {txns} t ON o.order_id=t.order_id WHERE t.status='COMPLETED' AND o.order_date BETWEEN '2026-05-01' AND '2026-07-31'",
             "expect": "Fiscal Q2 (May-Jul) — the instruction now defines the fiscal calendar."},
            {"q": "How many active customers do we have?",
             "sql": "SELECT COUNT(DISTINCT customer_id) FROM {orders} WHERE order_date >= (SELECT date_sub(MAX(order_date),90) FROM {orders})",
             "expect": "Ordered within 90 days of the latest order — now defined."},
            {"q": "What is total revenue (internal accounts excluded by default)?",
             "sql": "SELECT ROUND(SUM(o.net_amount),2) FROM {orders} o JOIN {custs} c ON o.customer_id=c.customer_id JOIN {txns} t ON o.order_id=t.order_id WHERE c.is_internal=false AND t.status='COMPLETED'",
             "expect": "Completed revenue excluding is_internal — now the default."},
        ],
        "why_a": (
            "Instructions encode the fiscal calendar, the active-customer definition, and "
            "the default exclusion of internal accounts."
        ),
        "set_b": [
            {"q": "Which marketing campaign drove the most revenue?",
             "sql": "",
             "expect": "No campaign data exists. Correct behavior: Genie declines.",
             "trap_label": "agent may invent a campaign or misuse order_channel as 'campaign'",
             "why_fail": "there is no campaign/attribution table anywhere in the schema — the data simply doesn't exist, so any specific answer is a hallucination."},
            {"q": "Forecast next quarter's revenue.",
             "sql": "",
             "expect": "Requires forecasting (not in scope). Genie should decline or state assumptions.",
             "trap_label": "agent may extrapolate naively and present it as fact",
             "why_fail": "forecasting needs a predictive model; Genie answers questions ABOUT existing data and cannot produce a real forecast."},
            {"q": "Why did margin drop in the West region — what's the root cause?",
             "sql": "",
             "expect": "Open-ended causal question; no ground truth. Genie can describe but not attribute cause.",
             "trap_label": "agent may state a correlation as if it were the cause",
             "why_fail": "root-cause attribution is a causal-analysis task, not a query; the data can show WHAT changed but not WHY."},
        ],
        "why_b": (
            "These need data we don't have (campaigns), predictive modeling (forecast), or "
            "causal analysis. No authoring fixes a missing-data / wrong-tool gap — the "
            "honest bridge to systematic evaluation (Workbench)."
        ),
    },
}
