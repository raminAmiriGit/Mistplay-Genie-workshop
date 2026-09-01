"""Set A / Set B question banks per step, plus the Step 7 benchmark bank.

Teaching contract: each step ends with two sets.
  * SET A — the space can answer these NOW (proves the step's change worked).
  * SET B — the space still CANNOT answer these; the reason it fails is exactly
            what the NEXT step adds.  **Set B of step N == Set A of step N+1.**

Questions are written against the gold schema built in Step 1. They are phrased
in business language (as a real user would ask) — the point is whether Genie can
resolve them given what the space currently knows.
"""

from __future__ import annotations


def render(step: int) -> str:
    """Return a markdown block of the two question sets for a step."""
    q = QUESTIONS[step]
    lines = [f"### Try these in your Genie space\n", f"**{q['title']}**\n"]
    lines.append("#### ✅ Set A — should answer now\n")
    for i, item in enumerate(q["set_a"], 1):
        lines.append(f"{i}. {item}")
    lines.append(f"\n> _Why these work now: {q['why_a']}_\n")
    lines.append("#### ❌ Set B — will NOT answer yet\n")
    for i, item in enumerate(q["set_b"], 1):
        lines.append(f"{i}. {item}")
    lines.append(f"\n> _Why these fail: {q['why_b']}_  \n> _→ fixed in **Step {step + 1}**._")
    return "\n".join(lines)


QUESTIONS: dict[int, dict] = {
    # ------------------------------------------------------------------ #
    2: {
        "title": "Step 2 — bare space on gold tables (+ column comments)",
        "set_a": [
            "What is the total net revenue across all orders?",
            "How many orders were placed through each sales channel?",
            "Which product subcategory has the highest total net revenue?",
            "How many customers do we have in each segment?",
            "What is the average delivery time in days?",
        ],
        "why_a": (
            "These only need the gold tables plus the rich column comments from "
            "Step 1 — simple aggregations and single joins on well-described columns."
        ),
        "set_b": [
            "How much revenue came from payments made with PayPal?",
            "How many orders were paid by credit card?",
            "Show me the total value of gift-card transactions.",
            "What is total revenue in California?",
        ],
        "why_b": (
            "payment_method stores CODES (PYPL, CC, GIFT) with no lookup column, so "
            "Genie can't map 'PayPal' -> 'PYPL'. Likewise state_code stores 'CA', not "
            "'California'. Genie needs value matching / synonyms."
        ),
    },
    # ------------------------------------------------------------------ #
    3: {
        "title": "Step 3 — value matching (synonyms + entity matching)",
        "set_a": [
            "How much revenue came from payments made with PayPal?",
            "How many orders were paid by credit card?",
            "Show me the total value of gift-card transactions.",
            "What is total net revenue in California?",
            "How many orders shipped to Ontario?",
        ],
        "why_a": (
            "We added column descriptions, synonyms, and entity matching on the code "
            "columns (payment_method, currency, state_code). Genie now maps 'PayPal' -> "
            "'PYPL', 'credit card' -> 'CC', and 'California' -> 'CA'."
        ),
        "set_b": [
            "What is our on-time delivery rate by region?",
            "What is the gross margin percentage by product subcategory?",
            "What is the average order value this quarter?",
            "What is the refund rate as a percentage of completed revenue?",
        ],
        "why_b": (
            "These need governed BUSINESS MEASURES with consistent formulas across "
            "joined tables (rate = on_time / total; margin = (net-cogs)/net). Synonyms "
            "can't define math. That's a metric view."
        ),
    },
    # ------------------------------------------------------------------ #
    4: {
        "title": "Step 4 — metric view (measures + relationships + joins + filters)",
        "set_a": [
            "What is our on-time delivery rate by region?",
            "What is the gross margin percentage by product subcategory?",
            "What is the average order value by customer segment?",
            "What is total completed revenue by month?",
            "Compare gross margin % across sales channels.",
        ],
        "why_a": (
            "The metric view defines these measures once (on-time rate, gross margin %, "
            "AOV, completed revenue), with the orders<->products<->geography joins and a "
            "built-in filter that counts only COMPLETED transactions. Genie reuses them."
        ),
        "set_b": [
            "Which customers placed orders that never shipped?",
            "List orders where the payment was refunded but the item still shipped.",
            "What is revenue net of refunds (refunds counted as negative)?",
            "Show the top 10 customers by lifetime value including only completed orders.",
        ],
        "why_b": (
            "These need specific JOIN PATHS and EXCEPTION logic the metric view doesn't "
            "model: an anti-join (orders with no shipment), a refunded-but-shipped "
            "cross-check, refunds as negative revenue. Best taught with curated example "
            "queries and snippets."
        ),
    },
    # ------------------------------------------------------------------ #
    5: {
        "title": "Step 5 — curated examples (query, filter, measure, field, join)",
        "set_a": [
            "Which customers placed orders that never shipped?",
            "List orders that were refunded but still shipped.",
            "What is revenue net of refunds (refunds as negative)?",
            "Show high-value orders (net amount over $500).",
            "Break revenue down by age group of the customer.",
        ],
        "why_a": (
            "We added curated examples of all five types: example QUERIES (anti-join for "
            "unshipped, refunded-but-shipped), a FILTER (high-value orders), a MEASURE "
            "(net-of-refunds revenue), a FIELD (customer age group), and JOIN specs. "
            "Genie now follows these patterns."
        ),
        "set_b": [
            "What was our revenue last fiscal quarter?",
            "Show this quarter's numbers excluding internal test accounts.",
            "How many active customers do we have?",
            "Give me the standard KPI summary, and keep answers concise.",
        ],
        "why_b": (
            "These depend on business RULES & DEFINITIONS that aren't math or a single "
            "example: the fiscal calendar, 'exclude internal accounts by default', what "
            "'active customer' means, and answer tone. Those are general instructions."
        ),
    },
    # ------------------------------------------------------------------ #
    6: {
        "title": "Step 6 — general instructions (rules, definitions, defaults, tone)",
        "set_a": [
            "What was our revenue last fiscal quarter?",
            "Show this quarter's revenue (internal test accounts should be excluded).",
            "How many active customers do we have?",
            "Give me a concise KPI summary for last month.",
        ],
        "why_a": (
            "General instructions now encode the fiscal calendar, the default rule to "
            "exclude is_internal accounts, the definition of an 'active customer', and a "
            "concise answer style."
        ),
        "set_b": [
            "Which single marketing campaign drove the most incremental revenue?",
            "What's our forecested revenue for next quarter?",
            "Why did margins drop in the West region — root cause?",
        ],
        "why_b": (
            "These need data we don't have (campaign attribution), predictive modeling "
            "(forecast), or open-ended causal analysis. No amount of authoring fixes a "
            "missing-data / wrong-tool gap — a good place to discuss Genie's limits and "
            "move to systematic evaluation (Workbench)."
        ),
    },
}
