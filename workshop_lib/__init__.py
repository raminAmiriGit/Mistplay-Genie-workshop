"""Databricks Genie Workshop — reusable library.

Thin notebooks (01..07) import from this package and call one function per step.
Nothing is hard-coded: every notebook resolves catalog / schema / warehouse from
widgets via :class:`workshop_lib.config.WorkshopConfig`, so each attendee runs the
same code in their own workspace.
"""

from .config import WorkshopConfig  # noqa: F401
