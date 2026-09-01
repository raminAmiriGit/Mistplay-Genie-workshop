"""Genie space authoring for the workshop (Steps 2-7).

Self-contained, clean-room helper built against the **public** Genie spaces REST
API (`/api/2.0/genie/spaces`) and the GA `serialized_space` version 2 shape:

* ``POST   /api/2.0/genie/spaces``                             — create
* ``GET    /api/2.0/genie/spaces/{id}?include_serialized_space=true`` — fetch
* ``PATCH  /api/2.0/genie/spaces/{id}``                        — update

Two pieces:

* :class:`SpaceBuilder` — builds / round-trips the ``serialized_space`` JSON.
  Covers every surface the workshop touches, including the ones that have no
  one-line helper elsewhere (value-matching ``column_configs`` and the
  ``sql_snippets`` filters / expressions / measures).
* :class:`GenieClient` — thin wrapper over the Databricks SDK ``WorkspaceClient``
  (auto-authenticated inside a Databricks notebook) for create / get / patch.

Cross-notebook state (the created space id) is persisted to a small Delta table
``<catalog>.<schema>._genie_workshop_state`` so Steps 3-7 can find the space
that Step 2 created.
"""

from __future__ import annotations

import copy
import json
from typing import Any, Optional
from uuid import uuid4

STATE_TABLE = "_genie_workshop_state"
SPACE_ID_KEY = "genie_space_id"


# --------------------------------------------------------------------------- #
# serialized_space builder
# --------------------------------------------------------------------------- #
def _new_id() -> str:
    return uuid4().hex


def _as_lines(sql: str) -> list[str]:
    """Split a SQL string into keepends lines (matches exported shape)."""
    return sql.splitlines(keepends=True) or [sql]


def column_config(
    column_name: str,
    description: Optional[str] = None,
    synonyms: Optional[list[str]] = None,
    entity_matching: bool = False,
    format_assistance: bool = True,
) -> dict:
    """Build one ``column_configs`` entry (Step 3 value matching).

    * ``synonyms`` — alternate phrasings a user might type for the column.
    * ``entity_matching`` — index the column's distinct VALUES so Genie can map
      user text (e.g. "PayPal") to a stored code (e.g. 'PYPL').
    """
    cfg: dict[str, Any] = {"column_name": column_name}
    if description:
        cfg["description"] = [description]
    if synonyms:
        cfg["synonyms"] = list(synonyms)
    if entity_matching:
        cfg["enable_entity_matching"] = True
    if format_assistance:
        cfg["enable_format_assistance"] = True
    return cfg


