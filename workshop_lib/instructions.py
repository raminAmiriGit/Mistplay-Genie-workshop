"""Step 6: general (natural-language) instructions.

These encode business rules that are NOT math, a filter, a join, or a single
example — the things only free-text guidance can express:

* a fiscal-calendar definition (fiscal year starts Feb 1),
* a DEFAULT rule to exclude internal / test accounts,
* the definition of an "active customer",
* answer tone / format.

This is deliberately the "what's left" surface after Steps 3-5 — the workshop's
point is that instructions are the residual layer, used only when a structured
asset can't express the rule.
"""

from __future__ import annotations

INSTRUCTIONS = """\
General guidance for answering questions about this data:

- FISCAL CALENDAR: The fiscal year starts on February 1. Fiscal Q1 = Feb-Apr, \
Q2 = May-Jul, Q3 = Aug-Oct, Q4 = Nov-Jan. When the user says "fiscal quarter" \
or "fiscal year", use this calendar, not the standard calendar.
- DEFAULT EXCLUSIONS: By default, EXCLUDE internal/test accounts \
(dim_customers.is_internal = true) from all business metrics, unless the user \
explicitly asks to include them.
- REVENUE DEFINITION: "Revenue" means net_amount from orders whose payment is \
COMPLETED. Prefer the mv_order_analytics metric view for revenue, margin, and AOV.
- ACTIVE CUSTOMER: An "active customer" is one who has placed at least one order \
in the last 90 days.
- ON-TIME / DELIVERY: Use the mv_shipment_performance metric view for on-time \
rate and delivery-days questions.
- ANSWER STYLE: Be concise. Lead with the number, then a one-line explanation. \
State any filters you applied (e.g. "excluding internal accounts"). Show amounts \
with their currency.
"""


def add_instructions(builder) -> str:
    builder.set_instructions(INSTRUCTIONS)
    return INSTRUCTIONS
