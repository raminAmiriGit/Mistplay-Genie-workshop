# Databricks Genie Workshop

A hands-on, fully code-generated workshop that walks attendees through **building a
Databricks Genie space and progressively optimizing it** — then feeds it into the
Genie benchmarking tooling.

Everything is **config-driven via notebook widgets** (catalog, schema, warehouse,
email), so each attendee runs the same package in **their own workspace** with
nothing hard-coded.

## How it's organized

Thin, cell-by-cell notebooks (`01`..`07`) each import the `workshop_lib` package and
call one function per step, so the logic is readable and reusable.

```
Databricks-Genie-workshop/
├── workshop_lib/
│   ├── config.py        # widgets → validated WorkshopConfig (catalog/schema/warehouse)
│   ├── data_gen.py      # synthetic raw data (orders / transactions / shipments)
│   ├── medallion.py     # bronze → silver → gold + rich table/column comments
│   ├── genie_builder.py # SpaceBuilder + REST client + cross-notebook state
│   ├── questions.py     # Set A / Set B question banks per step
│   ├── metric_view.py   # Step 4: two metric views (order + shipment grain)
│   ├── examples.py      # Step 5: all five example asset types
│   ├── instructions.py  # Step 6: general NL instructions
│   └── benchmarks.py    # Step 7: ~40 benchmark Q&A pairs
├── 01_data_and_medallion.ipynb
├── 02_create_genie_space.ipynb
├── 03_value_matching.ipynb
├── 04_metric_view.ipynb
├── 05_examples.ipynb
├── 06_instructions.ipynb
└── 07_benchmarks.ipynb
```

## Genie serialized_space invariants (learned the hard way)

The REST API validates `serialized_space` strictly. `SpaceBuilder.to_dict()`
enforces these automatically:
- `data_sources.tables` sorted by `identifier`
- each table's `column_configs` sorted by `column_name`
- every id-keyed collection (`join_specs`, `example_question_sqls`,
  `sql_snippets.*`, `benchmarks.questions`, `text_instructions`,
  `sample_questions`) sorted by `id`
- `version` stays at `2`

## The teaching arc

Each step improves the Genie space and ends with **two question sets**:
- **Set A** — what the space can answer *now* (proves the change worked).
- **Set B** — what it still *can't* answer (fails on purpose; the reason it fails is
  exactly what the next step adds). **Set B of step N = Set A of step N+1.**

| Step | Adds | Teaches |
|------|------|---------|
| 1 | Data + medallion + comments | Documented gold star schema |
| 2 | Bare Genie space on gold tables | Baseline; value-matching gap |
| 3 | Value matching / synonyms | `CA` → "California" |
| 4 | Metric view (measures + joins + filters) | Governed semantic layer |
| 5 | Example query / filter / measure / field / join | Teaching specific patterns & exceptions |
| 6 | General instructions | Tone, definitions, default rules |
| 7 | ~40 benchmark Q&A pairs pushed to the space | Objective evaluation input |

## Step 1 — data model (built on `metric_view_workshop`, enriched)

Gold star schema (all tables carry rich comments):

- **dim_customers** — segment, loyalty, `is_internal` flag (Step 6 default-exclude rule)
- **dim_products** — electronics catalog with `list_price` / `standard_cost` (margin)
- **dim_geography** — US states + Canadian provinces; **only `state_code`** (no
  `state_name` column, on purpose) so "California" must be taught in Step 3
- **fact_orders** — line-item grain: revenue, discount, COGS
- **fact_transactions** — payments with **opaque `payment_method` codes**
  (`PM01`–`PM04`, no lookup — agent mode can't decode them, the Step 3 lesson),
  `status` (COMPLETED/REFUNDED/FAILED/PENDING) and `currency` (USD/CAD)

### Designed to defeat Genie *agent mode*

Genie's deep-research/agent mode profiles column values and joins dimensions, so
easy Set B questions (e.g. "revenue in California") get answered before their
step. The data is deliberately **vague** where a value-matching lesson lives:
`payment_method` is opaque (`PM02`≠"PayPal" to any profiler) and there is no
`state_name` to join. Each step's Set B fails for a reason the *next* step fixes —
verified end-to-end by running all 7 notebooks in sequence.
- **fact_shipments** — carrier, delivery, `on_time_flag`; ~12% of orders never ship
  (Step 5 anti-join)

## Running it

Open each notebook in Databricks, set the widgets, and run cells top to bottom.
Start with `01_data_and_medallion.ipynb`.
