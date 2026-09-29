"""Workshop configuration — driven entirely by notebook widgets.

Every attendee runs in their own catalog / schema / workspace, so *nothing* is
hard-coded here. Each notebook calls :func:`setup_widgets` once (creates the
Databricks widgets) and then :meth:`WorkshopConfig.from_widgets` to read them.

Layer / table naming convention (all inside one schema):
  * bronze : ``<catalog>.<schema>.bronze_<name>``   (raw landing)
  * silver : ``<catalog>.<schema>.silver_<name>``   (cleaned / conformed)
  * gold   : ``<catalog>.<schema>.<dim|fact>_<name>`` (modeled star schema, Genie-facing)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

# Widget names — shared across every notebook so the workshop feels consistent.
WIDGET_CATALOG = "catalog"
WIDGET_SCHEMA = "schema"
WIDGET_WAREHOUSE_ID = "warehouse_id"
WIDGET_USER_EMAIL = "user_email"

# Defaults. Catalog is intentionally blank so each attendee must set their own.
DEFAULT_SCHEMA = "databricks_genie_workshop"
CONFIG_TABLE = "_workshop_config"
CONFIG_JSON = "_workshop_config.json"


def setup_widgets(dbutils) -> None:
    """Create the workshop widgets on the notebook (idempotent).

    Call this at the top of every notebook. ``dbutils`` is passed in from the
    notebook scope because it is not importable from a plain module.
    """
    dbutils.widgets.text(WIDGET_CATALOG, "", "1. Catalog (your catalog)")
    dbutils.widgets.text(WIDGET_SCHEMA, DEFAULT_SCHEMA, "2. Schema")
    dbutils.widgets.text(WIDGET_WAREHOUSE_ID, "", "3. SQL Warehouse ID (for Genie steps)")
    dbutils.widgets.text(WIDGET_USER_EMAIL, "", "4. Your email (Genie space owner/name)")


@dataclass
class WorkshopConfig:
    """Resolved, validated workshop configuration."""

    catalog: str
    schema: str = DEFAULT_SCHEMA
    warehouse_id: str = ""
    user_email: str = ""

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #
    @classmethod
    def from_widgets(cls, dbutils) -> "WorkshopConfig":
        """Read the widget values and build a validated config."""
        cfg = cls(
            catalog=dbutils.widgets.get(WIDGET_CATALOG).strip(),
            schema=(dbutils.widgets.get(WIDGET_SCHEMA).strip() or DEFAULT_SCHEMA),
            warehouse_id=dbutils.widgets.get(WIDGET_WAREHOUSE_ID).strip(),
            user_email=dbutils.widgets.get(WIDGET_USER_EMAIL).strip(),
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if not self.catalog:
            raise ValueError(
                "Catalog widget is empty. Set widget '1. Catalog' to a catalog you "
                "can create schemas in (e.g. your personal catalog)."
            )
        for part, label in ((self.catalog, "catalog"), (self.schema, "schema")):
            if not _is_valid_identifier(part):
                raise ValueError(
                    f"Invalid {label} name {part!r}: use letters, digits and "
                    f"underscores only (no hyphens or spaces)."
                )

    # ------------------------------------------------------------------ #
    # Name helpers
    # ------------------------------------------------------------------ #
    @property
    def full_schema(self) -> str:
        return f"{self.catalog}.{self.schema}"

    def bronze(self, name: str) -> str:
        return f"{self.full_schema}.bronze_{name}"

    def silver(self, name: str) -> str:
        return f"{self.full_schema}.silver_{name}"

    def gold(self, name: str) -> str:
        """Gold tables keep clean dimensional names (dim_/fact_ prefixes live in `name`)."""
        return f"{self.full_schema}.{name}"

    @property
    def genie_space_name(self) -> str:
        """Per-attendee Genie space name so 10-15 people don't collide."""
        suffix = self.user_email.split("@")[0].replace(".", "_") if self.user_email else "user"
        return f"databricks_genie_workshop_{suffix}"

    # ------------------------------------------------------------------ #
    # Persistence — save once in notebook 01, load everywhere else
    # ------------------------------------------------------------------ #
    def save_config(self, spark) -> str:
        """Persist config to a Delta table AND a local JSON pointer file.

        The Delta table holds the full config.  The JSON file (written next
        to the notebooks) stores only ``catalog`` + ``schema`` so that
        notebooks 02-06 can locate the table without any widgets.
        """
        self.ensure_schema(spark)
        fqn = f"{self.full_schema}.{CONFIG_TABLE}"
        from pyspark.sql import Row
        rows = [Row(key=k, value=v) for k, v in {
            "catalog": self.catalog,
            "schema": self.schema,
            "warehouse_id": self.warehouse_id,
            "user_email": self.user_email,
        }.items()]
        spark.createDataFrame(rows).write.mode("overwrite").saveAsTable(fqn)

        # Write a JSON pointer so downstream notebooks find the table
        # without needing any widgets.
        pointer_path = os.path.join(os.getcwd(), CONFIG_JSON)
        with open(pointer_path, "w") as f:
            json.dump({"catalog": self.catalog, "schema": self.schema}, f, indent=2)

        return fqn

    @classmethod
    def from_saved(cls, spark, catalog: str = "", schema: str = "") -> "WorkshopConfig":
        """Load config from the Delta table saved by notebook 01.

        When called **without** ``catalog`` / ``schema`` (the normal case
        for notebooks 02-06), the method reads the local JSON pointer file
        written by :meth:`save_config` to discover where the table lives.
        """
        if not catalog:
            pointer_path = os.path.join(os.getcwd(), CONFIG_JSON)
            try:
                with open(pointer_path) as f:
                    pointer = json.load(f)
                catalog = pointer["catalog"]
                schema = pointer.get("schema", DEFAULT_SCHEMA)
            except FileNotFoundError:
                raise FileNotFoundError(
                    f"Config pointer {pointer_path} not found. "
                    f"Run notebook 01 first to save the config."
                )
        schema = schema or DEFAULT_SCHEMA
        fqn = f"{catalog}.{schema}.{CONFIG_TABLE}"
        try:
            rows = {r["key"]: r["value"] for r in spark.table(fqn).collect()}
        except Exception as e:
            raise FileNotFoundError(
                f"Config table {fqn} not found. Run notebook 01 first to save the config."
            ) from e
        cfg = cls(
            catalog=rows.get("catalog", catalog),
            schema=rows.get("schema", schema),
            warehouse_id=rows.get("warehouse_id", ""),
            user_email=rows.get("user_email", ""),
        )
        cfg.validate()
        return cfg

    def ensure_schema(self, spark) -> None:
        """Create the catalog schema if it does not exist."""
        spark.sql(f"CREATE SCHEMA IF NOT EXISTS {self.full_schema}")

    def summary(self) -> str:
        return (
            f"catalog={self.catalog!r}  schema={self.schema!r}  "
            f"warehouse_id={self.warehouse_id or '(unset)'!r}  "
            f"genie_space={self.genie_space_name!r}"
        )


def _is_valid_identifier(name: str) -> bool:
    return bool(name) and name.replace("_", "").isalnum() and not name[0].isdigit()