class SpaceBuilder:
    """Build or round-trip a Genie ``serialized_space`` (version 2)."""

    def __init__(self, space: Optional[dict] = None) -> None:
        self._space: dict = copy.deepcopy(space) if space else {}
        self._space.setdefault("version", 2)

    # -- construction ------------------------------------------------------ #
    @classmethod
    def from_serialized(cls, serialized_space: Any) -> "SpaceBuilder":
        """Load from an API response dict or a serialized_space JSON string.

        Unknown fields are preserved so patches never drop server-side data.
        """
        if isinstance(serialized_space, dict):
            inner = serialized_space.get("serialized_space", serialized_space)
        else:
            inner = serialized_space
        if isinstance(inner, str):
            inner = json.loads(inner)
        return cls(space=inner)

    # -- nested-path helpers ---------------------------------------------- #
    def _list_at(self, *path: str) -> list:
        node = self._space
        for key in path[:-1]:
            node = node.setdefault(key, {})
        return node.setdefault(path[-1], [])

    # -- tables / metric views (data_sources.tables) ---------------------- #
    def add_table(self, identifier: str, column_configs: Optional[list[dict]] = None) -> "SpaceBuilder":
        tables = self._list_at("data_sources", "tables")
        entry = next((t for t in tables if t.get("identifier") == identifier), None)
        if entry is None:
            entry = {"identifier": identifier}
            tables.append(entry)
        if column_configs:
            # API requires column_configs sorted by column_name.
            entry["column_configs"] = sorted(column_configs, key=lambda c: c.get("column_name", ""))
        tables.sort(key=lambda t: t.get("identifier", ""))
        return self

    # A metric view is attached exactly like a table (same collection).
    add_metric_view = add_table

    def set_column_configs(self, identifier: str, column_configs: list[dict]) -> "SpaceBuilder":
        """Attach/replace value-matching column_configs on an existing table."""
        return self.add_table(identifier, column_configs=column_configs)

    # -- instructions.text_instructions (Step 6) -------------------------- #
    def set_instructions(self, text: str) -> "SpaceBuilder":
        self._space.setdefault("instructions", {})["text_instructions"] = [
            {"id": _new_id(), "content": [text]}
        ]
        return self

    # -- config.sample_questions ------------------------------------------ #
    def add_sample_question(self, question: str) -> "SpaceBuilder":
        self._list_at("config", "sample_questions").append(
            {"id": _new_id(), "question": [question]}
        )
        return self

    # -- instructions.example_question_sqls (Step 5) ---------------------- #
    def add_example_sql(self, question: str, sql: str, guidance: str = "") -> "SpaceBuilder":
        entry: dict[str, Any] = {
            "id": _new_id(),
            "question": [question],
            "sql": _as_lines(sql),
        }
        if guidance:
            entry["usage_guidance"] = [guidance]
        self._list_at("instructions", "example_question_sqls").append(entry)
        return self

    # -- instructions.sql_functions --------------------------------------- #
    def add_function(self, identifier: str) -> "SpaceBuilder":
        self._list_at("instructions", "sql_functions").append(
            {"id": _new_id(), "identifier": identifier}
        )
        return self

    # -- instructions.join_specs (Step 4/5) ------------------------------- #
    def add_join_spec(
        self,
        left_identifier: str,
        left_alias: str,
        right_identifier: str,
        right_alias: str,
        on_sql: str,
        relationship_type: str = "FROM_RELATIONSHIP_TYPE_MANY_TO_ONE",
    ) -> "SpaceBuilder":
        self._list_at("instructions", "join_specs").append(
            {
                "id": _new_id(),
                "left": {"identifier": left_identifier, "alias": left_alias},
                "right": {"identifier": right_identifier, "alias": right_alias},
                "sql": [on_sql, f"--rt={relationship_type}--"],
            }
        )
        return self

    # -- instructions.sql_snippets.{filters,expressions,measures} (Step 5) - #
    def _add_snippet(self, kind: str, sql: str, display_name: str,
                     instruction: str, synonyms: Optional[list[str]]) -> "SpaceBuilder":
        entry: dict[str, Any] = {
            "id": _new_id(),
            "sql": _as_lines(sql),
            "display_name": display_name,
            "instruction": [instruction],
        }
        if synonyms:
            entry["synonyms"] = list(synonyms)
        self._list_at("instructions", "sql_snippets", kind).append(entry)
        return self

    def add_filter(self, sql: str, display_name: str, instruction: str,
                   synonyms: Optional[list[str]] = None) -> "SpaceBuilder":
        return self._add_snippet("filters", sql, display_name, instruction, synonyms)

    def add_expression(self, sql: str, display_name: str, instruction: str,
                       synonyms: Optional[list[str]] = None) -> "SpaceBuilder":
        return self._add_snippet("expressions", sql, display_name, instruction, synonyms)

    def add_measure(self, sql: str, display_name: str, instruction: str,
                    synonyms: Optional[list[str]] = None) -> "SpaceBuilder":
        return self._add_snippet("measures", sql, display_name, instruction, synonyms)

    # -- benchmarks.questions (Step 7) ------------------------------------ #
    def add_benchmark(self, question: str, answer_sql: str = "") -> "SpaceBuilder":
        entry: dict[str, Any] = {"id": _new_id(), "question": [question]}
        if answer_sql:
            entry["answer"] = [{"format": "SQL", "content": _as_lines(answer_sql)}]
        self._list_at("benchmarks", "questions").append(entry)
        return self

    # -- output ------------------------------------------------------------ #
    # Every id-keyed collection must be exported sorted by id (API invariant).
    _ID_SORTED_PATHS = (
        ("config", "sample_questions"),
        ("instructions", "text_instructions"),
        ("instructions", "example_question_sqls"),
        ("instructions", "sql_functions"),
        ("instructions", "join_specs"),
        ("instructions", "sql_snippets", "filters"),
        ("instructions", "sql_snippets", "expressions"),
        ("instructions", "sql_snippets", "measures"),
        ("benchmarks", "questions"),
    )

    def to_dict(self) -> dict:
        out = copy.deepcopy(self._space)
        out.setdefault("version", 2)

        # tables sorted by identifier; their column_configs by column_name.
        tables = out.get("data_sources", {}).get("tables")
        if isinstance(tables, list):
            tables.sort(key=lambda t: t.get("identifier", ""))
            for t in tables:
                cfgs = t.get("column_configs")
                if isinstance(cfgs, list):
                    cfgs.sort(key=lambda c: c.get("column_name", ""))

        # all id-keyed lists sorted by id.
        for path in self._ID_SORTED_PATHS:
            node = out
            for key in path[:-1]:
                node = node.get(key) if isinstance(node, dict) else None
                if node is None:
                    break
            if isinstance(node, dict):
                lst = node.get(path[-1])
                if isinstance(lst, list):
                    lst.sort(key=lambda item: item.get("id", "") if isinstance(item, dict) else "")
        return out

    def to_serialized(self) -> str:
        return json.dumps(self.to_dict())

    def summary(self) -> str:
        d = self.to_dict()
        instr = d.get("instructions", {})
        snip = instr.get("sql_snippets", {})
        n_cfg = sum(len(t.get("column_configs", [])) for t in d.get("data_sources", {}).get("tables", []))
        return (
            f"tables={len(d.get('data_sources', {}).get('tables', []))} "
            f"column_configs={n_cfg} "
            f"examples={len(instr.get('example_question_sqls', []))} "
            f"joins={len(instr.get('join_specs', []))} "
            f"filters={len(snip.get('filters', []))} "
            f"expressions={len(snip.get('expressions', []))} "
            f"measures={len(snip.get('measures', []))} "
            f"instructions={len(instr.get('text_instructions', []))} "
            f"benchmarks={len(d.get('benchmarks', {}).get('questions', []))}"
        )


