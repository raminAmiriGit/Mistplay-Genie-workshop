"""Step 3: value matching — decode opaque codes + business jargon.

The gold data deliberately uses opaque values that agent mode cannot decode by
profiling:
  * payment_method — internal gateway codes PM01..PM04 (no lookup, not guessable),
  * state_code     — 'CA','ON',... with NO state_name column to join,
  * segment        — 'Corporate' etc., but users say "enterprise" / "B2B".

Value matching teaches Genie the meaning via three levers on `column_configs`:
  * description       — natural-language decode of the codes (the key lever),
  * synonyms          — alternate words users type for the column,
  * entity_matching   — index distinct values for fuzzy value resolution.

`add_value_matching(builder, cfg)` attaches configs to the tables already in the
space (round-trip: the notebook fetches the space, calls this, patches it back).
"""

from __future__ import annotations


def add_value_matching(builder, cfg) -> dict:
    from workshop_lib.genie_builder import column_config

    txn = cfg.gold("fact_transactions")
    geo = cfg.gold("dim_geography")
    cust = cfg.gold("dim_customers")

    txn_configs = [
        column_config(
            "payment_method",
            description=("Internal payment gateway code. PM01 = Credit Card, "
                        "PM02 = PayPal, PM03 = Gift Card, PM04 = Debit Card."),
            synonyms=["payment type", "payment method", "credit card", "paypal",
                      "gift card", "debit card"],
            entity_matching=True,
        ),
        column_config(
            "currency",
            description="ISO currency code. USD = US Dollars, CAD = Canadian Dollars.",
            synonyms=["us dollars", "canadian dollars"],
            entity_matching=True,
        ),
    ]

    geo_configs = [
        column_config(
            "state_code",
            description=("State or province code. CA = California, NY = New York, "
                        "TX = Texas, IL = Illinois, WA = Washington, FL = Florida, "
                        "MA = Massachusetts, ON = Ontario, QC = Quebec, "
                        "BC = British Columbia, AB = Alberta."),
            synonyms=["state", "province"],
            entity_matching=True,
        ),
    ]

    cust_configs = [
        column_config(
            "segment",
            description=("Customer segment. Corporate = enterprise / B2B clients, "
                        "SMB = small & mid-size businesses, Consumer = individual retail."),
            synonyms=["enterprise", "b2b", "small business", "individual", "retail"],
            entity_matching=True,
        ),
    ]

    builder.set_column_configs(txn, txn_configs)
    builder.set_column_configs(geo, geo_configs)
    builder.set_column_configs(cust, cust_configs)
    return {txn: len(txn_configs), geo: len(geo_configs), cust: len(cust_configs)}