# --------------------------------------------------------------------------- #
# REST client (WorkspaceClient auto-auths inside a Databricks notebook)
# --------------------------------------------------------------------------- #
class GenieClient:
    def __init__(self, workspace_client=None) -> None:
        if workspace_client is None:
            from databricks.sdk import WorkspaceClient
            workspace_client = WorkspaceClient()
        self._w = workspace_client

    def create_space(self, title: str, description: str, parent_path: str,
                     warehouse_id: str, serialized_space: str) -> str:
        body = {
            "title": title,
            "description": description,
            "parent_path": parent_path,
            "warehouse_id": warehouse_id,
            "serialized_space": serialized_space,
        }
        resp = self._w.api_client.do("POST", "/api/2.0/genie/spaces", body=body)
        space_id = resp.get("space_id") or resp.get("id")
        if not space_id:
            raise RuntimeError(f"Create returned no space id: {resp}")
        return space_id

    def get_space(self, space_id: str) -> dict:
        return self._w.api_client.do(
            "GET",
            f"/api/2.0/genie/spaces/{space_id}",
            query={"include_serialized_space": "true"},
        )

    def patch_space(self, space_id: str, title: str, description: str,
                    warehouse_id: str, serialized_space: str) -> dict:
        body = {
            "title": title,
            "description": description,
            "warehouse_id": warehouse_id,
            "serialized_space": serialized_space,
        }
        return self._w.api_client.do("PATCH", f"/api/2.0/genie/spaces/{space_id}", body=body)

    def load_builder(self, space_id: str) -> SpaceBuilder:
        """Fetch a space and return a round-trip SpaceBuilder (preserves fields)."""
        resp = self.get_space(space_id)
        return SpaceBuilder.from_serialized(resp)

    def space_url(self, space_id: str) -> str:
        host = self._w.config.host.rstrip("/")
        return f"{host}/genie/rooms/{space_id}"


# --------------------------------------------------------------------------- #
# Cross-notebook state (Delta key/value table)
# --------------------------------------------------------------------------- #
def _state_fqn(cfg) -> str:
    return f"{cfg.full_schema}.{STATE_TABLE}"


def save_state(spark, cfg, key: str, value: str) -> None:
    fqn = _state_fqn(cfg)
    spark.sql(
        f"CREATE TABLE IF NOT EXISTS {fqn} (key STRING, value STRING, updated_at TIMESTAMP)"
    )
    spark.sql(f"DELETE FROM {fqn} WHERE key = '{key}'")
    esc = value.replace("'", "''")
    spark.sql(
        f"INSERT INTO {fqn} VALUES ('{key}', '{esc}', current_timestamp())"
    )


def load_state(spark, cfg, key: str) -> Optional[str]:
    fqn = _state_fqn(cfg)
    if not spark.catalog.tableExists(fqn):
        return None
    rows = spark.sql(f"SELECT value FROM {fqn} WHERE key = '{key}'").collect()
    return rows[0]["value"] if rows else None


def require_space_id(spark, cfg) -> str:
    space_id = load_state(spark, cfg, SPACE_ID_KEY)
    if not space_id:
        raise RuntimeError(
            "No Genie space id found. Run notebook 02 (create the Genie space) first."
        )
    return space_id
